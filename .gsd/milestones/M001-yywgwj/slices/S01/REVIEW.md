# S01 Code Review — V2 Foundation + Aptness Evaluator

**Branch:** `milestone/M001-yywgwj`
**Final HEAD:** `4f04815c` (after `c9f11785` for code; subsequent commits are doc-only)
**Loop start:** 2026-05-02T13:59:00Z
**Loop end:** 2026-05-02T15:45:00Z
**Reviewers (round-robin):** superpowers, pr-review-toolkit, ux-designer
**Outcome:** ALL CLEAN — halt condition met after 8 iterations

## Result

The slice is reviewed. All three reviewers returned **zero fixable items** in their most-recent consecutive passes:

| Reviewer | Last clean iteration | Notes |
|----------|---------------------|-------|
| ux-designer | iter 6 (no-op) | No user-facing surface changes — slice scope is data-pipeline only |
| superpowers:code-reviewer | iter 7 | Verified iter-5 fixes; no regressions |
| pr-review-toolkit (3 agents) | iter 8 | code-reviewer + silent-failure-hunter + type-design-analyzer all CLEAN |

## Summary

**Total iterations:** 8 (within `max_iterations: 15` cap).
**Items found:** 25 across all reviewers.
**Items fixed:** 12 (with TDD red/green where new behaviour was introduced).
**Items skipped:** 12 (with rationale logged in the iteration log; mostly pre-existing schema concerns out of slice scope, or stylistic preferences the reviewer themselves flagged as advisory).
**Already-covered:** 1 (regression test for `score=0.0 + status='scored'` was already present).

**Tests:** 436 passing (started at 431, added 4 new tests across iterations 1-2 and 1 in iteration 5). 0 failing.

## Fix Categories

| Category | Count | Examples |
|----------|-------|----------|
| Observability | 4 | cluster_vocab CLI logging; explode_apt blank-row tally; CSV path/line context; struct.error context |
| Error handling / fail-fast | 2 | JSONL malformed-line tolerance; DB existence guard before sqlite3.connect |
| Correctness (semantic) | 1 | `PairScore` tagged dataclass distinguishing no_properties from no-overlap (affects headline `separation_score`) |
| Type design / invariant enforcement | 3 | `__post_init__` invariant check; `CohortResult` frozen dataclass; PEP 604 union sweep |
| Schema invariants | 1 | `synset_concreteness.score` CHECK 1.0..5.0 |
| Test clarity | 1 | docstring fix for missing-inapt test |

## Notable Decisions

- **`PairScore` semantic distinction (iter 2, type-design-analyzer)** — Reviewer correctly flagged that returning `0.0` from `score_pair` for both "no shared clusters" and "synset has no curated properties" was a real correctness bug affecting the headline metric. Fixed via tagged `@dataclass(frozen=True) PairScore(status, score)`. Note: `data-pipeline/output/eval_baseline_v2.json` was computed under the old conflated scoring; a fresh baseline run would yield a higher `separation_score`. Regeneration is intentionally not part of this code-review fix — the user can re-run `evaluate_aptness.py` and `evaluate_mrr.py` to refresh the artifact.

- **Pre-existing schema items skipped** — `rarity DEFAULT 'unusual'`, `relations` PK, `vocab_clusters` FK, `property_antonyms` ordering — all flagged as legitimate technical debt but unchanged in this slice's diff. Adding them now would expand scope to a schema-wide migration touching importers and downstream consumers. Filed as out-of-scope for the slice review.

- **Tagged-union refactor for PairScore (iter 5)** — Reviewer self-flagged as "don't insist". Current frozen dataclass + `Literal` status is idiomatic Python; the bigger refactor adds friction without commensurate clarity. Skipped.

## Commit Trail (review fixes only, in order)

```
0aa9df4f  fix(cluster_vocab): configure logging in CLI main
8bcffde0  docs(test_evaluate_aptness): clarify missing-inapt test description
c94d6a7a  fix(evaluate_aptness): tolerate malformed JSONL in inapt controls
423be05a  feat(preprocess_munch): tally rows with blank human_ans
32a763dc  fix(cluster_vocab): log vid + blob length on struct.error
72329995  fix(preprocess_munch): include file path + line number on CSV failure
59b63995  fix(evaluate_aptness): fail fast on non-existent --db
55882e15  fix(evaluate_aptness): distinguish no-properties from no-overlap (PairScore)
9805ceca  fix(schema): bound synset_concreteness.score to Brysbaert 1.0-5.0
f1d9b7f0  fix(evaluate_aptness): enforce PairScore status/score invariant in __post_init__
5b6b192a  refactor(evaluate_aptness): replace _score_cohort 4-tuple with CohortResult
c9f11785  style(evaluate_aptness): use PEP 604 union syntax
```

## Iteration Log

Full per-iteration detail (items found, decisions, rationale, fixes, test results) is in:
`docs/superpowers/review-logs/2026-05-02-milestone-M001-yywgwj-review.md`

## Verdict

**Ready to ship.** All reviewers clean, all tests passing, atomic commits, documented decisions.
