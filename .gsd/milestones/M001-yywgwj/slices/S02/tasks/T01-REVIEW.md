# T01 Code Review — Pluggable scoring registry in evaluate_aptness

**Verdict:** APPROVE

**Scope:** Critical/high only — bugs, data loss, security, missing boundary error handling, broken contracts. Cosmetic/style deferred to slice-level review.

## Files reviewed

- `data-pipeline/scripts/evaluate_aptness.py` (commit d8433635)
- `data-pipeline/scripts/test_evaluate_aptness.py` (commit d8433635)

## Findings

None at critical or high severity.

## Notes considered and cleared

| Concern | Resolution |
| --- | --- |
| `_cosine_salience` norm computed over raw `pa.values()` not zero-padded vector | Mathematically equivalent — zeros contribute nothing to a sum-of-squares norm. No bug. |
| `score_pair` previously short-circuited `shared==∅` to `score=0.0`; new path delegates to `scoring_fn` | Behaviour preserved for `_jaccard_salience` (returns 0.0 on empty intersection) and explicitly verified by `test_score_pair_default_scoring_matches_jaccard_salience`. |
| PairScore status semantics under formula swap | `score_pair` resolves `unresolved`/`no_properties` *before* invoking `scoring_fn`; verified by `test_score_pair_status_unchanged_across_scoring_formulas`. |
| Unknown scoring names | Fail fast in two places: `evaluate()` raises `ValueError` listing known keys; CLI uses argparse `choices=sorted(SCORING_FNS)`. Both covered by tests. |
| Division-by-zero / NaN risk in cosine | Explicit `if na == 0.0 or nb == 0.0: return 0.0` guard; covered by `test_cosine_salience_zero_norm_returns_zero` (including empty-dict case). |
| Empty-input safety on direct registry use | All three formulas guard against empty intersections / empty inputs without crashing. |

## Verification

```
python -m pytest data-pipeline/scripts/test_evaluate_aptness.py -v
# 41 passed in 0.64s
```

All pre-existing tests still green; 20 new tests added by this task all pass.
