# Stage 7: pick a cause and make the detections.

import sys

import pandas as pd

from . import config, evidence, s5_group

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


# Drop multipath dips on a tractor while it is being jammed. Those are the
# jammer pulsing, not signals bouncing.
def drop_jammed_dips(tested: pd.DataFrame) -> pd.DataFrame:
    jammed = tested[tested["cause"] == "JAMMING"]
    keep = []
    for candidate in tested.to_dict("records"):
        # Keep everything that isn't multipath
        if candidate["cause"] != "MULTIPATH":
            keep.append(True)
            continue

        # Drop it if a jamming candidate on the same tractor overlaps it
        same_tractor = jammed[jammed["tractor"] == candidate["tractor"]]
        overlaps = (same_tractor["start"] < candidate["end"]) & (
            same_tractor["end"] > candidate["start"]
        )
        keep.append(not overlaps.any())
    return tested[keep].copy()


# Turn tested candidates into detections.
def make_detections(tested: pd.DataFrame, feeds: dict) -> list[dict]:
    # Stop if there is nothing to report
    if tested.empty:
        return []

    # Pick a cause for each candidate
    causes = [pick_cause(candidate) for candidate in tested.to_dict("records")]
    tested = tested.assign(cause=causes).sort_values("start")
    tested = drop_jammed_dips(tested)

    # One-machine causes stay on their own tractor, the others can share tractors
    shared_by = []
    for tractor, cause in zip(tested["tractor"], tested["cause"]):
        shared_by.append(tractor if cause in config.ONE_TRACTOR_CAUSES else "fleet")
    tested["shared_by"] = shared_by

    # Same-cause candidates join if they overlap, even from different events, so
    # one cause found two ways is reported once
    tested["part"] = 0
    for _, same_cause in tested.groupby(["cause", "shared_by"]):
        parts = s5_group.overlap_numbers(same_cause["start"], same_cause["end"])
        tested.loc[same_cause.index, "part"] = parts

    # Make one detection per cause, tractor share, and part
    detections = []
    groups = tested.groupby(["cause", "shared_by", "part"])
    for (cause, _, _), same_cause in groups:
        detections.append(
            {
                "start": same_cause["start"].min().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end": same_cause["end"].max().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "tractors": sorted(same_cause["tractor"].unique()),
                "class": cause,
                "action": config.ACTIONS[cause],
                "rows": same_cause,
            }
        )

    # Check the signs and write the evidence, once every detection's span is known
    for detection in detections:
        overlapping = any(overlaps(detection, other) for other in detections)
        rows = detection.pop("rows")
        lines, score = evidence.explain(
            detection["class"], rows, tested, feeds, overlapping
        )
        detection["confidence"] = score
        detection["evidence"] = lines

    # Point each detection at the others that overlap it
    add_overlap_notes(detections)

    # Sort by start time, then cause
    detections.sort(key=lambda detection: (detection["start"], detection["class"]))

    return detections


# True if two different detections overlap in time and share a tractor.
# Multipath is left out both ways, since its dips are many and short.
def overlaps(detection: dict, other: dict) -> bool:
    if other is detection or "MULTIPATH" in (detection["class"], other["class"]):
        return False
    if other["start"] >= detection["end"] or other["end"] <= detection["start"]:
        return False
    return bool(set(other["tractors"]) & set(detection["tractors"]))


# Add a line naming each other detection that overlaps this one.
def add_overlap_notes(detections: list[dict]) -> None:
    for detection in detections:
        for other in detections:
            if not overlaps(detection, other):
                continue

            # Name the other cause
            start = other["start"][:16].replace("T", " ")
            end = other["end"][11:16]
            note = (
                f"Overlaps {other['class']} on {', '.join(other['tractors'])} "
                f"({start} to {end} UTC), reported as its own detection"
            )

            # Say it may explain the signs not seen, if there are any
            if any(line.startswith("Not seen") for line in detection["evidence"]):
                note += "; it may explain the signs not seen above"
            detection["evidence"].append(note + ".")
