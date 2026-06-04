# FINDINGS SO FAR — read before your analysis (checkpoint C1)

Read `GROUNDING.md` first (the measured fact base). This file adds what the orchestrator has already MEASURED, so you don't re-litigate settled ground.

## What is already settled (do not re-measure; build on it)
- **F1 — Naive feature-overlap derivation produces DEAD metaphors.** Ranking vehicles by shared curated-cluster overlap (raw/idf/idf·salience) over the 81k substrate surfaces synonyms, co-hyponyms, and definitional paraphrase (`ideas→conceptualise/design`, `anxiety→anxiousness/affright`, `doubt→incertain`), NOT live cross-domain metaphor. Direct evidence, API-free (`artifacts/derive_candidates.py`, `derived_cohort_ms2.json`). This is M02's null result extended from *scoring* to *candidate generation*. **Implication: maximising feature overlap is the wrong objective — metaphor needs cross-domain DISTANCE + a few selective salient features, not maximal overlap.**
- **F2 — Fan-out IS controllable.** df-cap pruning collapses the 455M shared-≥1 pairs to 8.94M (cap 200) / 271k (cap 30) by dropping only the mega stop-word clusters. Scale is not the blocker; *precision* is.
- **F3 — Pruning strips abstract topics.** The df-cap that buys tractability removes nearly all candidates for abstract topics (anger/time/life/hope/grief/courage → 0), because their distinctive "properties" ARE the generic mega-clusters. Abstract topics are the Forge's core product.
- **F4 — Sense-snapping is noisy.** Topic synsets snap to wrong senses (anger→"make angry", heart→"playing card"). Any feature-derived edge inherits this noise.
- **F5 — Substrate available:** `synset_centroids` (81,185 FastText), `lemma_embeddings` (56,181), raw FastText vec. Labelled cohort: ~2000 apt + ~2000 inapt `(topic,vehicle,shared_features)` triples in `data-pipeline/output/metaphor_spike_{apt,inapt}_phase2_20260525*.jsonl`.
- **F6 — Prior M04 result:** an embedding cosine band *surfaces* cross-domain candidates (anger→fire, idea→light pinned by a canary test) but *cannot score/rank* apt-above-inapt better than within-domain neighbours. So embeddings help RECALL, not PRECISION, on their own.

## The crux question for the whole mission
Given F1 + F6 + M02: **does ANY context-free function over the existing substrate (embeddings + curated features + concreteness + property-type diversity) separate apt from inapt metaphor pairs well enough to be a high-precision candidate proposer at 100k — without per-topic LLM generation?** The orchestrator is running this separability experiment directly on the 2000+2000 spike cohort. Your job is to design the best version of YOUR approach assuming that experiment's outcome could go either way, and to nail the 100k cost/quality math.

## Cost reality (for all 100k math)
- `claude -p` cold call ≈ $0.07 floor (57k cache-creation tokens) + per-token; amortises within 5-min cache windows during a batch. Use this, not API list prices, for CLI-based cost. State assumptions.
- Baseline generation = ~2 calls/topic (Haiku vehicles + Sonnet chains). At 100k topics that's ~200k calls.
- Hard limit: ≤4× current spend, ≤ a few weeks. No production enrichment; ≤20-synset measurement cohorts only.

## Your deliverable (structured)
Return the schema fields you are given. Additionally: (a) a concrete **harness script as text** the orchestrator can run (no API calls from you — design it, the orchestrator executes & tracks cost), (b) **100k scale math** with explicit assumptions and a confidence interval or a refusal to extrapolate, (c) **quality risks** specific to your approach, (d) a crisp **verdict** (viable | not_viable | inconclusive) against the quality bar in status.md.

Do NOT spend API / call the claude CLI. Reading files and running SQL/python on existing data to verify your numbers is encouraged; if you cannot run Bash, mark computed numbers `NEEDS_ORCHESTRATOR_RUN` with the exact command.
