# Checks that stage 1 reads the real files with our column names.
#
# python -m tests.test_load

import pandas as pd

from straightrows import config
from straightrows.s1_load import convert_names, load_feed, load_space_feeds, load_telemetry


# Every telemetry row is there, renamed, and sorted by tractor then time.
def test_load_telemetry():
    telemetry = load_telemetry()
    assert len(telemetry) == config.EXPECTED_ROWS
    assert list(telemetry.columns) == list(config.TELEMETRY_FIELDS.keys())
    assert str(telemetry["ts"].dt.tz) == "UTC"
    assert telemetry.equals(telemetry.sort_values(["tractor_id", "ts"]).reset_index(drop=True))


# A file's names become ours, and columns we don't list are dropped.
def test_convert_names_renames():
    table = pd.DataFrame({"kp": [1.9], "extra": [0]})
    renamed = convert_names(table, {"storm_kp": "kp"}, "test table")
    assert list(renamed.columns) == ["storm_kp"]


# A missing field stops with a message that names it.
def test_convert_names_missing_field():
    table = pd.DataFrame({"kp": [1.9]})
    try:
        convert_names(table, {"storm_kp": "kp", "storm_field_drop_nt": "dst_nT"}, "test table")
    except ValueError as error:
        assert "storm_field_drop_nt" in str(error)
    else:
        raise AssertionError("expected a ValueError for the missing field")


# Interference report times mix with and without microseconds, and all of them parse.
def test_interference_report_times():
    reports = load_feed("interference_reports")
    assert reports["received"].notna().all()
    assert str(reports["received"].dt.tz) == "UTC"
    assert reports["received"].is_monotonic_increasing


# Every space feed loads, with our column names and at least one row.
def test_load_space_feeds():
    feeds = load_space_feeds()
    assert list(feeds.keys()) == list(config.SPACE_FEED_FILES.keys())
    for feed, table in feeds.items():
        assert list(table.columns) == list(config.SPACE_FEED_FIELDS[feed].keys())
        assert len(table) > 0, f"{feed} is empty"


# Run every test
if __name__ == "__main__":
    tests = [value for name, value in list(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"passed {test.__name__}")
    print(f"{len(tests)} tests passed")
