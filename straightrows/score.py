# Dev scoring: grade predictions against the labeled episodes.
#
# python -m straightrows.score dev_predictions.json

import json
from pathlib import Path

import pandas as pd

from . import config

# The five causes, in the guide's order
CAUSES = list(config.ACTIONS)


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


# Short multipath reports are not false alarms, unless they overlap a labeled one.
def is_exempt(detection: dict, labels: list[dict]) -> bool:
    # Length of the report
    length_min = (detection["end"] - detection["start"]).total_seconds() / 60

    # Only short multipath reports can be exempt
    if (
        detection["class"] != "MULTIPATH"
        or length_min > config.MULTIPATH_EXEMPT_MIN
    ):
        return False

    # Not exempt if it overlaps a labeled multipath on a shared tractor
    for label in labels:
        shares_tractor = bool(set(detection["tractors"]) & set(label["tractors"]))
        if (
            label["class"] == "MULTIPATH"
            and time_iou(detection, label) > 0
            and shares_tractor
        ):
            return False

    return True


# Grade the detections and return the score and its details.
def score(detections: list[dict], labels: list[dict]) -> dict:
    # Sort the detections so ties always break the same way
    detections = sorted(
        detections,
        key=lambda d: (d["start"], d["end"], d["class"], tuple(sorted(d["tractors"]))),
    )

    # Pair up detections and labels
    matches = match(detections, labels)
    label_for = {d_index: l_index for l_index, d_index in matches.items()}

    # Start every cause at zero
    counts = {cause: {"hits": 0, "false": 0, "missed": 0} for cause in CAUSES}

    # Start the label results
    outcomes = []
    total_onset = 0.0
    actions_agreed = 0

    # Check each label
    for l_index, label in enumerate(labels):
        # Get its detection, if it has one
        detection = detections[matches[l_index]] if l_index in matches else None

        if detection is not None and detection["class"] == label["class"]:
            # Right cause is a hit and earns onset credit
            counts[label["class"]]["hits"] += 1
            credit = onset_credit(detection, label)
            total_onset += credit
            outcomes.append((label, detection, credit))

            # Count it if the action matches the label's
            if detection.get("action") == label.get("recommended_action"):
                actions_agreed += 1
        else:
            # Anything else is a miss
            counts[label["class"]]["missed"] += 1
            outcomes.append((label, detection, 0.0))

    # Check each detection
    false_alarms = []
    free_multipath = 0
    for d_index, detection in enumerate(detections):
        # Skip hits
        is_hit = (
            d_index in label_for
            and labels[label_for[d_index]]["class"] == detection["class"]
        )
        if is_hit:
            continue

        # Skip exempt reports
        if d_index not in label_for and is_exempt(detection, labels):
            free_multipath += 1
            continue

        # Everything else is a false alarm
        counts[detection["class"]]["false"] += 1
        false_alarms.append(detection)

    # Work out F1 for each cause
    for cause in CAUSES:
        hits = counts[cause]["hits"]
        false = counts[cause]["false"]
        missed = counts[cause]["missed"]
        counts[cause]["f1"] = 2 * hits / (2 * hits + false + missed) if hits else 0.0

    # Average the five F1 scores
    macro_f1 = sum(counts[cause]["f1"] for cause in CAUSES) / len(CAUSES)

    # Average the onset credit
    mean_onset = total_onset / len(labels) if labels else 0.0

    # Return the final score and details
    return {
        "total": 25 * macro_f1 + 15 * mean_onset,
        "macro_f1": macro_f1,
        "mean_onset": mean_onset,
        "counts": counts,
        "outcomes": outcomes,
        "false_alarms": false_alarms,
        "free_multipath": free_multipath,
        "actions_agreed": actions_agreed,
    }


# Format a time as day and clock.
def short_time(time: pd.Timestamp) -> str:
    return time.strftime("%m-%d %H:%M")


# Score a file against the dev labels and print a report.
def report(path: Path) -> dict:
    # Grade the file
    detections = read_items(path, "detections")
    result = score(detections, read_items(config.LABELS, "episodes"))

    # Print the total score
    print(
        f"\nDev score {result['total']:.1f} / 40  "
        f"(macro-F1 {result['macro_f1']:.2f} = {25 * result['macro_f1']:.1f}, "
        f"onset {result['mean_onset']:.2f} = {15 * result['mean_onset']:.1f})"
    )

    # Print how many hits had the label's action
    print(f"  actions agreed: {result['actions_agreed']} of {len(result['outcomes'])}")

    # Print one line per cause
    print(f"  {'cause':16} hits  false  missed   F1")
    for cause, c in result["counts"].items():
        counts = f"{c['hits']:4}  {c['false']:5}  {c['missed']:6}"
        print(f"  {cause:16} {counts}  {c['f1']:.2f}")

    # Print what happened to each label
    print("Labels:")
    for label, detection, credit in result["outcomes"]:
        name = f"{label['id']} {label['class']:15} {','.join(label['tractors']):8}"
        if detection is None:
            print(f"  {name} missed")
        elif detection["class"] != label["class"]:
            print(f"  {name} wrong cause ({detection['class']})")
        else:
            error_min = (detection["start"] - label["start"]).total_seconds() / 60
            print(f"  {name} hit, onset {error_min:+.1f} min, credit {credit:.2f}")

    # Labels that a wrong-cause detection was paired with, by detection
    wrong_for = {
        id(detection): label["id"]
        for label, detection, _ in result["outcomes"]
        if detection is not None and detection["class"] != label["class"]
    }

    # Print the false alarms, marking the ones that were a wrong cause
    print(f"False alarms ({len(result['false_alarms'])}):")
    for detection in result["false_alarms"]:
        wrong = wrong_for.get(id(detection))
        note = f"  (wrong cause for {wrong})" if wrong else ""
        print(
            f"  {short_time(detection['start'])} to {detection['end']:%H:%M}  "
            f"{','.join(detection['tractors']):8} {detection['class']}{note}"
        )

    # Print how many short multipath reports were let off
    print(f"Free multipath reports: {result['free_multipath']}")

    return result
