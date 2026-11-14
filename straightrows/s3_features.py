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


# True for each minute inside a labeled episode on that tractor.
def in_labeled_episode(minutes: pd.DataFrame, labels: pd.DataFrame) -> pd.Series:
    inside = pd.Series(False, index=minutes.index)

    # Mark each episode's minutes. Multipath labels last seconds, so start from their minute
    for episode in labels.to_dict("records"):
        on_tractor = minutes["tractor_id"].isin(episode["tractors"])
        in_time = (minutes["minute"] >= episode["start"].floor("min")) & (
            minutes["minute"] <= episode["end"]
        )
        inside = inside | (on_tractor & in_time)

    return inside


# Add how far each minute is below its tractor's normal.
def add_drop_from_normal(minutes: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    # Get each tractor's normal values from its working minutes outside labeled episodes
    usable = minutes["working"] & ~in_labeled_episode(minutes, labels)
    working_minutes = minutes[usable]
    normal_signal_mean = working_minutes.groupby("tractor_id")["signal_mean_db"].median()
    normal_signal_weakest = working_minutes.groupby("tractor_id")["signal_weakest_db"].median()
    normal_num_sats = working_minutes.groupby("tractor_id")["num_sats_min"].median()

    # Get the drop below normal. Bigger means worse
    minutes = minutes.copy()
    minutes["signal_mean_normal_db"] = minutes["tractor_id"].map(normal_signal_mean)
    minutes["signal_mean_drop_db"] = minutes["signal_mean_normal_db"] - minutes["signal_mean_db"]
    minutes["signal_weakest_drop_db"] = (
        minutes["tractor_id"].map(normal_signal_weakest) - minutes["signal_weakest_db"]
    )
    minutes["num_sats_drop"] = minutes["tractor_id"].map(normal_num_sats) - minutes["num_sats_min"]
    return minutes


# Add how the other working tractors did in the same minute.
def add_fleet_comparison(minutes: pd.DataFrame) -> pd.DataFrame:
    # Only count working tractors for the fleet
    own_drop = minutes["signal_mean_drop_db"].where(minutes["working"], 0)
    is_working = minutes["working"].astype(int)

    # Add up the whole fleet each minute
    fleet_total = own_drop.groupby(minutes["minute"]).transform("sum")
    fleet_count = is_working.groupby(minutes["minute"]).transform("sum")

    # Average drop of the other working tractors. Blank if no other tractor is working
    minutes = minutes.copy()
    others_count = (fleet_count - is_working).replace(0, float("nan"))
    minutes["fleet_signal_mean_drop_db"] = (fleet_total - own_drop) / others_count

    # True if another working tractor lost its base link that minute
    own_lost = (minutes["base_link_lost"] & minutes["working"]).astype(int)
    fleet_lost = own_lost.groupby(minutes["minute"]).transform("sum")
    minutes["fleet_base_link_lost"] = (fleet_lost - own_lost) > 0
    return minutes


# Make the minute table: summarize, compare to each tractor's normal, then to the fleet.
def minute_features(telemetry: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    minutes = summarize_minutes(telemetry)
    minutes = add_drop_from_normal(minutes, labels)
    return add_fleet_comparison(minutes)
