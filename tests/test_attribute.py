# Small made-up cases that check each of the five cause tests.
#
# python -m tests.test_attribute

from straightrows import config
from straightrows.s6_attribute import passing_causes


# Numbers for a long episode with a healthy signal on a fine fleet.
# Each test changes a few values.
def numbers(**changes) -> dict:
    healthy = {
        "duration_min": 60.0,
        "signal_mean_drop_max_db": 0.5,
        "signal_weakest_drop_median_db": 1.0,
        "fleet_worst_signal_mean_drop_db": 0.5,
        "signal_flicker_s4_max": 0.1,
        "cross_track_error_max_m": 0.1,
        "base_link_lost": False,
    }
    return {**healthy, **changes}


# Values that make the signal clearly bad, on this tractor or on the fleet.
BAD = config.HEALTHY_MAX_DROP_DB + 5
FLEET_BAD = config.FLEET_OK_DROP_DB + 5
HIGH_FLICKER = config.HIGH_FLICKER_S4 + 0.2
FAR_OFF = config.BAD_CROSS_TRACK_ERROR_M + 1


# One tractor bad while the others are fine is an equipment fault.
def test_equipment_fault():
    assert passing_causes(numbers(signal_mean_drop_max_db=BAD), "signal") == ["EQUIPMENT_FAULT"]


# No other tractor working counts as the others being fine.
def test_equipment_fault_alone():
    lone = numbers(signal_mean_drop_max_db=BAD, fleet_worst_signal_mean_drop_db=float("nan"))
    assert passing_causes(lone, "signal") == ["EQUIPMENT_FAULT"]


# The fleet down too, with the signal flickering, is space weather.
def test_space_weather():
    storm = numbers(
        signal_mean_drop_max_db=BAD,
        fleet_worst_signal_mean_drop_db=FLEET_BAD,
        signal_flicker_s4_max=HIGH_FLICKER,
    )
    assert passing_causes(storm, "signal") == ["SPACE_WEATHER"]


# The fleet down too, with no flicker, is jamming.
def test_jamming():
    jammed = numbers(signal_mean_drop_max_db=BAD, fleet_worst_signal_mean_drop_db=FLEET_BAD)
    assert passing_causes(jammed, "signal") == ["JAMMING"]


# Off the row with a healthy signal and the link up is spoofing.
def test_spoofing():
    assert passing_causes(numbers(cross_track_error_max_m=FAR_OFF), "signal") == ["SPOOFING"]


# Off the row with the link lost is not spoofing, since the lost link explains it.
def test_spoofing_needs_link():
    lost = numbers(cross_track_error_max_m=FAR_OFF, base_link_lost=True)
    assert "SPOOFING" not in passing_causes(lost, "signal")


# A short episode is multipath, even when the signal is bad.
def test_multipath():
    short = numbers(duration_min=config.SHORT_EPISODE_MIN, signal_mean_drop_max_db=BAD)
    assert passing_causes(short, "signal") == ["MULTIPATH"]


# A dip is only ever multipath.
def test_dip_kind():
    assert passing_causes(numbers(signal_mean_drop_max_db=BAD), "dip") == ["MULTIPATH"]


# A drift is spoofing, unless the link was lost.
def test_drift_kind():
    assert passing_causes(numbers(), "drift") == ["SPOOFING"]
    assert passing_causes(numbers(base_link_lost=True), "drift") == []


# A long lost link is an equipment fault, a short one is multipath.
def test_link_kind():
    assert passing_causes(numbers(base_link_lost=True), "link") == ["EQUIPMENT_FAULT"]
    short = numbers(duration_min=1.0, base_link_lost=True)
    assert passing_causes(short, "link") == ["MULTIPATH"]


# A step is jamming only if the fleet dropped too, whatever the flicker.
def test_step_kind():
    fleet_step = numbers(
        signal_mean_drop_max_db=BAD,
        fleet_worst_signal_mean_drop_db=FLEET_BAD,
        signal_flicker_s4_max=HIGH_FLICKER,
    )
    assert passing_causes(fleet_step, "step") == ["JAMMING"]
    assert passing_causes(numbers(signal_mean_drop_max_db=BAD), "step") == []


# A healthy, on-the-row episode passes no test.
def test_nothing_passes():
    assert passing_causes(numbers(), "signal") == []


# Run every test
if __name__ == "__main__":
    tests = [value for name, value in list(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"passed {test.__name__}")
    print(f"{len(tests)} tests passed")
