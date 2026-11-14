# Stage 8: save, validate, and summarize the detections.

import json
import subprocess
import sys
from pathlib import Path

from . import config


# Save the detections to a file.
def write(detections: list[dict], window: str) -> Path:
    # Get the output file
    path = config.OUTPUT[window]

    # Build the submission
    submission = {
        "participant": config.PARTICIPANT,
        "repository_url": config.REPOSITORY_URL,
        "detections": detections,
    }

    # Write the file
    path.write_text(json.dumps(submission, indent=2) + "\n", encoding="utf8")

    return path


# Run the validator on the file.
def validate(path: Path) -> bool:
    result = subprocess.run([sys.executable, str(config.VALIDATOR), str(path)])
    return result.returncode == 0
