# Runs the whole pipeline for one window.
#
# python run.py --window eval     # writes submission.json and validates it
# python run.py --window dev      # writes dev_predictions.json and scores it

import argparse
import sys
import time

from straightrows import score
from straightrows import s1_load, s2_mask, s3_features, s4_segment, s5_group
from straightrows import s6_attribute, s7_decide, s8_emit


# Run all 8 stages for one window.
def main() -> None:
    # Get the window from the command line
    parser = argparse.ArgumentParser(description="Straight Rows pipeline")
    parser.add_argument("--window", choices=["dev", "eval"], default="eval")
    window = parser.parse_args().window

    # Start the timer
    start_time = time.perf_counter()

    # Prepare: load the data, mark working rows, and summarize each minute.
    telemetry = s2_mask.add_working(s1_load.load_telemetry())
    space_feeds = s1_load.load_space_feeds()
    minutes = s3_features.minute_features(telemetry, s1_load.load_labels())

    # Find: get the episodes and group them into events
    candidates = s5_group.group_events(s4_segment.find_candidates(minutes, window))

    # Explain: test the causes, pick one, and write the evidence
    tested = s6_attribute.test_candidates(candidates, minutes, telemetry, space_feeds)
    detections = s7_decide.make_detections(tested, space_feeds)

    # Save and print a summary
    path = s8_emit.write(detections, window)
    s8_emit.write_thresholds(minutes)
    s8_emit.summarize(detections)
    print(f"wrote {path.name} in {time.perf_counter() - start_time:.1f}s")

    # Score dev runs, validate eval runs
    if window == "dev":
        score.report(path)
    elif not s8_emit.validate(path):
        sys.exit(1)


if __name__ == "__main__":
    main()
