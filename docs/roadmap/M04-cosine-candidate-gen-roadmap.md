# M04 — Cosine-Sim Candidate Generation

*Drafted 2026-05-21 during M03-S05 close.*

## Premise

The Go Forge endpoint currently generates candidates via curated-cluster overlap (the `per_sense_shared` CTE in `api/internal/db/cascade.go`). This requires the topic and vehicle synsets to share at least one entry in `synset_properties_curated.cluster_id`. The M03 cascade re-rank then sharpens those candidates with concreteness gating and centroid-distance scoring.

This works well for "near-domain" suggestions — words structurally similar to the source — but **cannot surface cross-domain metaphors that share no curated cluster**, which is precisely the class M03's centroid distance was designed to discriminate. The M03 Stage-2 sweep confirmed the discriminative signal exists; the Forge can't currently expose it.

### The concrete evidence

During M03-S05 smoke testing (2026-05-21), the Python `evaluate_cascade_pair` produced these scores for classical metaphor pairs:

| topic → vehicle | python status | ortony_score | cosine_distance | final_score |
|---|---|---|---|---|
| anger → fire | scored | 0.0 | 0.251 | 0.326 |
| idea → light | scored | 0.0 | 0.191 | 0.248 |
| time → money | scored | 0.0 | 0.241 | 0.312 |
| truth → hammer | scored | 0.0 | 0.207 | 0.267 |

All four pairs have `ortony_score = 0.0` — they share no curated clusters between topic-primary-synset and vehicle-primary-synset. The cascade's discrimination comes entirely from the centroid-distance re-rank. **The Go Forge cannot surface any of these as candidates today**, because the cluster-overlap CTE filters them out before scoring.

This is the canonical case M04 unblocks.

## Design

### Shape: ANN-backed centroid candidate generator

