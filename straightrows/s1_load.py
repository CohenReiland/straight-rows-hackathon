# Stage 1: Read the provided data (telemetry and space feeds)

import json
import sys

import pandas as pd

from . import config


# Rename a table's columns from the file's names to ours, and stop if any are missing.
def convert_names(table: pd.DataFrame, fields: dict, source: str) -> pd.DataFrame:
    # fields is {ours: file's}, so flip it to rename
    file_rename = {field: name for name, field in fields.items()}
    table = table.rename(columns=file_rename)

    # Stop with a clear message if a field is missing
    ours = list(fields.keys())
    missing = [name for name in ours if name not in table.columns]
    if missing:
        raise ValueError(
            f"{source} is missing {missing}. Its fields are {list(table.columns)}. "
            "Fix its fields map in config.py."
        )

    return table[ours]


# Read and sort the telemetry.
def load_telemetry() -> pd.DataFrame:
    # Read the file and convert field names
    telemetry = pd.read_csv(config.TELEMETRY)
    telemetry = convert_names(telemetry, config.TELEMETRY_FIELDS, config.TELEMETRY.name)
    telemetry["ts"] = pd.to_datetime(telemetry["ts"], utc=True)

    # Warn if rows are missing
    if len(telemetry) != config.EXPECTED_ROWS:
        print(
            f"Warning: {len(telemetry)} rows, expected {config.EXPECTED_ROWS}",
            file=sys.stderr,
        )

    # Sort by tractor, then time
    return telemetry.sort_values(["tractor_id", "ts"]).reset_index(drop=True)


# Read a feed from its JSON file into a table with our column names.
def load_feed(feed: str) -> pd.DataFrame:
    file_name, list_key, time_columns = config.SPACE_FEED_FILES[feed]
    fields = config.SPACE_FEED_FIELDS[feed]

    # Read the list of records
    content = json.loads((config.SPACE_FEEDS / file_name).read_text(encoding="utf8"))
    table = pd.DataFrame(content[list_key])

    # An empty list still gets its columns
    if table.empty:
        table = pd.DataFrame(columns=list(fields.values()))

    # Use our column names
    table = convert_names(table, fields, f"{file_name} [{list_key}]")

    # Parse the times as UTC. ISO8601 because interference report times mix with and without microseconds
    for column in time_columns:
        table[column] = pd.to_datetime(table[column], utc=True, format="ISO8601")

    # Sort by the first time column
    return table.sort_values(time_columns[0]).reset_index(drop=True)


# Read each space feed into its own table, keyed by our feed name.
def load_space_feeds() -> dict[str, pd.DataFrame]:
    return {feed: load_feed(feed) for feed in config.SPACE_FEED_FILES}


# Read the labeled dev episodes, one row per episode.
def load_labels() -> pd.DataFrame:
    content = json.loads(config.LABELS.read_text(encoding="utf8"))
    labels = pd.DataFrame(content["episodes"])

    # Parse the times as UTC
    for column in ["start", "end"]:
        labels[column] = pd.to_datetime(labels[column], utc=True, format="ISO8601")

    return labels.sort_values("start").reset_index(drop=True)
