# M05 Lakoff γ-Sweep Verdict

> **Phase 2 (2026-05-24)** — supersedes earlier all-zero verdict. With
> `limit=10000` removing ranking-cutoff confound and `m05_cohort_diagnose.py`
> confirming 100% of the cohort is pre-flight clean (every drop is a real
> candidate-gen rejection, not a data-availability gap), the sweep produces
> a clean monotone γ signal. **Production default ratified at γ=1.0**, applied
> at `forge.DefaultCascadeConfig()`.

_Baseline (cluster_only): separation_score = 0.0000, aptness_rate = 0.0000_

## Results Grid

| Cell | d_min | d_max | gamma | separation_score | aptness_rate | cluster | embedding | both | apt_miss | inapt_miss |
|------|------:|------:|------:|-----------------:|-------------:|--------:|----------:|-----:|---------:|-----------:|
| gamma2.00_dmax0.85 | 0.4 | 0.85 | 2.0 | 0.2717 | 0.0000 | 19 | 0 | 0 | 61 | 89 |
| gamma1.00_dmax0.85 | 0.4 | 0.85 | 1.0 | 0.0086 | 0.0000 | 19 | 0 | 0 | 61 | 89 |
| gamma1.00_dmax0.75 | 0.5 | 0.75 | 1.0 | 0.0000 | 0.0000 | 19 | 0 | 0 | 61 | 90 |
| gamma0.50_dmax0.85 | 0.4 | 0.85 | 0.5 | -0.1230 | 0.0000 | 19 | 0 | 0 | 61 | 89 |
| gamma0.25_dmax0.85 | 0.4 | 0.85 | 0.25 | -0.1888 | 0.0000 | 19 | 0 | 0 | 61 | 89 |
| gamma0.00_dmax0.85 | 0.4 | 0.85 | 0.0 | -0.2546 | 0.0000 | 19 | 0 | 0 | 61 | 89 |

## Ratified: γ = 1.0

- separation_score moves linearly with γ (Δsep ≈ +0.263 per unit γ across γ ∈ {0, 0.25, 0.5, 1, 2})
- γ = 1.0 brings the apt cohort to parity with the inapt survivors (separation crosses zero from −0.25 to +0.01)
- γ = 2.0 scores highest in this sweep (+0.27) but the magnitude rides on n=1 inapt and overweights one design dimension across general thesaurus traffic
- γ = 0 would silently keep the apt cohort *underperforming* inapt — the previous default was an artefact of the M05 dormant state, not a sweep-verified choice

## Caveats (read before extrapolating)

1. **n=1 inapt survives most cells.** 89/90 inapt pairs are filtered by candidate-gen at every γ. The single survivor (90 at γ=1_dmax0.75 — a transport timeout on `time` widened that cell to n=0) anchors mean(inapt); separation_score magnitude is sensitive to which one inapt vehicle made it through. The monotone *trend* across 5 γ values is robust to this — the apt cohort really does carry more type diversity than the inapt sample. The *magnitude* (+0.27 vs +0.01) is not.
2. **`aptness_rate = 0.0000` everywhere.** γ moves ranks; it does not push apt pairs past the absolute apt-classification line (apt_score > inapt_mean + σ). That is an absolute-score problem for a future milestone (M06+ candidates: cohort audit, gate tuning, or absolute-score recalibration).
3. **Apt resolution at limit=10000 is 19/80 = 24%.** Up materially from the previous limit=100 range (3–9%), but still a thin survivor count. Further coverage gain requires investigating why ~76% of pre-flight-clean apt vehicles are still rejected by candidate-gen / no-overlap.

## Drop Attribution (per-cause breakdown)

_Pre-flight diagnostics loaded — each apt/inapt drop is attributed to a typed bucket._
_Bucket meanings: `api_filtered_or_no_overlap` = pre-flight clean, the API still didn't_
_surface this vehicle (the real candidate-gen / no-overlap signal); `pre_topic_*` /_
_`pre_vehicle_*` = pre-flight blocked at the named layer (data not in DB)._

| Cell | apt:api_filtered_or_no_overlap |
|------|---:|
| gamma2.00_dmax0.85 | 61 |
| gamma1.00_dmax0.85 | 61 |
| gamma1.00_dmax0.75 | 61 |
| gamma0.50_dmax0.85 | 61 |
| gamma0.25_dmax0.85 | 61 |
| gamma0.00_dmax0.85 | 61 |

| Cell | inapt:api_filtered_or_no_overlap |
|------|---:|
| gamma2.00_dmax0.85 | 89 |
| gamma1.00_dmax0.85 | 89 |
| gamma1.00_dmax0.75 | 90 |
| gamma0.50_dmax0.85 | 89 |
| gamma0.25_dmax0.85 | 89 |
| gamma0.00_dmax0.85 | 89 |
