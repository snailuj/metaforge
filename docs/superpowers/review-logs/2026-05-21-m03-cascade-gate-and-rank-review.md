# Review Loop — M03-S05 Forge Integration

**Branch:** `m03/cascade-gate-and-rank`
**Base:** `251b41b1` (M03 cascade Python work + retro)
**Head at start:** `3223aef4`
**Adapters:** pr-review-toolkit, superpowers, standards, ux-designer (no-op — no UI files in scope)

## Scope

17 commits since base, +3934 lines / −17:

```
api/cmd/metaforge/main.go                    (+7/-2)   — --cascade flag
api/internal/db/cascade.go                   (+228)    — CascadeCandidate, batch props, gate-pushdown CTE
api/internal/db/cascade_cache.go             (+109)    — CascadeCache eager load
api/internal/db/cascade_cache_test.go        (+71)
api/internal/db/cascade_test.go              (+152)
api/internal/forge/cascade.go                (+194)    — JaccardSalience, ReRankBonus, CascadeCosineDistance, EvaluateCascadePair
api/internal/forge/cascade_parity_test.go    (+206)    — Python-parity test
api/internal/forge/cascade_test.go           (+212)
api/internal/forge/forge.go                  (+9)      — Match cascade fields
api/internal/forge/forge_test.go             (+29)
api/internal/handler/handler.go              (+177/-15)— cascade branch
api/internal/handler/handler_cascade_test.go (+146)
docs/plans/2026-05-21-m03-s05-forge-integration.md (+2020)
docs/plans/2026-05-21-m03-s05-smoke-test-crib.md   (+245)
docs/roadmap/M04-cosine-candidate-gen-roadmap.md   (+128)
docs/roadmap/PIPELINE.md                           (+18/-2)
```

## Deferrals Ledger

### D1 — Tagged-union refactor for CascadeResult (TD2)
- **status:** active
- **severity:** important (type-design)
- **raised by:** pr-review-toolkit:type-design-analyzer, round 1
- **scope_boundary:** API surface change — would refactor `CascadeResult` from a flat struct to a `(Status, *Scored)` tagged-union shape and ripple through every call site (handler, parity test, smoke crib).
- **why_out_of_scope:** Architectural improvement, not a correctness bug. The 4-status invariant is currently enforced by `EvaluateCascadePair`'s construction (only 4 valid shapes ever produced) plus the test suite. The refactor is high-value but is a separate slice — captured for the architectural review milestone in PIPELINE.md.
- **proposed_followup:** Land in the M03 retro / pipeline architectural review pass, alongside the M05 type-aligned scoring work which will add a fifth status route.

### D2 — Constrained-type discipline for CascadeStatus + Composition (TD3, TD6)
- **status:** active
- **severity:** low
- **raised by:** pr-review-toolkit:type-design-analyzer, round 1
- **scope_boundary:** Wider language-discipline change — would add `Valid()` methods or constructors that prevent bad string literals from being assigned to typed-string aliases.
- **why_out_of_scope:** `DefaultCascadeConfig()` is the only production constructor and tests use the typed constants; a typo is caught at compile time for any internal call site. The fix would be belt-and-braces against a future external caller that constructs configs by struct literal.
- **proposed_followup:** Combine with D1 in the architectural review pass.

### D3 — CascadeCache encapsulation (TD4)
- **status:** active
- **severity:** important
- **raised by:** pr-review-toolkit:type-design-analyzer, round 1
- **scope_boundary:** Cache shape change — would unexport `Concreteness`/`Centroids` maps and add accessor methods. Touches handler call sites in `handleSuggestCascade` plus the parity test.
- **why_out_of_scope:** Today the cache is constructed once in `NewHandlerWithCascade` and only read thereafter — the read-only contract holds. The fix would prevent a *future* mutation bug. The existing doc-comment ("read-only by convention") is the current discipline.
- **proposed_followup:** Land alongside D1/D2 when extracting the shared `metaphor` package for the Forge/Bridge unification (see M04 roadmap doc).

### D4 — Match struct legacy/cascade split (TD5)
- **status:** active
- **severity:** low
- **raised by:** pr-review-toolkit:type-design-analyzer, round 1
- **scope_boundary:** JSON-wire-format change — would either split into `LegacyMatch`/`CascadeMatch` or change `GatePassed` to `*bool`.
- **why_out_of_scope:** Today the legacy path never populates cascade fields and the cascade handler only ships `Scored` rows (others filtered out before encoding). The contract holds. Frontend consumes the existing single-Match shape.
- **proposed_followup:** Combine with D1.

