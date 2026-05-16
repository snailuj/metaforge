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

### D2 — `m02_s04_patch_and_repipeline.py` rollback-failure obscures original (corrected wording 2026-05-16, Round 2)
- **Source:** Round 1, silent-failure-hunter (item sf-8); wording corrected by Round 2 silent-failure-hunter (challenge accepted on rationale text — not on scope)
- **File:** `data-pipeline/scripts/m02_s04_patch_and_repipeline.py:86-107`
- **Severity:** low
- **scope_boundary:** Same as D1 — ad-hoc retro script captured in Pipeline Tooling Consolidation.
- **why_out_of_scope:** One-shot retro flow that already executed against the production DB during M02-S04. The rollback path has not actually fired in practice (no operator report of OperationalError-on-rollback); the deeper pattern (transactional clear-and-import) is captured in Pipeline Tooling Consolidation backfill 1c (`--clear-existing` flag on production import path).
- **Note on wording:** Round 1 framed this as "rollback discards original exception". Round 2 silent-failure-hunter correctly challenged: Python's `except: rollback; raise` uses bare `raise` which preserves the original exception via `__context__`. The actual residual concern is "if `rollback()` itself raises during exception handling, the rollback error's traceback obscures the original DELETE error" — not "original discarded". Severity unchanged (low — connection-died-during-rollback is rare); scope unchanged.
- **proposed_followup:** Subsumed by Pipeline Tooling Consolidation backfill 1c; the production `--clear-existing` flag should use Python's `raise ... from e` pattern correctly from the start (chain the rollback failure under the original DELETE error).
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
- `data-pipeline/SCHEMA.sql`: property_type CHECK constraint (1 item, 1 subagent) — **deferred mid-flight, see D10**
- `data-pipeline/scripts/m02_s04_clear_and_import.py`: transactional wrap (1 item — batch 2)
- `data-pipeline/scripts/evaluate_aptness.py`: ortony_log_ratio log.warning (1 item — batch 2)
- 3 retro audit scripts: JSONDecodeError logging (1 item across 3 files — batch 2)
- `data-pipeline/scripts/m02_s04_prompt_audit.py`: dead code deletion (1 item — batch 2)

**Defer queue:** 9 items → Deferrals Ledger D1–D9 above (D10 added mid-batch — see Round 1 Fixes Applied below).

### Round 1 Fixes Applied

**Batch 1 dispatched at SHA `b2198d06`; 4 subagents in parallel; 6 commits landed:**

