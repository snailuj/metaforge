# Programme Pipeline

The single source of truth for what comes next. Always read this when starting milestone-level work; update it whenever a milestone changes status.

**Reading guidance for agents:** the immediate next job is *always* the first item under **Next**, regardless of whether it's a fresh milestone, a code-review-loop, a tooling task, or any other bridging work. Do not skip ahead to a milestone in Queued just because Next contains a non-milestone item — the file is ordered intentionally.

## Active

_(none — M04 v1 implementation + 3-round code-review loop + calibration sweep complete on `m04/cosine-candidate-gen` 2026-05-23; awaiting merge.)_

## Next

- **M04 v2 — Cross-domain eval cohort + sweep re-run** *(promoted 2026-05-23 on M04 v1 sweep close)* — the M04 v1 calibration sweep over MUNCH (200 apt + 200 inapt subsample) found all 9 `(d_min, d_max)` cells identical to baseline (`separation_score=0.0258, aptness_rate=0.3333`). Root cause: MUNCH is paraphrase-style metaphors (`approach`→`direction`) — not the cross-domain pairs M04 is designed to surface. 97% of MUNCH pairs don't resolve at all through the API at `limit=50`. The cosine-band path IS working (canary `TestCascadeUnion_ClassicalPairsSurface_AsCandidates` pins anger→fire / idea→light / time→money / truth→hammer surfacing as candidates), but MUNCH simply cannot measure that surface. **v2 deliverable:** construct a Lakoff-classics cohort (cross-domain pairs + plausibility-rated inapt controls) and re-run the sweep harness against THAT. Sweep YAML + driver from M04 v1 are reusable; only the fixture changes. Verdict: [`m04_embedding_band_verdict.md`](../../data-pipeline/sweeps/m04_embedding_band_verdict.md).
  - Operator decision (recorded in verdict): keep `SourcesCluster` as production default; users opt into union/embedding via `METAFORGE_FORGE_CANDIDATES` env var or `--candidate-sources` CLI flag.
  - **M04 v1 shipped value:** binary generation lift confirmed (canary test); CLI/env knobs wired; observability counters (cluster vs embedding source mix, anomaly aggregator, unconditional cascade outcome logging); type discipline tightened (CandidateSource / CandidateSources / Composition.Valid + extended CascadeConfig.Validate); deterministic TopK (stable sort); sibling-sense exclusion; latency hot-path optimised (precomputed topic norm).
  - **Active M04 deferrals (24 — see `docs/superpowers/review-logs/2026-05-23-m04-cosine-candidate-gen-review.md`):**
    - **D5** — cluster-wins-on-conflict drops embedding-path topic synset; semantic correctness gap → M05 type-aligned scoring or `SourceBoth`-keyed dual-distance.
    - **D14** — production p99 latency budget (~500ms target) — Fix D shipped, re-measure under v2 sweep cohort.
    - **D24** — `handleSuggestCascade` god-function refactor into `cascadePipeline` type; flagged by catch-fixing-forwards (handler.go touched in 3+ review runs). **Binding pre-M05 constraint.**
    - **D1 / D2 / D11 / D26** — Source-tag constructor discipline + `CandidateSources` naming sweep; bundle as one "type-discipline" commit before M05.
    - **D3 / D17** — `ForgeEmbeddingConfig` consolidation + `EmbeddingTopK` naming + `getSynsetRow` polysemy-ASC comment.
    - **D9 / D10 / D13** — DB error-handling hygiene sweep (`errors.Is`, SQLite version probe).
    - **D15 / D19 / D20 / D23** — observability gap closures (`embedding_path_unavailable` flag, dim-mismatch counter, sibling-resolver empty log, lift `cascadeAnomalies` to named type).
    - **D6** — multi-sense ANN candidate generation (M04 follow-up — see legacy entry below).
    - **D7 / D8 / D18 / D21 / D22 / D25 / D27** — minor doc/test/observability lifts; bundle.
    - Full ledger at `docs/superpowers/review-logs/2026-05-23-m04-cosine-candidate-gen-review.md` (16 active + 3 superseded).

