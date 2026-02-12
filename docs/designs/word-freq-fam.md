# Word Frequency & Familiarity Design

**Status:** Design Complete — not yet implemented
**Priority:** High (unblocks rarity badges, HUD filter, Forge quality signals)
**Dependencies:** Core Thesaurus (data layer complete), Pipeline (restore script working)

---

## Overview

Word frequency and familiarity enrichment adds a "how well-known is this word?" signal to every lemma in the lexicon. This powers rarity badges in the UI, density-control filters on the 3D graph, ranking tiebreakers in search results, and recognisability signals in Metaphor Forge.

The design uses a **two-signal approach**: GPT-derived familiarity as the primary signal for rarity classification, and corpus frequency (Zipf) as a secondary signal for ranking and future gravity systems.

---

## Data Sources

### 1. Brysbaert GPT Familiarity (Primary — rarity classification)

**Paper:** Brysbaert, M., Martnez, G., & Reviriego, P. (2025). "Moving beyond word frequency based on tally counting: AI-generated familiarity estimates of words and phrases are an interesting additional index of language knowledge." *Behavior Research Methods*, 57:28.

- PubMed: https://pubmed.ncbi.nlm.nih.gov/39733132/
- OSF data: https://osf.io/c2yef/
- PDF: `data-pipeline/input/multilex-en/AI-based estimates of word familiarity final.pdf`

**Why familiarity over frequency:**
- GPT familiarity outperforms corpus frequency (SUBTLEX, Multilex) at predicting whether people know a word — ~20% more variance explained in accuracy tasks
- Captures "do people know this word?" which is exactly what common/unusual/rare should mean
- The 3.5 threshold is empirically validated — words below 3.5 are unlikely to be known by 90% of people
- Less correlated with word length than frequency, so it's a more independent signal

**Files at `data-pipeline/input/multilex-en/`:**

| File | Rows | Key Columns | Notes |
|------|------|-------------|-------|
| `Full list GPT4 estimates familiarity and Multilex frequencies.xlsx` | 417,118 | Word, GPT_Fam_dominant (int 1-7), GPT_Fam_probs (float ~0.95-7.0), Multilex (Zipf), Type, Subtype_MWE | **Use this.** Has all familiarity tiers including rare words. Multilex Zipf NULL for 59.5% of rows. |
| `Cleaned list GPT4 estimates familiarity and Multilex frequencies.xlsx` | 146,892 | Same schema | Subset: familiarity >3.5 only. Missing rare words. |
| `Multilex English.xlsx` | 613,803 | Word, Multilex (Zipf), Length, MS_spellcheck | Full frequency data, no familiarity scores. |

**Data quality notes:**
- 2 null Word entries, 17 duplicate words — trivial cleanup
- `GPT_Fam_probs` (continuous float) is the gold column — finer-grained than integer `GPT_Fam_dominant`
- 112K multi-word expressions in dataset — skip for now, gold for future collocations
- Type column: `W` (single word, 63%), `MWE` (multi-word, 27%), `WhW` (wh-phrase, 10%)

### 2. SUBTLEX-UK (Secondary — frequency/Zipf for ranking)

**Files at `data-pipeline/input/subtlex-uk/`:**

| File | Rows | Key Columns | Notes |
|------|------|-------------|-------|
| `SUBTLEX-UK.xlsx` | 160,024 | Spelling, FreqCount, LogFreq(Zipf) 1.17-7.67, CD (contextual diversity 0-0.98), DomPoS | Word-form level |
| `SUBTLEX-UK-flemmas.xlsx` | 290,434 | flemma, lemmafreqs_combined, Zipf 0.7-7.67, flemmafreqband | Lemma-level — **preferred for our use** |

---

## Coverage Analysis

Against our 127,311 distinct lemmas:

| Dataset | Overlap | % of Our Lemmas |
|---------|---------|-----------------|
| **Full GPT4 familiarity** | **88,414** | **69.4%** |
| Cleaned GPT4 familiarity | 49,385 | 38.8% |
| Multilex English | 52,074 | 40.9% |
| **Any dataset** | **~90,266** | **~70.9%** |

**The 30% gap** (38,897 lemmas) is dominated by:
- Hyphenated compounds (`self-aware`, `old-fashioned`)
- Numeric lemmas (`1000`, `10000`)
- Spelling variants (`calibre`/`caliber`)
- Obscure WordNet edge cases

---

## Design Decisions

### Three Rarity Tiers

| Tier | GPT_Fam_probs Range | Intuition | Examples |
|------|---------------------|-----------|----------|
| **Common** | >= 5.5 | Everyday vocabulary | happy, walk, money |
| **Unusual** | 3.5 - 5.5 | Recognised but not everyday | melancholy, sanguine |
| **Rare** | < 3.5 | Most people wouldn't know it | defenestration, petrichor |

Supersedes the PRD's original 4-tier system (common/uncommon/rare/archaic). Three tiers are cleaner and map directly to empirically validated thresholds from the Brysbaert paper.

### Two-Signal Approach

| Signal | Source | Used For |
|--------|--------|----------|
| **GPT familiarity** (`GPT_Fam_probs`) | Brysbaert full list | Rarity badges, HUD filter toggles, Forge quality display |
| **Corpus Zipf** | SUBTLEX-UK flemmas (preferred) > Multilex > NULL | Result ranking tiebreaker, autocomplete weighting, future gravity system |

### Fallback Strategy for Unmatched Words

| Category | Count | Strategy |
|----------|-------|----------|
| Matched in full familiarity list | 88,414 (69.4%) | Use `GPT_Fam_probs` directly |
| Unmatched but in SUBTLEX-UK | Variable | Derive rarity from Zipf: common >= 4.5, rare < 2.5, else unusual |
| Unmatched everywhere | ~37,000 (29.1%) | `NULL` familiarity, default rarity = `'unusual'` |

