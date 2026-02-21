# Metaforge Design: Curated Property Vocabulary

**Date:** 2026-02-14
**Status:** Design — not yet implemented
**Depends on:** 20K enrichment run (Variant C prompt, 10-15 properties per synset)

---

## ⚠️ DEVELOPMENT STANDARDS (applies to all implementation) ⚠️

- **TDD Red/Green:** Failing test first, then code, then refactor
- **Frequent commits:** Commit after each green test
- **CI/CD:** Automated test runs on all commits
- **Canary releases:** Deploy to subset first, monitor, then full rollout

---

## Problem

The Metaphor Forge currently computes similarity between synsets using cosine distance between FastText embedding centroids. This has two weaknesses:

1. **FastText is sense-blind.** `wiki-news-300d-1M.vec` assigns one vector per surface form. The property "light" gets the same embedding whether it means "not heavy" or "luminous". When synset A has property "light" (luminous) and synset B has property "light" (not heavy), cosine similarity treats them as identical — a false match.

2. **Evolutionary prompt search is expensive.** The A/B/C enrichment experiment showed that prompt design matters, but searching the prompt space with LLM evaluations burns tokens. We need the vocabulary itself to do the disambiguation work, not the prompt.

**Goal:** Boost MRR by at least 50% over baseline (raw cosine centroids) without expensive prompt search.

---

## Proposed Solution: Two-Pass Snap-to-Vocabulary

Replace the current free-form property space with a curated canonical vocabulary. Properties extracted by the LLM are normalised ("snapped") to vocabulary entries at build time. Runtime matching becomes set intersection — no embeddings needed.

### Overview

```
Build time:
  [WordNet synsets] → Pick least-polysemous lemma per synset → Deduplicate → VOCABULARY (~25-30k entries)
  [LLM extraction]  → Free-form properties (10-15 per synset)
  [Snap pipeline]   → Map each free-form property → nearest vocabulary entry (or drop)

Runtime:
  /forge/suggest?word=grief
  → Look up source synset properties (canonical IDs)
  → JOIN against all other synsets on shared canonical property IDs
  → COUNT shared + COUNT contrasts → Tier classification
  → No embeddings, no cosine distance
```

---

## Phase 1: Vocabulary Build

### Step 1: Select top-N synsets

Take the top 35,000 synsets ranked by max lemma familiarity (from SUBTLEX-UK/frequency data). This covers the useful vocabulary range while keeping the vocabulary manageable.

### Step 2: Pick canonical lemma per synset

For each synset, select the **least polysemous** lemma (fewest senses in WordNet). Ties broken by:
1. Prefer adjective/participial forms (matches the POS profile of extracted properties)
2. Prefer shorter surface forms
3. Alphabetical

### Step 3: Deduplicate surface forms

Multiple synsets may select the same surface form as their canonical lemma (e.g. "light" is least-polysemous for both a luminosity and a weight synset). Apply greedy deduplication:
- Sort synsets by familiarity (descending)
- For each synset, if its chosen lemma is already claimed, try the next-least-polysemous lemma
- If no unique lemma available, keep the synset but flag it as "shared form" for later disambiguation

### Step 4: Store vocabulary

```sql
CREATE TABLE property_vocab_curated (
    vocab_id    INTEGER PRIMARY KEY,
    synset_id   TEXT NOT NULL,      -- source WordNet synset
    lemma       TEXT NOT NULL,      -- canonical surface form
    pos         TEXT NOT NULL,      -- a/n/v/r/s
    polysemy    INTEGER NOT NULL,   -- number of senses for this lemma
    UNIQUE(synset_id)
);
CREATE INDEX idx_vocab_lemma ON property_vocab_curated(lemma);
```

### Expected vocabulary size

From the monosemy coverage analysis (`data-pipeline/scripts/analysis/monosemy_coverage.py`):

| Threshold (at 35k synsets) | Coverage |
|----------------------------|----------|
| Strictly monosemous (1 sense) | 34% (11,918) |
| <= 2 senses | 50% (17,581) |
| <= 3 senses | 61% (21,297) |
| <= 5 senses | 74% (25,814) |
| <= 10 senses | 88% (30,741) |

After deduplication, expect ~25-30k usable entries. Most will have <= 5 senses, which is acceptable — a property with 3 senses has at most a 2-in-3 chance of a wrong-sense match, and with 12 properties per synset, that noise is 1 in ~36 property-pairs per comparison.

### POS profile

The vocabulary benefits from a favourable POS alignment. Extracted properties are overwhelmingly adjectives and nouns — the categories with best monosemy coverage:

| POS | % of extracted properties | Monosemy coverage (35k) |
|-----|---------------------------|-------------------------|
| Adjective | 46% | 26-39% |
| Verb (mostly participles) | 36% | 15% |
| Noun | 17% | 42% |
| Adverb | 1% | 47% |

