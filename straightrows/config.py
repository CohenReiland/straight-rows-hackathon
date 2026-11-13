# All paths, windows, and thresholds.

from pathlib import Path

# File locations
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TELEMETRY = DATA / "farm" / "tractor_telemetry.csv.gz"

# Rows the telemetry has
EXPECTED_ROWS = 777_600
