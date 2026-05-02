# M001-yywgwj — Forge Algorithm Research Programme

## Programme Overview

Five milestones to transform the Metaforge metaphor forge from a flat property-overlap engine into a theoretically grounded, automatically evaluated metaphor generator. Guided by the "Steal Shamelessly" research report and its LLM council critique.

## Current State

- 12,066 synsets enriched with V1 properties (flat strings, no salience) in the staging DB
- 10,530 V2-enriched synsets sitting as JSON on disk (structured: salience, type, relation) — not imported
- MRR at 0.0358 against 274 gold-standard pairs — 62% of misses have zero shared properties
- V2 pipeline, schema, and scoring code lives on `review/cross-domain-metaphors` (5 unmerged commits ahead of main, 44 merged via PR)
- Cascade scoring architecture designed in `docs/plans/cascade-scoring-roadmap.md` but not implemented
- Concreteness prediction infrastructure exists on main but not wired into scoring

## Problem Statement

The forge algorithm uses symmetric property-overlap with a flat composite score. This is theoretically wrong for metaphor (Ortony salience imbalance requires asymmetric vehicle-side weighting) and practically limited (62% zero-overlap rate means the matching paradigm itself is the bottleneck). Every algorithm change is currently validated by manual MRR runs — there is no automated hypothesis testing.

## Milestone Sequence

| # | Milestone | Dependency | Purpose |
|---|-----------|------------|---------|
| **M1** | Automated Eval Harness | — | Build sweep infrastructure + discriminative aptness evaluator. MRR kept as regression check, aptness rate becomes primary KPI. Everything downstream validates against this. |
| **M2** | Asymmetric Ortony Scoring | M1 | Implement vehicle-side salience weighting. Smallest algorithm change, uses existing V2 data, directly attacks the scoring formula's biggest theoretical flaw. First real test of the eval harness. |
| **M3** | Cascade Gate-and-Rank | M2 | Replace flat composite with concreteness gate → Ortony rank → domain distance re-rank. Wire concreteness prediction into scoring. Restructures the pipeline architecture. |
| **M4** | Type-Aligned Structural Matching | M3 | Preserve property types during snap, add type-diversity bonus to scoring. Lightweight approximation of SME isomorphic subgraph matching using data the pipeline already extracts. |
| **M5** | Novelty Tracking | M3 | MuseScorer-style dynamic buckets, creative yield curve dashboard metric. Additive measurement layer. Optional for MVP, valuable for Substack narrative. |

## Ordering Rationale

M1 is the keystone — without automated evals, every algorithm change is manual eyeballing. Once M1 is done, M2–M4 each become a tight hypothesis → sweep → validate → commit loop. M2 before M3 because Ortony scoring is a formula change (small), while the cascade is an architectural change (larger) that depends on knowing the Ortony formula works. M4 after M3 because type alignment slots into the cascade's rank stage. M5 is genuinely optional — it measures creativity distribution, which is most useful after the algorithm changes have shifted that distribution.

## Key Constraint

Production (metaforge.julianit.me) remains frozen at the `production` branch (recovered feat/freq-fam). Staging (metaforge-next.julianit.me) is the development target. A promotion to production happens when staging demonstrates fundamentally better forge output — not just UI polish.

## Research Sources

- `docs/research/steal-shamelessly-report.md` — comprehensive literature survey of computational metaphor generation
- `docs/research/steal-shamelessly-report-critique.md` — LLM council critique identifying architectural conflicts and integration guidance
