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
    lookback = pd.Timedelta(minutes=config.FLICKER_LOOKBACK_MIN)
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
