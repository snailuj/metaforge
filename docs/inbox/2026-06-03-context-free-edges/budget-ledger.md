# BUDGET LEDGER — investigation API spend (final)

Tracks `claude` CLI calls made *during the investigation*. Analysis/derivation/separability/recall/graph-traversal/red-team/fact-check work was **API-free** (SQL + numpy/sklearn on existing data). Metered spend below is the orchestrator's measurement + probe calls. Source of truth: `artifacts/generation_cost_log.jsonl` (per-call `total_cost_usd` from the CLI JSON).

| event | model(s) | calls | cost USD | note |
|-------|----------|-------|----------|------|
| CLI probe (PONG) | haiku | 1 | 0.073 | cache-creation 57,279 tok (G6) |
| Haiku vehicle-proposal measurement | haiku | 5 | 0.310 | $0.062 ± 0.017/call |
| Sonnet chain measurement | sonnet | 3 | 0.717 | $0.143 / $0.229 warm + $0.345 cold |
| LLM-judge feasibility (tiered) | haiku/sonnet/opus | 69 | 5.551 | n=12 chains × 3 tiers + resumable re-runs after timeouts; agreement vs Julian's verdicts |

**Grand total metered API spend: $6.65 over 78 calls.**

The judge probe dominates ($5.55) because the run timed out repeatedly (63s–214s/call) and the resumable harness re-issued calls across invocations; the *informational* content is n=12 chains × 3 model tiers. A production judge would be a single tier (Haiku or Sonnet), batched.

Orchestration (session compute, not separately metered): ~26 subagents across 4 workflows (P1 analysis, red-team, fact-check) + the main loop. No bare estimates entered Results without a `total_cost_usd` source.
