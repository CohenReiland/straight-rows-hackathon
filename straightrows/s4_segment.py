# Stage 4: find runs of bad minutes on each tractor.

import pandas as pd

from . import config


# True for minutes where the fix dropped below RTK_FIXED while the link was fine.
# A lost link also drops the fix, so those minutes are left to the link check.
def has_bad_fix(minutes: pd.DataFrame) -> pd.Series:
    fix_dropped = minutes["fix_rank_worst"] < config.FIX_RANK["RTK_FIXED"]
    return fix_dropped & ~minutes["base_link_lost"]


# True for working minutes with a bad signal, position, or fix.
def is_signal_bad(minutes: pd.DataFrame) -> pd.Series:
    return minutes["working"] & (
        (minutes["signal_weakest_drop_db"] > config.BAD_WEAKEST_DROP_DB)
        | (minutes["cross_track_error_max_m"] > config.BAD_CROSS_TRACK_ERROR_M)
        | has_bad_fix(minutes)
    )


# True for working minutes that are still partially off the normal, used to stretch
# episodes. Not called yet: stretching waits for step 7.
def is_signal_weak(minutes: pd.DataFrame) -> pd.Series:
    return minutes["working"] & (
        (minutes["signal_mean_drop_db"] >= config.WEAK_MEAN_DROP_DB)
        | has_bad_fix(minutes)
    )


# True for working minutes with the base station link lost.
def is_link_bad(minutes: pd.DataFrame) -> pd.Series:
    return minutes["working"] & minutes["base_link_lost"]


# Join one kind of bad minutes into episodes, allowing small gaps.
def find_runs(
    bad_minutes: pd.DataFrame, window_end: pd.Timestamp, kind: str
) -> pd.DataFrame:
    # Set up the time steps
    max_gap = pd.Timedelta(minutes=config.MAX_GAP_MIN)
    one_minute = pd.Timedelta(minutes=1)

    # Check one tractor at a time
    candidates = []
    for tractor, tractor_minutes in bad_minutes.groupby("tractor_id"):
        start = last_minute = None

        # Go through its bad minutes in order
        for minute in tractor_minutes["minute"]:
            # A big gap ends the episode
            if start is not None and minute - last_minute > max_gap:
                candidates.append(
                    {
                        "tractor": tractor,
                        "start": start,
                        "end": last_minute + one_minute,
                    }
                )
                start = None

            # Start a new episode if none is open
            if start is None:
                start = minute

            # Remember this minute
            last_minute = minute

        # Save the last episode
        end = min(last_minute + one_minute, window_end)
        candidates.append({"tractor": tractor, "start": start, "end": end})

    # Make the table and label the kind
    table = pd.DataFrame(candidates, columns=["tractor", "start", "end"])
    table["kind"] = kind
    return table


# Find short dips of the weakest satellite in the 1-second data, for multipath.
def find_dips(telemetry: pd.DataFrame, window: str) -> pd.DataFrame:
    # Set up the window and the normal for each second
    window_start, window_end = config.WINDOWS[window]
    normal_size = config.DIP_NORMAL_WINDOW_S + 1
    one_second = pd.Timedelta(seconds=1)

    # Check one tractor at a time
    dips = []
    for tractor, seconds in telemetry.groupby("tractor_id"):
        seconds = seconds.sort_values("ts").reset_index(drop=True)

        # Normal = median of the weakest satellite over the seconds around it
        weakest = seconds["signal_weakest_db"]
        normal = weakest.rolling(
            normal_size, center=True, min_periods=normal_size // 4
        ).median()

        # Seconds well under that normal while working
        low = seconds["working"] & (normal - weakest >= config.DIP_DROP_DB)

        # Number each run of low seconds, then keep the long enough ones
        run_number = (low != low.shift()).cumsum()
        for _, run in seconds[low].groupby(run_number[low]):
            if len(run) < config.MIN_DIP_S:
                continue
            start = run["ts"].iloc[0]
            if window_start <= start < window_end:
                end = run["ts"].iloc[-1] + one_second
                dips.append({"tractor": tractor, "start": start, "end": end})

    # Make the table and label the kind
    table = pd.DataFrame(dips, columns=["tractor", "start", "end"])
    table["kind"] = "dip"
    return table


# Find smooth drifts off the line, each its own candidate.
def find_drifts(telemetry: pd.DataFrame, window: str) -> pd.DataFrame:
    # Set up the window and the block size
    window_start, window_end = config.WINDOWS[window]
    block = pd.Timedelta(minutes=config.DRIFT_BLOCK_MIN)
    max_step = block * (config.DRIFT_MAX_GAP_BLOCKS + 1)

    # Check one tractor at a time, using only working seconds
    drifts = []
    working = telemetry[telemetry["working"]]
    for tractor, seconds in working.groupby("tractor_id"):
        line_error = seconds.set_index("ts")["cross_track_error_m"]

        # Median and spread of each block
        blocks = line_error.resample(block).agg(["median", "std"])

        # A block drifts if it is far off the line but steady, unlike noise
        drifting = blocks[
            (blocks["median"] >= config.DRIFT_MEDIAN_M)
            & (blocks["std"] < config.DRIFT_SPREAD_M)
        ].index.to_series()

        # Start a new drift when the gap to the last drifting block is too big
        run_number = (drifting.diff() > max_step).cumsum()
        for _, run in drifting.groupby(run_number):
            start = run.iloc[0]
            if window_start <= start < window_end:
                end = run.iloc[-1] + block
                drifts.append({"tractor": tractor, "start": start, "end": end})

    # Make the table and label the kind
    table = pd.DataFrame(drifts, columns=["tractor", "start", "end"])
    table["kind"] = "drift"
    return table


# Find every candidate: link and signal episodes from the minutes, dips from the
# seconds.
def find_candidates(
    minutes: pd.DataFrame, telemetry: pd.DataFrame, window: str
) -> pd.DataFrame:
    # Keep the minutes in this window
    window_start, window_end = config.WINDOWS[window]
    in_window = minutes[
        (minutes["minute"] >= window_start) & (minutes["minute"] < window_end)
    ]

    # Find the link and signal episodes separately
    link = find_runs(in_window[is_link_bad(in_window)], window_end, "link")
    signal = find_runs(in_window[is_signal_bad(in_window)], window_end, "signal")

    # Find the short dips for multipath
    dips = find_dips(telemetry, window)

    # Put them in one table
    return pd.concat([link, signal, dips], ignore_index=True)
