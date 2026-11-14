# Small made-up cases that check the normal and the fleet comparison.
#
# python -m tests.test_features

import pandas as pd

from straightrows.s3_features import add_drop_from_normal, add_fleet_comparison


# Make a time on the test day.
def at(time: str) -> pd.Timestamp:
    return pd.Timestamp(f"2026-05-04T{time}Z")


# Make one minute row with a normal signal. Each test changes a few values.
def minute(tractor: str, time: str, **changes) -> dict:
    normal = {
        "tractor_id": tractor,
        "minute": at(time),
        "working": True,
        "signal_mean_db": 45.0,
        "signal_weakest_db": 38.0,
        "num_sats_min": 11,
        "base_link_lost": False,
    }
    return {**normal, **changes}


# Make a label table from (tractors, start, end) spans.
def labels(*spans: tuple) -> pd.DataFrame:
    rows = [
        {"tractors": tractors, "start": at(start), "end": at(end)} for tractors, start, end in spans
    ]
    return pd.DataFrame(rows, columns=["tractors", "start", "end"])


# Labeled and parked minutes stay out of the normal, so they don't drag it down.
def test_normal_skips_labeled_and_parked():
    # 3 normal minutes, then 4 bad ones: 3 labeled and 1 parked
    rows = [minute("T1", f"12:0{i}") for i in range(3)]
    rows += [minute("T1", f"12:0{i}", signal_mean_db=20.0) for i in range(3, 6)]
    rows.append(minute("T1", "12:06", signal_mean_db=20.0, working=False))
    table = add_drop_from_normal(pd.DataFrame(rows), labels((["T1"], "12:03", "12:05")))

    # Counting the bad minutes would make the normal 20, so 45 means they were skipped
    assert (table["signal_mean_normal_db"] == 45.0).all()
    assert table.loc[table["minute"] == at("12:04"), "signal_mean_drop_db"].item() == 25.0


# A label on another tractor doesn't remove this tractor's minutes.
def test_label_only_on_its_tractors():
    rows = [minute("T1", "12:00", signal_mean_db=40.0), minute("T1", "12:01", signal_mean_db=44.0)]
    table = add_drop_from_normal(pd.DataFrame(rows), labels((["T2"], "12:00", "12:00")))
    assert table["signal_mean_normal_db"].iloc[0] == 42.0


# The fleet value leaves out the tractor itself and parked tractors.
def test_fleet_leaves_out_self_and_parked():
    rows = [
        minute("T1", "12:00", signal_mean_drop_db=10.0),
        minute("T2", "12:00", signal_mean_drop_db=4.0),
        minute("T3", "12:00", signal_mean_drop_db=99.0, working=False),
    ]
    table = add_fleet_comparison(pd.DataFrame(rows)).set_index("tractor_id")
    assert table.loc["T1", "fleet_signal_mean_drop_db"] == 4.0
    assert table.loc["T2", "fleet_signal_mean_drop_db"] == 10.0


# With no other working tractor the fleet value is blank, not 0.
def test_fleet_blank_when_alone():
    rows = [minute("T1", "12:00", signal_mean_drop_db=10.0)]
    rows.append(minute("T2", "12:00", signal_mean_drop_db=0.0, working=False))
    table = add_fleet_comparison(pd.DataFrame(rows)).set_index("tractor_id")
    assert pd.isna(table.loc["T1", "fleet_signal_mean_drop_db"])


# Another tractor losing its link shows up for the others, not for itself.
def test_fleet_base_link_lost():
    rows = [
        minute("T1", "12:00", signal_mean_drop_db=0.0, base_link_lost=True),
        minute("T2", "12:00", signal_mean_drop_db=0.0),
    ]
    table = add_fleet_comparison(pd.DataFrame(rows)).set_index("tractor_id")
    assert not table.loc["T1", "fleet_base_link_lost"]
    assert table.loc["T2", "fleet_base_link_lost"]


# Run every test
if __name__ == "__main__":
    tests = [value for name, value in list(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"passed {test.__name__}")
    print(f"{len(tests)} tests passed")
