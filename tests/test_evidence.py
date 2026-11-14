# Small made-up cases that check the confidence sum and the evidence sentences.
#
# python -m tests.test_evidence

import pandas as pd

from straightrows import config
from straightrows.evidence import (
    confidence,
    distance_km,
    nearby_reports,
    sign,
    sign_lines,
    spoofing_signs,
)


# Make signs: how many "for" signs are seen out of the total, plus bonus and against.
def signs(seen_for: int, total_for: int, bonus: int = 0, against: int = 0) -> list[dict]:
    made = [sign("for", i < seen_for, "for", "") for i in range(total_for)]
    made += [sign("bonus", True, "bonus", "") for _ in range(bonus)]
    made += [sign("against", True, "against", "") for _ in range(against)]
    return made


# Every sign seen reaches the signs cap, none seen stays at the floor.
def test_confidence_all_and_none():
    assert confidence(signs(4, 4)) == config.CONFIDENCE_SIGNS_CAP
    assert confidence(signs(0, 4)) == config.CONFIDENCE_FLOOR


# Half the signs seen lands halfway between the floor and the signs cap.
def test_confidence_half():
    halfway = (config.CONFIDENCE_FLOOR + config.CONFIDENCE_SIGNS_CAP) / 2
    assert confidence(signs(2, 4)) == round(halfway, 2)


# A bonus sign takes it past the signs cap, but never past the cap.
def test_confidence_bonus_and_cap():
    one_bonus = config.CONFIDENCE_SIGNS_CAP + config.CONFIDENCE_BONUS
    assert confidence(signs(4, 4, bonus=1)) == round(min(one_bonus, config.CONFIDENCE_CAP), 2)
    assert confidence(signs(4, 4, bonus=3)) == config.CONFIDENCE_CAP


# A sign against takes points off, but never below the floor.
def test_confidence_against_and_floor():
    one_against = config.CONFIDENCE_SIGNS_CAP - config.CONFIDENCE_PENALTY
    assert confidence(signs(4, 4, against=1)) == round(one_against, 2)
    assert confidence(signs(0, 4, against=2)) == config.CONFIDENCE_FLOOR


# Each sign gets a sentence that says whether it was seen.
def test_sign_lines():
    lines = sign_lines(
        [
            sign("for", True, "short dip", "12 s"),
            sign("bonus", False, "strong flicker", "0.20"),
            sign("against", True, "report nearby", "RFI-1"),
            sign("against", False, "report nearby", "none"),
        ]
    )
    assert lines == [
        "Seen: short dip (12 s).",
        "Not seen: strong flicker (0.20).",
        "Against: report nearby (RFI-1).",
        "Nothing against: report nearby (none).",
    ]


# One degree of latitude is about 111 km.
def test_distance_km():
    assert abs(distance_km(46.0, -97.0, 47.0, -97.0) - 111.2) < 0.1


# Make a report table from (id, minutes after the start, km north of the tractors).
def reports(*rows: tuple) -> pd.DataFrame:
    start = pd.Timestamp("2026-05-04T12:00Z")
    return pd.DataFrame(
        [
            {
                "report_id": report_id,
                "received": start + pd.Timedelta(minutes=delay),
                "lat": 46.0 + north_km / 111.2,
                "lon": -97.0,
                "area_long_km": 2.0,
                "confidence": 0.5,
            }
            for report_id, delay, north_km in rows
        ]
    )


# Only reports that arrive soon after the start and reach the tractors count.
def test_nearby_reports():
    late = config.REPORT_MAX_DELAY_MIN + 10
    far = 2.0 + config.REPORT_EXTRA_KM + 5
    found = nearby_reports(
        reports(("near", 20, 1.0), ("late", late, 1.0), ("far", 20, far), ("early", -5, 1.0)),
        pd.Timestamp("2026-05-04T12:00Z"),
        46.0,
        -97.0,
    )
    assert [report["report_id"] for report in found] == ["near"]


# A smooth drift with a healthy signal and the link up shows every spoofing sign.
def test_spoofing_signs_all_seen():
    rows = pd.DataFrame(
        [
            {
                "kind": "drift",
                "cross_track_error_max_m": 2.0,
                "signal_mean_drop_max_db": 0.5,
                "signal_weakest_drop_median_db": 1.0,
                "num_sats_drop_max": 0,
                "base_link_lost": False,
            }
        ]
    )
    found = spoofing_signs(rows)
    assert all(s["seen"] for s in found)
    assert confidence(found) == config.CONFIDENCE_SIGNS_CAP


# Run every test
if __name__ == "__main__":
    tests = [value for name, value in list(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"passed {test.__name__}")
    print(f"{len(tests)} tests passed")
