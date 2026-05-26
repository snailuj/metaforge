# Iter 20 — `ortony_vehicle_salience` Pareto near-miss

**Status:** Reverted iteration but produced a sharp finding worth a follow-up iter.

## What iter 20 found

Probed all 5 unused `SCORING_FNS` variants at the iter-19 baseline (Phase 2 2.0878, Lakoff 0.8856) under the current loop-3 config (`gate_alpha=3.0`, `alpha=0.75`, `ortony_weight=1.75`, etc.). Results:

| Scorer | Phase 2 | Lakoff | Path-(a)? | Path-(b)? |
|--------|--------:|-------:|-----------|-----------|
| jaccard_salience (baseline) | 2.0878 | 0.8856 | — | — |
| ortony_imbalance | 2.0663 | 0.6250 | ❌ both | ❌ both |
| **ortony_vehicle_salience** | **2.0472** | **0.9293** | ❌ Phase 2 | ❌ Lakoff (off by 0.0063) |
| ortony_log_ratio | 2.0773 | 0.8856 | ❌ Phase 2 | ❌ Lakoff (flat) |
| ortony_cosine_salience | 2.0472 | 0.9293 | ❌ Phase 2 | ❌ Lakoff (off by 0.0063) |
| ortony_jaccard_raw | 2.0578 | 0.8856 | ❌ Phase 2 | ❌ Lakoff (flat) |

Plus one composite probe:
| ortony_vehicle_salience + alpha=0.5 | 2.0244 | 0.9293 | ❌ Phase 2 | ❌ Phase 2 (below path-b floor 2.0461) |

## The near-miss

`ortony_vehicle_salience` (and `ortony_cosine_salience` — they give identical scores under this config) hit:

- **Phase 2: 2.0472** — exactly at the path-(b) floor of **2.0461**, a 0.0011 margin
- **Lakoff: 0.9293** — needs to reach **0.9356** for the path-(b) +5% Lakoff floor; off by **0.0063**

On a 170-pair Lakoff cohort, 0.0063 in ratio is roughly **a single pair flip** away from passing. The scorer change alone gets us 4.93% of the 5% required Lakoff lift — extremely close.

## Follow-up hypothesis for iter 21

Combine `ortony_scoring='ortony_vehicle_salience'` with **one** small lever change that nudges a single Lakoff pair across the promotion threshold without pulling Phase 2 below 2.0461. Candidates:

- `ortony_weight` 1.75 → 1.80-1.90 (small up-nudge — strengthens the ortony signal which was already pro-Lakoff)
- `gate_alpha` 3.0 → 2.8 (small down-nudge — softens the gate slightly, letting one more sub-threshold Lakoff apt pair contribute)
- `concreteness_bonus_coef` 0.002 → 0.0015 (slightly lighter — gives back a tiny amount of the rerank-favouring trim)

Each is in the "single pair flip" regime by construction. Worth a multi-probe iter targeting exactly this near-miss.

## Why path-(a) is unlikely on this lever

All 5 scorer variants regressed Phase 2 below the path-(a) strict-improvement floor. The Phase 2 plateau-pin from iter 16 may be biting again: discrete-changes-only doesn't mean "all discrete changes lift Phase 2." `ortony_vehicle_salience` shifted enough pair rankings to flip a Lakoff pair upward but also flipped some Phase 2 pairs downward in net.

The path-(b) gate exists precisely for cases like this — accept a small Phase 2 cost for a real Lakoff lift. We just couldn't quite reach +5% Lakoff on the scorer change alone.

## Cumulative loop-3 state (unchanged after iter 20 revert)

Phase 2 2.0878 / Lakoff 0.8856 / HEAD `eccdc08a`.
