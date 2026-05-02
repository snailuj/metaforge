# Code Review Loop — milestone/M001-yywgwj

**Started:** 2026-05-02T13:59:00Z
**Branch:** `milestone/M001-yywgwj`
**Slice scope:** S01 — V2 Foundation + Aptness Evaluator
**Reviewers (round-robin):** superpowers, pr-review-toolkit, ux-designer
**max_iterations:** 15
**Initial SHA:** 6d4ba6533721f5967b73be05a1635f1b067e4bec

## Scope

Source files changed vs `main` (excluding generated data, fixtures, summaries):

- `data-pipeline/SCHEMA.sql` (+14 lines)
- `data-pipeline/enrich.sh` (+21 lines)
- `data-pipeline/import_raw.sh` (+46 lines)
- `data-pipeline/scripts/cluster_vocab.py` (+32 lines)
- `data-pipeline/scripts/enrich_pipeline.py` (+53 lines)
- `data-pipeline/scripts/evaluate_aptness.py` (+397 lines, NEW)
- `data-pipeline/scripts/preprocess_munch.py` (+180 lines, NEW)
- `data-pipeline/scripts/test_evaluate_aptness.py` (+235 lines, NEW)
- `data-pipeline/scripts/test_preprocess_munch.py` (+129 lines, NEW)

User-facing surfaces touched: NONE (data pipeline only).

---

## Iteration 1 — superpowers (2026-05-02T14:05:00Z)

**Reviewer:** superpowers:code-reviewer (handover: empty — first iteration)
**Pre-fix SHA:** 6d4ba6533721f5967b73be05a1635f1b067e4bec

### Items Found
- [important] **cluster_vocab.py CLI silently drops new progress logs** (`data-pipeline/scripts/cluster_vocab.py:216-226`)
  - The new `log.info(...)` chunk-progress lines emit only when invoked via enrich_pipeline.py; standalone CLI use (the documented usage) drops them at the default WARNING root logger.
  - Decision: **fix**
  - Rationale: real observability regression; the logs were added to give operators chunk-by-chunk feedback. Same pattern as preprocess_munch.py / evaluate_aptness.py.
- [low] **test docstring/assertion mismatch in test_aggregate_metrics_handles_missing_inapt** (`data-pipeline/scripts/test_evaluate_aptness.py:187-192`)
  - Wording "defaults to mean_apt" implied a fallback that doesn't exist; behaviour is plain arithmetic.
  - Decision: **fix**
  - Rationale: cheap clarity win.
- [low] **lookup_primary_synset query won't use idx_lemmas_lemma index** (`data-pipeline/scripts/evaluate_aptness.py:58-72`)
  - `WHERE LOWER(lemma) = ?` forces full table scan per lookup.
  - Decision: **skip**
  - Rationale: reviewer themselves recommends "keep as-is for now". Offline eval script, no production impact. Adding a TODO comment violates project standard against speculative comments. If MRR wall-clock becomes a bottleneck in S02, revisit with a functional index.
- [low] **load_inapt_controls swallows malformed JSONL lines as crashes** (`data-pipeline/scripts/evaluate_aptness.py:138-147`)
  - Per-line `json.loads` aborts entire evaluation on any malformed line.
  - Decision: **fix**
  - Rationale: CLAUDE.md mandates "all errors handled — even recoverable ones must be logged". Defensive handling is cheap.
- [cosmetic] **explode_apt does not log how many rows had blank human_ans** (`data-pipeline/scripts/preprocess_munch.py:60-78`)
  - Silent skip → opaque ETL trace when MUNCH refreshes.
  - Decision: **fix**
  - Rationale: aligns with project observability standard. Implementation collapses generator to list (small dataset, ~10k rows) and returns `(records, skipped)`.
