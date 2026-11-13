# Stage 1: Read the provided data (telemetry and space feeds)

import sys

import pandas as pd

from . import config


# Read and sort the telemetry.
def load_telemetry() -> pd.DataFrame:
    # Read the file
    telemetry = pd.read_csv(config.TELEMETRY)
    telemetry["ts"] = pd.to_datetime(telemetry["ts"], utc=True)

    # Warn if rows are missing
    if len(telemetry) != config.EXPECTED_ROWS:
        print(
            f"Warning: {len(telemetry)} rows, expected {config.EXPECTED_ROWS}",
            file=sys.stderr,
        )

    # Sort by tractor, then time
    return telemetry.sort_values(["tractor_id", "ts"]).reset_index(drop=True)
