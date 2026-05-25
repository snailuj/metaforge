# Karpathy Loop — Pre-flight Prep

Drafted while Phase 2 runs. Once Phase 2 finishes, three pieces of
infrastructure must land before the first loop iteration. This doc
captures all three so the loop can start the moment they're in place.

Cross-ref: `docs/inbox/2026-05-25-metaphor-spike-findings.md` (FU-1
metric correction, FU-2 lemmatisation — both flow into the prep
work below).

## The loop itself

```
while time_budget_remains:
    1. Pick top untried lever from the ranked list (below)
    2. Implement the change (≤ 5 lines preferred; never a new pipeline stage)
    3. Re-score the Phase 2 cohort with the new config — pure local op,
       no LLM calls (the cohort JSONL is saved)
    4. Compute end-to-end ratio + per-reason breakdown on BOTH the
       train split AND the val split (see Condition 2)
    5. Improvement gate:
         BOTH train AND val show better → commit, mark lever 'won'
         else                           → revert, mark lever 'tried'
    6. Loop with a 5-min wall-clock cap per iteration
```

Wall-clock budget per iteration: 5 min. Eval pass alone is ~40-90s for
200 topics × ~1500 vehicles through the cascade; the rest is the
implementation + reversion overhead. Levers that need re-snap may run
longer — explicitly allow up to 10 min for those, flagged in the list.

