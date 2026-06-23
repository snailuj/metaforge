# GROUNDING — measured facts for the context-free-edge investigation

**Every fact here is reproducible.** Each carries a `[repro]` pointer (a SQL query, a script, or a logged command). Subagents: treat this as the shared truth base. Do **not** assert anything beyond it without your own reproducible evidence. Mark hypotheses as hypotheses.

Snapshot DB: `data-pipeline/output/lexicon_v2.db` (main checkout, dated 2026-05-26). NOTE: this DB **predates** the metaphor-graph schema (no `metaphor_bridges` table — that schema was added 2026-05-28). The graph's metaphor layer currently lives as JSONL grading data under `data-pipeline/grading/`, not yet imported into a bridges table.

## G1 — The graph and what an "edge" is

`graph_edges` is a SQL **VIEW** (`data-pipeline/SCHEMA.sql:399`) unioning 4 arms:

| arm | source | per-topic LLM cost | nature |
|-----|--------|--------------------|--------|
| `has_property` | `synset_properties_curated` ⋈ `property_vocab_curated` | **none** (pure SQL over enrichments) | synset → property-cluster-representative synset |
| `metonym_of` | `synset_metonyms` ⋈ `syntagms` (SyntagNet) | none | pre-existing collocation links |
| `antonym_of` | `property_antonyms` | **none** (derived) | bidirectional |
| `metaphor_link` | `metaphor_bridges` ⋈ `metaphor_judgments WHERE label='live'` | **HIGH** (generate-then-judge) | topic → vehicle, admitted only when judged `live` |

**Key reframe:** three of four arms are already derived combinatorially from the 80k enrichments with zero per-topic generation. Only `metaphor_link` (the product-valuable cross-domain layer) currently requires per-topic LLM generation + judgement. The mission = populate that layer (or its equivalent) at ~100k scale.
[repro] `data-pipeline/SCHEMA.sql` lines 320–445.

## G2 — The enrichment substrate (the "~80k shared-feature enrichments")

| metric | value |
|--------|-------|
| synsets total | 107,519 |
| synsets with raw properties (`synset_properties`) | 81,602 |
| raw property rows | 973,947 (~11.9/synset) |
| synsets with curated property-clusters (`synset_properties_curated`) | 81,000 |
| curated property rows | 822,807 (~10.2/synset) |
| distinct clusters used | 7,728 |
| total vocab clusters | 22,307 |

[repro] `artifacts/substrate_counts.sql` (the queries in run_log RL-2).

## G3 — Combinatorial fan-out of shared-feature derivation (H-A's scalability driver)

Naive "two synsets share ≥1 curated cluster" candidate pairs = **454,972,167 (~455M)**.
Driven by mega-clusters: max cluster size **7,075** synsets; top-10 sizes `7075,6089,5481,5039,4913,4417,4323,3876,3851,3765`; median cluster size ~13.
A cluster of size m contributes m·(m−1)/2 pairs, so the top handful of mega-clusters dominate the 455M. **These mega-clusters are the "stop-words" of the property space** — generic features shared by thousands of synsets, low metaphor signal. H-A viability depends on TF-IDF-style cluster down-weighting / pruning + cross-domain gating to collapse 455M → a tractable, high-precision candidate set.
[repro] run_log RL-2 fan-out query.

## G4 — Quality ground truth (grading), and its thinness

Round-1 generated **200 chains** (`data-pipeline/grading/sonnet_chains_provisional_r1.jsonl`).
Human-judged so far: **11 distinct chains** (`judgements_provisional.jsonl`, latest-wins): **8 live, 1 dead, 2 legacy-null**. Confidence: 10 high, 1 med.
This is the only human label set. n=11 is too small to calibrate a precision estimate to a tight CI — a binding measurement-validity constraint (Invariant #2). Any LLM-judge must report agreement against these 11 and we must not over-extrapolate.
[repro] run_log RL-2 grading query.

## G5 — Generation baseline mechanism

`data-pipeline/scripts/run_chain_spike.py` (branch `metaphor-graph/grading-rhs-affordances`):
per topic → **Haiku** proposes 10 vehicles + flat shared-feature sets → **Sonnet (`claude-sonnet-4-6`)** rewrites into 10 ordered topic→vehicle chains of `{phrase,head}` steps. Prompt enforces the **context-free-hop** constraint ("each adjacent pair must stand on its own… blind to every other step"). Edges harvested = chain hops + the topic→vehicle bridge.
So the baseline is **already a 2-tier route** (cheap Haiku recall → Sonnet refine). ~2 LLM calls/topic, ~10 bridges × ~4 hops ≈ ~40 candidate edges/topic.
Acknowledged baseline cost (high variance, to be re-characterised): "≈1 hr for 20 topics × 10 vehicles."
[repro] `data-pipeline/scripts/run_chain_spike.py`.

## G6 — Model access + per-call cost model

LLM access is via the **`claude` CLI** (`lib/claude_client.py` shells `claude -p --output-format json --model {haiku|sonnet|opus}`), NOT the Anthropic API. No API key needed; CLI present (`claude 2.1.161`).
**Cost gotcha:** a trivial Haiku call reported `total_cost_usd=0.0725` with `cache_creation_input_tokens=57,279` — the Claude Code CLI loads a ~57k-token system prompt per cold call. Within a 5-min window subsequent identical-prefix calls hit `cache_read` (cheap). So batch throughput amortises the overhead; isolated calls pay ~$0.07 floor. This overhead is an artifact of the CLI harness, not intrinsic to the model — relevant to any "cost per edge" extrapolation.
[repro] run_log RL-1 probe.

## G7 — Hard constraints (inherited by every subagent)
- Total compute/spend may rise ≤ **4×** for ≤ a few **weeks**.
- **No production-scale enrichment.** Measurement/prototype cohorts **≤20 synsets** only. Gather evidence; do not run production enrichment.
- Tooling: `lib/claude_client.py` / `claude` CLI for Opus/Sonnet/Haiku; write analysis/harness/test/doc code freely.

## G8 — Strong priors from project history (do not re-derive; build on)
- **M02 closed empirically negative:** pointwise property-overlap (symmetric/asymmetric/null) does **not** beat `random_uniform` as a discriminative *scorer* (±0.06 of zero separation on a balanced cohort). H-A must justify overlap as *candidate generation*, not scoring.
- **Karpathy Loop-1 cohort inversion:** Phase-2 inapt vehicles are LOWER concreteness than apt; Lakoff inapt are HIGHER (anger→umbrella). Any global property-overlap signal that helps one cohort hurts the other.
- **Product target is LIVE/literary cross-domain metaphor**, not dead/conventional. Shared-feature overlap structurally tends to surface *similar* (often same-domain or dead) pairs — a quality risk H-A must confront head-on (memories: `product_goal_live_vs_dead_metaphors`, `eval_as_preference_tracking_instrument`).
