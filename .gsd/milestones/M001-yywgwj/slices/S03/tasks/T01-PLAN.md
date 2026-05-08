---
estimated_steps: 8
estimated_files: 2
skills_used: []
---

# T01: Add random_uniform null-control scoring function and tests

Extend the SCORING_FNS registry in data-pipeline/scripts/evaluate_aptness.py with `random_uniform` — a deterministic pseudo-random scoring fn keyed on the sorted concatenation of cluster_ids in pa∪pb. By construction it carries no semantic signal: any apt/inapt structure in the V2 corpus must yield separation_score ≈ 0 under this scoring. This becomes the slice's null reference for sensitivity validation in T02.

The scoring fn must:
- Be deterministic — same (pa, pb) inputs yield the same float across runs (use hashlib.blake2b on the canonical-sorted cluster_id string, mapped to [0,1]).
- Be order-insensitive across pa/pb so that score(pa,pb) == score(pb,pa) (sort the union, don't concatenate side-by-side).
- Return a float in [0,1] consistent with the existing scoring contract.
- NOT use random.random() / numpy.random — those are non-deterministic across processes without explicit seeding and would silently break reproducibility.

Add unit tests covering: registry membership, determinism (same inputs → same output, twice), order symmetry (pa,pb == pb,pa), distinctness (two clearly different (pa,pb) pairs yield different scores with overwhelming probability), evaluate() dispatch via scoring='random_uniform', and CLI dispatch via --scoring random_uniform (monkeypatch sys.argv pattern from S02 tests). Maintain the PairScore status invariant: random_uniform with non-empty pa & pb returns status='scored' (never accidentally 'no_properties').

Assumption (documented inline): the determinism+order-symmetry properties are sufficient for a null reference; we are NOT proving uniformity statistically — that would require thousands of samples and is out of scope.

## Inputs

- ``data-pipeline/scripts/evaluate_aptness.py` — existing SCORING_FNS registry (jaccard_salience, jaccard_raw, cosine_salience) and the (pa, pb) -> float scoring contract this fn must conform to`
- ``data-pipeline/scripts/test_evaluate_aptness.py` — existing fixture and monkeypatch patterns to mirror (registry membership tests, evaluate() dispatch tests, CLI argv tests)`

## Expected Output

- ``data-pipeline/scripts/evaluate_aptness.py` — adds `random_uniform` entry to SCORING_FNS plus the implementing function; module docstring updated to list the new formula and call out its null-control intent`
- ``data-pipeline/scripts/test_evaluate_aptness.py` — adds tests for registry membership, determinism, order symmetry, distinctness, evaluate() dispatch, and CLI dispatch; full file remains green`

## Verification

source data-pipeline/.venv/bin/activate && python -m pytest data-pipeline/scripts/test_evaluate_aptness.py -v -k random_uniform && python -m pytest data-pipeline/scripts/test_evaluate_aptness.py data-pipeline/scripts/test_run_sweep.py -v

## Observability Impact

New scoring fn surfaces in run_sweep INFO logs identically to existing entries (scoring name, separation_score, aptness_rate, n_apt/n_inapt, duration_ms). No new failure modes — deterministic by construction. Argparse choices=sorted(SCORING_FNS) auto-includes the new entry, so a sweep config typo of 'random_uniform' still fails fast at CLI parse time.
