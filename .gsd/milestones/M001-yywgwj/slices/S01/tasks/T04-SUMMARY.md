---
id: T04
parent: S01
milestone: M001-yywgwj
key_files:
  - data-pipeline/scripts/evaluate_aptness.py
  - data-pipeline/scripts/test_evaluate_aptness.py
  - data-pipeline/output/aptness_eval.json
key_decisions:
  - Salience-weighted Jaccard over shared curated cluster_ids — keeps T04 free of Go API dependency and produces deterministic, reproducible scores
  - p95 of inapt distribution as classification threshold — calibrated cutoff per the slice goal's MUNCH-calibrated thresholds requirement
  - Lemma resolution prefers property_vocab_curated (least-polysemous), falls back to lemmas table — covers MUNCH controls that don't have a curated entry
duration: 
verification_result: passed
completed_at: 2026-05-02T13:32:04.441Z
blocker_discovered: false
---

# T04: feat(eval): aptness evaluator scores 271 metaphor pairs vs 978 MUNCH inapt with separation_score=0.0103 (>0)

**feat(eval): aptness evaluator scores 271 metaphor pairs vs 978 MUNCH inapt with separation_score=0.0103 (>0)**

## What Happened

Built `data-pipeline/scripts/evaluate_aptness.py` — a discriminative aptness evaluator that scores (target, vehicle) pairs by salience-weighted Jaccard overlap on shared cluster_ids in `synset_properties_curated`. The score uses direct DB queries (no Go API server required, unlike `evaluate_mrr.py`), making it fast and deterministic for repeated baseline runs.

The evaluator resolves each lemma to its primary curated synset (least-polysemous, with a `lemmas` table fallback), computes weighted Jaccard `sum(min(s_a, s_b)) / sum(max(s_a, s_b))` over shared property clusters, then calibrates a classification threshold at the p95 of the MUNCH inapt control distribution.

Wrote `test_evaluate_aptness.py` first (TDD red), then implemented to green — 17 unit tests covering lookup, scoring, loaders, classification, aggregation, and the end-to-end JSON shape. Tests use an in-memory SQLite fixture mirroring the curated-vocab schema slice; no DB restore required to run them.

Real-data verification: 271/274 apt pairs and 978/1447 inapt controls resolve. mean_apt = 0.0231, mean_inapt = 0.0128, separation_score = 0.0103 — clears the T04 bar (>0.0). Note: separation falls short of the slice-level must-have (≥0.3) — that gap belongs to a future tuning task; T04 ships the evaluator framework and a positive baseline for downstream work.

Captured the scoring approach as architecture memory MEM022 so downstream sweep harnesses (S02) can reproduce the contract.

## Verification

Test suite: `.venv/bin/python -m pytest data-pipeline/scripts/test_evaluate_aptness.py -v` → 17/17 passed in 0.20s. Verification command from T04 plan: `python data-pipeline/scripts/evaluate_aptness.py --pairs data-pipeline/fixtures/metaphor_pairs_v2.json --controls data-pipeline/fixtures/munch_inapt.jsonl --output data-pipeline/output/aptness_eval.json` → exit 0, `separation_score = 0.0103` (>0 as required), structured JSON written to `data-pipeline/output/aptness_eval.json` (231KB) with keys `aptness_rate`, `separation_score`, `aggregate`, `per_pair_scores`, `config`.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `.venv/bin/python -m pytest data-pipeline/scripts/test_evaluate_aptness.py -v` | 0 | ✅ pass | 200ms |
| 2 | `.venv/bin/python data-pipeline/scripts/evaluate_aptness.py --pairs data-pipeline/fixtures/metaphor_pairs_v2.json --controls data-pipeline/fixtures/munch_inapt.jsonl --output data-pipeline/output/aptness_eval.json` | 0 | ✅ pass — separation_score=0.0103 | 4000ms |

## Deviations

None.

## Known Issues

"separation_score = 0.0103 satisfies T04's >0 bar but falls short of the slice-level must-have (≥0.3). T04 builds the framework and the positive-direction baseline; closing the slice-level gap is a downstream tuning concern (richer scoring signals: cross-property-type span, salience-weighted cosine, domain-distance gating) likely picked up in S02 sweep work."

## Files Created/Modified

- `data-pipeline/scripts/evaluate_aptness.py`
- `data-pipeline/scripts/test_evaluate_aptness.py`
- `data-pipeline/output/aptness_eval.json`
