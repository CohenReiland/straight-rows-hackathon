# Stage 6: run the five cause tests on each candidate.

import pandas as pd

from . import config


# Get the numbers the cause tests need.
def measure(
    candidate: dict,
    minutes: pd.DataFrame,
    telemetry: pd.DataFrame,
    signal_flicker: pd.DataFrame,
) -> dict:
    # Get this episode's minutes
    episode_minutes = minutes[
        (minutes["tractor_id"] == candidate["tractor"])
        & (minutes["minute"] >= candidate["start"])
        & (minutes["minute"] < candidate["end"])
    ]

    # Get the signal flicker readings near the episode
    lookback = pd.Timedelta(minutes=config.FLICKER_LOOKBACK_MIN_S4)
    nearby_flicker = signal_flicker[
        (signal_flicker["ts"] >= candidate["start"] - lookback)
        & (signal_flicker["ts"] < candidate["end"])
    ]

    # Get this episode's seconds, for where the tractor was
    seconds = telemetry[
        (telemetry["tractor_id"] == candidate["tractor"])
        & (telemetry["ts"] >= candidate["start"])
        & (telemetry["ts"] < candidate["end"])
    ]

    # Share of minutes with a large cross-track error
    line_error = episode_minutes["cross_track_error_max_m"]
    off_line = line_error > config.BAD_CROSS_TRACK_ERROR_M

    # Return the worst value of each signal
    return {
        "duration_min": (candidate["end"] - candidate["start"]).total_seconds() / 60,
        "collapse_s": collapse_seconds(
            second_drops(candidate, episode_minutes, telemetry)
        ),
        "signal_weakest_min_db": episode_minutes["signal_weakest_db"].min(),
        "signal_mean_drop_max_db": episode_minutes["signal_mean_drop_db"].max(),
        "signal_weakest_drop_median_db": episode_minutes[
            "signal_weakest_drop_db"
        ].median(),
        "num_sats_drop_max": episode_minutes["num_sats_drop"].max(),
        "num_sats_min": episode_minutes["num_sats_min"].min(),
        "cross_track_error_high_share": off_line.mean(),
        "cross_track_error_max_m": line_error.max(),
        "base_link_lost": bool(episode_minutes["base_link_lost"].any()),
        "fleet_base_link_lost": bool(episode_minutes["fleet_base_link_lost"].any()),
        "lat": seconds["lat"].mean(),
        "lon": seconds["lon"].mean(),
        "fleet_signal_mean_drop_db": episode_minutes[
            "fleet_signal_mean_drop_db"
        ].mean(),
        "signal_flicker_s4_max": nearby_flicker["signal_flicker_s4"].max(),
    }


# Get the average signal's drop below normal each second, from a bit before the episode.
def second_drops(
    candidate: dict, episode_minutes: pd.DataFrame, telemetry: pd.DataFrame
) -> list[float]:
    # Get the seconds, with a few minutes before the start
    lead_in = pd.Timedelta(minutes=config.COLLAPSE_LEAD_IN_MIN)
    seconds = telemetry[
        (telemetry["tractor_id"] == candidate["tractor"])
        & (telemetry["ts"] >= candidate["start"] - lead_in)
        & (telemetry["ts"] < candidate["end"])
    ]

    # Drop below this tractor's normal
    normal = episode_minutes["signal_mean_normal_db"].iloc[0]
    drops = normal - seconds["signal_mean_db"]

    # Smooth out the noise (counts rows, so it relies on one row per second)
    smooth = drops.rolling(config.COLLAPSE_SMOOTH_S, center=True, min_periods=1)
    return smooth.median().tolist()



# Seconds the drop took to rise from 20% to 80% of its worst.
# None if it never really dropped.
def collapse_seconds(drops: list[float]) -> int | None:
    # Skip episodes without a real drop
    worst = max(drops, default=0)
    if not worst >= config.MIN_COLLAPSE_DROP_DB:
        return None

    # Find the first second past each share of the worst drop
    rise_start = rise_end = None
    for second, drop in enumerate(drops):
        if rise_start is None and drop >= config.COLLAPSE_FROM_SHARE * worst:
            rise_start = second
        if drop >= config.COLLAPSE_TO_SHARE * worst:
            rise_end = second
            break

    # Seconds between the two
    return rise_end - rise_start
