# Karpathy Loop 1 — Findings

**Status:** Done (paused for operator review). 13 iterations, +28.7% Phase 2 median, Lakoff held flat.

**Cross-refs:**
- Pre-flight design: [`2026-05-25-karpathy-loop-prep.md`](2026-05-25-karpathy-loop-prep.md)
- Spike findings (FU-1/2/3 origin): [`2026-05-25-metaphor-spike-findings.md`](2026-05-25-metaphor-spike-findings.md)
- Branch: `loop` (cut from main at `88655cfd`, currently at `840c351d`)

## Scoreboard

| Iter | Hypothesis | Phase 2 | Lakoff | Outcome |
|------|------------|---------|--------|---------|
| 0    | loop launch baseline | 2.3512 | 0.6000 | — |
| 1    | WordNet lemmatiser fallback in `lookup_primary_synset` (FU-2) | 2.4097 (+2.5%) | 0.6000 | committed |
| 2    | noun-POS preference in lemma resolution (operator-promoted from iter-2 disowned diff) | 2.7001 (+12.1%) | 0.6000 | committed |
| 3    | sqrt-shape rerank bonus | regressed Lakoff | — | reverted |
| 4    | `rerank_exponent=0.75` (mild sqrt curve as new tunable knob) | 2.8621 (+6.0%) | 0.6000 | committed |
| 5    | `d_cap` 0.77 → 0.65 | 2.9494 (+3.0%) | 0.6000 | committed |
| 6    | `d_cap` 0.65 → 0.68 (interior probe) | 2.9534 (+0.1%) | 0.6000 | committed |
| 7    | broad d_cap/exp sweep (7 probes) | no win | — | reverted |
| 8    | d_cap=0.69 + 3 exponent probes | no win | — | reverted |
| 9    | ortony scoring swap via default (no-op — harness pinned) + d_cap probes | no win | — | reverted |
| 10   | concreteness-magnitude bonus on signed delta beyond gate (operator-promoted after test-gate auto-revert; tests updated to set `concreteness_bonus_coef=0.0`) | **3.0264 (+2.5%)** | 0.6000 | committed |
| 11   | absolute vehicle concreteness bonus | regressed Lakoff (cohort inversion) | — | reverted |
| 12   | `ortony_exponent` compression | regressed Phase 2 | — | reverted |
| 13   | `rerank_floor` deadzone | regressed both | — | reverted |

**Cumulative**: Phase 2 median **2.3512 → 3.0264 (+28.7%)**. Lakoff held at **0.6000** every single iteration — neither helped nor harmed by any global cascade tweak.

**Total iteration outcomes**: 6 committed wins, 7 informative reverts.

## Two cohort-divergence findings (the loop's biggest insight)

Iters 11, 12, 13 — three fresh agents with no shared context — all independently surfaced this pattern. It is now the load-bearing constraint for future loop design.

### Cohort 1 — Phase 2 (1112 apt + 600 inapt, LLM-generated, noisy)

- Apt vehicles cluster around `c=4.52`, inapt around `c=3.60` (Δ +0.92 on concreteness).
- Apt cosine distance median ~0.20, inapt ~0.18 (both far below `d_cap=0.68`).
- Apt-vs-inapt scored-pair separation is small but positive on the rerank bonus (Δ≈0.026 in cohort means).
- **Discriminator profile:** needs Ortony scoring to discriminate noisy machine-generated pairs cleanly; benefits from concreteness-magnitude lift; sensitive to small d_cap / exponent moves in the bootstrap-resample tails.

### Cohort 2 — Lakoff (80 apt + 90 inapt, hand-curated classics)

- Apt vehicles cluster around `c=4.47`, **inapt around `c=4.79`** (Δ −0.32 — inverted!). Inapt vehicles like "umbrella for anger" are *deliberately* concrete-but-mismatched.
- Apt cosine distance ~0.19, inapt ~0.24 (apt is closer than inapt — the OPPOSITE of Phase 2 where inapt is closer).
- **Discriminator profile:** clean cosine separation, benefits from distance-based amplification; structurally adversarial to any vehicle-concreteness bonus (inverts the desired direction); benefits from ortony compression (where Phase 2 is hurt by it).

### The implication

**A single global cascade-knob change cannot lift both cohorts indefinitely.** The reverted iterations are not "failures of the cascade" — they are correct rejections of moves that improved one cohort while degrading the other. The loop's commit gate (Phase 2 must improve AND Lakoff must not drop >5%) enforces this discipline mechanically.

What this means for any successor loop:

1. **Either accept the asymmetry** and stop chasing dual-cohort moves — promote loop-1's commits to main, declare done.
2. **Or break out of "global cascade tweak" framing** with one of:
   - Cohort-aware switching: the cascade detects which regime it's in (e.g. via a property-overlap floor) and applies different rerank shapes.
   - New algorithmic surface: `snap_properties.py` (entirely untouched by loop-1), `_get_properties` salience filtering, new derived caches alongside the canonical DB.
   - Harness modification (operator-supervised): test individual cohort metrics independently rather than requiring both to move together.
