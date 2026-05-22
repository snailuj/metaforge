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

## Round 2 — pr-review-toolkit (2026-05-21T01:30:00Z)

**Agents dispatched:** code-reviewer (5 items), silent-failure-hunter (3 items), type-design-analyzer (5 items)

### Cross-reviewer convergence — the biggest miss of Round 1

**ALL FIVE** Round 2 reviewers independently caught the same fix-induced regression:

**OF-1 (rerank counter producer/consumer drift):** Round-1 fix `2e2c3ed1` emits `rerank_skipped` (single collapsed bucket — per its own intent comment) but the paired `f6f9bf09` sweep-side forwarder iterates the suffixes `("rerank_skipped_missing_centroid", "rerank_skipped_zero_norm")` and the TypedDict declares those split fields. The `if agg_key in agg` guard silently swallowed the drift. Net effect: the SF-1 silent-failure fix landed cohort-side but DIED at the sweep boundary — exactly the silent-fail class it was meant to close. **DECISION: fix (R2 Subagent 2).**

**OF-2 (degenerate_cohort wrong dict level):** SF-3's fix puts `degenerate_cohort` inside `result["aggregate"]` but the sweep-side reader looks at `result["degenerate_cohort"]` (top-level). Always False, always silently dropped. **DECISION: fix (R2 Subagent 2).**

### Items Found (deduplicated)

**Important:**
- CR-OF-2 / SF-OF-2 `_centroid` empty-blob branch silently returns None without log — partial coverage of the SF-2/STD-4 work. **DECISION: defer** (the fix is now in m03_diagnostics; cascade's parallel-update arrives via Subagent 1's clamp-harmonisation commit chain — no separate empty-blob log added cascade-side this round. **status: deferred to round 3 if re-raised**).

Actually: re-categorising — Subagent 1's R2 work did not add an empty-blob log to cascade `_centroid`. Tracking as D12 (new active deferral) for round 3.

**Low:**
- CR-OF-3 / SF-OF-3 enrich_pipeline.py `print()` mixed with build_synset_centroids' `log.info` — observability inconsistency. **DECISION: fix (R2 Subagent 3).**
- CR-OF-4 / SF-OF-4 `_re_rank_bonus(d_cap<=0)` dead defense — Round-1 `__post_init__` now rejects construction with bad d_cap; the in-fn guard is dead code that silently degrades. **DECISION: fix (R2 Subagent 1).**
- SP-OF-2 `build_synset_centroids` line 116 `np.frombuffer` crashes on bad-length blob — sibling missed by R1 sibling sweep (684319f4 + 736032fd hit two of three siblings). **DECISION: fix (R2 Subagent 3).**
- SP-OF-3 m03_diagnostics `_centroid` missing empty-blob guard that cascade has — sibling drift created by R1's harmonisation pass. **DECISION: fix (R2 Subagent 4).**
- SF-OF-2 m03_diagnostics `_iter_apt`/`_iter_inapt` silent row drops on incomplete fixtures. **DECISION: fix (R2 Subagent 4).**
- TD-NEW-4 `__post_init__` SCORING_FNS import-order coupling — not a current bug, all callers lazy. **DECISION: defer.** scope_boundary: documentation of the construction-time coupling. why_out_of_scope: not load-bearing today, no current callers construct at import time. Track as D13.

**Cosmetic:**
- CR-OF-5 Docstring tense "S02 contract" drift — S02 has landed. **DECISION: fix (R2 Subagent 1).**
- standards-OF-4 Magic 5% threshold → module constant. **DECISION: fix (R2 Subagent 1).**
- 031246f1 cosine clamp asymmetry — m03_diagnostics has the fp-rounding clamp; cascade does not. **DECISION: fix (R2 Subagent 1 — adds clamp).**
- silent-failure-OF "fail-open in this case" docstring conflates directions. **DECISION: fix (R2 Subagent 3).**
- TD-NEW-3 `_CASCADE_ONLY_KEYS` ↔ `CascadeConfig` field-set drift risk. **DECISION: defer.** scope_boundary: refactor the set derivation. why_out_of_scope: cosmetic future-proofing; field set is stable in M03; revisit if M04 adds cascade hyperparams. Track as D14.

### Deferral Challenges from Round 2

**Type-design challenged D1 + D2:**
- D1 (CascadeResult impossible combinations) — challenged. `frozen=True` doesn't fix the impossible-construction problem. **DECISION: promote to fix in R2** (Subagent 1 adds `__post_init__` cross-field assertion).
- D2 (OkVariationResult discriminated union) — challenged on grounds that OF-1's drift is direct evidence the rationale is wrong. **DECISION: keep deferred for S05** (the OF-1 fix this round removes the most urgent symptom; the structural cleanup still belongs with S05's consumer-side type-narrowing needs). Updated rationale: "fix-A landing this round removes the urgency; the cleanup is still right but no longer load-bearing."

