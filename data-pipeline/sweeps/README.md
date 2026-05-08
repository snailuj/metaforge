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

## Available sweeps

- `baseline_v2.yaml` — S02-T03 baseline anchor (jaccard_salience /
  jaccard_raw / cosine_salience @ percentile 95 against the live V2
  lexicon).
- `sensitivity_v2.yaml` — S03 sensitivity demo: contrasts the baseline
  against degraded `threshold_percentile` variants (50, 99) and the
  `random_uniform` null-control scoring fn. See
  `SENSITIVITY-V2-FINDINGS.md` for the slice's verdict.

## How to run

> **Run from the repo root.** Paths in the YAML config (`db`, `pairs`,
> `controls`, `mrr_reference`) and the example paths below are resolved
> relative to the cwd of `run_sweep.py`.

### Prerequisites

YAML configs require PyYAML:

```sh
pip install pyyaml
```

JSON configs work out of the box.

### Run command

```sh
data-pipeline/.venv/bin/python data-pipeline/scripts/run_sweep.py \
  --config data-pipeline/sweeps/<name>.yaml \
  --output data-pipeline/output/sweep_<name>.json \
  --report data-pipeline/output/sweep_<name>.md
```

## Where artifacts go

`--output` JSON and `--report` markdown both land under
`data-pipeline/output/sweep_*` and are **gitignored** — they are
reproducible from the committed sweep config + DB snapshot. Only sweep
configs (this directory) are committed.

## Troubleshooting

- **A variation shows `status: failed` in the report.** Check the
  `error_type` and `error_message` fields in the per-row JSON or the
  Failures section of the markdown report. Common causes:
  - Typo in `scoring:` — compare against the registered names in
    `evaluate_aptness.SCORING_FNS`. Run
    `python data-pipeline/scripts/evaluate_aptness.py --help` to see
    them as the `--scoring` choices.
  - Missing or relative path for `db`, `pairs`, `controls`, or
    `mrr_reference` — paths resolve relative to cwd, so run from the
    repo root.
  - Malformed YAML config or malformed JSON in the `mrr_reference`
    artefact.
- **`run_sweep` exit codes.** Exit code `1` means some variations
  failed (partial failure); exit code `2` means every variation failed
  (catastrophic — usually a sweep-wide misconfiguration). Inspect the
  per-row error fields in the markdown report to localise the cause.
- **`ImportError: PyYAML required`.** Install per Prerequisites above,
  or convert the config to `.json`.
