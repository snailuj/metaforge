# M04 — Cosine-Sim Candidate Generation — Design

*Brainstormed and committed 2026-05-23.*

## Premise

The M03 cascade scorer can discriminate apt cross-domain metaphors (anger→fire, idea→light, time→money) via the centroid-distance re-rank — but only when those pairs reach the scorer as candidates. Today's cluster-overlap CTE in `api/internal/db/cascade.go` requires shared `cluster_id` between topic and vehicle synsets, which is false for the canonical cross-domain metaphors. They never become candidates; the cascade never gets to score them.

**M04 is a generation broadener.** It introduces an embedding-band candidate path that surfaces vehicles close to the topic centroid in vector space but structurally disjoint from it in WordNet's cluster graph. The cascade scoring math is unchanged.

## Scope discipline

M04 is **not** a scoring improvement, **not** a novelty-aptness measure, **not** an answer to the cliché-rewarding problem the MRR experiments hit. Those questions belong to M05 (type-aligned structural matching) and M06 (novelty tracking). Conflating them with M04's job would tempt us to overfit to clichéd-but-known cross-domain pairs (Lakoff cohort traps). We measure M04 against **generation lift** (do the candidates surface?) and **non-regression on aptness** (does MUNCH separation_score hold?), and report novelty-related observations as diagnostics — not targets.

## Success criteria

1. **Generation lift (binary)** — classical cross-domain pairs surface as *candidates* in the cascade response. Pinned by a Go integration test on a fixture set: at minimum {anger→fire, idea→light, time→money, truth→hammer}. The test asserts candidate **presence**, not final-score rank.
2. **Non-regression on aptness** — MUNCH `separation_score ≥ 0.1779` under union mode. The post-2026-05-23 baseline (M03 cascade + `idx_lemmas_synset_id`) is the floor; we are not raising the bar with a dedicated classical cohort (which would reify clichés as targets).
3. **Latency budget** — `/forge/suggest?word=...&limit=50` cascade requests stay under 500 ms p99 on production. Post-2026-05-23 baseline: 90-200ms scored, 90-700ms empty-gate-pass. Brute-force cosine scan adds ~30ms estimated. Generous headroom.
4. **Backward compatibility** — `METAFORGE_FORGE_CANDIDATES=cluster_only` reproduces today's M03 behaviour byte-for-byte. Pinned by an integration test that compares responses to a stored M03-snapshot.

## Architecture

Five layers, three of which gain new components:

| Layer | M03 (existing) | M04 (new in this milestone) |
|---|---|---|
| Data | `synset_centroids` (35,613 rows), `CascadeCache.Centroids` map, `idx_lemmas_synset_id` (landed 2026-05-23) | — |
| Candidate gen | `GetForgeCascadeCandidatesByLemma` (cluster-overlap CTE) | `GetForgeCascadeCandidatesByEmbedding` (brute-force cosine scan), `unionCandidates` (dedup, cluster-wins-on-conflict, Source tag) |
| Scoring | `EvaluateCascadePair` (gate → ortony → cosine reward) | — (unchanged) |
| Config | `CascadeConfig.ConcretenessThreshold`, etc. | `CandidateSources` enum (`cluster_only \| embedding_only \| union`), `EmbeddingDMin`, `EmbeddingDMax`, `EmbeddingTopK`, env `METAFORGE_FORGE_CANDIDATES`, `CascadeConfig.Validate()` |
| Observability | `observe.Start` per-stage timing | `cascade_embedding_query` stage timer, per-request anomaly aggregator (closes R1-D4 + R4-D1), runtime row-count tripwire on `synset_properties_curated` |

**Key invariants:**

- The brute-force cosine scan reads from `CascadeCache.Centroids` (already loaded at startup). Zero new DB round-trips on the hot path.
- Embedding path resolves topic via polysemy-ASC primary source synset (matches existing `resolvePrimarySynset` parity rule). Multi-sense embedding queries deferred to v2 — see PIPELINE backlog entry.
- Cluster wins on conflict during union; the cluster-row's `jaccard_salience > 0` is the richer signal. Embedding-only rows have `jaccard_salience = 0` and rely on the cosine reward alone. No scoring-math change.
- The `Source` tag (`"cluster" | "embedding" | "both"`) is purely diagnostic in v1. The calibration sweep will tell us whether two-path candidates correlate with apt MUNCH pairs; if so, a co-generation bonus (β·1{both}) lands as v2.
- No new third-party dependencies. Brute-force cosine scan at 35k × 300-dim is ~30ms estimated.

