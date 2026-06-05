# Metaphor-edge generation — launch & handover (2026-06-04)

Built + reviewed + validated this session. The continuous chain.v1 generation runner, the
proxy-judge live-rate tripwire, and the LLM sense-disambiguation pass are on branch
`metaphor-graph/enrich-stage-a` (the consolidated Stage-A run branch). All JSONL-native
(grading-tool consumes the round files directly); DB ingestion deferred per the 2026-06-04 call.

## SESSION-4 UPDATE (session-limit fast-pause + NTFY + autonomous wrapper) — READ FIRST
The 429 churn is fixed end-to-end, and the multi-day run is now launch-once.
- **Client classifies a 429 session limit on sight** (`5093ff5f`): `claude_client._parse_events` raises `SessionLimitError` (carries the parsed reset time) instead of a generic retryable error — so the runner stops *immediately* instead of grinding each topic ×5 (~500 retries / ~2.5h per outage before). A confirmed 429 whose reset clause is missing/changed → `SessionLimitFormatError` (LOUD), so a server-side format drift halts visibly rather than degrading to a blind grind. `parse_reset_time` is deliberately strict (am/pm clock only).
- **Runner fast-pauses + notifies** (`a79a45d4`): `run()` catches `SessionLimitError` → `pause_reason="session_limit"` + reset fields in the summary; `SessionLimitFormatError` → `pause_reason="session_limit_unparseable"` + CRITICAL log. A `notify_fn` fires on **any** pause (tripwire/cost_cap/session_limit[_unparseable]).
- **NTFY on pause** (`512ea323`): `main()` pushes an ntfy alert on every pause via `notify_ntfy(format_pause_message(summary))`. Reads `NTFY_URL`/`NTFY_TOKEN` from env (token kept OUT of the repo — in gitignored `data-pipeline/.env.ntfy`); no-ops with a warning if unset; best-effort (never aborts the run). `main()` exits **2** on `session_limit_unparseable` so the drift reaches the shell/cron. Channel currently = `ntfy.julianit.me/vault-sync` (from crontab); change `NTFY_URL` for a dedicated topic.
- **Autonomous wrapper** (`2a72f37f`): `data-pipeline/scripts/run_generation_loop.sh` — launch once, walk away. Runs the generator, and on a graceful `session_limit` sleeps exactly until the parsed reset (via `parse_reset_time`), then resumes. Idempotent, so killing the wrapper never double-bills. Stops on completion/cost_cap (0), tripwire (3), unparseable (2). **This is the new 10k launch path** (supersedes the raw nohup command below).
- **200-loop:** finished/finishing — was 163/197 done (1617 chains) at this write, 31 remaining, completing in the open window. The fast-pause path is validated by tests + the prior cycles' real 429 storms (no false pause).

### 10k launch (NEW — autonomous wrapper)
```bash
cd /home/agent/projects/metaforge
# build the topics file first (SemCor-gated; see hold below), then:
nohup data-pipeline/scripts/run_generation_loop.sh \
  > data-pipeline/output/generation_loop.log 2>&1 &
```
Tunables are env vars at the top of the script (`TOPICS`, `OUTPUT`, `MAX_TOPICS=7500`, `MAX_COST_USD=2000`, `HAIKU_JSONL`, …). It sources `data-pipeline/.env.ntfy` for alerts. The raw single-shot command in the older block below still works for a one-window run.

## SESSION-3 UPDATE (tripwire false-trip fixed) — READ FIRST
- **Bug found via the 200-loop's own pause:** the run paused at batch 13 (`live_rate 0.028 < abs_floor 0.03`) on GOOD chains. Root cause: a session-limit **429 storm** (114 topics, $0 each) produced zero-record batches, and the runner fed those into the tripwire as synthetic-`dead`. The brake can't tell "Sonnet is producing dead metaphors" from "the API is down". `chains_written` froze at 137 from batch 2 while the live-rate decayed purely on synthetic-dead-from-429.
- **Fixed (`6b3cd03b`, TDD):** `generate_metaphor_edges.run()` now tracks **clean-empty** topics (model answered, answer barren — a real collapse signal) separately from **errored** topics (no verdict; retried on resume). Only clean-empty feeds synthetic-dead. Mirror RED test added (`test_run_tripwire_ignores_transient_errors`). This matters most for the **multi-day 10k run**, which crosses session-limit windows repeatedly and would otherwise false-pause on every reset.
- **200-loop status:** 50/197 topics done (490 chains, ~9.8 each, all well-formed); 3 genuinely spent-and-empty (`.attempted`); 144 remain. Resumed clean after the 15:00 UTC reset — session confirmed clear (chains writing). Real spend so far ≈ $3–4 (the est_cost $24 was ~$21 phantom 429 charges).
- **Known follow-up (NOT fixed):** cost-accounting still charges the per-topic estimate on a 429 (which actually costs $0) and on reused-Haiku (free via `--haiku-jsonl`). Safe direction for the spend brake (over-counts, never under), but `est_cost_usd` overstates real spend and a long 429 outage could falsely approach `--max-cost-usd`. Captured in PIPELINE inbox.