| Commit | File(s) | Fix |
|---|---|---|
| `fe7cccc8` | `lib/test_claude_client.py` (subagent B; subagent A's strip_fences tests rolled in due to parallel-dispatch interference — see Note below) | Updated `test_invoke_command_shape` — cmd list now 12 args incl. `--strict-mcp-config` + `--mcp-config` + `_EMPTY_MCP`; `timeout=900`. Pre-existing failure closed. |
| `c5563cf6` | `data-pipeline/scripts/enrich_properties.py` + `test_enrich_properties.py` + `lib/claude_client.py` (subagent C; A's `_strip_fences` bracket-balance scan rolled in due to parallel-dispatch interference) | `log.exception` in batch loop, narrowed `except` to `ClaudeError` (recoverable). Programmer-error classes now propagate. Plus subagent A's `_strip_fences` bracket-balance + widened fence regex landed here. |
| `34dc061a` | `data-pipeline/scripts/enrich_properties.py` + tests | `--db` CLI flag (matches sibling scripts) — eliminates the preflight-tests-wrong-DB footgun. |
| `a7321060` | `lib/claude_client.py` + tests | `EmptyResponseError` + `_parse_events` failure paths now include stdout head/tail diagnostic; no longer requires `--verbose` to see the failure mode. |
| `914946c6` | `data-pipeline/scripts/enrich_properties.py` + tests | `log.warning` when `--skip-preflight` or `--skip-enriched-required` used (operator-visible audit trail of dangerous overrides). |
| `46499737` | `lib/claude_client.py` + tests | `_invoke_with_retries` validates `max_retries >= 1` to prevent `raise None → TypeError` foot-gun. |

**Batch 1 deferral mid-flight: D10 added.** Subagent D (SCHEMA.sql property_type CHECK) correctly halted per the fix-spec step-1 pre-check after `SELECT DISTINCT property_type` revealed unexpected values in the live DB:
- 188,206 empty-string rows (~46% of `synset_properties`)
- 120 rows `behavior` + 14 rows `behavioural` (US-spelling and adj-form drift)
- 4 rows hallucinated values (`spatial`, `temporal`, `structure`, `artistic`)

Adding the closed-enum CHECK would reject 188,344 existing rows. The empty-string mode is too dominant to dismiss as drift — possibly an import-path bug, possibly an LLM fallback for unclassifiable properties. Either way, investigating the root cause is out of M02 integration's scope; that's `Pipeline Architectural Review` territory.

**Batch 2 dispatched at SHA `46499737`; 4 subagents in parallel; 6 commits landed:**

| Commit | File(s) | Fix |
|---|---|---|
| `606227ba` | `data-pipeline/scripts/m02_s04_clear_and_import.py` | Transactional wrap of clear+import sequence. `delete_synset_rows` no longer commits internally; caller owns the boundary. Honest docstring note: downstream `enrich_pipeline.populate_*` functions commit internally too, so the wrapper provides "rollback on first-step failure" not full end-to-end atomicity — fuller refactor noted as future work. |
| `1150f340` | `data-pipeline/scripts/evaluate_aptness.py` + test | `log.warning` on `_ortony_log_ratio` non-positive-salience skip; cluster_id + pa[c] + pb[c] in diagnostic. New test `test_ortony_log_ratio_warns_on_non_positive_shared_cluster`. |
| `8a2c5b09` | `data-pipeline/scripts/m02_s04_a_attrition_audit.py` | `log.warning` on malformed JSONL skip — mirrors `evaluate_aptness.load_inapt_controls` canonical pattern. |
| `ac8dec96` | `data-pipeline/scripts/m02_s04_b_union_sizes.py` | Same pattern as above. |
| `c0510537` | `data-pipeline/scripts/m02_s04_g_vocab_audit.py` | Same pattern as above. |
| `097e5444` | `data-pipeline/scripts/m02_s04_prompt_audit.py` | Deleted unused `enrichment_for_synset` (29 lines) — referenced non-existent `property_text` column; would have crashed on use; no callers (grep-confirmed). |

### Note on Parallel-Dispatch Interference (Batch 1)

Subagents A (claude_client.py) and B (test_claude_client.py) ran in parallel. Subagent A wrote `_strip_fences` changes (Fix 1: bracket-balance + widened regex) to disk and presumably staged them between Fix 1 and Fix 2. Subagent B then committed `test_claude_client.py` and unexpectedly captured A's `lib/claude_client.py` changes that were staged. Subagent C similarly captured residual A staging in its first commit (`c5563cf6`).

**Net effect:** A's Fix 1 ("robust `_strip_fences` — bracket-balance scan + accept any fence language tag") landed as content across commits `fe7cccc8` (tests in test_claude_client.py) and `c5563cf6` (code in claude_client.py) rather than as its own commit. The diff content is correct; the commit messages drift from their diffs.

**Decision:** Leave the history as-is. The contents are correct (verified by `635 passed` test suite), and an interactive rebase to split commits would require force-push and history rewriting on a published branch for a cosmetic cleanup. Round 2 reviewers will see this note in handover and can call it out if it materially impedes review.

**Mitigation for batch 2:** the SCHEMA.sql blocker meant only 3 subagents touched code files (not 4 as planned), which reduced parallel-dispatch interleaving risk. Plus batch 2's files were all `data-pipeline/scripts/` with no overlap into `lib/`.

### Deferrals Ledger Update — D10 added

#### D10 — `synset_properties.property_type` CHECK constraint blocked on data-state investigation
- **Source:** Round 1, type-design-analyzer (item td-1); fix attempt halted by batch-1 subagent D per the fix-spec step-1 pre-check
- **File:** `data-pipeline/SCHEMA.sql` (around line 189)
- **Severity:** important (the invariant gap is real; the investigation is what's deferred)
- **scope_boundary:** Schema migration / data-quality investigation, not M02 integration scope. Investigating the 188K empty-string mode + 134 spelling drifts + 4 hallucinations belongs in `Pipeline Architectural Review` Q1 (Schema change management) and/or a dedicated data-cleanup milestone.
- **why_out_of_scope:** Adding the CHECK as specified would either:
  (a) reject 188,344 existing rows on fresh build (SCHEMA.sql diverges from live DB content)
  (b) codify the drift by widening the enum (wrong direction — defeats the purpose of the CHECK)
  (c) add an `'unknown'` sink (kicks the can; documents debt)
  Picking the right answer requires understanding *why* 46% of `property_type` is empty string. Possibilities: import-path writes `''` instead of `NULL` on missing field; LLM emits `""` for unclassifiable properties; schema-fix-up scripts wrote empties as placeholder. Without root-cause investigation, any choice bakes in something wrong.
- **proposed_followup:**
  1. Standalone investigation: trace the empty-string mode end-to-end (LLM output → JSON → import path). Sample 50 rows to see if there's a pattern (which synsets? which property texts?).
  2. Backfill or normalise based on findings.
  3. THEN add the CHECK in a dedicated schema migration (with table-recreation pattern since SQLite can't `ALTER TABLE ADD CHECK`).
- **status:** active

---

### Files Modified (Round 1, both batches)
- `lib/claude_client.py`
- `lib/test_claude_client.py`
- `data-pipeline/scripts/enrich_properties.py`
- `data-pipeline/scripts/test_enrich_properties.py`
- `data-pipeline/scripts/evaluate_aptness.py`
- `data-pipeline/scripts/test_evaluate_aptness.py`
- `data-pipeline/scripts/m02_s04_clear_and_import.py`
- `data-pipeline/scripts/m02_s04_a_attrition_audit.py`
- `data-pipeline/scripts/m02_s04_b_union_sizes.py`
- `data-pipeline/scripts/m02_s04_g_vocab_audit.py`
- `data-pipeline/scripts/m02_s04_prompt_audit.py`

(`data-pipeline/SCHEMA.sql` was inspected but **not modified** — deferred to D10.)

### Test Results
**Pre-round-1-fix:** 611 passed, 1 failed (`test_invoke_command_shape`) — the failure the round 1 critical finding called out.
**Post-batch-1:** 634 passed, 0 failed (test_invoke_command_shape fixed + new tests for fixes 1, 2, 3 in claude_client.py + new tests for enrich_properties fixes).
**Post-batch-2:** 635 passed, 0 failed (+1 for new `test_ortony_log_ratio_warns_on_non_positive_shared_cluster`).

Suite green. CI/CD standards violation (Round 1 Item 1) **resolved**.

### Cumulative
Total rounds: 1 (in progress)
Items resolved: 12 (all batch-1 + batch-2 fixes landed; deferred items moved to ledger)
Active deferrals: 10 (D1–D10)
Superseded deferrals: 0
Elapsed: ~1h fix-batch dispatch + suite run (batch 1 + batch 2 + test suite)

---

## Round 2 — pr-review-toolkit (2026-05-16T12:30:00Z)

**Agents dispatched:** code-reviewer, silent-failure-hunter, type-design-analyzer (parallel)

### Items Found (Round 2 — deduplicated across pr-review-toolkit + superpowers + standards)

**Cross-cutting:** Bracket-balance silent wrong-span pick was flagged by 3 reviewers (cr-1, sf-3, sp-1) — merged.

**code-reviewer (3 items):**
- [low] r2-cr-1 **Bracket-balance returns first-matching short JSON-valid prefix** — same as r2-sf-3/sp-1; merged.
- [cosmetic] r2-cr-2 **`_stdout_diagnostic` docstring incorrect for small-stdout branch** — claims byte-cap but dumps full repr.
- [cosmetic] r2-cr-3 **`prompt_json` inline head/tail duplicates `_stdout_diagnostic` (DRY drift)** — same as r2-sp-3.

**silent-failure-hunter (5 items):**
- [CRITICAL] r2-sf-1 **`subprocess.TimeoutExpired` regression from narrow `except ClaudeError`** — Round 1's narrowed except in `enrich_properties.run_enrichment` accidentally lets `subprocess.TimeoutExpired` escape per-batch isolation, abandoning checkpointing for all remaining batches. Real regression.
  - Decision: **fix** — wrap subprocess.run in `claude_client._invoke` to raise `ClaudeTimeoutError(ClaudeError)`.
- [important] r2-sf-2 **`prompt_json` + `prompt_batch` ParseError paths lack head/tail diagnostic** — 3 sibling sites at lines 317, 345, 347; same pattern as Round 1's `_parse_events` fix but anchor-incomplete.
  - Decision: **fix** — extend `_stdout_diagnostic` usage to upper layer.
- [important] r2-sf-3 **Bracket-balance picks wrong span on multi-block prose** — same as r2-cr-1; merged.
  - Decision: **fix** — add observability (log.debug on fallback, log.warning on suspiciously-short result).
- [low] r2-sf-4 **`_ortony_log_ratio` warning lacks pair identity** — cluster id alone insufficient diagnostic when fn called per-pair across thousands.
  - Decision: **fix** — include `pa.keys()`+`pb.keys()` profile in warning.
- [low] r2-sf-5 **`_strip_fences` never logs even when fallback path fires** — observability gap.
  - Decision: **fix** — combined with r2-sf-3 fix.
- D2 verdict: **challenge** on wording (not scope) — bare `raise` preserves original exception via `__context__`; rationale text amended in D2 above.

**type-design-analyzer (4 items):**
- [low] r2-td-1 **`EmptyResponseError` diagnostic untyped (magic-string contract)** — head/tail buried in args[0] f-string; downstream callers must regex-parse to get structured access.
  - Decision: **fix** — add typed `__init__` with `stdout_head`, `stdout_tail`, `total_len` fields.
- [cosmetic] r2-td-2 **`_strip_fences` bool-flag state machine vs Literal enum** — bool flags acceptable for tight private loop with extensive docstring; over-engineering to lift.
  - Decision: **defer-out-of-scope** → D11.
- [low] r2-td-3 **`delete_synset_rows` contract change not encoded in signature** — docstring-only "no longer commits" contract.
  - Decision: **fix** — rename to `_delete_synset_rows_within_txn` + precondition assert.
- [cosmetic] r2-td-4 **`run_enrichment(db_path: str = None)` typed lie** — should be `Optional[str]`.
  - Decision: **fix** — one-line annotation change.

**superpowers (3 items):**
- [low] r2-sp-1 = r2-cr-1 = r2-sf-3 — merged.
- [cosmetic] r2-sp-2 = r2-cr-2 — merged.
- [cosmetic] r2-sp-3 = r2-cr-3 — merged.

**standards: ✅ CLEAN.** All 12 round-1 fixes correctly close their target standards violations; all 15 standards re-checked individually; all 10 deferrals concurred with substantive scope-boundary rationale. No new findings. Single-adapter CLEAN, not round-CLEAN (other 4 adapters found items).

### Critique Sections (Persisted — verbatim summaries)

**code-reviewer:**
- PRIOR_FINDINGS_CRITIQUE: 8 categories checked across the 12 round-1 fixes; identified 3 gaps in own-previous-round findings (the first-block-wins variant of the bracket-balance hazard; the prompt_json DRY drift; the docstring inaccuracy).
- APPLIED_FIXES_CRITIQUE: 8 of 10 fixes correct; 2 partial (`a7321060` left DRY drift in prompt_json; `c5563cf6` introduced regression for TimeoutExpired noted by sf-1; bracket-balance scan introduces new first-block-wins false-positive).
- DEFERRAL_LEDGER_REVIEW: all 10 concurred.

**silent-failure-hunter:**
- PRIOR_FINDINGS_CRITIQUE: ≥11 categories checked; 3 substantive gaps in own prior-round findings (sf-1 regression — narrowing changed the silent-failure profile rather than closing it; sf-2 anchor-incomplete; sf-3 multi-block-prose wrong-span).
- APPLIED_FIXES_CRITIQUE: 7 correct, 5 partial, 1 dead-code-removal clean.
- DEFERRAL_LEDGER_REVIEW: 9 concur, 1 challenge (D2 wording — accepted).

**type-design-analyzer:**
- PRIOR_FINDINGS_CRITIQUE: 8 categories checked; 3 gaps in own prior-round (`EmptyResponseError` untyped; `delete_synset_rows` contract; `run_enrichment` Optional drift).
- APPLIED_FIXES_CRITIQUE: 8 clean, 4 partial (introduced or failed to lift structural-typing items), 1 doc-only.
- DEFERRAL_LEDGER_REVIEW: all 10 concurred.

**superpowers:**
- PRIOR_FINDINGS_CRITIQUE: 7 categories checked; 3 minor gaps (empty-container false-positive on bracket-balance; diagnostic-length asymmetry; unicode-escape state-machine comment).
- APPLIED_FIXES_CRITIQUE: 11 correct, 1 partial-by-design (transactional wrap with honest caveat).
- DEFERRAL_LEDGER_REVIEW: all 10 concurred (D10 specifically scrutinised — three-candidate-fix counterfactual analysis held up).

**standards:**
- PRIOR_FINDINGS_CRITIQUE: 15-standard re-check; no gaps; round 1's coverage was thorough; flagged 2 unflagged-but-non-violation observations.
- APPLIED_FIXES_CRITIQUE: all 12 fixes correctly close their target standards violations; no regressions; UK English consistent.
- DEFERRAL_LEDGER_REVIEW: all 10 concurred.
- **CLEAN: true** (adapter-CLEAN, not round-CLEAN).

### Round 2 Triage Summary

**Fix queue (10 items):**
- `lib/claude_client.py`: r2-sf-1 (CRITICAL), r2-sf-2 (important), r2-sf-3/cr-1/sp-1 (low, merged), r2-sf-5 (low), r2-td-1 (low), r2-cr-2/sp-2 (cosmetic), r2-cr-3/sp-3 (cosmetic) — 6 fixes, 1 subagent
- `enrich_properties.py`: r2-td-4 (cosmetic) — 1 fix, 1 subagent
- `evaluate_aptness.py`: r2-sf-4 (low) — 1 fix, 1 subagent
- `m02_s04_clear_and_import.py`: r2-td-3 (low) — 1 fix, 1 subagent

**Defer queue (1 new):** r2-td-2 → D11 (cosmetic, over-engineering).

### Round 2 Deferrals Ledger Update — D11 added

#### D11 — `_strip_fences` bool-flag state machine vs Literal/enum state
- **Source:** Round 2, type-design-analyzer (item r2-td-2)
- **File:** `lib/claude_client.py:95-105`
- **Severity:** cosmetic
- **scope_boundary:** Pure code-style refactor — lift implicit state (`in_string`, `escape` bool flags) into an explicit `Literal["struct","str","esc"]` state enum.
- **why_out_of_scope:** The bool-flag representation is acceptable for a 30-line private helper with extensive docstring + 12 new strip_fences tests pinning the invariants. Lifting to a state enum would be over-engineering for a tight loop; the *invariant* (depth count only advances outside string literals; escape state lives only inside strings) is correctly enforced — it's just not lifted into the type system. Cosmetic.
- **proposed_followup:** Capture in `docs/inbox/captures.md` if there's future refactor pressure on `_strip_fences` (e.g., needing to handle unicode escapes or new fence languages).
- **status:** active

### Round 2 Fixes Applied

Pre-fix SHA: `17083cc7` (Round 2 reviewers ran at this SHA).

**Batch 2-1 dispatched at `17083cc7`; 4 subagents in parallel; 9 commits landed:**

| Commit | File(s) | Fix |
|---|---|---|
| `1d8f2585` | `lib/claude_client.py` + tests | **CRITICAL fix**: wrap `subprocess.TimeoutExpired` as new `ClaudeTimeoutError(ClaudeError)`. Closes Round 2 sf-1 regression — retry/checkpoint logic now correctly catches subprocess timeouts via the existing `except ClaudeError` umbrella. |
| `ae6d4662` | `lib/claude_client.py` | Docstring correction: `_stdout_diagnostic` clarifies that short stdouts (≤head+tail) are dumped in full. |
| `33c6e46d` | `lib/claude_client.py` + tests | Typed fields on `EmptyResponseError` and `ParseError` — added `stdout_head`, `stdout_tail`, `total_len` attributes; threaded through all raise sites in `_parse_events` + `prompt_json` + `prompt_batch`. |
| `3cb044ff` | `lib/claude_client.py` + tests | Regression tests pinning head/tail behaviour on `prompt_json` + `prompt_batch` ParseError paths (locks Fix 2-4 contract). |
| `5f01f0c3` | `lib/claude_client.py` | DRY refactor: `prompt_json` + `prompt_batch` now call `_stdout_diagnostic` instead of inline head/tail logic. |
| `83097eee` | `lib/claude_client.py` + tests | `_strip_fences` observability: DEBUG on every unfenced extraction; WARNING when result list ≤3 items or empty dict (suspicious-mis-success signature). Threshold caveat documented in commit body. |
| `c34c733f` | `data-pipeline/scripts/enrich_properties.py` | `run_enrichment` annotation: `db_path: str = None` → `db_path: Optional[str] = None`. |
| `f52217e5` | `data-pipeline/scripts/evaluate_aptness.py` + tests | `_ortony_log_ratio` warning now includes `pa.keys()` + `pb.keys()` (Option A — preserve pure-function semantics; capped at 10 each to avoid log-line explosion). |
| `04bff62b` | `data-pipeline/scripts/m02_s04_clear_and_import.py` + `m02_s04_finalise_eval_rebuild.py` | Renamed `delete_synset_rows` → `_delete_synset_rows_within_txn` + `assert conn.in_transaction` precondition; updated cross-file caller in `m02_s04_finalise_eval_rebuild.py` to wrap Phase 1 in explicit BEGIN/COMMIT/ROLLBACK (bonus atomicity gain). |

### Files Modified (Round 2)
- `lib/claude_client.py`
- `lib/test_claude_client.py`
- `data-pipeline/scripts/enrich_properties.py`
- `data-pipeline/scripts/evaluate_aptness.py`
- `data-pipeline/scripts/test_evaluate_aptness.py`
- `data-pipeline/scripts/m02_s04_clear_and_import.py`
- `data-pipeline/scripts/m02_s04_finalise_eval_rebuild.py`

### Test Results
**Pre-round-2-fix:** 635 passed.
**Post-round-2-fix:** 644 passed, 0 failed (+9 tests for the new typed exception fields, ClaudeTimeoutError, observability, pair-identity, etc.).

CRITICAL regression (r2-sf-1) **resolved**.

### Cumulative
Total rounds: 2 (in progress)
Items resolved: 22 (12 in Round 1 + 10 in Round 2)
Active deferrals: 11 (D1–D11)
Superseded deferrals: 0
Standards adapter: CLEAN in Round 2.
Other adapters: not CLEAN (each found new items; all addressed except D11).

---

## Round 3 — pr-review-toolkit + superpowers + standards + type-design (2026-05-16T13:45:00Z)

**Reviewers dispatched:** code-reviewer, silent-failure-hunter, type-design-analyzer (pr-review-toolkit); superpowers:code-reviewer; standards (general-purpose); ux-designer no-op.

### Items Found (Round 3 — merged + deduplicated)

**important (3 items — all from Round 2 fix delta):**
- **r3-td-1: Multi-payload `_delete_synset_rows_within_txn` assert regression** (type-design-analyzer). `conn.execute("BEGIN")` runs once outside the loop; inner commits in `enrich_pipeline.populate_*` collapse the outer transaction; iteration-2 DELETE assert fails. Real regression from Round 2 fix `04bff62b`. Decision: **fix** — move BEGIN/COMMIT inside loop (per-payload atomicity).
- **r3-sp-1: ClaudeTimeoutError drops `exc.stdout`/`exc.stderr`** (superpowers). Round 2 `1d8f2585` wrapped TimeoutExpired but discarded the subprocess's partial output. Decision: **fix** — typed `stdout_head`/`stdout_tail`/`stderr_head`/`stderr_tail` fields.
- **r3-sp-2: Retry loop doesn't differentiate ClaudeTimeoutError — 75-min worst case** (superpowers). `max_retries=5 × 900s = 75 min` per stalled batch. Decision: **fix** — cap timeout retries at 1.

**low (5 items):**
- **r3-td-2: Suspiciously-short heuristic threshold not tuneable** (superpowers own-3). Decision: **fix** — lift to module constant.
- **r3-td-3: `delete_synset_rows_within_txn` precondition assert not unit-tested** (type-design own-5). Decision: **fix** — add test file with red/green for the assert.
- **r3-td-4: 5 remaining `T = None` typed-lies in `enrich_properties.py`** (type-design own-4). Decision: **fix** — apply `Optional[X]` to all 5 sites.
- **r3-sf-4: `_ortony_log_ratio` warning lacks total-size hint** (silent-failure-hunter own-5). Decision: **fix** — include `pa_n=N`, `pb_n=N`.
- **bracket-balance dict-side asymmetry** (silent-failure-hunter own-1): suspicious-short heuristic flags empty dicts but not small non-empty ones. Decision: **fix** — symmetric dict threshold.

**cosmetic (7 items):**
- Parsed-value content in WARNING (sf own-2) — **fix** (one-line log arg).
- DRY drift: prompt_json builds diagnostic twice (sf own-3) — **fix** combined with Mixin lift.
- Mixin lift for typed-field __init__ duplication (type-design own-2) — **fix** — `_StdoutDiagnosticMixin`.
- Dead `MonkeyPatch.context()` scaffold in test (sf own-6) — **fix**.
- ClaudeTimeoutError missing typed __init__ (type-design own-1) — **fix** combined with r3-sp-1.
- Typed fields mutable + serialisation round-trip (type-design own-3) — **defer** → D13.
- `conn.in_transaction` necessary-but-insufficient (type-design own-6) — **defer** → D12.
- `_strip_fences` worst-case O(N·K) opener density (superpowers own-4) — **defer** → D14.

**standards:** No new items at the per-standard level. Concurred with all 11 deferrals.

### Critique Sections Persisted (compact summary)

All four active adapters returned 4-section responses. Each adapter's PRIOR_FINDINGS_CRITIQUE substantively examined the previous round's findings; APPLIED_FIXES_CRITIQUE assessed all 10 Round 2 fix commits with per-fix yes/partial verdicts; DEFERRAL_LEDGER_REVIEW covered all 11 active deferrals individually. **No challenges raised this round (all 11 concurred).**

**Convergence verdict (per superpowers reviewer):** "Broadly converging — severity trend critical→critical→none for criticals, the round-3 importants are concentrated in the `1d8f2585` commit area rather than scattered, deferrals stable (no challenges). But not yet zero-finding."

### Deferrals Ledger Update — D12, D13, D14 added

#### D12 — `conn.in_transaction` precondition necessary-but-insufficient under sqlite3 implicit-BEGIN
- **Source:** Round 3, type-design-analyzer (own #6)
- **File:** `data-pipeline/scripts/m02_s04_clear_and_import.py:73-76`
- **Severity:** low
- **scope_boundary:** Requires either a `TransactionalConnection` Protocol wrapper that explicitly tracks "we BEGIN'd it" vs "the connection happens to be in implicit-DML-tx", or a coding convention that's hard to enforce mechanically.
- **why_out_of_scope:** Current call sites all use explicit `conn.execute("BEGIN")` immediately before the call — so the assert correctly catches the most common misuse ("forgot to BEGIN"). The implicit-BEGIN-from-prior-DML misuse is structurally rare. Lifting to a Protocol/wrapper is invasive across all sqlite3.Connection uses.
- **proposed_followup:** Pipeline Tooling Consolidation territory when the production `--clear-existing` flag (backfill item 1c) lands.
- **status:** active

#### D13 — Typed exception fields mutable post-construction (corrected wording 2026-05-16, Round 4)
- **Source:** Round 3, type-design-analyzer (own #3); wording corrected by Round 4 superpowers (challenge accepted on serialisation claim — not on scope)
- **File:** `lib/claude_client.py` `_StdoutDiagnosticMixin` (after R3 Mixin refactor)
- **Severity:** low
- **scope_boundary:** Mutability: nothing prevents `e.stdout_head = "fake"` after raise. Mitigation requires `__slots__` + maybe `__setattr__` override.
- **why_out_of_scope:** No code path in Metaforge currently writes to typed-field attributes after raise. Mitigation invasive (touches every raise site + adds slots machinery).
- **Note on wording correction:** Round 3 originally claimed two concerns: mutability AND serialisation-round-trip-broken. Round 4 superpowers reviewer empirically verified that typed fields DO round-trip via the default Exception `__reduce_ex__`/`__dict__` path despite the keyword-only `__init__` — the serialisation claim was technically wrong. D13 re-scoped to mutability only. The mutability concern stands.
- **proposed_followup:** Capture in `docs/inbox/captures.md` as an immutability-tightening item alongside any future `__slots__` work.
- **status:** active

#### D14 — `_strip_fences` worst-case O(N·K) on opener density
- **Source:** Round 3, superpowers (own #4)
- **File:** `lib/claude_client.py:137-179`
- **Severity:** low
- **scope_boundary:** Algorithmic complexity tightening — early-exit on the bracket-balance scan when start position passes the last balanced closer of a previously-tried opener, OR cap candidate_openers to first M (e.g. 20).
- **why_out_of_scope:** Bounded in practice: typical LLM responses are < 100 KB; K (opener count) scales with prose density but rarely > 50 for production batches. Tests against pathological inputs all complete in milliseconds.
- **proposed_followup:** If a future production incident traces back to `_strip_fences` CPU spend on adversarial LLM output, add the early-exit. Capture in `docs/inbox/captures.md`.
- **status:** active

### Round 3 Fixes Applied

Pre-fix SHA: `1d12a0f3`. 9 commits landed across 4 subagents (with parallel-staging interleaving on 2 of 9 — content correct, message attribution mixed):

| Commit | Fix |
|---|---|
| `350ae27a` | **r3-sp-1**: `ClaudeTimeoutError` typed `__init__` with timeout_seconds + cmd_prefix + stdout/stderr head/tail/len. `_invoke` reads `exc.stdout`/`exc.stderr` via `_decode_stream` helper. |
| `ed1b7eee` | **r3-sp-2**: `_MAX_TIMEOUT_ATTEMPTS=1`; retry loop caps timeout retries at 1. (Also bundled subagent D's `_ortony_log_ratio` pair_n size hint due to parallel staging.) |
| `b3e498c9` | **r3-td-2**: `_STRIP_FENCES_SUSPICIOUS_RESULT_THRESHOLD = 3` lifted to module constant. |
| `19b358b5` | **dict-side symmetry**: `_STRIP_FENCES_SUSPICIOUS_DICT_THRESHOLD = 2`; suspicious heuristic now flags small non-empty dicts. |
| `1ef8f875` | **sf-2**: WARNING log includes `parsed_value=%s` capped via `repr(parsed)[:200]`. |
| `f8d821d6` | **td-2 Mixin**: `_StdoutDiagnosticMixin` extracted; `EmptyResponseError(_StdoutDiagnosticMixin, ClaudeError)` and `ParseError(_StdoutDiagnosticMixin, ClaudeError)`. MRO verified. |
| `3f47e392` | **sf-6**: dead `pytest.MonkeyPatch.context()` scaffold removed. |
| `e8679702` | **td-5**: new `data-pipeline/scripts/test_m02_s04_clear_and_import.py` pins the precondition assert with 2 tests. |
| `10f43b6b` | **r3-td-4**: 5 sibling `T = None` typed-lies converted to `Optional[X] = None`. (Also bundled subagent B's **r3-td-1 multi-payload regression fix** — BEGIN/COMMIT moved inside `for path, data in payloads:` loop in `m02_s04_clear_and_import.py`, due to parallel staging.) |

### Note on Parallel-Dispatch Interference (Batch 3, recurrent)

Despite explicit `git add <file>` in every subagent prompt, parallel staging interleaving recurred. Root cause: `git commit` (no pathspec) commits *all* staged content; multiple subagents share the working directory + index. When subagent C's `git add data-pipeline/scripts/enrich_properties.py` ran while subagent B had already staged `data-pipeline/scripts/m02_s04_clear_and_import.py`, the subsequent commit captured both. Same pattern as Round 1.

**Mitigation for future batches:** prefer `git commit -- <pathspec>` (pathspec restricts commit to specified files even if index has more). Or single-file batches. Or per-subagent worktrees (heavy).

**Decision for Round 3:** Leave history as-is — content correct (verified by 653 tests passing); rewriting history on published branch trades cosmetic clarity for force-push risk. Round 4 reviewers see this note in handover.

### Files Modified (Round 3)
- `lib/claude_client.py`, `lib/test_claude_client.py`
- `data-pipeline/scripts/enrich_properties.py`
- `data-pipeline/scripts/evaluate_aptness.py`, `test_evaluate_aptness.py`
- `data-pipeline/scripts/m02_s04_clear_and_import.py`
- `data-pipeline/scripts/test_m02_s04_clear_and_import.py` (new)

### Test Results
**Pre-round-3-fix:** 644 passed.
**Post-round-3-fix:** 653 passed, 0 failed (+9 tests for ClaudeTimeoutError fields, retry-cap, dict-side suspicious threshold, parsed-value WARNING, mixin lift, precondition-assert pinning, pair_n assertion).

All 3 Round 3 **important** findings resolved:
- ✅ r3-td-1 multi-payload regression — per-payload BEGIN/COMMIT
- ✅ r3-sp-1 ClaudeTimeoutError diagnostic loss — typed fields capture stdout/stderr
- ✅ r3-sp-2 75-min retry burn — cap at 1 attempt

### Cumulative
Total rounds: 3 (in progress)
Items resolved: 31 (12 R1 + 10 R2 + 9 R3 distinct)
Active deferrals: 14 (D1–D14)
Superseded deferrals: 0
Trajectory: criticals R1+R2 → 0 critical R3; importants concentrated in same commit area each round; deferrals stable (zero challenges in R3).

---

## Round 4 — pr-review-toolkit + superpowers + standards (2026-05-16T15:00:00Z)

**Reviewers dispatched:** code-reviewer, silent-failure-hunter (pr-review-toolkit); superpowers:code-reviewer; standards (general-purpose); ux-designer no-op.

### Items Found (Round 4)

**important (1 item):**
- **r4-sf-3: Multi-payload rollback leaks deleted rows when failure lands after `curate_properties` internal commit** (silent-failure-hunter). The per-payload BEGIN/COMMIT fix from R3 (`10f43b6b`) correctly handles failures BEFORE any internal commit. But if `populate_synset_properties` raises AFTER `curate_properties` has committed internally, the rollback is a no-op — DELETEs + curate's writes are already committed. Module docstring acknowledges this honestly; production code doesn't log when the silent-leak case fires. Decision: **fix** — `log.warning` on the rollback-impossible branch.

**low (5 items):**
- **r4-sf-1: `assert` precondition stripped under `python -O`** — bare `assert conn.in_transaction` would be a no-op under optimisation flag, leaving DELETEs in autocommit. Decision: **fix** — replace with `if not ...: raise RuntimeError(...)`.
- **r4-sp-1/cr-1: `_MAX_TIMEOUT_ATTEMPTS=1` comment-math drift** — comment claims "2× the per-call timeout" but cap is actually 1×. Decision: **fix** — amend comment.
- **r4-sp-2: Dead-code path in timeout handler** — `if attempt < max_retries - 1: ... sleep` branch unreachable under cap=1. Latent foot-gun if cap bumped. Decision: **fix** — remove or guard.
- **r4-sp-5: Positive-path test doesn't exercise DELETE** — `test_delete_synset_rows_within_txn_accepts_explicit_transaction` passes `[]` which short-circuits before any DELETE runs. Decision: **fix** — strengthen test to seed rows + assert deletion.
- **r4-sp-3: Optional[X] pattern leaks to `evaluate_mrr.py:280`** — same pattern as r3-td-4 in a sibling file. Decision: **defer-out-of-scope** → out of M02 integration; capture in inbox.

**cosmetic (3 items):**
- **r4-sf-2: `_decode_stream` `errors="replace"` silently corrupts bytes** — substitutes `\ufffd` without log. Decision: **defer-out-of-scope** — bounded cost in failure-mode-only path; ClaudeTimeoutError already fail-loud.
- **r4-sp-4: Constants defined after their first use** — works at runtime but bad readability. Decision: **fix** — move constants to top.
- **r4-sp-6: `_MAX_TIMEOUT_ATTEMPTS` "attempts" vs "retries" vocabulary drift** — merged with comment fix.

**superpowers D13 challenge:** Empirically verified that typed exception fields DO round-trip via default Exception `__reduce_ex__`. The serialisation claim in D13 was technically wrong. **Action:** correct D13 wording to retain mutability concern only (done — see D13 above).

**standards: ✅ CLEAN.** 15-standard re-check holds against Round 3 fix delta. All 14 deferrals concurred. Suite green at 653 (verified locally).

### Critique Sections Persisted (compact)

All four active adapters returned 4-section responses with substantive PRIOR_FINDINGS_CRITIQUE (3+ categories per adapter, evidence-based), APPLIED_FIXES_CRITIQUE (per-fix yes/partial verdicts with evidence), DEFERRAL_LEDGER_REVIEW (all 14 deferrals individually addressed). Only 1 challenge raised: D13 serialisation rationale (corrected).

**Convergence verdict:** R1 (1 crit + 8 imp) → R2 (1 crit + 4 imp) → R3 (0 crit + 3 imp) → R4 (0 crit + 1 imp). Importants concentrated in same area each round (current round's are all rooted in Round 3 fix delta around timeout-cap and multi-payload). Severity monotone decreasing.

### Round 4 Fixes Applied

Pre-fix SHA: `2b656c51` (Round 4 reviewers ran here). 6 commits across 2 subagents — **no parallel-staging interference this batch** (used `git commit -- <pathspec>` discipline).

| Commit | File(s) | Fix |
|---|---|---|
| `d18340db` | `m02_s04_clear_and_import.py` + test | **r4-sf-1**: `assert` → `if not ...: raise RuntimeError(...)` for `-O` safety. Updated test from `pytest.raises(AssertionError)` to `RuntimeError`. |
| `4cf18669` | `lib/claude_client.py` | **r4-sp-1/cr-1 + r4-sp-6**: Corrected `_MAX_TIMEOUT_ATTEMPTS` comment math (cap = 1× per-call timeout, one attempt total, zero retries) + vocabulary clarification (attempts vs retries). |
| `6c25fa71` | `test_m02_s04_clear_and_import.py` | **r4-sp-5**: Strengthened positive-path test to actually exercise DELETE inside transaction — seeds 3 rows, deletes 2 via helper inside BEGIN, asserts deletion + control row survives + persistence after commit. |
| `5e628a9c` | `lib/claude_client.py` | **r4-sp-2**: Removed dead backoff branch in timeout handler (unreachable under `_MAX_TIMEOUT_ATTEMPTS=1`). Inline comment documents the latent foot-gun: if cap is bumped, re-added backoff must use `timeout_attempts` (not `attempt`). |
| `6119746f` | `lib/claude_client.py` | **r4-sp-4**: Moved `_RATE_LIMIT_INDICATORS`, `_STRIP_FENCES_*_THRESHOLD`, `_MAX_TIMEOUT_ATTEMPTS` into single `# Module configuration constants` block above first use. |
| `30dbb987` | `m02_s04_clear_and_import.py` + test | **r4-sf-3 fix**: `log.warning` on rollback-impossible-due-to-inner-commit. Factored per-payload body into `_import_one_payload` helper for testability. New test mocks inner commit + populate failure → asserts WARNING fires with payload path. |

### Files Modified (Round 4)
- `lib/claude_client.py`
- `data-pipeline/scripts/m02_s04_clear_and_import.py`
- `data-pipeline/scripts/test_m02_s04_clear_and_import.py`

### Test Results
**Pre-round-4-fix:** 653 passed.
**Post-round-4-fix:** 654 passed, 0 failed (+1 for strengthened positive-path test; other fixes update existing tests in-place).

All Round 4 important + low items resolved:
- ✅ r4-sf-3 multi-payload silent-leak — operator-visible WARNING
- ✅ r4-sf-1 `-O` strips assert — RuntimeError replacement
- ✅ r4-sp-1/cr-1 comment-math drift — corrected
- ✅ r4-sp-2 dead-code branch — removed
- ✅ r4-sp-5 shallow test — strengthened
- ✅ r4-sp-4 constants ordering — fixed
- D13 wording — corrected in ledger (mutability only; serialisation claim withdrawn)

### Deferred items (Round 4)
- **r4-sp-3** (Optional[X] leak to `evaluate_mrr.py:280`) — out of M02 integration scope; capture in `docs/inbox/captures.md`.
- **r4-sf-2** (`_decode_stream` errors=replace silently corrupts bytes) — bounded cost in failure-mode-only path; ClaudeTimeoutError already fail-loud.

These two are not promoted to ledger D-entries — they're inbox-captures, single-line follow-ups for future work.

### Cumulative
Total rounds: 4 (in progress)
Items resolved: 37 (12 R1 + 10 R2 + 9 R3 + 6 R4 distinct)
Active deferrals: 14 (D1–D14; D13 wording corrected R4)
Superseded deferrals: 0
Trajectory: criticals 0 since R3; importants 3 → 1 → expected 0 in R5; standards CLEAN R2-R4.

---



---

