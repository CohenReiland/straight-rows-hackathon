# Stage 7 helper: check the signs for a detection's cause, score the confidence,
# and write evidence in clean sentences that read on their own.

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
