# Code Review Loop — M02 Asymmetric Ortony Scoring + S04 Retro

**PR:** [#18](https://github.com/snailuj/metaforge/pull/18)
**Branch:** `m02/asymmetric-ortony-scoring`
**Base:** `main` @ `7ae65ade`
**Started:** 2026-05-16T11:11:55Z
**Loop config:** reviewers = [pr-review-toolkit, superpowers, standards, ux-designer]; max_iterations = 15
**Logfile convention:** This file is the canonical handover artifact between rounds. Reviewers read it as context (no editorialising).

## Scope

`git diff main..HEAD` excluding raw data files (`*.json` enrichment outputs, `snap_dropped.jsonl`). Files in scope (43):

**Library / pipeline code:**
- `lib/claude_client.py` (5 reliability fixes: parser dict/list, timeout, fence-strip, prose-tolerant JSON extraction, raw-response diagnostic)
- `lib/test_claude_client.py`
- `data-pipeline/scripts/evaluate_aptness.py` (3 new asymmetric Ortony scoring fns in `SCORING_FNS` registry)
- `data-pipeline/scripts/test_evaluate_aptness.py` (+23 tests for the new variants)
- `data-pipeline/scripts/enrich_properties.py` (preflight check, `--skip-preflight` and `--skip-enriched-required` flags)
- `data-pipeline/scripts/test_enrich_properties.py`
- `data-pipeline/scripts/run_sweep.py`, `test_run_sweep.py`
- `data-pipeline/scripts/snap_properties.py`, `test_snap_properties.py`
- `data-pipeline/SCHEMA.sql`, `data-pipeline/CLAUDE.md`

**S04 retro scripts** (acknowledged ad-hoc; future formalisation captured in Backlog `Pipeline Tooling Consolidation`):
- `data-pipeline/scripts/m02_s04_a_attrition_audit.py`
- `data-pipeline/scripts/m02_s04_b_union_sizes.py`
- `data-pipeline/scripts/m02_s04_build_apt_gap_synsets.py`
- `data-pipeline/scripts/m02_s04_clear_and_import.py`
- `data-pipeline/scripts/m02_s04_compare_sonnet_vs_haiku.py`
- `data-pipeline/scripts/m02_s04_finalise_eval_rebuild.py`
- `data-pipeline/scripts/m02_s04_g_vocab_audit.py`
- `data-pipeline/scripts/m02_s04_import_only.py`
- `data-pipeline/scripts/m02_s04_patch_and_repipeline.py`
- `data-pipeline/scripts/m02_s04_prompt_audit.py`
- `data-pipeline/scripts/m02_s04_reenrich_emotion_cohort.py`
- `data-pipeline/scripts/m02_s04_test_sensorimotor_prompt.py` (contains `BATCH_PROMPT_V2_SM`)

**Configs:**
- `data-pipeline/sweeps/m02_ortony_v1.yaml`, `m02_ortony_v2.yaml`, `m02_ortony_v3.yaml`, `m02_s04_threshold_sensitivity.yaml`

**Docs:**
- `data-pipeline/sweeps/M02-S02-sweep-findings.md`
- `data-pipeline/sweeps/M02-S04-A-attrition-audit.md`
- `data-pipeline/sweeps/M02-S04-apt-gap-classification.md`
- `data-pipeline/sweeps/M02-S04-B-union-sizes.md`
- `data-pipeline/sweeps/M02-S04-CLOSING-findings.md`
- `data-pipeline/sweeps/M02-S04-C-threshold-sensitivity-design.md`
- `data-pipeline/sweeps/M02-S04-G-vocab-audit.md`
- `data-pipeline/sweeps/M02-S04-prompt-audit-emotion.md`
- `data-pipeline/sweeps/M02-S04-prompt-rename-multidomain.md`
- `data-pipeline/sweeps/M02-S04-prompt-rename-test.md`
- `data-pipeline/sweeps/M02-S04-sonnet-vs-haiku.md`
- `docs/roadmap/M02-ortony-scoring-roadmap.md`
- `docs/roadmap/PIPELINE.md`
- `.claude/skills/metaforge-pipeline-management/SKILL.md`
- `.gitignore`

**Out-of-scope (raw data):** 5 `enrichment_*.json` files, 4 `m02_s04_*_synset_ids.json` files, `snap_dropped.jsonl`. These are diagnostic / training data artifacts, not source code.

---

## Deferrals Ledger

### D1 — `m02_s04_test_sensorimotor_prompt.run_one` collapses 3 failure modes into single `None`
- **Source:** Round 1, silent-failure-hunter (item sf-6)
- **File:** `data-pipeline/scripts/m02_s04_test_sensorimotor_prompt.py:196-218`
- **Severity:** important
- **scope_boundary:** Ad-hoc retro script flagged in PIPELINE.md Backlog item `Pipeline Tooling Consolidation` for formalisation alongside other `m02_s04_*.py` one-offs.
- **why_out_of_scope:** Script is a one-shot A/B test that produced `M02-S04-prompt-rename-test.md` and `M02-S04-prompt-rename-multidomain.md` — both committed. Reworking failure-mode distinction would require restructuring caller in the same script, which is already superseded by the production-bound work (`BATCH_PROMPT_V2_SM` migration to `enrich_properties.py` is item 1a of Pipeline Tooling Consolidation).
- **proposed_followup:** Address as part of Pipeline Tooling Consolidation backfill 1a; when `BATCH_PROMPT_V2_SM` moves to production `enrich_properties.py`, the production error-handling pattern (structured exception types, `log.exception`) supersedes this retro script's contract.
- **status:** active

### D2 — `m02_s04_patch_and_repipeline.py` rollback discards original exception
- **Source:** Round 1, silent-failure-hunter (item sf-8)
- **File:** `data-pipeline/scripts/m02_s04_patch_and_repipeline.py:86-107`
- **Severity:** low
- **scope_boundary:** Same as D1 — ad-hoc retro script captured in Pipeline Tooling Consolidation.
- **why_out_of_scope:** One-shot retro flow that already executed against the production DB during M02-S04. The rollback path has not actually fired in practice (no operator report of OperationalError-on-rollback); the deeper pattern (transactional clear-and-import) is captured in Pipeline Tooling Consolidation backfill 1c (`--clear-existing` flag on production import path).
- **proposed_followup:** Subsumed by Pipeline Tooling Consolidation backfill 1c; the production `--clear-existing` flag should use Python's `raise ... from e` pattern correctly from the start.
- **status:** active

### D3 — `prompt_json` `expect: type` weak static contract
- **Source:** Round 1, type-design-analyzer (item td-2)
- **File:** `lib/claude_client.py:201-226`
- **Severity:** low
- **scope_boundary:** Runtime contract is correct (`isinstance` raises `ParseError` on type mismatch). Item is a static-typing refactor (Protocol/overload pair to narrow return type at call sites).
- **why_out_of_scope:** No active bug — every consumer that needs a list passes `expect=list` and the runtime check catches violations. Lifting to TypeVar overload is mechanical but invasive (all `prompt_json` call sites would re-narrow). Better landed alongside the next round of `lib/claude_client.py` type-tightening, when there's other typing work to ride along with.
- **proposed_followup:** Capture in `docs/inbox/captures.md` as a `lib/claude_client.py` typing refactor; pick up alongside any future typing-pass on the client.
- **status:** active

### D4 — `m02_s04_*` retro scripts duplicate `PairStatus` literal set
- **Source:** Round 1, type-design-analyzer (item td-3)
- **File:** `data-pipeline/scripts/m02_s04_a_attrition_audit.py:42-66` (and same pattern in sibling retro scripts)
- **Severity:** low
- **scope_boundary:** Ad-hoc retro scripts, Pipeline Tooling Consolidation territory.
- **why_out_of_scope:** Identical to D1's rationale — these scripts are explicitly flagged for archive/formalise/delete triage in PIPELINE.md Backlog. Importing `PairStatus` now would be polish on code that's queued for triage.
- **proposed_followup:** Pipeline Tooling Consolidation relevance-audit step (item 2 of backlog entry) — when scripts are triaged into archive/formalise/delete buckets, formalised ones get the import; archived ones don't matter; deleted ones are gone.
- **status:** active

### D5 — `SCHEMA.sql` foreign-key declarations are advisory only (no `PRAGMA foreign_keys = ON`)
- **Source:** Round 1, type-design-analyzer (item td-5)
- **File:** `data-pipeline/SCHEMA.sql` (whole file)
- **Severity:** low (would be important if it were a regression)
- **scope_boundary:** Pre-existing project-wide invariant gap. The M02 branch added new CHECK constraints (salience bounds, snap_method enum) and is adding `property_type` CHECK in this round's fixes — but did not introduce the FK-not-enforced behaviour.
- **why_out_of_scope:** Pre-existing, structural, requires either a project-wide `PRAGMA foreign_keys = ON` rollout (with migration to handle any rows that would violate FKs today) or an explicit "FKs are documentation only" decision. PIPELINE.md Backlog entry `Pipeline Architectural Review` question #1 ("Schema change management") explicitly covers this lifecycle question.
- **proposed_followup:** Pipeline Architectural Review's recommendation step should surface a concrete sub-milestone for FK enforcement OR a documented decision to keep FKs advisory.
- **status:** active

### D6 — `prompt_text`/`prompt_json`/`prompt_batch` `max_retries=0` foot-gun + `max_attempts` naming clarity
- **Source:** Round 1, superpowers (item sp-5)
- **File:** `lib/claude_client.py:191-227`
- **Severity:** low
- **scope_boundary:** Rename + semantic-clarity refactor across the public API of `lib/claude_client.py`. Touches every call site.
- **why_out_of_scope:** No caller passes `max_retries=0` today (verified by grep). The naming-clarity concern is real but a rename ripples through every test, every script, and the prod enrichment path. Better as a focused refactor PR than buried in M02 retro integration. Item #9 in this round's fix queue (`_invoke_with_retries` raises `None` when `max_retries <= 0`) covers the actual foot-gun via input validation — that's a one-line guard that lands here.
- **proposed_followup:** Capture in `docs/inbox/captures.md` as a `claude_client` API ergonomics tightening; bundle with future client-API work.
- **status:** active

### D7 — `run_sweep.py` default values duplicated across 3 sites (DRY smell)
- **Source:** Round 1, type-design-analyzer (item td-6)
- **File:** `data-pipeline/scripts/run_sweep.py:105-110, 344-345` + `evaluate_aptness.py:634, 725`
- **Severity:** cosmetic
- **scope_boundary:** DRY refactor across sweep config + evaluator + CLI.
- **why_out_of_scope:** Real DRY violation but no current bug. Three sites duplicate `95.0` as the threshold-percentile default — a future change has to touch all three. Cosmetic until someone actually changes the value.
- **proposed_followup:** Capture in `docs/inbox/captures.md` as a sweep-config consolidation; pick up alongside any future sweep-config work.
- **status:** active

### D8 — `_random_uniform` collision-safety claim not exercised under salience-changing inputs at fixed union
- **Source:** Round 1, superpowers (item sp-6)
- **File:** `data-pipeline/scripts/test_evaluate_aptness.py:830-840`
- **Severity:** cosmetic
- **scope_boundary:** Test addition to lock the str(int) join invariant the docstring documents.
- **why_out_of_scope:** Existing test (`test_random_uniform_ignores_salience_values`) covers the same-union/different-salience case. The docstring concern (different insertion order, same set) is mathematically guaranteed by Python's `sorted(union)` call — no actual collision risk. A regression test would be belt-and-braces on a null-control formula that's not load-bearing for any algorithmic claim.
- **proposed_followup:** Optional capture in `docs/inbox/captures.md` if there's future refactor pressure on `_random_uniform`.
- **status:** active

### D9 — Emoji glyphs in `m02_s04_a_attrition_audit.py` markdown output
- **Source:** Round 1, standards (item st-3)
- **File:** `data-pipeline/scripts/m02_s04_a_attrition_audit.py:178`
- **Severity:** cosmetic
- **scope_boundary:** Generator script that produced an already-committed markdown file.
- **why_out_of_scope:** Markdown output (`data-pipeline/sweeps/M02-S04-A-attrition-audit.md`) is committed and human-readable. No project-wide ASCII-marker convention exists; changing requires both source-script update and markdown regeneration. Cosmetic.
- **proposed_followup:** None — captured here for transparency. If a future M03 retro generator standardises markers, this can be updated then.
- **status:** active

---

## Round 1 — pr-review-toolkit (2026-05-16T11:11:55Z)

**Agents dispatched:** code-reviewer, silent-failure-hunter, type-design-analyzer (parallel)

### Items Found

**code-reviewer (2 items):**
- [critical] **`test_invoke_command_shape` stale and currently failing** (`lib/test_claude_client.py:220-233`) — Asserts old `timeout=120` and 9-element cmd list, but production code now emits `timeout=900` and 12 elements (`--strict-mcp-config`, `--mcp-config`, `_EMPTY_MCP`). Failing pytest output: `Left contains 3 more items, first extra item: '--strict-mcp-config'`. Violates CLAUDE.md "No merging with failing tests."
  - Decision: **fix**
  - Rationale: One-line test update; CI/CD standard violation; flagged by 4 of 5 reviewers.
- [important] **`enrich_properties.py` no `--db` CLI flag — preflight hardcoded to `LEXICON_V2`** (`enrich_properties.py:865-896`) — Every sibling script (`evaluate_aptness.py`, `snap_properties.py`, `run_sweep.py`) exposes `--db`. Preflight tests wrong DB silently if `run_enrichment` invoked programmatically with custom `db_path` while `main()` handles argv.
  - Decision: **fix**
  - Rationale: Silent footgun + CLI consistency; one-line plumbing.

**silent-failure-hunter (10 items):**
- [critical] **Duplicate of code-reviewer item 1** (test_invoke_command_shape) — merged.
- [important] **`_strip_fences` heuristic can silently succeed on wrong substring** (`lib/claude_client.py:60-77`) — Refusal-with-example scenario: `"I can't help. Example: [1,2,3]."` parses `[1,2,3]` as valid, downstream `extract_batch` logs `LLM returned unknown ID` at WARNING and silently drops batch.
  - Decision: **fix** (combined with sp-2 below — same code region, different angle)
- [important] **`EmptyResponseError` and non-zero exit lack raw-stdout context outside verbose mode** (`lib/claude_client.py:85-122, 128-160`) — Raw-response diagnostic only on `prompt_json` JSON-decode path. Other failure paths (empty stdout, top-level json.loads, no result event, missing result field) require `--verbose` to see what happened.
  - Decision: **fix**
  - Rationale: Mirror `prompt_json` head/tail pattern in `_parse_events`; standards: "Observability".
- [low] **`_invoke_with_retries` raises `None` when `max_retries <= 0`** (`lib/claude_client.py:163-186`) — Defensive input validation missing.
  - Decision: **fix** (combined with claude_client fix batch)
- [important] **`enrich_properties.run_enrichment` swallows exceptions with `print` only** (`enrich_properties.py:711-718`) — Broad-catch, no traceback, no `log.error`. Replace with `log.exception` + narrow except classes.
  - Decision: **fix**
- [important] **`m02_s04_test_sensorimotor_prompt.run_one` collapses 3 failure modes into `None`**
  - Decision: **defer-out-of-scope** → D1
- [important] **3 retro scripts silently skip JSONDecodeError without log** (`m02_s04_a_attrition_audit.py:124-127`, `m02_s04_b_union_sizes.py:94-97`, `m02_s04_g_vocab_audit.py:60-63`) — Compare to canonical pattern in `evaluate_aptness.load_inapt_controls`.
  - Decision: **fix** (low-cost 3-line pattern from sibling code; touches retro scripts but the data-corruption risk is real on the same MUNCH JSONL feed)
- [low] **`m02_s04_patch_and_repipeline.py` rollback discards original exception**
  - Decision: **defer-out-of-scope** → D2
- [low] **`evaluate_aptness._ortony_log_ratio` silent `continue` on non-positive salience** (`evaluate_aptness.py:296-303`) — Add `log.warning`.
  - Decision: **fix** (one log line)
- [low] **`enrich_properties` skip flags don't log when used** (`enrich_properties.py:836-856, 865-882`) — Add `log.warning` when `--skip-preflight` or `--skip-enriched-required` set.
  - Decision: **fix** (two log lines)

**type-design-analyzer (6 items):**
- [important] **`synset_properties.property_type` unbounded TEXT despite documented closed enum** (`SCHEMA.sql:189`) — Branch's sensorimotor work introduces a new enum member; schema has no CHECK to anchor it. Drift from prompt-time enum to DB-time enum is silent.
  - Decision: **fix**
  - Rationale: New invariant introduced by this branch's work; fits the standard set by the new salience/snap_method CHECK constraints.
- [low] **`prompt_json` `expect: type` weak static contract**
  - Decision: **defer-out-of-scope** → D3
- [low] **`m02_s04_*` retro scripts duplicate `PairStatus` literal**
  - Decision: **defer-out-of-scope** → D4
- [low] **`m02_s04_prompt_audit.enrichment_for_synset` is dead code with wrong column name** (`prompt_audit.py:107-133`) — `property_text` doesn't exist; canonical name is `text`. Function never called.
  - Decision: **fix** (delete dead code)
- [low] **`SCHEMA.sql` FKs never enforced (no `PRAGMA foreign_keys = ON`)**
  - Decision: **defer-out-of-scope** → D5
- [cosmetic] **`run_sweep.py` defaults duplicated across 3 sites**
  - Decision: **defer-out-of-scope** → D7

### Critique Sections (Persisted)

**code-reviewer:**
- PRIOR_FINDINGS_CRITIQUE: `prior_reviewer: "N/A — first round"`; `categories_checked: "N/A — first round, no prior findings to critique"`; `summary: "N/A — first round, no prior findings to critique"`
- APPLIED_FIXES_CRITIQUE: `fixes_reviewed: []`; `summary: "N/A — no fixes applied since last round (first round)"`
- DEFERRAL_LEDGER_REVIEW: `ledger_size: 0`; `summary: "ledger empty"`
- CLEAN: false

**silent-failure-hunter:**
- PRIOR_FINDINGS_CRITIQUE: `prior_reviewer: N/A — first round`; `categories_checked: "silent exception swallowing, broad except Exception, except: pass/continue without log, return-None-on-error masking distinct failures, subprocess return-code handling, conditional-on-verbose diagnostics, fallback-without-log, async/batch-degrades-silently, cleanup-paths succeeding-when-not-opened, default-arg edge cases (max_retries=0), heuristic parsers returning a wrong substring, test assertions out of sync with production code (a meta-silent failure)"`; `summary: First round; 10 findings raised.`
- APPLIED_FIXES_CRITIQUE: First round; no prior fixes. Re-checked the 5 claude_client reliability fixes mentioned in the scope statement against the source and test suite — see Pass 1 items 1, 2, 3 for the gaps each fix leaves behind.
- DEFERRAL_LEDGER_REVIEW: `ledger_size: 0`; `summary: "ledger empty"`
- CLEAN: false

**type-design-analyzer:**
- PRIOR_FINDINGS_CRITIQUE: `prior_reviewer: N/A — first round`; `categories_checked: "schema CHECK/FK/NOT NULL invariants; Python TypedDict/dataclass vs raw dict contracts; Literal vs raw string enums (PairStatus, snap_method, property_type, register, connotation); optional vs required fields with NotRequired and required-key validation; cross-module type sharing (PairStatus duplication in retro scripts); magic-string contracts (property_type, scoring registry keys, status returns); encapsulation (PairScore __post_init__ enforcement); dead-code shape mismatches (enrichment_for_synset); preflight return contract (None vs Result discriminated tuple); sweep config schema validation completeness."`; `summary: Type-design coverage on new code generally strong (PairScore __post_init__, frozen dataclasses, tagged-union via status discriminator, comprehensive sweep config validation). Weak spots are external to this branch's new code: property_type enum (item 1) and FK enforcement (item 5) are project-wide invariant gaps that this branch inherits; retro-script PairStatus duplication (item 3) is the only direct regression on new code, mitigated by the Pipeline Tooling Consolidation backlog item.`
- APPLIED_FIXES_CRITIQUE: `N/A — first round, no prior fixes to critique.`
- DEFERRAL_LEDGER_REVIEW: `ledger_size: 0`; `summary: "ledger empty"`
- CLEAN: false

### Files Modified
(none yet — round 1 reviewer pass, fixes pending)

### Test Results
(not yet run — applied after fix batch dispatch)

### Cumulative
Total rounds: 1 | Items resolved: 0 | Active deferrals: 9 | Superseded deferrals: 0 | Elapsed: ongoing

---

## Round 1 — superpowers (2026-05-16T11:11:55Z)

### Items Found
- [critical] **Duplicate of test_invoke_command_shape** — merged.
- [important] **Unfenced JSON extraction can mis-pick `{...}` substring when prose contains stray braces** (`lib/claude_client.py:60-77`) — `"Note: {placeholder} list: [1,2,3]"` produces start=object_start, close_char='}', rfind matches the `{placeholder}` brace not the real array. Loud-fails (not silent), but burns retries.
  - Decision: **fix** (combined with sf-2 — same code region; bracket-balance scan addresses both angles)
- [important] **`m02_s04_clear_and_import.py` commits DELETEs before curate/populate — half-deleted DB state on failure** (`m02_s04_clear_and_import.py:38-68`) — Sibling `patch_and_repipeline.py` wraps DELETEs in `BEGIN ... ROLLBACK` correctly; this script doesn't. Was run against production DB during rebuild.
  - Decision: **fix** (transactional wrap; mirror patch_and_repipeline pattern)
- [low] **`_strip_fences` regex hardcodes `json|markdown` language tags** (`lib/claude_client.py:50-52`) — Sonnet/Haiku occasionally emit `javascript` / `text` tags. Widen group to `[a-z]*`.
  - Decision: **fix** (one-line regex change; combined with claude_client fix batch)
- [low] **`prompt_text` etc. `max_retries=0` foot-gun + `max_attempts` naming**
  - Decision: **defer-out-of-scope** → D6 (D6 covers the rename + API surface; the actual foot-gun is fixed via input validation in sf-4)
- [cosmetic] **`_random_uniform` collision-safety claim not test-pinned**
  - Decision: **defer-out-of-scope** → D8

### Critique Sections (Persisted)
- PRIOR_FINDINGS_CRITIQUE: `prior_reviewer: N/A — first round`; `categories_checked: "algorithmic correctness, test-suite green, fail-loud reliability semantics, data-corruption risk, doc-vs-implementation consistency, edge cases (empty, zero-mass, asymmetric), bounded-range invariants, parser robustness to LLM prose drift"`; `summary: Verified Pass 1 covered all categories. Doc-vs-impl numbers from CLOSING-findings cross-checked against sweep_m02_ortony_v3_post_haiku_rebuild.json (random_uniform=0.006822 ✓, ortony_imbalance=-0.000492 ✓, n_apt=271/n_inapt=978 ✓).`
- APPLIED_FIXES_CRITIQUE: `First round; no applied fixes. All 68 commits are part of the initial submission.`
- DEFERRAL_LEDGER_REVIEW: `ledger_size: 0`; `summary: "ledger empty"`
- CLEAN: false

### Files Modified
(none yet)

### Test Results
(pending)

---

## Round 1 — standards (2026-05-16T11:11:55Z)

**Standards sources:** `/home/agent/.claude/CLAUDE.md` · `/home/agent/projects/metaforge/CLAUDE.md` · `/home/agent/projects/metaforge/data-pipeline/CLAUDE.md`

### Standards Checked
- TDD (Red/Green)
- Algorithms / OOM risk
- Frequent Commits
- CI/CD
- All Errors/Exceptions Handled
- Idempotency
- Observability
- Planning Before Code
- FP over OOP, DRY/YAGNI, Code-to-interface, Immutable state, Refactor Mercilessly, UK English, Comments-explain-intent

### Items Found
- [important] **CI/CD + Refactor Mercilessly — pre-existing failing `test_invoke_command_shape` left unrepaired** — DUPLICATE of code-reviewer/silent-failure-hunter/superpowers item 1, merged.
- [low] **All Errors/Exceptions Handled — silent JSONDecodeError continue in 3 retro audit scripts** — DUPLICATE of silent-failure-hunter sf-7, merged.
- [cosmetic] **Comments explain intent — emoji in markdown output text** (`m02_s04_a_attrition_audit.py:178`)
  - Decision: **defer-out-of-scope** → D9

### Per-Standard Verdict (Pass 1)
1. TDD: ✓ for new code (23 ortony tests, 4 _parse_events tests, 8 preflight tests, scoring-name boundary test). ✗ companion test left rotting (Item 1).
2. Algorithms: ✓ Ortony fns O(|pa|+|pb|), no OOM risk for synset-sized maps.
3. Frequent Commits: ✓ 68 atomic topical commits, coherent story.
4. CI/CD: ✗ See Item 1 — 1 failed / 611 passed.
5. All Errors/Exceptions Handled: ✗ 3 retro scripts (Item 2). ✓ Production paths log + escalate properly; the 5 claude_client fixes add structured exception types — exemplary.
6. Idempotency: ✓ DELETE+INSERT in clear_and_import idempotent; import_only uses INSERT OR IGNORE per data-pipeline CLAUDE.md.
7. Observability: ✓ Preflight logs control flow; ortony fns pure & tested; client diagnostic head/tail exposes failure mode; run_sweep adds `exc_info=True`.
8. Planning Before Code: ✓ M02 roadmap + S04 retro + CLOSING-findings + PIPELINE.md state changes all in order.
9. FP over OOP: ✓ Ortony fns pure; SCORING_FNS dict registry; PairScore/CohortResult frozen dataclasses.
10. DRY/YAGNI: ✓ No speculative abstraction in new code.
11. Code-to-interface: ✓ run_sweep + evaluate_aptness consume SCORING_FNS by name; new boundary check at config-load.
12. Immutable state: ✓ All new dataclasses frozen.
13. Refactor Mercilessly: ✗ Item 1 is the canonical example.
14. UK English: ✓ "Normalise", "behaviour", "optimise", "favouring" used consistently.
15. Comments explain intent: ✓ Multi-paragraph docstrings on ortony fns explain WHY (Ortony 1979, asymmetry rationale). `_strip_fences` records 2026-05-14 8k failure mode as WHY — exemplary. ✗ Item 3 (emoji in markdown output, cosmetic).

### Critique Sections (Persisted)
- PRIOR_FINDINGS_CRITIQUE: `prior_reviewer: N/A — first round`; `summary: First round — no prior reviewer to critique.`
- APPLIED_FIXES_CRITIQUE: `N/A — first round of M02 review; no fixes applied yet in this loop.`
- DEFERRAL_LEDGER_REVIEW: `ledger_size: 0`; `summary: "ledger empty"`
- CLEAN: false

### Files Modified
(none yet)

### Test Results
(pending)

---

## Round 1 — ux-designer (2026-05-16T11:11:55Z)

**Status:** No-op — PR contains zero UI-touching files (no `.html`, `.css`, `.jsx`, `.tsx`, `.vue`, `.svelte`, or files under `components/`, `pages/`, `views/`, `layouts/`, `templates/`, `styles/`).
**Counts as:** adapter-CLEAN for halt purposes (no dispatch, no four-section gate validation required).

---

## Round 1 — Triage Summary

**Merged & deduplicated:** 27 raw items → 22 distinct findings. The `test_invoke_command_shape` failure was independently raised by 4 of 5 reviewers (cr-1, sf-1, sp-1, st-1) — strong cross-validation.

**Fix queue (12 items, grouped by file):**
- `lib/claude_client.py`: bracket-balance scan + widen fence regex + EmptyResponseError head/tail + max_retries validation (4 items, 1 subagent)
- `lib/test_claude_client.py`: command-shape assertion update (1 item, 1 subagent)
- `data-pipeline/scripts/enrich_properties.py`: log.exception + `--db` flag + skip-flag warnings (3 items, 1 subagent)
- `data-pipeline/SCHEMA.sql`: property_type CHECK constraint (1 item, 1 subagent)
- `data-pipeline/scripts/m02_s04_clear_and_import.py`: transactional wrap (1 item — batch 2)
- `data-pipeline/scripts/evaluate_aptness.py`: ortony_log_ratio log.warning (1 item — batch 2)
- 3 retro audit scripts: JSONDecodeError logging (1 item across 3 files — batch 2)
- `data-pipeline/scripts/m02_s04_prompt_audit.py`: dead code deletion (1 item — batch 2)

**Defer queue:** 9 items → Deferrals Ledger D1–D9 above.