- **M04 v1 — Cosine-Sim Candidate Generation** *(promoted to Next 2026-05-21; v1 implementation complete 2026-05-23 on `m04/cosine-candidate-gen`)* — original M04 description below for archival reference. v1 ships the cosine-band candidate generator unioning with cluster-overlap path; the eval-cohort question is what v2 must answer.
  - Why before type-alignment: optimising the *scoring* of a candidate set that systematically excludes apt cross-domain pairs is peak diminishing returns. Broadening the set first delivers the eval-cohort lift; M05 type-alignment then sharpens that richer set.
  - Detail doc: [`M04-cosine-candidate-gen-roadmap.md`](M04-cosine-candidate-gen-roadmap.md)
  - Depends on: M03 (done)
  - **Deferrals to address as part of M04** *(carried from M03-S05 review log, 2026-05-21, plus M03-pre-M04-deferrals branch close, 2026-05-22)*:
    - **D9** — cascade ordering by salience+contrast vs final_score; revisit ordering criterion once ANN candidates UNION with cluster-overlap.
    - **D15** — IN-clause batch chunking for `GetSynsetClusterPropertiesBatch`; chunk when the candidate set broadens beyond ~1k.
    - **D17** — formalise the centroid-coverage contract and asymmetric centroid-vs-concreteness lookup discipline in the handler.
    - **R2-D1** — `handleSuggestLegacy` silently degrades to `domainDist=0` when `sourceEmb` absent (legacy path's (nil, nil) benign-absence contract leaves no breadcrumb at request time). Land when cascade becomes default — legacy path may be retired or held to cascade's domainDist-signal discipline.
    - **R1-D7** — `cascade_cache_load_*` timing records emit before the "Metaforge API starting" banner. Cosmetic log-ordering fix; folds into M04's ANN-index startup wiring in `cmd/metaforge/main.go`.
  - **Cascade-anomaly aggregator** *(new slice, queued for M04 or shortly after)*:
    - **R1-D4** — `handleSuggestCascade` logs `Error` + continues when batch `propsByID` is empty for all candidates (200 indistinguishable from legitimate no-gate-pass). Wants a runtime row-count tripwire for `synset_properties_curated`.
    - **R4-D1** — `handler.go:325-328` cache-divergence `Error` log fires per candidate with no per-request cap (asymmetric with the `malformedLogCap` throttle in `db.go`).
    - Both want the same per-request anomaly aggregator: consolidate per-candidate Error logs into a count tagged on the `cascade_request_total` timing record, plus a startup-style runtime tripwire on cascade-supporting tables.
  - **Observability prerequisite** *(landed on `m03/pre-m04-deferrals` 2026-05-22)*: cascade hot-path timing + per-request trace + encode-stage outcome attribution + malformed-blob log throttle — latency baseline now collectable before M04 broadens the candidate pool. M04 should re-run the timing-enabled smoke set after wiring ANN candidates to compare against the M03-S05 baseline.

- **M03 — Cascade Gate-and-Rank** *(Stages 1 + 2 complete 2026-05-20)* — concreteness gate → Ortony rank → domain-distance re-rank. Restructures the pipeline from pointwise formula choice (M02 territory) to structural primitives. Wires in concreteness prediction (already available via `synset_concreteness`) and domain-distance re-rank.
  - Why now: M02 — Asymmetric Ortony Scoring closed empirically negative on 2026-05-16. Every variant in the pointwise-property-overlap family (symmetric, asymmetric, null) landed within ±0.06 of zero separation on a balanced cohort. The pointwise approach is exhausted; structural primitives are the next available lever.
  - **Inherits from M02's retro work**:
    - Trustworthy eval harness on a balanced cohort (random_uniform = +0.0068 ≈ 0, apt 271 / inapt 978, 67% MUNCH retention vs 22% before)
    - Haiku+sensorimotor enrichment: 5.4 sensorimotor properties per synset average
    - S04-A/B's cohort-shape diagnostic methodology — should be the first thing M03 runs before trusting any new verdict
  - **Three-tier eval strategy** (set during 2026-05-16 planning):
    1. **Composed harness** — run apt/inapt pairs through `gate → rank → re-rank`, score the cascade as one fn; cohort-shape preflight mandatory.
    2. **Ablation** — pipeline-only / +gate / +rank / +re-rank; each layer must lift separation without lifting `random_uniform`.
    3. **Lakoff-prediction tests** — independent of harness: do MUNCH-apt pairs show target-more-concrete-than-source asymmetry (pure Brysbaert)? Do apt pairs cluster at intermediate domain-distance?
    - Go/no-go: Tier 2 ablation clean + Tier 3 predictions hold → Tier 1 separation >0.05 is trustworthy lift.
  - **Strategic loop-back** *(noted 2026-05-16)*: after M03 + The Bridge ship, revisit the forge algorithm with the new tools (concreteness gate, domain-distance ranking, Bridge-generated novel-apt cohort). The Bridge cohort especially addresses the novelty/cliché blind spot that neither MRR nor `separation_score` measures.
  - **Two-stage eval baked into the plan** *(added 2026-05-17)*: Stage 1 runs M03 against `lexicon_v2.db.pre-purge-20260517` (the byte-state on which M02's published plateau was measured) — clean ablation against M02's numbers. Stage 2 runs against the rebuilt DB after the 2026-05-17 curated-vocab haiku-sm enrichment lands — forward validation in production data state. Without Stage 1, a single-stage measurement on the rebuilt DB would entangle algorithm + prompt + model + coverage in one delta. The pre-purge backup is therefore load-bearing for M03 and must survive any backup-pruning chore.
  - Depends on: M02 integration merged to main
  - Detail doc: [`M03-cascade-gate-and-rank-roadmap.md`](M03-cascade-gate-and-rank-roadmap.md) *(drafted 2026-05-17)*
  - Branch: TBD (cut from fresh main after M02 PR merges)

## Queued

- **M05 — Type-Aligned Structural Matching** *(renumbered from M04 on 2026-05-21)* — preserve property types during snap, type-diversity bonus in scoring. Lightweight approximation of SME isomorphic subgraph matching using data the pipeline already extracts.
  - Depends on: M03, M04 (richer candidate set makes type-alignment higher-leverage)
- **M06 — Novelty Tracking** *(renumbered from M05 on 2026-05-21; optional for MVP, valuable for Substack narrative)* — MuseScorer-style dynamic buckets, creative yield curve dashboard metric. Additive measurement layer.
  - Depends on: M03
- **The Bridge** *(new feature, surfaced during M02-S04 close on 2026-05-16)* — dual of the Forge: given source AND target, return the path through wordspace linking them. Graph search rather than ranking; different mechanism class than pointwise scoring. Two product values:
  - **Explanatory:** "anger → fire" returns the conceptual chain (e.g. `anger → heat → consuming → destruction → fire`), surfacing the metaphor's mechanism for users
  - **Inapt cohort generation:** weak/no-path queries can semi-supervisedly produce inapt examples, expanding the eval cohort beyond MUNCH
  - Algorithmic notes: branching factor ~78/hop, mitigated via salience-weighted edges, bidirectional BFS, embedding-prefilter A*, concreteness gradient, and a precomputed cluster-cluster adjacency matrix. 2-3 hops covers most apt metaphors.
  - Architectural framing *(added 2026-05-21)*: Forge and Bridge share the same language structure — concept-senses as nodes, semantic relations as edges, concreteness gradient, type-aware features. They differ at the *traversal* layer (1-hop frontier vs bidirectional A*), not the substrate. Extract the shared `metaphor` package (graph + cascade + candidate gens) before building the Bridge; both orchestrators then sit on top cleanly. See M04 roadmap doc for the structure-vs-orchestrator argument.
  - Dependency on M04: M04's ANN index over `synset_centroids` IS the Bridge's embedding-prefilter A* layer. Building M04 first reduces the Bridge from "2 days from scratch" to ~1.5 days of orchestration on top of shared infrastructure.
  - Cost: ~2 days to shippable demo if built before M04; ~1.5 days if built after.

## Backlog (no clear slot yet)

- **Snap-tuning research** — see project memories `project_metaforge_snap_threshold_curve` and `project_metaforge_signal_weighted_snap_JSJSJS`
  - ~~Threshold default change 0.70 → 0.48~~ — **promoted into M02 — Asymmetric Ortony Scoring S04-D (in progress 2026-05-15)**.
  - ~~Curated vocab additions for sensorimotor losses (`resonant`, `earthy`, `angular`, etc.)~~ — **promoted into M02 — Asymmetric Ortony Scoring S04-G (queued, runs only if S04-D is partial)**.
  - Per-property signal eval extension as a closed-loop instrument *(still backlog)*
  - JSJSJS — signal-weighted snap (Stage 3 picks highest-aptness target, not highest-cosine) *(still backlog)*
- **Purge stale DB backups** — `data-pipeline/output/lexicon_v2.db.*-backup` (and `*.pre-purge-*` snapshots) accumulate during destructive operations like the M02-S04 retro and the 2026-05-17 pre-enrichment clean. Each is ~336 MB. They're gitignored so they don't bloat the repo, but they do bloat the worktree volume. Define a retention policy (e.g. keep newest two, archive older to `~/.local/share/metaforge/backups/`, prune anything >30 days unless tagged) and a small `scripts/prune_db_backups.sh` to enforce it. **Required: honour a `<dbname>.keep-for-<reason>` sentinel companion file as a "do not delete" marker** — M03's Stage-1 eval depends on `lexicon_v2.db.pre-purge-20260517` (tagged with `.keep-for-m03-baseline`) and must survive any pruning sweep. Run manually for now; promote to a periodic hook if it becomes a recurring chore.
- **Pre-existing Go handler test failures** — 8 tests in `api/internal/handler/handler_test.go` failing because the test fixture DB isn't being provided. Confirmed pre-existing at the pre-M01 main HEAD. Worth tackling alongside or just before the M01 review-loop since the reviewer will trip on these.
- **Sweep-with-next-touch micro-fixes** *(from M03-pre-M04-deferrals review log, 2026-05-22)*:
  - **R1-D5** — `GetLemmaForSynset` (`api/internal/db/db.go`) returns bare `err` without wrapping. One-line `fmt.Errorf("GetLemmaForSynset failed for %s: %w", synsetID, err)` fix; pick up on the next `db.go` touch (likely the M04 cluster-prop work).
- **M04 follow-up — secondary-sense ANN candidate generation** *(captured during M04 brainstorm 2026-05-23)*: M04 v1 ships the ANN candidate path against a *single* polysemy-ASC primary source synset per lemma (mirroring the existing `resolvePrimarySynset` parity rule). For polysemous lemmas where a secondary sense would surface a better cross-domain vehicle, M04 v1 relies on the cluster-overlap path to catch it. **Open question for v2:** would running the ANN query against ALL source senses (5× cosine-scan cost on a polysemous lemma) surface MUNCH-apt vehicles the primary-only path misses? **Eval-first follow-up:** (a) extend the Python `evaluate_cascade_pair` harness to score all-senses-ANN vs primary-only-ANN candidate sets on the MUNCH-apt cohort; (b) if Python eval shows ≥5% lift on apt-pair coverage with acceptable inapt-pair noise, port the all-senses path to Go behind a config flag; (c) sweep cosine-scan cost vs candidate-quality on the production DB. Defer to post-M04 (post-Bridge maybe) so M04 ships its core lift without scope creep.
- **Atomic-commit hygiene — recurring pattern** *(R1-D6 + R4-D2 informational; M03-pre-M04 review log)*: commits `ccfa6c3b` and `218fad1d` each bundled 3-4 logically independent fixes (test + behaviour change + config plumbing). Project standard "Commit after each green test. Small, atomic commits. Never batch up changes" was violated twice in the same loop. Cannot fix retroactively (force-push trade-off). Watch-list item for future review-loop fix dispatches — each finding's fix should land as its own commit. Round-5 commit `b1f820cf` showed the discipline can be restored.
- **CI/CD pipeline** — referenced in MVP punch list, no dedicated milestone yet
- **20k-word enrichment** — 8k top-up *in progress as a side-task of M02 — Asymmetric Ortony Scoring S04* (running 2026-05-15, ~52h ETA, ~144 synsets/hour at batch-size 10). Brings DB from ~12k → ~20k enriched synsets. After import (`enrich.sh --from-json`), feeds S04-F re-sweep.

- **Pipeline Tooling Consolidation & Relevance Audit** *(programme-level refactor; queued for after M02 — Asymmetric Ortony Scoring lands)* — captures portability/maintainability work surfaced during the M02-S04 retro. Two sub-goals:
  1. **Backfill four items** into the canonical production code:
     a. Move `BATCH_PROMPT_V2_SM` (sensorimotor prompt) into `data-pipeline/scripts/enrich_properties.py` alongside `BATCH_PROMPT_V2`, with a `--prompt-variant {physical,sensorimotor}` CLI flag. Currently lives in a test-script file (`m02_s04_test_sensorimotor_prompt.py`) which is brittle.
     b. Atomic incremental JSON writes in production `enrich_properties.py` (flush after every batch, .tmp-rename pattern). The 2525 Sonnet synsets lost when the in-flight broad run was killed on 2026-05-15 are evidence this matters.
     c. `--clear-existing` flag on the import path that DELETEs old rows before INSERT, instead of INSERT OR IGNORE silently keeping stale data. Useful for model switches and prompt iteration.
     d. Haiku-friendly worked-example IDs (numeric, not `oewn-foo-n`) plus explicit *"use the input ID verbatim"* instruction in the canonical prompt. Improves cross-model reliability — Haiku 39%-failed at ID format until this was patched in the local SM prompt.
  2. **Relevance audit** of existing pipeline tooling — which scripts/wrappers are now obfuscation rather than abstraction?
     * `data-pipeline/enrich.sh` — orchestrator wrapper for restore → enrich → pipeline → dump. In recent work we bypassed it entirely (called `enrich_properties.py` and `enrich_pipeline.run_pipeline` directly) because its assumption of restoring from `PRE_ENRICH.sql` doesn't fit incremental top-ups. Decide: keep + fix, simplify into a thin orchestrator, or retire.
     * `data-pipeline/scripts/m02_s04_*.py` — eleven ad-hoc scripts written during the retro. Triage: archive (audit one-offs that document the retro), formalise (the patch/import workflow patterns), or delete (superseded by formal versions).
     * Other potentially-defunct files: `evolve_prompts.py`, `evolve_trials.sh`, `ab_test_purpose_prompt.py`, `prompt_templates.py` — pre-M01 evolutionary-prompt-search era. Confirm whether any still active.
  - Goal: keep `code-as-documentation` of valuable patterns; remove clutter that misleads future contributors.
  - Cost estimate: ~1-day PR for the backfills + relevance audit doc.

- **`metaphor` package extraction & architectural cleanup** *(programme-level; queued for the M04 → Bridge gap)* — extract the shared language structure (concept-senses as nodes, semantic relations as edges, concreteness gradient, type-aware features, cascade scorer, candidate generators) into a small `metaphor` package so Forge and Bridge sit on top as thin orchestrators. See M04 roadmap doc's "language-structure framing" section for the structure-vs-orchestrator argument. Carries the following deferrals:
  - **From the M03-S05 review log (2026-05-21):**
    - **D1** — Tagged-union refactor for `CascadeResult` (`(Status, *Scored)` shape).
    - **D2** — Constrained-type discipline for `CascadeStatus` + `Composition` (Valid() methods / constructors).
    - **D3** — `CascadeCache` encapsulation (unexport maps, add accessors) — pairs with the package extraction.
    - **D4** — `Match` struct legacy/cascade split (or `GatePassed` → `*bool`) for cleaner JSON wire format.
    - **D5** — Nil-cache defence in `handleSuggestCascade` (lands when cache lifecycle moves into the package).
    - **D14** — Port Python `__post_init__` validation into `CascadeConfig.Validate()`.
  - **From the M03-pre-M04-deferrals review log (2026-05-22):** the observe-surface redesign cluster — three deferrals converged here independently:
    - **R1-D1** — `observe.Start` allocates a closure literal + variadic slice on every disabled-path call. Architectural fix is a typed `Timer` struct (or two-method `Stop()` + `StopWith(...)` API) so callers opt into variadic boxing only on the enabled path.
    - **R1-D2** — `handler_legacy_embedding_error_test.go` bypasses `NewHandlerWithCascade` via direct `&Handler{}` construction. Add a `newHandlerForTest(...)` constructor as part of the Handler-construction discipline rework alongside D3/D5; migrate the test.
    - **R1-D3** — `observe.enabled` global `atomic.Bool`; race vector under `t.Parallel()`. The observe surface redesign removes the global by injecting `*Timer` through the handler graph.
  - Cost estimate: ~1-2 day refactor for the core extraction; the observe-surface redesign is ~half a day on top — total ~1.5-2.5 days. Lands between M04 and The Bridge so the Bridge inherits the package shape on day one.

- **Pipeline Architectural Review** *(programme-level; queued after the tooling consolidation chunk above)* — design-level retro on how Metaforge maintains its three data tiers and the schema that holds them. Four lifecycle questions:
  1. **Schema change management.** `SCHEMA.sql` is the canonical DDL but it has drifted from the committed `lexicon_v2.sql` (which is the actual data dump). When a column is added (e.g. `synset_properties.salience` in M01), how does that propagate to (a) fresh-from-PRE_ENRICH DB rebuilds, (b) in-place schema upgrades on the live DB, (c) backwards compatibility for old enrichment JSONs? Today this is implicit and breaks when assumed (see M02-S04 DB-freshness incident on 2026-05-12).
  2. **Seed data lifecycle.** Raw sources (OEWN/sqlunet, SUBTLEX-UK, Brysbaert, SyntagNet, VerbNet, FastText) live outside the repo in `~/.local/share/metaforge/`. Provenance, versioning, and update cadence are undocumented. What's the story for "the FastText vectors have improved, refresh"?
  3. **Enrichment data lifecycle.** `synset_properties` and friends accumulate from many model/prompt runs over time. Today INSERT OR IGNORE silently mixes them. The clear-and-import pattern (from chunk A) fixes one symptom but the deeper question is: should the DB carry a per-row `(model, prompt_variant, run_date)` provenance, so we can roll forward/back and reason about which data was used in any given M0X eval?
  4. **Derived curation lifecycle.** `synset_properties_curated`, `property_vocab_curated`, `vocab_clusters`, `property_antonyms` are all rebuild-from-scratch outputs of the post-enrichment pipeline. Their build cost is significant (~30-60 min per full rebuild). Is there value in incremental rebuilds for surgical changes, or is the rebuild-everything pattern correct because the derived state is small relative to source state?
  - Output: an `ARCH-REVIEW.md` doc with recommendations, possibly spawning concrete follow-on milestones.
  - Cost estimate: ~half-day design doc, half-day to scope concrete follow-ups.

## Done (newest first)

- **M03-S05 — Forge integration into Go API** *(landed 2026-05-21, branch `m03/cascade-gate-and-rank`)* — cascade scoring wired into `api/internal/forge` + `api/internal/handler` behind `--cascade` flag / `METAFORGE_FORGE_CASCADE=1` env var. Per-request hot path: 2 DB queries + N in-memory map lookups via `CascadeCache` (~50 MB at startup, eliminates ~4× per-candidate DB hops). SQL gate-pushdown via `shared_gated` CTE keeps query under 2 s on broad-coverage lemmas (vs 200 s without the CTE refactor). Scoring-math parity with Python verified to ±1e-6 by `cascade_parity_test.go` against the 4 scored crib pairs (anger→fire, idea→light, time→money, truth→hammer). Crib: [`2026-05-21-m03-s05-smoke-test-crib.md`](../plans/2026-05-21-m03-s05-smoke-test-crib.md); plan: [`2026-05-21-m03-s05-forge-integration.md`](../plans/2026-05-21-m03-s05-forge-integration.md). Surfaced finding: classical cross-domain metaphor pairs share no curated cluster between primary synsets, so the Go endpoint can't surface them today — broadening the candidate set via ANN over `synset_centroids` is the **M04 — Cosine-Sim Candidate Generation** milestone.
- **M02 — Asymmetric Ortony Scoring** *(closed empirically negative 2026-05-16)* — built three asymmetric scoring variants (`ortony_vehicle_salience`, `ortony_imbalance`, `ortony_log_ratio`) and exercised them via the M01 eval harness. The S04 retro identified a cohort-shape mismatch confound that was producing artifactual signal on the original sweeps. After the Haiku+sensorimotor rebuild balanced the cohort, **no scoring formula in the pointwise-property-overlap family beats the random_uniform null reference**. M02's algorithmic premise is empirically refuted. What M02 *did* deliver: a trustworthy eval harness on a balanced cohort, the `physical → sensorimotor` prompt rename (5.4 vs 0.8 sensorimotor props per synset), Haiku adopted as production enrichment model, and a cohort-shape diagnostic methodology (S04-A/B) that is now standard eval-harness toolkit. Detail: [`M02-S04-CLOSING-findings.md`](../../data-pipeline/sweeps/M02-S04-CLOSING-findings.md), [`M02-ortony-scoring-roadmap.md`](M02-ortony-scoring-roadmap.md).
- **Code-review-loop on M01 + snap memory-opt refactor** *(PR [#17](https://github.com/snailuj/metaforge/pull/17) — merged 2026-05-12)* — Holistic 4-round oscillating review (pr-review-toolkit ×3, superpowers, standards). 29 fix commits, 23 new tests (suite 512 → 535), 16 active deferrals captured. Round 4 CLEAN halt. Detail: `docs/superpowers/review-logs/2026-05-08-review-m01-and-snap-memopt-review.md`.
- **M01 — Automated Eval Harness** *(merged 2026-05-03)* — discriminative aptness evaluator, parameter sweep harness, MUNCH preprocessor, scoring-fn registry, baseline + sensitivity sweep configs, `SENSITIVITY-V2-FINDINGS.md`. S01 V2 Foundation + Aptness Evaluator, S02 Parameter Sweep Harness, S03 Baseline and Sensitivity Validation all delivered. ([roadmap](M01-eval-harness-roadmap.md), [context](M01-eval-harness-context.md))
- **Sprint Zero** — Backend API, data pipeline foundations, staging deployment.

## Conventions

- **Next is always the immediate next job.** It can be a milestone, a code-review-loop on a recently-merged milestone, a tooling task, a pre-flight blocker — whatever genuinely comes first. Do not assume Next must be a milestone.
- New milestones land in **Queued** with at minimum: name, why, depends-on, detail-doc link.
- Move to **Next** when its prerequisites are met (M-1 done, blocking tasks resolved, etc.).
- Move to **Active** when work starts; flesh out detail doc; create per-slice sub-docs as needed.
- Move to **Done** with a one-line summary and merge date when shipped.
- **Backlog** items have no current slot — items either lack prerequisites, are speculative, or are awaiting prioritisation. Promote to Queued (or Next directly) when a slot opens up. Adding to Backlog should never strand work that's actually ready to go.
- Detail docs live as flat `docs/roadmap/M0X-name-{roadmap,context,S0Y-name}.md`; if a milestone grows enough sub-docs to clutter, switch to a per-milestone subdirectory.
