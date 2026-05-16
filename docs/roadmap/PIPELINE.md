# Programme Pipeline

The single source of truth for what comes next. Always read this when starting milestone-level work; update it whenever a milestone changes status.

**Reading guidance for agents:** the immediate next job is *always* the first item under **Next**, regardless of whether it's a fresh milestone, a code-review-loop, a tooling task, or any other bridging work. Do not skip ahead to a milestone in Queued just because Next contains a non-milestone item — the file is ordered intentionally.

## Active

- **M02 — Asymmetric Ortony Scoring** — vehicle-side salience weighting in forge scoring
  - Status: **algorithm work paused — currently in S04 — Eval-Harness Retro.** S01 (plumbing) ✅, S02 v1/v2/v3 sweeps ✅ but all three asymmetric variants landed inside the ±0.02 null-noise band (`ortony_imbalance` best at +0.0010 separation_score — sign-flip but below the 5% success criterion). S03 (wire winner into Go forge) **parked**.
  - **S04 findings so far (2026-05-15):**
    - **S04-A** ✅ Cohort attrition has 25.9pp domain-retention spread — emotion domain at 69% vs cognition at 95%, surfacing a structural bias in the apt cohort. Inapt cohort drops to ~22% retention across all three MUNCH genres. See [`M02-S04-A-attrition-audit.md`](../../data-pipeline/sweeps/M02-S04-A-attrition-audit.md).
    - **S04-B** ✅ Apt cohort lives in a 30% smaller property-count space than inapt (`|pa|` median 10 vs 15; `|pa ∪ pb|` median 19 vs 27). Mechanically explains the `random_uniform` null drift to −0.0164. See [`M02-S04-B-union-sizes.md`](../../data-pipeline/sweeps/M02-S04-B-union-sizes.md).
    - **Apt-gap classification** ✅ Of 38 emotion-domain apt drops, only 1 is genuinely unenriched (`comedy`); the other 37 are **snap-dropped** — they have LLM properties in `synset_properties` but none survived snap at the current 0.7 cosine threshold. See [`M02-S04-apt-gap-classification.md`](../../data-pipeline/sweeps/M02-S04-apt-gap-classification.md). This pivots the next lever from "surgical enrichment" to **snap threshold retuning**.
    - **S04-D** 🟡 *In progress 2026-05-15* — re-snap at threshold 0.48 (per project-memory note: validated +30.4% aptness on a prior harness, pending re-verification here). On completion: re-run S04-A audit and `m02_ortony_v3.yaml` sweep against the new snap state.
    - **S04-C** ⏸ Threshold-percentile sensitivity sweep config staged; not run yet (deferred until D resolves so we're not measuring threshold-of-threshold on a moving cohort).
    - **S04-G** ⏸ *New lever* — curated-vocab expansion mined from `snap_dropped.jsonl` (memory flags `resonant`, `earthy`, `angular` etc. as sensorimotor losses). Promote D's most-dropped texts into `property_vocab_curated`. Only run if D is partial.
    - **S04-E** ⏸ Synthetic matched inapt cohort — replace MUNCH with apt-side topics × wrong-domain vehicles drawn from same domain distribution. Removes the 78% MUNCH attrition + the cross-task asymmetry. Biggest design change; queued if D + G stall.
    - **S04-F** ⏸ Re-run all sweeps after the in-flight 8k enrichment imports. Blocked on the enrichment finishing + `--from-json` round-trip.
  - **In-flight side-task (concurrent with S04-D):** 8k Sonnet v2 enrichment top-up running at `--batch-size 10`, ~144 synsets/hour, ~52h ETA. Output: `data-pipeline/output/enrichment_8k-topup_sonnet_v2_20260514.json`. Five enrichment-pipeline fixes shipped today (parser, timeout, fence-strip, prose-tolerant JSON extraction, preflight tripwire) — see commit log on this branch.
  - Why: smallest algorithm change that uses existing V2 data, directly attacks the scoring formula's biggest theoretical flaw (symmetric overlap). First real test of the eval harness.
  - Depends on: M01 — Automated Eval Harness (✅ done) + code-review-loop ([PR #17](https://github.com/snailuj/metaforge/pull/17) merged)
  - Detail: [M02-ortony-scoring-roadmap.md](M02-ortony-scoring-roadmap.md)
  - Branch: `m02/asymmetric-ortony-scoring`

## Next

*(none — M03 promotes once M02 lands)*

## Queued

- **M03 — Cascade Gate-and-Rank** — concreteness gate → Ortony rank → domain distance re-rank. Restructures the pipeline architecture, wires in concreteness prediction.
  - Depends on: M02
- **M04 — Type-Aligned Structural Matching** — preserve property types during snap, type-diversity bonus in scoring. Lightweight approximation of SME isomorphic subgraph matching using data the pipeline already extracts.
  - Depends on: M03
- **M05 — Novelty Tracking** *(optional for MVP, valuable for Substack narrative)* — MuseScorer-style dynamic buckets, creative yield curve dashboard metric. Additive measurement layer.
  - Depends on: M03

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

- **Code-review-loop on M01 + snap memory-opt refactor** *(PR [#17](https://github.com/snailuj/metaforge/pull/17) — pending merge)* — Holistic 4-round oscillating review (pr-review-toolkit ×3, superpowers, standards). 29 fix commits, 23 new tests (suite 512 → 535), 16 active deferrals captured. Round 4 CLEAN halt. Detail: `docs/superpowers/review-logs/2026-05-08-review-m01-and-snap-memopt-review.md`.
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
