# Programme Pipeline

The single source of truth for what comes next. Always read this when starting milestone-level work; update it whenever a milestone changes status.

## Active

*(none — M01 just landed; pick next from Queued)*

## Next

- **M02 — Asymmetric Ortony Scoring** — vehicle-side salience weighting in forge scoring
  - Why: smallest algorithm change that uses existing V2 data, directly attacks the scoring formula's biggest theoretical flaw (symmetric overlap). First real test of the eval harness.
  - Depends on: M01 (✅ done)
  - Detail: *(to be created — `docs/roadmap/M02-ortony-scoring-roadmap.md`)*

## Queued

- **M03 — Cascade Gate-and-Rank** — concreteness gate → Ortony rank → domain distance re-rank. Restructures the pipeline architecture, wires in concreteness prediction.
  - Depends on: M02
- **M04 — Type-Aligned Structural Matching** — preserve property types during snap, type-diversity bonus in scoring. Lightweight approximation of SME isomorphic subgraph matching using data the pipeline already extracts.
  - Depends on: M03
- **M05 — Novelty Tracking** *(optional for MVP, valuable for Substack narrative)* — MuseScorer-style dynamic buckets, creative yield curve dashboard metric. Additive measurement layer.
  - Depends on: M03

## Backlog (no clear slot yet)

- **Snap-tuning research** — see project memories `project_metaforge_snap_threshold_curve` and `project_metaforge_signal_weighted_snap_JSJSJS`
  - Threshold default change 0.70 → 0.48 (validated, +30.4% aptness; pending qualitative API check)
  - Per-property signal eval extension as a closed-loop instrument
  - Curated vocab additions for sensorimotor losses (`resonant`, `earthy`, `angular`, etc.)
  - JSJSJS — signal-weighted snap (Stage 3 picks highest-aptness target, not highest-cosine)
- **Full code-review-loop on M01 + snap memory-opt refactor** — `review/m01-and-snap-memopt` branch is frozen at the post-merge HEAD ready for this
- **CI/CD pipeline** — referenced in MVP punch list, no dedicated milestone yet
- **20k-word enrichment** — referenced in MVP punch list, mostly compute work

## Done (newest first)

- **M01 — Automated Eval Harness** *(merged 2026-05-03)* — discriminative aptness evaluator, parameter sweep harness, MUNCH preprocessor, scoring-fn registry, baseline + sensitivity sweep configs, `SENSITIVITY-V2-FINDINGS.md`. S01 V2 Foundation + Aptness Evaluator, S02 Parameter Sweep Harness, S03 Baseline and Sensitivity Validation all delivered. ([roadmap](M01-eval-harness-roadmap.md), [context](M01-eval-harness-context.md))
- **Sprint Zero** — Backend API, data pipeline foundations, staging deployment.

## Conventions

- New milestones land in **Queued** with at minimum: name, why, depends-on, detail-doc link.
- Move to **Next** when M-1 is done.
- Move to **Active** when work starts; flesh out detail doc; create per-slice sub-docs as needed.
- Move to **Done** with a one-line summary and merge date when shipped.
- **Backlog** items have no slot yet — promote to Queued when a milestone slot opens up.
- Detail docs live as flat `docs/roadmap/M0X-name-{roadmap,context,S0Y-name}.md`; if a milestone grows enough sub-docs to clutter, switch to a per-milestone subdirectory.
