# Stage 5: group candidates that overlap in time.

import pandas as pd

# Kinds that group together, and whether overlapping ones join into one event.
# Steps, dips and drifts sit inside episodes, so they are kept apart from them
EVENT_GROUPS = [(["link", "signal"], True), (["step"], True), (["dip", "drift"], False)]


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

    # Number each group of kinds after the last, joining overlaps where it should
    candidates["event"] = 0
    next_event = 0
    for kinds, join_overlaps in EVENT_GROUPS:
        chosen = candidates["kind"].isin(kinds)
        group = candidates[chosen]
        if group.empty:
            continue
        if join_overlaps:
            numbers = overlap_numbers(group["start"], group["end"])
        else:
            numbers = list(range(len(group)))
        candidates.loc[chosen, "event"] = [next_event + n for n in numbers]
        next_event += max(numbers) + 1

    return candidates
