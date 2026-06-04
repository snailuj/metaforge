# CLAIMS & EVIDENCE LEDGER (live)

Every empirical claim → its reproducing artifact. A claim with no artifact is a **hypothesis** and labelled so. Maintained throughout the run, not just at the end.

| # | claim | status | evidence / repro artifact |
|---|-------|--------|---------------------------|
| C1 | The graph's `has_property`/`antonym_of`/`metonym_of` arms are pure derivations (no per-topic LLM); only `metaphor_link` needs generate-then-judge | **verified** | `data-pipeline/SCHEMA.sql:399-445` (the VIEW) |
| C2 | 81,000 synsets carry curated property-clusters over 7,728 shared clusters; 81,602 carry raw properties | **verified** | run_log RL-2 sqlite counts |
| C3 | Shared-≥1-cluster candidate pairs = 454,972,167; max cluster 7,075 synsets | **verified** | run_log RL-2 fan-out query |
| C4 | Human ground truth = 11 judged chains (8 live/1 dead/2 null) of 200 generated | **verified** | run_log RL-2 grading parse |
| C5 | Generation baseline = Haiku(10 vehicles)→Sonnet(10 ordered chains) per topic, ~2 calls/topic | **verified** | `data-pipeline/scripts/run_chain_spike.py` (G5) |
| C6 | `claude -p` cold call carries ~57k cache-creation tokens (~$0.07 Haiku floor), amortised in 5-min cache windows | **verified (n=1)** | run_log RL-1 probe; needs n>1 to bound variance |
| C7 | Raw shared-feature overlap is low-precision for LIVE cross-domain metaphor | **HYPOTHESIS** (strong prior from M02 null + product-target mismatch, G8) | to be measured on gold cohort |
| C8 | A combinatorial recall-gen + pruning can collapse 455M → tractable high-precision candidate set | **HYPOTHESIS** | P1 H-A analysis + measurement |
| C9 | Baseline "≈1hr / 20 topics × 10 vehicles" | **UNVERIFIED (operator estimate, high variance)** | to re-characterise with CI in P2 |

## Update (checkpoint C1)
| # | claim | status | evidence / repro artifact |
|---|-------|--------|---------------------------|
| C7 | Raw shared-feature overlap is low-precision for LIVE cross-domain metaphor (surfaces synonyms/dead metaphor) | **VERIFIED (direct, API-free)** | `artifacts/derive_candidates.py` + `derived_cohort_ms2.json` (RL-5) |
| C8 | df-cap pruning collapses 455M fan-out to tractable (df200→8.94M, df30→271k) dropping only the mega stop-word clusters | **VERIFIED** | RL-4 collapse curve |
| C10 | Pruning mega-clusters for tractability simultaneously strips abstract topics (anger/time/life/hope) of nearly all candidates — their signal lives in the dropped generic clusters | **VERIFIED (cohort n=20)** | RL-5 (`n_topic_clusters_surviving` 0–2 for abstract topics) |
| C11 | Embedding substrate exists for distance-gated approaches: synset_centroids=81,185 | **VERIFIED** | RL-6 sqlite count |
| C12 | ~2000 apt + ~2000 inapt (topic,vehicle,shared_features) triples already exist as a labelled cohort | **VERIFIED** | RL-6 `metaphor_spike_*_phase2_*.jsonl` |
| C13 | Topic-synset snapping is sense-noisy (anger→'make angry', heart→'playing card', road→figurative) — pollutes any feature-derived edge | **VERIFIED (observed)** | RL-5 definitions; corroborates PIPELINE 'Snapping reconciliation' backlog |

## Update (checkpoint C2 — PRIMARY hypothesis refuted)
| # | claim | status | evidence / repro artifact |
|---|-------|--------|---------------------------|
| C14 | The 80k shared-feature substrate ALONE separates apt-vs-inapt at AUC 0.552 (~chance); the embedding distance 0.571; topic-specific features together 0.580 | **VERIFIED (grouped 5-fold CV)** | `separability_experiment.py` / `separability_result.txt` |
| C15 | The only usable context-free signal is CONCRETENESS: concreteness-only AUC 0.812 ≈ all-features 0.818; apt vehicle concreteness 4.51 vs inapt 3.58 (topics balanced). It is topic-independent → filters, does not generate. Confound: inapt-cohort construction may make 0.81 an upper bound | **VERIFIED** | same |
| C16 | Shared-feature derivation recall of apt vehicles is near-zero: 2.10% (df200), 31.5% (no-cap, but all via non-discriminative mega-clusters); INAPT pairs share MORE at every granularity (anti-correlation) | **VERIFIED** | `recall_ceiling.py` / `recall_ceiling_result.txt` |
| C17 | Mechanistic root cause: only 0.31% (18/5846) of Haiku's OWN claimed shared-features for apt pairs are present in both synsets' DB enrichments — the metaphor bridge feature is contextually constructed, not retrievable from static per-concept enrichments | **VERIFIED** | same |

