# M04 Cosine Candidate Generation — Code Review Log

**Branch:** `m04/cosine-candidate-gen`
**Base:** `main`
**Scope:** S01 (embedding generator + enums) + S02 (union + dispatch + CLI) + S03 (anomaly aggregator + tripwire). 21 commits at round entry, +1180 / -41 lines / 14 files.

## Deferrals Ledger

### D1 — CandidateSource zero-value enforcement (constructor discipline)
- **Severity:** low
- **Status:** active
- **Raised by:** type-design-analyzer (TD-OWN-2)
- **scope_boundary:** Type-safety hardening for `db.CascadeCandidate`; both current generators stamp `Source` correctly so the invariant holds today.
- **why_out_of_scope:** Would require either a `NewCascadeCandidate` constructor that all sites route through, or a `Valid()` check in the dispatch path. M04's two generators tag deterministically; the bug is hypothetical until a third generator lands. Fixing now adds refactoring blast radius without closing a real failure.
- **proposed_followup:** When M05 type-aligned scoring lands its own candidate generator, introduce `NewCascadeCandidate(source, ...)` and migrate existing generators.

### D2 — `unionCandidates` Source re-stamping (cosmetic)
- **Severity:** low
- **Status:** active
- **Raised by:** type-design-analyzer (TD-OWN-3); superpowers (M04-CR1-9)
- **scope_boundary:** Single-source-of-truth for the Source tag.
- **why_out_of_scope:** The double-stamp (generator + union) is functionally equivalent today — both assign the same value. Removing one without breaking the other requires a small refactor that's pure rearrangement of where the stamp lives, no behavioural change.
- **proposed_followup:** Stamp ONLY in `unionCandidates`; remove stamping from generators. Land alongside D1 since both touch constructor discipline.

### D3 — `ForgeEmbeddingConfig` duplicates `CascadeConfig` embedding fields
- **Severity:** low
- **Status:** active
- **Raised by:** type-design-analyzer (TD-OWN-4)
- **scope_boundary:** Cross-package config-shape refactor.
- **why_out_of_scope:** The duplication is a 3-field copy at the handler boundary. The justification (layer isolation) is partially valid even if `db` already imports `forge` for `CandidateSource`. A future knob will be forgotten in one of the two places — but until that happens, the explicit copy is fine.
- **proposed_followup:** Either lift `ForgeEmbeddingConfig` into `forge` and embed in `CascadeConfig`, or add `CascadeConfig.EmbeddingBand() ForgeEmbeddingConfig` accessor for the handler copy.

### D4 — Embedding-only candidates get `TierUnlikely` in JSON wire
- **Severity:** important
- **Status:** active
- **Raised by:** type-design-analyzer (TD-OWN-5)
- **scope_boundary:** JSON wire correctness for cascade response — surfaces in frontend rendering, not in scoring.
- **why_out_of_scope:** `ClassifyTierCurated(salienceSum=0, contrast=0)` returns `TierUnlikely`. Embedding-only rows have zero salience by construction, so every embedding-only candidate is JSON-emitted with `"tier": "unlikely"` regardless of `final_score`. This is real wire incorrectness — a UI that filters by tier will hide all embedding-only candidates. M04 currently has no frontend consumer wiring up the cascade tier field; the M03 forge UI uses CompositeScore tier (legacy path). Will surface as a real bug when the cascade frontend lands (currently parked).
- **proposed_followup:** Either skip `ClassifyTierCurated` for `SourceEmbedding` rows and emit empty `TierName` (preferred — semantic honesty), OR design an embedding-tier classifier keyed on cosine distance / re-rank bonus.

### D5 — Cluster-wins-on-conflict drops embedding-path topic synset
- **Severity:** important
- **Status:** active
- **Raised by:** superpowers (M04-CR1-10)
- **scope_boundary:** Semantic correctness on dual-path candidate hits in union mode.
- **why_out_of_scope:** When the same synset appears via both paths, the cluster row's payload (including `SourceSynsetID`) wins. The embedding path qualified the candidate against a different topic synset (the primary-curated-sense pick), and that sense is silently discarded. Whether this is "right" depends on which sense the user meant. Resolving requires either type-aligned scoring (M05) or a co-generation bonus that keeps both sense choices around. Cluster-wins is the M04-spec-prescribed behaviour; this deferral records the limitation.
- **proposed_followup:** M05 type-aligned work should revisit. Or land a `SourceBoth`-keyed dual-distance computation that keeps the smaller cosine.

