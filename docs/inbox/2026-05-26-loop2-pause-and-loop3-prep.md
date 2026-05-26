# Loop-2 pause → loop-3 prep (2026-05-26)

## Where loop-2 paused

Loop-2 paused after iter 17 (operator-promoted) at HEAD `ffae371e`. Baseline at pause:

| Metric | Loop-2 start | Loop-2 end (iter 17 promoted) | Δ |
|--------|-------------:|------------------------------:|---:|
| Phase 2 median | 1.9844 | 2.0017 | +0.87% |
| Phase 2 full ratio | 2.1229 | 2.1012 | −1.0% |
| Lakoff ratio | 0.5727 | 0.8617 | **+50.4%** |

Loop-2 scoreboard: 14 (committed), 15 (committed), 16 (reverted_plateau), 17 (path-(b) operator-promoted on test-pinning fix).

## Why we paused before loop-3

Four reasons converged on the same break:

1. **Phase 2 plateau-pin** — iter 16 diagnosed that the bootstrap median is order-pinned at 2.0312; small per-pair score perturbations move the full-cohort ratio but not the median. Discontinuous moves only.
2. **Cohort axis inversion finding** (iter 16) — every signal axis pro-discriminates on one cohort and anti-discriminates on the other. The cascade is at a Pareto frontier, not a local minimum on a uniform surface.
3. **Ortony is anti-discriminative on Phase 2** — apt ortony 0.026 vs inapt 0.053. The cascade is winning Phase 2 by suppressing its primary signal via rerank. Suggests Phase 2 cohort design (LLM-generated inapt vehicles being too property-rich) and/or jaccard_salience calibration may be off.
4. **40k haiku-sm enrichments landed** — pipeline regen pending. Loop measurement is sensitive to DB state (harness scores live against `synset_properties_curated`, `synset_centroids`, `synset_concreteness`), so the regen will shift the baseline numbers and may amplify or evaporate the loop-1+2 wins.

## Loop-3 setup (in progress)

1. **Incremental DB rebuild** running in background. `enrich.sh --no-restore --from-json` on `enrichment_remainder_haiku-sm_v2_20260520.json` (45,642 synsets). PRE_ENRICH.sql was never committed by design — pipeline is built incrementally on top of `lexicon_v2.db`, with the JSONs as the source of truth for "rebuild from scratch if you really have to" reproducibility.

2. **Harness pin unlock — queued.** Remove explicit pins from `PRODUCTION_CASCADE_CONFIG` for:
   - `ortony_scoring` (currently `'jaccard_salience'` — opens 6 unused SCORING_FNS variants to the loop)
   - `gate_alpha` (currently `2.0` — opens soft-gate sigmoid steepness)
   - `alpha` (currently `1.0` — opens rerank composition coefficient)

   Each pin removal becomes a free lever the loop agent can tune via dataclass default mutation. Together this triples the discrete search space and includes the levers the user flagged as "not yet touched."

3. **Baseline refresh** under the new DB. Loop-3 starts from whatever the refreshed numbers are. Loop-1+2 cumulative wins are revalidated by inspection — if the refreshed baseline is much higher or lower than 2.0017/0.8617, that tells us how much of the loop's measurement was DB-state-specific vs structural.

4. **Path (b) gate retained.** First path-(b) commit (iter 17) proved out — modest Phase 2 cost (-1.5%) buys substantial Lakoff lift (+42.6%). Loop-3 inherits the dual-path gate with the same thresholds: path (a) "Phase 2 ↑ AND Lakoff ≥ −5%"; path (b) "Phase 2 ≥ −2% AND Lakoff ≥ +0.05 abs".

## Open questions for loop-3 / post-loop-3 follow-up

- **Noise floor.** Per-iter Phase 2 deltas (0.01-0.04 ratio points) sit at ~6-10% of the bootstrap p10-p90 spread (0.42 points). Cumulative loop-2 lift (+0.87% Phase 2) is well inside spread. Truth of these small moves: unknown without a multi-seed validation run. **Worth a one-off sanity check between iterations:** re-run baseline with bootstrap_seed ∈ {42, 7, 1000} and see whether median moves by less than 0.04. If yes, signal; if no, noise. Out of normal loop scope but cheap.

- **Cohort design audit.** Lakoff inversion + Phase 2 ortony anti-discrimination both point at the cohorts as a source of metric kink. A loop optimising against a kinked metric will faithfully chase the kink. Worth a separate session on cohort regeneration / addition of a third independent cohort.

- **Soft-gate Go port** still queued (`docs/inbox/2026-05-25-soft-gate-go-port.md`). Should follow loop-3's ratification of `gate_alpha` so the Go port adopts the tuned value, not the starting placeholder.

## Pre-loop-3 checklist

- [ ] Background import completes successfully (`enrich.sh` exit code 0)
- [ ] Verify DB post-import: row counts on `synset_properties_curated`, `synset_centroids`, `synset_concreteness` all up
- [ ] Refresh `data-pipeline/output/loop_baseline.json` under new DB
- [ ] Unlock harness pins (ortony_scoring, gate_alpha, alpha) in PRODUCTION_CASCADE_CONFIG
- [ ] Update iter-prompt template to include the unlocked levers + noise-floor note
- [ ] Fire iter 18 (loop-3 first iteration)
