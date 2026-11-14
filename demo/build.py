# Builds the small JSON files the demo page reads, from the latest pipeline outputs.
# Python does all the math here, so the page only draws.
#
# python -m demo.build

import json
from pathlib import Path

import pandas as pd

from straightrows import config, score
from straightrows import s1_load, s2_mask, s3_features, s4_segment

# Where the page's data goes
OUT = Path(__file__).resolve().parent / "data"


# A time as ISO 8601 UTC text, like submission.json.
def format_time(time) -> str:
    return pd.Timestamp(time).strftime("%Y-%m-%dT%H:%M:%SZ")


# Write one JSON file, small (no spaces).
def write_json(name: str, content) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(content, separators=(",", ":")), encoding="utf8")


# A table's times as text and its other values as plain lists, one list per column.
def columns(table: pd.DataFrame, time_columns: list[str]) -> dict:
    result = {}
    for column in table.columns:
        if column in time_columns:
            result[column] = [format_time(time) for time in table[column]]
        else:
            # Missing values become null, since JSON has no NaN
            values = table[column].astype(object)
            result[column] = values.where(values.notna(), None).tolist()
    return result


# One row per tractor per minute, one list per signal.
def build_minutes() -> dict:
    # Run the Prepare stages, like run.py
    telemetry = s2_mask.add_working(s1_load.load_telemetry())
    minutes = s3_features.minute_features(telemetry, s1_load.load_labels())

    # Mark the minutes stage 4 calls bad, for debugging
    minutes["bad"] = s4_segment.is_signal_bad(minutes)

    # Keep only what the charts draw, rounded to keep the file small
    keep = minutes[
        [
            "tractor_id",
            "minute",
            "working",
            "signal_mean_db",
            "signal_weakest_db",
            "num_sats_min",
            "fix_rank_worst",
            "base_link_lost",
            "cross_track_error_max_m",
            "bad",
        ]
    ].round({"signal_mean_db": 2, "signal_weakest_db": 2, "cross_track_error_max_m": 3})

    # One block per tractor
    return {
        tractor: columns(rows.drop(columns="tractor_id"), ["minute"])
        for tractor, rows in keep.groupby("tractor_id")
    }


# The space feeds: storm strength, field drop, signal flicker, advisories, interference reports.
def build_space_feeds() -> dict:
    feeds = s1_load.load_space_feeds()
    time_columns = {
        "storm_kp": ["ts"],
        "storm_field_drop": ["ts"],
        "signal_flicker_s4": ["ts"],
        "advisories": ["issued"],
        "interference_reports": ["received"],
    }
    return {feed: columns(table, time_columns[feed]) for feed, table in feeds.items()}


# Read the detections from one output file, or none if it hasn't been made yet.
def read_detections(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf8"))["detections"]


# A label or detection with its times as text again.
def as_text(item: dict) -> dict:
    return {
        **item,
        "start": format_time(item["start"]),
        "end": format_time(item["end"]),
    }


# Grade the dev predictions exactly like python -m straightrows.score.
def build_matches() -> dict:
    detections = score.read_items(config.OUTPUT["dev"], "detections")
    labels = score.read_items(config.LABELS, "episodes")
    return match_report(detections, labels)


# Match detections to labels with score.py, so the page and the score agree.
def match_report(detections: list[dict], labels: list[dict]) -> dict:
    result = score.score(detections, labels)

    # What happened to each label
    label_results = []
    detection_status = {}
    for label, detection, credit in result["outcomes"]:
        entry = {"label_id": label["id"], "status": "missed", "credit": credit}
        if detection is not None:
            entry["detection"] = as_text(detection)
            entry["time_iou"] = round(score.time_iou(detection, label), 3)
            entry["onset_min"] = (
                detection["start"] - label["start"]
            ).total_seconds() / 60
            if detection["class"] == label["class"]:
                entry["status"] = "hit"
                detection_status[id(detection)] = ("hit", label["id"])
            else:
                entry["status"] = "wrong_cause"
                detection_status[id(detection)] = ("false_alarm", label["id"])
        label_results.append(entry)

    # False alarms that weren't matched to anything
    for detection in result["false_alarms"]:
        detection_status.setdefault(id(detection), ("false_alarm", None))

    # Every dev detection gets a status; anything left is a free short multipath
    detection_results = []
    for detection in detections:
        status, label_id = detection_status.get(id(detection), ("exempt", None))
        detection_results.append(
            {**as_text(detection), "status": status, "label_id": label_id}
        )

    return {
        "total": result["total"],
        "macro_f1": result["macro_f1"],
        "mean_onset": result["mean_onset"],
        "actions_agreed": result["actions_agreed"],
        "free_multipath": result["free_multipath"],
        "counts": result["counts"],
        "labels": label_results,
        "detections": detection_results,
    }


# Window times, causes, actions, and the cutoff lines, so the page doesn't repeat config.
def build_meta() -> dict:
    return {
        "windows": {
            window: [format_time(start), format_time(end)]
            for window, (start, end) in config.WINDOWS.items()
        },
        "actions": config.ACTIONS,
        "fix_rank": config.FIX_RANK,
        "cutoffs": {
            "BAD_CROSS_TRACK_ERROR_M": config.BAD_CROSS_TRACK_ERROR_M,
            "STORM_KP": config.STORM_KP,
            "STORM_FIELD_DROP_NT": config.STORM_FIELD_DROP_NT,
            "HIGH_FLICKER_S4": config.HIGH_FLICKER_S4,
        },
        "built": format_time(pd.Timestamp.now(tz="UTC")),
    }


# A label's times as timestamps, so labels use the same "Z" text as detections.
def score_times(label: dict) -> dict:
    return {
        **label,
        "start": pd.Timestamp(label["start"]),
        "end": pd.Timestamp(label["end"]),
    }


# Write every data file.
def main() -> None:
    write_json("meta.json", build_meta())
    write_json("minutes.json", build_minutes())
    write_json("space_feeds.json", build_space_feeds())

    labels = json.loads(config.LABELS.read_text(encoding="utf8"))["episodes"]
    write_json("labels.json", [as_text(score_times(label)) for label in labels])

    detections = {
        window: read_detections(path) for window, path in config.OUTPUT.items()
    }
    write_json("detections.json", detections)

    # Dev matching needs dev predictions; skip it if they're missing
    if config.OUTPUT["dev"].exists():
        write_json("matches.json", build_matches())

    # Copy the thresholds if a run has written them
    if config.THRESHOLDS.exists():
        write_json(
            "thresholds.json", json.loads(config.THRESHOLDS.read_text(encoding="utf8"))
        )

    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
