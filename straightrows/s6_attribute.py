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
    # Get this episode's minutes, including the minute a dip starts in
    episode_minutes = minutes[
        (minutes["tractor_id"] == candidate["tractor"])
        & (minutes["minute"] >= candidate["start"].floor("min"))
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
        "fleet_worst_signal_mean_drop_db": episode_minutes[
            "fleet_worst_signal_mean_drop_db"
        ].mean(),
        "signal_flicker_s4_max": nearby_flicker["signal_flicker_s4"].max(),
    }


# Return the causes this candidate passes.
def passing_causes(numbers: dict, kind: str) -> list[str]:
    # Facts several tests share
    short = numbers["duration_min"] <= config.SHORT_EPISODE_MIN

    # Healthy means the average barely dropped and the weakest satellite stayed up
    healthy = (
        numbers["signal_mean_drop_max_db"] < config.HEALTHY_MAX_DROP_DB
        and numbers["signal_weakest_drop_median_db"] < config.BAD_WEAKEST_DROP_DB
    )

    # Fleet is fine if no other tractor was working, or even the worst barely dropped
    fleet_drop = numbers["fleet_worst_signal_mean_drop_db"]
    fleet_ok = pd.isna(fleet_drop) or fleet_drop < config.FLEET_OK_DROP_DB

    # A dip is only ever multipath
    if kind == "dip":
        return ["MULTIPATH"]

    # A link episode only tests the link causes
    if kind == "link":
        cause_tests = {"MULTIPATH": short, "EQUIPMENT_FAULT": not short}
        return [cause for cause, passed in cause_tests.items() if passed]

    # Storms make the signal flicker, jamming doesn't
    high_flicker = numbers["signal_flicker_s4_max"] >= config.HIGH_FLICKER_S4

    # Regional means the other tractors dropped too
    regional = not short and not healthy and not fleet_ok

    # Far off the line, with the base link fine (a lost link explains the drift)
    off_line = numbers["cross_track_error_max_m"] > config.BAD_CROSS_TRACK_ERROR_M
    link_fine = not numbers["base_link_lost"]

    # One test per cause
    cause_tests = {
        "MULTIPATH": short,
        "EQUIPMENT_FAULT": not short and not healthy and fleet_ok,
        "SPACE_WEATHER": regional and high_flicker,
        "SPOOFING": not short and healthy and off_line and link_fine,
        "JAMMING": regional and not high_flicker,
    }

    # Keep the causes that passed
    return [cause for cause, passed in cause_tests.items() if passed]


# Measure and test every candidate.
def test_candidates(
    candidates: pd.DataFrame,
    minutes: pd.DataFrame,
    telemetry: pd.DataFrame,
    space_feeds: dict,
) -> pd.DataFrame:
    # Check each candidate
    tested = []
    for candidate in candidates.to_dict("records"):
        # Get its numbers
        numbers = measure(
            candidate, minutes, telemetry, space_feeds["signal_flicker_s4"]
        )

        # Save its numbers and passing causes
        passed = passing_causes(numbers, candidate["kind"])
        tested.append({**candidate, **numbers, "passed": passed})

    # Make the table
    return pd.DataFrame(tested)
