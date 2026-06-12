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

## Addendum — sonnet arm (2026-06-12, later): FAIL — Stage-1 CLOSED

Sonnet, same config: **κ 0.131, band [0.074, 0.179]**, accuracy 0.608 (majority 0.570), 342/342
scored, zero abstentions. Confusion good→[176, 19], bad→[**115**, 32]: sonnet misses **78% of
bad-linkage chains** — even more conservative than haiku (59% missed). Both model classes fail the
gate in the same direction. **Stage-1 is closed pending the extractor fix; do not prompt-tune past
two independent model classes.**

Two $0 follow-up diagnostics sharpen the conclusion:

1. **Mechanical head-mismatch detection: 0/44 recall.** Every gold `bad_head` row has its head
   present as a token of its phrase — the defect is choosing the WRONG word as semantic head, not a
   malformed extraction. No string heuristic covers it; it is a semantic judgement that two LLM
   classes also failed to reproduce from chain text alone.
2. **Cohort rates: the generation-side repair halved bad_head but did not solve it.** Graded chains
   by generation date: 2026-05-30 round (pre-fix) **54%** bad_head; 2026-06-04/05 rounds (post
   head-polarity clauses + sense disambiguation) **26–33%**.

Implication for the Phase B gate: the gate's purpose (protect the operator's grading attention and
the corpus from construction garbage) is NOT achievable by LLM triage or string filtering today, and
only partially achieved at source. However — bad_head corrupts INTERMEDIATES only (endpoints are
canonicalised); the Stage-2 liveness judge operates on the (topic, vehicle) PAIRING and never sees
intermediates. Under the forge-not-index purpose (the corpus is a distillation/few-shot asset of
judged pairings), Stage-2 is the load-bearing gate for Phase B, not Stage-1. Re-pointing the gate is
an operator decision, pending the Stage-2 read.
