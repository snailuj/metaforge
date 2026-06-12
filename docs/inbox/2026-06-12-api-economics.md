# API economics — post-June-15 cost model for the metaphor programme

**Context:** subscription usage policy changes 2026-06-15; assume worst case = all LLM compute at API
list price thereafter. All figures below are grounded in **measured** data: the 2026-06-03 generation
cost harness (n=5 Haiku / n=3 Sonnet, CLI-billed), the 200-topic loop's real spend, and offline
token-measurement of the actual judge prompts (2026-06-12, k=6 few-shot, chars/3.8). API prices:
Haiku 4.5 $1/$5 per MTok in/out, Sonnet 4.6 $3/$15, Opus 4.8 $5/$25; Batches −50%; cache reads 0.1×.
Key transfer factor: CLI-measured costs ≈ **2× API-direct** (the CLI bills its own system-prompt
overhead per call) — the generation report's "≈ halved API-direct" is applied throughout.

## 1. Unit costs (API-direct)

| Workload | Measured size | Haiku 4.5 | Sonnet 4.6 | Batched (−50%) |
|---|---|---|---|---|
| Judge call, Stage-1 (construction) | ~800 tok in / 10 out | $0.0009 | $0.0026 | $0.0004 / $0.0013 |
| Judge call, Stage-2 (liveness pairing) | ~650 tok in / 10 out | $0.0007 | $0.0021 | $0.0004 / $0.0011 |
| Calibration sweep (342 calls, à la today) | ~0.5M tok in | ~$0.50 | ~$1.50 | n/a (interactive) |
| Generation, full topic (Haiku propose + Sonnet chain) | ~6k + ~9–14k out tok | — | **$0.10–0.15/topic** | $0.05–0.08/topic |
| Generation, Haiku-only propose | ~5.8k out tok | **~$0.03/topic** | — | ~$0.016/topic |

**Caching caveat (measured):** the judge's stable prefix is only ~490 tok (S1) / ~300 tok (S2) —
*below every model's minimum cacheable prefix* (Sonnet 4.6: 2,048; Haiku 4.5: 4,096). Prompt caching
contributes **nothing** to judge economics unless we deliberately fatten the fixed few-shot block past
the threshold (viable at k≈20+ on Sonnet; evaluate only if κ also benefits). Batches is the real lever.

## 2. Programme-scale totals

| Item | Volume | API-direct | Batched |
|---|---|---|---|
| Judge ablation sweeps (k/model/prompt, ~10 more runs) | ~3.5k calls | ~$5–15 | — |
| **10³ completion-training verdicts** (2-stage, Sonnet) | 1k chains | ~$4.7 | ~$2.4 |
| **10⁴ completion-training verdicts** (2-stage, Sonnet) | 10k chains | **~$47** | **~$24** |
| Auto-triage of Phase B output (Stage-1 Haiku gate + Stage-2 Sonnet on survivors) | ~10k chains | ~$9 + ~$21 | ~$15 total |
| **Phase B generation** (1k demand-curve topics, ~10 chains/topic) | 1k topics | **$100–150** | $50–80 |
| Phase C generation (held 10k run, 7.5k topics) | 7.5k topics | $750–1,100 | $380–560 |
| Full 15–35k frontier (audit figure, API-direct) | — | $1.5–5k | $0.8–2.5k |

**Headline:** the audit's "judge is the cheap multiplier" claim survives contact with measured prices,
hard. Even the full 10⁴-verdict completion-training corpus costs **less than $50** — pocket change
next to generation. The June-15 cliff is **only material for generation**: Phase B is the one item
where the remaining subscription window saves real money ($100–290 equivalent); every judge-side
workload is single-digit dollars on the API whenever we run it.

## 3. Local steady-state crossover (RTX-3060-class, Qwen, ~3.5M tok/day)

Generation is output-token-dominated (~15–20k tok/topic) → a 3060 yields ~**175–250 topics/day** at
~$0 marginal. Phase C equivalent: ~30–40 days local vs $380–1,100 API. Crossover: local wins whenever
(a) >~$300/month of sustained generation, or (b) timeline tolerance ≥ weeks — both true of the
steady-state corpus build. API wins for **iteration speed** (prompt experiments, calibration, anything
gated on a human decision). The distilled judge (product runtime) was always local per the
sovereignty constraint, so judge *serving* costs trend to ~$0 regardless. Pending: the on-device
feasibility spike must validate quality, not throughput — throughput is already sufficient on paper.

## 4. Recommendations

1. **Race exactly one thing before June 15: Phase B generation** (if Stage-1 clears its gate, per
   PIPELINE). It is the only sub-fundable item worth >$20, and at ~1–2 days wall-clock under session
   caps it consumes the whole window — start within hours of the gate read, run via the existing
   autonomous wrapper (`run_generation_loop.sh`).
2. **Do not panic-spend the window on judge work.** Calibration sweeps cost ~$1.50 each on the API;
   front-loading them buys nothing meaningful and competes with Phase B for the serial session.
3. **Post-15th defaults:** judge runs API-direct (interactive) or Batched (bulk labelling);
   generation → Batches API at −50% for any API-side runs; evaluate the local-Qwen path before
   committing to Phase C on API.
4. **Design note for the production judge:** if Stage-2 lands on Sonnet, a k≈20 fixed few-shot block
   would cross the 2,048-tok caching threshold → bulk-labelling input cost drops ~10× on the prefix.
   Test κ at k=20 in the same sweep that tests it for accuracy.
5. **Assumption to verify with the operator:** "usage policy changes" = worst case (no more flat-rate
   CLI compute). If the sub retains *any* metered allowance, items 1–2 relax accordingly.

*Scripts: /tmp/judge_econ.py (prompt measurement); generation figures from
`docs/inbox/2026-06-03-context-free-edges/FINAL_REPORT.md` §cost-harness and the 2026-06-04
generation-launch notes. No LLM spend incurred for this memo.*
