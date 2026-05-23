# M05 Type-Aligned Structural Matching — Review Loop

Branch: `m05/type-aligned`
Base: `main` (merge-base `4399abff`)
Adapters: pr-review-toolkit, superpowers, standards (ux-designer skipped — no UI changes)
Started: 2026-05-23

## Commits Under Review

```
9977c003 docs(m05): γ-sweep verdict — type-diversity confirmed, γ=0 default for now
25ab7aa9 feat(api,sweeps): M05 S04 prep — Gamma CLI/env + sweep runner γ-axis + Lakoff γ-grid
72426410 feat(forge): M05 S03 — type-diversity bonus in EvaluateCascadePair
46e261b3 feat(db): M05 S02 — load vocab_clusters.dominant_type into CascadeCache
7746783c feat(snap): M05 S01 — propagate property type into vocab_clusters.dominant_type
```

## Files In Scope

- api/cmd/metaforge/main.go
- api/internal/db/cascade_cache.go
- api/internal/db/cascade_cache_test.go
- api/internal/forge/cascade.go
- api/internal/forge/cascade_test.go
- api/internal/handler/cascade_pipeline.go
- api/internal/handler/handler_cascade_test.go
- data-pipeline/SCHEMA.sql
- data-pipeline/scripts/cluster_vocab.py
- data-pipeline/scripts/m04_sweep_runner.py
- data-pipeline/scripts/snap_properties.py
- data-pipeline/scripts/test_snap_properties.py
- data-pipeline/sweeps/m05_lakoff_gamma.yaml
- data-pipeline/sweeps/m05_lakoff_gamma_verdict.md
- docs/inbox/m05-brainstorming-notes.md

## Deferrals Ledger

(empty at round 1 start)

## Pre-existing known issues (informational, NOT deferred from this loop)

These were established at the M04 v1 merge point (commit 985ef696) and have separate deferral entries in earlier review logs:

1. `TestCascadeUnion_LatencyBudget` (api/internal/handler/handler_cascade_test.go:647) — load-sensitive environmental flake; identical 5.3s elapsed at HEAD and on main today (confirmed reproducible on main with M05 reverted). Not an M05 regression.
2. `TestCascadeUnion_ClassicalPairsSurface_AsCandidates` — times out under heavy load (TopK=10000); skipped via `-skip` flag in full-suite runs.

Reviewers should treat these as pre-existing if surfaced; they are not in this loop's deferral ledger.
