# Metaphor-Graph Fitness Audit

**Date:** 2026-06-11 · **Status:** adversarially reviewed (4 workflow phases, 21 agents: 5 grounding + gap critic, 3 probes + digest, 5 hypothesis builders + 5 dedicated refuters, 1 report fact-checker — whose corrections are folded in) · **Operator brief:** assess fitness of the graph schema + population methodology (incl. all prompts/output formats) for *algorithmically deriving novel, apt metaphors* between synsets/lemmas (noun-primary); accuracy ≈ Julian's graded verdicts; commodity hardware; survey what's been attempted; adversarially assemble 3–5 competing hypotheses.

**Product constraints in force:** creative-writing aid for **middle grades and up** (not a linguistics bench); schools/colleges deployment ⇒ **provably-zero lookup exfiltration** (runtime LLM only if self-hosted/edge AND quantified-feasible). Gold = operator gradings only.

---

## 1. Executive verdict

**UNFIT AS-IS; RIGHT SKELETON.** The bridge-centric schema's bones (path-first proposals, multi-proposer pool, per-(bridge,judge) verdicts, idempotent hashing, FK-to-synset spine, index shape good to ~1M rows on SQLite/commodity hardware) are correct. But the substrate fails the fitness definition on three load-bearing counts:

1. **It cannot store the verdicts it exists to learn from.** `metaphor_judgments` is a single flat enum (`live/dead_synonym/dead_lakoff/irrelevant/edge_case`) predating the v2 two-axis verdict model — linkage axis, tiers, `tags[]` (bad_head unfilterable in SQL), ordinal confidence, rounds, and supersedes chains all have no home.
2. **It persists the dead features and omits the live one.** Bridges cache the four cascade features measured **at chance** for liveness (raw AUC ≈ 0.50; 16-feature grouped-CV 0.554) and have no columns for `max_hop_cos`/`std_hop_cos` — the only verified signal. `chain_signature` (proposer + phrases) is incompatible with `path_hash` (intermediates-only), so even the 4,390 precomputed geometry rows can't be joined without recomputation; bridge steps drop per-step `phrase`/`head`, making the ~31–34% bad_head defect undiagnosable from the DB.
3. **The graph has no graph.** All three `metaphor_*` tables are 0 rows in every DB; staging never received the DDL at all (working assumption was wrong — the only DDL-bearing DB is the main checkout's typed one). All 95 verdict records live in JSONL on a deploy branch. "Metaphor-graph-completion" currently has nothing to complete: synset-level edge recurrence ~5/248, and KG-embedding/GNN methods are dead below 10³–10⁴ edges.

**The strong (structural-extrapolation) form of the incumbent hypothesis is unfit at current and near-term scale.** The defensible centre of gravity after the adversarial round: a **generate → measured-judge → geometry-feature → judged-index factory** (H3's spine, minus its refuted serving fallback), with every other hypothesis demoted to *features* or *cheap pre-registered probes*, and a short list of hypothesis-independent schema/pipeline repairs that every agent independently endorsed (§6).

The binding constraint is unchanged — five adversarial refutations independently converged on it (sharing, to be fair, the same 90-verdict evidence base): **the unbuilt, κ-measured judge + label scale** — not the schema, not new feature families.

---

## 2. Pinned evidence base (corrected anchors)

Denominators pinned by two independent agents (full-file hand-reads, double-verified; Bash classifier outages prevented scripted re-derivation — flagged in §9):

| Quantity | Value |
|---|---|
| Verdict records | 95 raw → **90 resolved** (3 superseded, 2 latest-wins) |
| Classes | **49 live / 37 dead / 4 irrelevant** (86 live+dead) |
| Topics | **22 topic_synset_ids / 19 topic lemmas** (light, argument, anger split across senses r1 vs r2) |
| bad_head | 29–30 tagged = **33.7%** of live+dead; root cause = generation-time phrase→head-lemma loss (99.6% of steps snap fine); rows STAY in liveness corpus, excluded from geometry only |
| Effective linkage (bad ∨ {bad_head, leap, merge}) | ≈ 35 bad / ≈ 54 good (sums to the prior 89-snapshot; re-derive at 90). Raw v2 linkage-bad = **12** of 85 v2 rows; resolved live+dead bad-linkage = **11** (6 live + 5 dead) — slice discrepancy flagged; needs the single derivation script (§7 Tier-0e) |
| Geometry (within-topic concordance, current snapshot) | **max_hop_cos 0.667** (62/93 pairs, 14 topics); **0.767 bad_head-clean** (33/43, 10 topics). The earlier 0.85 was a smaller prior snapshot. std_hop_cos 0.667/0.700 |
| endpoint_cos_dist | 0.531 within-topic / 0.622 cross-topic = a **topic-level prior**, not chain quality; 27% structural nulls (incl. ALL 10 adornment rows) |
| Fragility | ambush = 24/93 pairs (9/10 bad_head, 5/6 bad-linkage lives); drop-adornment moved an earlier estimate to 0.580; 11/86 chains single-hop (max_hop degenerates to endpoint) |
| Property overlap | **INVERTED**: dead pairs share ≥1 curated cluster 0.370 vs live 0.227 |
| Coverage holes | 12 graded vehicles with ZERO curated properties — exactly the live-skewing rare nouns (palimpsest, sargasso, patina, undertow, thunderhead…); 27% of pairs missing ≥1 endpoint centroid; cascade scored only 32/71 graded pairs |
| Vehicle flips | **4/4** vehicles graded under ≥2 topics flip live↔dead (palimpsest, wound, tide, river) — liveness is pair-level; flips occur between plausibly same-domain topics |
| Corpus | 2,750 = **raw sum** of the live-worktree files (r1 200 + r2 1,804 + handpicked 746) — handpicked is proven NOT disjoint from r2, so the true deduped count is unknown (<2,750). Handpicked triplication **746 live worktree vs 876 snapshot vs 2,386 main uncommitted: unresolved**; geometry 4,390 sigs covers the union; graded 90/90 join geometry |
| Substrate | 107,519 synsets; 81.6k enriched; 822,807 curated property rows / 7,728 clusters; centroids 81,185; SemCor tagcount 34,767; domains 45 (100% backfill claimed). **Deployed staging forge runs ~12k UN-typed enrichment** vs the analysed 80k typed (substrate drift) |
| Gold quality | Single rater; intra-rater reliability **never measured**; live base-rate unstable 0.10–0.71 across cohorts; novelty not yet operationalised as an *analysis* axis — tiers ARE assigned (25/135 raw records: strong 20, surprising 11, ironic 1) but nothing downstream consumes them. **Correction:** an earlier audit claim that tiers were never assigned traced to a stale `models.py` docstring; refuted against live data 2026-06-12. Corpus has since grown: 135 raw records (40 added 2026-06-11/12) — pinned analyses need re-running at the new n |
| POS | Everything graded is noun-noun; all-POS is aspiration, not evidence |
| NEW (this audit; **approximate** — hand gloss-audit during the classifier outage, pending scripted re-check) | ~12/85 graded vehicles snapped to **visibly wrong senses** (jewel→person, aurora→dawn, music→"face the music", ink→cuttlefish-fluid, chisel→cheat-verb…) — a second extraction-layer defect beyond bad_head; 2 graded topics sit on VERB synsets (anchor 23626, anger 30227) |

---

## 3. Structural findings — schema, prompts, population

### 3.1 Schema (bridge layer + property substrate)

Defined at `data-pipeline/SCHEMA.sql:404–521` + `scripts/metaphor_graph.py:93–149` (branch `metaphor-graph/schema-base`, HEAD c403ea19, not an ancestor of main). Representational gaps, most consequential first:

1. Verdict-axes mismatch (single enum vs two-axis v2 + tiers/tags/confidence/rounds/supersedes) — the 0.767-clean subset is **unselectable in SQL**.
2. Geometry omitted, at-chance cascade features cached; `chain_signature`↔`path_hash` join gap; proposer inside the verdict key (one rename orphans all 90 verdicts; ~47% vehicle churn per prompt tweak already measured).
3. Steps drop `phrase`/`head`/snap provenance → bad_head + wrong-sense snaps permanently invisible.
4. No lemma/sense anchoring → sense-split fragmentation (19 lemmas → 22 synset strata; 3 graded topics silently split into zero-pair strata).
5. No negative-edge surface (graph_edges exposes live-only); no round/prompt/model provenance; triage artefacts (2,680+ rows) have no landing tables; `UNIQUE(bridge_id, judged_by)` + update-in-place destroys supersedes history.
6. Live-DB drift: undocumented `property_similarity` (1.55M dead rows in both DBs), `synset_centroids` absent from SCHEMA.sql, index names diverge — committed DDL is not a reliable map of the live DB. `synsets(domainid)` has **no index** (full 107k scan).

Scalability: completion-style queries are point-lookup/posting-list bounded — fine on SQLite at 20k–100k synsets. The hazard is candidate **fan-out** (455M shared-cluster pairs; df-cap → ~271k), not per-query latency.

### 3.2 Prompts + output formats (18 surfaces inventoried)

Cross-cutting defects: **no prompt-version provenance anywhere** (no stored row can be traced to the prompt that produced it); rationales/confidences systematically discarded — including **paid proxy-judge weak labels on the very chains the operator later grades**; edges untyped ("typed nodes, untyped edges" — no prompt asks *why* a hop holds); the **negative-feedback channel is broken** (`build_next_round_prompt.py:82` keys legacy v1 `bad_path` → emits empty AVOID blocks under v2 data); sense lost at every word→synset boundary except topics (the bad_head factory + the wrong-sense snaps above); model aliases float (`haiku`/`sonnet` unpinned) vs pinned generation IDs; latent bug `run_chain_spike.py:285–292` overwrites `step['head']` with the synset_id when `--db` is passed.

**Single highest-signal-per-dollar change** (consensus across three agents): extend chain output `{phrase, head}` → `{phrase, head, gloss-or-sense-index}` + a deterministic head∈phrase validator — ≈ +150–250 output tokens/chain ≈ +$0.01–0.03/topic (~+$100–200 on the held 10k run), collapses bad_head at source, protects the geometry signal and verdict transfer.

### 3.3 Population state

Metaphor layer empty everywhere; truth in worktree-pinned JSONL; the 9-task JSONL→bridges materialisation plan exists, never executed; handpicked-cohort triplication (746/876/2,386) unreconciled; main checkout's verdict file is stale (13 rows vs 95 live).

---

## 4. What has been attempted (compressed; full table in grounding artefacts)

| Attempt | Result | Status |
|---|---|---|
| MRR-era enrichment + evolutionary prompts | MRR 0.0358→0.0073; demoted | superseded |
| M01 eval harness | sensitivity verified; trustworthy instrument | supported |
| M02 asymmetric Ortony | all variants ±0.06 of null | **refuted** |
| M02-S04 substrate (Haiku + sensorimotor) | density 0.8→5.4 props/synset; production model | supported |
| M03 cascade gate-and-rank | sep +0.1779 on MUNCH — but features at chance vs human liveness; demoted to feature-provider | supported*/dead-for-liveness |
| M04 v1 cosine-band (MUNCH) | sweep proved nothing — paraphrase-style cohort | inconclusive |
| M04 v2 (Lakoff cohort) | all cells 0 to −0.27 | refuted |
| M05 type-aligned (γ) | Δsep/Δγ +0.263, merged | supported |
| Metaphor-enrichment pivot spike | 2.78× apt/inapt discrimination | supported |
| Karpathy loop 1 | +28.7% Phase-2 median; Phase-2 vs Lakoff inverted discriminators | supported |
| Karpathy loops 2–3 | Pareto trade; several "wins" sub-1σ; product-misaligned cohort | superseded |
| Context-free edge derivation | **refuted 5 ways** (AUC 0.50–0.55, anti-correlated, 0.31% bridge-feature presence) | refuted |
| Generation subsystem + tripwire | r2 ran (1,804 + handpicked); sense blocker → 10k held | in-flight |
| SQLUNET import | tagcount/domains/BNC landed | supported |
| Grading bootstrap loop | 90 resolved / 22 topics; bad_head 31–34% | in-flight |
| Path-geometry "one big leap" | the only verified scoring signal (0.667/0.767) | **supported** |
| Completion baseline harness | cascade at chance; ~300–500 labels / 80–120 topics guidance | supported |
| LLM judge harness (planned 2026-06-10) | zero code | in-flight |

**Meta-pattern (three regularities):** (1) every *static-similarity* substrate fails for cross-domain liveness in every framing — the bridge feature of a live metaphor is constructed in context (0.31% presence in static enrichments); similarity substrates select synonyms (the inapt direction). (2) What works: instruments validated against gold, and **human-judged, contextually-generated artifacts** — the only verified signal lives in the geometry of generated-then-graded chains. (3) Recurring failure mode: eval-cohort/objective misalignment (MUNCH, Lakoff, proxy bias) — and every judge never measured against gold failed silently (extraction-evaluator ~1% vs 31% reality).

Named high-leverage surfaces never touched by any loop: `snap_properties.py` (~800 lines, flagged repeatedly) and **The Bridge** (target-conditioned bidirectional A*, queued since M02, never built).

---

## 5. The five competing hypotheses — adversarial outcome

Each built as a steelman, then attacked by a dedicated refuter. **All five: WOUNDED** (none killed, none survives as stated). Verdict snapshots:

| # | Hypothesis | Refuter verdict | What survives |
|---|---|---|---|
| H1 | Domain-pair generalisation layer (45 lexname priors + MetaNet conventionality penalty) | wounded | Vehicle-super-domain log-odds as ONE feature (builder's own hand-run ≈0.61 landed in its pre-registered "demote-to-feature" zone); `domainid` index; the topic-marginal-preserving permutation protocol; grade-into-sparse-cells as a *breadth* tactic. The distinctive pair-table claim is currently **untestable** (no cell has ≥2 topics + both classes). Counter-nuance the builder measured: 3 of the 4 vehicle flips ARE consistent with lexname-cell boundaries (only wound defeats domain granularity). MetaNet → held-out eval items only, licence unverified. |
| H2 | Lemma/sense anchoring + extraction fix | wounded | **Large salvage as engineering, not hypothesis:** the DDL additions, content-keyed identity (+ alias table) landed *before* any prompt change, the generator gloss fix before the 10k run, the head-overwrite bug fix. The retro de-noising claim is confounded (bad_head-clean ≈ drop-ambush); the FastText basis swap is a smuggled substrate change toward measured-dead static similarity — dropped. Honest retro test: re-snap the 29 bad_head chains' heads, recompute on the SAME centroid basis, McNemar on common pairs. |
| H3 | Generate-then-rank; graph as judged INDEX, not deriver | wounded | **The spine survives best of all five** — it is the context-free refutation's own recommendation, avoids every measured-dead route, and uniquely produces the 10³–10⁴ judged-edge corpus any future learned completion would need. Deleted: the nearest-topic centroid-cosine serving fallback (static-similarity liveness *transfer*, refuted-in-direction by the 4/4 vehicle flips) and the invented stacked-AUC 0.70–0.78. The keystone test is NOT the rank-lift probe (underpowered: ~12 binary observations) but **Stage-2 judge κ on the 90 verdicts (~$10–30)**. |
| H4 | Relational / structure-mapping features | wounded | One genuinely new, $0 probe: relation-phrase bridge-presence (the 369,461 stored `synset_properties.relation` phrases were **never read by any analysis**; the refuted 0.31% measured property *tokens* only) — but run WITH a verb-collision null and treated as binding. The keystone Stage-1 design was contaminated (operator hand-extracts predicates for verdict-known endpoints); per-hop "why does this hop hold" relation labels in generation survive as edge-typing. |
| H5 | Supervised pair scorer over substrate features | wounded | **The wrapper is right; the basket is half-zombie** (AA/Jaccard + cascade + endpoint cosine = resurrected measured-dead families; vehicle-marginal frequency features misrank every flip pair by construction). Survives as the **distillation/serving layer of the judge hypothesis** once labels scale; single-family pre-registered probes first (frequency *asymmetry* as a pair construction; domain-pair w/ null; bottleneck-bridge leap + hubness audit); missingness-only null model mandatory (live-correlated coverage holes can manufacture AUC that collapses at serving). Serving-blindness finding: a shared-cluster df-capped candidate universe structurally **excludes the 12 zero-property (live-skewing) vehicles** — any precomputed serving artefact needs a kNN-style candidate design before its coverage claim holds. |

**Convergent refuter findings (appeared independently ≥3 times):**
- **No gate on any hypothesis is interpretable without an intra-rater reliability floor.** Single rater, never measured; claimed effects (0.05–0.11 concordance edges) sit inside the plausible noise band. The supersede re-grades + a ~20–30-chain blind re-grade are free material.
- **Topic concentration breaks naive tests**: ambush (24/93 pairs) and adornment (structural nulls) must be pre-registered drop-slices in every probe; cross-topic AUC is inflated by topic-marginal prediction (argument 0/5, anxiety 5/5).
- **Selection ≠ intervention**: reading the bad_head-clean subset (0.767) as the payoff of a fix repeats the M02 cohort-shape artefact; matched-pair designs on common pairs are the honest form.
- **Eval-set burn is live**: every feature family was conceived while staring at the same 90 verdicts; quarantine newly graded labels as rolling holdout.

---

## 6. The hypothesis-independent repair list (unanimous)

Every builder needed these and every refuter endorsed them regardless of verdict — they are substrate debts, not hypothesis bets:

1. **Align `metaphor_judgments` to verdict-model v2**: linkage+metaphor axes, `judgment_tags` child table (tags + tiers), ordinal confidence, round, versioned verdicts ((bridge, judge, judged_at) + latest-view preserving supersedes).
2. **Persist the verified signal**: `max_hop_cos`/`std_hop_cos`/`n_hops` on bridges; per-step `phrase`/`head`/`gloss`/`snap_method`/`snap_score` on steps; drop the four at-chance cascade caches.
3. **Content-keyed chain identity** (strip proposer; `chain_signature_aliases` mapping all 90 existing verdicts) — **must land before any prompt change** (gloss emission re-mints every signature).
4. **Generator emits `{phrase, head, gloss}`** + head∈phrase validator — before the $1.9k 10k run. Fix `run_chain_spike.py:285–292`.
5. **Execute the JSONL→`metaphor_bridges` materialisation** (the 9-task plan) so the graph exists; apply DDL to staging; resolve the deployed-vs-analysed substrate drift (decide which DB ships).
6. **Repair the negative-feedback channel** (re-key on `linkage_effective` + dead; persist AVOID contents + prompt hash) — prompt provenance generally.
7. **Stop discarding paid signal**: persist proxy-judge `{verdict, confidence, reason}` per chain.
8. `CREATE INDEX ON synsets(domainid)`; canonicalise the 746/876/2,386 handpicked triplication; drop the dead 1.55M-row `property_similarity` from both DBs.
9. **Lemma + sensekey columns on bridge endpoints/steps** (sense-split aggregation becomes a query-time choice; fixes the wrong-sense snap visibility too).

---

## 7. Recommendations

**Tier 0 — this week, $0 API, before anything else:**
- **(a) Intra-rater reliability floor**: mine the supersede re-grades + a ~20–30-chain blind re-grade round. *Universal prerequisite — every κ gate and concordance lift is uninterpretable without it.*
- **(b) Domain probe — re-authored pre-registration, then run.** The H1 draft carries the topic-marginal-preserving permutation null (keep it — strongest protocol in the programme) but keys its prior on vehicle super-domain ALONE, pre-registers no drop slices, and its middle zone absorbs most outcomes (the refuter's central critique). Re-author before running: pair-keyed AND vehicle-marginal variants; drop-ambush/drop-adornment slices; concreteness + endpoint_cos_dist ablations (incremental value, not standalone). Cheap either way; decides whether domain enters as a feature.
- **(c) Relation-phrase bridge-presence probe** with verb-collision null (~2h) — binding: at/below floor ⇒ static-relational retrieval joins attribute overlap in the grave; above ⇒ first new substrate lead. (Substrate measured ~89% non-copular/~11% stative this audit — not attributive mush.)
- **(d) Schema hygiene batch** (§6 items 1–3, 8) — small, mechanical, unblocks SQL-side analysis.
- **(e) Single denominator-derivation script**, committed: 95 → 90 resolved → class/linkage/tag slices → geometry subsets — one source of numbers (four reports quoted four slices; this audit itself still carried an 11-vs-12 and an 89-vs-90 drift).

**Tier 1 — the milestone (unchanged by this audit, mandate strengthened): build the κ-measured judge** per `docs/plans/2026-06-10-judge-harness-plan.md`. Stage-2 κ vs the 90 verdicts is the decisive experiment for the whole programme (~$10–30 cached); Stage-1 gate doubles as the bad_head auto-filter. Read all gates against the Tier-0(a) reliability floor. Generator gloss fix (§6 item 4) lands with it, before the 10k run.

**Tier 2 — after labels scale (~300–500 / 80–120 topics):** single-family pre-registered probes (frequency-asymmetry pair construction; bottleneck-bridge leap + hubness audit; domain feature if 0(b) supports); then the H5-shaped supervised distillation layer as the shippable scorer; revisit learned link-prediction only at 10³–10⁴ judged edges. *(The H5 refuter would run the frequency-asymmetry and bottleneck-leap probes sooner — both ~$0/a day; defensible to pull them into Tier 1 as adjuncts if there's slack, with the n=90 power caveat standing.)*

**Deleted / parked:** nearest-topic similarity *transfer* of liveness at serving (refuted in direction); FastText basis swap for geometry; MetaNet as scoring gate (eval items only; licence unverified); ConceptNet pending the ShareAlike decision + content vetting; KG embeddings/GNN at current n; per-vehicle or per-domain *standalone* scoring (vehicle flips).

**Sovereignty architecture (consensus, satisfies the schools constraint by construction):** schools run pure precomputed SQLite lookup — zero LLM, zero network in the serve path; all generation/judging offline at HQ (API Sonnet preferred; quantified sovereign fallback: RTX-3060-class ≈ 29–42 tok/s ≈ 3.5M output tok/day ⇒ judging throughput is never the bottleneck — calibration labels are; Qwen Apache-2.0 cleanest licence). Small local judges are materially worse than Sonnet for aesthetic calls until fine-tuned on ~10³ operator verdicts.

---

## 8. Fitness scorecard (against the operator's definition)

| Criterion | Today | After Tier 0–1 |
|---|---|---|
| Stores the supervision signal | ✗ (JSONL only; schema can't hold v2) | ✓ (materialised, two-axis, tags) |
| Carries the verified scoring signal | ✗ (geometry uncolumned, key-incompatible) | ✓ |
| Derives novel apt pairs algorithmically | ✗ strong form (no graph; recurrence 5/248; static substrates dead/inverted) | partial — generate→judge→index factory; structural derivation deferred to 10³–10⁴ judged edges |
| Accuracy ≈ operator gradings | best verified instrument: within-topic geometry 0.667/0.767; judge κ unknown (zero code) | judge κ measured; reliability floor known |
| Commodity hardware / zero exfiltration | ✓ runtime (lookup-only); ✗ unresolved deployed-substrate drift; ✗ shared-cluster candidate universe excludes the live-skewing zero-property vehicles | ✓ with shipped-DB decision + kNN-style candidate design |
| Noun-primary, all-POS capable | noun-noun only in evidence; 2 graded topics on verb synsets are noise, not coverage | unchanged (flagged, not blocking) |
| Novelty operationalised | ✗ as analysis (tiers assigned in 25/135 records but consumed by nothing; live/dead conflates aptness/novelty/conventionality) | open — candidate: conventionality prior as *negative eval axis*, never a gate |

---

## 9. Caveats & unverified items

- Repeated `claude-fable-5[1m]` safety-classifier outages blocked scripted SQL across multiple agent sessions; the pinned denominators come from independent double hand-reads, and substrate counts are tiered (binary-grep / artefact / doc / target). **Re-run live COUNT(*) verification + the drafted domain-pair script when tooling is stable.**
- H1's ≈0.61 domain concordance is a hand-run with post-hoc buckets — treat as the *middle zone* it pre-registered, pending the frozen script.
- External claims unverified: MetaNet licence; NOC licence; DiStefano exact correlations (paywalled); Gemma-4 licence terms. ConceptNet ShareAlike + FastText-vector ShareAlike (two shipped geometry columns) await an operator licensing decision — school-facing, hence externally-facing.
- The 71% vs 10–20% live-rate gap reconciles as instrument+cohort (operator grading on 3 topics vs conservative zero-FP proxy on ~90 abstract topics); true raw live-rate plausibly 20–50% by topic class — per-admitted-edge cost on core abstract-emotion topics may run 5–20× the headline $0.20–0.29/topic.

---

## Addendum (2026-06-12) — operator product-vision correction

The operator rejected the "judged index = product" framing this report's serving recommendations leaned on, on grounds the audit itself supports: **metaphors are positional goods** — a published static list depreciates on contact with its audience (rust-to-cliché + tool-tagging fear), unlike a thesaurus. The audit's own deepest finding (live bridges are constructed in context; 0.31% static presence) is the measurement-form of "writers create metaphors on the fly."

**Reframed roles:** the judged corpus is the *invisible bootstrap asset* (judge gold, steering memory, fine-tuning set) — never user-facing; the judge is the *teacher model* for a distilled runtime ranker; the **product is the session** — stochastic conditioned generation (topic blends, sensibility knobs: gothic/romance/journalistic), gated by the distilled ranker, session-salted so no two users see the same list. MERMAID (sub-1B, consumer GPU, mapping-conditioned generation + discriminative re-rank, 66–68% human preference) is the literature existence proof of this shape.

**Plan deltas:** Phase A unchanged ($0; judge κ remains the sole kill-gate — it is the teacher either way). Phase B re-purposed from serving-index to distillation corpus (same spend). NEW named spike: **on-device conditioned generation feasibility for schools** (§7's "quantify, never assume" now applies to the product's heart; fallback = combinatorial depth: deep judged pools + session-salted sampling + local knob re-rendering). The scoring-geometry signal (max_hop, now deflating on the 8-topic out-of-sample cohort) is decoupled from the forge: blending is generative conditioning; quality control is the judge. §8's "Commodity hardware ✓ (lookup-only)" row applies to the fallback tier only.

**Artefacts:** grounding `…/tasks/wmv0z9ee1.output` (147,628 B); probes+digest `…/tasks/wc4wlcoxu.output` (69,911 B); hypotheses+refutations `…/tasks/wpf22ytg7.output` (156,200 B) — all under `/tmp/claude-1001/-home-agent-projects-metaforge/3e9f1998-6824-4096-9508-84a8600a54f2/`. **Archival beside this report is PENDING** (the classifier outage blocked `cp` through the whole audit); when tooling recovers: `cp` each to `grounding.json` / `probes-digest.json` / `hypotheses.json` in this directory, then checksum both sides — before /tmp eviction.