## Components

### `GetForgeCascadeCandidatesByEmbedding`

**Location:** `api/internal/db/cascade_embedding.go` (new file, sibling to `cascade.go`).

**Signature** (final shape — function accepts DB for primary-synset resolution + synsets-row lookup):
```go
func GetForgeCascadeCandidatesByEmbedding(
    database *sql.DB,
    cache *CascadeCache,
    lemma string,
    cfg ForgeEmbeddingConfig,  // DMin, DMax, TopK
) ([]CascadeCandidate, error)
```

**What it does:** Resolves topic synset (polysemy-ASC primary), reads topic centroid from cache, brute-force-scans all 35k entries computing cosine distance, filters by `[DMin, DMax]`, returns top-K nearest as `CascadeCandidate` rows with `SalienceSum=0`, `ContrastCount=0`, `SharedProps=nil`, `Source=SourceEmbedding`, `SourceSynsetID=topicSynsetID`. Source-side definition/POS comes from the topic synset row; target-side POS/Definition come from a single batched `synsets` lookup for the top-K target IDs.

**Depends on:** `CascadeCache` (read-only), `embeddings.CosineDistance`, `synsets` table (one batched query), `lemmas` table via the existing primary-synset resolver.

**Errors:**
- `ErrLemmaNotFound` if lemma has no curated synsets (same contract as cluster path)
- Wrapped DB errors for the synsets row lookup
- Returns `(nil, nil)` if topic synset is enriched but its centroid is absent (defensive — this should be unreachable since 100% of enriched have centroids)

### `unionCandidates`

**Location:** `api/internal/handler/cascade_union.go` (new file — extracts testable logic from `handler.go`).

**Signature:**
```go
func unionCandidates(cluster, embedding []db.CascadeCandidate) []db.CascadeCandidate
```

