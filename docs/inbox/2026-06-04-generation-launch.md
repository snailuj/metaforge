# Metaphor-edge generation — launch & handover (2026-06-04)

Built + reviewed + validated this session. The continuous chain.v1 generation runner, the
proxy-judge live-rate tripwire, and the LLM sense-disambiguation pass are on branch
`metaphor-graph/enrich-stage-a` (the consolidated Stage-A run branch). All JSONL-native
(grading-tool consumes the round files directly); DB ingestion deferred per the 2026-06-04 call.

## What runs where

| Piece | Command (from repo root, run branch `metaphor-graph/enrich-stage-a`) |
|---|---|
| **200-loop (round 2)** | `data-pipeline/.venv/bin/python data-pipeline/scripts/generate_metaphor_edges.py --topics data-pipeline/output/generation_topics_200.json --output data-pipeline/grading/sonnet_chains_provisional_r2.jsonl --db data-pipeline/output/lexicon_v2.db --haiku-jsonl data-pipeline/output/metaphor_spike_apt_phase2_20260525T004154.jsonl --round 2 --batch-size 20 --autocommit-every 1` |
| **disambiguation → 10k topics file** | `data-pipeline/.venv/bin/python data-pipeline/scripts/metaphor_disambiguate.py --db data-pipeline/output/lexicon_v2.db --limit 10000 -o data-pipeline/output/generation_topics_10k.json` |
| **10k generation (Julian-launched, multi-day)** | as the 200-loop but `--topics …_10k.json --output …_r2_10k.jsonl --max-topics 10000 --max-cost-usd <cap>` (live Haiku — drop `--haiku-jsonl`) |

The 200-loop reuses the stored Haiku apt dump (no Haiku re-spend → Sonnet-only). The 10k run
generates Haiku fresh (no stored dump for new topics).

## Cost ladder (deterministic via --max-topics)
- 200-loop (Sonnet-only, ~10 vehicles each): **~$40–50**.
- disambiguation → 10k: **~$20–50 one-time** (batched Haiku; single-sense lemmas free).
- 10k generation (Haiku+Sonnet, ~$0.25/topic): **~$2.5k, multi-day** — Julian's switch.

## Safety brakes (both hardened in the pre-spend review)
- **`--max-topics`** — hard deterministic cap (topic-count). The real budget bound.
- **`--max-cost-usd`** — soft guard, charged at point-of-spend (no longer fails open on an
  all-error tail), checked in-loop (overshoot ≤ ~1 topic).
- **live-rate tripwire** — pauses on absolute-floor (near-total collapse) OR relative-drop from
  a frozen baseline; fed synthetic-dead on zero-record batches; judge-samples one-per-topic.
  Default `--tw-abs-floor 0.08` is a COLLAPSE line, NOT a quality bar — **calibrate below the
  measured healthy live-rate** (see below).
- Resume is idempotent: completed topics (in the JSONL) + spent-and-empty topics (`.attempted`
  sidecar) are skipped; transient errors retry. A crash/restart never double-bills.

## Tripwire calibration (from the smoke)
Proxy-judge (Haiku, conservative) **healthy live-rate ≈ 0.20** on validated good chains
(n=5 smoke sample: 1 live `deadline→fuse`, 4 conservative-dead). The default
`--tw-abs-floor 0.08` sits safely below this → no fail-closed on healthy output. The
relative-drop arm (`--tw-rel-drop 0.4`) catches a sag from the frozen baseline. As the
200-loop runs, refine: read `live_rate_window` from the batch log once it stabilises and, if
it settles well above 0.08, you may raise `--tw-abs-floor` to ~half the stable rate.

Judge cost/latency: ~19s per Haiku judge call (retries capped at 2 — a flaky judge fails fast
and is skipped, never a retry storm). At `--judge-sample 3` that's ~1min of judging per batch
of 20 — Sonnet generation dominates wall-clock.

## Monitoring a live run
- Per-batch log line: `batch N: {chains_written_total, est_cost_usd, elapsed_s, live_rate_window}`.
- `paused`/`pause_reason` in the final summary JSON (`tripwire` or `cost_cap`).
- Output grows append-only; re-running resumes. To feed the LIVE grading tool, the round JSONL
  must reach `.worktrees/next/data-pipeline/grading/` on branch `grading-live` (deploy step,
  separate from the run branch).

## Known follow-ups (captured in PIPELINE inbox)
- 1 topic dropped (`ideas` — plural, no noun sense; lemmatise to `idea` if wanted).
- Cross-file/cross-round `chain_signature` dedup belongs in the grading consumer.
- DB `metaphor_judgments.label` is v1; reconcile before JSONL→DB judgment ingestion.