3. **Or change the metric.** The current bootstrap-median commit gate has discrete-plateau structure (iter 7 / 8 / 9 noted this) and the Lakoff cliff at d_cap≈0.65 is a single binary pair flip (5/80 → 4/80). A smoother metric — full-cohort ratio, or apt-promotion rate alone with a separate Lakoff non-regression assertion — might give finer resolution.

## Plateau structure (the local-optima map)

Knowledge that will save future iterations time:

- **`d_cap`, `rerank_exponent`** (the two CascadeConfig fields not pinned by harness) — explored densely across iters 4–9. Current `(d_cap=0.68, rerank_exponent=0.75)` is a sharp local optimum. Adjacent integer-step probes all regress Phase 2 OR cross the Lakoff cliff. Don't re-explore without a structural change.
- **`alpha`, `composition`, `concreteness_threshold`, `ortony_scoring`** — pinned by `PRODUCTION_CASCADE_CONFIG` in the immutable harness. Changing CascadeConfig defaults for these is a no-op. Requires escalation.
- **`_jaccard_salience` body** — pytest pins exact values in `test_evaluate_aptness.py:480-499`. Modifying the scorer body fails the orchestrator test gate. Requires either updating tests (operator call) or working around the scorer.
- **`concreteness_bonus_coef`** (iter 10's new field) — operator-promoted at 0.002 (largest tested coef that preserves Lakoff). Iter 10's own probes showed Lakoff cliff at coef≈0.0025, Phase 2 lift up to 24% with coef=0.05 if Lakoff weren't a constraint.

## Loop infrastructure that landed

Built during loop-1 (operator-side, on loop branch, not iteration-generated):

- `evaluate_loop_metric.py` — immutable end-to-end ratio + bootstrap + commit-gate evaluator. 16 unit tests.
- `evaluate_loop_harness.py` — immutable harness that scores cohorts and emits structured PASS/FAIL. 5 loader tests.
- `loop_iter_wrap.py` — orchestrator wrapper. Pre-hook snapshots DB + chmod-locks immutables. Post-hook runs pytest + go test, hash-checks DB, hard-resets on revert, refreshes baseline on clean commit. ~430 lines.
- `.worktrees/loop/` worktree isolation, symlinks for DB / venv / vectors.
- Go deadlock fix in `getSynsetRowsBatch` (chunked LEFT JOIN + MIN aggregation) — unblocked `TestCascadeUnion_ClassicalPairsSurface_AsCandidates`.
- `TestCascadeUnion_LatencyBudget` skipped pending FU-LATENCY-BUDGET (5s vs 750ms target on pristine main — pre-existing perf regression, unrelated to loop).

These all stay on the loop branch as infrastructure-for-the-next-loop. Worth merging to main if loop-2 is planned.

## Decision points for loop-2 (if there's a loop-2)

If the operator wants another round, the high-leverage moves I'd propose:

1. **Merge loop-1 wins to main first.** 6 commits, +28.7%, clean diff. Lock in the gain before chasing more.
2. **Add a third cohort.** The Phase 2 / Lakoff asymmetry is now a binding constraint; a third independent cohort would either (a) give a tiebreaker or (b) reveal which cohort is the outlier. Cohort candidate: a held-out subset of the M01 evaluation set with different domain mix.
3. **Loosen the harness on `ortony_scoring`.** The SCORING_FNS registry has 6 unused variants. Iter 9 tried to swap via defaults and discovered the harness pin. An operator-blessed harness change to make `ortony_scoring` a per-call parameter (rather than a pinned default) opens that whole subspace.
4. **Try `snap_properties.py`** — the loop never touched this 800-line file. Salience curves, embedding threshold, morphological normalisation — all uncharted. Different layer of the cascade than rerank.
5. **Operator-prompt hint becomes part of the contract.** The "git log --oneline -15" nudge in the iter-10+ prompt worked — it pushed agents off the rerank plateau into the concreteness-bonus space. Future iterations should always include "if you see 2+ recent reverts on the same axis, pick a different layer".

## Cost

Rough Anthropic credits estimate (13 iterations × ~$0.10-0.30 each + operator orchestration):
- Iteration agents: ~$2-4
- Orchestrator (me) running pre/post hooks, dispatching, light-reviewing, recovering iter 10: ~$5-10 (this is the dominant cost)
- Total: ~$10-15 for +28.7% Phase 2 lift.

Per-iteration metric movement averages ~$1.50-2.50 per percentage point of Phase 2 lift. Diminishing returns are visible in the recent reverts.
