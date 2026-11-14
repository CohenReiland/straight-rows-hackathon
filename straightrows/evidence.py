# Stage 7 helper: check the signs for a detection's cause, score the confidence,
# and write evidence in clean sentences that read on their own.

import math

import pandas as pd

from . import config


# Make one sign. kind is "for", "bonus", or "against".
def sign(kind: str, seen: bool, label: str, detail: str) -> dict:
    return {"kind": kind, "seen": bool(seen), "label": label, "detail": detail}


# Signs for spoofing: off the row while the signal and the link look fine.
def spoofing_signs(rows: pd.DataFrame) -> list[dict]:
    # Worst values across the detection's candidates
    off_row_m = rows["cross_track_error_max_m"].max()
    average_drop = rows["signal_mean_drop_max_db"].max()
    weakest_drop = rows["signal_weakest_drop_median_db"].max()
    sats_drop = rows["num_sats_drop_max"].max()

    # Healthy means the average barely dropped and the weakest satellite stayed up
    healthy = (
        average_drop < config.HEALTHY_MAX_DROP_DB
        and weakest_drop < config.BAD_WEAKEST_DROP_DB
    )

    return [
        sign(
            "for",
            healthy,
            "off its row while the satellite signals stayed normal",
            f"up to {off_row_m:.1f} m off; average signal strength at most "
            f"{average_drop:.1f} dB below usual, normal is under "
            f"{config.HEALTHY_MAX_DROP_DB:.0f} dB",
        ),
        sign(
            "for",
            (rows["kind"] == "drift").any(),
            "drifted away from the row smoothly instead of jumping around",
            f"distance off the row moved less than {config.DRIFT_SPREAD_M} m "
            f"within each {config.DRIFT_BLOCK_MIN}-minute block",
        ),
        sign(
            "for",
            not rows["base_link_lost"].any(),
            "correction link from the base station stayed up",
            "a lost link can also pull the position off, so this rules it out",
        ),
        sign(
            "for",
            sats_drop <= config.SATS_NORMAL_DROP,
            "satellite count stayed normal",
            "none lost" if sats_drop <= 0 else f"at most {sats_drop:.0f} below usual",
        ),
    ]


