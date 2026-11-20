# NDSU x Bluestaq "Straight Rows" Hackathon

My entry for the Bluestaq × NDSU Straight Rows hackathon. A Python pipeline reads 72 hours of GNSS telemetry from three tractors plus five space-weather feeds. It finds each degraded episode, names the cause and the operator action, and writes `submission.json`.

It uses rules for each cause, not a trained model, because 12 labeled episodes are too few to train on. The official guide is in `docs/`.

## Results

- **Dev:** 40.0 / 40. All 12 labels found with the right cause.
- **Eval:** 7 episodes plus 440 short multipath reports in `submission.json`.

## How it works

`run.py` runs 8 stages in `straightrows/` (load, mask, features, segment, group, attribute, decide, emit). Every cutoff lives in `straightrows/config.py`.

| Cause | Test | Action |
|---|---|---|
| `MULTIPATH` | A short dip, or an episode of 3 min or less | `CONTINUE_FALSE_ALARM` |
| `EQUIPMENT_FAULT` | Only this tractor's signal drops, or a lost correction link | `SERVICE_MACHINE_OTHERS_CONTINUE` |
| `SPACE_WEATHER` | Fleet-wide signal drop with S4 ≥ 0.3 | `HALT_OR_DEGRADED_MODE` |
| `JAMMING` | Fleet-wide signal drop with S4 < 0.3 | `HALT_AND_REPORT` |
| `SPOOFING` | Off the row with a healthy signal and the link up | `HALT_CROSSCHECK_AND_REPORT` |

## Big decisions

- **No LLM and no trained model.** We weren't given enough data to train one, so each cause gets its own rules instead.
- **Averages, not hard values.** Each tractor is compared with its own normal, the average of its calm dev minutes, instead of fixed cutoffs.
- **Space feeds are evidence, not the decider.** They only add signs for or against a cause, which set the confidence.
- **Every short dip is multipath.** A dip has to last at least 7 seconds, which keeps the file under the validator's 500-detection limit.

## What I learned

- **Real data is messier.** The rules fit this dataset, and real tractors would throw more at them.
- **Try bigger, more interesting approaches.** Running this on real-time data is where it would actually be useful in real life.
- **Visuals matter for business value.** The demo page shows what the pipeline found in a way people outside the code can follow.

## Setup

Requires Python 3.11+.

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python scripts/get_data.py          # downloads the dataset into data/
```

## Run

```bash
python run.py --window eval   # writes submission.json and validates it
python run.py --window dev    # writes dev_predictions.json and scores it against the 12 labels
```

## Tests

Plain Python, no pytest or data needed. Run each file under `tests/` by name:

```bash
python -m tests.test_score
```

## Demo

```bash
pip install -r requirements-demo.txt
python -m demo.serve          # http://localhost:8000 (run both windows first)
```

Built with help from Claude Code. No AI or network calls at runtime.
