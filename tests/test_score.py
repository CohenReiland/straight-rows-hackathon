# Small made-up cases that check the dev score.
#
# python -m tests.test_score

import pandas as pd

from straightrows.score import CAUSES, match, score


# A detection or label at the given hours on May 6, on one tractor.
def item(cause: str, start_h: float, end_h: float, tractors=("T1",)) -> dict:
    day = pd.Timestamp("2026-05-06T00:00Z")
    return {
        "class": cause,
        "start": day + pd.Timedelta(hours=start_h),
        "end": day + pd.Timedelta(hours=end_h),
        "tractors": list(tractors),
    }


# One 2-hour label per cause, spread over the day.
LABELS = [item(cause, 2 + 3 * i, 4 + 3 * i) for i, cause in enumerate(CAUSES)]


# A detection that copies a label.
def copy_of(label: dict) -> dict:
    return dict(label)


# Every label found exactly scores the full 40.
def test_perfect():
    result = score([copy_of(label) for label in LABELS], LABELS)
    assert round(result["total"], 2) == 40.00
    assert result["false_alarms"] == []


# Leaving out the jamming label loses its F1 and its onset credit.
def test_one_miss():
    detections = [copy_of(label) for label in LABELS if label["class"] != "JAMMING"]
    result = score(detections, LABELS)
    assert round(result["total"], 2) == 32.00
    assert result["counts"]["JAMMING"]["missed"] == 1


# Calling the jamming label spoofing is a miss for jamming and a false alarm for
# spoofing, and earns no onset credit.
def test_wrong_cause():
    detections = [copy_of(label) for label in LABELS]
    detections[CAUSES.index("JAMMING")]["class"] = "SPOOFING"
    result = score(detections, LABELS)
    assert round(result["total"], 2) == 30.33
    assert result["counts"]["JAMMING"]["missed"] == 1
    assert result["counts"]["SPOOFING"]["false"] == 1


# An extra jamming detection where nothing happened is a false alarm.
def test_false_alarm():
    detections = [copy_of(label) for label in LABELS] + [item("JAMMING", 18, 19)]
    result = score(detections, LABELS)
    assert round(result["total"], 2) == 38.33
    assert len(result["false_alarms"]) == 1


# An extra multipath report of 3 minutes or less is free; a longer one is not.
def test_short_multipath_is_free():
    detections = [copy_of(label) for label in LABELS]
    short = score(detections + [item("MULTIPATH", 18, 18 + 2 / 60)], LABELS)
    long = score(detections + [item("MULTIPATH", 18, 18 + 4 / 60)], LABELS)
    assert round(short["total"], 2) == 40.00
    assert short["free_multipath"] == 1
    assert round(long["total"], 2) == 38.33
    assert long["free_multipath"] == 0


# Starting 20 minutes late still matches but earns only part of the onset credit.
def test_late_onset():
    detections = [copy_of(label) for label in LABELS]
    detections[0]["start"] += pd.Timedelta(minutes=20)
    result = score(detections, LABELS)
    assert round(result["total"], 2) == 39.18
    assert result["counts"][LABELS[0]["class"]]["hits"] == 1


# Pairing looks at every option, not just each detection's best label: detection 0
# fits label 0 best, but giving it label 1 lets detection 1 pair too.
def test_pairs_every_option():
    labels = [item("JAMMING", 0, 1), item("JAMMING", 50 / 60, 110 / 60)]
    detections = [item("JAMMING", 20 / 60, 80 / 60), item("JAMMING", 0, 0.5)]
    assert match(detections, labels) == {0: 1, 1: 0}


# Two detections of one label: only one pairs, the other is a false alarm.
def test_label_pairs_once():
    detections = [copy_of(label) for label in LABELS] + [copy_of(LABELS[1])]
    result = score(detections, LABELS)
    assert result["counts"][LABELS[1]["class"]]["hits"] == 1
    assert len(result["false_alarms"]) == 1


# When two detections could pair with one label, the closer one gets it, whether it
# comes first or second.
def test_closer_detection_wins():
    labels = [item("JAMMING", 2, 4)]
    exact = item("JAMMING", 2, 4)
    assert match([exact, item("JAMMING", 2.5, 4)], labels) == {0: 0}
    assert match([item("JAMMING", 1.5, 4), exact], labels) == {0: 1}


# A same-cause detection gets the label even when a wrong-cause one overlaps more.
def test_same_cause_first():
    labels = [item("JAMMING", 0, 1)]
    detections = [item("SPOOFING", 0, 1), item("JAMMING", 10 / 60, 1)]
    result = score(detections, labels)
    assert result["counts"]["JAMMING"]["hits"] == 1
    assert result["counts"]["SPOOFING"]["false"] == 1


# Run every test
if __name__ == "__main__":
    tests = [value for name, value in list(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"passed {test.__name__}")
    print(f"{len(tests)} tests passed")
