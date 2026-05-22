# Code Review Loop — m03/pre-m04-deferrals branch

Branch: `m03/pre-m04-deferrals` (cut from `main` after PR #19 merge on 2026-05-22).

## Scope

Closes three deferrals from the 2026-05-21 M03-S05 review log:

- **D20** — Cascade observability (per-request trace + timing instrumentation)
- **D16** — Mirror PR1.1 LIMIT-truncation fix into legacy `GetForgeMatchesCuratedByLemma`
- **D8** — Tighten legacy embedding-lookup error escalation

Plus a PIPELINE.md anchor commit so the remaining 14 deferrals (D9/D15/D17 against M04, D1/D2/D3/D4/D5/D14 against the `metaphor` package extraction, and D6/D11/D13/D18/D19 against later slots) don't get lost.

Files touched (backend + docs only, no UI):
- `api/cmd/metaforge/main.go`
- `api/internal/db/cascade_cache.go`
- `api/internal/db/db.go`
- `api/internal/db/db_test.go`
- `api/internal/handler/handler.go`
- `api/internal/handler/handler_cascade_test.go`
- `api/internal/handler/handler_legacy_embedding_error_test.go` (new)
- `api/internal/observe/timer.go` (new)
- `api/internal/observe/timer_test.go` (new)
- `docs/roadmap/PIPELINE.md`

## Deferrals Ledger

### R1-D1 — Disabled-path per-call allocation in observe.Start (TD1 / SP4 / ST3; R3-OWN-3 addendum)
- **status:** active
- **severity:** low (perf)
- **raised by:** pr-review-toolkit:type-design-analyzer, superpowers:code-reviewer, standards reviewer (round 1); rationale extended round 3 (R3-OWN-3)
- **scope_boundary:** API-shape change. The clean fix is a two-method API (`Stop()` + `StopWith(extra ...any)`) so callers opt into variadic boxing only on the enabled path; alternatively a typed Timer struct injected through the handler graph.
- **why_out_of_scope:** Per-request cost on the disabled path is bounded at ~6 closure literals + ~6 variadic slices (round 2's timer.go doc explicitly enumerated both costs) on a path that already pays for slog and json encoding overhead. The architectural fix lands cleanly with the metaphor-package extraction (anchored in PIPELINE.md against D1/D2/D3/D4/D5/D14) where the observe surface can be redesigned alongside CascadeCache encapsulation. Fixing it pre-M04 would either ship a brittle one-package-level-noop trick or thrash the call sites twice.
- **proposed_followup:** Land with the `metaphor` package extraction milestone (between M04 and Bridge per PIPELINE.md). Redesign the observe surface to a typed Timer that callers can construct per-request, removing both the global flag and the variadic + closure allocation concerns.

### R1-D2 — Test bypasses NewHandlerWithCascade via direct &Handler{} construction (TD2)
- **status:** active
- **severity:** low (test discipline)
- **raised by:** pr-review-toolkit:type-design-analyzer (round 1)
- **scope_boundary:** `api/internal/handler/handler_legacy_embedding_error_test.go:85-89` constructs `&Handler{database: testDB, useCascade: false, cascadeConf: ...}` directly, bypassing the row-count/cache-load discipline of NewHandlerWithCascade. The fix is either a test-only `newHandlerForTest(...)` constructor or restructuring Handler so private-construction is safe.
- **why_out_of_scope:** D3 (CascadeCache encapsulation) and D5 (nil-cache defence) from the prior review log already cover the broader Handler-construction discipline rework. Adding a test-only constructor before that lands would create the second escape hatch we'd then need to remove. The current test reaches the SF1 + D8 error paths it was written for; the construction style is a precedent worth flagging but not blocking.
- **proposed_followup:** Fold into the `metaphor` package extraction milestone alongside D3/D5; add `newHandlerForTest` (or its successor) as part of that refactor and migrate this test.

### R1-D3 — Global mutable observe.enabled state (TD3 / ST5)
- **status:** active
- **severity:** low (concurrency / testability)
- **raised by:** pr-review-toolkit:type-design-analyzer, standards reviewer (round 1)
- **scope_boundary:** `observe.enabled` is package-level `atomic.Bool` mutated through `Init()`. Today's tests rely on Go's serial-by-default execution within a package; the moment any test uses `t.Parallel()` on the cascade hot path it becomes a race vector. Clean fix: inject a `*Timer` (or interface) through the handler graph.
- **why_out_of_scope:** Same architectural slot as R1-D1 — the observe surface redesign is the right place to remove the global. Adding test-scope wrappers (`observe.WithEnabled(t, true)` + Cleanup) before then would patch the symptom but leave the global in place for production callers.
- **proposed_followup:** Land with the `metaphor` package extraction milestone; redesign observe surface to remove global flag.

### R1-D4 — handleSuggestCascade logs Error and continues when batch propsByID is empty for all candidates (SF3)
- **status:** active
- **severity:** low
- **raised by:** pr-review-toolkit:silent-failure-hunter (round 1)
- **scope_boundary:** `api/internal/handler/handler.go:290-299` — when the gated CTE returned candidates but `GetSynsetClusterPropertiesBatch` returned no properties for any of them, the handler logs at Error level and continues into the scoring loop (every candidate then drops as `CascadeStatusNoProperties` and the user sees an empty 200). The comment explicitly diagnoses this as a database-integrity event ("synset_properties_curated truncated post-startup or schema drifted") but the response shape is the same as the legitimate "lemma enriched but no gate-pass" case.
- **why_out_of_scope:** This decision was made in the M03-S05 review (the slog.Error+continue is from that branch's design, not introduced here). Changing 200→500 on this path is a behavioural change beyond the D20/D16/D8 scope of this branch. The Error-level log gives operators the signal; a startup-style row-count tripwire would be the right fix and that's the same shape as the existing tripwire in NewHandlerWithCascade.
- **proposed_followup:** Standalone slice (or fold into the cascade-observability follow-up that lands around M04) — add a runtime row-count tripwire for synset_properties_curated, fail-loud on truncation.

### R1-D5 — GetLemmaForSynset returns bare err without wrapping (SF4)
- **status:** active
- **severity:** low
- **raised by:** pr-review-toolkit:silent-failure-hunter (round 1)
- **scope_boundary:** `api/internal/db/db.go:443-452` (post-fix line offsets approximate). Function returns raw `err` rather than `fmt.Errorf("GetLemmaForSynset failed for %s: %w", synsetID, err)` like every other helper in the file. Pre-existing pattern, not touched by this branch.
- **why_out_of_scope:** Function not in the D20/D16/D8 scope. Mirrors several other pre-existing pattern inconsistencies (the `wraps with context` discipline is consistent everywhere except this one helper). Worth fixing but not blocking pre-M04.
- **proposed_followup:** Sweep with the next `db.go` touch (likely the M04 cluster-prop work or the tooling-consolidation milestone in PIPELINE.md backlog).

### R1-D6 — Atomic-commit hygiene: ccfa6c3b bundled 4 logical changes (SP3)
- **status:** active (informational — cannot fix retroactively)
- **severity:** low (process)
- **raised by:** superpowers:code-reviewer (round 1)
- **scope_boundary:** Commit ccfa6c3b wired observability across cascade_cache.go + handler.go + main.go + a test in one commit. Per project standard "Commit after each green test. Small, atomic commits." this should have been split into cache-load + per-request + CLI-flag + test commits.
- **why_out_of_scope:** Rewriting branch history to split the commit would require force-push and lose review trail. Lesson is captured: future observability-wiring lands per-surface.
- **proposed_followup:** None — recorded for future branches.

### R1-D7 — Startup log ordering: cascade_cache_load_* records emit before "Metaforge API starting" banner (ST6)
- **status:** active
- **severity:** cosmetic
- **raised by:** standards reviewer (round 1)
- **scope_boundary:** `api/cmd/metaforge/main.go` — `observe.Init` and `NewHandlerWithCascade` run before the `slog.Info("Metaforge API starting", ...)` line, so operators reading logs top-down see timing records before the start-up banner.
- **why_out_of_scope:** Pure log ordering, no functional impact. The fix is a one-line move of the banner above NewHandlerWithCascade, but the banner currently includes the resolved `--cascade-timing` flag value (set by `flag.Parse`) so moving requires careful re-ordering and isn't worth a dedicated commit pre-M04.
- **proposed_followup:** Fold into the next `cmd/metaforge/main.go` touch (likely the M04 ANN-index startup wiring).

### R4-D1 — handler.go cache-divergence Error log unbounded (R4-S3)
- **status:** active
- **severity:** low
- **raised by:** pr-review-toolkit:silent-failure-hunter (round 4)
- **scope_boundary:** `api/internal/handler/handler.go:325-328` — `slog.Error("cascade candidate concreteness missing from cache despite SQL filter", ...)` fires once per affected candidate with no per-request cap. If the in-memory cache went stale across the dataset (DB rewritten under a running process), a single request could emit hundreds of identical Error records. Asymmetric vs the db.go-side malformed-blob throttle (capped at `malformedLogCap`).
- **why_out_of_scope:** Same shape as R1-D4 (`handleSuggestCascade` log-and-continue on cascade anomalies). The canonical fix is a per-request observer that consolidates these anomaly counts and surfaces them as a tag on the `cascade_request_total` timing record rather than as N separate slog.Error calls. Both R4-D1 and R1-D4 want the same per-request anomaly aggregator; should land together.
- **proposed_followup:** Fold into the cascade-observability follow-up alongside R1-D4 — replace per-candidate slog.Error patterns with a per-request anomaly aggregator that emits at request close.

### R4-D2 — Atomic-commit hygiene: 218fad1d repeats the R1-D6 bundling pattern (R4-ST4)
- **status:** active (informational — recurring pattern)
- **severity:** low (process)
- **raised by:** standards reviewer (round 4)
- **scope_boundary:** Commit 218fad1d bundled three logically independent fixes (R3-S1 empty-branch test + R3-S2 cap widening + R3-S3 outcome enum branching) into one commit. Per project standard "Commit after each green test. Small, atomic commits. Never batch up changes" each should have been its own commit. This is the same pattern R1-D6 captured for ccfa6c3b — the lesson is not transferring across rounds.
- **why_out_of_scope:** Cannot fix retroactively without force-push (same rationale as R1-D6). Recording so the pattern is visible.
- **proposed_followup:** None — informational, but worth flagging for future review-loop fix dispatches that each finding's fix lands as its own commit.

### R2-D1 — handleSuggestLegacy silent domainDist=0 when sourceEmb absent (R2-S4)
- **status:** active
- **severity:** low
- **raised by:** pr-review-toolkit:silent-failure-hunter (round 2)
- **scope_boundary:** `api/internal/handler/handler.go:194-199` (legacy path). When `GetLemmaEmbedding` returns `(nil, nil)` for a benign-absence case (lemma row exists but no embedding row), every candidate falls through to `domainDist=0` and the response returns 200 with silently-degraded CompositeScore. No log breadcrumb at request time. The cascade path drops such candidates with `CascadeStatusNoProperties` which is at least visible in the response shape; the legacy path leaves no signal.
- **why_out_of_scope:** Pre-existing legacy behaviour — not introduced by D20/D16/D8. The (nil, nil) contract for `GetLemmaEmbedding` is an explicit design choice (benign absence ≠ error) and predates this branch. The remedy is either a debug-level log or a response-level flag — both are M04-friendly changes (M04's broader candidate set will surface this more often). Folding into M04 keeps the legacy path stable until cascade goes default.
- **proposed_followup:** Land with M04 ANN-candidate work — by then the cascade path will be the default and the legacy path may be retired or held to the same domainDist-signal discipline as cascade.

---

## Round 1 — pr-review-toolkit (2026-05-22T22:00:00Z)

**Agents dispatched:** code-reviewer, silent-failure-hunter, type-design-analyzer (in parallel)

### Items Found

- **code-reviewer:** zero findings — `CLEAN: true` after walking error-handling, CTE-tripwire, observability NO-OP contract, perf, idempotency, TDD trail, SQL correctness, API contract, fixture realism, comment discipline.
- **silent-failure-hunter:** 5 findings —
  - [important] **SF1** — `GetLemmaEmbeddingsBatch` swallows per-row Scan errors with `slog.Warn` + continue (`db.go:425-428`). D8 hardens the call site; the underlying helper still hides structural drift. **Decision: fix.**
  - [important] **SF2** — `GetLemmaEmbedding` silently returns nil for malformed/wrong-dim BLOB (`db.go:391`). The (nil, nil) absence contract was overstated by the D8 commit narrative — malformed is not benign. **Decision: fix.**
  - [low] **SF3** — `handleSuggestCascade` logs Error + continues when batch properties is empty for all candidates. Pre-existing S05 design decision, the Error-level log is signal enough. **Decision: defer as R1-D4.**
  - [low] **SF4** — `GetLemmaForSynset` returns raw err without wrapping. Pre-existing, untouched function. **Decision: defer as R1-D5.**
  - [cosmetic] **SF5** — no `cascade_response_encode` stage timer; encode time only shows up as a gap in `request_total − sum(stage timers)`. **Decision: fix.**
- **type-design-analyzer:** 4 findings, all `low`:
  - **TD1** — `observe.Start` variadic call sites allocate even on disabled path. **Decision: defer as R1-D1 (architectural).**
  - **TD2** — test bypasses NewHandlerWithCascade with direct `&Handler{...}` construction. **Decision: defer as R1-D2 (architectural).**
  - **TD3** — `observe.enabled` global flag will race with parallel tests. **Decision: defer as R1-D3 (architectural).**
  - **TD4** — `CascadeCache` "read-only by convention" maps; concurs with D3 from the prior log. **Decision: concur with prior D3 (already anchored in PIPELINE.md against the `metaphor` package extraction).**

### Critique Sections
- **code-reviewer:** `prior_reviewer: "N/A — first round"`, `fixes_reviewed: []` (first round), `ledger_size: 0`. Categories walked: concurrency, error handling, CTE regression tripwire, Observability standard, performance, idempotency, TDD, SQL correctness, API contract, test-fixture realism, comment accuracy. Marked CLEAN after thorough Pass 1.
- **silent-failure-hunter:** `prior_reviewer: "N/A — first round"`, `fixes_reviewed: []`, `ledger_size: 0`. Categories: swallowed errors, scan-error suppression, nil-on-miss map lookups, log-and-continue patterns, defer-error suppression, silent fallbacks, ignored Write returns, malformed-blob handling.
- **type-design-analyzer:** `prior_reviewer: "N/A — first round"`. Cross-referenced 2026-05-21 prior-log deferrals against current code (D1/D3/D4/D5/D14 unchanged). `fixes_reviewed:` all 5 commits with per-fix correct=yes/partial. `ledger_size: 0`. Categories: tagged-union shape (D1), encapsulation (D3), Match struct (D4), nil-cache defence (D5), constrained-type discipline (D2), pointer-discipline contract (TD1 legacy), CTE distinct-on-target invariant.

### Fixes Applied
- **adcdeef5** — SF1 + SF2 + ST4. Escalate Scan + malformed-blob in db.go embedding helpers; document lemmas(synset_id) index gap in D16 subquery comment. Pinned by `TestGetLemmaEmbeddingsBatch_RealDBErrorEscalates` and `TestGetLemmaEmbedding_MalformedBlobEscalates`.
- **1006b1af** — ST1 + SP1 + SP5 + SF5. Drop unused `observe.Enabled()`; align timer doc with both manual + defer patterns; pin all three cache_load labels in the timing test; add `cascade_response_encode` stage timer.
- **3d512c41** — SP2 comment cleanup in cascade_cache.go.

### Files Modified
- `api/internal/db/db.go`
- `api/internal/db/db_test.go`
- `api/internal/observe/timer.go`
- `api/internal/handler/handler.go`
- `api/internal/handler/handler_cascade_test.go`
- `api/internal/db/cascade_cache.go`

### Test Results
Full Go suite green: 7 packages PASS (`blobconv`, `db`, `embeddings`, `forge`, `handler`, `observe`, `thesaurus`). Total CPU time ~95s on first run; mostly cached on rerun.

### Cumulative Status
Total rounds: 1 | Items resolved: 5 (SF1, SF2, SF5, ST4, plus ST1+SP1+SP5+SP2 in two grouped commits) | Active deferrals: 7 (R1-D1..R1-D7) | Superseded deferrals: 0 | Elapsed: ~30m

`last_reviewer_pre_fix_sha = ee34b9ac`

## Round 1 — superpowers (2026-05-22T22:00:00Z)

5 findings — SP1 (timer doc/defer drift), SP2 (misleading malformed-BLOB comment), SP3 (atomic-commit hygiene on ccfa6c3b), SP4 (closure escape on disabled path — duplicate of TD1), SP5 (cache_load labels not asserted). **Decisions:** SP1 + SP2 + SP5 fixed (commits 1006b1af, 3d512c41). SP4 deferred as R1-D1 (duplicate). SP3 deferred as R1-D6 (informational, cannot fix retroactively).

`PRIOR_FINDINGS_CRITIQUE`: prior_reviewer N/A first round; categories TDD trail, commit atomicity, perf/allocation on observe.Start hot path, error-handling completeness, thread safety, observability standard compliance, SQL correctness, test coverage, doc accuracy, PIPELINE.md anchoring.
`APPLIED_FIXES_CRITIQUE`: all 5 commits read end-to-end; per-fix verdicts captured in the per-finding decisions above.
`DEFERRAL_LEDGER_REVIEW`: ledger_size 0 ("ledger empty"). Returned `CLEAN: false`.

## Round 1 — standards (2026-05-22T22:00:00Z)

**Standards sources:** `/home/agent/.claude/CLAUDE.md` · `/home/agent/projects/metaforge/CLAUDE.md`

### Standards Checked
- TDD (Red/Green) — gap on D8 candidate-batch path → ST2 fix via unit tests SF1+SF2
- Algorithms / OOM risk — D16 correlated subquery index gap → ST4 (documented in commit adcdeef5)
- All Errors/Exceptions Handled — D8 closure complete after SF1+SF2 fixes
- Idempotency — LoadCascadeCache is idempotent; no batch-state regressions
- Observability — D20 satisfies the standard; ST3 mutable-global flagged → R1-D3
- Coding Style — ST1 YAGNI on `observe.Enabled()` fixed; ST5 mutable-global → R1-D3 (duplicate); UK spelling clean
- Frequent Commits — ST6 ordering noted → R1-D7

6 findings: ST1 (fixed), ST2 (fixed via SF1+SF2 unit pins — the chain through GetLemmaEmbeddingsBatch is now pinned), ST3 (deferred R1-D3), ST4 (fixed by doc-comment), ST5 (deferred R1-D3 duplicate), ST6 (deferred R1-D7). Returned `CLEAN: false`.

`PRIOR_FINDINGS_CRITIQUE`: prior_reviewer N/A first round; all 7 project standards walked individually.
`APPLIED_FIXES_CRITIQUE`: all 5 commits walked against each standard; D8 partial (TDD gap closed by SF1+SF2 unit pins), D16 partial (index-gap doc landed in same commit), D20 partial (alloc nuance + global flag), PIPELINE anchor clean.
`DEFERRAL_LEDGER_REVIEW`: ledger_size 0 ("ledger empty").

## Round 1 — ux-designer (2026-05-22T22:00:00Z)

**No-op** — no UI files in scope (10 changed files are all Go backend or markdown). Per the ux-designer adapter's scope-detection rule, no subagent dispatched. Counts as adapter-CLEAN for halt purposes.

Files in scope checked: `*.go`, `*.md` only — no `*.html`, `*.css`, `*.scss`, `*.jsx`, `*.tsx`, `*.vue`, `*.svelte`, no `components/` / `pages/` / `views/` / `templates/` paths.

---

### Round 1 — Severity Assessment & Stop Nudge

Items fixed this round (by severity):
- 2 important (SF1, SF2) — silent-failure hardening in db embedding helpers
- 6 low (ST1, ST4, SP1, SP5, SF5, SP2) — observability polish + comment + test pins
- 0 critical / cosmetic

Cumulative: round 1 fixed 8 items; 7 active deferrals (4 architectural → metaphor-package extraction; 2 process/cosmetic; 1 pre-existing).

Stop nudge: N/A — trend not yet established (single round).


## Round 2 — pr-review-toolkit (2026-05-22T22:45:00Z)

**Agents dispatched:** code-reviewer, silent-failure-hunter, type-design-analyzer (in parallel)

### Items Found

- **code-reviewer** (3 findings, CLEAN: false):
  - [important] **R2-P1** — `TestGetLemmaEmbeddingsBatch_RealDBErrorEscalates` does not actually pin SF1's Scan-error branch. The wrong-column-shape table makes `db.Query` fail before `rows.Next()` is reached, so the test exercises a pre-existing escalation path and the SF1 per-row Scan branch (and the new SF2 malformed-tally branch) is unpinned. **Decision: fix.**
  - [low] **R2-P2** — `GetLemmaEmbeddingsBatch` malformed-tally drops correctly-formed rows on partial corruption; loop comment ("Don't drop the whole batch") contradicts function-level effect (one bad blob → 500). **Decision: fix via doc clarification (strict-fail-by-design is the intended policy; comment + godoc tightened to match).**
  - [low] **R2-P3** — `cascade_response_encode` timer asymmetric across the two encode call sites (scored vs empty_no_gate_pass). **Decision: fix.**
- **silent-failure-hunter** (4 findings, CLEAN: false):
  - [cosmetic] **R2-S1** — timer.go doc says "≤5 stages" but the encode timer adds a 6th. **Decision: fix.**
  - [cosmetic] **R2-S2** — SF2 fix-comment claims "parallel to cascade_cache.go" but the actual policy is asymmetric (per-request escalate immediately vs loader-side log+continue+aggregate). **Decision: fix via comment clarification.**
  - [low] **R2-S3** — `GetLemmaEmbeddingsBatch` per-row malformed-blob log can flood alerts if the table is fully corrupted (bounded at ≤200 per request). **Decision: fix — log first occurrence at Error, count silently, aggregate in post-loop error.**
  - [low] **R2-S4** — `handleSuggestLegacy` silently degrades to `domainDist=0` when `sourceEmb == nil` (benign-absence case). Pre-existing behaviour, not introduced by this branch's commits. **Decision: defer as R2-D1.**
- **type-design-analyzer** (3 findings, CLEAN: false):
  - [low] **R2-T1** — encode-stage timer missing on empty-candidates branch (duplicate of R2-P3). **Decision: fix (deduplicated).**
  - [low] **R2-T2** — `GetLemmaEmbeddingsBatch` doc-comment doesn't explicitly document the (nil, err) discard-partial-map contract. **Decision: fix via godoc clarification.**
  - [cosmetic] **R2-T3** — observe.Start doc updated in round 1 acknowledges variadic-slice cost but omits the per-call closure construction. **Decision: fix (folded into timer.go doc update).**
- **superpowers** (CLEAN: true) — no own findings; concurred with all 7 active deferrals (R1-D1..R1-D7).
- **standards** (CLEAN: true) — no own findings; concurred with all 7 active deferrals.

### Critique Sections
- **code-reviewer:** `prior_reviewer:` all 5 round-1 reviewers; `categories_checked:` TDD trail, error escalation, CTE tripwire, NO-OP contract, SQL correctness, fixture realism, malformed-blob handling, partial-batch semantics, atomic.Bool, comment-vs-behaviour consistency. `fixes_reviewed:` all 3 round-1 fix commits + round-1 log commit; per-fix verdicts captured above. `ledger_size: 7`; all 7 concurred.
- **silent-failure-hunter:** Walked 9 categories including scan-error, malformed-BLOB, log-and-continue, log-flood risk, silent fallback, partial-state observability. `fixes_reviewed:` all 4 commits with evidence (BlobToFloats nil contract, EmbeddingDim=300 byte arithmetic, encode-timer placement). `ledger_size: 7`; all 7 concurred.
- **type-design-analyzer:** Categories include tagged-union shape, encapsulation, pointer-discipline, constructor invariant bypass, variadic-API hot-path, global-flag concurrency, error-contract shape. `fixes_reviewed:` all 4 commits with EmbeddingDim contract verification + closure-allocation cross-check. `ledger_size: 7`; all 7 concurred.
- **superpowers:** Categories include TDD trail, atomic-commit hygiene, Algorithms/perf, R1-D1/D2/D3 anchor re-validation, observe.Enabled() removal sweep. `fixes_reviewed:` all 4 commits, all `correct: yes`. `ledger_size: 7`; 7/7 concurred.
- **standards:** All 7 standards walked individually against the round-1 fix diff. `fixes_reviewed:` all 4 commits per-standard; all 4 `correct: yes` with no new drift. `ledger_size: 7`; 7/7 concurred.

### Fixes Applied
- **c59b673e** — R2-P1 + R2-P2 + R2-S2 + R2-S3 + R2-T2. Rename `TestGetLemmaEmbeddingsBatch_RealDBErrorEscalates` → `_QueryFaultEscalates`; add `TestGetLemmaEmbeddingsBatch_MalformedBlobEscalates` that DOES exercise the SF2 post-loop tally branch. Tighten function godoc on the (nil, err) discard contract. Acknowledge the per-request vs loader-side asymmetry in the SF2 fix comment. Throttle per-row malformed log to first occurrence.
- **e793e168** — R2-P3 + R2-T1 + R2-S1 + R2-T3. Add encode timer to empty-candidates branch (symmetric coverage). Update timer.go doc: "≤5 stages" → "≤6"; add explicit note on closure-construction cost on the disabled path.

### Files Modified
- `api/internal/db/db.go`
- `api/internal/db/db_test.go`
- `api/internal/handler/handler.go`
- `api/internal/observe/timer.go`

### Test Results
Full Go suite green: 7 packages PASS. New `TestGetLemmaEmbeddingsBatch_MalformedBlobEscalates` verified red-then-green (insert 4-byte blob → SF2 escalation fires).

### Cumulative Status
Total rounds: 2 | Items resolved: 14 (R1: 8, R2: 6) | Active deferrals: 8 (R1-D1..R1-D7 + R2-D1) | Superseded/closed deferrals: 0 | Elapsed: ~75m

`last_reviewer_pre_fix_sha = 5f20ef84`

## Round 2 — superpowers (2026-05-22T22:45:00Z)

**CLEAN: true.** 0 own findings after walking all four passes. `categories_checked:` TDD trail / atomic-commit hygiene / Algorithms-perf / R1-D1/D2/D3 anchor re-validation / observe.Enabled removal sweep / startup ordering. `fixes_reviewed:` all 4 round-1 commits — all `correct: yes` with evidence (file:line re-reads, test reruns). `DEFERRAL_LEDGER_REVIEW.summary:` "all 7 concurred".

## Round 2 — standards (2026-05-22T22:45:00Z)

**Standards sources:** `/home/agent/.claude/CLAUDE.md` · `/home/agent/projects/metaforge/CLAUDE.md`

**CLEAN: true.** Walked all 7 standards individually against the round-1 fix diff; no new drift. `fixes_reviewed:` all 4 commits with explicit per-fix per-standard evidence — TDD red-then-green trail verified; Algorithms/OOM via the documented index gap; All-Errors-Handled via the malformed-blob escalation and aggregate error contract; Idempotency preserved; Observability NO-OP contract honestly documented; Coding-style (YAGNI on Enabled() removal); Frequent-Commits acceptable per atomic intent. `DEFERRAL_LEDGER_REVIEW:` 7/7 concur — all entries have substantive scope_boundary + why_out_of_scope.

## Round 2 — ux-designer (2026-05-22T22:45:00Z)

**No-op** — still no UI files in scope (round-2 fixes touched the same 4 Go files as round-1; no new file types added). Counts as adapter-CLEAN for halt purposes per the scope-detection rule.

---

### Round 2 — Severity Assessment & Stop Nudge

Items fixed this round (by severity):
- 1 important (R2-P1 — TDD test-coverage gap on SF1/SF2 batch branches)
- 4 low (R2-P2, R2-P3/R2-T1, R2-S3, R2-T2)
- 3 cosmetic (R2-S1, R2-S2, R2-T3)

Cumulative: round 1 fixed 8, round 2 fixed 6; 8 active deferrals (1 new pre-existing R2-D1).

Trend: severities decreasing (round 1 had 2 important, round 2 has 1 important on test coverage rather than code-fault). Two adapters (superpowers + standards) returned CLEAN this round — the loop is converging.

Stop nudge: not yet — pr-review-toolkit's three sub-agents all found new items, so the round-1 fixes triggered real (if low-severity) follow-on concerns. One more round to confirm convergence on the four-section critique pass.


## Round 3 — pr-review-toolkit (2026-05-22T23:30:00Z)

**Agents dispatched:** code-reviewer, silent-failure-hunter, type-design-analyzer (in parallel)

### Items Found

- **code-reviewer:** CLEAN — zero own findings; concurred with all 8 active deferrals (R1-D1..R1-D7, R2-D1). Categories: TDD trail, error escalation, NO-OP contract, encode-timer symmetry/ordering, malformed-blob handling, godoc accuracy.
- **silent-failure-hunter:** 3 findings (CLEAN: false):
  - [low] **R3-S1** — empty-branch `cascade_response_encode` timer added in e793e168 has no test pinning it; existing TimingEnabled test only exercises scored path ('anger'). **Decision: fix.**
  - [low] **R3-S2** — malformed-blob log throttle (first occurrence only) loses lemma identifiers for rows 2..N on partial corruption. **Decision: fix — widen cap to `malformedLogCap = 10` with occurrence index in the log.**
  - [low] **R3-S3** — `cascade_request_total` records `outcome="scored"` / `"empty_no_gate_pass"` even when `json.NewEncoder.Encode` fails (client disconnect, write error). Pre-existing pattern, but R2 work touched the site. **Decision: fix — branch outcome enum to `scored_encode_error` / `empty_encode_error` when encodeErr != nil.**
- **type-design-analyzer:** CLEAN — zero own findings; concurred with all 8 active deferrals.
- **superpowers:** 3 findings (CLEAN: false):
  - [cosmetic] **R3-OWN-1** — duplicate of R3-S1 (TDD gap on empty-branch encode timer). **Decision: fix via the R3-S1 test addition.**
  - [cosmetic] **R3-OWN-2** — e793e168 commit message under-states the `stopTotal` ordering normalisation on the empty branch (was before encode block, now after). **Decision: skip — informational; can't retroactively edit commit messages without force-push.**
  - [low informational] **R3-OWN-3** — R1-D1's rationale "~6 variadic slice allocations" is now stale after round 2's timer.go doc enumerated both closure-literal escape AND variadic-slice costs. **Decision: fix — update R1-D1 wording.**
- **standards:** CLEAN — zero own findings; concurred with all 8 active deferrals. All 7 standards walked individually against the round-2 fix diff.
- **ux-designer:** No-op — still no UI files in scope. Counts as adapter-CLEAN for halt purposes.

### Critique Sections
- **code-reviewer:** categories include test discipline, encode-timer placement, godoc accuracy, throttle correctness. Per-fix evidence cites `go test -run TestGetLemmaEmbeddingsBatch -v` output and code-reading of both encode call sites. `DEFERRAL_LEDGER_REVIEW:` 8/8 concur with per-entry engagement (verified e793e168 didn't change R1-D1 anchor; verified handler_legacy_embedding_error_test.go unchanged for R1-D2; etc.).
- **silent-failure-hunter:** categories include scan-error escalation, log-flood throttle, encode-error outcome attribution, TDD coverage of new instrumentation. `DEFERRAL_LEDGER_REVIEW:` 8/8 concur — mild challenge note on R2-D1 that a `slog.Debug` could land sooner without M04 dependency, but deferring is defensible.
- **type-design-analyzer:** categories include error-contract shape, asymmetric-policy documentation, NO-OP-contract honesty, encode-timer symmetry, godoc-vs-comment discipline. `DEFERRAL_LEDGER_REVIEW:` 8/8 concur with explicit verification that round-2 fixes didn't pull territory into scope.
- **superpowers:** categories include TDD discipline symmetry, semantic-change documentation in commit messages, deferral-rationale freshness. `DEFERRAL_LEDGER_REVIEW:` 8/8 concur with explicit note on R1-D1 cost-envelope drift (raised as R3-OWN-3).
- **standards:** Standards-checked all 7 individually per file (TDD, Algorithms, Frequent Commits, All Errors, Idempotency, Observability, Coding Style); cross-checked `GetLemmaForSynset` line 495 still returns bare err (R1-D5 still accurate); `_QueryFaultEscalates` rename comment + `_MalformedBlobEscalates` test both walked. `DEFERRAL_LEDGER_REVIEW:` 8/8 concur.

### Fixes Applied
- **218fad1d** — R3-S1 + R3-S2 + R3-S3. Branch `outcome` on encode error in both cascade response paths; widen malformed-blob log cap to 10 with occurrence index; add `TestCascadeRequest_TimingEnabled_EmptyNoGatePass_EmitsEncodeStage` using 'cat' fixture.
- **R3-OWN-3 ledger update** — R1-D1 rationale extended to mention closure-literal cost alongside variadic-slice cost (applied inline in this commit's review-log update).
- **R3-OWN-2 skipped** — informational only; commit message cannot be retroactively edited without force-push.

### Files Modified
- `api/internal/db/db.go`
- `api/internal/handler/handler.go`
- `api/internal/handler/handler_cascade_test.go`
- `docs/superpowers/review-logs/2026-05-22-m03-pre-m04-deferrals-review.md`

### Test Results
Full Go suite green: 7 packages PASS. New `TestCascadeRequest_TimingEnabled_EmptyNoGatePass_EmitsEncodeStage` passes against 'cat' fixture.

### Cumulative Status
Total rounds: 3 | Items resolved: 17 (R1: 8, R2: 6, R3: 3) | Active deferrals: 8 (R1-D1..R1-D7 + R2-D1, with R1-D1 rationale extended) | Superseded/closed deferrals: 0 | Elapsed: ~110m

`last_reviewer_pre_fix_sha = fcb11b85`

## Round 3 — superpowers (2026-05-22T23:30:00Z)

3 own findings (R3-OWN-1, R3-OWN-2, R3-OWN-3) — R3-OWN-1 fixed via R3-S1 test; R3-OWN-2 skipped (informational); R3-OWN-3 fixed via ledger rationale update. `DEFERRAL_LEDGER_REVIEW:` 8/8 concur. Returned `CLEAN: false`.

## Round 3 — standards (2026-05-22T23:30:00Z)

**Standards sources:** `/home/agent/.claude/CLAUDE.md` · `/home/agent/projects/metaforge/CLAUDE.md`

**CLEAN: true.** Walked all 7 standards individually against round-2 fix diff; no new drift. `fixes_reviewed:` all 3 round-2 commits per-standard; all `correct: yes`. `DEFERRAL_LEDGER_REVIEW:` 8/8 concur.

## Round 3 — ux-designer (2026-05-22T23:30:00Z)

**No-op** — no UI files in scope (round-2 + round-3 fixes touched only Go backend + docs). Counts as adapter-CLEAN.

---

### Round 3 — Severity Assessment & Stop Nudge

Items fixed this round (by severity):
- 3 low (R3-S1/R3-OWN-1, R3-S2, R3-S3)
- 1 low informational (R3-OWN-3 — ledger rationale)
- 0 important / critical / cosmetic

Cumulative: round 1 fixed 8, round 2 fixed 6, round 3 fixed 4; 8 active deferrals (1 new R2-D1, rest from round 1).

Trend: severities decreasing (round 1: 2 important; round 2: 1 important; round 3: 0 important). 3 of 5 adapters CLEAN this round.

**Stop nudge: APPROACHING.** Last 2 rounds all low/cosmetic. One more round expected to confirm convergence on the four-section critique pass.


## Round 4 — pr-review-toolkit (2026-05-22T23:30:00Z)

**Agents dispatched:** code-reviewer, silent-failure-hunter, type-design-analyzer (in parallel)

### Items Found

- **code-reviewer** (1 finding, CLEAN: false):
  - [low] No test for `malformedLogCap = 10` boundary behaviour — existing test inserts a single malformed blob, so the widening from cap=1 to cap=10 is unpinned. **Decision: fix (covered by `TestGetLemmaEmbeddingsBatch_MalformedBlob_LogCapBounded`).**
- **silent-failure-hunter** (3 findings, CLEAN: false):
  - [low] **R4-S1** — empty-branch encode-stage test is fixture-tolerant; doesn't assert outcome="empty_no_gate_pass". **Decision: fix (tightened test).**
  - [cosmetic] **R4-S2** — no marker emitted at cap boundary; if `rows.Err()` short-circuits the post-loop aggregate, the cap event is invisible. **Decision: fix (Warn record at cap transition).**
  - [low] **R4-S3** — handler.go cache-divergence Error log unbounded (asymmetric vs db.go throttle). **Decision: defer as R4-D1 (same shape as R1-D4; should land with the cascade-anomaly aggregator).**
- **type-design-analyzer** (4 findings, agent self-declares CLEAN: true with all items pre-triaged to defer/skip — orchestrator treats per-item):
  - [low] **OWN-T1** — outcome enum is 7 free-form strings; defensible at this scale, fold into Loki/Prometheus integration milestone. **Decision: skip — agent's own recommendation; revisit if a consumer starts parsing.**
  - [low] **OWN-T2** — `malformedLogCap` lives in db package but semantically belongs to observability policy. **Decision: skip — agent's own defer; fold with metaphor-package extraction.**
  - [low] **OWN-T3** — `outcome` local is reassigned (mutability nit). **Decision: skip — cosmetic.**
  - **OWN-T4** — concur with R1-D4. **Decision: noted.**
- **superpowers** (2 findings, CLEAN: false):
  - [important] **R4-OWN-1** — R3-S2 widening to 10 has no failing-test trail. **Decision: fix (covered by `TestGetLemmaEmbeddingsBatch_MalformedBlob_LogCapBounded`).**
  - [important] **R4-OWN-2** — R3-S3 encode-error outcome enums unpinned. **Decision: fix (covered by `TestCascadeRequest_ScoredEncodeError_OutcomeBranches` + `_EmptyEncodeError_OutcomeBranches`).**
- **standards** (4 findings, CLEAN: false):
  - [low] **R4-ST1** — TDD trail on cap widening (duplicate of R4-OWN-1). **Decision: fix (same fix).**
  - [low] **R4-ST2** — TDD trail on outcome enum branching (duplicate of R4-OWN-2). **Decision: fix (same fix).**
  - [low] **R4-ST3** — empty-branch test fixture tolerance (duplicate of R4-S1). **Decision: fix (same fix).**
  - [low process] **R4-ST4** — 218fad1d atomic-commit hygiene repeats R1-D6 pattern. **Decision: defer as R4-D2.**

### Critique Sections
All 5 adapters returned populated four-section responses. The 4 reviewers that returned CLEAN: false converged on the same root concern: round 3 fixed 3 behaviours but only added 1 test, leaving 2 behavioural changes (R3-S2 cap widening, R3-S3 outcome enum) unpinned. Round 4 closes this trail with 3 new tests + the cap-boundary marker.

### Fixes Applied
- **72bd9a0b** — R4-OWN-1 + R4-OWN-2 + R4-ST1 + R4-ST2 + R4-ST3 + R4-S1 + R4-S2 + the code-reviewer's TDD-cap finding. Three new tests (`TestGetLemmaEmbeddingsBatch_MalformedBlob_LogCapBounded`, `TestCascadeRequest_ScoredEncodeError_OutcomeBranches`, `TestCascadeRequest_EmptyEncodeError_OutcomeBranches`); tightened empty-branch encode-stage test assertion; added cap-boundary Warn marker.

### Files Modified
- `api/internal/db/db.go`
- `api/internal/db/db_test.go`
- `api/internal/handler/handler_cascade_test.go`

### Test Results
Full Go suite green: 7 packages PASS. Five cascade-timing tests + two malformed-blob batch tests + new cap-boundary test all PASS individually.

### Cumulative Status
Total rounds: 4 | Items resolved: 22 (R1: 8, R2: 6, R3: 4, R4: 4) | Active deferrals: 10 (R1-D1..R1-D7 + R2-D1 + R4-D1 + R4-D2) | Superseded/closed deferrals: 0 | Elapsed: ~150m

`last_reviewer_pre_fix_sha = 8e89da81`

## Round 4 — superpowers (2026-05-22T23:30:00Z)

2 own findings — R4-OWN-1 (important: TDD gap on cap widening) and R4-OWN-2 (important: TDD gap on encode-error outcome enums). Both fixed by 72bd9a0b. `DEFERRAL_LEDGER_REVIEW:` 8/8 concur (pre-fix ledger size). Returned `CLEAN: false`.

## Round 4 — standards (2026-05-22T23:30:00Z)

**Standards sources:** `/home/agent/.claude/CLAUDE.md` · `/home/agent/projects/metaforge/CLAUDE.md`

4 findings: R4-ST1/2/3 (TDD-trail dupes of pr-review-toolkit + superpowers — fixed); R4-ST4 (process — deferred R4-D2). `DEFERRAL_LEDGER_REVIEW:` 8/8 concur (pre-fix ledger size). Returned `CLEAN: false`.

## Round 4 — ux-designer (2026-05-22T23:30:00Z)

**No-op** — no UI files in scope. Counts as adapter-CLEAN.

---

### Round 4 — Severity Assessment & Stop Nudge

Items fixed this round (by severity):
- 2 important (R4-OWN-1, R4-OWN-2 — TDD trail completeness on R3 fixes)
- 4 low (R4-S1/R4-ST3, R4-S2, R4-ST1, code-reviewer's cap finding)

Cumulative: round 1 fixed 8, round 2 fixed 6, round 3 fixed 4, round 4 fixed 4 (no R3-only count discrepancy after this round).

Trend: 1 adapter CLEAN (type-design with deferred caveats) → 5 adapters with mixed but converging findings on TDD-trail completeness. The round-4 fixes close the last meaningful gap.

**Stop nudge: APPROACHING (round 5 expected to halt).** Last 4 rounds: 2 important, 1 important, 0 important, 2 important (round 4 brought back important via TDD-trail catching missing tests from round 3 — but those are now closed). Round 5 should converge if no new fixes land.


## Round 5 — pr-review-toolkit (2026-05-22T23:55:00Z)

**Agents dispatched:** code-reviewer, silent-failure-hunter, type-design-analyzer (in parallel)

### Items Found

- **code-reviewer:** **CLEAN: true.** Zero own findings; 10/10 deferrals concur with engaged reasoning.
- **silent-failure-hunter:** **CLEAN: true.** Zero own findings. Noted that cap-boundary Warn marker's "fires exactly once" guarantee is structurally provable (`malformed == cap` strict equality on monotonic counter) — below threshold for OWN_FINDINGS. 10/10 deferrals concur.
- **type-design-analyzer:** **CLEAN: true.** Zero own findings. Walked failingWriter type (test-scoped, correct shape for encode-error path), outcome enum at 7 values (still defensible at this scale per OWN-T1 self-defer rationale), `malformedLogCap` constant locality (now load-bearing at 2 sites in db.go — strengthens R1-D1/D3 cluster deferral). 10/10 deferrals concur.
- **superpowers:** **CLEAN: false.** 2 findings:
  - [low] **R5-OWN-1** — Cap-boundary Warn marker added in 72bd9a0b lacks a specific TDD pin. Test exercises the marker at runtime but doesn't assert it fires. **Decision: fix.**
  - [low] **R5-OWN-2** — `TestGetLemmaEmbeddingsBatch_MalformedBlob_LogCapBounded` only asserts the aggregate-count error; would pass under cap=1 or cap=100. **Decision: fix (same change as R5-OWN-1).**
- **standards:** **CLEAN: false.** 1 finding:
  - [low] **R5-ST1** — Same shape as R5-OWN-1 (TDD pin on cap-boundary marker). Reviewer self-recommended defer as R5-D1, but applying the fix in this round closes the trail and prevents a sixth round. **Decision: fix.**

### Critique Sections
- code-reviewer: 6 categories walked (TDD trail on R3+R4 fixes, encode-error symmetry, cap-marker design, fixture tolerance, atomic-commit pattern recurrence, deferral freshness); explicit "no gaps identified" with files re-checked.
- silent-failure-hunter: categories include failingWriter mock semantics, cap-boundary trigger fires-once invariant, atomic-commit recurrence, EmbeddingDim contract. Acknowledges R4-D2 captures the bundling pattern that 72bd9a0b also exhibits (third instance this loop).
- type-design-analyzer: walked outcome enum threshold, malformedLogCap locality reinforcement, failingWriter interface shape (no http.Flusher/Hijacker dependency — cleanly minimal).
- superpowers: critiqued round-4 superpowers' own fix-acceptance — observed that the "important" R4-OWN-1 finding was closed against an assertion that didn't actually pin the cap *value*. Self-critique surfaced R5-OWN-1/R5-OWN-2.
- standards: walked all 7 standards individually against the round-4 diff; noted that the cap-boundary Warn marker is itself instrumentation without a TDD pin — same recursion as the round-3-to-round-4 chain.

### Fixes Applied
- **b1f820cf** — R5-OWN-1 + R5-OWN-2 + R5-ST1. Captures slog output in `TestGetLemmaEmbeddingsBatch_MalformedBlob_LogCapBounded` and asserts (i) exactly `malformedLogCap`=10 Error records emit, (ii) exactly 1 cap-boundary Warn record fires. Closes the TDD trail on the R4-S2 cap-boundary marker.

### Files Modified
- `api/internal/db/db_test.go`

### Test Results
Full Go suite green: 7 packages PASS. Tightened test PASSes with new assertions.

### Cumulative Status
Total rounds: 5 | Items resolved: 25 (R1: 8, R2: 6, R3: 4, R4: 4, R5: 3) | Active deferrals: 10 (R1-D1..R1-D7 + R2-D1 + R4-D1 + R4-D2) | Superseded/closed deferrals: 0 | Elapsed: ~180m

`last_reviewer_pre_fix_sha = 878c3ed7`

## Round 5 — superpowers (2026-05-22T23:55:00Z)

2 own findings (R5-OWN-1, R5-OWN-2 — TDD gaps on cap-boundary marker and cap-value pinning). Both fixed by b1f820cf. `DEFERRAL_LEDGER_REVIEW:` 10/10 concur. Returned `CLEAN: false`.

## Round 5 — standards (2026-05-22T23:55:00Z)

**Standards sources:** `/home/agent/.claude/CLAUDE.md` · `/home/agent/projects/metaforge/CLAUDE.md`

1 own finding (R5-ST1 — TDD gap on cap-boundary marker, duplicate of R5-OWN-1). Fixed by b1f820cf (rather than the self-recommended defer, since the fix is a 3-line slog-buffer assertion and closes the trail in one round). `DEFERRAL_LEDGER_REVIEW:` 10/10 concur. Returned `CLEAN: false`.

## Round 5 — ux-designer (2026-05-22T23:55:00Z)

**No-op** — no UI files in scope. Counts as adapter-CLEAN.

---

### Round 5 — Severity Assessment & Stop Nudge

Items fixed this round (by severity):
- 3 low (R5-OWN-1, R5-OWN-2, R5-ST1 — duplicate TDD-trail gaps on cap-boundary marker)
- 0 important / critical / cosmetic

Cumulative: R1: 8, R2: 6, R3: 4, R4: 4, R5: 3 = 25 items resolved across 5 rounds.

Trend: severity strictly decreasing. Round 5 is the first round with **zero important findings** — all 3 pr-review-toolkit subagents returned CLEAN. The only NOT-CLEAN responses were from superpowers + standards, both converging on the same trivial TDD-trail gap which is now closed.

**Stop nudge: STRONG — halt expected in round 6.** Round 5 closed the recursive TDD-trail loop the previous rounds had been catching. Round 6 should see all 5 adapters return CLEAN.

