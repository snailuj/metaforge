# Farm-out model bake-off — can we generate metaphors off Sonnet, cheaper?

**Date:** 2026-07-02
**Branch:** `generation/emit-the-sense` (isolated worktree `.worktrees/stock-gen`)
**Status:** Complete. Verdict is definitive.

## TL;DR

We tested whether metaphor generation can move off the expensive Claude Sonnet
path onto a cheaper model (DeepSeek Flash, GLM 5.2, or Claude Haiku) without
losing quality. **Answer: no cheap drop-in preserves Sonnet's liveness.** Live-rate
tracks model capability — Sonnet 0.224 → Haiku 0.129 → open models ~0.09 — with a
Claude-family bonus for Haiku. The quality lives in the **chain-expansion** stage,
not vehicle proposal, so no hybrid rescues it. The only two viable paths are the
extremes: **keep Sonnet**, or **Flash + overgenerate + judge-filter** (~30× cheaper
for equal absolute live yield) — and the second hinges entirely on having a good,
cheap live/dead judge.

## Question

Generation on Sonnet is the dominant cost (~$0.03/topic, ~$290 for a 10k run) and
sits on the rate-limited Claude subscription. Can we farm it out to a cheaper /
open-weight model — or a cheaper Claude tier — without a quality regression, where
"quality" = the rate of **live** (apt, vivid, cross-domain) metaphors?

## Method

- **Topics:** 100 sampled from the existing Sonnet stock corpus (`chain-topics_stock_emit.jsonl`),
  sense-pinned by gloss so every arm starts from the identical topic sense.
- **Arms (proposer + expander):** the Sonnet baseline is reused from the stock corpus
  (zero Claude re-spend). Flash/GLM generated fresh, full-pipeline and hybrid (Haiku
  proposals + open expander, via a shared Haiku proposal dump). Haiku+Haiku added last.
- **Judge:** the calibrated liveness proxy (`metaphor_live_rate.build_judge_prompt`),
  **one chain per call**, run per-chain via OpenRouter Sonnet. Checkpointed/resumable.
- **Controls held fixed across arms:** identical topics + senses, identical Haiku
  proposal dump (hybrids), identical chain-expansion prompt, identical judge. Only the
  expander model varies.

## Result — six arms, per-chain Sonnet judge

| proposer + expander | live-rate | 95% CI (Wilson) | n |
|---|---|---|---|
| Haiku + **Sonnet** (baseline) | **0.224** | [0.199, 0.251] | 983 |
| Haiku + **Haiku** | **0.129** | [0.109, 0.151] | 996 |
| Haiku + GLM | 0.103 | [0.085, 0.125] | 863 |
| Haiku + Flash | 0.091 | [0.074, 0.110] | 971 |
| Flash + Flash | 0.089 | [0.073, 0.108] | 980 |
| GLM + GLM | 0.082 | [0.066, 0.101] | 940 |

## Findings

1. **Farming out to open models is a large, definitive liveness regression.**
   Flash/GLM produce ~0.09 vs Sonnet's 0.224 (`z ≈ -7.5, p ≈ 0`) — **~40% of the
   baseline rate, a ~60% cut.** Earlier underpowered / lenient-judge reads
   ("roughly competitive") badly understated this.

2. **The deficit is in the chain-*writer*, not the vehicle-*proposer*.** Feeding the
   open models the identical Haiku proposals barely moved them (Haiku+Flash 0.091 ≈
   Flash+Flash 0.089, `p=0.90`; Haiku+GLM vs GLM+GLM `p=0.08`). A hybrid that keeps a
   good proposer but farms out expansion does **not** recover liveness.

3. **Liveness tracks model capability, with a Claude-family bonus.** Haiku-as-expander
   lands cleanly in the middle: 0.129 — below Sonnet (`p ≈ 0`, only 57% of its rate)
   but significantly above the open models (`p = 0.007`). So the expansion edge is not
   purely Sonnet-tier-specific, but nothing cheaper comes close to matching it.

4. **Flash ≈ GLM on every axis** — liveness (`p=0.59` full / `0.25` hybrid), gloss
   accuracy (rank-correlation ≈ 0 across two judges), diversity (both at the floor).
   Interchangeable; the choice between them was only ever cost/structure.

## Strategic conclusion

There is no cheap drop-in. The two genuinely viable paths are the extremes:

| path | live/topic | ~cost/topic | cost for equal *absolute* live yield |
|---|---|---|---|
| Sonnet | 0.224 | ~$0.030 | ~$0.030 (1×) |
| Haiku | 0.129 | ~$0.010 | ~$0.017 (1.7× topics) — only ~1.7× cheaper |
| Flash | 0.089 | ~$0.0004 | ~$0.001 (2.5× topics) — **~30× cheaper** |

1. **Keep Sonnet** — quality floor, highest cost.
2. **Flash + overgenerate + judge-filter** — ~30× cheaper for the same absolute live
   count, but contingent on (a) a good, cheap live/dead judge to filter the extra dead
   chains, and (b) whether Flash's "live" ones are as good as Sonnet's "live" ones (the
   binary rate is blind to within-live quality).

Haiku is the trap in the middle — barely cheaper than Sonnet once you account for
overgeneration. **Both roads lead back to the live/dead judge as the real lever.**

## Methodology notes (hard-won)

- **Batching drifts the liveness judge lenient.** Judging many metaphors in one context
  anchors the model toward "all plausible": batch-20 scored the baseline 0.40, subagent
  batch-250 scored 0.55, vs the calibrated per-chain ~0.22. The calibrated instrument
  **requires one chain per call**. (`data-pipeline/scripts/batch_liveness_judge.py`
  carries this caveat; it's bulk-triage only.)
- **Judge transport:** per-chain OpenRouter Sonnet (fast, calibrated, metered) beats the
  subscription `claude_client` here (slow, 429-limited, self-competes with the session).
  Reserve metered API for the models genuinely under test + this kind of calibrated
  measurement; use in-session/subscription for offline instrument work.
- **OpenRouter reserves credit for the full `max_tokens`** — uncapped judge calls (model
  default ~65536) 402 once the balance is low, even though a verdict is ~50 tokens. Fixed
  by an optional `max_tokens` cap in `lib/openai_client.py` (judges cap at 256/512).

## Artifacts / reproduction

- Harness: `data-pipeline/scripts/bakeoff.py` (`proxy_live_rate`, per-chain, checkpointed);
  provider-agnostic generation via `generate_metaphor_edges.py --provider/--base-url/--reasoning-off`.
- Data (not committed — reproducible, `data-pipeline/output/bakeoff/`): `stock100_*.jsonl`
  (six arms), `judge/or_verdicts/*.liverate.jsonl` (per-chain verdicts), `stock100_haiku_proposals.jsonl`.
- Cost measured from real token usage; open-model slugs verified on OpenRouter 2026-06-27.
