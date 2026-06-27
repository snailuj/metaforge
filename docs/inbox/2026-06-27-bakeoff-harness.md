# Generation-model bake-off harness (2026-06-27)

Purpose: farm metaphor generation OFF the Claude subscription quota onto a cheaper
backend (GLM-5.2 Coding Plan, or a pay-per-token open model via OpenRouter/DeepInfra,
or self-hosted later) — chosen on data, not vibes.

## What was built (TDD, on `generation/emit-the-sense`)

- **`lib/openai_client.py`** — provider-agnostic OpenAI-compatible `prompt_text`/`prompt_json`
  (mirrors `claude_client`'s shape; stdlib urllib transport; retry/backoff; fence-stripping).
  Targets any `/chat/completions` endpoint via `base_url`+`api_key`.
- **`generate_metaphor_edges.py`** — the existing runner is now provider-selectable:
  `--provider {claude|openai}` (default `claude`, byte-identical), `--base-url`, `--api-key-env`.
  The bulk **haiku-apt + sonnet-chain** calls route to the chosen backend (the occasional
  tripwire judge stays on Claude; bake-offs run `--no-tripwire`). emit-the-sense glosses,
  AVOID steering, resume — all unchanged.
- **`bakeoff.py`** — `run` (same topics through each candidate + reuse an existing Claude
  baseline, no re-spend) and `score` (markdown + JSON scorecard). Metrics: chains, topics,
  vehicles/topic, vehicle diversity, **gloss coverage**, zero-gloss chains, chain length,
  self-metaphor, wall-clock. Optional spend-gated: `--liveness N` (proxy live-rate),
  `--gloss-judge N` (Claude-judged gloss **sense-accuracy** — the load-bearing emit-the-sense metric).
- Inputs: `bakeoff_candidates.json` (template — **verify current model slugs at openrouter.ai/models**),
  `output/generation_topics_bakeoff_50.json` (50 topics, all covered by the existing Claude baseline).

Tests: `lib/test_openai_client.py` (7), `scripts/test_bakeoff.py` (4),
`scripts/test_generate_metaphor_edges_provider.py` (3) — all green; runner regression intact.

## Run it (when you have an OpenRouter key)

```bash
export OPENROUTER_API_KEY=sk-or-...
cd <repo>/.worktrees/stock-gen
PYTHONPATH=lib:data-pipeline/scripts data-pipeline/.venv/bin/python \
  data-pipeline/scripts/bakeoff.py run \
  --candidates data-pipeline/bakeoff_candidates.json \
  --topics    data-pipeline/output/generation_topics_bakeoff_50.json \
  --db        data-pipeline/output/lexicon_v2.db \
  --out-dir   data-pipeline/output/bakeoff \
  --max-topics 50 \
  --baseline-chains data-pipeline/grading/stock/chain-topics_stock_emit.jsonl \
  --gloss-judge 60 --liveness 40
```

Outputs `data-pipeline/output/bakeoff/{<model>.jsonl, scorecard.md, scorecard.json}`.
Re-score without re-running: `bakeoff.py score --manifest data-pipeline/output/bakeoff/manifest.json --gloss-judge 60`.

## Decision rule

The discriminating metric is **gloss sense-accuracy** (emit-the-sense depends on the model
emitting correct per-node senses). Liveness can be a bit weaker (stock corpus, judge triages
later); JSON-reliability shows up as low chains/topic or high zero-gloss. Pick the cheapest
backend whose gloss-accuracy ≈ Claude's, then run production on it:
- GLM win → GLM Coding Plan flat-rate (~$30 Pro, whole core in ~2 wks).
- Open-model win → DeepInfra direct on that model (~$7–30 for the whole core, parallelisable).

## Production note (before a long farmed run)

Fix the **autocommit counter**: `--autocommit-every` counts batches per generator invocation,
which resets each session-limit window, so it never fired on the multi-day Claude run (the 3,158
chains had to be committed by hand on pause). Commit per-window (in the wrapper, after each
generator returns) before relaunching a long run.