The 36% "verbs" are nearly all VBG/VBN participles functioning as adjectives ("flickering", "absorbing", "abridged"). The vocabulary doesn't need verb synsets — it needs the adjective/participial forms. A morphological normalisation step handles the mapping.

---

## Phase 2: Snap Pipeline (Build Time)

After LLM extraction produces free-form properties for each synset, snap each property to the nearest vocabulary entry. This runs once at build time, not at query time.

### Snap cascade

For each extracted property string:

1. **Exact match** — property string matches a vocabulary lemma verbatim → snap to that vocab entry
2. **Morphological normalisation** — stem/lemmatise the property, then exact match (e.g. "flickering" → "flicker", "absorbing" → "absorbent")
3. **Embedding top-K** — compute cosine similarity against vocabulary entry embeddings, take top-5, accept best match above **0.7 threshold**
4. **Drop** — if no match at >= 0.7, discard the property

### Why 0.7?

- Below 0.6, antonyms start matching (hot↔cold have ~0.65 cosine similarity in FastText). This would create false bridges.
- Above 0.75, only near-exact synonyms match, losing the collapsing benefit.
- 0.7 is the conservative starting point. Tune based on the audit loop (Phase 4).

### Output

```sql
CREATE TABLE synset_properties_curated (
    synset_id   TEXT NOT NULL,
    vocab_id    INTEGER NOT NULL,
    snap_method TEXT NOT NULL,       -- 'exact', 'morphological', 'embedding', for audit
    snap_score  REAL,                -- cosine similarity (null for exact/morphological)
    FOREIGN KEY (vocab_id) REFERENCES property_vocab_curated(vocab_id),
    PRIMARY KEY (synset_id, vocab_id)
);
```

### Expected snap rates

From the pilot data (5,069 unique properties across 2k synsets):
- 51% of properties appear in only 1 synset (long tail — many will be dropped or snapped to common forms)
- 22% appear in 2-5 synsets (moderate reuse)
- 12% appear in 6-20 synsets (core vocabulary)
- 2% appear in >20 synsets (universal properties like "sudden", "internal", "precise")

The snap pipeline will collapse the long tail into canonical forms, reducing the effective vocabulary from ~5k unique strings to a denser, more reliable set. Properties that don't snap to anything are genuinely niche — dropping them loses some signal but removes noise.

---

## Phase 3: Antonym Contrast Detection

### Motivation

Some of the most powerful metaphors are ironic — "subtle as a sledgehammer", "clear as mud". These pairs share few properties directly but have properties that are **antonymous**. The current system ranks them as "Unlikely" (low overlap, low distance). With antonym detection, they can surface as a new "Ironic" tier.

### WordNet attribute relations (type 60)

WordNet links adjectives to shared **attribute nouns**. Adjectives sharing an attribute noun are typically antonyms:

```
attribute noun "weight" → {heavy, light}
attribute noun "temperature" → {hot, cold}
attribute noun "size" → {large, small}
```

From the database:
- **472 antonym pairs** across 267 attribute nouns
- **333 extracted properties (6.6%)** have known antonyms

6.6% sounds small, but these are the highest-value words: hot/cold, light/dark, hard/soft, strong/weak, deep/shallow, fast/slow, heavy/light, loud/soft, dry/wet, tall/short.

### Schema

```sql
CREATE TABLE property_antonyms (
    vocab_id_a  INTEGER NOT NULL,
    vocab_id_b  INTEGER NOT NULL,
    FOREIGN KEY (vocab_id_a) REFERENCES property_vocab_curated(vocab_id),
    FOREIGN KEY (vocab_id_b) REFERENCES property_vocab_curated(vocab_id),
    PRIMARY KEY (vocab_id_a, vocab_id_b)
);
```

Populated by joining the curated vocabulary against WordNet attribute relations. Bidirectional — both (a, b) and (b, a) stored. Expected ~200-300 rows.

### Runtime query

Alongside the normal property intersection query, run a contrast overlap:

```sql
-- Contrast overlap (antonymous properties)
SELECT sp_tgt.synset_id, COUNT(*) as contrast_count
FROM synset_properties_curated sp_src
JOIN property_antonyms pa ON sp_src.vocab_id = pa.vocab_id_a
JOIN synset_properties_curated sp_tgt ON sp_tgt.vocab_id = pa.vocab_id_b
WHERE sp_src.synset_id = :source AND sp_tgt.synset_id != :source
GROUP BY sp_tgt.synset_id
```

### Extended tier classification

| Shared props | Contrast props | Tier |
|-------------|---------------|------|
| High | Low | **Legendary / Strong** (normal metaphor) |
| Low | High | **Ironic** (new — "subtle as a sledgehammer") |
| High | High | **Complex** (simultaneously alike and opposed) |
| Low | Low | Weak / Unlikely |

