# Stage-1 construction judge — first calibration arm (haiku): FAIL

**Run:** 2026-06-12, `judge_harness --axis construction --judge stage1 --n-repeats 3` (k_shot 6, seed 0),
model **haiku** (stage default), gold = grading-live `judgements_provisional.jsonl` (132 resolved / 30 topics),
code at `b4ee9b4b`. 342/342 judgements scored, **zero abstentions** (the mechanical path — prompt → CLI →
strict JSON → cache — is flawless). Result JSON committed beside this note.

## Verdict

| metric | value | gate |
|---|---|---|
| κ (pooled) | **0.169** | ≥ 0.4 — **FAIL** |
| κ band [p5, p95] | [0.122, 0.196] | entirely below the 0.2 stop-clause line |
| accuracy | 0.605 | majority baseline 0.570 — barely above |
| human ceiling (operator self-κ, linkage) | 0.63 | judge reaches 27% of ceiling |

Confusion (rows = gold, cols = judge): good→[146, 49], bad→[**86**, 61].
The judge **misses 59% of bad-linkage chains** (86/147 judged good) while false-flagging 25% of good ones.
Per-repeat κ is stable (0.114 / 0.196 / 0.196) — this is consistent blindness, not few-shot draw noise.

## Reading

This is the plan §7 pre-registered failure mode, now quantified: haiku replicates the known-blind
extraction evaluator (`head_extraction_broken_confirmed` — the in-loop Haiku triage judge was equally
blind to mis-extracted heads). κ 0.17 against a 0.63 human ceiling is a model/task failure, not label
noise: the gold's own reliability would cap an ideal judge near 0.63, and we are nowhere near it.

Per the plan: **κ < 0.2 ⇒ report and stop — the head-extractor fix is the real prerequisite.** Do not
prompt-tune past this.

## One in-plan arm remains before that conclusion is final

The plan's Stage-1 design includes a model sweep. The sonnet arm (~342 calls, cached, sub-funded)
distinguishes "haiku-specific blindness" from "construction quality is not judgeable from the chain text".
If sonnet also lands under the gate, the extractor-fix-first conclusion is confirmed from two independent
model classes and Stage-1 closes until the generation-side extraction is repaired.

Decision at time of writing: with the operator (sonnet arm vs immediate pivot to Stage-2 liveness
calibration, which is orthogonal by design and unaffected by this result).
