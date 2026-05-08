# Review Log — M01 Eval Harness + Snap Memory-Opt Refactor

**Branch:** `review/m01-and-snap-memopt`
**Started:** 2026-05-08
**Diff base:** `e93d0d6b` (parent of M01 merge — pre-M01 main HEAD)
**Diff head:** `e509b264` (post-M02-merge HEAD = review branch HEAD)
**Configured adapters:** pr-review-toolkit, superpowers, standards, ux-designer
**Mode:** diff mode (`e93d0d6b..e509b264`)
**Max iterations:** 15

## Scope

M01 milestone deliverable + the snap memory-opt refactor that landed alongside M02. M01 had S03-only review previously (clean across 3 reviewers in iter5/6/7); this is the holistic pass covering S01 + S02 + the `perf(snap)` cursor-streaming refactor.

### In-scope code files

```
data-pipeline/SCHEMA.sql
data-pipeline/enrich.sh
data-pipeline/import_raw.sh
data-pipeline/scripts/cluster_vocab.py
data-pipeline/scripts/enrich_pipeline.py
data-pipeline/scripts/evaluate_aptness.py
data-pipeline/scripts/preprocess_munch.py
data-pipeline/scripts/run_sweep.py
data-pipeline/scripts/snap_properties.py
data-pipeline/scripts/test_evaluate_aptness.py
data-pipeline/scripts/test_preprocess_munch.py
data-pipeline/scripts/test_run_sweep.py
data-pipeline/scripts/test_snap_properties.py
data-pipeline/sweeps/baseline_v2.yaml
data-pipeline/sweeps/sensitivity_v2.yaml
```

(86 files total in diff; the rest are docs / fixture JSON / sweep result snapshots — out of code-review scope but reviewable as supporting artefacts.)

### Pre-existing failures to ignore

- 8 tests in `api/internal/handler/handler_test.go` failing due to absent test fixture DB. Confirmed pre-existing at the pre-M01 main HEAD. Not introduced by this work.

### Methodology caveats

- ux-designer is expected to be a no-op (backend / data-pipeline only — no UI changes).
- Python suite baseline on this branch: **512 passed, 1 skipped** (run 2026-05-08).

## Deferrals Ledger

*(empty)*

## Round Log

