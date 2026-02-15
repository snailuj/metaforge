# SyntagNet Dataset Assessment

**Date:** 2026-01-30
**Dataset:** SyntagNet (semantic collocation network)
**Source:** sqlunet_master.db (1 table, `sn_syntagms`)

---

## 1. Schema Analysis

### Core Table & Relationships

```
sn_syntagms (87,265)
├── syntagmid (collocation ID)
├── word1id → words.wordid (first word)
├── synset1id → OEWN synsets (first word sense)
├── sensekey1 (WordNet sense key)
├── word2id → words.wordid (second word)
├── synset2id → OEWN synsets (second word sense)
└── sensekey2 (WordNet sense key)
```

### Coverage Statistics

- **Total Collocations:** 87,265
- **Unique First Words:** 8,026
- **Unique Second Words:** 9,579
- **Unique Synsets (word1):** 13,405 (12.5% of OEWN's 107k)
- **Unique Synsets (word2):** 13,959 (13% of OEWN's 107k)
- **Synset Link Completeness:** 100% (no null synset links)

---

## 2. Quality Assessment

### Coverage

✅ **High-Quality Sense Disambiguation:**
- Every collocation is sense-disambiguated (synset1id + synset2id)
- 100% synset link coverage (no missing links)
- 13k+ distinct synsets covered (~13% of OEWN)

### Sample Collocations

**"abandon" (verb) collocates with:**
- abandon + hope (give up hope)
- abandon + child (desert a child)
- abandon + ship (evacuate a ship)
- abandon + belief (relinquish a belief)

**"whisper" (verb) collocates with:**
- whisper + ear (whisper in ear)
- whisper + voice (speak in whisper voice)
- whisper + pine (poetic: pine trees whisper)

**"metaphor" (noun) collocates with:**
- describe + metaphor
- use + metaphor
- represent + metaphor

### Quality Indicators

✅ **Strengths:**
- **Sense-Aware:** Each collocation links specific word senses (not just lemmas)
- **Semantic Relationships:** Captures typical verb-object, adj-noun, noun-noun pairs
- **Clean Schema:** Simple single-table design, minimal joins required
- **Complete Links:** 100% synset coverage (all entries linked to OEWN)

⚠️ **Weaknesses:**
- **Limited Coverage:** 13k synsets (12.5% of OEWN) - focused on most common collocations
- **No Frequency Data:** No indication of collocation strength or corpus frequency
- **No Relation Types:** Unclear if pairs are verb-object, modifier-head, etc.
- **Verb-Heavy First Position:** 8k first words suggests verb-object bias (not confirmed)

---

## 3. Metaforge Relevance

### Use Cases

#### 1. "Commonly Used With" Suggestions (MEDIUM VALUE)

**Scenario:** User enters target word → show common collocations for context.

**Example:**
- Target: "whisper" → Suggestions: "whisper into ear", "whisper sweet nothings", "whisper conspiratorially"

**UI Integration:**
- Metaphor Forge: Show collocations as "typical usage" hints
- Core Thesaurus: Display collocations in word detail panel

**Verdict:** **Nice-to-have, not MVP-critical** - adds context but not essential for metaphor forging.

#### 2. Inform Property Extraction (LOW-MEDIUM VALUE)

**Scenario:** Use collocation patterns to infer properties during LLM enrichment.

**Example:**
- "whisper" + "ear" + "voice" → infer "quiet", "intimate", "confidential" properties
- "illuminate" + "room" + "darkness" → infer "emits light", "visibility" properties

**Workflow:**
1. Look up synset → SyntagNet → get common collocates
2. Pass collocations to LLM as additional context
3. Extract properties informed by typical usage patterns

**Verdict:** **Speculative** - would need testing to validate if collocations improve property extraction quality.

#### 3. Collocation-Based Surprise (LOW VALUE)

**Scenario:** Measure metaphor surprise by checking if forge pairs are atypical collocations.

**Example:**
- "whisper" + "darkness" (not in SyntagNet) → HIGH surprise
- "whisper" + "voice" (in SyntagNet) → LOW surprise

**Verdict:** **Not aligned with design** - Metaphor Forge uses semantic distance (GloVe embeddings + VerbNet classes), not collocation frequency.

#### 4. Filter Out Literal Pairs (LOW VALUE)

**Scenario:** During metaphor forging, de-prioritize word pairs that are common literal collocations.

**Example:**
- "heavy" + "rain" (common collocation) → de-prioritize as likely literal
- "heavy" + "silence" (not common collocation) → prioritize as potential metaphor

**Verdict:** **Contradicts 5-tier visual system** - design explicitly shows ALL matches, letting user decide. No automatic filtering planned.

---

## 4. Integration Feasibility

### Complexity Assessment

**Schema Complexity: LOW**

- Single table with 7 columns
- Straightforward foreign keys to OEWN synsets
- Minimal integration cost

**Data Volume:**

- 87,265 collocation pairs (lightweight)
- 13k distinct synsets (manageable)

### Proposed Integration Strategy

#### Option A: Full Integration (Low Priority Post-MVP)

**Import:**
- All 87k collocation pairs as `syntagms` table
- Link to sch.v2 synsets via synset1id/synset2id

**Use Cases:**
- Display "commonly used with" in UI
- Experimental: inform LLM property extraction with collocation context

**Costs:**
- Minimal schema complexity (1 table)
- No immediate MVP value (nice-to-have only)

#### Option B: Collocation-Informed Enrichment (Experimental)

**Scenario:** Query SyntagNet during LLM enrichment, but don't import into sch.v2.

**Workflow:**
1. Look up synset in sqlunet_master.db → SyntagNet on-demand
2. Pass collocations to LLM enrichment prompt as context
3. Test if collocations improve property extraction quality

**Benefits:**
- Zero schema complexity (no sch.v2 integration)
- Can prototype enrichment improvements without commitment

**Drawbacks:**
- Requires sqlunet_master.db access during enrichment
- Slower (extra query per synset)

#### Option C: Skip for MVP (Recommended)

**Rationale:**
- No clear MVP use case (collocations not in design)
- "Commonly used with" is nice-to-have, not critical
- Collocation-based surprise conflicts with design (semantic distance, not frequency)
- Uncertain if collocations improve LLM property extraction

**Decision:** **SKIP SyntagNet for MVP**, revisit Post-MVP if testing shows collocations add value.

---

## 5. Comparison with Other Datasets

| Dataset | Purpose | SyntagNet Relevance |
|---------|---------|---------------------|
| **OEWN** | Word-sense-definition core | ✅ SyntagNet links 13k OEWN synsets |
| **VerbNet** | Verb semantic classes | ⚠️ Potential overlap (verb-object patterns) |
| **FrameNet** | Frame semantics | ⚠️ Collocations could complement frame usage patterns |
| **SUBTLEX-UK** | Frequency data | ❌ SyntagNet lacks frequency/strength metrics |

**Key Insight:** SyntagNet is **complementary** to other datasets:
- OEWN provides definitions, SyntagNet provides usage patterns
- VerbNet provides semantic classes, SyntagNet provides typical arguments
- FrameNet provides frame structure, SyntagNet provides corpus-attested collocates

---

## 6. Integration Recommendation

### VERDICT: **LOW Relevance - SKIP for MVP**

**Rationale:**

⚠️ **No Clear MVP Use Case:**
- "Commonly used with" suggestions are nice-to-have, not MVP-critical
- Collocation-based surprise conflicts with design (semantic distance prioritized)
- Filtering literal pairs contradicts 5-tier visual system (show all matches)

✅ **Potential Post-MVP Value:**
- Could improve LLM property extraction by providing usage context
- "Commonly used with" could enhance Core Thesaurus UX
- Minimal integration cost (1 table, 87k rows)

❌ **No Frequency Data:**
- SyntagNet only provides binary collocation (yes/no), no strength metric
- Can't distinguish "very common" from "rarely used together"

### Recommended Strategy: **Defer to Post-MVP**

**For MVP (sch.v2):**
- **SKIP SyntagNet** - no clear use case in current design
- Focus on OEWN (definitions) + VerbNet (verb classes) + SUBTLEX-UK (frequency)

**For Post-MVP:**
- **Experiment with collocation-informed enrichment** - test if usage patterns improve LLM property extraction
- **Consider UI integration** - add "commonly used with" to Core Thesaurus detail panels
- Integration cost is minimal if value is proven

---

## 7. Open Questions

1. **Enrichment Value:** Would providing collocations to LLM enrichment improve property extraction quality? Needs A/B testing.

2. **Relation Types:** SyntagNet doesn't specify relation type (verb-object, adj-noun, etc.). Are there patterns we could infer from POS tags?

3. **Frequency Alternative:** Could we derive collocation data from our own corpus (e.g., usage examples from OEWN + VerbNet + PropBank)?

4. **Metaphor Detection:** Research question - are atypical collocations stronger metaphor indicators than semantic distance? (Unlikely, but worth noting)

5. **Coverage Expansion:** 13k synsets (12.5%) is limited. Would full collocation extraction from OEWN examples be more valuable?

---

## 8. Decision Log

| Decision | Rationale | Date |
|----------|-----------|------|
| **SKIP SyntagNet for MVP** | No clear use case in current design; collocation suggestions are nice-to-have, not critical | 2026-01-30 |
| **Low integration cost** | Single table, 87k rows - trivial to add if value proven | 2026-01-30 |
| **Experimental Post-MVP** | Test if collocation context improves LLM property extraction before committing to integration | 2026-01-30 |

---

## Next Steps

1. ✅ Complete Phase 1 dataset assessments (ALL 8 DATASETS COMPLETE)
2. Create Phase 1 summary document with integration strategy matrix
3. Proceed to Phase 2: Remix (design sch.v2 schema)
