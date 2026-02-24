# P2: Concreteness Gate — Design

**Date:** 2026-02-25
**Branch:** `feat/steal-shamelessly`
**Cascade position:** Between candidate retrieval (property overlap) and salience ranking (Ortony)

---

## Goal

Hard filter that discards metaphor candidates where the target is more concrete than the vehicle. Cheap gate that prunes bad candidates early in the cascade — prevents inversions like suggesting "anger" as a vehicle for "fire".

```
Retrieve candidates (property overlap)
  → Gate: concreteness(vehicle) >= concreteness(target)   ← THIS
    → Rank: Ortony salience score
      → Re-rank top N: affective alignment, SPV, novelty
```

---

## Data Source

**Brysbaert et al. (2014)** — 37,058 English lemmas rated 1-5 on a concreteness scale by ~4,000 human judges via crowdsourcing.

- Paper: Brysbaert, Warriner & Kuperman (2014), *Behav Res* 46, 904-911
- Dataset: https://github.com/ArtsEngine/concreteness
- Scale: 1.0 (most abstract) to 5.0 (most concrete)

**Gap-filling:** FastText regression for lemmas not in Brysbaert (if coverage gaps prove significant after initial import).

---

## Data Pipeline

### New table

```sql
CREATE TABLE synset_concreteness (
    synset_id TEXT PRIMARY KEY,
    score REAL NOT NULL,          -- 1.0 (abstract) to 5.0 (concrete)
    source TEXT NOT NULL,         -- 'brysbaert' or 'fasttext_regression'
    FOREIGN KEY (synset_id) REFERENCES synsets(synset_id)
);
```

### Population

1. Download Brysbaert data file
2. For each synset, collect all its lemmas, look up each in Brysbaert
3. Take the **mean** of available lemma scores as the synset score (`source = 'brysbaert'`)
4. Synsets where zero lemmas have Brysbaert coverage remain unscored (no row)
5. FastText regression fills gaps in a later pass if needed (`source = 'fasttext_regression'`)

### Storage level decision

Scores stored at **synset level**, aggregated from lemma ratings. Brysbaert rates word forms without sense disambiguation — a lemma like "rock" gets one score regardless of whether the rater was thinking of the stone or the music genre. Aggregating via mean smooths polysemy noise. Accepted trade-off: the gate is a coarse filter, not a precision instrument. Dominant sense is usually the most concrete (grounding bias), and false positives (letting bad candidates through) are cheaper than false negatives (killing good metaphors). The salience ranker downstream handles precision.

### New script

`data-pipeline/scripts/import_concreteness.py` — parses Brysbaert data, joins against `lemmas` table, computes mean per synset, writes to `synset_concreteness`.

---

## SQL Gate

### Implementation

Gate added to both `GetForgeMatchesCurated` and `GetForgeMatchesCuratedByLemma` queries. Joins `synset_concreteness` twice — once for the source synset, once for each candidate — and filters:

```sql
WHERE candidate_concreteness >= source_concreteness
```

For `GetForgeMatchesCuratedByLemma` (polysemous sources), the gate compares the candidate against whichever source sense it was matched to (consistent with existing sense-alignment logic).

### Edge cases

- **Missing scores** (either side has no `synset_concreteness` row): pass through. No data = no opinion. Implemented via `LEFT JOIN` + `COALESCE` or `WHERE` null-check.
- **Equal concreteness**: allowed through. Gate is `>=`, not `>`.

---

## API Surface

No changes. The gate is invisible to the frontend — same endpoint, same response shape, same `CuratedMatch` struct. Fewer bad candidates in results.

---

## Testing

### Python pipeline

- Parsing Brysbaert data format
- Mean aggregation across lemmas per synset
- Handling synsets with no Brysbaert coverage (no row written)
- Round-trip integration: import sample data, verify scores in DB

### Go

- Candidate more concrete than source → kept
- Candidate less concrete than source → filtered
- Equal concreteness → kept
- Missing score on either side → kept (pass-through)
- `GetForgeMatchesCuratedByLemma`: gate uses matched source sense's concreteness
- Existing tests unaffected (no `synset_concreteness` rows = pass-through)

### MRR evaluation

Re-run MRR eval after gate is live against the 274-pair gold set. Expectation: flat or slight improvement (removing bad candidates, not reordering good ones). MRR drop = false negatives = gate too aggressive.

---

## Future Considerations

- **POS filtering:** Brysbaert rates word forms without sense disambiguation. Adding POS matching (only apply rating to synsets sharing the rated word's POS) would reduce noise. Not needed for v1 coarse gate but worth revisiting if false negatives are too high.
- **Gate filtering telemetry:** Logging how often specific candidates get filtered in real-world usage could surface patterns useful for tuning the gate threshold or informing downstream scoring decisions. Shape TBD.
- **Threshold tuning:** The gate currently uses strict `>=`. A soft margin (e.g. filter only when target exceeds vehicle by > 0.5) could reduce false negatives at the cost of letting more marginal candidates through.