### D5 — Nil-cache defence in handleSuggestCascade (SF6)
- **status:** active
- **severity:** low
- **raised by:** pr-review-toolkit:silent-failure-hunter, round 1
- **scope_boundary:** Defensive guard. Today `useCascade` and `cache != nil` are guaranteed to track together by `NewHandlerWithCascade`.
- **why_out_of_scope:** Unreachable in current code. Reviewer's concern is "future refactor that splits the flag from the cache lifecycle". Defence-in-depth costs 3 lines but adds no signal until the hypothetical refactor lands.
- **proposed_followup:** Add when the metaphor package extraction (D3) lands and the cache lifecycle moves.

### D6 — Write-error inconsistency in HandleStrings / health (SF7)
- **status:** active
- **severity:** low
- **raised by:** pr-review-toolkit:silent-failure-hunter, round 1
- **scope_boundary:** Pre-existing (not introduced by S05). Same file as new cascade code; the inconsistency is the bug, not the silent write itself.
- **why_out_of_scope:** Pre-existing, low-impact, and the cascade path's new encode-error logging is the right direction. Filing for the post-PR cleanup pass.
- **proposed_followup:** Tooling consolidation milestone (queued in PIPELINE.md backlog).

### D7 — GROUP_CONCAT empty-token leak (SF8)
- **status:** active
- **severity:** low
- **raised by:** pr-review-toolkit:silent-failure-hunter, round 1
- **scope_boundary:** Schema-constraint question — depends on whether `property_vocab_curated.lemma` is NOT NULL.
- **why_out_of_scope:** Needs schema verification before deciding fix scope. The visible symptom (empty token in `shared_properties` array) would be a JSON shape issue, not a crash.
- **proposed_followup:** Capture in the pipeline architectural review milestone alongside the SCHEMA.sql canonicality work.

### D8 — Pre-existing legacy embedding-lookup silent degradation (F5)
- **status:** active
- **severity:** important
- **raised by:** pr-review-toolkit:silent-failure-hunter, round 1
- **scope_boundary:** Pre-existing in `handleSuggestLegacy`; the new `handleSuggestCascade` path correctly escalates via 500.
- **why_out_of_scope:** S05 is about wiring cascade; touching legacy error-handling shape is a separate concern. The cascade path sets the higher bar; legacy can be tightened in a follow-up.
- **proposed_followup:** Backlog: tighten legacy error escalation to match cascade path's contract, ideally when cascade goes default.

### D9 — Cascade ordering by salience+contrast vs final_score (PR1.2, SP3, SP4)
- **status:** active
- **severity:** low
- **raised by:** pr-review-toolkit:code-reviewer + superpowers, round 1
- **scope_boundary:** Pre-rank dimension is divorced from final-rank dimension; candidates ranked 51st by salience+contrast that would top final_score are silently lost.
- **why_out_of_scope:** M04 (cosine-sim candidate gen) is the strategic fix for the broader candidate-gen mismatch; this ordering quirk is a subset of that work. Until M04, operators can mitigate by raising limit (capped at 200).
- **proposed_followup:** Folds into M04 work — the M04 ANN candidate gen will UNION with the cluster-overlap path; revisit the ordering criterion when both sources contribute.

### D10 — Cascade observability: per-request trace + timing instrumentation (ST1, SP6)
- **status:** active
- **severity:** low
- **raised by:** standards reviewer + superpowers, round 1
- **scope_boundary:** Observability standard says timing-behind-feature-flag for complex routines; cascade qualifies. Today: no per-request control-flow trace, no cache-load timing, no scan-failure counter (though SF4 fix added the malformed-centroid counter).
- **why_out_of_scope:** Standards-driven addition rather than a correctness fix; the cascade is correct without it. Worth a dedicated observability slice rather than bolted onto S05.
- **proposed_followup:** Capture as a small observability slice when the team next touches the cascade path (likely M04 integration).

