# Cross-Domain Metaphor Scoring

**Date:** 2026-02-22
**Branch:** `feat--cross-domain-metaphors`
**Evaluation set:** 271 metaphor pairs (metaphor_pairs_v2.json)
**Enrichment:** ~12k synsets

## Summary

Cross-domain metaphors (e.g. "bureaucracy is a web", "anger is fire") are more interesting than same-domain matches (e.g. "anger is fury") because they bridge conceptual categories. This feature adds a **composite scoring** mechanism that boosts candidates from distant semantic domains while preserving overlap-based ranking.

**Chosen configuration:** Alpha=1.0, Beta=0.5
**MRR improvement:** 0.0337 → 0.0347 (+3.0%)

## Problem

The Forge ranks candidates by property overlap count (shared curated vocabulary entries). This works well for finding related concepts but doesn't distinguish between same-domain synonyms and cross-domain metaphors. A word with 6 shared properties from the same domain always outranks one with 4 shared properties from a distant domain — even if the distant match is more metaphorically interesting.

## Approach

### Domain Distance

FastText cosine distance between source and candidate lemma embeddings serves as a proxy for conceptual distance. Lemmas in the same domain cluster together in embedding space; cross-domain pairs have higher distance.

**Data:** 56,181 lemma embeddings stored in `lemma_embeddings` table (FastText wiki-news-300d).

### Composite Score Formula

```
score = overlap^Beta × (1 + Alpha × domainDistance)
```

- **overlap^Beta** — compresses the overlap scale. With Beta < 1, the gap between overlap counts narrows, giving the distance bonus more room to reorder.
- **(1 + Alpha × domainDistance)** — multiplicative bonus for cross-domain candidates. Distance ranges from 0 (identical) to ~1.0 (orthogonal).

Ranking is still **tier-first** (Legendary > Complex > Ironic > Strong > Unlikely), then by composite score within each tier.

## Experiments

### Configuration Grid

| Config | Alpha | Beta | MRR | vs Baseline | Notes |
|--------|-------|------|-----|-------------|-------|
| Baseline (no distance) | — | — | 0.0337 | — | Overlap count only |
| Linear + moderate boost | 1.0 | 1.0 | 0.0343 | +1.8% | Distance only reranks within same overlap |
| Heavy boost | 10.0 | 1.0 | 0.0346 | +2.7% | anger→fire drops rank 1→49 |
| **Sqrt compression** | **1.0** | **0.5** | **0.0347** | **+3.0%** | Clean improvement, no regressions |
| Heavy compression | 1.0 | 0.3 | 0.0322 | -4.4% | Overlap signal too flattened |

### Key Findings

1. **Linear overlap (Beta=1.0) limits distance influence.** With linear overlap, a candidate needs the same or higher overlap count to benefit from the distance bonus. The bonus can only reorder within the same overlap tier — it can never promote a 4-overlap cross-domain word over a 6-overlap same-domain word.

2. **Sqrt compression (Beta=0.5) is the sweet spot.** The gap between overlap 3→4 shrinks from 33% (linear) to 15% (sqrt), letting moderate distance bonuses cross overlap boundaries. This gives a clean +3.0% MRR improvement with no regressions on strong pairs.

3. **Too much compression (Beta=0.3) degrades quality.** At Beta=0.3 the overlap signal is too flattened and domain distance noise can overpower genuine property matches. `anger→fire` drops from rank 1 to 2; `chaos→storm` drops from 7 to 22.

4. **High Alpha without compression is counterproductive.** Alpha=10 with linear overlap gives a misleading +2.7% MRR on aggregate but harms well-known metaphors (anger→fire rank 1→49) because it over-rewards distant but irrelevant matches.

### Pair-Level Analysis (Beta=0.5 vs Baseline)

Top-ranked pairs preserved:

| Pair | Rank |
|------|------|
| anger → fire | 1 |
| fear → shadow | 1 |
| breath → wind | 1 |
| shame → stain | 1 |
| resurrection → dawn | 1 |

Cross-domain pairs benefiting from distance bonus:

| Pair | Overlap | Distance Effect |
|------|---------|-----------------|
| creativity → forge | rank 5 | Cross-domain boost |
| clarity → crystal | rank 8 | Cross-domain boost |
| abstraction → cloud | rank 8 | Cross-domain boost |
| rhetoric → weapon | rank 27 | Cross-domain boost |

## Implementation

### Go API Changes

- `forge.go`: Added `Beta=0.5` constant, `CompositeScore()` uses `math.Pow(overlap, Beta) × (1 + Alpha × distance)`
- `db.go`: Added `GetLemmaEmbedding()` and `GetLemmaEmbeddingsBatch()` for FastText lookups
- `handler.go`: Wired domain distance computation into the forge handler — computes cosine distance per candidate, populates `DomainDistance` and `CompositeScore` fields

### Data Pipeline Changes

- `enrich_pipeline.py`: Added `store_lemma_embeddings()` — populates `lemma_embeddings` table from FastText vectors for all lemmas in the database (56,181 entries)

### Schema Addition

```sql
CREATE TABLE IF NOT EXISTS lemma_embeddings (
    lemma TEXT PRIMARY KEY,
    embedding BLOB NOT NULL  -- 300 × float32 = 1200 bytes
);
```

## Future Work

- **More enrichment data.** With only ~12k enriched synsets, overlap counts are naturally compressed (most pairs share 2-6 properties). The Beta compression will have more impact at 20k+ enrichments where overlap distributions widen.
- **Per-POS Beta tuning.** Nouns and verbs may benefit from different compression rates.
- **MRR by category.** Breaking down MRR by metaphor category (emotion, time, body, politics, etc.) would reveal which domains benefit most from cross-domain scoring.