**Type-design challenged D4 (apt_scored/inapt_scored omission):**
- Silent-failure verified the recovery argument (`n_apt - apt_gate_dropped == apt_scored`) is mathematically correct, contra the standards reviewer's first-pass critique.
- BUT Subagent 2's Round-2 work surfaced `apt_scored`/`inapt_scored` through the forwarder anyway (as the conservation-law denominator). **status: superseded-by-fix in R2 commit `4d8a6e64`.**

**Standards re-validated D10:** Round-1 fixes added `synsets_seen: set[str]` (6MB) and `synsets_with_all_malformed: list[str]` (small) — neither moves the 150-200MB peak. D10 rationale holds. **status: concur.**

**Other deferrals all concurred** (D3, D5, D6, D7, D8, D9, D11) — rationale unchanged.

### Critique Sections (compressed per reviewer)

**pr-review-toolkit:code-reviewer** — CLEAN: false. 5 items. Caught the OF-1 producer/consumer drift directly; also flagged the empty-blob silent return, print/log inconsistency, dead `_re_rank_bonus` defense, docstring tense drift.

**pr-review-toolkit:silent-failure-hunter** — CLEAN: false. 3 items (OF-1 schema drift, m03_diagnostics `_iter_*` silent drops, `_re_rank_bonus` dead silent fallback). Verified 7-of-8 R1 fixes assertively correct; flagged the rerank-counter pair as the half-broken cross-module contract.

**pr-review-toolkit:type-design-analyzer** — CLEAN: false. 5 items. Critically: OF-1 is "exactly the silent-fail class TD-6's deferral rationale claimed wouldn't happen". Verified R1's `frozen=True` + `__post_init__` are correct but identified the impossible-construction-time CascadeResult combinations still constructable (D1 promote-to-fix).

## Round 2 — superpowers (2026-05-21T01:30:00Z)

**Agent:** `superpowers:code-reviewer` — CLEAN: false. 3 items.

