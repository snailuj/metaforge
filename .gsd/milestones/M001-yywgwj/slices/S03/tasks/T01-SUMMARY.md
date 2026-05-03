---
id: T01
parent: S03
milestone: M001-yywgwj
key_files:
  - data-pipeline/scripts/evaluate_aptness.py
  - data-pipeline/scripts/test_evaluate_aptness.py
key_decisions:
  - Use hashlib.blake2b(digest_size=8) keyed on the sorted union of cluster_ids — deterministic, fast, order-symmetric. Rejected random.random()/numpy.random as non-deterministic across processes.
  - Score depends on union topology only (not on salience values) — makes the null-control property robust by construction rather than empirically.
  - Map the 64-bit digest into [0, 1) via n / (1 << 64). Strictly within the [0.0, 1.0] contract — no chance of returning 1.0 exactly.
duration: 
verification_result: passed
completed_at: 2026-05-03T00:08:07.245Z
blocker_discovered: false
---

# T01: feat(evaluate_aptness): add random_uniform null-control scoring fn and tests

**feat(evaluate_aptness): add random_uniform null-control scoring fn and tests**

## What Happened

Extended `data-pipeline/scripts/evaluate_aptness.py` SCORING_FNS registry with `random_uniform` — a deterministic pseudo-random null-control. The scoring fn hashes the sorted union of cluster_ids in pa∪pb via `hashlib.blake2b(digest_size=8)` and maps the 64-bit digest into [0, 1) by dividing by 2**64. By construction it carries no semantic signal: apt/inapt cohorts in V2 should yield separation_score ≈ 0, which is the property S03/T02 will exploit as a null reference in the sensitivity sweep.

Implementation choices made:
- `hashlib.blake2b` not `random.random()` / `numpy.random` — the latter are non-deterministic across processes without explicit seeding and would silently break reproducibility across sweep runs.
- Score depends only on the **union topology** (sorted set of cluster_ids in pa∪pb), not on order or salience values. This makes it order-symmetric (`score(pa,pb) == score(pb,pa)`) and salience-invariant by construction — the strongest possible "no semantic signal" property short of statistically proving uniformity (out of scope).
- Returns [0, 1) rather than [0, 1] (n / 2**64 < 1 always) — strictly inside the existing scoring contract `float in [0.0, 1.0]`.
- Empty union (defensive only — score_pair short-circuits to `no_properties` before reaching the scoring fn for empty inputs) returns 0.0.
- Argparse `choices=sorted(SCORING_FNS)` auto-includes the new entry, so a typo'd `--scoring random_uniforn` still fails fast at CLI parse time (verified by the existing `test_main_cli_rejects_unregistered_scoring`).

Module docstring updated to list `random_uniform` alongside the S02 trio with a brief note on its null-control intent.

Added 10 tests covering: registry membership, return-type/range, determinism (same inputs → same output twice), order symmetry, salience invariance (same cluster topology ⇒ same score regardless of weights), distinctness across three different cluster-id unions, score_pair status invariant for non-empty pa & pb, score_pair status invariant for the no-overlap-but-both-have-properties case (still 'scored' under random_uniform — distinct from jaccard's 0.0), evaluate() dispatch with `scoring='random_uniform'`, and CLI dispatch via `--scoring random_uniform` using the existing monkeypatch-sqlite3-connect pattern from S02.

The existing parametric `test_score_pair_status_unchanged_across_scoring_formulas` automatically picks up the new fn and verifies that 'unresolved' and 'no_properties' coverage statuses are preserved across all four scoring formulas.

Captured MEM038 (architecture) recording the new entry's intent for downstream T02 work.

## Verification

Ran the slice's verification command from S03-PLAN.md exactly as specified. The targeted `-k random_uniform` filter selected 10 tests, all passed. The full union of `test_evaluate_aptness.py` and `test_run_sweep.py` then ran 92 tests, all passed — confirming no regression in the S02 contract or the sweep harness.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `python -m pytest data-pipeline/scripts/test_evaluate_aptness.py -v -k random_uniform` | 0 | ✅ pass (10 selected, 10 passed, 43 deselected) | 660ms |
| 2 | `python -m pytest data-pipeline/scripts/test_evaluate_aptness.py data-pipeline/scripts/test_run_sweep.py -v` | 0 | ✅ pass (92 passed) | 1190ms |

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `data-pipeline/scripts/evaluate_aptness.py`
- `data-pipeline/scripts/test_evaluate_aptness.py`
