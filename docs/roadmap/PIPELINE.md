# Programme Pipeline

The single source of truth for what comes next. Always read this when starting milestone-level work; update it whenever a milestone changes status.

**Reading guidance for agents:** the immediate next job is *always* the first item under **Next**, regardless of whether it's a fresh milestone, a code-review-loop, a tooling task, or any other bridging work. Do not skip ahead to a milestone in Queued just because Next contains a non-milestone item — the file is ordered intentionally.

## Active

- **M02 — Asymmetric Ortony Scoring** — vehicle-side salience weighting in forge scoring
  - Why: smallest algorithm change that uses existing V2 data, directly attacks the scoring formula's biggest theoretical flaw (symmetric overlap). First real test of the eval harness.
  - Depends on: M01 (✅ done) + code-review-loop ([PR #17](https://github.com/snailuj/metaforge/pull/17) pending merge)
  - Detail: [M02-ortony-scoring-roadmap.md](M02-ortony-scoring-roadmap.md)
  - Branch: `m02/asymmetric-ortony-scoring` (cut from review tip)

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
  - Threshold default change 0.70 → 0.48 (validated, +30.4% aptness; pending qualitative API check)
  - Per-property signal eval extension as a closed-loop instrument
  - Curated vocab additions for sensorimotor losses (`resonant`, `earthy`, `angular`, etc.)
  - JSJSJS — signal-weighted snap (Stage 3 picks highest-aptness target, not highest-cosine)
- **Pre-existing Go handler test failures** — 8 tests in `api/internal/handler/handler_test.go` failing because the test fixture DB isn't being provided. Confirmed pre-existing at the pre-M01 main HEAD. Worth tackling alongside or just before the M01 review-loop since the reviewer will trip on these.
- **CI/CD pipeline** — referenced in MVP punch list, no dedicated milestone yet
- **20k-word enrichment** — referenced in MVP punch list, mostly compute work

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
