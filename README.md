# Straight Rows: GNSS Degradation Attribution

This is a Python pipeline for the Bluestaq × NDSU Straight Rows hackathon. It reads 72 hours of GNSS telemetry from three tractors and five space domain awareness (SDA) feeds. For the evaluation day it finds each degraded episode and names the cause and the operator action. It then writes `submission.json` with a confidence and evidence for each detection.

The pipeline uses rules for each cause, not a trained model. Twelve labeled episodes are too few to train on, and rules can be explained and changed live. The official guide is `docs/Bluestaq_NDSU_Straight_Rows_Hackathon_Official.pdf`. The Bluestaq starter files (`data/`, `submission/`, `notebooks/`, `docs/`, `scripts/get_data.py`) are left as they came.

## 1. Setup and Run

You need Python 3.11 or newer. It was built and tested on Python 3.13 on Windows. From the repo root, run:

```bash
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scripts/get_data.py         # downloads the dataset into data/ and checks its SHA-256
```

The pinned dependencies in `requirements.txt` are the official starter's: `numpy==2.3.3`, `pandas==2.3.3`, `matplotlib==3.10.6`. If you already have the package ZIP, run `python scripts/get_data.py --zip StraightRows_Student_Package.zip` instead.

This command regenerates the submitted results. It writes `submission.json` for 2026-05-06 and runs the official validator on it:

```bash
python run.py --window eval
```

To check the rules, run `python run.py --window dev`. It writes `dev_predictions.json` for 2026-05-04 and 2026-05-05 and scores it against the 12 labels. The runs take about 20 and 30 seconds, and the same data always gives the same file. Every run also writes `thresholds.json` with each tractor's normal and the cutoffs.

## 2. Tests

The tests are plain Python with small made-up cases, so they need neither pytest nor the data. There are 65 tests in 9 files under `tests/`, and you run each file by name:

```bash
python -m tests.test_load        # also: test_mask, test_features, test_segment, test_group,
                                 # test_attribute, test_decide, test_evidence, test_score
```

`tests/test_decide.py` prints three `warning:` lines on purpose.

## 3. Demo Page

The demo page walks through the data, the rules, the development check, the evaluation results, one deep dive, and the limits. It only draws what the pipeline already decided.

```bash
python -m pip install -r requirements-demo.txt   # plotly==7.1.0
python run.py --window dev
python run.py --window eval
python -m demo.serve                             # then open http://localhost:8000
```

`python -m demo.serve` builds `demo/data/` first, then serves the page. It works offline, since Plotly is served from the installed package. If port 8000 is taken, use `python -m demo.serve --port 8001`.

## 4. Approach

The 8 stages live in `straightrows/` and run in order from `run.py`. Every cutoff is in `straightrows/config.py`. Each one is marked **fixed** (from the guide, the scorer, or a standard level) or **learned** (picked from the development data).

- **Prepare:** load the data and summarize each minute.
  - `s1_load.py` reads the telemetry and the five feeds. Then `s2_mask.py` marks working rows, so parked rows are never scored.
  - `s3_features.py` compares each minute with the tractor's own normal and with the worst other tractor. The normal is the median of calm development minutes, which are working and outside every label. The evaluation day never sets the normal.
- **Find:** turn bad minutes into candidate episodes (`s4_segment.py`, `s5_group.py`).
  - A minute is bad when the weakest satellite is more than 13 dB below normal or the tractor is more than 0.50 m off its row. A fix below `RTK_FIXED` with the link up is also bad.
  - Bad minutes up to 3 minutes apart join into one episode. The edges then stretch up to 30 minutes, while the average signal stays 3 dB or more below normal.
  - A short dip is the weakest satellite falling 5 dB under its 2-minute median for at least 7 seconds.
  - A drift is a run of 3-minute blocks at least 1 m off the row, with a spread under 0.3 m.
  - A step is the average signal falling 5 dB below its last 30 minutes, on top of an episode.
- **Explain:** test the causes and write the evidence (`s6_attribute.py`, `s7_decide.py`, `evidence.py`, `s8_emit.py`).

| Cause             | Test                                                                                                          | Action                            |
| ----------------- | ------------------------------------------------------------------------------------------------------------- | --------------------------------- |
| `MULTIPATH`       | A short dip, or an episode of 3 minutes or less                                                               | `CONTINUE_FALSE_ALARM`            |
| `EQUIPMENT_FAULT` | Signal down on this tractor while the worst other tractor dropped less than 2.5 dB, or a lost correction link | `SERVICE_MACHINE_OTHERS_CONTINUE` |
| `SPACE_WEATHER`   | Signal down on the fleet too, with signal flicker (S4) at 0.3 or more                                         | `HALT_OR_DEGRADED_MODE`           |
| `JAMMING`         | Signal down on the fleet too, with S4 under 0.3, or a step on the fleet                                       | `HALT_AND_REPORT`                 |
| `SPOOFING`        | More than 0.50 m off the row with a healthy signal and the link up, or a drift                                | `HALT_CROSSCHECK_AND_REPORT`      |

