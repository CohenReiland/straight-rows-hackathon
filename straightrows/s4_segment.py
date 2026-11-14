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
# episodes. Not called yet: stretching waits for step 7 (D56).
def is_signal_weak(minutes: pd.DataFrame) -> pd.Series:
    return minutes["working"] & (
        (minutes["signal_mean_drop_db"] >= config.WEAK_MEAN_DROP_DB)
        | has_bad_fix(minutes)
    )


# True for working minutes with the base station link lost.
def is_link_bad(minutes: pd.DataFrame) -> pd.Series:
    return minutes["working"] & minutes["base_link_lost"]