Net-new findings:
- SP-OF-2 `build_synset_centroids` line 116 — missed sibling in R1 BLOB-length sweep
- SP-OF-3 m03_diagnostics `_centroid` empty-blob guard missing (created by R1's own harmonisation)
- TD-NEW-3 _CASCADE_ONLY_KEYS / CascadeConfig drift risk (deferred D14)

Test quality verdict on R1 work: 13 of 15 new R1 tests are assertive; 2 are smoke-shape (`test_cascade_variation_carries_attrition_counters` was the smoke-shape that hid OF-1). R2 Subagent 2 strengthens it.

DEFERRAL_LEDGER_REVIEW: 11 of 11 concurred (D2 with caveat noting OF-1 evidence).

## Round 2 — standards (2026-05-21T01:30:00Z)

**Standards sources:** `~/.claude/CLAUDE.md` · `/home/agent/projects/metaforge/CLAUDE.md` · `/home/agent/projects/metaforge/data-pipeline/CLAUDE.md`

**Agent:** `general-purpose` — CLEAN: false. 4 items + per-standard re-audit.

### Items Found

- STD-OF-1 (important) Rerank counter producer/consumer drift — Code-to-interface violation. Same as the convergence.
- STD-OF-2 (important) degenerate_cohort wrong dict level — Code-to-interface violation. Same as convergence.
- STD-OF-3 (low) Round-1 fix introduced new TypedDict fields with no producer or consumer test — TDD violation.
- STD-OF-4 (cosmetic) Magic 5% threshold — Comments-explain-intent violation.

### Per-standard re-audit

| # | Standard | Verdict (post R1, pre R2-fixes) |
|---|----------|--------------------------------|
| 1 | TDD (Red/Green) | NON-COMPLIANT (R2 OF-1, OF-3) |
| 2 | Algorithms / OOM | COMPLIANT (D10 re-validated) |
| 3 | All Errors/Exceptions Handled | COMPLIANT |
| 4 | Idempotency | COMPLIANT |
| 5 | Observability | MOSTLY COMPLIANT (R2 OF-4 magic literal) |
| 6 | FP over OOP | COMPLIANT |
| 7 | Code to interface, not implementation | NON-COMPLIANT (OF-1, OF-2) |
| 8 | Immutable state across boundary | COMPLIANT |
| 9 | UK English | COMPLIANT |
| 10 | Comments explain intent | MOSTLY COMPLIANT |
| 11 | Secrets policy | COMPLIANT |

## Round 2 — ux-designer (2026-05-21T01:30:00Z)

**Status:** No-op — no UI files in diff. Counts as adapter-CLEAN for halt.

## Round 2 — Deferrals (added this round)

| ID | Source | Severity | scope_boundary | why_out_of_scope |
|----|--------|----------|----------------|------------------|
| D12 | R2 CR-OF-2 | low | `_centroid` empty-blob log harmonisation cascade-side | Subagent 1 added the clamp + tense fixes but not the empty-blob log; harmless silent path (returns None like NOT-NULL violation) but breaks sibling-symmetry. Defer to type-design follow-up PR. |
| D13 | R2 TD-NEW-4 | low | __post_init__ SCORING_FNS import-order coupling | Not a current bug; all callers construct lazily. Document if a future caller constructs at import time. |
| D14 | R2 TD-NEW-3 | cosmetic | _CASCADE_ONLY_KEYS field-set drift risk | Stable in M03; revisit if M04 adds cascade hyperparams. |

**Deferral D4 (TD-7) status update:** R2 Subagent 2's commit `4d8a6e64` surfaced `apt_scored`/`inapt_scored` through the forwarder as the conservation-law denominator → **status: superseded-by-fix in `4d8a6e64`, superseded_in_round=2.**

Total active deferrals: **13** (was 11 before R2; +3 new, −1 superseded).

### Fixes Applied

14 fix commits across 4 disjoint files. Pre-fix SHA: `6676240c`.

**evaluate_cascade.py + tests (5 commits):**
- `8b8d5d9c` — CascadeResult __post_init__ per-status invariant assertion (D1 promoted)
- `57e7299e` — remove dead _re_rank_bonus d_cap<=0 guard (CR-OF-4 / SF-OF-4)
- `67ba9090` — magic 5% → RERANK_COVERAGE_WARN_BELOW module constant (STD-OF-4)
- `773d0cee` — docstring tense correction (CR-OF-5)
- `33d9e733` — clamp cosine to [-1, 1] — harmonise with m03_diagnostics

**run_sweep.py + tests (3 commits):**
- `8c0d2306` — align rerank counter forwarding (OF-1) + remove dead TypedDict fields + new round-trip test
- `9f43584c` — degenerate_cohort reads from result['aggregate'] (OF-2) + new test
- `4d8a6e64` — strengthen rerank conservation-law test + surface apt_scored/inapt_scored (D4 superseded)

**build_synset_centroids.py + enrich_pipeline.py + tests (3 commits):**
- `24c8310a` — guard BLOB length divisibility before np.frombuffer (SP-OF-2 — missed sibling)
- `1bcad30a` — print → log.info in enrich_pipeline (CR-OF-3 / SF-OF-3)
- `9dab0cd2` — docstring direction conflation fix

**m03_diagnostics.py (3 commits):**
- `5290b567` — _centroid empty-blob guard (SP-OF-3 — sibling drift)
- `4d7346c3` — _iter_apt/_iter_inapt count + log skipped rows (SF-OF-2)
- `2b5292fd` — cosine clamp docstring + sibling harmonisation note

### Files Modified

- `data-pipeline/scripts/evaluate_cascade.py`
- `data-pipeline/scripts/test_evaluate_cascade.py`
- `data-pipeline/scripts/run_sweep.py`
- `data-pipeline/scripts/test_run_sweep.py`
- `data-pipeline/scripts/build_synset_centroids.py`
- `data-pipeline/scripts/test_build_synset_centroids.py`
- `data-pipeline/scripts/enrich_pipeline.py`
- `data-pipeline/scripts/m03_diagnostics.py`

### Test Results

**729 passing, 0 failed** (was 723 — +6 new tests from round 2).

### Cumulative

Total rounds: 2 | Items resolved: 14 (R2) / 39 cumulative | Active deferrals: 13 | Superseded deferrals: 1 | Elapsed: ~75 min

**Severity trend (this round only):** 3 important + 7 low + 4 cosmetic fixed; 0 important + 2 low + 1 cosmetic deferred (D12-D14); 1 important (D4) superseded by fix. Notable: convergence on OF-1 across all 5 reviewers — the most important defect of the loop so far, introduced by R1's own fix-forward pattern. Round was non-clean (fixes applied) → next round begins. `last_reviewer_pre_fix_sha = 6676240c`; new HEAD = `4d8a6e64`.

---

## Round 3 — All adapters (2026-05-21T02:45:00Z)

**Agents dispatched in parallel:**
- pr-review-toolkit:code-reviewer (2 items)
- pr-review-toolkit:silent-failure-hunter (3 items)
- pr-review-toolkit:type-design-analyzer (3 items)
- superpowers:code-reviewer (6 items)
- standards (general-purpose, 4 items)
- ux-designer (no-op — adapter-CLEAN by virtue of no UI files in diff)

### Cross-reviewer convergence (Round 3)

**Convergent finding A — 3 reviewers (code-reviewer OWN-1, silent-failure OF-B, superpowers OF-R3-1):** `test_ok_row_carries_rerank_counters` asserts conservation law against `n_apt` instead of `apt_scored`. The current fixture has zero gate-dropped apt pairs so `n_apt == apt_scored` coincidentally — but the moment a fixture grows to include a gate-drop, the assertion fires false-positive. The sibling test `test_cascade_variation_carries_attrition_counters` uses the correct denominator. **DECISION: fix (R3 Subagent 2).**

**Convergent finding B — 2 reviewers (type-design TD-R3-1/2, superpowers OF-R3-2):** `CascadeResult.__post_init__` (Round-2 fix `8b8d5d9c`) under-specifies invariants for the three None-result statuses. Documented invariants for `missing_concreteness` / `no_properties` / `unresolved` include specific `gate_passed` values AND `cosine_distance=None` + `re_rank_bonus=None` — none of these were enforced. **DECISION: fix (R3 Subagent 1).**

### Items Found (deduplicated)

**Important (2):**
- Conv-A: denominator fix (covered above)
- Conv-B: __post_init__ partial invariant coverage (covered above)

**Low (5):**
- TD-R3-3 — `__post_init__` no exhaustiveness fallback for unknown status. **DECISION: fix (R3 Subagent 1).**
- D12 challenge (standards): cascade-side `_centroid` empty-blob path silent — institutionalised by misleading comment in m03_diagnostics docstring. **DECISION: promote D12 to fix in both siblings (R3 Subagents 1 + 3).**
- OF-R3-5 / standards-STD-R3-1 — m03_diagnostics `_centroid` misleading comment after R2 5290b567. **DECISION: fix (R3 Subagent 3, combined with D12 promotion).**
- silent-failure OF-A — `run_sweep` cohort-attrition forwarder uses `int(agg.get(key, 0))` silent-default for non-rerank attrition keys. **DECISION: defer (D15).** scope_boundary: mitigated by strengthened conservation-law test pinning specific attrition values for 5 of 8 keys. why_out_of_scope: the convergence-finding-A fix (Conv-A) makes the conservation law non-vacuous for the rerank pair; the parallel attrition keys would benefit from the same pinning but require new fixture variations per key. Defer to type-design follow-up alongside D2/D6/D8.
- silent-failure OF-C — cosine clamp lands without dedicated unit test. **DECISION: defer (D16 — test-polish bundle).** Numerical hardening is exercised indirectly by all existing cosine tests; adversarial-input test is incremental polish.

**Cosmetic (3):**
- standards-STD-R3-2 — review-process metadata creeping into production comments (round-N references in docstrings). **DECISION: defer (D17).** scope_boundary: convention adjustment. why_out_of_scope: the metadata is informative for current contributors; tightening to drop round-N references is a stylistic call that pairs with the type-design follow-up PR.
- OF-R3-3 / OF-R3-6 — RERANK_COVERAGE_WARN_BELOW fires noisily on small fixtures; magic literals (271/978) in docstring. **DECISION: defer (D16, bundled).**
- STD-R3-3 — gate_dropped's 2nd raise (cosine/re_rank_bonus) lacks a dedicated test. **DECISION: defer (D16, bundled).** New invariant tests landing in this round cover gate_passed + cosine_distance + re_rank_bonus for the three None-result statuses; the symmetric coverage for gate_dropped's cosine_distance/re_rank_bonus is a small test addition pairing with the test-polish bundle.

**Informational (1):**
- code-reviewer OWN-2: CascadeResult `unresolved` invariant exists but cohort orchestrator constructs the unresolved per-pair row inline (dict literal) rather than via CascadeResult. Not a bug — defensive code that hardens future migration of the inline construction site to use CascadeResult.

**Cosmetic-only (1):**
- standards-STD-R3-4: FP-vs-OOP — `__post_init__` could be tabularised. **DECISION: skip.** Pragmatic carve-out applies; explicit form is more readable for per-status invariants.

### Deferral evolution (R3)

- **D12 (cascade _centroid empty-blob log) — SUPERSEDED by R3 5ec963e3 + cc6592f7.** Both siblings now `log.debug` on empty-blob path.
- **D15 (new):** silent-failure OF-A — `run_sweep.py` attrition forwarder silent-default on missing keys. Severity: low. scope_boundary: mitigation already provided by conservation-law test pinning 5 of 8 attrition values. why_out_of_scope: pair with type-design follow-up where the TypedDict refactor (D2) would force the producer/consumer contract through the type system rather than runtime guards.
- **D16 (new):** test-polish bundle — OF-C (cosine clamp adversarial test), OF-R3-3 (RERANK warn noise on small fixtures), OF-R3-4 (m03_diagnostics iter-summary test), OF-R3-6 (magic literals 271/978 in docstring), STD-R3-3 (gate_dropped 2nd-raise test). Severity: low. scope_boundary: test-quality polish across 5 minor coverage gaps. why_out_of_scope: collectively a half-day's work that doesn't change semantics; lands cleanly in a dedicated test-polish PR.
- **D17 (new):** review-process metadata in production comments (STD-R3-2). Severity: cosmetic. scope_boundary: stylistic convention adjustment. why_out_of_scope: convention call; pairs with type-design follow-up PR.

Net deferral count: 12 active − 1 superseded (D12) + 3 new = **14 active**. Superseded count: 3.

### Critique Sections (compressed per reviewer)

**code-reviewer** — CLEAN: false. Verified 12 of 14 R2 fixes correct. Headline catch: OWN-1 denominator nit. Verified OF-1/OF-2 fixes complete via grep symmetry check.

**silent-failure-hunter** — CLEAN: false. 3 items: OF-A (sibling drift in attrition forwarder — same class as OF-1 but for non-rerank keys), OF-B (denominator), OF-C (clamp untested). Verified producer-consumer drift class genuinely closed for rerank pair. The cosine clamp on cascade-side is correct numerical hardening but lands without a test.

**type-design-analyzer** — CLEAN: false. 3 items, all on `CascadeResult.__post_init__` incompleteness (TD-R3-1 gate_passed, TD-R3-2 cosine/re_rank_bonus pinning, TD-R3-3 exhaustiveness fallback). Verified 13 of 14 R2 commits clean by type-design lens; the headline fix (8b8d5d9c) lands the structure but under-specifies three of five status branches.

**superpowers** — CLEAN: false. 6 items, mostly redundant with the other reviewers' findings (denominator, partial invariants, RERANK warn noise, untested iter-summary, misleading comment, magic literals in docstring). Verified statistical claims unchanged.

**standards** — CLEAN: false. 4 items + per-standard re-audit. The 11-standard table came out MOSTLY COMPLIANT (3 standards) + COMPLIANT (8 standards). Headline challenge: D12 (cascade empty-blob log) — silent-skip should be log.debug for sibling parity. Plus STD-R3-2 (review-process metadata) + STD-R3-3 (test gap) + STD-R3-4 (FP refactor candidate).

### Fixes Applied

5 fix commits across 3 disjoint files. Pre-fix SHA: `1ee6ff4b`.

**evaluate_cascade.py + tests (3 commits — Subagent 1):**
- `368b7464` — extend CascadeResult __post_init__ for None-result statuses (gate_passed + cosine/re_rank_bonus pinning, 6 new tests)
- `f8750548` — exhaustiveness fallback raises on unknown status (1 new test)
- `5ec963e3` — _centroid log.debug on empty-blob fail-open (D12 cascade-side)

**run_sweep.py tests (1 commit — Subagent 2):**
- `a75a73e7` — conservation law uses apt_scored denominator + new reinforcing test with gate-dropped fixture

**m03_diagnostics.py (1 commit — Subagent 3):**
- `cc6592f7` — _centroid log.debug + correct misleading sibling comment (D12 diagnostics-side, OF-R3-5)

### Files Modified

- `data-pipeline/scripts/evaluate_cascade.py`
- `data-pipeline/scripts/test_evaluate_cascade.py`
- `data-pipeline/scripts/test_run_sweep.py`
- `data-pipeline/scripts/m03_diagnostics.py`

### Test Results

**737 passing, 0 failed** (was 729 — +8 new tests: 6 new invariant tests + 1 exhaustiveness + 1 reinforcing gate-drop).

### Cumulative

Total rounds: 3 | Items resolved this round: 5 | Cumulative resolved: 44 | Active deferrals: 14 | Superseded deferrals: 3 | Elapsed: ~110 min

**Severity trend (this round only):** 2 important + 1 low fixed (D12 + Conv-A + Conv-B + exhaustiveness); 0 important + 2 low + 3 cosmetic deferred (D15, D16-bundle, D17). The loop is now resolving polish items rather than load-bearing defects. Round was non-clean (fixes applied) → next round begins. `last_reviewer_pre_fix_sha = 1ee6ff4b`; new HEAD = `a75a73e7`.

---

## Round 4 — All adapters (2026-05-21T03:30:00Z)

**Status:** CLEAN round — all five reviewer adapters returned adapter-CLEAN with substantive four-section critique. ux-designer remains no-op. **HALT FIRES.**

### Adapter verdicts

**pr-review-toolkit:code-reviewer** — CLEAN: true. Verified all 5 R3 fixes correct; no boundary defects or partial-coverage residue introduced by polish-tier work. All 14 active deferrals concurred.

**pr-review-toolkit:silent-failure-hunter** — CLEAN: true. Read diff `1ee6ff4b..HEAD` end-to-end with own rule set; cross-file contract verified by grep — producer-emitted counter keys (`{unresolved, missing_concreteness, gate_dropped, no_properties, scored, rerank_applied, rerank_skipped}`) match consumer-read keys at `run_sweep.py:585-598`. **D15 deferral rationale refined**: the silent-default `int(agg.get(key, 0))` is now dead defence under the current literal-dict producer; the real exposure is *future* producer drift, not a current bug. The KeyError-on-missing-key fix is a 1-line change but conceptually pairs with D2's TypedDict refactor — defer co-resolution.

**pr-review-toolkit:type-design-analyzer** — CLEAN: true. Verified `CascadeResult.__post_init__` covers 4 of 5 statuses exhaustively; the `scored` branch intentionally leaves the cosine_distance/re_rank_bonus pairing rule unenforced because the producer at lines 397-403 sets them in lockstep (structurally unreachable illegal state). Exhaustiveness fallback reachable via `# type: ignore` bypass (tested). **Recommendation: tag D2 + D8 + D15 as co-blocking trio** for the S05 type-design polish PR — three dict surfaces (`OkVariationResult`, per-pair dict, attrition forwarder) in the same code region all want TypedDict discipline together.

**superpowers:code-reviewer** — CLEAN: true. Holistic verdict: loop has reached natural termination. R3 resolved only polish items (denominator nit, exhaustiveness, sibling log parity); R4 would either find adapter-CLEAN or surface items that legitimately belong in deferred follow-up PRs. Hostile-refactor robustness check: deleting any new `__post_init__` branch breaks at least one R3 test; replacing `apt_scored` with `n_apt` breaks the new gate-drop fixture test. Test suite is genuinely assertive. Statistical claims (Stage-2 separation +0.1779, etc.) still verifiable against sweep JSON.

**standards (general-purpose)** — CLEAN: true. Full per-standard re-audit returns COMPLIANT on all 11 standards. D17 (review-process metadata in production comments) re-examined and concurred — round-N references are citation annotations, not violations of "comments explain intent" (the intent is still explained; round-N is provenance). All 14 active deferrals concurred.

**ux-designer** — No-op. Diff contains no UI-touching files; adapter-CLEAN by virtue of nothing to review.

### Round 4 Result

- **Items found:** 0
- **Fixes applied:** 0
- **Round CLEAN:** YES (all adapters adapter-CLEAN AND no fixes applied this round)
- **Halt condition:** SATISFIED

### Files Modified

(none — no fixes applied)

### Test Results

**737 passing, 0 failed** (unchanged from Round 3 HEAD).

### Cumulative (final)

Total rounds: 4 | Items resolved: 44 | Active deferrals: 14 | Superseded deferrals: 3 | Elapsed: ~135 min

---

## Out-of-Scope Deferral Report

Ledger evolution: **17 recorded** · 3 superseded by downstream fix (D1, D4, D12) · 0 withdrawn · **14 still active**

Active deferrals across 4 rounds: **14**
Severity breakdown (active only): **2 important · 8 low · 4 cosmetic**

### Deferral D2 — `OkVariationResult total=False` defeats narrowing
- Round raised: R1 (type-design TD-6) • Reviewer: pr-review-toolkit:type-design-analyzer • Severity: **important**
- File: `data-pipeline/scripts/run_sweep.py:60-99` (TypedDict definition)
- Description: TypedDict is `total=False` to accommodate cascade-only fields, but the side effect is that every field becomes NotRequired including the always-set core fields (`aptness_rate`, `separation_score`, etc.). Static checkers cannot narrow `row["aptness_rate"]` from `float | None` to `float`.
- Scope boundary: invasive TypedDict refactor — split into discriminated union (`OkAptnessResult | OkCascadeResult`)
- Why out-of-scope: structurally cleaner long-term shape, but the runtime invariants are protected by `_run_one_variation`; refactor is best paired with the S05 forge integration where the consumer side gains real benefit from narrowing.
- Challenge history: R2 challenged on grounds of OF-1 evidence; rationale updated post-OF-1-fix ("fix-A removes urgency"). R3 + R4 concurred with updated rationale.
- Proposed follow-up: S05 forge integration / type-design polish PR
- **Co-blocking with: D8, D15** (per R4 type-design-analyzer recommendation)

### Deferral D3 — Per-pair detail rows don't record concreteness/delta
- Round raised: R1 (silent-failure SF-6) • Reviewer: pr-review-toolkit:silent-failure-hunter • Severity: **low**
- File: `data-pipeline/scripts/evaluate_cascade.py:349-361`
- Description: Per-pair detail rows record `status, gate_passed, ortony_score, cosine_distance, re_rank_bonus, score` but NOT concreteness scores or signed delta. When a pair lands in `gate_dropped`, the per-pair row says only `status: "gate_dropped"`.
- Scope boundary: per-pair JSON contract extension
- Why out-of-scope: schema extension touches the per-pair JSON contract that an operator-side notebook would consume; lands alongside operator-tooling work
- Proposed follow-up: Pipeline Tooling Consolidation backlog item

### Deferral D5 — Defensive `row[0] is None` against schema NOT NULL
- Round raised: R1 (type-design TD-12) • Severity: **cosmetic**
- File: `data-pipeline/scripts/evaluate_cascade.py:136` (and similar sites)
- Description: Schema declares `centroid BLOB NOT NULL` but Python guard still checks `row[0] is None`. Belt-and-braces.
- Scope boundary: belt-and-braces cleanup
- Why out-of-scope: low-yield change, would obscure the per-cell read pattern with no operator benefit
- Proposed follow-up: type-design polish PR (with D2)

### Deferral D6 — Sibling `_concreteness` divergent return types
- Round raised: R1 (type-design TD-14) • Severity: **cosmetic**
- File: `data-pipeline/scripts/evaluate_cascade.py:103-109` vs `m03_diagnostics.py:87-93`
- Description: Two `_concreteness` functions, same table, different return shapes (`Optional[float]` vs `tuple[float|None, str|None]`).
- Scope boundary: refactor to shared helper
- Why out-of-scope: extraction belongs with type-design follow-up PR alongside D2, D8
- Proposed follow-up: type-design polish PR

### Deferral D7 — `_summarise` dict shape diverges for n=0/n=1/n>=2
- Round raised: R1 (type-design TD-15) • Severity: **low**
- File: `data-pipeline/scripts/m03_diagnostics.py:246-266`
- Description: Same key takes different value types depending on `n`. Downstream consumers must branch on `n`.
- Scope boundary: m03_diagnostics is one-shot pre-flight script (~400 lines, no tests, no callers)
- Why out-of-scope: the script ran successfully and produced the JSON used by S01-findings; reshape has no consumer
- Proposed follow-up: revisit if M04 re-runs the diagnostic

### Deferral D8 — Per-pair dict uses untyped string keys (no TypedDict)
- Round raised: R1 (superpowers SP-7) • Severity: **cosmetic**
- File: `data-pipeline/scripts/evaluate_cascade.py:349-361`
- Description: Per-pair rows assembled with literal string keys; no `CascadePairRow` TypedDict.
- Scope boundary: cosmetic typing extension
- Why out-of-scope: pairs with D2 / D6 in S05 type-design follow-up PR
- **Co-blocking with: D2, D15**

### Deferral D9 — Underscore-prefixed imports from evaluate_aptness
- Round raised: R1 (superpowers SP-1) • Severity: **low**
- File: `data-pipeline/scripts/evaluate_cascade.py:37-46` (and 6 other scripts)
- Description: Six other scripts already import underscore-private helpers; M03 entrenches but doesn't introduce.
- Scope boundary: pre-existing pattern across 6 scripts
- Why out-of-scope: not introduced by M03; promotion is broader-scope refactor
- Proposed follow-up: standalone "promote module API" PR

### Deferral D10 — OOM batch-flush in `build_synset_centroids`
- Round raised: R1 (standards STD-3) • Severity: **low**
- File: `data-pipeline/scripts/build_synset_centroids.py:85-118`
- Description: All centroid blobs accumulated into a list before single `executemany`; ~150-200MB peak at production scale.
- Scope boundary: optimisation for current vocabulary; not load-bearing
- Why out-of-scope: re-validated R2/R3/R4 — current peak is below process limits
- Proposed follow-up: 20k-word enrichment milestone (when memory pressure increases)

### Deferral D11 — TDD commit-history visibility
- Round raised: R1 (superpowers SP-5) • Severity: **low**
- File: git history of evaluate_cascade.py (and other M03 commits)
- Description: Tests + code shipped in single `feat` commits; per-test red-then-green not visible from `git log`.
- Scope boundary: process improvement
- Why out-of-scope: cannot retroactively fix
- Proposed follow-up: milestone retro / future-milestone discipline

### Deferral D13 — `__post_init__` SCORING_FNS import-order coupling
- Round raised: R2 (type-design TD-NEW-4) • Severity: **low**
- File: `data-pipeline/scripts/evaluate_cascade.py:CascadeConfig.__post_init__`
- Description: `__post_init__` references `SCORING_FNS` at construction; a future caller constructing at module-import time before evaluate_aptness imports would crash.
- Scope boundary: documentation of construction-time coupling
- Why out-of-scope: not load-bearing today; all current callers lazy
- Proposed follow-up: document if a future caller emerges

### Deferral D14 — `_CASCADE_ONLY_KEYS` field-set drift risk
- Round raised: R2 (type-design TD-NEW-3) • Severity: **cosmetic**
- File: `data-pipeline/scripts/run_sweep.py` (set definition) vs `evaluate_cascade.py` (CascadeConfig fields)
- Description: Two sets must stay in lock-step; future cascade hyperparam additions could silently slip past validator.
- Scope boundary: future-proofing
- Why out-of-scope: field set is stable in M03
- Proposed follow-up: revisit if M04 adds cascade hyperparams

### Deferral D15 — `run_sweep` cohort-attrition forwarder silent-default
- Round raised: R3 (silent-failure OF-A) • Severity: **low**
- File: `data-pipeline/scripts/run_sweep.py:585-598`
- Description: Forwarder uses `int(agg.get(key, 0))` for 8 attrition keys. R4 refined: silent-default is dead defence under current literal-dict producer; real exposure is future producer drift.
- Scope boundary: structural fix pairs with D2 TypedDict refactor
- Why out-of-scope: conservation-law test (R3 strengthening) pins 1 of 8 keys non-trivially; KeyError-on-missing pairs with discriminated union landing
- Proposed follow-up: type-design polish PR (with D2, D8)
- **Co-blocking with: D2, D8**

### Deferral D16 — Test-polish bundle (5 sub-items)
- Round raised: R3 (multi-reviewer) • Severity: **low**
- Sub-items:
  - Cosine clamp adversarial-input test
  - RERANK_COVERAGE_WARN_BELOW noise on small fixture cohorts
  - m03_diagnostics `_iter_*` summary log test
  - Magic literals 271/978 in RERANK constant docstring
  - gate_dropped 2nd-raise (cosine/re_rank_bonus) dedicated test
- Scope boundary: test-quality polish across 5 minor coverage gaps
- Why out-of-scope: collectively a half-day's work that doesn't change semantics
- Proposed follow-up: dedicated test-polish PR

### Deferral D17 — Review-process metadata in production comments
- Round raised: R3 (standards STD-R3-2) • Severity: **cosmetic**
- File: build_synset_centroids.py, enrich_pipeline.py, m03_diagnostics.py (various)
- Description: Round-N references in production docstrings (e.g. "Round-1 documented this asymmetry; Round-2 clarified..."). Informative now but rot over time.
- Scope boundary: stylistic convention adjustment
- Why out-of-scope: round-N markers are citation annotations, not "comments explain intent" violations
- Proposed follow-up: type-design polish PR

### Patterns

**Cluster by subsystem:** 8 of 14 deferrals (D2, D5, D6, D7, D8, D13, D14, D15) cluster in the type-design / TypedDict / dataclass-invariant space → form a natural S05 type-design polish PR. 1 in observability (D3 — per-pair JSON extension), pairs with Pipeline Tooling Consolidation. 1 each in: OOM optimisation (D10 — 20k-enrichment milestone), TDD process (D11 — retro), import-style (D9 — broader-scope refactor), test-polish (D16 — dedicated PR), and convention (D17 — type-design PR).

**Severity skew:** Only 2 of 14 are `important` (D2 + D15, co-blocking); the rest are low/cosmetic. The loop legitimately resolved every defect that could ship and deferred only structural-cleanup or pre-existing-pattern items.

**Co-blocking trio:** D2 + D8 + D15 should land together in the S05 type-design polish PR. The same root cause (TypedDict and friends not carrying producer/consumer contract through type system) manifests across all three.

**No deferral bounced ≥2 times.** D1 + D4 + D12 were promoted-to-fix once each (in R2 + R2 + R3 respectively) and resolved cleanly. No oscillation.

---

