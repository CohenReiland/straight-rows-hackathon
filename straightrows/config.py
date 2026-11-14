# All paths, windows, and thresholds.

from pathlib import Path

import pandas as pd

# File locations
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TELEMETRY = DATA / "farm" / "tractor_telemetry.csv.gz"
SPACE_FEEDS = DATA / "sda"
LABELS = DATA / "labels" / "train_episodes.json"
VALIDATOR = ROOT / "submission" / "validate_submission.py"

# Where run.py writes each window's detections
OUTPUT = {"dev": ROOT / "dev_predictions.json", "eval": ROOT / "submission.json"}
# Each tractor's normal and the cutoffs, rewritten every run
THRESHOLDS = ROOT / "thresholds.json"

# Who is submitting: GitHub username only, never email or student ID. fixed
PARTICIPANT = {"github_handle": "CohenReiland"}
REPOSITORY_URL = "https://github.com/CohenReiland/straight-rows-hackathon"

# Time windows, start included and end left out. fixed (README)
WINDOWS = {
    "dev": (pd.Timestamp("2026-05-04T00:00Z"), pd.Timestamp("2026-05-06T00:00Z")),
    "eval": (pd.Timestamp("2026-05-06T00:00Z"), pd.Timestamp("2026-05-07T00:00Z")),
}

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

# Segment settings
# A minute is bad if its weakest satellite is this far below normal. learned
BAD_WEAKEST_DROP_DB = 13.0
# A minute is bad if the tractor strays this far off its line. learned
BAD_CROSS_TRACK_ERROR_M = 0.50
# Stretch an episode while the average signal is still this far below normal. learned
WEAK_MEAN_DROP_DB = 3.0
# Bad minutes this close together join into one episode. learned
MAX_GAP_MIN = 3
# A dip is the weakest satellite this far under its normal for the moment. fixed
DIP_DROP_DB = 5.0
# Seconds around each second used for that normal (its median). fixed
DIP_NORMAL_WINDOW_S = 120
# Shortest dip reported as multipath, to stay under 500 detections. fixed
MIN_DIP_S = 10
# Minutes in each block when looking for a smooth drift off the line. fixed
DRIFT_BLOCK_MIN = 3
# A block drifts if its median cross-track error reaches this. fixed
DRIFT_MEDIAN_M = 1.0
# its cross-track error spread (standard deviation) stays under this. fixed
DRIFT_SPREAD_M = 0.3
# Drifting blocks this many blocks apart or closer join into one drift. fixed
DRIFT_MAX_GAP_BLOCKS = 1
# Walk a drift's start back while each minute's median is this far above the last
DRIFT_RISE_M = 0.05
# Minutes before each minute used for its own level (median average drop). fixed
STEP_LOOKBACK_MIN = 30
# A step is the average drop rising this far above that level. fixed
STEP_RISE_DB = 5.0
# Shortest step kept, in minutes. fixed
MIN_STEP_MIN = 10

# Cause test settings
# Look this far before an episode for signal flicker (S4) readings. fixed
FLICKER_LOOKBACK_MIN_S4 = 15
# Episodes this many minutes or shorter are short (multipath). fixed
SHORT_EPISODE_MIN = 3
# The signal is healthy if the average stayed within this much of normal. learned
HEALTHY_MAX_DROP_DB = 3.0
# The fleet is fine if the other tractors dropped less than this. learned
FLEET_OK_DROP_DB = 2.5
# Signal flicker (S4) at or above this means a storm. fixed 
HIGH_FLICKER_S4 = 0.3
# Causes that stay on one tractor and never join across tractors. fixed (guide)
ONE_TRACTOR_CAUSES = ["EQUIPMENT_FAULT", "MULTIPATH"]
