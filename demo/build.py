# Builds the small JSON files the demo page reads, from the latest pipeline outputs.
# Python does all the math here, so the page only draws.
#
# python -m demo.build

import json
import re
from pathlib import Path

import pandas as pd

from straightrows import config, score
from straightrows import s1_load, s2_mask, s3_features, s4_segment

# Where the page's data goes
OUT = Path(__file__).resolve().parent / "data"

# The deep-dive windows: one clear call and one ambiguous one
DEEP_DIVES = {
    "clear": ("2026-05-06T01:45Z", "2026-05-06T03:15Z"),
    "ambiguous": ("2026-05-06T17:45Z", "2026-05-06T20:45Z"),
}

# Seconds per point in the deep-dive charts
DEEP_DIVE_STEP_S = 10

# How each evidence line starts, and what kind of line it is
SIGN_PREFIXES = {
    "Seen": "seen",
    "Not seen": "not_seen",
    "Against": "against",
    "Nothing against": "nothing_against",
}


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
def build_minutes(telemetry: pd.DataFrame) -> dict:
    # Run the Prepare stages, like run.py
    minutes = s3_features.minute_features(telemetry, s1_load.load_labels())

    # Mark the minutes stage 4 calls bad, and the working minutes far off the line
    minutes["bad"] = s4_segment.is_signal_bad(minutes)
    off_line = minutes["cross_track_error_max_m"] > config.BAD_CROSS_TRACK_ERROR_M
    minutes["off_row"] = off_line & minutes["working"]

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
            "off_row",
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


# Split a detection's evidence into its summary, confidence math, signs, and notes.
def parse_evidence(detection: dict) -> dict:
    lines = detection["evidence"]

    # The summary line ends with what the cause means
    meaning = lines[0].split("): ", 1)[-1].rstrip(".")

    # The confidence line gives the counts
    counts = {"seen": 0, "of": 0, "bonus_seen": 0, "bonus_of": 0, "against": 0}
    found = re.search(r"(\d+) of (\d+) signs seen", lines[1])
    if found:
        counts["seen"], counts["of"] = int(found[1]), int(found[2])
    found = re.search(r"(\d+) of (\d+) bonus signs seen", lines[1])
    if found:
        counts["bonus_seen"], counts["bonus_of"] = int(found[1]), int(found[2])
    found = re.search(r"(\d+) against", lines[1])
    if found:
        counts["against"] = int(found[1])

    # Each sign line is "<prefix>: <label> (<detail>)."; anything else is a note
    signs = []
    notes = []
    for line in lines[2:]:
        prefix, _, rest = line.partition(": ")
        if prefix not in SIGN_PREFIXES:
            notes.append(line)
            continue
        label, _, detail = rest.rstrip(".").partition(" (")
        signs.append(
            {"state": SIGN_PREFIXES[prefix], "label": label, "detail": detail[:-1]}
        )

    return {
        "meaning": meaning,
        "signs": signs,
        "notes": notes,
        "formula": confidence_formula(counts, detection["confidence"]),
    }


# The confidence math written out, with the numbers from config.
def confidence_formula(counts: dict, confidence: float) -> str:
    if not counts["of"]:
        return ""
    spread = config.CONFIDENCE_SIGNS_CAP - config.CONFIDENCE_FLOOR
    parts = [
        f"{config.CONFIDENCE_FLOOR:.2f}",
        f"+ {spread:.2f} × {counts['seen']}/{counts['of']}",
    ]
    if counts["bonus_of"]:
        parts.append(f"+ {config.CONFIDENCE_BONUS:.2f} × {counts['bonus_seen']}")
    if counts["against"]:
        parts.append(f"− {config.CONFIDENCE_PENALTY:.2f} × {counts['against']}")
    return " ".join(parts) + f" = {confidence:.2f}"


# Every dev and eval detection with its status and parsed evidence, for section 5.
def build_episodes(matches: dict | None, detections: dict) -> list[dict]:
    # Dev detections carry their hit / false alarm / free status when scored
    if matches:
        dev = matches["detections"]
    else:
        dev = [{**d, "status": "dev", "label_id": None} for d in detections["dev"]]
    evals = [{**d, "status": "eval", "label_id": None} for d in detections["eval"]]

    # Add the parsed evidence to each one
    episodes = []
    for detection in dev + evals:
        episodes.append({**detection, **parse_evidence(detection)})
    return episodes


# Per-second data around each deep-dive window, thinned to one point per step.
def build_deep_dives(telemetry: pd.DataFrame) -> dict:
    result = {}
    for name, (start, end) in DEEP_DIVES.items():
        start, end = pd.Timestamp(start), pd.Timestamp(end)
        inside = telemetry[(telemetry["ts"] >= start) & (telemetry["ts"] < end)]

        # One block per tractor: the worst value in each step
        tractors = {}
        for tractor, rows in inside.groupby("tractor_id"):
            steps = rows.set_index("ts").resample(f"{DEEP_DIVE_STEP_S}s")
            table = pd.DataFrame(
                {
                    "signal_weakest_db": steps["signal_weakest_db"].min(),
                    "cross_track_error_m": steps["cross_track_error_m"].max(),
                    "base_link_lost": steps["base_link_ok"].min() == 0,
                }
            ).reset_index()
            table = table.round({"signal_weakest_db": 1, "cross_track_error_m": 2})
            tractors[tractor] = columns(table, ["ts"])
        result[name] = {
            "window": [format_time(start), format_time(end)],
            "tractors": tractors,
        }
    return result


# One plain sentence per cause test, with the numbers from config.
def cause_tests() -> dict:
    short = config.SHORT_EPISODE_MIN
    flicker = config.HIGH_FLICKER_S4
    return {
        "SPACE_WEATHER": (
            f"Several tractors drop together and signal flicker (S4) "
            f"reaches {flicker} or more."
        ),
        "JAMMING": (
            f"Several tractors drop together while S4 stays under {flicker}, "
            f"or every tractor steps down at once during a storm."
        ),
        "SPOOFING": (
            f"More than {config.BAD_CROSS_TRACK_ERROR_M} m off the line while the "
            f"signal looks healthy and the base link is fine, or a slow drift."
        ),
        "EQUIPMENT_FAULT": (
            f"One tractor drops while the others stay within "
            f"{config.FLEET_OK_DROP_DB} dB of normal, or its correction link is "
            f"lost for more than {short} min."
        ),
        "MULTIPATH": f"A short dip ({short} min or less) on one tractor.",
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
        "tests": cause_tests(),
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
    telemetry = s2_mask.add_working(s1_load.load_telemetry())
    write_json("meta.json", build_meta())
    write_json("minutes.json", build_minutes(telemetry))
    write_json("space_feeds.json", build_space_feeds())
    write_json("deep_dives.json", build_deep_dives(telemetry))

    labels = json.loads(config.LABELS.read_text(encoding="utf8"))["episodes"]
    write_json("labels.json", [as_text(score_times(label)) for label in labels])

    detections = {
        window: read_detections(path) for window, path in config.OUTPUT.items()
    }

    # Dev matching needs dev predictions; skip it if they're missing
    matches = build_matches() if config.OUTPUT["dev"].exists() else None
    if matches:
        write_json("matches.json", matches)
    write_json("episodes.json", build_episodes(matches, detections))

    # Copy the thresholds if a run has written them
    if config.THRESHOLDS.exists():
        write_json(
            "thresholds.json", json.loads(config.THRESHOLDS.read_text(encoding="utf8"))
        )

    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