# Distance between two points on the ground, in km.
def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    # Turn the differences into radians
    lat_change = math.radians(lat2 - lat1)
    lon_change = math.radians(lon2 - lon1)

    # Haversine formula
    a = (
        math.sin(lat_change / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(lon_change / 2) ** 2
    )
    return 2 * config.EARTH_RADIUS_KM * math.asin(math.sqrt(a))


# Readings of a storm feed from a few hours before the start to the end.
def storm_readings(
    feed: pd.DataFrame, column: str, start: pd.Timestamp, end: pd.Timestamp
) -> pd.Series:
    lead_in = pd.Timedelta(hours=config.STORM_LEAD_IN_H)
    nearby = feed[(feed["ts"] >= start - lead_in) & (feed["ts"] < end)]
    return nearby[column]


# Space weather advisories issued in the hours before the start.
def storm_advisories(advisories: pd.DataFrame, start: pd.Timestamp) -> pd.DataFrame:
    lead_in = pd.Timedelta(hours=config.ADVISORY_LEAD_IN_H)
    recent = (advisories["issued"] >= start - lead_in) & (advisories["issued"] <= start)
    return advisories[recent & (advisories["type"] == "SPACE_WEATHER")]


# Interference reports that arrived soon after the start, close enough to the tractors.
def nearby_reports(
    reports: pd.DataFrame, start: pd.Timestamp, lat: float, lon: float
) -> list[dict]:
    # Reports come in late, so look a while after the start
    latest = start + pd.Timedelta(minutes=config.REPORT_MAX_DELAY_MIN)

    # Keep reports in time whose area reaches the tractors
    found = []
    for report in reports.to_dict("records"):
        if not start <= report["received"] <= latest:
            continue
        away_km = distance_km(lat, lon, report["lat"], report["lon"])
        if away_km <= report["area_long_km"] + config.REPORT_EXTRA_KM:
            found.append({**report, "away_km": away_km})

    return found


# Describe the interference reports in plain words.
def describe_reports(found: list[dict], start: pd.Timestamp) -> str:
    # Say none came
    if not found:
        return f"none within {config.REPORT_MAX_DELAY_MIN} min of the start"

    # List each report with its delay, distance, and confidence
    parts = []
    for report in found:
        delay_min = (report["received"] - start).total_seconds() / 60
        parts.append(
            f"{report['report_id']} arrived {delay_min:.0f} min after the start, "
            f"{report['away_km']:.1f} km away, its own confidence "
            f"{report['confidence']}"
        )
    return "; ".join(parts)


# Signs for space weather: strong flicker on several tractors during a storm.
def space_weather_signs(rows: pd.DataFrame, feeds: dict) -> list[dict]:
    # Times, tractors, and place of the detection
    start = rows["start"].min()
    end = rows["end"].max()
    tractors = sorted(rows["tractor"].unique())

    # Storm feed readings around the detection
    flicker = rows["signal_flicker_s4_max"].max()
    storm_kp = storm_readings(feeds["storm_kp"], "storm_kp", start, end).max()
    field_drop = storm_readings(
        feeds["storm_field_drop"], "storm_field_drop_nt", start, end
    ).min()
    advisories = storm_advisories(feeds["advisories"], start)
    reports = nearby_reports(
        feeds["interference_reports"], start, rows["lat"].mean(), rows["lon"].mean()
    )

    # Name the advisories, if any
    if advisories.empty:
        advisory_text = f"none in the {config.ADVISORY_LEAD_IN_H} h before the start"
    else:
        advisory_text = ", ".join(
            f"{a['advisory_id']} issued {a['issued']:%m-%d %H:%M} UTC"
            for a in advisories.to_dict("records")
        )

    return [
        sign(
            "for",
            flicker >= config.HIGH_FLICKER_S4,
            "satellite signals flickering, a sign of a space storm",
            f"highest signal flicker (S4) {flicker:.2f} near the start, "
            f"storm level is {config.HIGH_FLICKER_S4} or more",
        ),
        sign(
            "for",
            len(tractors) >= 2,
            "several tractors hit at once",
            ", ".join(tractors),
        ),
        sign(
            "for",
            storm_kp >= config.STORM_KP,
            "storm level high",
            f"highest storm level (Kp) {storm_kp:.1f} from "
            f"{config.STORM_LEAD_IN_H} h before the start, a storm is "
            f"{config.STORM_KP} or more",
        ),
        sign(
            "for",
            field_drop <= config.STORM_FIELD_DROP_NT,
            "Earth's magnetic field dropped",
            f"lowest magnetic field drop (Dst) {field_drop:.0f} nT, a storm is "
            f"{config.STORM_FIELD_DROP_NT} nT or lower",
        ),
        sign(
            "bonus",
            flicker >= config.STRONG_FLICKER_S4,
            "strong flicker",
            f"{flicker:.2f}, strong is {config.STRONG_FLICKER_S4} or more",
        ),
        sign(
            "bonus",
            not advisories.empty,
            "space weather advisory issued before the start",
            advisory_text,
        ),
        sign(
            "against",
            reports,
            "interference report nearby, which points to jamming instead",
            describe_reports(reports, start),
        ),
    ]


# Signs for jamming: several tractors lose signal at once without a space storm.
def jamming_signs(rows: pd.DataFrame, feeds: dict) -> list[dict]:
    # Times, tractors, and nearby interference reports
    start = rows["start"].min()
    tractors = sorted(rows["tractor"].unique())
    reports = nearby_reports(
        feeds["interference_reports"], start, rows["lat"].mean(), rows["lon"].mean()
    )

    # During a storm, the sign is a further drop on top of it on every tractor
    stepped = sorted(rows.loc[rows["kind"] == "step", "tractor"].unique())
    if stepped:
        storm_sign = sign(
            "for",
            len(stepped) >= 2 and stepped == tractors,
            "signal dropped further on top of the space storm, on every tractor "
            "at once",
            f"average signal fell at least {config.STEP_RISE_DB:.0f} dB below its "
            f"level over the {config.STEP_LOOKBACK_MIN} min before, on "
            f"{', '.join(stepped)}",
        )
    # Otherwise, the sign is flicker staying low, which rules out a storm
    else:
        flicker = rows["signal_flicker_s4_max"].max()
        storm_sign = sign(
            "for",
            flicker < config.HIGH_FLICKER_S4,
            "satellite signals not flickering, which rules out a space storm",
            f"highest signal flicker (S4) {flicker:.2f} near the start, "
            f"storm level is {config.HIGH_FLICKER_S4} or more",
        )

    return [
        sign(
            "for",
            len(tractors) >= 2,
            "several tractors hit at once",
            ", ".join(tractors),
        ),
        storm_sign,
        sign(
            "bonus",
            reports,
            "interference report nearby",
            describe_reports(reports, start)
            + (
                ""
                if reports
                else "; reports are often missing, so this is not "
                "counted against jamming"
            ),
        ),
    ]


# Signs for an equipment fault: one tractor goes bad while the others are fine.
def equipment_fault_signs(rows: pd.DataFrame, feeds: dict) -> list[dict]:
    # Times, tractors, and nearby interference reports
    start = rows["start"].min()
    tractors = sorted(rows["tractor"].unique())
    reports = nearby_reports(
        feeds["interference_reports"], start, rows["lat"].mean(), rows["lon"].mean()
    )

    # A lost correction link and a failing antenna have different signs
    if rows["base_link_lost"].any():
        others_lost = rows["fleet_base_link_lost"].any()
        machine_sign = sign(
            "for",
            not others_lost,
            "correction link from the base station lost on this tractor only",
            "the other tractors' links "
            + ("were lost too" if others_lost else "stayed up"),
        )
    else:
        sats_drop = rows["num_sats_drop_max"].max()
        weakest_drop = rows["signal_weakest_drop_median_db"].max()
        machine_sign = sign(
            "for",
            sats_drop > config.SATS_NORMAL_DROP
            or weakest_drop >= config.BAD_WEAKEST_DROP_DB,
            "satellites lost or weakened on this tractor, like a failing antenna",
            f"up to {sats_drop:.0f} satellites below usual; weakest satellite "
            f"typically {weakest_drop:.1f} dB below usual, bad is "
            f"{config.BAD_WEAKEST_DROP_DB:.0f} dB or more",
        )

    # Other tractors are fine if none was working, or even the worst barely dropped
    fleet_drop = rows["fleet_worst_signal_mean_drop_db"].mean()
    if pd.isna(fleet_drop):
        fleet_text = "no other tractor was working"
    else:
        fleet_text = (
            f"the worst other tractor's average signal was {fleet_drop:.1f} dB below "
            f"usual, fine is under {config.FLEET_OK_DROP_DB} dB"
        )

    return [
        machine_sign,
        sign("for", len(tractors) == 1, "only one tractor hit", ", ".join(tractors)),
        sign(
            "for",
            pd.isna(fleet_drop) or fleet_drop < config.FLEET_OK_DROP_DB,
            "other tractors fine at the same time",
            fleet_text,
        ),
        sign(
            "against",
            reports,
            "interference report nearby, which points to jamming instead",
            describe_reports(reports, start),
        ),
    ]


# Turn the signs into a confidence between the floor and the cap.
def confidence(signs: list[dict]) -> float:
    # Count the signs for, the bonus signs seen, and the signs against
    signs_for = [s for s in signs if s["kind"] == "for"]
    seen_for = sum(s["seen"] for s in signs_for)
    bonus = sum(s["seen"] for s in signs if s["kind"] == "bonus")
    against = sum(s["seen"] for s in signs if s["kind"] == "against")

    # Share of signs seen gets up to the signs cap, bonus signs go past it
    share = seen_for / len(signs_for) if signs_for else 0
    score = (
        config.CONFIDENCE_FLOOR
        + (config.CONFIDENCE_SIGNS_CAP - config.CONFIDENCE_FLOOR) * share
        + config.CONFIDENCE_BONUS * bonus
        - config.CONFIDENCE_PENALTY * against
    )

    # Keep it in range
    score = max(config.CONFIDENCE_FLOOR, score)
    return round(min(config.CONFIDENCE_CAP, score), 2)


# Write one plain sentence per sign.
def sign_lines(signs: list[dict]) -> list[str]:
    lines = []
    for s in signs:
        if s["kind"] == "against":
            prefix = "Against" if s["seen"] else "Nothing against"
        else:
            prefix = "Seen" if s["seen"] else "Not seen"
        lines.append(f"{prefix}: {s['label']} ({s['detail']}).")
    return lines
