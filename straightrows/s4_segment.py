# Stage 4: find runs of bad minutes on each tractor.

import pandas as pd

from . import config


# True for working minutes with a bad signal, position, or fix.
def is_signal_bad(minutes: pd.DataFrame) -> pd.Series:
    # A lost link also drops the fix, so only count the fix when the link is fine
    bad_fix = (minutes["fix_rank_worst"] < config.FIX_RANK["RTK_FIXED"]) & ~minutes[
        "base_link_lost"
    ]

    return minutes["working"] & (
        (minutes["signal_weakest_drop_db"] > config.BAD_WEAKEST_DROP_DB)
        | (minutes["cross_track_error_max_m"] > config.BAD_CROSS_TRACK_ERROR_M)
        | bad_fix
    )


# True for working minutes that are still partially off the normal, used to stretch episodes.
def is_signal_weak(minutes: pd.DataFrame) -> pd.Series:
    # Same fix check as above
    bad_fix = (minutes["fix_rank_worst"] < config.FIX_RANK["RTK_FIXED"]) & ~minutes[
        "base_link_lost"
    ]

    return minutes["working"] & (
        (minutes["signal_mean_drop_db"] >= config.WEAK_MEAN_DROP_DB) | bad_fix
    )