## SESSION-2 UPDATES (after Julian review) — READ FIRST
- **Tripwire recalibrated:** abs_floor 0.08→**0.03**, window→40, rel_drop→0.6. The 200-loop false-fired at 0.0625 on GOOD chains; measured healthy live-rate is ~0.10 (not the n=5 0.20). Re-measure per cohort; keep the floor well below the healthy band.
- **Disambiguation rebuilt resilient:** per-chunk checkpoint (`<output>.partial.jsonl`, flush+fsync) + resume + progress log + a free WordNet POS pre-filter (drops 12% verb/adj sneak-ins). The prior accumulate-in-memory version lost 2h25m on a kill.
- **⚠️ `claude` CLI session limit:** running 200-loop + disambiguation concurrently hit 429 "session limit · resets 10am UTC" ($0, resumable). **Run LLM jobs ONE AT A TIME**; the 10k run must lean on resume.
- **SemCor is the principled next step (HOLD the 10k disambiguation for it):** importing SemCor tagcounts from `sqlunet_master.db` gives true per-sense usage frequency → a proper POS filter (catches gerunds/`thaw`/`regard` the WordNet ratio misses) AND deterministic dominant-sense selection that replaces most LLM disambiguation (free/reproducible). Rebuild 10k selection on tagcounts once the DB is uploaded.

## LIVE STATUS (2026-06-04, end of build session)
- **200-loop (round 2): RUNNING** in background → `data-pipeline/grading/sonnet_chains_provisional_r2.jsonl`
  (Sonnet-only, stored-Haiku reuse; `--batch-size 10 --judge-sample 3`, tripwire on, caps 200 topics / $80).
  Resumable: re-run the exact command to continue after any interruption (idempotent by topic_synset_id).
- **Disambiguation → ~7.5k vetted topics: BUILDING** in background → `data-pipeline/output/generation_topics_10k.json`
  (head_lemmas ~7,473 at min_zipf 2.5; single-sense auto, multi-sense LLM dominant-sense; ~$5–8 one-time).
- **10k generation: NOT started — Julian's switch** (the multi-day ~$1.9k spend). Command below.
- Monitor: `tail -f` the task output, or `wc -l data-pipeline/grading/sonnet_chains_provisional_r2.jsonl`.
  Stop a run: `pkill -f generate_metaphor_edges` (resumable). Healthy live-rate ≈ 0.20 (see calibration).

## What runs where

| Piece | Command (from repo root, run branch `metaphor-graph/enrich-stage-a`) |
|---|---|
| **200-loop (round 2)** | `data-pipeline/.venv/bin/python data-pipeline/scripts/generate_metaphor_edges.py --topics data-pipeline/output/generation_topics_200.json --output data-pipeline/grading/sonnet_chains_provisional_r2.jsonl --db data-pipeline/output/lexicon_v2.db --haiku-jsonl data-pipeline/output/metaphor_spike_apt_phase2_20260525T004154.jsonl --round 2 --batch-size 20 --autocommit-every 1` |
| **disambiguation → 10k topics file** | `data-pipeline/.venv/bin/python data-pipeline/scripts/metaphor_disambiguate.py --db data-pipeline/output/lexicon_v2.db --limit 10000 -o data-pipeline/output/generation_topics_10k.json` |
| **10k generation (Julian-launched, multi-day)** | see the exact command below (live Haiku — drops `--haiku-jsonl`) |

### 10k generation — Julian's launch command (after `generation_topics_10k.json` is built)
```bash
cd /home/agent/projects/metaforge
nohup data-pipeline/.venv/bin/python data-pipeline/scripts/generate_metaphor_edges.py \
  --topics data-pipeline/output/generation_topics_10k.json \
  --output data-pipeline/grading/sonnet_chains_provisional_r2_10k.jsonl \
  --db data-pipeline/output/lexicon_v2.db \
  --round 2 --batch-size 20 --judge-sample 3 \
  --max-topics 7500 --max-cost-usd 2000 \
  > data-pipeline/output/generation_10k.log 2>&1 &
```
Live Haiku+Sonnet (~$0.25/topic). `--max-topics` is the hard cap; `--max-cost-usd` the soft guard;
the tripwire (default `--tw-abs-floor 0.08`) is the emergency brake. Resumable: re-run to continue.
To "feed after the 200 exhausts", point `--topics` at the 10k file once the 200-loop completes — or run
both files into the SAME `--output` so resume-by-topic_synset_id de-dupes the overlap automatically.

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
- 2 of 200 dropped (`a`, `ideas` — single letter / plural, no noun sense; lemmatise `ideas`→`idea` if wanted).
- **Frequency-head topic selection includes primarily-verb/function words** whose only noun sense is rare
  (`down`→"feathers", `take`→"film take"). The disambiguator picks the dominant *noun* sense correctly, but
  these are marginal metaphor topics. No POS-dominance data in the DB to filter them (same gap as
  sense-frequency). A future POS-dominance filter (require the lemma's dominant POS = noun) would clean the
  head; for now the grading loop filters quality downstream. Minority of topics.
- Cross-file/cross-round `chain_signature` dedup belongs in the grading consumer.
- DB `metaphor_judgments.label` is v1; reconcile before JSONL→DB judgment ingestion.
- Feeding the LIVE grading tool: the r2 round file is generated in the main checkout on `enrich-stage-a`;
  the live grader reads `.worktrees/next/data-pipeline/grading/` on `grading-live` — copy/commit the round
  file there (deploy step) to grade round 2.