The "Complex" case is linguistically the most interesting — concepts that are both similar and antonymous. "Life is a prison" shares properties (confining, structured, enduring) plus contrasts (free/captive, chosen/imposed).

---

## Phase 4: Audit Loop

The snap pipeline is a one-shot transformation. To ensure quality:

### Automated validation

1. **Snap rate report:** What % of extracted properties snapped at each stage (exact, morphological, embedding, dropped)?
2. **Coverage report:** After snapping, how many synsets have >= 5 canonical properties? >= 3?
3. **Distribution report:** What's the IDF distribution of canonical vocabulary entries? Are high-IDF entries mostly monosemous?

### Manual spot-check

Sample 50 synsets across tiers. For each:
- Compare original free-form properties vs snapped canonical properties
- Flag any clearly wrong snaps (wrong sense, unrelated concept)
- Measure "would a human have chosen the same canonical form?"

### Threshold tuning

If audit reveals:
- Too many wrong-sense snaps → raise threshold from 0.7 to 0.75
- Too many dropped properties (coverage < 60%) → lower to 0.65 or add morphological rules
- Specific POS categories underperforming → add POS-specific handling

---

## Runtime Impact

### Before (current)

```
/forge/suggest → mega-query with property_similarity matrix (IDF-weighted cosine)
                → fetch pre-computed synset centroids
                → compute cosine distance in Go
                → tier classification
```

Relies on: `property_similarity` table (300d FastText embeddings, 0.5 threshold), `synset_centroids` table, in-memory cosine distance.

### After (curated vocabulary)

```
/forge/suggest → JOIN synset_properties_curated ON shared vocab_id (integer comparison)
                → COUNT shared properties
                → JOIN property_antonyms for contrast count
                → tier classification (shared + contrast dimensions)
```

Relies on: integer JOINs only. No embeddings, no floating-point distance. The `property_similarity` and `synset_centroids` tables can be dropped (or retained as fallback).

### Performance

Set intersection via integer JOINs is orders of magnitude faster than the current approach. The entire forge query becomes a single SQL query with no post-processing in Go.

---

## Implementation Plan

| Step | Script / File | Tests | Depends on |
|------|---------------|-------|------------|
| 1. Vocabulary build | `data-pipeline/scripts/build_vocab.py` | Dedup correctness, POS filtering, size bounds | 20K enrichment complete |
| 2. Snap pipeline | `data-pipeline/scripts/snap_properties.py` | Exact/morph/embedding stages, threshold, drop rate | Step 1 |
| 3. Antonym table | `data-pipeline/scripts/build_antonyms.py` | Attribute relation extraction, bidirectional storage | Step 1 |
| 4. Audit report | `data-pipeline/scripts/analysis/snap_audit.py` | Snap rate, coverage, distribution metrics | Step 2 |
| 5. Go API update | `api/internal/db/db.go`, `forge.go` | New query, tier classification with contrast | Steps 2 + 3 |
| 6. Frontend tier colours | `web/src/graph/colours.ts` | Ironic/Complex tier visual treatment | Step 5 |

Steps 1-4 are pipeline-only (Python). Step 5 is backend. Step 6 is frontend. Can be parallelised after step 2.

---

## Open Questions

- **Multi-word properties:** 8.9% of extracted properties are multi-word ("action-oriented", "Central Asian"). Should these snap to single-word vocabulary entries, or extend the vocabulary to include MWEs?
- **Participial normalisation:** Should "flickering" snap to "flicker" (verb synset) or remain as "flickering" (adjective form)? The vocabulary should contain the adjective/participial form, but the lemmatiser may disagree.
- **Threshold per-POS:** Should the embedding snap threshold vary by POS? Adjectives cluster tighter than nouns in FastText space.
- **Complex tier UX:** How to visually distinguish "Ironic" from "Complex" from "Legendary"? Needs design input.

---

## Supporting Data

- Monosemy coverage analysis: `data-pipeline/scripts/analysis/monosemy_coverage.py`
- POS distribution of properties: 46% adjective, 36% verb (participles), 17% noun, 1% adverb (from 2k pilot)
- Property frequency: 51% hapax (1 synset), 22% 2-5 synsets, 12% 6-20 synsets, 2% >20 synsets
- Top properties: sudden (102), internal (81), precise (66), forceful (63), formal (59), rhythmic (59)
- Antonym pairs: 472 via 267 WordNet attribute nouns; 333 properties (6.6%) have known antonyms
- Enrichment experiment report: `docs/plans/20260209-enrichment-experiment-report.md`

---

## Related Documents

- [metaphor-forge.md](./metaphor-forge.md) — Forge matching algorithm, tier system, prompt design
- [word-freq-fam.md](./word-freq-fam.md) — Rarity tiers, frequency/familiarity data sources
- `Metaforge-PRD-2.md` — Authoritative PRD
