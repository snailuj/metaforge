# BNC (British National Corpus) Dataset Assessment

**Date:** 2026-01-30
**Dataset:** British National Corpus (BNC) frequency data
**Source:** sqlunet_master.db (4 tables, `bnc_*` prefix)

---

## 1. Schema Analysis

### Core Tables & Relationships

```
bnc_bncs (26,980)
├── wordid → words.wordid
├── posid (POS tag: n, v, a, r)
├── freq (raw frequency count)
├── range (distribution across 100 text sections, 0-100)
└── disp (dispersion metric, 0.0-1.0)

bnc_convtasks (496)
├── wordid, posid
├── freq1, range1, disp1 (conversation subcorpus)
├── freq2, range2, disp2 (task-oriented subcorpus)
└── ll (log-likelihood ratio for comparison)

bnc_spwrs (466)
├── wordid, posid
├── freq1, range1, disp1 (spoken subcorpus)
├── freq2, range2, disp2 (written subcorpus)
└── ll (log-likelihood ratio)

bnc_imaginfs (507)
├── wordid, posid
├── freq1, range1, disp1 (imaginative subcorpus)
├── freq2, range2, disp2 (informative subcorpus)
└── ll (log-likelihood ratio)
```

### Part-of-Speech Distribution

| POS | Count | Percentage |
|-----|-------|------------|
| Nouns | 19,116 | 70.9% |
| Verbs | 7,126 | 26.4% |
| Adjectives | 723 | 2.7% |
| Adverbs | 15 | 0.1% |

**Total:** 26,980 entries (22,865 unique words)

---

## 2. Quality Assessment

### Coverage

- **Total Entries:** 26,980 (word-POS pairs)
- **Unique Words:** 22,865
- **Non-Zero Frequency:** 15,916 (59.0%)
- **Zero Frequency:** 11,064 (41.0%) - vocabulary placeholders?

### Frequency Statistics

- **Range:** 0 - 42,277 (verb "be")
- **Mean:** ~14.2
- **Top Words:** be (42k), have (13k), do (5.6k), say (3.3k) - sensible high-frequency items

### Quality Indicators

✅ **Strengths:**
- **British English:** Native UK frequency data (complementary to SUBTLEX-UK)
- **Subcorpus Analysis:** 3 detailed subcorpus comparisons with log-likelihood ratios
  - Spoken vs Written (spwrs)
  - Conversation vs Task-oriented (convtasks)
  - Imaginative vs Informative (imaginfs)
- **Dispersion Metrics:** `range` (0-100 text distribution) and `disp` (0-1 evenness) provide rarity nuance
- **Well-Structured:** Simple, clean schema with minimal joins required

⚠️ **Weaknesses:**
- **Limited Coverage:** 22,865 words vs SUBTLEX-UK (160k) - only 14% coverage
- **Zero-Frequency Entries:** 41% of entries have freq=0 (vocabulary placeholders without corpus data)
- **Noun-Heavy:** 71% nouns, only 3% adjectives - unbalanced POS distribution
- **Unknown Version:** No metadata indicating BNC version (original 100M corpus? BNC2014?)

---

## 3. Metaforge Relevance

### Use Cases

#### 1. Frequency Data (LOW VALUE - REDUNDANT)

**Current State:** sch.v1 uses SUBTLEX-UK (160k words)

**BNC Comparison:**
- SUBTLEX-UK: 160,022 entries (7x more coverage)
- BNC: 22,865 unique words (14% of SUBTLEX coverage)
- Both are British English corpora

**Verdict:** BNC frequency data is **redundant** - SUBTLEX-UK provides far superior coverage.

#### 2. Subcorpus Analysis (LOW-MEDIUM VALUE)

BNC provides 3 subcorpus comparisons with log-likelihood ratios:

1. **Spoken vs Written** (466 words)
   - Could flag "casual" vs "formal" words
   - Example use: Tag words with strong spoken bias (colloquialisms)

2. **Conversation vs Task-oriented** (496 words)
   - Could identify interactive vs instructional vocabulary

3. **Imaginative vs Informative** (507 words)
   - Could flag creative writing vocabulary vs technical/factual

**Potential Use:** Add "register" tags to synsets (spoken, formal, creative, etc.)

**Drawback:** Only ~500 words per comparison (2-3% of vocabulary) - very limited coverage

#### 3. Dispersion Metrics (LOW VALUE)

BNC provides `range` (0-100 text distribution) and `disp` (0-1 evenness):

