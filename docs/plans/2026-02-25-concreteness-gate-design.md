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
3. Take the **max** of available lemma scores as the synset score (`source = 'brysbaert'`)
4. Synsets where zero lemmas have Brysbaert coverage remain unscored (no row)
5. FastText regression fills gaps in a later pass if needed (`source = 'fasttext_regression'`)

### Storage level decision

Scores stored at **synset level**, aggregated from lemma ratings via **max** (not mean). Brysbaert rates word forms without sense disambiguation — a lemma like "rock" gets one score regardless of whether the rater was thinking of the stone or the music genre. Max aggregation was chosen because metaphors rely on the most tangible sense of a word — mean penalises concrete vehicles that have secondary abstract lemmas. Accepted trade-off: the gate is a coarse filter, not a precision instrument. Dominant sense is usually the most concrete (grounding bias), and false positives (letting bad candidates through) are cheaper than false negatives (killing good metaphors). The salience ranker downstream handles precision.

### New script

`data-pipeline/scripts/import_concreteness.py` — parses Brysbaert data, joins against `lemmas` table, computes mean per synset, writes to `synset_concreteness`.

---

## SQL Gate

### Implementation

Gate added to both `GetForgeMatchesCurated` and `GetForgeMatchesCuratedByLemma` queries. Joins `synset_concreteness` twice — once for the source synset, once for each candidate — and filters with a **soft margin of +0.5** and a **POS gate (noun-noun only)**:

```sql
WHERE (
    source_pos != 'n'                           -- POS bypass: source not noun
    OR candidate_pos != 'n'                     -- POS bypass: candidate not noun
    OR candidate_concreteness IS NULL           -- missing score: pass through
    OR source_concreteness IS NULL              -- missing score: pass through
    OR candidate_concreteness + 0.5 >= source_concreteness  -- soft margin
)
```

The margin constant (`ConcretenessMargin = 0.5`) is defined in `db.go` and interpolated into SQL via `fmt.Sprintf`.

For `GetForgeMatchesCuratedByLemma` (polysemous sources), the gate compares the candidate against whichever source sense it was matched to (consistent with existing sense-alignment logic).

### POS gate rationale

Concreteness norms are most reliable for nouns. Applying the gate to verbs/adjectives where semantic boundaries are fluid would create false negatives. The gate only fires when **both** source and candidate are nouns. Non-noun POS on either side bypasses the gate entirely.

### Edge cases

- **Missing scores** (either side has no `synset_concreteness` row): pass through. No data = no opinion. Implemented via `LEFT JOIN` + `WHERE` null-check.
- **Equal concreteness**: allowed through. Gate is `+ 0.5 >=`, so equal and near-equal pass.
- **Soft margin**: candidates within 0.5 of the source pass through. This allows horizontal metaphors between concepts at similar concreteness while still catching severe inversions (e.g. "anger" as vehicle for "fire").

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

## Telemetry

### Startup coverage

`GetConcretenessStats(db)` counts scored synsets vs total synsets. Called at startup via `LogConcretenessStats()`:

```
INFO concreteness coverage scored=52154 total=107519 pct=48.5%
WARN concreteness coverage below 80% pct=48.5%
```

Warns if coverage drops below 80%. Current coverage (48.5%) indicates FastText regression is needed to fill gaps.

### Per-request POS bypass logging

After forge queries return, the handler counts candidates with non-noun POS and logs at `slog.Debug` level:

```
DEBUG forge gate stats word=anger results=42 non_noun_candidates=7
```

Zero overhead in production unless debug logging is enabled.

---

## Results

- **MRR:** 0.0372 (up from 0.0358 baseline, +3.9%)
- **Concreteness coverage:** 52,154 / 107,519 synsets (48.5%)
- **Testable pairs:** 271 / 274

---

## Council Review

Design reviewed by LLM council (`docs/designs/20260225-cascade-scoring-P2-design-council-review.md`). Accepted amendments:

1. **Max aggregation** (not mean) — metaphors rely on the most tangible sense
2. **Soft margin +0.5** — allows horizontal metaphors, catches severe inversions
3. **POS gate (noun-noun only)** — concreteness norms unreliable for verbs/adjectives
4. **Telemetry** — startup coverage + debug-level POS bypass logging

---

## Future Considerations

- **FastText regression:** Coverage at 48.5% — training a regression model to predict concreteness from FastText embeddings would fill the gap for unrated lemmas.
- **Extend POS support:** Per-request telemetry will show how often the gate is bypassed for non-nouns. If the bypass rate is high, consider extending concreteness norms to verbs/adjectives.
- **Margin tuning:** The 0.5 margin is a starting point. Real usage data may suggest tightening or loosening.
