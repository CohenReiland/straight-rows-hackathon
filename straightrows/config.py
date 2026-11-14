# All paths, windows, and thresholds.

from pathlib import Path

# File locations
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TELEMETRY = DATA / "farm" / "tractor_telemetry.csv.gz"
SPACE_FEEDS = DATA / "sda"
LABELS = DATA / "labels" / "train_episodes.json"

# Where run.py writes each window's detections
OUTPUT = {"dev": ROOT / "dev_predictions.json", "eval": ROOT / "submission.json"}

# Rows the telemetry has
EXPECTED_ROWS = 777_600

# Telemetry column names, as {our column: column name in the file}
TELEMETRY_FIELDS = {
    "ts": "ts",
    "tractor_id": "tractor_id",
    "lat": "lat",
    "lon": "lon",
    "speed_mps": "speed_mps",
    "cross_track_error_m": "cross_track_error_m",
    "num_sats": "num_sats",
    "signal_mean_db": "mean_cn0_dbhz",
    "signal_weakest_db": "min_cn0_dbhz",
    "fix_state": "fix_state",
    "base_link_ok": "base_link_ok",
}

# Where each space feed is: (file, list key inside it, columns that are times)
SPACE_FEED_FILES = {
    "storm_kp": ("sgi_indices.json", "kp", ["ts"]),
    "storm_field_drop": ("sgi_indices.json", "dst", ["ts"]),
    "signal_flicker_s4": ("scintillation_series.json", "series", ["ts"]),
    "advisories": ("constellation_advisories.json", "advisories", ["issued"]),
    "interference_reports": ("rfi_reports.json", "reports", ["received"]),
}

# Space feed field names, as {our column: field name in the file}.
SPACE_FEED_FIELDS = {
    "storm_kp": {"ts": "ts", "storm_kp": "kp"},
    "storm_field_drop": {"ts": "ts", "storm_field_drop_nt": "dst_nT"},
    "signal_flicker_s4": {"ts": "ts", "signal_flicker_s4": "s4"},
    "advisories": {
        "advisory_id": "id",
        "issued": "ts",
        "type": "type",
        "svn": "svn",
        "text": "text",
    },
    "interference_reports": {
        "report_id": "id",
        "received": "ts",
        "band": "band",
        "confidence": "confidence",
        "lat": "centerLat",
        "lon": "centerLon",
        "area_long_km": "semiMajor_km",
        "area_short_km": "semiMinor_km",
        "text": "text",
    },
}

# Mask settings
# A tractor is moving above this speed. fixed (real speed is only 0 or 4.5 m/s)
WORKING_SPEED_MPS = 0.5
# A row counts as working if the tractor moved within this many seconds of it. fixed
WORKING_LOOKAROUND_S = 30

# Fix states, worst to best. fixed (README)
FIX_RANK = {"NO_FIX": 0, "AUTONOMOUS": 1, "DGPS": 2, "RTK_FLOAT": 3, "RTK_FIXED": 4}

# A minute is working if more 50% of its seconds are working. fixed
WORKING_MINUTE_SHARE = 0.5

# Scoring rules
# A detection matches a label only if both overlaps reach these. fixed
MATCH_TIME_IOU = 0.30
MATCH_TRACTOR_IOU = 0.50
# Onset credit is full within this many minutes of the true start. fixed
ONSET_FULL_MIN = 5
# Onset credit falls to 0 at this many minutes off. fixed
ONSET_ZERO_MIN = 60
# Multipath reports this many minutes or shorter are not false alarms. fixed
MULTIPATH_EXEMPT_MIN = 3

# Causes and the action for each, in the guide's order. fixed (guide, matches labels)
ACTIONS = {
    "SPACE_WEATHER": "HALT_OR_DEGRADED_MODE",
    "JAMMING": "HALT_AND_REPORT",
    "SPOOFING": "HALT_CROSSCHECK_AND_REPORT",
    "EQUIPMENT_FAULT": "SERVICE_MACHINE_OTHERS_CONTINUE",
    "MULTIPATH": "CONTINUE_FALSE_ALARM",
}