Defaulting to "unusual" is the safe middle ground — unmatched words are neither flagged as common nor hidden as rare. On-the-fly GPT generation is deferred (complexity, latency, cost not justified for MVP).

---

## Schema

### Current (empty, unused)

```sql
CREATE TABLE frequencies (
    lemma TEXT PRIMARY KEY,
    frequency INTEGER NOT NULL,
    zipf REAL NOT NULL,
    rarity TEXT NOT NULL CHECK (rarity IN ('common', 'uncommon', 'rare', 'archaic'))
);
```

### Proposed

```sql
CREATE TABLE frequencies (
    lemma TEXT PRIMARY KEY,
    familiarity REAL,                -- GPT_Fam_probs (0.95-7.0), NULL if unmatched
    familiarity_dominant INTEGER,    -- GPT_Fam_dominant (1-7), NULL if unmatched
    zipf REAL,                       -- best available: SUBTLEX-UK > Multilex > NULL
    frequency INTEGER,               -- raw count from SUBTLEX-UK, NULL if unavailable
    rarity TEXT NOT NULL DEFAULT 'unusual'
        CHECK (rarity IN ('common', 'unusual', 'rare')),
    source TEXT                      -- provenance: 'brysbaert', 'subtlex', 'derived'
);

CREATE INDEX idx_frequencies_lemma ON frequencies(lemma);
CREATE INDEX idx_frequencies_zipf ON frequencies(zipf);
CREATE INDEX idx_frequencies_rarity ON frequencies(rarity);
CREATE INDEX idx_frequencies_familiarity ON frequencies(familiarity);
```

**Key changes from current:**
- `familiarity` + `familiarity_dominant` added as primary signal
- `rarity` updated from 4-tier to 3-tier with `DEFAULT 'unusual'`
- All numeric columns NULLable — honest about gaps
- `source` column for provenance tracking
- Index on `familiarity` for range queries

### Rarity Computation at Import Time

```
if familiarity is not NULL:
    if familiarity >= 5.5: rarity = 'common'
    elif familiarity >= 3.5: rarity = 'unusual'
    else: rarity = 'rare'
elif zipf is not NULL:
    if zipf >= 4.5: rarity = 'common'
    elif zipf >= 2.5: rarity = 'unusual'
    else: rarity = 'rare'
else:
    rarity = 'unusual'  (default)
```

Thresholds are defined as constants in the import script for easy tuning.

---

## Matching Strategy

Our lemmas are lowercase WordNet entries. The familiarity dataset has mixed case, spaces, apostrophes.

1. **Exact match** (case-insensitive) — catches 69.4%
2. **Strip hyphens, retry** — e.g. `self-aware` -> `self aware`
3. **No inflection matching** — familiarity is form-specific; `run` and `running` should not cross-match
4. **Skip MWEs** — our DB is single-lemma; the 112K multi-word expressions are deferred for future collocations

---

## API Changes

### Response Shape

The existing `RelatedWord` and lookup response gain a `rarity` field:

```json
{
  "word": "melancholy",
  "senses": [{
    "definition": "a feeling of thoughtful sadness",
    "pos": "noun",
    "synonyms": [
      { "word": "sadness", "synset_id": 12345, "rarity": "common" },
      { "word": "wistfulness", "synset_id": 12346, "rarity": "unusual" }
    ]
  }],
  "rarity": "unusual"
}
```

### Go Implementation

- `db.go`: JOIN `frequencies` table in `GetLookup()` query, populate `Rarity` field
- `handler.go`: `Rarity` already in the response struct (placeholder wired up)
- No new endpoints needed — rarity piggybacks on existing lookup

---

## Frontend Changes

### Rarity Badges (Results Panel)

- Rendered alongside POS badges in `mf-results-panel`
- Colour-coded pills: common (muted), unusual (amber), rare (purple)
- Applied to both the looked-up word and each related word in the sense groups

### HUD Filter Toggles

- Three independent toggle checkboxes: **Common** / **Unusual** / **Rare**
- Placement: inside results panel header, below search bar
- Default state: all ON (show everything; user opts out)
- Visual: pill toggles with the tier's colour
- Behaviour: filtered nodes **fade out** (opacity 0) but remain in force layout — removing nodes would cause jarring re-layout
- Words with `NULL` familiarity use "unusual" styling and are controlled by the Unusual toggle

### Forge Quality Signals

- **MVP: display only** — show rarity badge on each Forge suggestion
- **Post-MVP (deferred):** optional "Prefer familiar words" toggle/slider that adds familiarity weight to Forge scoring

---

## Ranking & Sorting

### Thesaurus Results (meaning-driven)

Semantic similarity remains the primary sort. Familiarity is a **tiebreaker only**:

```
ORDER BY semantic_similarity DESC, familiarity DESC NULLS LAST
```

### Autocomplete / Search Suggestions (speed-driven)

Frequency-weighted so common words surface first:

```
ORDER BY prefix_match, zipf DESC NULLS LAST, familiarity DESC NULLS LAST
```

---

## References

- Brysbaert et al. (2025) — [PubMed](https://pubmed.ncbi.nlm.nih.gov/39733132/) | [OSF](https://osf.io/c2yef/)
- SUBTLEX-UK: van Heuven et al. (2014)
- PR review flagging the gap: `reports/pr-review-pipeline.md` issue I6
- Core thesaurus design: `docs/designs/core-thesaurus.md:55` (rarity badge reference)
- PRD rarity references: `Metaforge-PRD-2.md` lines 217, 325, 350, 588-596
- Brainstorm state dump: `docs/plans/2026-02-12-frequency-familiarity-brainstorm.md`
