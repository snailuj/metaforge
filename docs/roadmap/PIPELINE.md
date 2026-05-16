# Programme Pipeline

The single source of truth for what comes next. Always read this when starting milestone-level work; update it whenever a milestone changes status.

**Reading guidance for agents:** the immediate next job is *always* the first item under **Next**, regardless of whether it's a fresh milestone, a code-review-loop, a tooling task, or any other bridging work. Do not skip ahead to a milestone in Queued just because Next contains a non-milestone item — the file is ordered intentionally.

## Active

*(none — M03 — Cascade Gate-and-Rank promotes from Next; not yet started)*

## Next

- **M03 — Cascade Gate-and-Rank** — concreteness gate → Ortony rank → domain-distance re-rank. Restructures the pipeline from pointwise formula choice (M02 territory) to structural primitives. Wires in concreteness prediction (already available via `synset_concreteness`) and domain-distance re-rank.
  - Why now: M02 — Asymmetric Ortony Scoring closed empirically negative on 2026-05-16. Every variant in the pointwise-property-overlap family (symmetric, asymmetric, null) landed within ±0.06 of zero separation on a balanced cohort. The pointwise approach is exhausted; structural primitives are the next available lever.
  - **Inherits from M02's retro work**:
    - Trustworthy eval harness on a balanced cohort (random_uniform = +0.0068 ≈ 0, apt 271 / inapt 978, 67% MUNCH retention vs 22% before)
    - Haiku+sensorimotor enrichment: 5.4 sensorimotor properties per synset average
    - S04-A/B's cohort-shape diagnostic methodology — should be the first thing M03 runs before trusting any new verdict
  - Depends on: M02 closed ✅
  - Detail doc: to be created (`M03-cascade-gate-and-rank-roadmap.md`)
  - Branch: TBD (cut from current m02 tip once it's merged)

## Queued

- **M04 — Type-Aligned Structural Matching** — preserve property types during snap, type-diversity bonus in scoring. Lightweight approximation of SME isomorphic subgraph matching using data the pipeline already extracts.
  - Depends on: M03
- **M05 — Novelty Tracking** *(optional for MVP, valuable for Substack narrative)* — MuseScorer-style dynamic buckets, creative yield curve dashboard metric. Additive measurement layer.
  - Depends on: M03
- **The Bridge** *(new feature, surfaced during M02-S04 close on 2026-05-16)* — dual of the Forge: given source AND target, return the path through wordspace linking them. Graph search rather than ranking; different mechanism class than pointwise scoring. Two product values:
  - **Explanatory:** "anger → fire" returns the conceptual chain (e.g. `anger → heat → consuming → destruction → fire`), surfacing the metaphor's mechanism for users
  - **Inapt cohort generation:** weak/no-path queries can semi-supervisedly produce inapt examples, expanding the eval cohort beyond MUNCH
  - Algorithmic notes: branching factor ~78/hop, mitigated via salience-weighted edges, bidirectional BFS, embedding-prefilter A*, concreteness gradient, and a precomputed cluster-cluster adjacency matrix. 2-3 hops covers most apt metaphors.
  - Cost: ~2 days to shippable demo. Independent of M03/M04/M05 — could slot in any time.

## Backlog (no clear slot yet)

- **Snap-tuning research** — see project memories `project_metaforge_snap_threshold_curve` and `project_metaforge_signal_weighted_snap_JSJSJS`
  - ~~Threshold default change 0.70 → 0.48~~ — **promoted into M02 — Asymmetric Ortony Scoring S04-D (in progress 2026-05-15)**.
  - ~~Curated vocab additions for sensorimotor losses (`resonant`, `earthy`, `angular`, etc.)~~ — **promoted into M02 — Asymmetric Ortony Scoring S04-G (queued, runs only if S04-D is partial)**.
  - Per-property signal eval extension as a closed-loop instrument *(still backlog)*
  - JSJSJS — signal-weighted snap (Stage 3 picks highest-aptness target, not highest-cosine) *(still backlog)*
- **Pre-existing Go handler test failures** — 8 tests in `api/internal/handler/handler_test.go` failing because the test fixture DB isn't being provided. Confirmed pre-existing at the pre-M01 main HEAD. Worth tackling alongside or just before the M01 review-loop since the reviewer will trip on these.
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

- **Pipeline Architectural Review** *(programme-level; queued after the tooling consolidation chunk above)* — design-level retro on how Metaforge maintains its three data tiers and the schema that holds them. Four lifecycle questions:
  1. **Schema change management.** `SCHEMA.sql` is the canonical DDL but it has drifted from the committed `lexicon_v2.sql` (which is the actual data dump). When a column is added (e.g. `synset_properties.salience` in M01), how does that propagate to (a) fresh-from-PRE_ENRICH DB rebuilds, (b) in-place schema upgrades on the live DB, (c) backwards compatibility for old enrichment JSONs? Today this is implicit and breaks when assumed (see M02-S04 DB-freshness incident on 2026-05-12).
  2. **Seed data lifecycle.** Raw sources (OEWN/sqlunet, SUBTLEX-UK, Brysbaert, SyntagNet, VerbNet, FastText) live outside the repo in `~/.local/share/metaforge/`. Provenance, versioning, and update cadence are undocumented. What's the story for "the FastText vectors have improved, refresh"?
  3. **Enrichment data lifecycle.** `synset_properties` and friends accumulate from many model/prompt runs over time. Today INSERT OR IGNORE silently mixes them. The clear-and-import pattern (from chunk A) fixes one symptom but the deeper question is: should the DB carry a per-row `(model, prompt_variant, run_date)` provenance, so we can roll forward/back and reason about which data was used in any given M0X eval?
  4. **Derived curation lifecycle.** `synset_properties_curated`, `property_vocab_curated`, `vocab_clusters`, `property_antonyms` are all rebuild-from-scratch outputs of the post-enrichment pipeline. Their build cost is significant (~30-60 min per full rebuild). Is there value in incremental rebuilds for surgical changes, or is the rebuild-everything pattern correct because the derived state is small relative to source state?
  - Output: an `ARCH-REVIEW.md` doc with recommendations, possibly spawning concrete follow-on milestones.
  - Cost estimate: ~half-day design doc, half-day to scope concrete follow-ups.

## Done (newest first)

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