### D6 — Embedding primary-sense resolver differs from cluster-path CTE
- **Severity:** low
- **Status:** active (acknowledged in cascade_embedding.go doc comment)
- **Raised by:** superpowers (M04-CR1-4)
- **scope_boundary:** Multi-sense ANN candidate generation — already documented in `resolvePrimaryCuratedSynset` doc comment as intentional v1 narrowing.
- **why_out_of_scope:** The asymmetry (cluster iterates ALL senses; embedding scans neighbours of ONE primary sense) is by design for M04 v1. M04 v2 is "multi-sense ANN" per the PIPELINE backlog.
- **proposed_followup:** PIPELINE M04 v2 backlog entry covers this.

### D7 — `getSynsetRow` NullString for defensive lemma scan
- **Severity:** low
- **Status:** active
- **Raised by:** superpowers (M04-CR1-8)
- **scope_boundary:** Defensive guard against pipeline contract violation (synset row exists with empty lemmas).
- **why_out_of_scope:** The pipeline contract guarantees every enriched synset has at least one lemma row. Pre-existing assumption in cluster path's `cascade.go:144` (uses the same `(SELECT lemma FROM lemmas …)` subquery without NullString). Hardening one without the other is asymmetric churn.
- **proposed_followup:** If pipeline ever surfaces a no-lemmas case, add NullString in both call sites at once.

### D8 — Centroid loader malformed-row log volume
- **Severity:** low
- **Status:** active
- **Raised by:** superpowers (M04-CR1-12)
- **scope_boundary:** Startup observability; pre-existing in `cascade_cache.go`.
- **why_out_of_scope:** Not modified by M04. The aggregator on the loader (`malformed_count` log line) already provides a summary; sampling per-row Errors is a refinement, not a regression.
- **proposed_followup:** Wider observability sweep before M05.

