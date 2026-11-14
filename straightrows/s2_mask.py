# Stage 2: mark which rows are working.

import pandas as pd

from . import config


# Add a working column. True if the tractor moved within 30 s of that row.
def add_working(telemetry: pd.DataFrame) -> pd.DataFrame:
    # 1 if the tractor is moving, 0 if not
    is_moving = (telemetry["speed_mps"] > config.WORKING_SPEED_MPS).astype(int)

    # Seconds to look at around each row. Counts rows, so it relies on one row per second
    # with no gaps. The loader warns if rows are missing.
    window_size = 2 * config.WORKING_LOOKAROUND_S + 1

    # Start every row as parked
    working = pd.Series(False, index=telemetry.index)

    # Check one tractor at a time
    for tractor in telemetry["tractor_id"].unique():
        # Get this tractor's rows
        this_tractor = telemetry["tractor_id"] == tractor

        # Check if it moved near each row
        moved_nearby = (
            is_moving[this_tractor].rolling(window_size, center=True, min_periods=1).max()
        )

        # Save the result
        working[this_tractor] = (moved_nearby > 0).to_numpy()

    # Return a copy with the working column
    return telemetry.assign(working=working)
