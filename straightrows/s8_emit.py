# Stage 8: save, validate, and summarize the detections.

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

from . import config

# The settings that decide what counts as bad, saved with each tractor's normal
CUTOFF_SETTINGS = [
    "WORKING_SPEED_MPS",
    "WORKING_MINUTE_SHARE",
    "BAD_WEAKEST_DROP_DB",
    "BAD_CROSS_TRACK_ERROR_M",
    "WEAK_MEAN_DROP_DB",
    "MAX_GAP_MIN",
    "SHORT_EPISODE_MIN",
    "HEALTHY_MAX_DROP_DB",
    "FLEET_OK_DROP_DB",
    "HIGH_FLICKER_S4",
    "MULTIPATH_EXEMPT_MIN",
]


# Save the detections to a file.
def write(detections: list[dict], window: str) -> Path:
    # Get the output file
    path = config.OUTPUT[window]

    # Build the submission
    submission = {
        "participant": config.PARTICIPANT,
        "repository_url": config.REPOSITORY_URL,
        "detections": detections,
    }

    # Write the file
    path.write_text(json.dumps(submission, indent=2) + "\n", encoding="utf8")

    return path


# Run the validator on the file.
def validate(path: Path) -> bool:
    result = subprocess.run([sys.executable, str(config.VALIDATOR), str(path)])
    return result.returncode == 0


# Print the detections.
def summarize(detections: list[dict]) -> None:
    # Print the count per cause
    cause_counts = Counter(detection["class"] for detection in detections)
    print(f"{len(detections)} detections: {dict(cause_counts)}")

    # Print one line per detection, except multipath
    multipath = []
    for detection in detections:
        if detection["class"] == "MULTIPATH":
            multipath.append(detection)
            continue
        tractors = ",".join(detection["tractors"])
        times = f"{detection['start']} to {detection['end'][11:]}"
        print(f"  {times}  {tractors:8} {detection['class']}")

    # Print one line for all the multipath reports
    if multipath:
        first, last = multipath[0]["start"], multipath[-1]["start"]
        print(f"  {len(multipath)} MULTIPATH reports, from {first} to {last}")


# Save each tractor's normal values and the cutoffs that came from them.
def write_thresholds(minutes: pd.DataFrame) -> Path:
    # Read each tractor's normal back from stage 3, so the file matches exactly
    working = minutes[minutes["working"]]
    tractors = {}
    for tractor, rows in working.groupby("tractor_id"):
        first = rows.iloc[0]
        normal_weakest = first["signal_weakest_db"] + first["signal_weakest_drop_db"]
        normal_sats = first["num_sats_min"] + first["num_sats_drop"]
        tractors[tractor] = {
            "normal_signal_mean_db": round(float(first["signal_mean_normal_db"]), 2),
            "normal_signal_weakest_db": round(float(normal_weakest), 2),
            "normal_num_sats": int(normal_sats),
            "bad_below_signal_weakest_db": round(
                float(normal_weakest - config.BAD_WEAKEST_DROP_DB), 2
            ),
            "working_minutes": int(len(rows)),
        }

    # The cutoff settings from config
    settings = {name: getattr(config, name) for name in CUTOFF_SETTINGS}

    # Write the file
    content = {"tractors": tractors, "settings": settings}
    text = json.dumps(content, indent=2) + "\n"
    config.THRESHOLDS.write_text(text, encoding="utf8")
    return config.THRESHOLDS
