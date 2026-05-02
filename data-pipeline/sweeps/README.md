# Sweeps

Parameter sweep configs for the aptness evaluator harness
(`data-pipeline/scripts/run_sweep.py`).

## How to add a sweep

1. Create `<name>.yaml` (or `.json`) in this directory.
2. Define `name`, `db`, `pairs`, `controls`, optional `mrr_reference`,
   and a `variations[]` list — each variation needs at least `name`,
   `scoring` (key from `evaluate_aptness.SCORING_FNS`), and
   `threshold_percentile`.
3. See `baseline_v2.yaml` for the canonical shape.

## How to run

```sh
data-pipeline/.venv/bin/python data-pipeline/scripts/run_sweep.py \
  --config data-pipeline/sweeps/<name>.yaml \
  --output data-pipeline/output/sweep_<name>.json \
  --report data-pipeline/output/sweep_<name>.md
```

YAML configs require PyYAML (`pip install PyYAML`); JSON works out of
the box.

## Where artifacts go

`--output` JSON and `--report` markdown both land under
`data-pipeline/output/sweep_*` and are **gitignored** — they are
reproducible from the committed sweep config + DB snapshot. Only sweep
configs (this directory) are committed.