If several tests pass, the first in this order wins: multipath, spoofing, space weather, jamming, equipment fault. If none pass, the pipeline warns and uses `EQUIPMENT_FAULT`. Two causes at the same time become separate detections, and each one names the other.

The space feeds (Kp, Dst, S4, interference reports, satellite advisories) never pick the cause. They only add signs for or against it. Confidence is `0.40 + 0.45 × (share of signs seen) + 0.10 × bonus signs − 0.15 × signs against`, kept between 0.40 and 0.95. The evidence gives one sentence per sign with its value and cutoff.

## 5. How the Labeled Data Was Used

The 12 labeled development episodes were the tuning set. Nothing was tuned on the evaluation day, and it was only run to check that the file is valid.

`straightrows/score.py` is a port of the official scorer: 25 × macro-F1 plus 15 × onset credit. On the development predictions it gives the same result as Bluestaq's `scoring/score_submission.py`. The learned cutoffs were set just above the calm development minutes. For example, 13 dB flags no calm minute and still finds every label. The unit tests use made-up cases, not the labels.

## 6. Results

**Development:** 40.0 / 40 (macro-F1 1.00, onset credit 1.00), and all 12 actions agree.

| Label \ Call      | `SPACE_WEATHER` | `JAMMING` | `SPOOFING` | `EQUIPMENT_FAULT` | `MULTIPATH` | Missed |
| ----------------- | --------------- | --------- | ---------- | ----------------- | ----------- | ------ |
| `SPACE_WEATHER`   | 2               |           |            |                   |             |        |
| `JAMMING`         |                 | 3         |            |                   |             |        |
| `SPOOFING`        |                 |           | 3          |                   |             |        |
| `EQUIPMENT_FAULT` |                 |           |            | 2                 |             |        |
| `MULTIPATH`       |                 |           |            |                   | 2           |        |

Every label is found with the right cause, and no false alarm is scored. Ten calls start on the labeled minute, and TRN-06 and TRN-08 start 1 minute late. The run also reports 913 short multipath dips that match no label. They cost nothing, since the scorer does not count multipath reports of 3 minutes or less. One candidate (T1 at 2026-05-05 02:00) passed no test, and it joined the real fault TRN-10. A perfect score shows the rules fit these 12 episodes. It does not show how they do on new data.

**Evaluation:** `submission.json` has 447 detections. That is 7 episodes and 440 short multipath reports.

| Start to end (UTC) | Tractors   | Cause             | Confidence |
| ------------------ | ---------- | ----------------- | ---------- |
| 01:00 to 02:00     | T1         | `EQUIPMENT_FAULT` | 0.85       |
| 02:12 to 02:55     | T1, T2, T3 | `JAMMING`         | 0.95       |
| 13:00 to 16:00     | T1, T2, T3 | `SPACE_WEATHER`   | 0.84       |
| 16:30 to 17:12     | T1         | `SPOOFING`        | 0.85       |
| 18:30 to 19:00     | T1, T2, T3 | `JAMMING`         | 0.85       |
| 19:48 to 20:30     | T2         | `EQUIPMENT_FAULT` | 0.85       |
| 21:49 to 22:24     | T3         | `SPOOFING`        | 0.85       |

Two candidates on T2 (19:48 and 20:11) passed no test and fell back to `EQUIPMENT_FAULT`. They were not looked at further, so the evaluation day stays untuned.

## 7. Failure Modes

- **Short dips:** every one is reported as multipath.
  - The evaluation day has 440, mostly at row ends with all three tractors dipping together. The shortest dip is 7 seconds, which is the shortest that stays under the validator's 500-detection limit.
  - Without per-satellite data, row-end shading cannot be told apart from true multipath.
- **Wrong cause:** cases the rules would call wrong.
  - Jamming on one tractor reads as `EQUIPMENT_FAULT`. A base-station outage reads as three equipment faults.
  - A signal fault on one tractor during a storm reads as `SPACE_WEATHER`.
  - The fleet is only two other tractors. So one of them having its own problem can make a fault look regional.
- **Limits:** what the rules and data cannot show.
  - Not every combination of two or three causes has been tested, since the labels show only a few.
  - The rules fit the development data, and real data is messier.
  - The confidence weights are a judgment call, since the scorer does not use confidence.
  - It runs on recorded data after the fact. A real scenario would need it to run in real time.

## 8. Data That Would Help

- **AGC level and noise floor:** these jump under jamming, so they would catch jamming on one tractor.
- **Per-satellite signal strength with satellite IDs:** this would tell shading from multipath and match satellite advisories.
- **More labeled episodes:** especially single-tractor jamming, faults during storms, and base-station outages.
- **Base-station logs, wheel odometry or an IMU, and a field map:** these would check the link, the position, and known reflectors.

## 9. External Services and AI Use

The pipeline makes no network calls and uses no AI at runtime. So it runs offline once the data is downloaded. The validator `submission/validate_submission.py` is the official starter's. The demo page only requests Google Fonts, and it falls back to system fonts. AI coding assistants (Claude Code) were used while building, writing tests, and reviewing. Every rule and cutoff was chosen and reviewed by me.