## Update (checkpoint C3 — swarm verdicts + cost reframe)
| # | claim | status | evidence / repro artifact |
|---|-------|--------|---------------------------|
| C18 | Embedding ANN bands are anti-correlated with aptness: median apt vehicle rank 2,870/81,185; recall@200=13%; inapt outrank apt at every band; 50% recall needs b~2870 → 11.5M verify calls = $86k-878k (6-60x baseline) | **VERIFIED (swarm H-B)** | `artifacts/hb_band_recall.py` |
| C19 | A distilled context-free classifier reaches AUC 0.764 but is ~1 feature (concreteness); dead-metaphor AUC 0.608 → pre-filter, not a live-metaphor proposer | **VERIFIED (swarm H-C, replicates my separability)** | `artifacts/hc_fast_multivariate.py` |
| C20 | Symmetry & transitivity are invalid for metaphor: 0/1112 apt pairs reverse to apt; transitive closure 93%+ garbage; 5.9% pairs self-contradict | **VERIFIED (swarm H-F)** | `artifacts/hf_relational_shortcuts.py` |
| C21 | Edge-level caching/dedup is 1.00x by construction (each topic computed once); feature-keyed (V,C) cache invalid (33% reused vehicles flip apt↔inapt) | **VERIFIED (swarm H-E)** | `artifacts/measure_dedup_HE.py` |
| C22 | Direct-measured Haiku vehicle-proposal cost = $0.062±0.017/call (warm, real prompt, 5762-tok output, n=5); supersedes H-D's stale $0.005 estimate. 100k Haiku-step ≈ $6.2k CLI (~$3k API-direct) | **VERIFIED (n=5, σ measured)** | `artifacts/generation_cost_log.jsonl` |
| C23 | ≤4× spend is NOT the binding constraint — generation at 100k is low-thousands of $; the binding constraint is QUALITY ADMISSION (judging live) + thin eval ground truth (n=11) | **ASSESSED (from C18-C22 + G4)** | synthesis |

## Update (checkpoint C3b — Sonnet cost + full pipeline)
| # | claim | status | evidence / repro artifact |
|---|-------|--------|---------------------------|
| C24 | Sonnet chain step = $0.186/call (n=2; anger 0.229, life 0.143), wall ~175s, output ~11.6k tok. Full 2-call pipeline = $0.248/topic. 100k = ~$24.8k CLI full / ~$6.2k Haiku-only; ~$12-15k / ~$3k API-direct. Weeks-feasible at concurrency ~30 | **VERIFIED (n=2, direct cost capture)** | `artifacts/sonnet_cost_result.txt`, `generation_cost_log.jsonl` |
| C22-rev | H-D's $0.005/Haiku-call REFUTED by direct measurement ($0.062); H-D under-counted by using a stale "~$2/400-call" recollection and ignoring large output. Direct measurement supersedes | **RECONCILED** | RL-12, RL-13 |

## Update (checkpoint C4 — red-team corrections)
| # | claim | status | evidence / repro artifact |
|---|-------|--------|---------------------------|
| C4-FIX | Human ground truth: stale read corrected. LIVE data in `.worktrees/next/.../judgements_provisional.jsonl` = 21 chains over 3 topics (anxiety/anchor/ambush), all concrete/action — NO abstract-emotion human labels. v2 two-axis model; exact live/dead split parse-dependent (~7-8 live) | **VERIFIED + corrected** | RL-15; `.worktrees/next/...` |
| C15-RETRACT | The concreteness signal (spike AUC 0.81) is a COHORT ARTIFACT, not a universal signal: it INVERTS on human-graded concrete-action topics (red-team AUC 0.375), consistent with the established G8/Karpathy Loop-1 abstract-vs-concrete cohort inversion. Demoted from "the one usable signal" to "spike-cohort-specific, needs human re-validation per topic class" | **CORRECTED** | redteam_critiques.json (cohort-validity); G8 |
| C25 | WordNet `relations` table (234,810 rows: hypernym/meronym/similar arms) tested as edge substrate → recovers 0/7 canonical live pairs (within-domain taxonomic similarity, same failure). Derivation now refuted across 4 substrates: features, embeddings, relations, glosses | **VERIFIED (red-team harness + my row-count)** | redteam_critiques.json (completeness); relations COUNT=234,810 |
| C26 | NO automated live/dead judge exists in the codebase (`build_judge_prompt`: 0 occurrences). The recommendation's quality-admission gate is UNBUILT and UNVALIDATED | **VERIFIED** | grep RL-15 |
| C27 | The "100k topics" target overshoots the queryable universe: only ~35k synsets carry a curated single-word lemma; frequency-weighted frontier ~15-35k (zipf≥3→35.8k, zipf≥4→18.9k via `frequencies`, 127,311 rows). Cuts cost 3-7× and makes the 200-topic seed ~1.5% of a realistic target | **VERIFIED** | RL-14, frequencies COUNT |
| C28 | CORE REFUTATION (derive impossible) HOLDS ON HUMAN LABELS: under Julian's verdicts, shared-features don't separate live/dead (zero-share 1/7 live vs 1/5 dead) and embeddings don't (dead pairs closer: median rank 320 vs 390 live) — so "generate not derive" is NOT an artifact of the LLM-generated cohort | **VERIFIED (red-team, n small)** | redteam_critiques.json (cohort-validity) |
| C23-FIX | Generation+judging at 100k ≈ $20-29k warm full / ~$6.2k Haiku-only / ~halved API-direct; judging ~600k edges batched ≈ $0.25-2k (small output). "≤4× not binding" → route-dependent without an absolute baseline. Still ORDERS cheaper than rejected retrieve-verify ($86k-878k). Cost is not the primary blocker; the judge is | **CORRECTED** | generation_cost_log.jsonl; redteam (cost-and-judging) |

