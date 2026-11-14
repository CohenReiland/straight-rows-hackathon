# Dev scoring: grade predictions against the labeled episodes.
#
# python -m straightrows.score dev_predictions.json

import json
from pathlib import Path

import pandas as pd


# Read detections or labels from a file.
def read_items(path: Path, key: str) -> list[dict]:
    # Get the list from the file
    items = json.loads(Path(path).read_text(encoding="utf8"))[key]

    # Turn start and end into UTC times
    for item in items:
        item["start"] = pd.to_datetime(item["start"], utc=True)
        item["end"] = pd.to_datetime(item["end"], utc=True)

    return items


# How much two time spans overlap, from 0 to 1.
def time_iou(a: dict, b: dict) -> float:
    # Seconds they share
    overlap = (min(a["end"], b["end"]) - max(a["start"], b["start"])).total_seconds()

    # Seconds from the first start to the last end
    union = (max(a["end"], b["end"]) - min(a["start"], b["start"])).total_seconds()

    # Shared time divided by total time
    return max(overlap, 0) / union if union > 0 else 0.0


# How much two tractor lists overlap, from 0 to 1.
def tractor_iou(a: dict, b: dict) -> float:
    # Make the tractor sets
    a_set, b_set = set(a["tractors"]), set(b["tractors"])

    # Shared tractors divided by all tractors (0 if both lists are empty)
    union = a_set | b_set
    return len(a_set & b_set) / len(union) if union else 0.0
