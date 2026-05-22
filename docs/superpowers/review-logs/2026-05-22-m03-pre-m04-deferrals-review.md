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

### R1-D1 — Variadic-on-disabled-path allocation in observe.Start (TD1 / SP4 / ST3)
- **status:** active
- **severity:** low (perf)
- **raised by:** pr-review-toolkit:type-design-analyzer, superpowers:code-reviewer, standards reviewer (round 1)
- **scope_boundary:** API-shape change. The clean fix is a two-method API (`Stop()` + `StopWith(extra ...any)`) so callers opt into variadic boxing only on the enabled path; alternatively a typed Timer struct injected through the handler graph.
- **why_out_of_scope:** Per-request impact is bounded at ~6 variadic slice allocations on a path that already pays for slog and json encoding overhead. The architectural fix lands cleanly with the metaphor-package extraction (anchored in PIPELINE.md against D1/D2/D3/D4/D5/D14) where the observe surface can be redesigned alongside CascadeCache encapsulation. Fixing it pre-M04 would either ship a brittle one-package-level-noop trick or thrash the call sites twice.
- **proposed_followup:** Land with the `metaphor` package extraction milestone (between M04 and Bridge per PIPELINE.md). Redesign the observe surface to a typed Timer that callers can construct per-request, removing both the global flag and the variadic-allocation concern.

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

