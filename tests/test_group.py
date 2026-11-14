# Small made-up cases that check how candidates are grouped into events.
#
# python -m tests.test_group

import pandas as pd

from straightrows.s5_group import group_events, overlap_numbers


# Make a time on the test day.
def at(time: str) -> pd.Timestamp:
    return pd.Timestamp(f"2026-05-04T{time}Z")


# Make a candidate table from (tractor, kind, start, end) rows.
def candidates(*rows: tuple) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"tractor": tractor, "kind": kind, "start": at(start), "end": at(end)}
            for tractor, kind, start, end in rows
        ]
    )


# Overlapping spans share a number, and a gap starts the next number.
def test_overlap_numbers():
    starts = [at("12:00"), at("12:05"), at("13:00")]
    ends = [at("12:10"), at("12:20"), at("13:10")]
    assert overlap_numbers(starts, ends) == [0, 0, 1]


# A span that starts right at the end of the last one still joins it.
def test_overlap_numbers_touching():
    assert overlap_numbers([at("12:00"), at("12:10")], [at("12:10"), at("12:20")]) == [0, 0]


# Link and signal episodes that overlap become one event, even across tractors.
def test_link_and_signal_join():
    grouped = group_events(
        candidates(("T1", "link", "12:00", "12:30"), ("T2", "signal", "12:10", "12:40"))
    )
    assert grouped["event"].nunique() == 1


# A dip inside a signal episode stays its own event, and so does each dip.
def test_dips_kept_apart():
    grouped = group_events(
        candidates(
            ("T1", "signal", "12:00", "12:30"),
            ("T1", "dip", "12:10", "12:11"),
            ("T1", "dip", "12:10", "12:11"),
        )
    )
    assert grouped["event"].nunique() == 3


# A step on top of an episode is a separate event from it.
def test_step_kept_apart():
    grouped = group_events(
        candidates(("T1", "signal", "12:00", "13:00"), ("T1", "step", "12:20", "12:40"))
    )
    assert grouped["event"].nunique() == 2


# Run every test
if __name__ == "__main__":
    tests = [value for name, value in list(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"passed {test.__name__}")
    print(f"{len(tests)} tests passed")