- **High range + high disp:** Common across all text types (general vocabulary)
- **Low range + low disp:** Specialized/technical vocabulary

**Potential Use:** Identify "general" vs "specialized" words

**Drawback:** SUBTLEX-UK likely has similar dispersion data (not checked yet)

---

## 4. Comparison with SUBTLEX-UK

| Metric | BNC | SUBTLEX-UK |
|--------|-----|------------|
| Coverage | 22,865 words | 160,022 words |
| Relative Size | 14% | 100% (baseline) |
| Corpus Source | Written + spoken text (100M words?) | Film/TV subtitles (201M words) |
| British English | ✅ Yes | ✅ Yes |
| Frequency Data | ✅ Yes | ✅ Yes |
| Dispersion Metrics | ✅ range + disp | ✅ (likely, not confirmed) |
| Subcorpus Analysis | ✅ 3 comparisons | ❌ (single corpus) |
| Zero-Frequency Entries | ⚠️ 41% | ❓ (unknown) |

**Key Insight:** SUBTLEX-UK has **7x more coverage** than BNC.

### Why is BNC coverage so limited?

**Hypothesis:** This BNC data in sqlunet may be a **subset** (e.g., only words linked to WordNet synsets), not the full BNC frequency list.

Full BNC corpus (100M words) would contain far more than 23k unique lemmas.

---

## 5. Integration Recommendation

### VERDICT: **LOW Relevance - SKIP for MVP**

**Rationale:**

❌ **No Value Over SUBTLEX-UK:**
- SUBTLEX-UK provides 7x more frequency coverage
- Both are British English corpora
- BNC frequency data is **strictly redundant**

⚠️ **Subcorpus Analysis is Too Limited:**
- Only 466-507 words per comparison (2-3% of vocabulary)
- "Register" tags could be useful, but coverage is too sparse for MVP
- Would require additional UX design for displaying register metadata

✅ **Current Strategy is Superior:**
- SUBTLEX-UK (160k words) retained from sch.v1
- Provides broad, reliable British English frequency data
- No integration cost (already in use)

### Recommended Strategy: **SKIP BNC**

**For MVP (sch.v2):**
- **Retain SUBTLEX-UK** as frequency source (status quo)
- SKIP BNC integration entirely

**For Post-MVP:**
- **Low priority** - only reconsider if:
  1. Register tagging (spoken/written, formal/casual) becomes a design requirement
  2. User testing shows need for "context appropriateness" hints
  3. Even then, BNC's 500-word coverage may be insufficient

### Alternative: Check SUBTLEX-UK for Dispersion

Before writing off dispersion metrics entirely:

**Action:** Check if SUBTLEX-UK in sch.v1 includes dispersion/range data.

- If yes: BNC offers nothing unique
- If no: BNC's dispersion could still be useful, but limited to 16k words (59% of BNC entries with freq > 0)

---

## 6. Open Questions

1. **BNC Version:** Which BNC corpus is this? Original 100M? BNC2014? Why so limited?

2. **SUBTLEX-UK Dispersion:** Does sch.v1's SUBTLEX-UK data include dispersion metrics? If so, BNC is completely redundant.

3. **Zero-Frequency Puzzle:** Why do 41% of BNC entries have freq=0? Are these:
   - Vocabulary placeholders (words in WordNet but not BNC corpus)?
   - Low-frequency items rounded to zero?
   - Data quality issue?

4. **Subcorpus Value:** Could the 3 subcorpus comparisons inform LLM property extraction? E.g., "This word is strongly associated with spoken register" → extract "informal" property?

---

## 7. Decision Log

| Decision | Rationale | Date |
|----------|-----------|------|
| **SKIP BNC for MVP** | SUBTLEX-UK provides 7x more coverage; BNC frequency data is redundant | 2026-01-30 |
| **Retain SUBTLEX-UK** | 160k British English frequency entries already integrated in sch.v1; superior coverage | 2026-01-30 |
| **Low priority for Post-MVP** | Subcorpus analysis (register tags) has potential but only covers 2-3% of vocabulary | 2026-01-30 |

---

## Next Steps

1. ✅ Complete Phase 1 dataset assessments (SemLink, PredicateMatrix, SyntagNet remaining)
2. Document BNC as "redundant with SUBTLEX-UK" in Phase 1 summary
3. Note: Check SUBTLEX-UK for dispersion metrics to confirm BNC offers nothing unique