- **Index:** approximate-nearest-neighbour structure over `synset_centroids` (300-dim float32). Hnswlib or Annoy in-process, built once at startup or pre-computed and loaded from disk.
- **Memory:** ~40–100 MB additional RAM (graph index + node payload), on top of the existing 50 MB cache. Acceptable for a single-process Go server.
- **Build time:** one-shot from `synset_centroids` table. ~30s for ~36k vectors.
- **Lookup:** topic synset → topic centroid → ANN query → top-K vehicles within a cosine-distance band `[d_min, d_max]`.
- **Distance band:** the M03 sweep peaked at `d_cap = 0.77` with monotonic-up-to-cap rewards. Empirical sweet spot for "metaphorically apt" looks like `[0.4, 0.85]` — far enough that the vehicle isn't a synonym, close enough that there's recoverable mapping. Calibrate via a small re-sweep on the existing M03 eval harness.
- **Composition:** `UNION` with the existing cluster-overlap candidates. The cascade scorer ranks across both sources; the best candidates win regardless of origin.
- **Filter:** concreteness gate (M03's signed-delta `vehicle - topic ≥ 1.0`) applied SQL-side or post-ANN to drop abstract vehicles. Probably post-ANN is fine — the ANN result set is already bounded at K~100.

### Hot-path cost

Per-request, the cascade-enabled `/forge/suggest` adds:
- 1 cache lookup for topic centroid (already amortised)
- 1 ANN query: O(log N) ~ <1 ms
- Filter pass: O(K) ~ negligible
- Cascade scoring for the union candidate set: unchanged shape, slightly larger set

Net impact: negligible vs the current ~430 ms baseline (which is dominated by the SQL CTE for cluster candidates).

### Implementation surface

Estimated 1-2 day Go feature:

1. ANN index abstraction (`api/internal/embeddings/ann.go`) — pluggable: start with hnswlib (`github.com/hnswlib-go/hnsw` or similar; check current Go ANN library health).
2. Index build: `LoadSynsetCentroidANN(db)` similar to `LoadCascadeCache`, builds the index at startup.
3. Candidate generator: `GetForgeCascadeCandidatesByEmbedding(topicSynsetID, threshold, dBand, k)` — returns CascadeCandidate-shaped rows from the ANN result.
4. Handler integration: `handleSuggestCascade` unions cluster-overlap + embedding-band candidates, dedupe by synset_id, run cascade scoring.
5. Calibration sweep: re-run M03 eval harness with the union candidate set to confirm the embedding-band candidates lift `separation_score` above the M03 baseline of +0.1779.

### Configuration

New cascade-config knobs:
- `embedding_d_min` (default 0.4)
- `embedding_d_max` (default 0.85)
- `embedding_top_k` (default 100)
- `candidate_sources`: enum `cluster_only | embedding_only | union` (default `union` post-M04, `cluster_only` for backward compat)

## Relationship to M05 (Type-Aligned Structural Matching)

M05 sharpens *scoring* with property-type diversity bonuses. It composes cleanly on top of M04 — once the candidate set is broader, type-alignment has more candidates to discriminate.

**Order matters.** Doing M05 before M04 would optimise the scoring of a candidate set that systematically excludes apt cross-domain pairs — peak diminishing returns. Doing M04 first delivers the eval-cohort improvement *and* gives M05 a richer set to discriminate.

This is why M04 (cosine candidate gen) was promoted ahead of the original M04 (type-aligned), now renumbered as M05.

## Relationship to The Bridge

The Bridge (queued, no number) is the dual of the Forge: given source AND target, return the path through wordspace linking them. It needs:

1. Bidirectional graph search (BFS or A*)
2. **Embedding-prefilter A***: at each frontier expansion, prefer nodes whose centroid is closer to the meet-in-the-middle target. **This requires the same ANN index M04 builds.**
3. Cluster-cluster adjacency for short-path enumeration
4. Concreteness gradient for direction-aware traversal

M04's ANN index is the load-bearing infrastructure for the Bridge's embedding-prefilter step. Building M04 first means the Bridge inherits a ready-made ANN layer and reduces from "2 days from scratch" to "1-1.5 days of orchestration."

### Forge / Bridge unification — the language-structure framing

A natural temptation is to fold the Forge and the Bridge into one algorithm with different hyperparameters. The instinct points at a real architectural opportunity, but the unification lives at the *language-structure* layer, not the *algorithm* layer.

**Both operate on the same language structure:**
- Concept-senses as nodes (synsets)
- Semantic relations as edges (cluster overlap, embedding distance, type alignment, antonym links)
- A concreteness gradient defining traversal direction
- Property-type features colouring each node

That structure is the shared substrate. Layer it cleanly and both Forge and Bridge sit on top as thin orchestrators:

- **Forge** = 1-hop frontier expansion from source, top-K by cascade score → "give me destinations"
- **Bridge** = bidirectional A* between source and target, top-K paths by path-cascade score → "give me paths"

The traversal algorithms are genuinely different (single-source vs single-pair shortest path; BFS frontier vs bidirectional A*). The optimisation targets are different (Forge needs sub-100ms p99 for live UX; Bridge can run slower and also serves offline eval-cohort generation). Pretending they're the same algorithm would obscure both.

**The elegant move:** extract the shared language structure into a small `metaphor` package — concept graph, cascade scorer, candidate generators, type-aware features. Forge and Bridge each consume it as orchestrators on top. The structure is the load-bearing unification; the orchestrators stay distinct.

This package extraction is a natural milestone between M04 and the Bridge — possibly its own slice as part of Bridge planning. Capture as a backlog note for now.

## Success criteria

1. **Candidate-set lift:** with M04 enabled, classical cross-domain metaphor pairs (anger→fire, idea→light, time→money) surface in `/forge/suggest` for their source words. Verified by a Go integration test pinning a small fixture set.
2. **Eval-harness lift:** re-running the M03 eval harness with the union candidate set produces `separation_score > 0.1779` (no regression from M03's plateau) AND demonstrably surfaces more apt MUNCH pairs.
3. **Latency budget:** single `/forge/suggest?word=...&limit=50` request under cascade returns within 500 ms p99 on the production DB. (M03 baseline ~430 ms.)
4. **No backward incompatibility:** legacy `cluster_only` mode reproduces today's behaviour exactly; cascade default switches to `union` only after the calibration sweep passes.

## Open questions

- **ANN library choice for Go.** hnswlib has Go bindings of varying maturity; annoy has a Go port. Audit options before committing — index portability matters if we ever ship a Docker image.
- **Distance band calibration.** `[0.4, 0.85]` is a hypothesis. The M03 sweep covered `d_cap` but not the lower bound. A small one-day re-sweep over `(d_min, d_max)` would tighten the defaults.
- **Pre-built vs runtime-built index.** Runtime build is ~30s startup penalty. Pre-built + loaded-from-disk is faster but adds a build-step + artifact storage concern. Default to runtime-built for now; revisit if startup time becomes a deploy issue.
- **Memory footprint.** ~40-100 MB is a rough estimate; tighten via prototype.

## Dependencies

- M03 (cascade scoring) — landed.
- `synset_centroids` table populated to 99%+ — already true on the current DB.
- A modern Go ANN library that compiles cleanly on Linux/amd64. Audit pre-implementation.

## Estimated effort

1-2 day Go feature for the implementation; +0.5-1 day for the calibration sweep and integration testing. Total: 2-3 days.
