# Metaphor-edge generation phase — handoff / resume note (2026-06-04)

Follows the context-free-edge investigation (`docs/inbox/2026-06-03-context-free-edges/FINAL_REPORT.md`), which concluded: **derivation is dead; edges must be LLM-generated; the bottleneck is the judge.** Julian then asked to start populating the metaphor-edge layer (`metaphor_bridges`) continuously in the background while judging matures. This note captures where that stands so it can resume without re-deriving.

## Decisions already made (Julian, this session)
- **Staging = "Hybrid: throttle + live grading"** — open full-scale generation but instrument a per-batch live-rate tripwire that auto-pauses if quality craters over a rolling window. The live-rate monitor = the **proxy LLM judge** (Haiku/Sonnet), measured at 64–75% agreement with Julian, **zero false-positives**, conservative — good as a "is the prompt cratering?" tripwire, NOT as the final admission gate (that still needs Julian-calibration).
- **Scope = "Top few-k head only first"** — frequency-ordered head of the queryable vocabulary, lazily extend the tail later.

## ⚠️ BLOCKER discovered (the reason the run is NOT launched)
**Auto sense-selection from `lexicon_v2.db` is unreliable — there is no sense-frequency data** (WordNet/SemCor tagcounts were never imported). Both heuristics (least-polysemous synset; lowest synset_id) mis-pick the dominant sense of common words, sometimes embarrassingly:
- `house` → "playing house"; `feel` → "manual stimulation of the genital area"; `love` → "sexual activities"; `still` → "distillation apparatus"; `must` → "grape juice"; `fire` → "act of firing weapons".

Mass-generating metaphor chains on auto-selected senses = **garbage** (and reputationally bad output). This **is** the deferred PIPELINE item *"Snapping reconciliation + sense-accuracy"*, now concretely demonstrated. It is a hard gate for the head-of-frequency run.

## Recommended path (fast-but-safe) — awaiting Julian's A/B call
1. **Start the continuous hybrid loop now on the ~200 already-curated correct-sense topics** (the spike/grading cohort — vetted glosses: time, anger, love, life, …). Zero sense-blocker; exercises the full pipeline + tripwire; feeds grading immediately.
2. **In parallel, build a one-time LLM sense-disambiguation pass** (batched Haiku: lemma + its candidate glosses → dominant everyday sense) to extend the topic list to the next few-thousand *correctly*. ~$10–15 one-time; permanently fixes topic-selection for scale.
3. Runner consumes whatever vetted topics file exists → scales 200 → few-k as (2) lands.

**Pending operator decision:**
- **(A)** build disambiguation pass + wire the runner, validate end-to-end on ~5 vetted topics (~$1), hand Julian the launch command. *(orchestrator leans A)*
- **(B)** also kick off the continuous run on the 200 vetted topics once validated.
Julian said he will make the call after memories are saved.

## State of the code (be accurate)
- **BUILT:** `data-pipeline/scripts/select_topics.py` — zipf-head content topic selector (stopword + length≥3 + enriched-noun filters + primary-sense dedup). **Runs**, but its output inherits the sense blocker above (it used the least-polysemous heuristic) → **not production-usable until the sense fix lands.** Output sample: `data-pipeline/output/generation_topics_head.json` (3000 topics, sense-noisy).
- **NOT BUILT YET:** `generate_metaphor_edges.py` — the resumable continuous runner (designed only). Intended shape: per batch of 20 topics → Haiku `build_apt_prompt` (10 vehicles+shared-features) → Sonnet `run_chain_spike.build_prompt` (10 ordered chains, context-free-hop clause) → append `chain.v1` to a round JSONL (`data-pipeline/grading/sonnet_chains_provisional_r2.jsonl`, the format the grading tool already consumes) → proxy-judge live-rate tripwire → log cost/timing → resumable by completed-synset-id, with a `--max-topics` budget cap. Auto-commit per N batches. Launch via nohup/systemd (background-agent writes are auto-denied, so Julian launches it).
- **NOT BUILT:** the sense-disambiguation pass.

## Generation facts (from the investigation, reuse)
- Prompts already exist & are production-ready: `metaphor_spike_1a.build_apt_prompt` (Haiku) + `run_chain_spike.build_prompt` (Sonnet, has the context-free-hop + head clauses). Measured cost ~$0.062 Haiku + ~$0.19 Sonnet per topic; ~71% live by Julian on n=21.
- `claude` CLI cost-capture pattern: see `docs/inbox/2026-06-03-context-free-edges/artifacts/measure_generation_cost.py` (`cli_call` parses `total_cost_usd`).
- Generator + clauses live ONLY on branch **`metaphor-graph/grading-rhs-affordances`** (current branch). The `enrich-stage-a` branch lacks them — do NOT run Stage A from there or it regenerates the dead chains the clauses prevent (PIPELINE inbox item).
- The metaphor-graph schema (`metaphor_bridges` etc.) is NOT in the main-checkout `lexicon_v2.db` (predates it) — apply schema before DB ingestion, OR keep output as `chain.v1` JSONL round files (grading-tool-native) and ingest later via `metaphor_graph_enrich_haiku.ingest_haiku_apt` / `insert_bridge_with_raw_path`.
- Open design fork (PIPELINE inbox): edge-vs-path liveness — does the graph edge = the topic→vehicle bridge (path-level) or each hop (per-edge)? Coupled to the judge; doesn't block generation; settle before locking `graph_edges.metaphor_link` semantics.

## Open pre-flight checklist before the *scaled* run
- [ ] Sense-accuracy fix (disambiguation pass) — **hard gate**.
- [ ] Branch lineage consolidated (generator + clauses on the run branch).
- [ ] Target DB has metaphor-graph schema (or commit to JSONL-first output).
- [ ] Topic head curated/vetted (content concepts, correct senses).
- [ ] Runner: idempotent/resumable, `--max-topics` cap, per-batch live-rate tripwire, cost log, auto-commit.