### D9 — `err == sql.ErrNoRows` direct comparison
- **Severity:** cosmetic
- **Status:** active
- **Raised by:** silent-failure-hunter (#8)
- **scope_boundary:** Defensive Go idiom — `errors.Is` is the modern recommendation, direct comparison works today.
- **why_out_of_scope:** The cluster path uses a substring match (different idiom) and a refactor would touch both. Cosmetic only — driver wrapping is not introduced anywhere in the codebase.
- **proposed_followup:** Bundle with #D10 in a single "DB error handling discipline" sweep.

### D10 — Substring SQL error text match in `cascade.go`
- **Severity:** low
- **Status:** active (pre-existing)
- **Raised by:** silent-failure-hunter (#9)
- **scope_boundary:** Pre-existing in `GetForgeCascadeCandidatesByLemma`; not introduced by M04.
- **why_out_of_scope:** The "no such table" substring depends on go-sqlite3 driver text being stable. Not a new bug. Replacing with a startup-time table-existence probe is a wider DB-layer refactor.
- **proposed_followup:** Bundle with D9.

### D11 — `CandidateSources` / `CandidateSource` naming collision
- **Severity:** cosmetic
- **Status:** active
- **Raised by:** type-design-analyzer (TD-OWN-7)
- **scope_boundary:** Naming readability — singular/plural distinction is visually fragile.
- **why_out_of_scope:** Renaming to `CandidateMode` / `ModeCluster` etc. would touch every call site in db, forge, handler, main, tests — wide blast radius for a cosmetic win. The Go compiler catches the only realistic confusion (passing `CandidateSource` where `CandidateSources` is expected).
- **proposed_followup:** Land before M05 type-aligned work to avoid compounding the type vocabulary.

### D12 — `forge.Match.Source` JSON tag collides with `SuggestResponse.Source`
- **Severity:** low
- **Status:** active
- **Raised by:** type-design-analyzer (TD-OWN-6)
- **scope_boundary:** JSON wire format — clients reading `response.source` vs `response.suggestions[i].source` see two different vocabularies under the same key name.
- **why_out_of_scope:** Wire-format change. No cascade-mode JSON consumer is yet wired up (M04 frontend parked); landing the rename now is free, but breaking established field naming patterns warrants a wider discussion.
- **proposed_followup:** Rename `Match.Source` JSON tag to `"candidate_source"` when the cascade frontend lands.

### D13 — Old-SQLite-build IN-clause variable limit (≤3.31 ships 999)
- **Severity:** low
- **Status:** active
- **Raised by:** orchestrator (during Fix E follow-up)
- **scope_boundary:** Cross-platform safety for `getSynsetRowsBatch` on old SQLite builds.
- **why_out_of_scope:** `EmbeddingTopKCeiling = 10000` works on SQLite ≥ 3.32 (mainstream 2020+ builds). Old builds (≤ 3.31) would fail with "too many SQL variables" — but the project deploys against modern Debian/Vultr and the historical ceiling is documented in the new `EmbeddingTopKCeiling` comment.
- **proposed_followup:** Chunk the IN-clause inside `getSynsetRowsBatch` when `len(ids) > 999`. Lands as part of M04 v2 backlog (multi-sense ANN already requires touching this function).

### D14 — Production cascade latency at ~487ms (close to 500ms p99 target)
- **Severity:** important
- **Status:** active (re-measure after Fix D)
- **Raised by:** superpowers (M04-CR1-6); pr-rt code-reviewer (#2)
- **scope_boundary:** Hot-path performance budget.
- **why_out_of_scope:** Fix D (precomputed topic norm) lands an estimated ~250-300ms saving by eliminating the per-iteration sqrt + sum-of-squares. The latency re-measurement happens in the calibration sweep (Task 20) — the sweep verdict will report production-realistic p99 numbers across (DMin, DMax) settings. If post-fix latency still exceeds 500ms p99, escalate to M05 hot-path optimisation (heap top-K, SIMD inner product, or ANN index).
- **proposed_followup:** Calibration sweep (Task 20) measures actual p99. If > 500ms, file M04.5 perf milestone.

---

## Round 1 — 2026-05-23T09:00:00Z

**Reviewers dispatched in parallel:**
- pr-review-toolkit: 3 sub-agents (code-reviewer, silent-failure-hunter, type-design-analyzer)
- superpowers:code-reviewer
- standards (general-purpose with standards-checking instructions)
- ux-designer: NO-OP (no UI files in scope; backend-only Go diff)

**Last reviewer pre-fix SHA:** `7c715003`

### Items Found (merged across all 5 reviewers)

#### Critical (consensus across 3 reviewers)
- [critical] **Observability: cascade outcomes invisible in production** (`api/internal/handler/handler.go` — every `stopTotal` call site)
  - Decision: **fix** — Subagent 1 / Fix A
  - Rationale: `observe.Start` is NO-OP in production by design; all outcome enums + counts live only on the timing record. CLAUDE.md "All Errors/Exceptions Handled" requires recoverable anomalies to be logged. Unconditional `slog.Info` mirrors each `stopTotal` site.

#### Important
- [important] **Concreteness aggregator Error fires for healthy embedding-path rows** (`handler.go:393-396, 442-447`)
  - Decision: **fix** — Subagent 1 / Fix B
  - Rationale: Embedding path produces rows for synsets that legitimately lack concreteness (~30 per request observed); the Error semantic "cache and SQL diverged" is false for those rows. Branch counter + Error severity on `c.Source`.
- [important] **`scanEmbeddingBand` TopK nondeterminism under distance ties** (`cascade_embedding.go:52-57`)
  - Decision: **fix** — Subagent 2 / Fix C
  - Rationale: `sort.Slice` is unstable + Go map iteration is randomised → topK varies between requests on ties. Hurts sweep reproducibility. Fix: `sort.SliceStable` + secondary key on `synsetID`.
- [important] **Topic norm recomputed 35k× per request** (`cascade_embedding.go:37-51` + `forge/cascade.go:66-86`)
  - Decision: **fix** — Subagent 2 / Fix D
  - Rationale: `CascadeCosineDistance` recomputes `Σ topic[i]²` and `math.Sqrt` per call. ~12M wasted multiplies + 35k wasted sqrts per request. New helper `CascadeCosineDistanceWithANorm` + precompute once outside the scan loop.
- [important] **`CascadeConfig.Validate()` doesn't cover Composition / Alpha / DCap / TopK ceiling** (`forge/cascade.go:191-206`)
  - Decision: **fix** — Subagent 2 / Fix E
  - Rationale: Bad `Composition` value silently produces Ortony-only score; negative `Alpha` / non-positive `DCap` / non-finite `ConcretenessThreshold` accepted; unbounded `EmbeddingTopK` risks SQLite variable limit. Added `Composition.Valid()`, NaN/Inf guards, and `EmbeddingTopKCeiling = 10000`.
- [important] **`scanEmbeddingBand` only excludes primary synset — sibling senses leak through** (`cascade_embedding.go:38-40`)
  - Decision: **fix** — Subagent 2 / Fix F
  - Rationale: Polysemous lemmas can yield "anger is like anger" candidates via sister-sense centroids. Cluster path's CTE excludes ALL senses. Embedding path now accepts an `excludeIDs map[string]struct{}` covering every sense of the topic lemma.
- [important] **Union-mode 404 discards cluster candidates on incidental ErrLemmaNotFound agreement** (`handler.go:300-305`)
  - Decision: **fix** — Subagent 1 / Fix G
  - Rationale: Cluster-only and embedding-path 404s happen to coincide today, but the invariant is unenforced. Per-path `clusterLemmaNotFound` flag; only 404 when both paths return ErrLemmaNotFound (or single-mode active).

#### Low / Suggestions (folded into above fixes or deferred)
- [low] `empty_no_gate_pass` outcome name misleading — folded into Fix A telemetry rename consideration; left as-is to avoid wire churn this round.
- [low] Embedding-hit no-synsets-row counter — folded into Fix A's aggregator pattern (the existing per-occurrence Error log is acceptable until counts get noisy).

#### Deferred (real bugs, scope-bound)
- See Deferrals Ledger D1 — D14 above. 14 active deferrals.

#### Pushed back
- [silent-failure-hunter #7] env helpers should `log.Fatalf` on malformed values
  - **Push-back:** CLAUDE.md says "All Errors/Exceptions Handled — even if recoverable it should be logged". The new `slog.Warn` (landed in commit `53868878` during Task 8 review) satisfies this — the malformed env value IS logged with key + value + default. Killing the process on a single misconfigured env var is more disruptive than the standard requires. Operator can override with explicit `--candidate-sources` flag or the cmd-line short-circuit at startup is still loud.
  - Counter-reasoning available if a future reviewer disagrees.

### Critique Sections

*pr-review-toolkit:code-reviewer (id PR-CR-1):*
- `OWN_FINDINGS`: 3 items (TopK nondeterminism, topic-norm waste, TopK upper guard) — all promoted to fixes.
- `PRIOR_FINDINGS_CRITIQUE`: N/A — first round.
- `APPLIED_FIXES_CRITIQUE`: N/A — first round.
- `DEFERRAL_LEDGER_REVIEW`: ledger empty.
- CLEAN: false.

*pr-review-toolkit:silent-failure-hunter (id PR-SFH-1):*
- `OWN_FINDINGS`: 10 items focused on observability gaps, error swallowing, missing aggregators, sentinel-error robustness, dropped-result-on-error patterns.
- Promoted to fixes: #1 (props-batch silent in prod, ⊂ Fix A), #2 (outcomes invisible in prod, ⊂ Fix A), #5 (centroid miss in scoring loop, ⊂ Fix B symmetry — TBD round 2), #6 (404 invariant, ⊂ Fix G).
- Deferred: #3 (dim-mismatch counter — fold into Fix A counter symmetry round 2), #4 (missing-centroid Debug → Warn — fold into Fix A), #8/#9 → D9/D10, #10 (embedding-hit counter — fold round 2).
- Pushed back: #7 (env Fatal).
- CLEAN: false.

*pr-review-toolkit:type-design-analyzer (id PR-TDA-1):*
- `OWN_FINDINGS`: 7 items on type invariants, encapsulation, naming, JSON wire.
- Promoted to fixes: TD-OWN-1 (`Validate()` incomplete, ⊂ Fix E).
- Deferred: TD-OWN-2 → D1, TD-OWN-3 → D2, TD-OWN-4 → D3, TD-OWN-5 → D4, TD-OWN-6 → D12, TD-OWN-7 → D11.
- CLEAN: false.

*superpowers:code-reviewer (id SP-CR-1):*
- `OWN_FINDINGS`: 12 items spanning observability, latency, type-design, SQLite limits, and project bookkeeping.
- Promoted to fixes: M04-CR1-1 (⊂ Fix B), M04-CR1-3 (⊂ Fix E), M04-CR1-6 (re-measure post-Fix D → D14), M04-CR1-7 (⊂ Fix F).
- Deferred: M04-CR1-2 (heap top-K), M04-CR1-4 → D6, M04-CR1-5 (rename), M04-CR1-8 → D7, M04-CR1-9 → D2, M04-CR1-10 → D5, M04-CR1-11 (admin), M04-CR1-12 → D8.
- CLEAN: false.

*standards (id STD-1):*
- `OWN_FINDINGS`: 1 item (SF1: empty_props_batch silent in prod). Standards consulted: global + project root. Per-standard walk shows TDD ✓, Algorithms ✓ (with M04 v2 deferral), Frequent Commits ✓, CI/CD ✓, Idempotency ✓, Observability mostly ✓ (SF1 the exception), Planning ✓. Coding style: FP ✓, Readability ✓, UK English ✓, comments ✓.
- Promoted to fix: SF1 → Fix A.
- CLEAN: false.

### Fixes Applied

- **Fix A: Unconditional cascade-outcome `slog.Info`** — every `stopTotal(...)` site in `handleSuggestCascade` now also emits an `slog.Info("cascade request complete", ...)` with the same attrs minus elapsed_ms. Closes critical observability hole.
- **Fix B: Concreteness aggregator branches on `c.Source`** — `clusterConcretenessCacheMisses` (Error) vs `embeddingConcretenessMisses` (Info attr) replace the single counter. Removes pager noise on healthy union requests.
- **Fix C: Stable sort + secondary key on `scanEmbeddingBand`** — `sort.SliceStable` + `synsetID` tiebreak makes TopK deterministic across requests.
- **Fix D: Precomputed topic norm** — new `forge.CascadeCosineDistanceWithANorm` helper; topic-norm computed once outside the 35k-iteration scan.
- **Fix E: Extended `CascadeConfig.Validate()`** — `Composition.Valid()`, `Alpha ≥ 0` + finite, `DCap > 0` + finite, `ConcretenessThreshold` finite, `EmbeddingTopK ≤ EmbeddingTopKCeiling (10000)`.
- **Fix F: Sibling-sense exclusion in embedding path** — `scanEmbeddingBand` signature changed to accept `excludeIDs map[string]struct{}`; `GetForgeCascadeCandidatesByEmbedding` resolves all senses of the lemma via new `resolveLemmaSiblingSynsets` helper.
- **Fix G: Per-path ErrLemmaNotFound tracking** — `clusterLemmaNotFound` flag; only 404 in union mode when BOTH paths return ErrLemmaNotFound.
- **Follow-up: TopK ceiling raised 1000→10000** — to unblock canary while staying ~3× under SQLite modern variable limit.

### Files Modified
- `api/internal/handler/handler.go`
- `api/internal/forge/cascade.go`
- `api/internal/forge/cascade_test.go`
- `api/internal/db/cascade_embedding.go`
- `api/internal/db/cascade_embedding_test.go`
- `api/internal/handler/handler_cascade_test.go`

### Test Results
Full `go test ./...` PASS across all 7 packages (db 6.8s, forge 1.2s, handler 33.2s, others cached).

### Cumulative
Total rounds: 1 | Items resolved (fixed): 7 | Active deferrals: 14 | Superseded deferrals: 0 | Elapsed: ~1h
