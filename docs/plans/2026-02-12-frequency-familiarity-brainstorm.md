# Frequency & Familiarity Brainstorm — State Dump

**Date:** 2026-02-12
**Status:** Brainstorm in progress (following superpowers:brainstorming skill)
**Next step:** Continue design exploration, then write up final design doc

---

## Context

We're designing a word frequency/familiarity system for Metaforge to support:
1. **Rarity badges** on words in the UI (common / unusual / rare)
2. **Ranking/sorting** thesaurus results by how well-known words are
3. **HUD filter toggles** — three independent checkboxes to show/hide common, unusual, rare nodes on the 3D graph (density control for busy graphs)
4. **Forge quality signals** — helping Metaphor Forge prefer/avoid words based on reader recognisability
5. **Search & autocomplete** — frequency-weighted suggestions
6. **3D graph layout** — node size, colour, or gravity influenced by frequency (gravity system is parked for Phase 4+ per PRD)

---

## Data Sources

### 1. Brysbaert GPT Familiarity (Primary signal for rarity)

**Paper:** Brysbaert, M., Martínez, G., & Reviriego, P. (2025). "Moving beyond word frequency based on tally counting: AI-generated familiarity estimates of words and phrases are an interesting additional index of language knowledge." *Behavior Research Methods*, 57:28.
- PubMed: https://pubmed.ncbi.nlm.nih.gov/39733132/
- OSF data: https://osf.io/c2yef/
- PDF saved locally: `data-pipeline/input/multilex-en/AI-based estimates of word familiarity final.pdf`

**Key findings relevant to us:**
- GPT familiarity outperforms corpus frequency (SUBTLEX, Multilex) at predicting whether people know a word — ~20% more variance explained in accuracy tasks
- Familiarity captures "do people know this word?" which is exactly what common/unusual/rare should mean
- The 3.5 threshold is empirically validated — words below 3.5 are unlikely to be known by 90% of people
- Familiarity is less correlated with word length than frequency, so it's a more independent signal
- Works for multi-word expressions too (relevant for future collocations)

**Files downloaded to `data-pipeline/input/multilex-en/`:**

| File | Rows | Key Columns | Notes |
|------|------|-------------|-------|
| `Cleaned list GPT4 estimates familiarity and Multilex frequencies.xlsx` | 146,892 | Word, GPT_Fam_dominant (int 1-7), GPT_Fam_probs (float 3.5-7.0), Multilex_Zipf, Type, Subtype_MWE | Cleaned subset (familiarity >3.5 only). Missing rare words like defenestration, petrichor, obfuscate |
| `Multilex English.xlsx` | 613,803 | Word, Multilex (Zipf), Length, MS_spellcheck | Full frequency data. Has all words including rare ones. No familiarity scores. |
| **PENDING UPLOAD: Full 417K familiarity list** | ~417,118 | Expected: Word, GPT_Fam_dominant, GPT_Fam_probs, Multilex_Zipf | Needed for rare words (familiarity <3.5). User uploading from OSF. |

### 2. SUBTLEX-UK (Secondary signal for ranking/gravity)

**Files at `data-pipeline/input/subtlex-uk/`:**

| File | Rows | Key Columns | Notes |
|------|------|-------------|-------|
| `SUBTLEX-UK.xlsx` | 160,024 | Spelling, FreqCount, LogFreq(Zipf) (1.17-7.67), CD (contextual diversity 0-0.98), DomPoS, + 22 more | Word-form level, rich metadata |
| `SUBTLEX-UK-flemmas.xlsx` | 290,434 | flemma, lemmafreqs_combined, flemmafreqband (1-291), FPMW, Zipf (0.7-7.67) | Lemma-level, cleaner for our use |

---

## Design Decisions (Settled)

