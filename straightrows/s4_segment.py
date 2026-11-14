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


# Join bad minutes into episodes, one list for each kind.
def find_candidates(minutes: pd.DataFrame, window: str) -> pd.DataFrame:
    # Keep the minutes in this window
    window_start, window_end = config.WINDOWS[window]
    in_window = minutes[
        (minutes["minute"] >= window_start) & (minutes["minute"] < window_end)
    ]

    # Find the link and signal episodes separately
    link = find_runs(in_window[is_link_bad(in_window)], window_end, "link")
    signal = find_runs(in_window[is_signal_bad(in_window)], window_end, "signal")

    # Put them in one table
    return pd.concat([link, signal], ignore_index=True)
