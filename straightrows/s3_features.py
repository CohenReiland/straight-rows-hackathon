# Stage 3: summarize the telemetry per tractor per minute.

import pandas as pd

from . import config


# Make one row per tractor per minute.
def summarize_minutes(telemetry: pd.DataFrame) -> pd.DataFrame:
    # Stop if a fix state has no rank
    unknown = set(telemetry["fix_state"]) - set(config.FIX_RANK)
    if unknown:
        raise ValueError(f"Unknown fix states {sorted(unknown)}. Add them to config.FIX_RANK.")

    # Add the helper columns to a copy
    with_helpers = telemetry.assign(
        minute=telemetry["ts"].dt.floor("min"),
        fix_rank=telemetry["fix_state"].map(config.FIX_RANK),
        base_link_lost=~telemetry["base_link_ok"],
        cross_track_error_abs_m=telemetry["cross_track_error_m"].abs(),
    )

    # Summarize each minute
    minutes = (
        with_helpers.groupby(["tractor_id", "minute"])
        .agg(
            working_share=("working", "mean"),
            signal_mean_db=("signal_mean_db", "mean"),
            signal_weakest_db=("signal_weakest_db", "min"),
            num_sats_min=("num_sats", "min"),
            fix_rank_worst=("fix_rank", "min"),
            base_link_lost=("base_link_lost", "any"),
            cross_track_error_max_m=("cross_track_error_abs_m", "max"),
        )
        .reset_index()
    )

    # A minute is working if most of its seconds moving
    minutes.insert(2, "working", minutes.pop("working_share") > config.WORKING_MINUTE_SHARE)
    return minutes
