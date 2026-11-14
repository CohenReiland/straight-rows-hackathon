# Small made-up cases that check which rows count as working.
#
# python -m tests.test_mask

import pandas as pd

from straightrows import config
from straightrows.s2_mask import add_working


# Make one tractor's rows, one per second, at the given speeds.
def rows(tractor: str, speeds: list[float]) -> pd.DataFrame:
    times = pd.date_range("2026-05-06T12:00Z", periods=len(speeds), freq="s")
    return pd.DataFrame({"tractor_id": tractor, "ts": times, "speed_mps": speeds})


# A 2-minute stop: rows near the moving parts stay working, the middle is parked.
def test_stop_edges():
    edge = config.WORKING_LOOKAROUND_S
    speeds = [4.5] * 60 + [0.0] * 120 + [4.5] * 60
    working = add_working(rows("T1", speeds))["working"].tolist()

    # Moving rows are working
    assert all(working[:60]) and all(working[180:])

    # Stopped rows within the look-around of moving are still working
    assert all(working[60 : 60 + edge]) and all(working[180 - edge : 180])

    # The rest of the stop is parked
    assert not any(working[60 + edge : 180 - edge])


# One tractor moving never marks another tractor as working.
def test_tractors_kept_apart():
    telemetry = pd.concat([rows("T1", [4.5] * 120), rows("T2", [0.0] * 120)], ignore_index=True)
    telemetry = telemetry.sort_values(["tractor_id", "ts"]).reset_index(drop=True)
    result = add_working(telemetry)
    assert result.loc[result["tractor_id"] == "T1", "working"].all()
    assert not result.loc[result["tractor_id"] == "T2", "working"].any()


# Run every test
if __name__ == "__main__":
    tests = [value for name, value in list(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"passed {test.__name__}")
    print(f"{len(tests)} tests passed")
