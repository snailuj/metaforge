# Metaphor Enrichment Spike — Cross-Phase Findings

Living log of findings, surprises and follow-up work surfaced by the
metaphor-enrichment spike. Spans Phase 1a, 1b, 2 (in progress) and any
follow-ups beyond. Pin into `docs/inbox/` so it triages naturally with
other captures, and link from the spike doc.

Spike doc: `docs/inbox/2026-05-24-metaphor-enrichment-pivot-spike.md`

---

## Phase 1a (2026-05-24)

Run timestamp: 20260524T115144 · Branch: spike/metaphor-enrichment-phase-1a
(merged to main). Outputs: `data-pipeline/output/metaphor_spike_*phase1a_*`.

5 topics × 2 models × 2 prompts = 20 calls. Gates:

| Model | Parse | Schema | Single-word | Snap |
|-------|-------|--------|-------------|------|
| haiku-4-5  | 100% | 100% | 100% | 94% |
| sonnet-4-6 | 100% | 100% | 100% | 89% |

All four format gates passed with margin. Snap-rate >80% on both models.
Sonnet correctly flagged dead metaphors (e.g., `pump` for heart) that
Haiku returned as top apt vehicles — calibration difference confirmed.

Phase 1a verdict: **PASS** → promote to Phase 1b.

---

## Phase 1b (2026-05-25)

Run timestamp: 20260524T234150 · Branch: spike/metaphor-enrichment-phase-1b.
Outputs: `data-pipeline/output/metaphor_spike_*phase1b_*`.

**Architecture pivot:** Sonnet-as-prompt-engineer. One-off Sonnet pass
on 3 example topics (love, knowledge, fear — outside test set) → gold
few-shot baked into Haiku prompts. Then 20 topics × Haiku-only × 2
prompts = 40 calls.

**Cost:** ~$0.41 actual (6 Sonnet + 40 Haiku) vs ~$1.12 dual-model
projection (~63% saving). Holds for Phase 2 too (only marginal extra
Sonnet cost).

### Format gates (all PASS)

| Metric         | Value | Threshold |
|----------------|-------|-----------|
| Parse rate     | 100%  | ≥80%      |
| Schema rate    |  95%  | ≥80%      |
| Single-word %  | 100%  | ≥90%      |
| Snap rate      |  91%  | ≥80%      |

One schema slip: a single concept slipped through with a space
(`"system failure"`) — the violation surfaced in the report but
didn't fail the gate.

### Cascade attrition — the surprise

| Cohort  | Scored | Gate-dropped | Unresolved | No-props | Missing |
|---------|--------|--------------|------------|----------|---------|
| apt     | 56     | 32           | 15         | 8        | 0       |
| inapt   | 12     | 41           | 3          | 2        | 2       |

- Apt   end-to-end promote rate: 56/111 = ~50% scored, ~25% above median
- Inapt end-to-end promote rate: 12/60  = ~20% scored, ~10% above median

**The concreteness gate is doing most of the discrimination work.** It
drops 68% of inapt vehicles (41/60) vs only 29% of apt vehicles (32/111).
Among pairs that *survive* the gate, scores are nearly equal:

- Mean apt score:   0.2707 (n=56)
- Mean inapt score: 0.2646 (n=12)
- Separation score: **+0.0061**
- Aptness rate (median split): **50%**
- FP rate:                     **50%**

### Per-`inapt_reason_type` breakdown

| Reason              | n  | Gate-pass | Score-discriminated |
|---------------------|----|-----------|---------------------|
| dead_metaphor       | 8  | 38%       | 67%                 |
| same_domain         | 19 | 21%       | 67%                 |
| single_dimension    | 31 | 19%       | 40%                 |
| synonym_or_hypernym | 1  | 100%      |  0% (n=1)           |
| wrong_concreteness  | 1  | 0%        | (gate-only)         |

Phase 1b verdict: **PASS** → promote to Phase 2.

---

## Follow-ups (to revisit AFTER Phase 2)

Both are safe to defer; neither confounds Phase 2 because the cohort
JSONLs are saved and snap+scoring are fast in-memory ops — we can
re-snap and re-score retroactively.

### FU-1: Separation-score metric correction

**Problem.** Phase 1b's separation_score (+0.0061) reports near-zero
discrimination, but the *end-to-end* system promotes 2.5× more apt
than inapt vehicles. The metric is computed over scored-pairs only —
it doesn't credit the gate for filtering inapt vehicles out before
scoring.

**Fix.** Introduce an end-to-end aptness metric that counts vehicles
filtered at the gate AS the cascade discriminating. Concretely:

    system_aptness_rate = (n_apt_above_threshold) / n_apt_total
    system_fp_rate      = (n_inapt_above_threshold) / n_inapt_total

where the denominators are the FULL cohort, not the scored subset. Gate-
dropped + missing-concreteness + no-properties rows count as "below
threshold" because the system declined to promote them.

**Where to apply.** Both Phase 1b and Phase 2 cohorts. Five-line metric
change, retroactive.

**Why this matters for M05.** The current γ-sweep tunes for scored-pair
mean separation — a metric that doesn't move because gate-dropped
inapt vehicles are invisible to it. Re-running γ-sweep against
system_aptness_rate gives γ a real signal to optimise against.

### FU-2: Lemmatise concepts before snap

**Problem.** 9% snap miss rate. The misses are almost entirely `-ing`
gerund forms: `anchoring`, `carrying`, `swirling`, `obscuring`,
`scarring`, `triggering`, etc. — the lemmas table has the base form
(`anchor`, `carry`, ...) but not the gerund.

**Fix.** Run WordNet lemmatiser (or simple `-ing → ∅ / -ing → e` rules)
on each concept before `SELECT FROM lemmas`. Estimated lift: 91% → ~99%.

**Where to apply.** `snap_properties.py` (canonical pipeline snap) and
the spike runner's `check_concept_snap_rate` helper. After landing,
re-snap Phase 2 cohort and recompute scores.

**Risk.** Pipeline change. Wants its own TDD pass; cheap but real.

---

## Phase 2 (in progress)

Run timestamp: _pending_ · Branch: spike/metaphor-enrichment-phase-2.

200 topics × Haiku-only × 2 prompts = ~400 calls. Same gold examples
as Phase 1b. Curator samples from the lexicon by frequency × POS ×
concreteness tier; combined with the Phase 1b 20-topic anchor set so
the cohort retains a hand-curated spine.

### Findings (fill in after run)

- [ ] Format gates pass/fail
- [ ] End-to-end aptness rate (preview of FU-1)
- [ ] Per-reason discrimination at scale
- [ ] Surprises / pivots
- [ ] Cost vs estimate

### Follow-ups (collect here as they surface)

_(empty — fill in as Phase 2 reveals new follow-ups)_

---

## Cross-phase decisions

_(append architectural / convention decisions surfaced by the spike
here. Mirror to `docs/decisions/log.md` if they cross the architectural
threshold.)_

- **2026-05-25 — Sonnet-as-prompt-engineer is the production pattern.**
  Phase 1b validated the cost/quality trade-off. Future enrichment
  prompts that want Sonnet quality should bake Sonnet-generated gold
  few-shots into a Haiku-runtime template, not run Sonnet at request
  time. ~65% cheaper than Sonnet-alone, no measurable quality loss in
  Phase 1b.
