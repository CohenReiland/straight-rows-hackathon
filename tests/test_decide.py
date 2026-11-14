# Small made-up cases that check how a cause is picked and detections are joined.
#
# python -m tests.test_decide

import pandas as pd

from straightrows.s7_decide import add_overlap_notes, drop_jammed_dips, overlaps, pick_cause


# Make a time on the test day.
def at(time: str) -> pd.Timestamp:
    return pd.Timestamp(f"2026-05-04T{time}Z")


# A candidate that passed the given causes.
def candidate(*passed: str) -> dict:
    return {"tractor": "T1", "start": at("12:00"), "passed": list(passed)}


# Make a detection the way stage 7 does, with times as text.
def detection(cause: str, start: str, end: str, tractors=("T1",), evidence=()) -> dict:
    return {
        "class": cause,
        "start": f"2026-05-04T{start}:00Z",
        "end": f"2026-05-04T{end}:00Z",
        "tractors": list(tractors),
        "evidence": list(evidence),
    }


# When several causes pass, the one first in the priority list wins.
def test_pick_by_priority():
    assert pick_cause(candidate("JAMMING", "MULTIPATH")) == "MULTIPATH"
    assert pick_cause(candidate("EQUIPMENT_FAULT", "SPACE_WEATHER")) == "SPACE_WEATHER"


# When no test passes, the candidate falls back to an equipment fault.
def test_pick_fallback():
    assert pick_cause(candidate()) == "EQUIPMENT_FAULT"


# Multipath dips on a jammed tractor are dropped; dips on other tractors stay.
def test_drop_jammed_dips():
    rows = [
        ("T1", "JAMMING", "12:00", "13:00"),
        ("T1", "MULTIPATH", "12:10", "12:11"),
        ("T2", "MULTIPATH", "12:10", "12:11"),
        ("T1", "MULTIPATH", "14:00", "14:01"),
    ]
    tested = pd.DataFrame(
        [
            {"tractor": tractor, "cause": cause, "start": at(start), "end": at(end)}
            for tractor, cause, start, end in rows
        ]
    )
    kept = drop_jammed_dips(tested)
    assert len(kept) == 3
    assert not ((kept["tractor"] == "T1") & (kept["start"] == at("12:10"))).any()


# Two detections overlap only if they share a tractor and some time.
def test_overlaps():
    storm = detection("SPACE_WEATHER", "12:00", "13:00", ("T1", "T2"))
    assert overlaps(storm, detection("EQUIPMENT_FAULT", "12:30", "14:00", ("T2",)))
    assert not overlaps(storm, detection("EQUIPMENT_FAULT", "12:30", "14:00", ("T3",)))
    assert not overlaps(storm, detection("EQUIPMENT_FAULT", "13:00", "14:00", ("T1",)))
    assert not overlaps(storm, storm)


# Multipath never counts as overlapping, since its dips are many and short.
def test_overlaps_skip_multipath():
    storm = detection("SPACE_WEATHER", "12:00", "13:00")
    assert not overlaps(storm, detection("MULTIPATH", "12:10", "12:11"))


# Each overlapping detection gets a note naming the other one.
def test_overlap_notes():
    storm = detection("SPACE_WEATHER", "12:00", "13:00", ("T1", "T2"), ["Seen: a sign."])
    fault = detection("EQUIPMENT_FAULT", "12:30", "14:00", ("T2",), ["Not seen: a sign."])
    add_overlap_notes([storm, fault])

    # The storm's note names the fault
    assert storm["evidence"][-1].startswith("Overlaps EQUIPMENT_FAULT on T2")

    # The fault had a sign not seen, so its note says the storm may explain it
    assert "SPACE_WEATHER" in fault["evidence"][-1]
    assert "may explain the signs not seen" in fault["evidence"][-1]


# Run every test
if __name__ == "__main__":
    tests = [value for name, value in list(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"passed {test.__name__}")
    print(f"{len(tests)} tests passed")
