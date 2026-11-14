# Stage 7: pick a cause and make the detections.

import sys

import pandas as pd

from . import config, s5_group

# If several causes pass, the first one wins
PRIORITY = ["MULTIPATH", "SPOOFING", "SPACE_WEATHER", "JAMMING", "EQUIPMENT_FAULT"]


# Pick one cause for a candidate.
def pick_cause(candidate: dict) -> str:
    # Get the candidate's name for warnings
    passed = candidate["passed"]
    name = f"{candidate['tractor']} {candidate['start']:%m-%d %H:%M}"

    # The tests should not overlap, so say if they do
    if len(passed) > 1:
        print(f"warning: {name} passed {', '.join(passed)}", file=sys.stderr)

    # Take the first passing cause
    for cause in PRIORITY:
        if cause in passed:
            return cause

    # No test passed, which means the rules have a gap
    print(f"warning: {name} passed no test, using EQUIPMENT_FAULT", file=sys.stderr)
    return "EQUIPMENT_FAULT"


# Turn tested candidates into detections.
def make_detections(tested: pd.DataFrame, feeds: dict) -> list[dict]:
    # Stop if there is nothing to report
    if tested.empty:
        return []

    # Pick a cause for each candidate
    causes = [pick_cause(candidate) for candidate in tested.to_dict("records")]
    tested = tested.assign(cause=causes).sort_values("start")

    # One-machine causes stay on their own tractor, the others can share tractors
    shared_by = []
    for tractor, cause in zip(tested["tractor"], tested["cause"]):
        shared_by.append(tractor if cause in config.ONE_TRACTOR_CAUSES else "fleet")
    tested["shared_by"] = shared_by

    # Same-cause candidates in an event only join if they overlap each other
    tested["part"] = 0
    for _, same_cause in tested.groupby(["event", "cause", "shared_by"]):
        parts = s5_group.overlap_numbers(same_cause["start"], same_cause["end"])
        tested.loc[same_cause.index, "part"] = parts

    # Make one detection per event, cause, tractor share, and part
    detections = []
    events = []
    groups = tested.groupby(["event", "cause", "shared_by", "part"])
    for (event, cause, _, _), same_cause in groups:
        start = same_cause["start"].min()
        end = same_cause["end"].max()
        tractors = sorted(same_cause["tractor"].unique())

        # TODO step 8: replace this placeholder with evidence.explain(cause,
        # same_cause, tested, feeds), which checks the signs and sets the
        # confidence. Until then every detection gets 0.5 and one line.
        # Also port add_overlap_notes then, to name the other causes in an event.
        score = 0.5
        lines = [
            f"Bad minutes on {', '.join(tractors)} from {start:%H:%M} to {end:%H:%M}; "
            f"the {cause} test passed."
        ]

        detections.append(
            {
                "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "tractors": tractors,
                "class": cause,
                "action": config.ACTIONS[cause],
                "confidence": score,
                "evidence": lines,
            }
        )
        events.append(event)

    # Sort by start time, then cause
    detections.sort(key=lambda detection: (detection["start"], detection["class"]))

    return detections