## Update (checkpoint C5 — multi-hop graph traversal, operator-requested)
| # | claim | status | evidence / repro artifact |
|---|-------|--------|---------------------------|
| C29 | Multi-hop traversal of the unified dedup'd property∪synset graph ALSO fails to derive metaphor edges. Personalized PageRank (the faithful "traverse the graph" metric): discrimination AUC 0.502 (chance); apt-vehicle median PPR rank 30,984/81,185 (cannot propose them); inapt more reachable. Adamic-Adar/RA/CN cap at 0.61 (weak, useless for generation). BFS: every apt AND inapt pair connects at length 2 or 4 (0 unreachable ≤6 hops) → small-world via generic mega-hubs, path-existence uninformative. Refutation now spans pairwise AND graph-traversal framings | **VERIFIED (API-free)** | `multihop_graph_experiment.py` / `multihop_graph_result.txt` |

## Update (checkpoint C6 — operator-requested guided traversal + judge feasibility)
| # | claim | status | evidence / repro artifact |
|---|-------|--------|---------------------------|
| C30 | SIGNAL-GUIDED multi-hop beam search (POS-filtered nouns; kNN edges; cosine-smoothness + concreteness + cross-domain signals) does NOT beat direct embedding. Local schemes reach inapt>apt (synonym bias); cross-domain push corrects direction (apt>inapt) but tiny; best apt recall@200 ≈ 11.9% (< direct 13%); AUC 0.506–0.545 (≈chance) across 4 schemes × depth{2,3} × beam{300,800,2000}. Structural: geometry can't pick WHICH far node is the apt vehicle for THIS topic | **VERIFIED (API-free)** | `guided_traversal_experiment.py`, `guided_traversal_wide.py` + result txts |
| C31 | LLM judge feasibility vs Julian's verdicts (n=12 chains/2 topics): Haiku 75% κ+0.44, Sonnet 75% κ+0.44, Opus 64% κ+0.31; ALL models FP=0 (never admit a human-dead metaphor) but FN≈30% (reject Julian's live). Out-of-box judge = conservative-but-precise, moderately aligned, needs calibration | **VERIFIED (n=12, in-sample)** | `judge_feasibility.py`, `judge_feasibility_rows.jsonl` |
| C32 | Sonnet generation graded ~71% live (15/21) by Julian over 3 topics (v1 label + v2 metaphor axis); only positive quality anchor, directional only | **VERIFIED** | `.worktrees/next/.../judgements_provisional.jsonl` |

## Update (checkpoint C7 — gloss substrate now actually tested)
| # | claim | status | evidence / repro artifact |
|---|-------|--------|---------------------------|
| C33 | Gloss-as-features (topic vs vehicle DEFINITION content-word overlap) also fails: AUC 0.537 (~chance); apt share >=1 gloss word 4.6% vs inapt 11.8% (anti-correlated). 4th tested substrate. (Previously asserted-not-measured; now measured.) | **VERIFIED (API-free)** | `gloss_overlap_experiment.py` / `gloss_overlap_result.txt` |

## Update (checkpoint C8 — PPR bug fix + corrected numbers)
| # | claim | status | evidence / repro artifact |
|---|-------|--------|---------------------------|
| C29-FIX | Uniform-PageRank harness had an all-zero-transition-matrix bug (element-wise `A.multiply(diag)` vs `A @ diag`); FIXED + re-run. CORRECTED: PPR discrimination AUC 0.615 (raw) / 0.630 (idf) — weakly above chance, ~AA/RA level; but anti-correlated as a GENERATOR — apt median PPR rank 14,202/81,185, inapt 6,238 (inapt closer); recall@100 apt 2.0%. AA/RA/CN 0.606/0.609/0.599 (always valid). BFS unchanged (all pairs 2–4 hops, 0 unreachable). Conclusion (traversal cannot derive apt edges) HOLDS with corrected, weak-not-degenerate numbers | **VERIFIED (re-run)** | `multihop_graph_experiment.py` (fixed) / `multihop_graph_result_FIXED.txt` |