**What it does:** Dedup by `SynsetID`; cluster wins on conflict; attaches `Source` tag to each row. Cluster-only candidates → `SourceCluster`; embedding-only → `SourceEmbedding`; both-paths → `SourceBoth` (cluster row's fields preserved, only the tag changes).

**Depends on:** nothing beyond the input slices.

### `CandidateSources` and `CandidateSource` enums

**Location:** `api/internal/forge/cascade.go` (alongside existing `CascadeStatus`).

```go
// Config-side enum — which candidate-generation paths to run.
type CandidateSources string
const (
    SourcesCluster   CandidateSources = "cluster_only"
    SourcesEmbedding CandidateSources = "embedding_only"
    SourcesUnion     CandidateSources = "union"
)
func (s CandidateSources) Valid() bool { /* one-line switch */ }

// Per-row enum — which path produced this candidate. Different value set:
// a `union`-mode request can produce rows tagged cluster, embedding, OR both.
type CandidateSource string
const (
    SourceCluster   CandidateSource = "cluster"
    SourceEmbedding CandidateSource = "embedding"
    SourceBoth      CandidateSource = "both"
)
func (s CandidateSource) Valid() bool { /* one-line switch */ }
```

JSON wire format stays string-typed (`"source": "embedding"`) — same shape as today's `CascadeStatus`. Closes the part of D2 (constrained-type discipline) that touches the cascade surface; the rest (CascadeStatus/Composition discipline) remains anchored against the metaphor-package extraction.

### `CascadeConfig` extensions

**Location:** `api/internal/forge/cascade.go` (extends existing struct).

```go
type CascadeConfig struct {
    // ...existing fields
    CandidateSources    CandidateSources  // default SourcesUnion after sweep verdict; SourcesCluster pre-verdict
    EmbeddingDMin       float64           // default 0.4 (hypothesis, sweep-validated)
    EmbeddingDMax       float64           // default 0.85 (hypothesis, sweep-validated)
    EmbeddingTopK       int               // default 100
}

func (c CascadeConfig) Validate() error { /* dMin range, dMax > dMin, topK > 0, CandidateSources.Valid() */ }
```

**Env wiring:** `METAFORGE_FORGE_CANDIDATES` → maps to enum string. Invalid values fail `Validate()` at startup. The CLI gains a `--candidate-sources` flag mirroring the env var (same pattern as `--cascade-timing`).

### Per-request anomaly aggregator

**Location:** small unexported struct in `api/internal/handler/handler.go`.

```go
type cascadeAnomalies struct {
    concretenessCacheMisses int
    emptyPropsBatchFlag     bool
}
```

**Per-request flow:**
- Replace today's per-candidate `slog.Error("cascade candidate concreteness missing from cache despite SQL filter", ...)` with `anomalies.concretenessCacheMisses++`.
- Replace today's per-request `slog.Error("cascade batch properties returned empty for all candidates", ...)` with `anomalies.emptyPropsBatchFlag = true`.
- At request close, attach `concreteness_cache_misses=N` and `empty_props_batch=bool` as attributes on the existing `cascade_request_total` timing record.
- Single Error log post-loop ONLY when `concretenessCacheMisses > 0`, with the total — matching the `db.go` malformedLogCap pattern of "log first, count rest" inverted to "count all, log aggregate once."

This closes R1-D4 and R4-D1 from the 2026-05-22 review log.

### Runtime row-count tripwire

**Location:** `NewHandlerWithCascade` in `api/internal/handler/handler.go`.

Extends the existing post-preflight assertion loop (currently covers `synset_concreteness` and `synset_centroids`) to ALSO assert `synset_properties_curated` is non-empty. One-line addition to the existing tripwire pattern — addresses the half of R1-D4 that wants startup-time fail-loud on cascade-supporting table truncation.

### Calibration-sweep harness

**Location:** `data-pipeline/sweeps/m04_embedding_band.yaml` (new) + `data-pipeline/sweeps/m04_embedding_band_verdict.md` (output).

**What it does:** Sweep grid over `(d_min, d_max)` — e.g. `d_min ∈ {0.3, 0.4, 0.5}`, `d_max ∈ {0.75, 0.85, 0.95}` — = 9 cells. Each cell runs the MUNCH cohort against the API in union mode with the configured band. Output is per-cell `separation_score`, `aptness_rate`, plus diagnostic counts of `cluster_only` / `embedding_only` / `both_paths` candidates and their final_score distributions.

**Verdict deliverable:** Markdown summary committed to `data-pipeline/sweeps/m04_embedding_band_verdict.md`:
- Top performing cell (best separation_score)
- Whether it beats the M03 baseline of 0.1779 (non-regression check)
- Diagnostic observations re: two-path candidate correlation with apt pairs (informs v2 β-bonus decision)
- Verdict: ratify `SourcesUnion` as default with the chosen band, OR keep `SourcesCluster` default and document the recalibration TODO

## Per-request data flow

```
HandleSuggest validates → handleSuggestCascade
│
├─ stopTotal := observe.Start("cascade_request_total")
│  anomalies := &cascadeAnomalies{}
│
├─ Cluster-overlap candidate gen (skipped if mode == SourcesEmbedding):
│  ├─ stopCand := observe.Start("cascade_candidates_query")
│  ├─ cluster, err := db.GetForgeCascadeCandidatesByLemma(...)
│  ├─ stopCand(word, count=len(cluster))
│  ├─ err == ErrLemmaNotFound → stopTotal(outcome=lemma_not_found) → 404
│  └─ err != nil → stopTotal(outcome=candidates_error) → 500
│
├─ Embedding-band candidate gen (skipped if mode == SourcesCluster):
│  ├─ stopEmb := observe.Start("cascade_embedding_query")
│  ├─ embedding, err := db.GetForgeCascadeCandidatesByEmbedding(database, cache, word, cfg.Embedding...)
│  ├─ stopEmb(word, count=len(embedding), no_centroid=bool)
│  ├─ err == ErrLemmaNotFound + mode == SourcesEmbedding → 404
│  └─ err != nil → stopTotal(outcome=embedding_error) → 500
│
├─ Union (single-mode passes through unchanged):
│  └─ candidates := unionCandidates(cluster, embedding)
│
├─ Empty short-circuit (today's path, unchanged):
│  └─ len(candidates) == 0 → stopEncode + empty 200 + stopTotal(empty_no_gate_pass | empty_encode_error)
│
├─ Batch-props query (today's path, with aggregator):
│  ├─ stopProps := observe.Start("cascade_batch_props_query")
│  ├─ propsByID, err := db.GetSynsetClusterPropertiesBatch(...)
│  ├─ stopProps(...)
│  ├─ err != nil → stopTotal(outcome=batch_props_error) → 500
│  └─ len(propsByID) == 0 AND len(candidates) > 0 → anomalies.emptyPropsBatchFlag = true
│
├─ Scoring loop (today's math + aggregator):
│  ├─ stopScore := observe.Start("cascade_scoring_loop")
│  ├─ for each candidate c:
│  │     concreteness cache miss → anomalies.concretenessCacheMisses++ (was per-candidate slog.Error)
│  │     EvaluateCascadePair → CascadeResult
│  │     Status != Scored → droppedNonScored++; continue
│  │     append Match with Source: c.Source
│  └─ stopScore(word, scored, dropped_non_scored)
│
├─ Sort + encode (today, unchanged):
│  ├─ sortByFinalScore(matches)
│  ├─ stopEncode := observe.Start("cascade_response_encode")
│  ├─ json.NewEncoder(w).Encode(resp)
│  └─ stopEncode(suggestion_count)
│
└─ Close-out:
   └─ stopTotal(
        word, outcome=scored|*_encode_error,
        candidates=len(candidates), scored_count=len(matches),
        concreteness_cache_misses=anomalies.concretenessCacheMisses,
        empty_props_batch=anomalies.emptyPropsBatchFlag,
        cluster_only=N, embedding_only=N, both_paths=N,  // diagnostic source-mix
      )
```

## Error handling

| Condition | Path | Response | Logging |
|---|---|---|---|
| Topic synset present, centroid absent (rare — defensive) | Graceful | Continue cluster-only that request | `slog.Debug("no topic centroid, skipping embedding path", ...)` + `stopEmb(no_centroid=true)` |
| Topic synset not enriched | `ErrLemmaNotFound` from primary-synset resolver | 404 (same as cluster path today) | `stopTotal(outcome=lemma_not_found)` |
| Cosine scan finds zero in-band hits | Legitimate (no apt cross-domain neighbours) | Continue with `embedding=nil` | None — `stopEmb(count=0)` is the signal |
| Cosine scan errors (cache map corruption — should be unreachable) | Hard fail | 500 | `slog.Error("embedding scan failed", ...)` + `stopTotal(outcome=embedding_error)` |
| `CascadeConfig.Validate()` fails | Hard fail | Server fails to start | Standard startup-failure path |
| `synset_properties_curated` empty at startup | New runtime tripwire | NewHandlerWithCascade fails to construct | Matches existing tripwire message shape |
| Per-request concreteness cache divergence | Counted in aggregator | Continue request | Single Error post-loop with total count (was per-candidate spam) |
| Per-request empty `propsByID` | Counted in aggregator | Continue request (today's behaviour) | Single Error attribute on `cascade_request_total` (was per-request Error) |

**Notable invariants:**
- `embedding_only` mode + un-enriched lemma still 404s (cascade is fundamentally curated-property-based)
- The cosine scan iterates `CascadeCache.Centroids` keys directly; every entry has a valid centroid by construction
- Unrecognised `CandidateSource` would be a structural bug, not a user-input concern — pinned via Go const + `Valid()` + test

## Testing

| Surface | Test type | What it pins |
|---|---|---|
| `GetForgeCascadeCandidatesByEmbedding` | Unit, synthetic in-memory cache | Cosine math; band filter (in/out of `[dMin, dMax]`); top-K cap; topicSynsetID-not-in-cache → empty result |
| `unionCandidates` | Unit, table-driven | All 4 dedup paths; Source tag correctness; cluster-wins-on-conflict invariant |
| `CandidateSource.Valid()` + `CandidateSources.Valid()` | Unit | Each constant returns true; unknown values return false |
| `CascadeConfig.Validate()` | Unit | dMin range, dMax > dMin, topK > 0, CandidateSources.Valid(), default config valid |
| `handleSuggestCascade` — union mode | Integration, real DB | The 4 canary pairs surface as candidates (asserts presence, not final-score rank) |
| `handleSuggestCascade` — `cluster_only` mode | Integration, real DB | Behaves byte-for-byte identically to today's M03 path |
| `handleSuggestCascade` — `embedding_only` mode | Integration, real DB | Cross-domain canary candidates surface; cluster-only candidates absent |
| `NewHandlerWithCascade` — empty `synset_properties_curated` | Unit, synthetic schema | Fails loud at startup (extends existing `TestNewHandlerWithCascade_EmptyCascadeTables_FailsLoud`) |
| Per-request anomaly aggregator | Integration with controlled fixture | Aggregates concreteness misses into single Error log + count attribute; no per-candidate spam |
| `cascade_embedding_query` timing stage | Integration with `observe.Init(true)` | Stage label present on union/embedding paths; absent on cluster-only |
| Topic-without-centroid graceful path | Unit + integration | Embedding path returns nil; Debug log fires; union falls back to cluster-only; embedding_only returns empty 200 |
| Calibration sweep harness | Python eval | Sweep runs; cell results land in JSON; verdict markdown generated as final-slice deliverable |

**Notable testing decisions:**
- No new dependencies — synthetic caches via `map[string][]float32` literals; no third-party mocking framework
- The 4 canary pairs gate CI — cheap (~1s) and deterministic (production DB has all 4 in `synset_centroids`)
- MUNCH non-regression test is the calibration sweep — too expensive for per-commit, runs once per slice close
- `cluster_only` backward-compat test is the critical safety guard — pins that M03 path is unchanged for users who opt out

## Implementation order

Single branch `m04/cosine-candidate-gen`, atomic commits per slice, one review-loop after S03 and before S04.

| # | Slice | Files touched | Effort |
|---|---|---|---|
| **S01** | Embedding candidate generator + struct/enum changes — `GetForgeCascadeCandidatesByEmbedding`, extend `CascadeCandidate` with typed `Source`, add `CandidateSource` enum + `Valid()`, unit tests | `api/internal/db/cascade_embedding.go` (new), `api/internal/db/cascade.go` (struct extension), `api/internal/forge/cascade.go` (enum), tests | ~½ day |
| **S02** | Config + union + handler integration — extend `CascadeConfig` with embedding knobs + `CandidateSources` enum + `Validate()`, env `METAFORGE_FORGE_CANDIDATES`, `unionCandidates`, dispatch in `handleSuggestCascade`, `cascade_embedding_query` timing stage, 4-pair canary test, backward-compat test | `api/internal/forge/cascade.go`, `api/internal/handler/handler.go`, `api/internal/handler/cascade_union.go` (new), `api/cmd/metaforge/main.go`, tests | ~1 day |
| **S03** | Cascade-anomaly aggregator + runtime tripwire — `cascadeAnomalies` struct, replace per-candidate Error logs with counters, runtime row-count tripwire on `synset_properties_curated`, integration tests | `api/internal/handler/handler.go`, tests | ~½ day |
| **`/code-review-loop`** | Gates the code into sweep-ready state | — | ~½-1 day |
| **S04** | Calibration sweep + verdict — `data-pipeline/sweeps/m04_embedding_band.yaml`, run against production DB, output JSON + verdict markdown, default-flip decision lands as final commit if warranted | `data-pipeline/sweeps/m04_embedding_band.yaml` (new), `data-pipeline/sweeps/m04_embedding_band_verdict.md` (new), possible `CascadeConfig` default tweak | ~½-1 day |
| **Merge to main** | Single PR with code + verdict bundled | — | — |

**Total estimate: 2.5-3 days engineering + sweep + review.** Matches the roadmap's original 2-3 day estimate even with the aggregator slice folded in.

**Atomic-commit hygiene reminder (per R1-D6 + R4-D2 lessons):** each finding in S01-S03 lands as its own commit. The S03 runtime tripwire is conceptually distinct from the anomaly aggregator — separate commits in the same slice. The plan should be explicit about which atoms belong together.

## Out of scope (explicit)

- Multi-sense ANN candidate generation (deferred to M04 v2 — see PIPELINE backlog)
- A co-generation scoring bonus β·1{both} (post-sweep decision — separate v2 commit if calibration evidence supports it)
- Novelty-aptness measurement (M06)
- Type-aligned scoring (M05)
- ANN library selection / index build (deferred — brute-force is fast enough for v1; revisit when Bridge needs it)
- A dedicated classical-metaphor eval cohort (would reify clichés as targets; avoided by design)

## Open questions for plan-writing

- Whether the S03 runtime tripwire on `synset_properties_curated` warrants its own ~5-line commit separate from the aggregator. My instinct says yes — they're conceptually distinct fixes in the same slice. Plan should be explicit.
- Whether the YAML sweep grid should be `3×3 = 9 cells` or wider on initial run. Erring narrow keeps S04 cheap; if the verdict markdown surfaces a "sweep didn't cover the interesting band" issue, a follow-up sweep slice is cheap to add.

## References

- Roadmap: [`docs/roadmap/M04-cosine-candidate-gen-roadmap.md`](../../roadmap/M04-cosine-candidate-gen-roadmap.md)
- Pipeline: [`docs/roadmap/PIPELINE.md`](../../roadmap/PIPELINE.md) — M04 entry under `## Next`
- Prior review log (D-references): [`docs/superpowers/review-logs/2026-05-22-m03-pre-m04-deferrals-review.md`](../review-logs/2026-05-22-m03-pre-m04-deferrals-review.md)
- M03-S05 plan (cascade integration): [`docs/plans/2026-05-21-m03-s05-forge-integration.md`](../../plans/2026-05-21-m03-s05-forge-integration.md)