### D11 — Parity test coverage of CTE correctness (SP7)
- **status:** active
- **severity:** low
- **raised by:** superpowers, round 1
- **scope_boundary:** The parity test bypasses `GetForgeCascadeCandidatesByLemma` deliberately. CTE shape is verified by `TestGetForgeCascadeCandidatesByLemma_LimitReturnsDistinctCandidates` (added round 1) and the AllPassConcretenessGate test; no pinned-fixture test asserts shared_props correctness or antonym attachment shape.
- **why_out_of_scope:** The CTE returns whatever the underlying data shape produces; pinning a fixture requires a stable test DB, which conflicts with the live-DB convention. Defer until a test-fixture DB strategy is decided.
- **proposed_followup:** Pipeline architectural review milestone.

### D12 — Empty cascade tables → confusing empty 200 (SP8)
- **status:** active
- **severity:** low
- **raised by:** superpowers, round 1
- **scope_boundary:** `NewHandlerWithCascade` validates tables exist but not that they have rows. Empty cascade tables produce zero-result responses.
- **why_out_of_scope:** Today the deploy pipeline guarantees populated tables (74k+36k rows on prod DB). Reviewer's concern is a future fresh-build deploy.
- **proposed_followup:** Add row-count assertion in `NewHandlerWithCascade` pre-flight; small change but separate concern from S05's scope.

### D13 — sort.Slice not stable in sortByFinalScore (SP5)
- **status:** active
- **severity:** low
- **raised by:** superpowers, round 1
- **scope_boundary:** UI flicker on tied scores; consequence-of-stability not correctness.
- **why_out_of_scope:** Tied scores are rare in practice and the UI is in M03 backlog (not yet implemented). Worth fixing when the frontend lands.
- **proposed_followup:** Frontend integration milestone — switch to `sort.SliceStable` with documented tiebreaker.

### D14 — CascadeConfig.Validate() not ported from Python __post_init__ (PR1.3)
- **status:** active
- **severity:** low
- **raised by:** pr-review-toolkit:code-reviewer, round 1
- **scope_boundary:** Python `__post_init__` rejects negative alpha / non-positive d_cap / unknown composition; Go has no equivalent.
- **why_out_of_scope:** Only `DefaultCascadeConfig()` is exercised in production; struct-literal config construction is internal-only and unit-tested.
- **proposed_followup:** Combine with D1/D2 in architectural cleanup.

### D15 — IN-clause batch chunking absent (SP2)
- **status:** active
- **severity:** low
- **raised by:** superpowers, round 1
- **scope_boundary:** `GetSynsetClusterPropertiesBatch` has no chunking; SQLite default `SQLITE_MAX_VARIABLE_NUMBER = 32766`. Today bounded at ~402 placeholders (limit=200).
- **why_out_of_scope:** Future-proofing for M04's potentially larger candidate-pool. Today's bound is well under SQLite's limit.
- **proposed_followup:** M04 work; chunk when the candidate set broadens beyond ~1k.

### D16 — Legacy GetForgeMatchesCuratedByLemma carries the pre-PR1.1 LIMIT-truncation bug (OWN-F2 round 2)
- **status:** active
- **severity:** important
- **raised by:** pr-review-toolkit:code-reviewer, round 2
- **scope_boundary:** `api/internal/db/db.go:273-277` — same row-amplification pattern (JOIN lemmas before LIMIT) as the cascade query had pre-PR1.1. Legacy `/forge/suggest` (cascade=off) still truncates to ~half the requested limit on broad-coverage lemmas.
- **why_out_of_scope:** S05's scope was the cascade path; touching the legacy CTE shape is out of scope. The cascade path is now the prescribed path going forward (M04 + Bridge build on it); legacy may be retired or fixed during cascade default-on cutover.
- **proposed_followup:** Mirror the PR1.1 fix into the legacy CTE when (a) cascade goes default, or (b) someone files a user-visible bug on the legacy path. Trivial port — same one-lemma-per-target subquery pattern.

### D17 — Asymmetric centroid vs concreteness lookup discipline in handler (O3 round 2)
- **status:** active
- **severity:** low
- **raised by:** pr-review-toolkit:silent-failure-hunter, round 2
- **scope_boundary:** `handler.go:267-268` reads centroids with single-value map access (silent nil-on-miss), while concreteness uses two-value form (now Error-logged on miss after the round-2 fix). Centroid absence is more legitimate ("no embedding yet" — common during pipeline ramp-up) than concreteness absence.
- **why_out_of_scope:** Centroid coverage gaps are an M04 concern (the ANN candidate generator will need to handle them); inverting the discipline now would clash with M04's design.
- **proposed_followup:** Revisit when M04 lands and the centroid coverage contract is formalised.

