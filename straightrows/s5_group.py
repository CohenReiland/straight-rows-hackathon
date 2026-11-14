# Stage 5: group candidates that overlap in time.

import pandas as pd


# Number the time spans so overlapping spans share a number.
# The spans are sorted by start.
def overlap_numbers(starts: list[pd.Timestamp], ends: list[pd.Timestamp]) -> list[int]:
    # Set up the tracking
    numbers = []
    number = -1
    group_end = None

    # Go through the spans in order
    for start, end in zip(starts, ends):
        if group_end is None or start > group_end:
            # After a gap, start a new group
            number += 1
            group_end = end
        else:
            # Otherwise, extend the current group
            group_end = max(group_end, end)

        # Save the group number
        numbers.append(number)

    return numbers


# Give each candidate an event number.
def group_events(candidates: pd.DataFrame) -> pd.DataFrame:
    # Sort by start time
    candidates = candidates.sort_values("start").reset_index(drop=True)

    # Overlapping episodes are one event (dips are left out)
    is_dip = candidates["kind"] == "dip"
    episodes = candidates[~is_dip]
    numbers = overlap_numbers(episodes["start"], episodes["end"])
    candidates["event"] = 0
    candidates.loc[~is_dip, "event"] = numbers

    # Each dip is its own event, numbered after the episodes
    first_dip = max(numbers) + 1 if numbers else 0
    candidates.loc[is_dip, "event"] = range(first_dip, first_dip + int(is_dip.sum()))

    return candidates
