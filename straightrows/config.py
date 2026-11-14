# All paths, windows, and thresholds.

from pathlib import Path

# File locations
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TELEMETRY = DATA / "farm" / "tractor_telemetry.csv.gz"
SPACE_FEEDS = DATA / "sda"

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