### D18 — Pre-existing write-error ignored on /health endpoint (O5 / F-R2-5 round 2)
- **status:** active
- **severity:** cosmetic
- **raised by:** pr-review-toolkit:silent-failure-hunter + superpowers, round 2
- **scope_boundary:** `api/cmd/metaforge/main.go:45` — `w.Write([]byte(...))` ignores error. Same class as D6 (HandleStrings) but in a different file (touched for the `--cascade` flag).
- **why_out_of_scope:** Pre-existing standards-drift, low blast radius (health endpoint, write error means client gave up — log-and-continue is fine if logged).
- **proposed_followup:** Fold into D6's followup (tooling consolidation milestone).

### D19 — Polysemy-ASC lemma ordering deferred on perf grounds (Fix 2 round 2)
- **status:** active
- **severity:** low
- **raised by:** pr-review-toolkit:code-reviewer (F-R2-3 round 2)
- **scope_boundary:** `api/internal/db/cascade.go:148` — alphabetical-first `ORDER BY lemma LIMIT 1` for target lemma picking. Polysemy-ASC ordering (mirror of Python's `lookup_primary_synset`) was tested and produces semantically better lemma selection but cost 16× perf (15.97s vs ~1s on `anger limit=50`) because SQLite cannot index a correlated COUNT(*) over the lemmas table.
- **why_out_of_scope:** The semantic gain doesn't justify a 15× latency regression. Path forward: materialise `lemmas.polysemy_count` column at enrichment time so polysemy-ASC becomes an index-friendly scalar comparison.
- **proposed_followup:** Backlog item for next enrichment-pipeline schema pass — add `lemmas.polysemy_count` (computed once during PRE_ENRICH build), then switch the ORDER BY to `polysemy_count ASC`.

### D20 — Cascade observability: severity recalibration of D10 (round 2 standards challenge)
- **status:** active
- **severity:** **important** (escalated from low — see standards challenge below)
- **raised by:** standards reviewer, round 2
- **scope_boundary:** Same as D10 — per-request control-flow trace, cache-load timing, scan-failure aggregate counters.
- **why_out_of_scope:** Per project Observability standard text: "Collect timing behind feature-flags for all complex or potentially long-running routines. Timer functions must devolve to NO-OP when the feature-flag is disabled and in all production deployments." Cascade hot path is unambiguously complex (multi-CTE + batch lookup + per-candidate scoring + sort + encode) and product-critical. The standards-aligned severity is **important**, not **low**. Re-classified at round 2 close.
- **proposed_followup:** Dedicated observability slice before M04 ships (M04's broader candidate pool will increase the latency surface; the timing instrumentation should land before that change so we have a baseline to compare against).

---

## Round 1 — pr-review-toolkit (2026-05-21T11:00:00Z)

**Agents dispatched:** code-reviewer, silent-failure-hunter, type-design-analyzer

### Items Found

- [important] **LIMIT before dedup truncates cascade candidates 44-68%** (`api/internal/db/cascade.go:147-205`) — anger limit=50 returned 23 distinct synsets pre-fix.
  - Decision: fix
  - Rationale: visible regression in product behaviour; one-row-per-target subquery is the right shape.
- [critical] **loadConcreteness/loadCentroids fail-open on "no such table"** (`api/internal/db/cascade_cache.go:51-74,76-109`) — masks production schema races.
  - Decision: fix
- [critical] **Re-check error silently swallows → 200 instead of 500** (`api/internal/db/cascade.go:212-225`)
  - Decision: fix (duplicated by superpowers F1; consolidated)
- [critical] **Malformed centroid swallowed at Warn** (`api/internal/db/cascade_cache.go:96-103`) — pipeline contract violation.
  - Decision: fix (promote to Error + counter)
- [important] **Per-row Scan errors continue silently** (`cascade.go:193-195`, `cascade_cache.go:64-69,88-92`)
  - Decision: fix (first scan error escalates)
- [high (type-design)] **CascadeInputs pointer contract violated by handler** (`handler.go:252-264`) — `&topicConc` always non-nil strips absence signal.
  - Decision: fix (concreteness via cache, *float64 discipline mirrors parity test)
- [important] **Tagged-union refactor for CascadeResult** — defer to D1.
- [low...cosmetic] PR1.2, PR1.3, PR1.4, TD3-8, SF6-8, F5, SP2-10, ST1-3 — defer (D2-D15) or skip.

### Critique Sections
First round — `prior_reviewer: "N/A — first round"`, `fixes_reviewed: []`, `ledger_size: 0` for all 4 reviewers.

### Fixes Applied
- **db cache hardening (commit `0e0da567`)** — SF1 (drop fail-open), SF2-cache (escalate first scan error), SF4 (promote malformed centroid to Error + counter).
- **db candidate + handler cascade (commit `a0476094`)** — PR1.1 (one-lemma-per-target subquery so LIMIT applies post-dedup), SF2-cascade (escalate first scan error), SF3 (re-check error propagates), TD1 (concreteness via cache, drop topic_score/vehicle_score from row).

### Files Modified
- `api/internal/db/cascade_cache.go`
- `api/internal/db/cascade_cache_test.go`
- `api/internal/db/cascade.go`
- `api/internal/db/cascade_test.go`
- `api/internal/handler/handler.go`

### Test Results
Full `go test ./...` — 6 packages PASS (blobconv cached, db 9.6s, embeddings cached, forge 0.96s, handler 41.2s, thesaurus 39.5s). New regression test `TestGetForgeCascadeCandidatesByLemma_LimitReturnsDistinctCandidates`: anger limit=50 → 50 distinct (was 23).

### Cumulative
Total rounds: 1 | Items resolved: 6 | Active deferrals: 15 | Superseded deferrals: 0 | Elapsed: ~30m

---

## Round 1 — superpowers (2026-05-21T11:00:00Z)

10 findings, all but F1 (=SF3, fixed in batch B) deferred (D8-D15). See Deferrals Ledger above. Critique sections N/A for round 1.

## Round 1 — standards (2026-05-21T11:00:00Z)

**Standards sources:** `~/.claude/CLAUDE.md`, `/home/agent/projects/metaforge/CLAUDE.md`

### Standards Checked
- TDD (Red/Green) — atomic test+impl commits visible
- Algorithms / OOM — bounded, gate-pushdown perf-fix recorded
- All Errors/Exceptions Handled — 4 standards-driven fixes landed (SF1-4, SF3)
- Idempotency — read-only handler N/A in spirit
- Observability — partial; deferred to D10
- Coding style (FP, DRY/YAGNI, interface, immutable, UK English, comments)
- Project-local: Canary Releases (cascade flag), Pipeline (PIPELINE.md updated), Secrets

Findings: ST1 deferred to D10. ST2 (borderline comment restatement) skipped. ST3 (CI live-DB dependency) noted-not-flagged.

## Round 1 — ux-designer (2026-05-21T11:00:00Z)

**Status:** No-op — diff contains no user-facing surface changes (all Go API + docs; UI work parked per PIPELINE.md).
**Counts as:** adapter-CLEAN for halt purposes (no dispatch, no four-section gate validation required).

---

## Round 2 — pr-review-toolkit (2026-05-21T11:45:00Z)

**Agents dispatched:** code-reviewer, silent-failure-hunter, type-design-analyzer

### Items Found

- [critical/important × 3 reviewers] **GetSynsetClusterPropertiesBatch retains slog.Warn + continue** (`api/internal/db/cascade.go:41-44`) — sibling scan-loop missed by round-1 SF2 fix. Three reviewers (silent-failure-hunter O1, superpowers F-R2-1, standards ST4) converged. **Decision: fix.**
- [high] **Defence-in-depth log severity mismatch** (`handler.go:263-266`) — Warn understates a deterministic invariant violation. **Decision: fix (bump to Error + rewrite comment).**
- [important] **Empty propsByID despite candidates → silent empty 200** (`handler.go` post-batch) — schema drift / curated-vocab truncation. **Decision: fix (log Error).**
- [important] **D12 challenge: row-count assertion in NewHandlerWithCascade** — silent-failure-hunter promoted D12 from deferral to fix. **Decision: fix.**
- [low] **F-R2-3 / OWN-F1: alphabetical lemma pick is semantically arbitrary** — **Decision: attempt polysemy-ASC; fall back if slow.** (Result: fell back — 16× perf regression. Captured as D19.)
- [important] **F-R2-2: Go-side dedup masks SQL contract from test** — **Decision: fix (convert dedup to fmt.Errorf tripwire).**
- [low] **O7: sortByFinalScore (nil,nil) transitivity bug** — **Decision: fix.**
- [low] **Type-design re-confirmation of D1-D4, D14 + severity-recalibration of D3 (important → low)** — **Decision: note in ledger, no code change.**
- [important] **OWN-F2: legacy GetForgeMatchesCuratedByLemma has same LIMIT-before-dedup bug** — **Decision: defer as D16.**
- Several low-severity items (O3, O5, F-R2-5, Gap G) — **Decision: defer as D17/D18.**

### Critique Sections
- type-design-analyzer: CLEAN (OF1-OF3 noted as concur-with-existing-deferrals; no new actionable findings; recalibrated D3 important→low)
- silent-failure-hunter: NOT CLEAN (5 new findings — fixed O2, O7, O4; deferred O3, O5)
- pr-review-toolkit code-reviewer: NOT CLEAN (5 new findings + ledger reviewed; OWN-F1/F-R2-2 fixed, F-R2-3 attempted+deferred as D19, OWN-F2 deferred D16, OWN-F5 fixed via comment)
- DEFERRAL_LEDGER_REVIEW: 13 concur, 2 challenge (D7, D12). D12 promoted to fix this round; D7 stays deferred (schema check not done).

### Fixes Applied
- **db cascade.go (commit `42b44b83`)** — F-R2-1/ST4/O1 (escalate batch-props scan error), F-R2-2 (convert Go-side dedup to tripwire that catches SQL regressions), F-R2-3 attempted (polysemy-ASC ordering — fell back to alphabetical with documented trade-off after 16× perf hit; captured as D19).
- **handler.go (commit `78ffaa2e`)** — O2 (bump invariant tripwire to Error + fix misleading comment), O7 (sortByFinalScore (nil,nil) transitivity), O4 (log Error on empty propsByID with non-empty candidates), D12 (row-count assertion in NewHandlerWithCascade).

### Files Modified
- `api/internal/db/cascade.go`
- `api/internal/handler/handler.go`

### Test Results
Full `go test ./...` — 6 packages PASS (blobconv cached, db 13.5s, embeddings cached, forge 2.1s, handler 43.1s, thesaurus 39.5s). `TestGetForgeCascadeCandidatesByLemma_LimitReturnsDistinctCandidates`: anger limit=50 → 50 distinct (unchanged).

### Cumulative
Total rounds: 2 | Items resolved: 13 | Active deferrals: 19 | Superseded deferrals: 1 (D12 → fix) | Elapsed: ~75m

---

## Round 2 — superpowers (2026-05-21T11:45:00Z)

5 new findings (F-R2-1 through F-R2-5). F-R2-1 fixed (batch-props scan escalation). F-R2-2 fixed (Go-dedup tripwire). F-R2-3 attempted + deferred (D19). F-R2-4 (dead-code Warn) addressed via O2 fix. F-R2-5 (health write-error) deferred as D18.

Deferral verdicts: 13 concur, 2 challenge (D7 demote-to-quick-fix, D12 demote-to-quick-fix). D12 promoted to fix this round; D7 stays deferred (schema verification not done).

---

## Round 2 — standards (2026-05-21T11:45:00Z)

**Standards sources:** `~/.claude/CLAUDE.md`, `/home/agent/projects/metaforge/CLAUDE.md`

### Standards Checked
- TDD (Red/Green) — clean (test updates landed atomic with impl changes)
- Algorithms / OOM — clean (polysemy-ORDER BY would have been a regression; correctly fell back)
- All Errors/Exceptions Handled — ST4 fixed; standard now fully discharged across `cascade_cache.go`, `cascade.go`, `GetSynsetClusterPropertiesBatch` scan loops
- Idempotency — N/A
- Observability — D10 severity bumped to D20 (important); deferred to dedicated observability slice
- Coding style (FP, DRY, interface, immutable, UK English, comments) — clean
- Canary Releases, Pipeline, Secrets — clean

Findings: ST4 fixed, ST5 → D20 severity bump documented in ledger.

## Round 2 — ux-designer (2026-05-21T11:45:00Z)

**Status:** No-op — no UI-touching files changed between round 1 and round 2 (only Go API + review log).
**Counts as:** adapter-CLEAN for halt purposes.

---
