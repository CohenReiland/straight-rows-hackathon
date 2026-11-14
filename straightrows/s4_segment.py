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
# episodes.
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


# Move each episode's start back and end forward while the minutes next to it are
# weak. An episode never stretches into its neighbor on the same tractor.
def stretch_runs(
    runs: pd.DataFrame,
    weak_minutes: pd.DataFrame,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
) -> pd.DataFrame:
    # Set up the time steps
    one_minute = pd.Timedelta(minutes=1)
    max_stretch = pd.Timedelta(minutes=config.MAX_STRETCH_MIN)

    # Get the weak minutes of each tractor
    weak = set(zip(weak_minutes["tractor_id"], weak_minutes["minute"]))

    # Work on a copy, sorted so neighbors are next to each other
    runs = runs.sort_values(["tractor", "start"]).reset_index(drop=True)
    starts = list(runs["start"])
    ends = list(runs["end"])

    # Check one episode at a time
    for i in range(len(runs)):
        tractor = runs.at[i, "tractor"]

        # Get the limits: the window, the stretch cap, and the neighbors
        earliest = max(window_start, starts[i] - max_stretch)
        latest = min(window_end, ends[i] + max_stretch)
        if i > 0 and runs.at[i - 1, "tractor"] == tractor:
            earliest = max(earliest, ends[i - 1])
        if i + 1 < len(runs) and runs.at[i + 1, "tractor"] == tractor:
            latest = min(latest, starts[i + 1])

        # Step the start back while the minute before it is weak
        while (
            starts[i] - one_minute >= earliest
            and (tractor, starts[i] - one_minute) in weak
        ):
            starts[i] -= one_minute

        # Step the end forward while the minute at the end is weak
        while ends[i] + one_minute <= latest and (tractor, ends[i]) in weak:
            ends[i] += one_minute

    # Save the new edges
    runs["start"] = starts
    runs["end"] = ends

    # Stretched episodes can now meet their neighbors, so join those
    return join_touching(runs)


# Join episodes on the same tractor where one ends right as the next starts.
def join_touching(runs: pd.DataFrame) -> pd.DataFrame:
    joined = []
    for run in runs.to_dict("records"):
        # Get the last saved episode
        last = joined[-1] if joined else None

        # Extend it if this one touches it, otherwise save this one
        same_tractor = last is not None and last["tractor"] == run["tractor"]
        if same_tractor and run["start"] <= last["end"]:
            last["end"] = max(last["end"], run["end"])
        else:
            joined.append(run)

    return pd.DataFrame(joined, columns=runs.columns)


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


# Walk a drift's start back while the tractor was still climbing off the line.
def climb_start(rise: pd.Series, start: pd.Timestamp) -> pd.Timestamp:
    one_minute = pd.Timedelta(minutes=1)
    earlier = start
    while rise.get(earlier, 0) >= config.DRIFT_RISE_M:
        start = earlier
        earlier -= one_minute
    return start


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

        # Median and spread of each block, and the rise of each minute's median
        blocks = line_error.resample(block).agg(["median", "std"])
        rise = line_error.resample("1min").median().diff()

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
                start = climb_start(rise, start)
                drifts.append({"tractor": tractor, "start": start, "end": end})

    # Make the table and label the kind
    table = pd.DataFrame(drifts, columns=["tractor", "start", "end"])
    table["kind"] = "drift"
    return table


# Find the average drop jumping up on top of an episode already going on.
# Each step is its own candidate.
def find_steps(minutes: pd.DataFrame, window: str) -> pd.DataFrame:
    # Set up the window and the lookback
    window_start, window_end = config.WINDOWS[window]
    lookback = pd.Timedelta(minutes=config.STEP_LOOKBACK_MIN)
    shortest = pd.Timedelta(minutes=config.MIN_STEP_MIN)

    # Check one tractor at a time
    steps = []
    for tractor, rows in minutes.groupby("tractor_id"):
        rows = rows.set_index("minute").sort_index()
        drop = rows["signal_mean_drop_db"].where(rows["working"])

        # Each minute's level = median drop over the minutes before it, and the
        # lowest drop there, so a step only sits on an episode that filled them all
        before = drop.rolling(
            lookback, closed="left", min_periods=config.STEP_LOOKBACK_MIN // 2
        )
        level = before.median()
        lowest = before.min()

        # Walk the minutes. A step starts when the drop jumps well above a level
        # that was bad the whole lookback, and ends when it falls back near it
        runs = []
        start = None
        for minute, value in drop.items():
            if start is None:
                already_bad = lowest[minute] >= config.HEALTHY_MAX_DROP_DB
                if already_bad and value - level[minute] >= config.STEP_RISE_DB:
                    start, base = minute, level[minute]
            elif pd.isna(value) or value - base < config.STEP_RISE_DB:
                runs.append((start, minute))
                start = None
        if start is not None:
            runs.append((start, drop.index[-1] + pd.Timedelta(minutes=1)))

        # Keep the long enough steps that start in the window
        for start, end in runs:
            if end - start >= shortest and window_start <= start < window_end:
                steps.append({"tractor": tractor, "start": start, "end": end})

    # Make the table and label the kind
    table = pd.DataFrame(steps, columns=["tractor", "start", "end"])
    table["kind"] = "step"
    return table


# Find every candidate: link and signal episodes and steps from the minutes, dips
# and drifts from the seconds.
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

    # Stretch the signal episodes while the signal is still partly low
    weak = in_window[is_signal_weak(in_window)]
    signal = stretch_runs(signal, weak, window_start, window_end)

    # Find the short dips for multipath and the smooth drifts for spoofing
    dips = find_dips(telemetry, window)
    drifts = find_drifts(telemetry, window)

    # Find steps from all minutes, so the lookback can reach before the window
    steps = find_steps(minutes, window)

    # Put the non-empty ones in one table
    tables = [link, signal, steps, dips, drifts]
    return pd.concat([table for table in tables if not table.empty], ignore_index=True)