- [low] **enrich.sh argparse edge case — no JSON files supplied to --from-json** (`data-pipeline/enrich.sh:95-101`)
  - Empty `FROM_JSON_FILES` falls through to a generic error rather than a specific one.
  - Decision: **skip**
  - Rationale: reviewer admits "Quality-of-life only". Existing behaviour does error out with `--enrich or --from-json` is required` — adequate. Not worth additional code complexity for a contrived scenario (the user must explicitly type `--from-json` followed by another flag with no path).

### Fixes Applied
- **Configure logging in cluster_vocab.py CLI main** — added `--verbose/-v` flag + `logging.basicConfig` mirroring sibling scripts. (commit `0aa9df4f`)
- **Clarify test docstring** — replaced misleading "defaults to" wording. (commit `8bcffde0`)
- **Tolerate malformed JSONL in inapt controls** — TDD: failing `caplog` test → try/except `JSONDecodeError` with `log.warning(...)` naming file path and line number. (commit `c94d6a7a`)
- **Tally blank human_ans rows in explode_apt** — TDD: updated existing test + added new test → `explode_apt` now returns `(records, skipped)`; `preprocess` logs `"explode_apt: %d rows had blank human_ans"`. (commit `423be05a`)

### Test Results
431 passing, 0 failing (`python -m pytest data-pipeline/scripts/ -v`, 54.12s)

### Cumulative
Total iterations: 1 | Items found: 6 | Items fixed: 4 | Items skipped: 2 (with rationale) | Elapsed: ~10m
Status: NOT clean (fixes applied — re-review needed) → next: pr-review-toolkit

---

## Iteration 2 — pr-review-toolkit (2026-05-02T14:25:00Z)

**Agents dispatched (sequential):** code-reviewer, silent-failure-hunter, type-design-analyzer
**Pre-fix SHA:** 423be05aa6383230186241b5e0fe08ed138adca5
**Handover read:** iteration 1 superpowers log

### Items Found

**code-reviewer:** CLEAN.

**silent-failure-hunter:** 7 items.

- [important] **enrich.sh restore step doesn't surface sqlite3 failure** (`data-pipeline/enrich.sh:172-173`)
  - Decision: **skip**
  - Rationale: pre-existing code, NOT changed in this PR's diff (the diff only touches the Step 4 concreteness block at lines 253+). The restore step has been in production use under `set -euo pipefail`. Reviewer's concern about command substitution masking sqlite3 failures has theoretical merit but no observed bug. Filed as backlog: `git diff` shows this isn't adjacent to the slice's changes — addressing it would expand scope to general shell hardening across the import pipeline.
- [low] **enrich.sh HAS_BRYSBAERT command substitution swallows errors** (`data-pipeline/enrich.sh:262-263`, this IS in the diff)
  - Decision: **skip**
  - Rationale: under `set -euo pipefail`, a top-level assignment `var=$(failing_cmd)` does propagate non-zero exit. Adding extra error guards adds bash complexity for a marginal scenario (sqlite3 failing on a SELECT against `sqlite_master`). The existing `set -euo pipefail` pre-amble at the top of enrich.sh provides reasonable safety.
- [low] **enrich_pipeline.py validation re-reads JSON but final read is unguarded — TOCTOU** (`data-pipeline/scripts/enrich_pipeline.py:342-357`)
  - Decision: **skip**
  - Rationale: theoretical race (file replaced between validation and use during a seconds-long pipeline). Files are local, owned by the user running the pipeline. No realistic exploit / failure mode. Adding try/except wrapping every re-read adds noise without removing the underlying race.
- [low] **cluster_vocab.py silently ignores embedding-shape mismatches** (`data-pipeline/scripts/cluster_vocab.py:108-111`)
  - Decision: **fix**
  - Rationale: cheap log-and-re-raise improves debugging across 35k entries when one corrupt blob exists.
- [low] **enrich_pipeline.py store_lemma_embeddings INSERT OR REPLACE silently overwrites** (`data-pipeline/scripts/enrich_pipeline.py:301-304`)
  - Decision: **skip**
  - Rationale: lemma_embeddings is a derived cache from FastText vectors; overwriting on re-run is the desired idempotent behaviour. The CLAUDE.md "never INSERT OR REPLACE" warning is specifically about synset_properties FKs, not embeddings. Adding diff-tracking would inflate code without clear value.
- [low] **preprocess_munch.py CSV loaders have no error context on malformed rows** (`data-pipeline/scripts/preprocess_munch.py:46-57`)
  - Decision: **fix**
  - Rationale: matches iter-1 JSONL hardening pattern — cheap and consistent.
- [cosmetic] **evaluate_aptness.py main() has no try/except around sqlite3.connect** (`data-pipeline/scripts/evaluate_aptness.py:353`)
  - Decision: **fix**
  - Rationale: SQLite silently creates an empty DB on missing path; cheap Path.is_file() guard prevents the empty-result-after-typo footgun.

**type-design-analyzer:** 7 items.

- [important] **rarity DEFAULT 'unusual' masks NULL frequency data** (`data-pipeline/SCHEMA.sql:44-45`)
  - Decision: **skip**
  - Rationale: pre-existing schema. Diff only adds synset_concreteness table — does not modify frequencies. Changing this DEFAULT is a schema migration touching all importers and downstream consumers; out of scope for this slice's review. Filed as technical debt.
- [important] **relations table accepts duplicate (source, target, type) triples** (`data-pipeline/SCHEMA.sql:26-32`)
  - Decision: **skip**
  - Rationale: pre-existing schema, unchanged by this PR. Adding a PK now is a migration with downstream impact. Filed as technical debt.
- [important] **score_pair conflates unresolved-properties with zero-overlap** (`data-pipeline/scripts/evaluate_aptness.py:88-116`)
  - Decision: **fix**
  - Rationale: this IS in new code and IS a real correctness issue affecting the headline metric of S01 (separation_score). Pairs lacking curated properties currently flow into apt_scores at 0.0, deflating mean_apt. Fix: tagged `PairScore` dataclass + new `no_properties` counter excluded from cohort means.
- [low] **enrichment_data passed as untyped dict throughout pipeline** (`data-pipeline/scripts/enrich_pipeline.py:128-269`)
  - Decision: **skip**
  - Rationale: introducing TypedDicts across enrich_pipeline.py is a pre-emptive refactor of stable production code. Project standards prefer pragmatic gradual typing over comprehensive shapes. Should be a dedicated task with reviewer alignment, not a code-review-loop fix.
- [low] **vocab_clusters lacks FK and boolean CHECK constraints** (`data-pipeline/SCHEMA.sql:235-240`)
  - Decision: **skip**
  - Rationale: vocab_clusters is created/dropped by cluster_vocab.py inline (not from SCHEMA.sql) — adding FK to property_vocab_curated would require restructuring the inline DDL. Pre-existing pattern; not introduced in this slice. Filed as technical debt.
- [low] **property_antonyms permits asymmetric duplicates and self-pairs** (`data-pipeline/SCHEMA.sql:257-263`)
  - Decision: **skip**
  - Rationale: pre-existing schema. Adding CHECK requires migration and may break build_antonyms.py if it currently relies on either ordering. Filed as technical debt.
- [cosmetic] **synset_concreteness.score has no bounded CHECK** (`data-pipeline/SCHEMA.sql:278-283`)
  - Decision: **fix**
  - Rationale: this table IS new in this PR — adding the CHECK now (no migration) is the cheap moment to lock the 1.0-5.0 invariant.

### Fixes Applied

- **cluster_vocab struct.error context** — try/except logs vid + blob length, re-raises. (commit `32a763dc`)
- **preprocess_munch CSV path/line context** — TDD: 2 failing tests, then helper using csv.DictReader(strict=True) chaining file path + line_num via `raise from`. (commit `72329995`)
- **evaluate_aptness DB existence guard** — Path.is_file() check before sqlite3.connect raises FileNotFoundError. (commit `59b63995`)
- **evaluate_aptness PairScore tagged result** — TDD: 3 new tests, then frozen dataclass `PairScore(status, score)` with `scored | unresolved | no_properties`; `_score_cohort` tracks 4 counters; cohort mean only includes `scored`; aggregate adds `apt_no_properties` / `inapt_no_properties`; per-pair JSON carries status; CLI summary updated. Existing tests adjusted to new shape. (commit `55882e15`)
- **SCHEMA.sql concreteness bound** — `CHECK (score >= 1.0 AND score <= 5.0)` added to synset_concreteness.score. (commit `9805ceca`)

### Test Results
435 passing, 0 failing (`python -m pytest data-pipeline/scripts/ -v`, 58.78s)

### Cumulative
Total iterations: 2 | Items found total: 6 + 0 + 7 + 7 = 20 | Items fixed: 4 + 5 = 9 | Items skipped: 2 + 9 = 11 | Elapsed: ~30m
Status: NOT clean (fixes applied — re-review needed) → next: ux-designer

### Note on baseline JSON
(see end of iteration entry)

---

## Iteration 3 — ux-designer (2026-05-02T14:35:00Z)

**Carrier:** general-purpose subagent loaded with `ux-designer` skill
**Scope:** diff vs main on milestone/M001-yywgwj
**Status:** No-op — diff contains no user-facing surface changes.
**Rationale:** All changes are in `data-pipeline/` (Python scripts, SQL schema, JSONL fixtures, JSON eval outputs, shell scripts) and `.gsd/` planning artifacts. No changes to `web/` (frontend), no changes to `api/` HTTP response shapes, no end-user-facing CLI/copy/UI.
**Reviewer slot:** counts as CLEAN for round-robin / halt purposes.

### Cumulative
Total iterations: 3 | Items found cumulative: 20 | Items fixed: 9 | Items skipped: 11 | ux-designer no-ops: 1
Status: round-robin not yet complete in consecutive clean — superpowers and pr-review-toolkit must each return CLEAN after the iter-2 fixes before halt. → next: superpowers (round 2)

---

## Iteration 4 — superpowers (2026-05-02T14:45:00Z)

**Reviewer:** superpowers:code-reviewer
**Handover read:** iterations 1-3
**Re-review focus:** verify iter-2 fixes (especially `55882e15` PairScore refactor) introduced no regressions; surface any new heuristic findings.

### Items Found
None — verified PairScore dataclass cleanly encodes three statuses; `_score_cohort` returns four values correctly threaded into aggregate; `n_apt`/`n_inapt` now means "number of scored pairs" consistent with mean over scored pairs; tests cover no-properties exclusion explicitly; CSV `strict=True` is a behaviour improvement consistent with "all errors handled"; CHECK constraint is forward-looking-only safety guard; all other fixes are clean observability adds. All 435 tests pass.

```
CLEAN: true
```

### Cumulative
Total iterations: 4 | Items fixed: 9 | Items skipped: 11 | superpowers passes: 2 (1 not-clean, 1 clean) | pr-review-toolkit passes: 1 (not-clean) | ux-designer passes: 1 (no-op clean)
Status: superpowers CLEAN this round; pr-review-toolkit must also return CLEAN before halt. → next: pr-review-toolkit (round 2)

---

### Note on baseline JSON
`data-pipeline/output/eval_baseline_v2.json` was computed under the old conflated scoring. Fix #4 (`PairScore` distinction) means a fresh baseline run would yield a higher `separation_score` because no_properties pairs no longer drag down `mean_apt`. Regeneration is a separate user-facing eval run, intentionally NOT part of this code-review fix; the user can re-run `evaluate_aptness.py` and `evaluate_mrr.py` to refresh the artifact when they want the new baseline locked in.

---