### Three rarity tiers
- **common / unusual / rare** (not the PRD's original common/uncommon/rare/archaic)
- Schema `rarity` CHECK constraint will need updating from `('common', 'uncommon', 'rare', 'archaic')` to `('common', 'unusual', 'rare')`
- Future gamification tiers (legendary etc.) are possible but deferred

### Two-signal approach
- **GPT familiarity** → rarity badges, HUD filter toggles, Forge quality signals
- **Multilex Zipf / SUBTLEX-UK** → result ranking tiebreaker, future gravity system, autocomplete weighting

### Default thresholds (tuneable)
| Tier | GPT Familiarity Range | Intuition |
|------|----------------------|-----------|
| **Common** | ≥ 5.5 | Everyday vocabulary — "happy", "walk", "money" |
| **Unusual** | 3.5 – 5.5 | Recognised but not everyday — "melancholy", "sanguine" |
| **Rare** | < 3.5 | Most people wouldn't know it — "defenestration", "petrichor" |

This puts ~67% of the cleaned dataset into "common" (the 6-7 range holds ~47% of entries, 5-6 holds ~30%).

### HUD filter
- Three independent toggle checkboxes: Common, Unusual, Rare
- Controls visibility of nodes on the 3D force graph
- Primary use case: thinning busy graphs (a word like "good" has 30+ synonyms)

---

## Design Decisions (Still To Explore)

1. **HUD filter UX details** — toggle placement, default state (all on?), visual feedback
2. **Forge quality signals** — how familiarity influences metaphor suggestions (e.g. prefer recognisable words, or flag when a suggestion is obscure)
3. **Ranking algorithm** — how familiarity and Zipf combine for result ordering. Semantic similarity is primary for MVP (per core-thesaurus design), frequency/familiarity as tiebreaker or secondary sort
4. **Pipeline integration** — schema update to `frequencies` table, Python import script, matching strategy (lemma vs word-form)
5. **Fallback strategy** — what happens for words not in any dataset? (Could generate familiarity on-the-fly with the paper's GPT prompt, or leave as NULL)
6. **Coverage gap** — the cleaned list (147K) misses rare words. The full list (417K, pending upload) should cover most of our lexicon. Need to check overlap with our WordNet-derived vocabulary.

---

## Existing Codebase State

| Component | Status | What exists | What needs changing |
|-----------|--------|-------------|-------------------|
| **Schema** | Defined but empty | `frequencies(lemma, frequency, zipf, rarity)` in `docs/designs/schema-v2.sql` | Add `familiarity REAL`, update rarity CHECK to `('common', 'unusual', 'rare')`, thresholds as config |
| **SQL dump** | Empty table | `data-pipeline/output/lexicon_v2.sql` has `CREATE TABLE frequencies` but 0 rows | Pipeline step to populate |
| **Go API** | Stub | `api/internal/db/db.go:27` has `Rarity string` placeholder field | Wire up JOIN to frequencies table |
| **Frontend** | POS badges only | `web/src/components/mf-results-panel.ts` renders `.pos-badge` | Add rarity badge rendering + HUD filter toggles |
| **Pipeline runner** | Gap noted | `data-pipeline/run_pipeline.sh:101` has comment "SUBTLEX-UK frequency import is pending" | New import step |
| **PRD** | Calls for it | `Metaforge-PRD-2.md` lines 216-220, 325, 350 reference rarity badges + SUBTLEX-UK | Update to reflect familiarity approach |

---

## Sample Data Points

| Word | GPT_Fam_probs | Multilex_Zipf | SUBTLEX-UK Zipf | Rarity Tier |
|------|--------------|---------------|-----------------|-------------|
| the | 7.00 | 7.57 | 7.67 | common |
| happy | 7.00 | 5.55 | 5.56 | common |
| melancholy | 5.84 | 3.43 | 3.43* | unusual |
| tummy | 6.24 | 3.67 | — | common |
| defenestration | — (need full list) | 1.58 | 1.17 | rare |
| petrichor | — (need full list) | 0.85 | — | rare |
| obfuscate | — (need full list) | 2.02 | 1.17 | rare |

---

## References

- Brysbaert et al. (2025) — [PubMed](https://pubmed.ncbi.nlm.nih.gov/39733132/) | [OSF](https://osf.io/c2yef/) | [ResearchGate preprint](https://www.researchgate.net/publication/385939692)
- German companion: [Journal of Cognition](https://journalofcognition.org/articles/10.5334/joc.482)
- SUBTLEX-UK: van Heuven et al. (2014)
- PR review flagging the gap: `reports/pr-review-pipeline.md` issue I6
- Core thesaurus design drift check: `docs/designs/core-thesaurus.md:126`
