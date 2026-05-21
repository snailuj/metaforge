# Code Review Loop — M03 Cascade Gate-and-Rank

**Branch:** `m03/cascade-gate-and-rank`
**Base:** `main` @ `8cb94cf6` (post PR #18 merge)
**Started:** 2026-05-20T23:42:00Z
**Loop config:** reviewers = [pr-review-toolkit, superpowers, standards, ux-designer]; max_iterations = 15

## Scope

12 M03 commits on top of main; pre-PR review. 16 files: 3 new prod Python + 2 new test Python + 3 modified Python + 2 YAML configs + 5 docs. ~3300 lines added.

**UX scope:** zero UI files (pure backend Python + YAML + Markdown). ux-designer adapter is a no-op for the loop.

**Baseline:** 708/708 passing at commit `374fda4b`.

## Deferrals Ledger

*(deferrals from round 1 are appended below — see "Round 1 — Deferrals")*

---

## Round 1 — pr-review-toolkit (2026-05-21T00:15:00Z)

**Agents dispatched:** code-reviewer (CLEAN), silent-failure-hunter (6 items), type-design-analyzer (15 items)

### Items Found (deduplicated against superpowers + standards in merge step)

**Important:**
- SF-2 `_centroid` swallows broad `sqlite3.OperationalError` without log (`evaluate_cascade.py:127-135`) — silent-failure rule violation, also flagged by standards. **DECISION: fix.**
- SF-3 `evaluate_cohort` silent on empty cohorts — `aptness_rate=0.0 / separation=0.0` reported on `status=ok` (`evaluate_cascade.py:415-430`). **DECISION: fix.**
- SF-1 Re-rank fail-open path has no attrition counter — 81-82% of pairs go through this branch silently (`evaluate_cascade.py:253-282`). The 3948dedf-class regression risk. **DECISION: fix.**
- TD-1 `CascadeResult` permits internally contradictory field combinations (`evaluate_cascade.py:80-98`). **DECISION: defer.** scope_boundary: invasive dataclass restructure / factory methods. why_out_of_scope: `__post_init__` cross-field assertion is the smallest fix but Subagent 1's freezing already prevents *post-construction* drift; the contradictory-combination footgun at construction time has not bitten in this milestone (5 callers, all consistent). Defer to S05 type-design polish PR.
- TD-2 Cosine pair-dim mismatch silently truncates via `zip()` (`evaluate_cascade.py:143-152`). **DECISION: fix.**
- TD-3 m03_diagnostics `_cosine_distance` returns NaN vs cascade returns None — sibling drift (`m03_diagnostics.py:184-191`). **DECISION: fix (harmonise).**
- TD-5 `VariationSpec` silently ignores `scoring` under `evaluator: cascade` (`run_sweep.py:125-136, 418-421`). **DECISION: fix (validator).**
- TD-6 `OkVariationResult total=False` defeats narrowing on universal fields (`run_sweep.py:60-99`). **DECISION: defer.** scope_boundary: invasive TypedDict refactor (split into discriminated union). why_out_of_scope: structurally cleaner long-term shape, but the runtime invariants are already protected by `_run_one_variation`; refactor is best paired with the S05 forge integration where the consumer side gains real benefit from narrowing. Two cleaner shapes documented in original finding for the future PR.
- TD-8 `CascadeConfig` has no construction-time invariant validation (`evaluate_cascade.py:61-77`). **DECISION: fix (`__post_init__`).**

**Low (cheap to fix in-loop):**
- TD-4 `CascadeStatus.unresolved` produced only by cohort orchestrator, not pair fn. **DECISION: fix (docstring).**
- SF-6 Per-pair detail rows don't record concreteness/delta (`evaluate_cascade.py:349-361`). **DECISION: defer.** scope_boundary: ops-debug observability feature; not blocking S05. why_out_of_scope: schema extension touches the per-pair JSON contract that an operator-side notebook would consume; better landed alongside the operator-tooling work scheduled in the Pipeline Tooling Consolidation backlog.
- TD-7 `OkVariationResult` lists 8 attrition fields but omits `apt_scored`/`inapt_scored` (`run_sweep.py:92-99`). **DECISION: defer.** scope_boundary: cohort-attrition observability completeness. why_out_of_scope: `apt_scored = n_apt - apt_gate_dropped` is recoverable from existing fields; surfacing the raw counter is nice-to-have but the rerank-attrition fix (Subagent 4 fix 3) already broke the same TypedDict — adding two more fields here is duplicative churn without a forcing consumer.
- TD-9 `_re_rank_bonus(d, d_cap=0.0)` silent. **DECISION: fix (validator + `__post_init__`).**
- TD-10 `alpha` unconstrained — negative alpha inverts re-rank silently. **DECISION: fix (validator + `__post_init__`).**
- TD-11 `_centroid` swallows malformed blobs (`len % 4 != 0`). **DECISION: fix (length validation).**
- TD-13 `build_synset_centroids` docstring claims Go API requires the table — verified inaccurate. **DECISION: fix (correct docstring).**
- SF-4 `build_synset_centroids` silently skips all-malformed-embedding synsets. **DECISION: fix (counter + log).**

**Cosmetic / refactor:**
- TD-12 Defensive `row[0] is None` against schema-NOT NULL. **DECISION: defer.** scope_boundary: belt-and-braces cleanup; semantically harmless. why_out_of_scope: low-yield change, would obscure the per-cell read pattern with no operator benefit. Captures `defer` here to demonstrate the principle (the standards reviewer might re-raise; if so, fix in round 2).
- TD-14 Sibling `_concreteness` divergent return types. **DECISION: defer.** scope_boundary: refactor-to-shared-helper. why_out_of_scope: extraction belongs with the type-design follow-up PR alongside TD-1, TD-6.
- TD-15 `_summarise` dict shape diverges for n=0/n=1/n>=2. **DECISION: defer.** scope_boundary: m03_diagnostics is a one-shot pre-flight script (~400 lines, no tests, no callers). why_out_of_scope: the script ran successfully and produced the JSON used by S01-findings; reshaping its output dict has no consumer. Will revisit if M04 needs to re-run the diagnostic.

### Critique Sections (verbatim per reviewer)

**pr-review-toolkit:code-reviewer** — CLEAN: true. Read all 12 files end-to-end + ran data-pipeline targeted tests (633/633 pass). Categories checked: bugs/correctness, CLAUDE.md adherence (TDD/error-handling/observability/idempotency/FP-pragmatic/UK-English), project conventions, data-shape & DB contract, edge cases, sweep-config validation surface, pipeline-regression risk, doc/code consistency. Notes sub-threshold items (CascadeStatus.unresolved provenance, print vs log inconsistency in run_pipeline centroid step, no test pinning "additive rescues ortony==0" mechanism) — these surface in peer reviewers' findings.

**pr-review-toolkit:silent-failure-hunter** — CLEAN: false. 6 findings. Categories: try/except blocks (4 located, all reviewed), silent fallbacks (cascade re-rank fail-open path, _centroid table-absent, classify_aptness empty-cohort, _percentile empty-list), Optional-returning hot paths, empty/degenerate input handling, observability gaps, parallel-code drift, the 3948dedf-class bug. Headline finding: SF-1 (rerank attrition counter) — same class as the centroid regression.

**pr-review-toolkit:type-design-analyzer** — CLEAN: false. 15 findings. Categories: invariants, encapsulation, schema correctness, invalid-state-representability, dataclass design, Optional vs Required, enum/Literal use, type-safety at runtime boundaries. Top 3 by ROI per reviewer: TD-1 (CascadeResult impossible states), TD-2 (cosine dim mismatch), TD-5 (sweep silently ignores `scoring`).

DEFERRAL_LEDGER_REVIEW: ledger empty for round 1.

## Round 1 — superpowers (2026-05-21T00:15:00Z)

**Agent:** `superpowers:code-reviewer` — CLEAN: false. 8 findings.

### Items Found (overlap with pr-review-toolkit shown; net-new in **bold**)

- SP-1 Cascade imports `_get_properties`/`_percentile` (underscore-private) from evaluate_aptness — pre-existing tech debt. **DECISION: skip.** Pre-existing pattern across 6 other scripts; not introduced by M03.
- SP-2 `_centroid` BLOB decoder crashes on length-not-divisible-by-4 — same root as TD-11. **DECISION: fix (merged).**
- SP-3 `_re_rank_bonus(d_cap=0.0)` silent — same as TD-9. **DECISION: fix (merged).**
- **SP-4** Centroid + Ortony read from different tables — asymmetry undocumented. **DECISION: fix (docstring).**
- **SP-5** TDD ordering not visible in commit history — tests + code shipped in single `feat` commits. **DECISION: skip.** Process improvement; cannot retroactively fix. Recorded for milestone retro.
- **SP-6** Scoring policy (gate-dropped pairs contribute 0 to cohort mean) buried in inline comment. **DECISION: fix (promote to module docstring).**
- **SP-7** `evaluate_cohort` per-pair dicts use untyped string keys — no TypedDict. **DECISION: defer.** scope_boundary: cosmetic typing extension to the per-pair row format. why_out_of_scope: M02 introduced typed `PairScore`; M03 didn't extend the pattern. Defer to the type-design follow-up PR alongside TD-1, TD-6, TD-14.
- **SP-8** Stale-row pruning documented but not implemented in `build_synset_centroids`. **DECISION: fix.**

### Critique Sections (verbatim)

Verified 4 statistical claims against sweep JSON + live DB: Stage-2 separation +0.1779 ✓, M02 plateau −0.0407 ✓ (sanity check to 6 dp), curated × centroid 99.345% ✓, 20× null-reference ratio ✓. Composition correctness confirmed (`multiplicative: ortony × (1 + α × bonus)`, `additive: ortony + α × bonus`). Test-to-code ratio 1.6× for both new modules; tests assert behaviours not lines. Idempotency contract tested for happy paths; unhappy paths (mid-`executemany` crash, stale-row pruning) untested. Cohort attrition counters expose mechanism honestly. Sweep configs `v1.yaml`/`v2_stage2.yaml` are near-duplicate by methodological necessity. `m03_diagnostics.py` is uncovered by tests (acceptable for a one-shot pre-flight tool).

## Round 1 — standards (2026-05-21T00:15:00Z)

**Standards sources:** `~/.claude/CLAUDE.md` · `/home/agent/projects/metaforge/CLAUDE.md` · `/home/agent/projects/metaforge/data-pipeline/CLAUDE.md`

**Agent:** `general-purpose` with standards-checking instructions — CLEAN: false. 6 findings.

### Standards Checked

- TDD (Red/Green) — STD-5 below
- Algorithms / worst-case + OOM — STD-3 below
- All Errors/Exceptions Handled — STD-4 below
- Idempotency / `INSERT OR REPLACE` — **compliant** (no FK references to `synset_centroids` confirmed via grep)
- Observability — STD-1 below
- FP over OOP — compliant
- Code to interface, not implementation — compliant
- Immutable state across boundary — STD-2 below
- UK English in identifiers/comments — compliant (grepped color/behavior/optimization/favorite/analyze, zero hits)
- Comments explain intent — STD-6 below
- Secrets policy — compliant

### Items Found

- **STD-1** Cascade module emits no log trace or timing for a multi-minute routine — Observability standard. **DECISION: fix (module logger + cohort-level logs).**
- **STD-2** `CascadeConfig` + `CascadeResult` not `frozen=True` — Immutable-state standard. Test at line 425 mutates `cfg.concreteness_threshold` post-construction. **DECISION: fix (`frozen=True` + rewrite the test using `dataclasses.replace`).**
- **STD-3** `build_synset_centroids` accumulates all centroid blobs in memory before bulk insert — OOM-risk standard. **DECISION: defer.** scope_boundary: optimisation for ~117k synsets × 1.2KB centroid = ~150-200MB peak. why_out_of_scope: current vocabulary doesn't push memory limits; 20k-word enrichment milestone is when this becomes load-bearing. Batch-flush pattern is a 10-line change deferrable to that milestone. proposed_followup: 20k-enrichment milestone.
- **STD-4** Silent swallow in `_centroid` (broad OperationalError catch, no log) — same root as SF-2. **DECISION: fix (merged).**
- **STD-5** No test pins observability/logging — consequential to STD-1. **DECISION: skip.** STD-1's fix lands the logger; no separate TDD-red test is needed if the cohort-level log lines are exercised by existing cohort tests indirectly.
- **STD-6** Comment line 272 restates code — Comments standard. **DECISION: fix.**

## Round 1 — ux-designer (2026-05-21T00:15:00Z)

**Status:** No-op — diff contains no user-facing surface changes (zero `*.html`/`*.css`/`*.jsx`/`*.tsx`/`*.vue`/`*.svelte` files; no `components/`, `pages/`, `views/`, `templates/`, `styles/` paths).

**Counts as:** adapter-CLEAN for halt purposes (no dispatch, no four-section gate validation required).

## Round 1 — Deferrals

Six items deferred this round, recorded into the top-level Deferrals Ledger:

| ID | Reviewer | Severity | scope_boundary | why_out_of_scope |
|----|----------|----------|----------------|------------------|
| D1 | type-design (TD-1) | important | invasive dataclass restructure | `__post_init__` cross-field assert is smallest fix but `frozen=True` (this round) already prevents post-construction drift; 5 callers all consistent. Pair with S05 type-design polish. |
| D2 | type-design (TD-6) | important | invasive TypedDict refactor | runtime invariants protected by `_run_one_variation`; cleaner shape lands when S05 forge integration adds a real consumer for narrowing. |
| D3 | silent-failure (SF-6) | low | per-pair JSON contract extension | ops-debug observability; lands with Pipeline Tooling Consolidation backlog. |
| D4 | type-design (TD-7) | low | TypedDict completeness | `apt_scored` recoverable as `n_apt - apt_gate_dropped`; duplicative churn without a forcing consumer; fix 3 already broke the same TypedDict this round. |
| D5 | type-design (TD-12) | cosmetic | defensive belt-and-braces cleanup | low-yield, semantically harmless. |
| D6 | type-design (TD-14) | cosmetic | refactor to shared `_concreteness` helper | pair with TD-1, TD-6, SP-7 in type-design follow-up PR. |
| D7 | type-design (TD-15) | low | `_summarise` dict shape consistency | m03_diagnostics is one-shot, no consumer; revisit if M04 re-runs the diagnostic. |
| D8 | superpowers (SP-7) | cosmetic | per-pair dict typing | pair with type-design follow-up PR. |
| D9 | superpowers (SP-1) | low | underscore-import promotion | pre-existing pattern across 6 scripts; not introduced by M03. |
| D10 | standards (STD-3) | low | OOM batch-flush optimisation | proposed_followup: 20k-word enrichment milestone. |
| D11 | superpowers (SP-5) | low | TDD commit history visibility | process improvement; cannot retroactively fix. Recorded for milestone retro. |

Total: 11 deferrals (3 important, 5 low, 3 cosmetic).

### Fixes Applied

19 fix commits across 4 disjoint files. Pre-fix SHA: `374fda4b`.

**evaluate_cascade.py + tests (10 commits):**
- `7e86d719` — add module logger + cohort-level progress trace (STD-1)
- `17635786` — freeze CascadeConfig + CascadeResult (STD-2 / TD-1 partial)
- `1f2dc54b` — CascadeConfig.__post_init__ validates composition / ortony_scoring / d_cap>0 / alpha>=0 (TD-8 / TD-9 / TD-10)
- `8fb9d4ab` — tighten _centroid OperationalError catch (SF-2 / STD-4)
- `bc18eb1c` — _cosine_distance returns None on dim-mismatch (TD-2)
- `684319f4` — _centroid validates BLOB length % 4 (TD-11)
- `2e2c3ed1` — rerank attrition counters (SF-1)
- `195615ac` — evaluate_cohort flags degenerate_cohort + log warning (SF-3)
- `6deb46b9` — docstring/comment cleanup (TD-4 / STD-6 / SP-6)
- `0962e987` — remove duplicate config validation now handled by __post_init__

**m03_diagnostics.py (2 commits):**
- `031246f1` — _cosine_distance returns None (was NaN) — harmonise with cascade (SF-5 / TD-3)
- `736032fd` — _centroid validates BLOB length divisibility (mirror of TD-11)

**build_synset_centroids.py + tests (4 commits):**
- `11b59b82` — track + log all-malformed-embedding synsets (SF-4)
- `25437a9a` — prune stale centroids for synsets with no properties (SP-8)
- `4748e7ae` — correct Go API docstring (TD-13)
- `8c14c5af` — document table asymmetry between centroid build + Ortony (SP-4)

**run_sweep.py + tests (3 commits):**
- `a5223ae2` — validator rejects evaluator-incompatible hyperparam keys (TD-5)
- `bb1ebffd` — validator enforces alpha>=0 + d_cap>0 (TD-9 / TD-10)
- `f6f9bf09` — thread cascade rerank counters + degenerate_cohort through OkVariationResult (TD-6 partial / extends fix 7 of evaluate_cascade)

### Files Modified

- `data-pipeline/scripts/evaluate_cascade.py`
- `data-pipeline/scripts/test_evaluate_cascade.py`
- `data-pipeline/scripts/m03_diagnostics.py`
- `data-pipeline/scripts/build_synset_centroids.py`
- `data-pipeline/scripts/test_build_synset_centroids.py`
- `data-pipeline/scripts/run_sweep.py`
- `data-pipeline/scripts/test_run_sweep.py`

### Test Results

**723 passing, 0 failed** (was 708 — +15 new tests added by fix subagents).

### Cumulative

Total rounds: 1 | Items resolved: 25 | Active deferrals: 11 | Superseded deferrals: 0 | Elapsed: ~35 min

**Severity trend (this round only):** 8 important + 7 low + 1 cosmetic fixed; 3 important + 5 low + 3 cosmetic deferred. No critical findings. Round was non-clean (fixes applied) → next round begins. `last_reviewer_pre_fix_sha = 374fda4b`; new HEAD = `0962e987`.

---
