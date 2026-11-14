# Small made-up cases that check how bad minutes become episodes.
#
# python -m tests.test_segment

import pandas as pd

from straightrows import config
from straightrows.s4_segment import find_dips, find_runs, join_touching, stretch_runs


# Make a time on the test day.
def at(time: str) -> pd.Timestamp:
    return pd.Timestamp(f"2026-05-04T{time}Z")


# Make a table of (tractor, minute) rows, like the bad or weak minutes.
def minutes(*rows: tuple) -> pd.DataFrame:
    return pd.DataFrame(
        [{"tractor_id": tractor, "minute": at(time)} for tractor, time in rows]
    )


# Make an episode table from (tractor, start, end) spans.
def runs(*spans: tuple) -> pd.DataFrame:
    rows = [
        {"tractor": tractor, "start": at(start), "end": at(end), "kind": "signal"}
        for tractor, start, end in spans
    ]
    return pd.DataFrame(rows, columns=["tractor", "start", "end", "kind"])


# Bad minutes with a small gap join into one episode that ends a minute after the last.
def test_small_gap_joins():
    bad = minutes(("T1", "12:00"), ("T1", "12:01"), ("T1", "12:03"))
    found = find_runs(bad, at("23:00"), "signal")
    assert len(found) == 1
    assert found.iloc[0]["start"] == at("12:00")
    assert found.iloc[0]["end"] == at("12:04")
    assert found.iloc[0]["kind"] == "signal"


# A gap longer than the allowed gap starts a new episode.
def test_big_gap_splits():
    later = at("12:00") + pd.Timedelta(minutes=config.MAX_GAP_MIN + 1)
    bad = minutes(("T1", "12:00"), ("T1", later.strftime("%H:%M")))
    found = find_runs(bad, at("23:00"), "signal")
    assert len(found) == 2


# Each tractor gets its own episodes, even at the same time.
def test_runs_per_tractor():
    bad = minutes(("T1", "12:00"), ("T2", "12:00"))
    found = find_runs(bad, at("23:00"), "link")
    assert sorted(found["tractor"]) == ["T1", "T2"]


# An episode that runs to the end of the window stops at the window end.
def test_run_capped_at_window_end():
    bad = minutes(("T1", "23:59"))
    found = find_runs(bad, at("23:59:30"), "signal")
    assert found.iloc[0]["end"] == at("23:59:30")


# Episodes that touch on the same tractor join; other tractors stay apart.
def test_join_touching():
    joined = join_touching(
        runs(("T1", "12:00", "12:05"), ("T1", "12:05", "12:10"), ("T2", "12:10", "12:15"))
    )
    assert len(joined) == 2
    assert joined.iloc[0]["end"] == at("12:10")


# An episode stretches over the weak minutes next to it.
def test_stretch_over_weak_minutes():
    weak = minutes(("T1", "11:58"), ("T1", "11:59"), ("T1", "12:05"))
    stretched = stretch_runs(runs(("T1", "12:00", "12:05")), weak, at("00:00"), at("23:59"))
    assert stretched.iloc[0]["start"] == at("11:58")
    assert stretched.iloc[0]["end"] == at("12:06")


# Stretching stops at the cap, even if the signal stays weak.
def test_stretch_capped():
    weak = minutes(*[("T1", f"{h:02d}:{m:02d}") for h in (10, 11) for m in range(60)])
    stretched = stretch_runs(runs(("T1", "12:00", "12:05")), weak, at("00:00"), at("23:59"))
    earliest = at("12:00") - pd.Timedelta(minutes=config.MAX_STRETCH_MIN)
    assert stretched.iloc[0]["start"] == earliest


# Stretching never reaches into the next episode on the same tractor.
def test_stretch_stops_at_neighbor():
    weak = minutes(("T1", "12:05"), ("T1", "12:06"), ("T1", "12:07"))
    both = runs(("T1", "12:00", "12:05"), ("T1", "12:07", "12:10"))
    stretched = stretch_runs(both, weak, at("00:00"), at("23:59"))

    # The first one grows up to the second one, then they touch and join
    assert len(stretched) == 1
    assert stretched.iloc[0]["start"] == at("12:00")
    assert stretched.iloc[0]["end"] == at("12:10")


# Make one tractor's seconds with a steady weakest satellite, and lower it in spans.
def seconds(dips: list[tuple], working: bool = True) -> pd.DataFrame:
    times = pd.date_range(at("12:00"), periods=600, freq="s")
    weakest = [38.0] * len(times)
    for first, length in dips:
        for i in range(first, first + length):
            weakest[i] = 38.0 - config.DIP_DROP_DB - 3
    return pd.DataFrame(
        {"tractor_id": "T1", "ts": times, "signal_weakest_db": weakest, "working": working}
    )


# A dip long enough is found, with its edges to the second; a shorter one is skipped.
def test_dips_long_enough():
    long_s, short_s = config.MIN_DIP_S + 2, config.MIN_DIP_S - 1
    found = find_dips(seconds([(200, long_s), (400, short_s)]), "dev")
    assert len(found) == 1
    assert found.iloc[0]["start"] == at("12:00") + pd.Timedelta(seconds=200)
    assert found.iloc[0]["end"] == at("12:00") + pd.Timedelta(seconds=200 + long_s)
    assert found.iloc[0]["kind"] == "dip"


# A dip while parked is never reported.
def test_dips_skip_parked():
    found = find_dips(seconds([(200, 20)], working=False), "dev")
    assert found.empty


# Run every test
if __name__ == "__main__":
    tests = [value for name, value in list(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"passed {test.__name__}")
    print(f"{len(tests)} tests passed")