Termination: the operator stops the loop, OR three consecutive iterations
fail the improvement gate (drift signal — we're in noise floor).

---

## Condition 1: FU-1 end-to-end metric

**What.** Replace separation_score (scored-pair mean delta) with the
end-to-end discrimination ratio as the loop's truth-metric.

**Why.** Phase 1b showed separation_score = +0.0061 against a system
with 2.5× end-to-end discrimination. Modest cascade tweaks move
separation_score by ≤0.005 — below noise floor.

**Where.** `evaluate_aptness.py:aggregate_metrics()` and the cascade
sweep harness. Add a new function `end_to_end_ratio(apt_scored,
inapt_scored, threshold) -> dict` returning::

    {
      "apt_promote_rate":   n_apt_above   / n_apt_total,
      "inapt_promote_rate": n_inapt_above / n_inapt_total,
      "ratio": apt_promote_rate / inapt_promote_rate,
    }

Denominator is the FULL cohort (gate-dropped + missing-concreteness +
no-properties + unresolved all count as 'not promoted').

**Effort.** ~30 lines + 3 unit tests. ~30 min.

**Loop dependency.** Lever evaluation step 4 uses this metric.

---

## Condition 2: Train/val split of the Phase 2 cohort

**What.** Deterministic 80/20 split (160 train + 40 val topics) of the
200-topic cohort. Apply the lever to BOTH splits; commit only if BOTH
improve.

**Why.** With ~20-30 loop iterations against one cohort, any tweak
will eventually find a noise direction that improves the metric.
Held-out val catches this.

**Where.** New helper in the cascade harness:

    def split_cohort(scores_jsonl: Path, seed: int = 20260525) -> tuple[list, list]:
        """Deterministic 80/20 split. Returns (train, val) score-row lists."""

Topics (not vehicles) are split, so all vehicles for a topic stay in
the same partition — prevents within-topic leakage.

The Phase 1b 20-topic spine is forced into TRAIN to keep the val set
purely sampled (i.e., no spine bias in the held-out signal).

**Effort.** ~20 lines + 1 test. ~15 min.

**Alternative held-out.** If the Lakoff cohort is still intact, also
run each lever against it as a sanity check. A tweak that helps
Phase 2 train+val but hurts Lakoff is a yellow flag, not a green.

---

## Condition 3: Lever list (ranked)

Drafted from a read of `evaluate_cascade.py` (CascadeConfig knobs) and
`evaluate_aptness.py` (SCORING_FNS registry). Ordered roughly by
expected-effect ÷ implementation-cost.

### Tier 1 — single-knob tweaks (≤2 lines, eval-only)

These mutate `CascadeConfig` without touching code paths. Re-score is
the entire work.

1. **Gate threshold sweep.** `concreteness_threshold` ∈ {0.5, 0.75,
   1.0, 1.25, 1.5}. Phase 1b's gate dropped 68% of inapt vs 29% of
   apt — moving the threshold trades apt-attrition for inapt-promotion.
   Current default 1.0 may be sub-optimal at the new cohort scale.
2. **Alpha sweep.** `alpha` ∈ {0.0, 0.25, 0.5, 0.75, 1.0, 1.5}.
   Re-rank weight on the cosine bonus. M05 sweep ratified 1.0 at
   Lakoff scale; Phase 2 may want different.
3. **Composition flip.** `composition` ∈ {"additive",
   "multiplicative"}. Production is additive; multiplicative dampens
   high-cosine bonuses on low-Jaccard pairs. Could help discriminate
   same_domain vehicles (which often have high cosine, low Jaccard).
4. **d_cap sweep.** `d_cap` ∈ {0.5, 0.65, 0.77, 0.85, 0.95}. Cosine
   re-rank cap. Higher d_cap promotes more distant vehicles
   (potentially more apt cross-domain).

### Tier 2 — formula swap (1-line config change, eval-only)

5. **Scoring formula swap.** `ortony_scoring` ∈ {jaccard_salience,
   jaccard_raw, cosine_salience, ortony_vehicle_salience,
   ortony_imbalance, ortony_log_ratio}. The registry already has 6
   variants. Production is `jaccard_salience`. Run all 6 against the
   same cohort + threshold and pick the discrimination winner.

### Tier 3 — small algorithmic tweaks (5-15 lines)

6. **Vehicle-side concreteness penalty.** Currently the gate is a
   one-sided check (signed delta ≥ threshold). Add a soft penalty
   when vehicle concreteness is below a floor (e.g., 3.0), even if
   the signed delta passes. Targets abstract-vehicle inapt cases
   (wrong_concreteness reason type).
7. **Property-type weighting in Jaccard.** Weight sensorimotor /
   behavioural properties more heavily than social / emotional in
   the salience-weighted Jaccard. Phase 1b per-reason data should
   tell us which types correlate with apt vs inapt.
8. **Confidence-gated apt scoring.** Drop apt vehicles where Haiku
   returned confidence < 0.7 before scoring. Tests whether Haiku's
   self-rating is a useful signal we're currently throwing away.

### Tier 4 — needs re-snap (≤10 min budget)

9. **Concept lemmatisation (FU-2).** Lemmatise concepts before
   lemmas-table lookup. Bigger effect on bridge-node data than on
   cascade scoring directly, but may shift snap-rate-driven attrition.
10. **Sense-disambiguated concept snap.** When a concept resolves to
    multiple synsets (polysemy), pick the one whose properties have
    the highest Jaccard against the topic. Currently the snap takes
    the primary sense by frequency — context-driven snap may improve
    bridge-node quality.

### Off-limits — explicitly NOT loop fodder

These are real cascade improvements but too big for a 5-min iteration.
Promote to a separate plan if they look promising during the loop:

- Adding a new pipeline stage (e.g., antonym-pair penalty stage)
- Replacing the embedding model (wiki-news → another)
- Adding new property types beyond the existing six
- Restructuring the snap cascade (3-stage → N-stage)
- Anything that requires re-running LLM enrichment

---

## What to do if Phase 2 reveals a different picture

If Phase 2 shows end-to-end ratio drops below ~1.5×, the cascade is too
noisy for the loop to converge. In that case:

1. Bail on the loop until lemmatisation lifts snap and recomputes the
   baseline.
2. Or pivot to a larger structural change (one of the off-limits items
   above) outside the loop.

Decision point: log the Phase 2 ratio in the findings doc; if <1.5×,
explicitly stop and re-plan.
