# Sustainable Context-Free Edge Population for the Metaphor Graph — Decision-Ready Report

_2026-06-03. Orchestrated investigation. Total metered API spend: **$6.65** (78 calls — mostly the judge-feasibility probe; all derivation/traversal/separability analysis was API-free). All artifacts under `docs/inbox/2026-06-03-context-free-edges/`; every number below maps to a committed, re-runnable harness (see Claims Ledger)._

---

## Executive summary

**Recommendation: do not build a derivation/retrieval pipeline. Keep per-topic LLM generation (it is the only mechanism that produces live cross-domain edges, and it is cheap), and spend the effort instead on the one thing that actually gates quality at scale — an automated live/dead *judge* calibrated to Julian's grading, which does not yet exist.**

The brief asked us to treat one hypothesis as primary: that high-quality context-free edges can be **derived/synthesised from the existing ~80k shared-feature enrichments** rather than generated per topic. **We measured this and it is false** — and we proved *why*, across four independent substrates and, critically, on the only human-graded data that exists (not just the LLM-generated cohort):

- Shared-feature overlap discriminates apt-vs-inapt at **AUC 0.55 ≈ chance**, recalls apt vehicles at **2%** (recall *ceiling*: pairs sharing zero surviving cluster can never be derived), and is **anti-correlated** with aptness — inapt pairs share *more* features than apt (amplified by this cohort's inapt vehicles being same-domain/synonymic; see caveat #1 — but the mechanism *is* the point: overlap selects synonyms, i.e. the inapt direction).
- Embedding ANN bands are **anti-correlated** too (median apt vehicle at rank **2,870 / 81,185**; recall@200 = 13%).
- WordNet `relations` (234,810 structural rows) recover **0/7** canonical live pairs.
- **Multi-hop traversal of the unified, deduplicated property∪synset graph also fails** — both the *uniform* random walk (PageRank only weakly discriminative, AUC ~0.62, and *anti-correlated as a generator*: it buries apt vehicles at median rank 14k while ranking inapt closer at 6k) **and** a *signal-guided* beam search (POS-filtered, cosine+concreteness+cross-domain, even with hub-penalty; best apt recall@200 11.9% < direct embedding's 13%). The cross-domain signal corrects direction but can't pick *which* far node is the apt vehicle. Every pair connects within 2–4 hops through generic mega-hubs, so path-existence is uninformative.
- **Root cause (measured):** only **0.31%** of the shared features an LLM *itself names* for an apt pair are present in both concepts' static enrichments. A metaphor's bridge feature is *contextually constructed*, not retrievable from per-concept property lists. Cross-domain metaphor is, by definition, the **low-surface-similarity** case — the opposite of what any similarity substrate encodes, **at any hop count**.

This refutation **holds on human labels**: under Julian's verdicts, neither features nor embeddings separate live from dead — so the conclusion is **not** an artifact of grading the model with the model.

Generation, by contrast, works and is affordable: direct-measured **~$0.06/Haiku + ~$0.19/Sonnet per topic** → **~$6–29k for 100k topics** (≈ halved API-direct; ~$2–10k at the realistic ~15–35k queryable frontier). That is **orders cheaper** than the rejected retrieve-then-verify route ($86k–878k for 50% recall). **Cost is not the binding constraint.**

The binding constraint is **quality admission**: an edge only meets the bar once judged `live`, and (a) there is **no automated judge** in the codebase, (b) the human ground truth is **~12–21 verdicts over 3 concrete topics**, with **zero** signal on the abstract-emotion topics that are the Forge's core. A first feasibility probe is encouraging-but-incomplete: an out-of-box LLM judge agrees with Julian **64–75% (κ 0.31–0.44, n=12 over 3 topics)** with **zero false-positives** (never admits a human-dead metaphor) but rejects ~30–44% of his live ones (κ rests on only 2 dead chains — directional, not validated). The decision-ready move is to **invest in the judge + grading loop first** — the existing bootstrap instrument, scaled and query-weighted — not in a derivation mechanism that the evidence shows cannot exist.

### Three caveats stated up front (not buried)
1. **Cohort validity.** Most AUC/recall numbers are measured against the Sonnet/Haiku-generated `metaphor_spike` apt/inapt cohort, **not** human-graded data. On the only overlap with Julian's verdicts (2 topics, 4 pairs), spike-"apt" agrees with human-"live" just **1/4**. The *derivation refutation* survives on human labels (so the headline is safe); but —
2. **Concreteness is retracted as "the one usable signal."** Vehicle-concreteness separates apt/inapt at AUC 0.81 *on the spike* but **inverts to 0.375 on human-graded concrete-action topics** — exactly the documented Karpathy-Loop-1 / Lakoff cohort inversion. It is a topic-class-dependent prior, usable only as a *per-class-validated volume pre-filter*, never a quality gate, and it has **no defence against dead metaphor**.
3. **No validated quality at scale.** Every positive quality claim rests on 8/11–ish chains over 2–3 topics. We can certify what *fails*; we cannot yet certify a production *pass rate*.

---

## Approaches tried

| Approach | Mechanism | Verdict | Reproducing artifact |
|----------|-----------|---------|----------------------|
| **H-A — derivational seeding (PRIMARY)** | rank vehicles by shared curated-cluster overlap | **NOT VIABLE** — surfaces synonyms/dead metaphor; recall 2%; anti-correlated | `derive_candidates.py`, `recall_ceiling.py`, `separability_experiment.py` |
| **H-A-refined — distance-gated, feature-anchored** | cross-domain distance band + cross-type salient feature + concreteness gradient | **NOT VIABLE as generator** — cross-type-shared AUC 0.439 (below random); 70% of apt pairs share zero cluster; salvages only a weak concreteness pre-filter | `ha_refined_separability.py` |
| **H-B — embedding ANN band + cheap verify** | top-b FastText neighbours → Haiku verify | **NOT VIABLE** — bands anti-correlated; 50% recall needs b≈2,870 → 11.5M verify calls = $86k–878k (6–60× baseline) | `hb_band_recall.py` |
| **H-C — distillation to cheap classifier** | logistic/GBM on context-free features from 2k+2k labelled pairs | **NOT VIABLE as proposer** — AUC 0.76 but ≈ one feature (concreteness), dead-metaphor AUC 0.61 | `separability_experiment.py`, `hc_fast_multivariate.py` |
| **H-D — tiered model routing** | Haiku bulk + selective Sonnet escalation | **NOT NEEDED as a special approach** — generation already affordable; its $0.005/call estimate was **wrong by ~12×** (Haiku) / ~15× (Sonnet output under-count); corrected below | `hd_routing_cost_harness.py`, `measure_generation_cost.py` |
| **H-E — caching / dedup** | amortise recurring vehicles/edges | **NOT VIABLE as a lever** — bridge-edge dedup **≈1.00×** (1.01× measured; the 0.01 is ~5 empty-synset-ID collisions, not real recurrence; each topic computed once); feature-keyed cache invalid (33% of reused vehicles flip apt↔inapt) | `measure_dedup_HE.py` |
| **H-F — relational shortcuts (symmetry/transitivity)** | multiply edges via graph closure | **NOT VIABLE — documented NEGATIVE** — 0/1112 apt pairs reverse to apt (observational — generator never reversed); transitive closure 93%+ **unverifiable** (only 6.6% labelled); 5.9% self-contradict | `hf_relational_shortcuts.py` |
| **WordNet `relations` traversal** (red-team) | hypernym/meronym/similar arms as substrate | **NOT VIABLE** — 0/7 canonical live pairs (within-domain similarity) | red-team harness |
| **Gloss-as-features** | topic vs vehicle definition content-word overlap | **NOT VIABLE** — AUC 0.537; apt share 4.6% vs inapt 11.8% (anti-correlated) | `gloss_overlap_experiment.py` |
| **Unified property∪synset graph, *uniform* multi-hop traversal** (operator-requested) | one graph, vertices = synsets ∪ canonical (dedup'd) property nodes; find edges by uniform-random walk (PageRank / link-prediction) | **NOT VIABLE** — PPR weakly discriminative (AUC 0.62) but anti-correlated as a generator (apt median rank 14k > inapt 6k); AA/RA/CN ~0.60; every pair 2–4 hops apart via hubs | `multihop_graph_experiment.py` |
| **Signal-*guided* multi-hop beam search** (operator steelman) | POS-filtered kNN graph; beam scored by cosine-smoothness + concreteness + cross-domain; sample depth-{2,3} surviving pool | **NOT VIABLE** — cross-domain push corrects direction (apt>inapt) but best apt recall@200 11.9% (< direct 13%); AUC 0.51–0.55 across 4 schemes × depth × beam | `guided_traversal_experiment.py`, `guided_traversal_wide.py` |
| **LLM judge feasibility** (admission gate) | tiered Haiku/Sonnet/Opus live/dead judge vs Julian's verdicts | **FEASIBLE, needs calibration** — 64–75% agree, κ 0.31–0.44, zero false-positives, ~30–44% conservative rejects (n=12, 3 topics; κ rests on 2 dead chains) | `judge_feasibility.py` |
| **Generation baseline (the survivor)** | Haiku propose → Sonnet refine, per topic | **VIABLE mechanism** — only thing that yields topic-relevant cross-domain vehicles; cheap | `run_chain_spike.py`, `measure_generation_cost.py` |

---

## Methods

- **Substrate quantification** — direct SQL on `lexicon_v2.db` (81,000 synsets with curated property-clusters over 7,728 clusters; 822,807 `has_property` edges already derived; 81,185 FastText centroids; 234,810 `relations`; 127,311 `frequencies`).
- **Derivation quality** — built an inverted-index candidate generator (`derive_candidates.py`) with IDF/df-cap pruning; ran on the 20-topic grading cohort and eyeballed with definitions.
- **Separability** — two harnesses, kept distinct: `separability_experiment.py` ran the topic-grouped 5-fold logistic regression (no leakage) + ablations over **12** features on **1,507** resolved pairs (983 apt / 524 inapt), giving AUC 0.818 / concreteness-only 0.812 / shared-feature-only 0.552. `ha_refined_separability.py` (H-A-refined) computed **in-sample single-feature ROC-AUCs with 1000-sample bootstrap CIs** (no CV) on its own 1,649-pair resolution (1067/582) — source of cross_type_shared 0.439 and concreteness-gradient 0.745. `hc_fast_multivariate.py` (H-C) is a third, 11-feature classifier (1,509 pairs) → AUC 0.764.
- **Recall ceiling** — fraction of apt pairs sharing ≥1 feature at 4 granularities + whether the LLM's own claimed shared-features appear in both synsets' enrichments.
- **Multi-hop graph traversal** — built the unified bipartite synset∪cluster graph (89k nodes, 822k edges); ran personalized PageRank (α=0.15, 60 iters, raw + IDF-weighted) per topic, plus Adamic-Adar / resource-allocation / common-neighbours and BFS shortest-path, scored for both discrimination and apt-vehicle recall.
- **Cost** — direct `claude -p --output-format json` calls with the **real** prompts (`build_apt_prompt`, `run_chain_spike.build_prompt`), capturing `total_cost_usd` + latency + cache tokens per call; cold vs cache-warm separated.
- **Red-team** — 4 adversarial agents independently re-ran harnesses and cross-validated against the **live** human grading data in `.worktrees/next`.
- **Variance honesty (Invariant #2):** Haiku cost n=5 (σ measured); Sonnet n=2 (high variance, output-length-driven — reported as a range, not a point); recall/AUC bootstrapped. We **refuse to extrapolate a production precision** from any cohort because the candidate-pool base rate at 100k is far below the cohort's 65% apt.

---

## Results (measured, with intervals)

**Substrate / fan-out**
- 455M shared-≥1 candidate pairs collapse to 8.94M (df-cap 200) / 271k (df-cap 30) by dropping the mega stop-word clusters → **scale is controllable; precision is the blocker.**

**Derivation quality (the refutation)**
- Shared-feature substrate discriminator: grouped-CV **AUC 0.552** (folds 0.51–0.60).
- Apt-vehicle recall *ceiling* via shared clusters (upper bound on any pruned-overlap derivation): **2.10%** (df-cap), 31.5% (no-cap, all via non-discriminative mega-clusters). Inapt > apt at **every** granularity (df-cap 7.4%, no-cap 45.9%, raw 46.9%).
- LLM-claimed shared feature present in both synsets' enrichments: **18/5846 = 0.31%**.
- Embedding ANN: median apt vehicle **rank 2,870/81,185**; recall@10/50/200/1000 = 0.5/4.6/12.9/30.8%; apt:inapt odds <1 at every band.
- WordNet relations: **0/7** canonical live pairs recovered.
- Gloss-as-features (topic vs vehicle definition content-word overlap): **AUC 0.537** (≈chance); apt pairs share ≥1 gloss content word **4.6%** vs inapt **11.8%** (anti-correlated, like every other substrate). The 4th tested substrate.

**Multi-hop traversal of the unified property∪synset graph (operator-requested).** Graph: 81,000 synset nodes ∪ 7,728 canonical (deduplicated) property-cluster nodes, 822,807 `has_property` incidence edges. Tested as both a *generator* (rank candidate vehicles by graph proximity to the topic) and a *discriminator* (score a given pair), on 1,497 resolved cohort pairs:
- **Personalized PageRank** (random-walk-with-restart over the dedup'd graph; column-stochastic transition matrix — *re-run after a fact-check fixed an all-zero-matrix bug*): discrimination AUC **0.615** (raw) / **0.630** (IDF-edge-weighted) — *weakly* above chance, on par with the link predictors below, not a usable signal. Generation: apt-vehicle **median PPR rank 14,202/81,185** (recall@10/100/1000 = 0.4/2.0/7.8%), but **inapt vehicles rank higher/closer** (median **6,238**; recall@5000 44.0% vs apt 25.9%) — PPR proximity favours same-domain/synonym over cross-domain, so it is **anti-correlated as a generator and cannot propose apt vehicles**.
- **Hub-down-weighted link predictors:** Adamic-Adar **0.606**, resource-allocation **0.609**, common-neighbours **0.599** — same weak ballpark; none usable for generation.
- **Hub-connectivity artifact, explicit:** BFS shortest-path length — apt `{2:45, 4:75}`, inapt `{2:61, 4:59}`, **0 unreachable within 6 hops**. Every concept reaches every other in 2–4 hops through generic mega-hubs, so **path existence carries no signal**; the walk pools among same-domain synonyms (near in the similarity graph) and buries cross-domain vehicles.

**SIGNAL-GUIDED multi-hop traversal (operator steelman — the random walk above used no signal).** A fair objection: PageRank chose edges *uniformly*. We then built a **guided beam search** using the project's real signals, POS-filtered to nouns: edges = top-K (=40) cosine-nearest noun synsets (smooth conceptual steps); the beam (width 300–2000) keeps paths that take smooth steps while reaching cross-domain (far from the topic); the depth-{2,3} frontier is ranked toward cross-domain distance + concreteness. Four scoring schemes (`smooth_only`, `+concreteness`, `+cross-domain`, `+cross+concr`), 174 topics / 1,345 noun-resolved pairs:
- Local schemes (`smooth`, `+concr`): reach **inapt more than apt** (13.0% vs 7.9%) — the synonym/same-domain bias — recall@200 below direct embedding.
- Cross-domain schemes: the push **corrects the direction** (depth-3 apt reach 2.5% > inapt 1.3%; depth-3 beam-2000 apt 13.6% > inapt 13.0%) — the operator's intuition that cross-domain matters is directionally right — **but the magnitude is negligible**: best apt recall@200 = **11.9%** (depth-2, beam-2000) < direct embedding's 13%, with inapt reached *more* (25%). (The reported AUC(path-score) 0.506–0.545 is **tie-dominated** — ~90% of cohort pairs are unreached and share an identical sentinel score — so the operative metrics here are *reach rate* and *recall@k*, not AUC; both confirm no improvement over direct embedding.)
- **Hub-penalty refinement (operator):** down-weighting each hop into a high-in-degree kNN "god-node" by its in-degree (`guided_traversal_hubpenalty.py`; in-degree max 407, p99 161) — to stop the walk drifting into generic hubs — gave **no improvement**: across λ_hub ∈ {0, 0.5, 1, 2} apt recall@200 went 11.9% → 10.9% (slightly *worse*) and AUC 0.545 → 0.550. (The PageRank IDF variant had already hub-down-weighted the *property* edges, also with no effect.)
- **Why (geometric restatement of the contextual-signal problem):** pushing cross-domain spreads the beam over *thousands* of far concrete nouns; the embedding+concreteness geometry cannot identify *which* far node is the apt vehicle for *this* topic. Hub-avoidance doesn't help because the limiting factor isn't hub-drift — it's that many *non-hub* cross-domain endpoints are reached and nothing distinguishes the apt one. The stepping-stone (`anger→pressure→eruption→volcano`) does not preferentially terminate on the apt vehicle. (Bounded scheme space explored — not exhaustive; the Ortony property-overlap scorer was excluded as already null per M02.)

**Judge feasibility (does the recommended admission judge actually work?).** A tiered Haiku/Sonnet/Opus live/dead judge run against Julian's own verdicts (n=12 graded chains over **3 topics** — anxiety, anchor, ambush; probe timed out before all 21; resumable): **Haiku 75% (κ+0.44, n=12), Sonnet 75% (κ+0.44, n=12), Opus 64% (κ+0.31, n=11** — Opus missing one chain to the timeout). Decisive pattern: **all three models have zero false-positives** (never call a human-*dead* metaphor live) but reject ~30% (Haiku/Sonnet) to ~44% (Opus) of Julian's *live* ones (conservative). **Caveat the κ rests on only 2 human-*dead* chains** — directional, not validated. So an out-of-box LLM judge is **conservative-but-precise and moderately aligned** — feasible, but it must be **validated and calibrated** (the recommendation), not deployed raw.

**Generation quality vs the human bar (the one positive anchor — weak n)**
- Of the Sonnet-generated chains Julian has graded (live worktree, latest-wins, v1 `label` + v2 `metaphor` axis combined): **15 live / 6 dead = ~71% live**, over 21 distinct chains / 3 topics (anxiety, anchor, ambush). This is the only direct evidence that the *generation* mechanism clears the human live bar at a usable rate — but it is **n≈21 over 3 topics**, with the abstract-emotion core (anger, grief, hope, …) essentially unrepresented. It supports "generation is viable on quality" *directionally only*; it does not establish a production live-rate.

**The (retracted) concreteness signal**
- Spike: vehicle-concreteness AUC **0.797**; concreteness-only model 0.812 ≈ all-features 0.818; apt veh-conc 4.51 vs inapt 3.58 (topics balanced). Within-inapt-class AUCs all 0.75–0.87 (not a single-class artifact).
- **Human labels: AUC 0.375 (inverted).** → demoted to a topic-class-dependent prior.

**Cost (direct-measured, CLI warm; corrected)**
- Haiku vehicle-proposal: **$0.062 ± 0.017/call**, wall 53 ± 8 s, ~5,762 output tok (n=5).
- Sonnet chain: **$0.14–0.23/call warm, $0.35 cold** (n=3: 0.143/0.229/0.345), wall 135–214 s, 8.7k–14.4k output tok.
- Full 2-call/topic ≈ **$0.20–0.29**. **100k → ~$20–29k warm (~$41k cold-risk); Haiku-only ~$6.2k; ≈ halved API-direct.** At the realistic ~15–35k frontier: **~$3–10k full / ~$1–2k Haiku-only.**
- Judging ~600k candidate edges, batched small-output judge ≈ **$0.25–2k**. (Does not relocate the cost.)
- vs rejected retrieve-then-verify (H-B): **$86k–878k** for 50% recall.

---

## Discussion

**Why derivation cannot work (and this is not a tuning failure).** Three model families (property-overlap, embeddings, taxonomic relations) and four substrates all fail by the *same mechanism*: they encode **similarity**, and live cross-domain metaphor is a **dissimilarity-with-selective-correspondence** relation. The 0.31% result is the cleanest evidence — the connecting feature is an abstraction the LLM builds in context, absent from either concept's static description. This is M02's pointwise-overlap null result, generalised and explained. No amount of pruning, weighting, or distance-gating recovers a signal that isn't in the data.

**Why *multi-hop graph traversal* doesn't rescue it (it makes it worse for generation).** A natural counter-proposal is to stop scoring pairs and instead build one unified graph (synsets ∪ deduplicated property nodes) and *walk* it to discover edges. We tested this directly. It fails for a structural reason that adding hops cannot fix: the deduplicated property graph is a **small-world dominated by a handful of mega-hub property nodes** (the largest cluster touches 7,075 synsets). Through those hubs, every concept reaches every other within 2–4 hops — so reachability is uniform and uninformative (apt and inapt pairs are indistinguishable by path existence). A random walk (PageRank) from a topic therefore concentrates probability on **same-domain neighbours** (other emotions, for "anger") — the synonyms — and assigns the genuinely cross-domain apt vehicle a *deeper* rank (median ~14k/81k) than the same-domain *inapt* vehicle (~6k), because the apt vehicle shares only a few *specific* features and many *generic* ones. A correct PageRank is only weakly discriminative (AUC ~0.62) and hub-down-weighting (Adamic-Adar/RA) is the same weak ~0.61 — neither usable for generation. The graph framing inherits the same defect as pairwise overlap and amplifies the synonym-bias in the generative direction. **Important distinction:** the unified graph is an entirely sensible *storage and navigation* structure — and three of its four edge arms already exist (822,807 `has_property` edges) — but it cannot *synthesise* the metaphor (`metaphor_link`) edges by traversal; those edges have to be generated and judged first, after which they become first-class graph edges (the metaphor-graph-completion direction — explicit judged edges, property-cascade demoted to a feature-provider).

**Hardware-skepticism (mandate satisfied).** Nothing here recommends more hardware. The opposite: the investigation *kills* the compute-heavy paths (per-topic generation O(topics) was the assumed cost; embedding-verify at $86k–878k is worse). Generation is cheap; the scarce resource is **human judgement**, not compute. Every place the analysis could have leaned on spend, the red-team forced a cheaper algorithmic answer (Haiku-only, query-weighting, batched judge).

**Residual risks / quality caveats.**
- The **judge does not exist** and is the load-bearing component. The recommendation is only as good as an automated live/dead judge's agreement with Julian — currently unmeasured.
- Human ground truth is **~12–21 verdicts over 3 concrete topics**; the abstract-emotion core has **none**. Any quality number today is unsupported there.
- The **v2 two-axis verdict model** (linkage + live/dead) means even the "live count" needs careful parsing; the grading data is richer but narrower than a flat label parse suggests.
- **Sense-snapping noise** (anger→"make angry") pollutes any synset-keyed analysis; mitigated where possible (lemma-mean concreteness) but not eliminated.
- **Target sizing:** "100k" exceeds the ~35k curated-lemma queryable universe; honest planning should be query-weighted.

---

## Completeness — what was tried, and what was deliberately not

**Tested (each with a committed harness; see Approaches table + `ALGORITHMS.md`):** pairwise shared-feature overlap (raw / IDF / IDF·salience); distance-gated cross-type feature-anchoring (H-A-refined); embedding ANN band + cheap verify (H-B); distilled context-free classifier (H-C); WordNet `relations` traversal; unified-graph uniform PageRank + Adamic-Adar/RA/common-neighbour; signal-guided multi-hop beam search (4 schemes × depth{2,3} × beam{300,800,2000}); relational shortcuts symmetry/transitivity (H-F); caching/dedup amortisation (H-E); tiered routing cost model (H-D); direct generation cost/latency measurement; tiered LLM-judge feasibility. **Substrates covered: curated property-clusters, raw properties, FastText embeddings, WordNet relations, definition glosses, concreteness, property-type diversity.**

**Deliberately not tried (and why):**
- **Target-conditioned A* / bidirectional "Bridge" search** — requires *both* endpoints known; it is the *explanation/verification* use case, not generative edge discovery. Out of scope for *populating* edges.
- **GNN / learned link-prediction trained on judged edges** — needs a corpus of judged metaphor edges that does not yet exist (n≈21). This is the *post-judge* graph-completion direction, not a bootstrap derivation; it is downstream of the recommended judge work, not an alternative to it.
- **Gloss-conditioned cheap generation** (Haiku on sense-gloss only) — a live PIPELINE backlog idea; it is a *generation* variant (cheaper prompt), not a *derivation*, so it does not change the derive-vs-generate verdict — flagged for the generation-optimisation phase, not measured here.
- **Exhaustive hyperparameter/scheme search for guided traversal** — a bounded slice (4 schemes, 2 depths, 3 beam widths) was explored; AUC sat at chance throughout, and the structural reason (geometry can't localise the apt cross-domain node) predicts no scheme escapes it. We do not claim the entire scheme space is covered.
- **The Ortony pointwise property-overlap *scorer*** — excluded as already empirically null (project milestone M02), not re-run.

## Feasibility — cost and time (direct-measured, with variance)

**Cost** (CLI warm rates, `total_cost_usd` captured per call): Haiku vehicle-proposal **$0.062 ± 0.017** (n=5); Sonnet chain **$0.14–0.35** (n=3, output-length-driven). Full 2-call/topic ≈ **$0.20–0.29**.

| target | full 2-call (CLI) | Haiku-only (CLI) | API-direct (≈ −50%) | + judging (batched) |
|--------|-------------------|------------------|----------------------|---------------------|
| 100k topics | $20–29k (cold-risk $41k) | ~$6.2k | $10–15k full / ~$3k | + $0.25–2k |
| ~35k queryable frontier | $7–10k | ~$2.2k | $4–7k / ~$1k | + $0.1–0.7k |

vs the rejected retrieve-then-verify route (H-B): **$86k–878k** for 50% recall. Generation is **orders cheaper**.

**Time** (wall-clock, measured latency): Haiku ~53 s/call, Sonnet ~175 s/call. Serial 100k 2-call ≈ 6,330 machine-hours; at concurrency *C*, wall-clock = 6,330/*C* h → **~3 weeks at C≈13, ~1 week at C≈38**. Haiku-only 100k ≈ 1,472 h serial → **~5 days at C≈13**. At the ~35k frontier, Haiku-only ≈ **~2 days at C≈13**. The CLI subprocess model is I/O-bound (waiting on the API), so local concurrency of 13–40 is trivial on one machine; **the real ceiling is API rate-limits, which this investigation did not measure** — that is the one feasibility input still open, and it is a generation-phase concern, not a blocker on the recommendation.

## Conclusion (decision-ready)

1. **Abandon derivation/retrieval.** It is refuted across **four substrates** (features, embeddings, WordNet relations, glosses), across **both framings** (pairwise scoring *and* multi-hop unified-graph traversal), and **on human labels**. This *saves* weeks of effort on a path the data shows cannot meet the quality bar. (Highest-confidence finding.)
2. **Generation is the mechanism. It is cheap and weeks-feasible.** Use the existing Haiku→Sonnet generator (graded **~71% live by Julian** so far, n≈21/3 topics — directional only); Haiku-only is a viable bulk route (~$2–6k). Query-weight the run (frequency head first, lazy tail, cache). Cost is **not** the blocker.
3. **The real deliverable is the JUDGE — and it must be an LLM judge, not a feature classifier.** The reason no context-free classifier works is the *same* reason the judge must be context-aware: the live/dead signal is **contextual** (the bridge feature is constructed in-context; static features give AUC 0.55 / inverting concreteness). So the admission gate is necessarily an LLM reading the pair-and-chain (cheap: small output, ~$0.25–2k batched at 100k). Build and validate it against Julian's grading; until its agreement with the human axis is measured, "high-quality at 100k" is unprovable. **This is where the ≤4×-spend / few-weeks budget should go** — not into a derivation engine that cannot exist.
4. **Feed the judge.** Expand human grading beyond the current 3 concrete topics to span the abstract-emotion core (zero signal there today). This is the existing grading-tool bootstrap loop — the instrument exists; it needs graded breadth.
5. **Concreteness is a weak, per-class prior** — use it only as a validated volume pre-filter, never as a quality gate; it cannot reject dead metaphor.

**What this depends on:** that an LLM judge can replicate Julian's live/dead axis at acceptable agreement. That is the open research question the investigation surfaces and cannot yet answer with n≈12 over 3 topics — and it is the correct next milestone, in place of any derivation engineering.

---

## Correctness — internal fact-check against the codebase

Before submission, an 11-agent adversarial fact-check re-read every harness and re-ran the API-free ones, recomputing each number the report cites and checking for leakage / base-rate / statistical flaws (`artifacts/factcheck_results.json`):
- **10 / 11 approaches: `numbers_match = MATCH`** — every headline figure reproduced from the committed code/DB.
- **1 real bug found and fixed:** the *uniform* PageRank harness column-normalised with element-wise `A.multiply(diag)` instead of `A @ diag`, yielding an all-zero transition matrix (the PPR never propagated). The Adamic-Adar / resource-allocation / common-neighbour / BFS arms were unaffected and always valid. Fixed (`A @ sp.diags(1/d)` + a column-stochastic assertion) and **re-run** — corrected numbers in the PageRank Results block.
- **Methodology confirmed sound** where it matters: GroupKFold-by-topic prevents leakage in the separability/distillation AUCs; the recall figure is correctly an *upper-bound ceiling*; the guided-beam AUC is *tie-dominated* by unreached pairs (so reach/recall are the operative metrics, as stated).
- **Caveats surfaced and applied:** the apt-vs-inapt "anti-correlation" is amplified by the cohort's same-domain inapt controls (the mechanism, not a universal law); the judge probe spans 3 topics with κ resting on 2 dead chains; cost small-n. All folded into the text above.

## Pointers
- **Claims & evidence ledger:** `claims-ledger.md` (C1–C28; every empirical claim → reproducing artifact).
- **Budget ledger:** `budget-ledger.md` + `artifacts/generation_cost_log.jsonl` (total $6.65).
- **Timeline / audit trail:** `run_log.md` (RL-1…RL-15).
- **Swarm findings:** `artifacts/p1_swarm_findings.json`; **red-team:** `artifacts/redteam_critiques.json`.
- **Algorithms (data structures + faithful pseudocode per approach):** `ALGORITHMS.md`.
- **Harnesses:** `artifacts/*.py` (all re-runnable, API-free except `measure_*_cost.py` and `judge_feasibility.py`).
- **Fact-check:** `artifacts/factcheck_results.json` (per-approach number verification + correctness).
