# Liveness judge re-measure after corpus sense-cleaning

**Date:** 2026-06-22
**Branch:** `metaphor-graph/judge-harness` (harness) · gold + corpus from `grading-data` @ promote commit `0402dde9`
**Axis:** Stage-2 liveness (`y_live`), sonnet judge

## Question

The corpus was sense-cleaned (gloss-backfill + FastText embedding re-snap), lifting
end-to-end endpoint snap accuracy **52% → 78%** on the 121 human sense-labels. The
Stage-2 judge renders the pairing as `topic (pos: gloss) -> vehicle (pos: gloss)`,
so a corrected endpoint sense changes the gloss the judge reads. **Did the cleaner
senses make the liveness judge agree with the operator more?**

## Method — controlled A/B (one variable: the endpoint sense shown)

- Both arms run **fresh on the current gold** (127 liveness rows, 30 topics). The gold
  changed since the historical κ=0.332 run (2026-06-12), so that number is not directly
  comparable — hence both arms re-run here.
- Identical config: `--judge stage2 --model sonnet --k-shot 6 --n-repeats 5 --seed 0`,
  leave-one-topic-out.
- **Unified gloss map** = union(pre-clean backup precompute, cleaned precompute); covers
  140/141 old and 144/145 new endpoint synsets, so **neither arm is gloss-starved**.
- Only difference between arms: each row's **vehicle** synset (→ vehicle gloss).
  Cleaning changed the vehicle sense on **62/127** pairings; **topic: 0 changed** (topics
  were already on their dominant sense) — so the LOTO folds are identical across arms.
- No harness code changed: data-prep (remapped gold + merged gloss file) + the existing
  CLI twice. Attribution pass is cache-only (free, 0 misses).

Worked example of a corrected sense — *anxiety → swarm* (gold: live):
`swarm (n: a group of many things in the air or on the ground)` →
`swarm (v: move in large numbers)` — the live reading.

## Result

| Arm | Cohen's κ | band [p5,p95] | accuracy | confusion `[[TN,FP],[FN,TP]]` |
|---|---|---|---|---|
| OLD sense | 0.297 | [0.262, 0.324] | 0.650 | `[[161,84],[114,206]]` |
| **CLEANED sense** | **0.335** | [0.278, 0.399] | 0.672 | `[[156,89],[96,223]]` |
| **Δ** | **+0.038** | — | +0.022 | FN 114→96 (recovered ~18 true-live) |

Majority baseline ≈ 0.566. The gain is concentrated in **recovering live metaphors the
judge previously called dead** (false-negatives 114→96) — consistent with the noun→verb
mechanism.

### Attribution (cache-only replay, n over 5 repeats)

| Subset | OLD acc | CLEANED acc | Δ |
|---|---|---|---|
| Changed-vehicle (the corrected pairings) | 0.607 | 0.668 | **+0.061** |
| Unchanged-vehicle (few-shot spillover only) | 0.691 | 0.676 | −0.015 |

The benefit lands **exactly where a sense was corrected** (+6.1pp). The cleaned exemplars
bleeding into the few-shot block of the untouched items were a wash (−1.5pp, noise).

## Interpretation

- **Direction confirmed, mechanism confirmed.** Cleaning the vehicle sense helps the judge
  on precisely the items it corrected (+6.1pp), by surfacing the intended (often verbal,
  active) reading a wrong lowest-id snap had hidden.
- **Aggregate lift is modest and underpowered.** Pooled κ +0.038 with overlapping bands —
  not significant at n=127. ~half the pairings were already correctly snapped, diluting the
  signal; the gold is small.
- **Not the unlock.** The judge is still at moderate κ≈0.335. Sense-cleaning is a net-positive
  contributor (and already promoted live at zero ongoing cost), but the bigger levers for the
  judge remain **more gold (statistical power)** and **prompt/persona tuning** — not further
  sense-work.

## Caveats

- Bands overlap → suggestive, not conclusive.
- The measure is holistic (item gloss + few-shot exemplar glosses both move); the attribution
  pass isolates the direct effect (+6.1pp on changed) from spillover (−1.5pp).
- Topic senses were already clean (0 changed), so this measures the *vehicle*-sense effect only.

## Reproduce

```
# from .worktrees/judge-harness/data-pipeline/scripts, main-checkout venv python
judge_harness.py --axis liveness --gold <EXP>/gold_old.jsonl     --grading-dir <EXP> \
  --judge stage2 --model sonnet --k-shot 6 --n-repeats 5 --seed 0 --cache <EXP>/judge_cache.jsonl -o result_old.json
judge_harness.py --axis liveness --gold <EXP>/gold_cleaned.jsonl --grading-dir <EXP> \
  --judge stage2 --model sonnet --k-shot 6 --n-repeats 5 --seed 0 --cache <EXP>/judge_cache.jsonl -o result_cleaned.json
# EXP = data-pipeline/output/liveness_resnap/ (gitignored; gold_*/gloss/cache built by the prep step)
```
