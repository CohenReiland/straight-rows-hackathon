# Dev scoring: grade predictions against the labeled episodes.
#
# python -m straightrows.score dev_predictions.json

import json
from pathlib import Path

import pandas as pd

from . import config


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


# The time and tractor overlap of a pair, or None if they're too far apart to match.
def pair_overlap(detection: dict, label: dict) -> tuple[float, float] | None:
    time_overlap = time_iou(detection, label)
    tractor_overlap = tractor_iou(detection, label)
    if (
        time_overlap >= config.MATCH_TIME_IOU
        and tractor_overlap >= config.MATCH_TRACTOR_IOU
    ):
        return time_overlap, tractor_overlap
    return None


# The best one-to-one pairs between some detections and some labels,
# the most pairs, then the most time overlap, then the most tractor overlap.
def best_pairs(
    detections: list[dict],
    labels: list[dict],
    d_indexes: list[int],
    l_indexes: list[int],
    same_cause_only: bool,
) -> dict[int, int]:
    # For each set of used labels, the best pairing so far: ((time, tractor), pairs)
    best = {frozenset(): ((0.0, 0.0), ())}

    # Add the detections one at a time
    for d_index in sorted(d_indexes):
        # Labels this detection could pair with
        options = []
        for l_index in sorted(l_indexes):
            if (
                same_cause_only
                and detections[d_index]["class"] != labels[l_index]["class"]
            ):
                continue
            overlap = pair_overlap(detections[d_index], labels[l_index])
            if overlap is not None:
                options.append((l_index, overlap))

        # Try adding this detection to every pairing so far
        updated = dict(best)
        for used, (weight, pairs) in best.items():
            for l_index, overlap in options:
                # Each label pairs only once
                if l_index in used:
                    continue

                # Keep the new pairing if it beats the old one for the same labels
                new_used = used | {l_index}
                new_weight = (weight[0] + overlap[0], weight[1] + overlap[1])
                new_pairs = pairs + ((l_index, d_index),)
                old = updated.get(new_used)
                if old is None or new_weight > old[0]:
                    updated[new_used] = (new_weight, new_pairs)
                elif new_weight == old[0] and new_pairs < old[1]:
                    updated[new_used] = (new_weight, new_pairs)
        best = updated

    # Most pairs, then most time overlap, then most tractor overlap, then earliest pairs
    winner = min(
        best,
        key=lambda used: (
            -len(used),
            -best[used][0][0],
            -best[used][0][1],
            best[used][1],
        ),
    )
    return dict(best[winner][1])


# Pair detections with labels one to one: same-cause pairs first, then any cause.
def match(detections: list[dict], labels: list[dict]) -> dict[int, int]:
    # Same-cause pairs
    all_d = list(range(len(detections)))
    all_l = list(range(len(labels)))
    matches = best_pairs(detections, labels, all_d, all_l, True)

    # Any cause, for what is left
    left_d = [i for i in all_d if i not in matches.values()]
    left_l = [i for i in all_l if i not in matches]
    matches.update(best_pairs(detections, labels, left_d, left_l, False))

    return matches


# Full credit within 5 min of the true start, down to 0 at 60 min.
def onset_credit(detection: dict, label: dict) -> float:
    # Minutes between the two starts (early and late count the same)
    error_min = abs((detection["start"] - label["start"]).total_seconds()) / 60

    # Close enough gets full credit
    if error_min <= config.ONSET_FULL_MIN:
        return 1.0

    # Minutes where the credit shrinks
    zero_range = config.ONSET_ZERO_MIN - config.ONSET_FULL_MIN

    # Less credit the further off, never below 0
    return max(0.0, (config.ONSET_ZERO_MIN - error_min) / zero_range)
