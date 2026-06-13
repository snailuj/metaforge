# Stage-2 liveness judge — first calibration (sonnet): MARGINAL PASS

**Run:** 2026-06-12/13, `judge_harness --axis liveness --judge stage2 --n-repeats 5` (k_shot 6, seed 0),
model **sonnet 4.6**, gold = grading-live `judgements_provisional.jsonl` (the 9-record vintage layer
re-graded; 127 live/dead rows / 30 topics), code at `19ed1540`. 565 pooled judgements (113/repeat),
**zero abstentions** — the mechanical path (prompt → CLI → strict JSON → cache → checkpoint/auto-resume)
ran flawlessly through a session-limit halt + auto-resume mid-run. Result JSON committed beside this note.

## Verdict

| metric | value | gate |
|---|---|---|
| κ (pooled, 5 repeats) | **0.332** | ≥ 0.3 — **PASS (marginal)** |
| κ band [p5, p95] | [0.278, 0.370] | well clear of 0 (not "underpowered/unusable"); toe just under 0.3 |
| accuracy | 0.667 | majority baseline 0.566 |
| human ceiling (operator blind self-κ, liveness) | 0.47 | judge captures ~70% of the learnable signal |

Per-repeat κ: 0.361 / 0.371 / 0.283 / 0.367 / 0.277 — stable "fair" band, not draw-noise.

Confusion (rows = gold, cols = judge; n=565):
- gold **dead** (245): → 165 dead / 80 live  (67% specificity)
- gold **live** (320): → 108 dead / 212 live (66% recall)

Symmetric ~⅓ error each direction. This is a **fair** judge (Landis–Koch 0.21–0.40), not a strong one.

## Reading

**The Phase-A kill-gate does NOT fire.** Its question was "is liveness so unjudgeable that scaling
is pointless?" — the catastrophic case (κ→0, same failure as the broken extractor). The answer is a
clear no: κ 0.33, band comfortably positive, errors symmetric and well above chance.

**But this is a first, untuned point — not the final judge.** One model (sonnet), one prompt (Forge
Reader persona v1, never iterated), k=6 few-shot, no sweep. The human ceiling is 0.47, so there is
**real headroom we have not tried to close**: k-sweep (plan flags k≈20, which also crosses the
caching threshold), prompt/persona iteration (the operator is the taste source — his edits may move
this more than any hyperparameter), and a haiku baseline to quantify the model lift. Per the plan:
"A/B model+k via the κ harness, not blind hand-tuning." None of that is done.

## Contrast with Stage-1

Stage-1 (construction) FAILED both model arms (haiku 0.169, sonnet 0.131) — bad-linkage is not
judgeable from chain text by two model classes, and the defect (wrong-word-as-head) has 0/44
mechanical recall. Stage-2 (liveness) operates on the **(topic, vehicle) pairing only**, never sees
the corrupted intermediates, and clears its floor. This vindicates the orthogonal two-stage design:
the gate that matters for a pairing-corpus is Stage-2, and Stage-2 is the one that passed.

## What it unlocks (and what it does not)

- **DOES:** judge-assisted labelling — Stage-2 triages live/dead at ~67% accuracy, prioritising the
  operator's grading attention (active learning) rather than replacing it. A meaningful multiplier
  over grade-everything-by-hand.
- **DOES NOT (yet):** autonomous manufacture of pristine 10³–10⁴ training edges. At κ 0.33 the
  harvested labels carry ~⅓ disagreement with the operator; a completion algorithm trained on them
  inherits that noise floor. Closing the gap to ~0.47 (the operator's own ceiling) via tuning is the
  prerequisite for trusting the judge as a standalone edge-harvester.

Economics note (`2026-06-12-api-economics.md`): all judge tuning is single-digit dollars **anytime** —
zero window-urgency. The only June-15-urgent item is generation.
