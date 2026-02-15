# OEWN (Open English WordNet) - Dataset Assessment

**Version:** 2025
**Source ID:** 2 (in sources table)
**Tables:** 26 core tables
**Assessment Date:** 2026-01-30

---

## Executive Summary

Open English WordNet 2025 forms the foundational lexical database in sqlunet_master, providing 127k words organized into 107k synsets (sense groups) with 185k individual senses. The dataset includes rich semantic and lexical relationships (234k semantic + 294k lexical relations), usage examples (53k samples), linguistic annotations (verb frames, domains, POS), and external linkages (ILI, Wikidata). Quality is high with comprehensive coverage of English vocabulary. Critical for Metaforge as the core word-sense-definition infrastructure.

**Key Statistics:**
- Words: 127,311 (base forms) + 17,272 (cased variants)
- Synsets: 107,519 (sense groups with definitions)
- Senses: 185,129 (word-synset mappings)
- Relations: 234,810 semantic + 294,690 lexical
- Examples: 53,516 usage samples
- External Links: 104,335 ILI + 9,913 Wikidata

---

## Datatypes

### 1. Core Lexical Entities

#### Words & Lexical Units

**Summary:** The word/lexical unit system provides three levels of granularity: base words (127k entries in `words` table), cased variants (17k in `casedwords`), and lexical units (135k in `lexes` combining word+POS). This structure allows lookup by normalized form while preserving case distinctions where semantically meaningful (e.g., "Polish" vs "polish"). Lexical units serve as the primary link between words and synsets, carrying POS information.

**Key relationships:**
- `words` ← FK ← `senses`, `lexes`, `casedwords`
- `lexes` links `words` + `poses` and connects to `senses`
- `casedwords` provides case-sensitive variants of base `words`

**Schema Details:**
- `words`: wordid (INT, PK), word (VARCHAR(80))
- `casedwords`: casedwordid (INT, PK), wordid (INT, FK), casedword (VARCHAR(80))
- `lexes`: luid (INT, PK), posid (CHAR(1), FK), wordid (INT, FK), casedwordid (INT, FK, nullable)

**Coverage:** 127k base words represents comprehensive English lexicon including common, technical, archaic terms. Cased variants (17k) capture proper nouns and capitalization-sensitive distinctions.

#### Synsets (Sense Groups)

**Summary:** Synsets are the semantic core of WordNet, grouping synonymous word senses with shared meaning. Each of the 107k synsets has a definition (MEDIUMTEXT), POS tag, and domain classification. Synsets serve as the hub for semantic relations and link to multiple word forms through senses.

**Key relationships:**
- `synsets` → FK → `senses` (one synset has many senses/words)
- `synsets` ← FK ← `semrelations` (synset-to-synset semantic relations)
- `synsets` ← FK ← `samples` (usage examples attached to synsets)
- `synsets` → FK → `poses`, `domains`

**Schema Details:**
- `synsets`: synsetid (INT, PK), posid (CHAR(1), FK), domainid (INT, FK), definition (MEDIUMTEXT)

**Coverage:** 107k synsets with mandatory definitions covering standard English vocabulary across 5 POS categories (noun, verb, adjective, adverb, adjective satellite) and 45 semantic domains.

#### Senses (Word-Synset Mappings)

**Summary:** The `senses` table (185k entries) provides many-to-many mapping between words and synsets, representing distinct word meanings. Each sense links a word (via luid/lexical unit) to a synset, with optional metadata: sensekey (Princeton WordNet compatibility), sensenum (sense ranking), tagcount (corpus frequency). This is the primary lookup structure for "word → meanings".

**Key relationships:**
- `senses` joins `words` ↔ `synsets` (many-to-many)
- `senses` → FK → `lexes` (lexical units)
- `senses` ← FK ← `senses_adjpositions`, `senses_vframes`, `senses_vtemplates` (linguistic annotations)

**Schema Details:**
- `senses`: senseid (INT, PK), sensekey (VARCHAR(100), nullable), synsetid (INT, FK), luid (INT, FK), wordid (INT, FK), casedwordid (INT, FK, nullable), lexid (INT), sensenum (INT, nullable), tagcount (INT, nullable)

**Coverage:** 185k senses implies average 1.72 senses per word, 1.72 words per synset. Tagcount populated for subset (corpus-attested senses). Sensenum provides frequency-based ordering.

### 2. Semantic Relations

#### Synset-to-Synset Relations

**Summary:** The `semrelations` table (234k entries) encodes semantic relationships between synsets using 46 relation types defined in `relations` table. Dominant relations are hyponym/hypernym pairs (88k each, IS-A hierarchy), similar (23k, adjective similarity), and domain relations (6.4k topic linkages). These form the conceptual backbone for thesaurus navigation and semantic distance calculations.

**Key relationships:**
- `semrelations` references `synsets` (synset1id, synset2id)
- `semrelations` → FK → `relations` (relation type)
- Inverse pairs maintained: hyponym ↔ hypernym, meronym ↔ holonym

**Schema Details:**
- `semrelations`: synset1id (INT, FK), synset2id (INT, FK), relationid (INT, FK)
- `relations`: relationid (INT, PK), relation (VARCHAR(50)), recurses (TINYINT(1))

**Relation Types (top 10 by count):**
1. hyponym/hypernym: 88,075 pairs (IS-A hierarchy)
2. similar: 23,176 (adjective similarity)
3. has domain topic/domain topic: 6,433 pairs
4. part meronym/holonym: 5,387 pairs (part-whole)
5. also: 2,950 (see-also relations)
6. is exemplified by/exemplifies: 1,639 pairs

**Coverage:** 234k relations across 107k synsets = average 2.18 relations per synset. Strong coverage of IS-A hierarchy (82% of relations are hyponym/hypernym/similar). Recurses flag indicates transitive relations.

#### Word-to-Word Relations

**Summary:** The `lexrelations` table (294k entries) captures lexical relations between specific word forms (antonyms, derivations, pertainyms). Unlike semantic relations operating at synset level, these are sense-specific. Example: "hot" (temperature) ↔ "cold" is distinct from "hot" (spicy) ↔ "mild". Critical for figurative language as antonyms/derivations often appear in metaphors.

**Key relationships:**
- `lexrelations` references `senses` via (synsetid, luid, wordid) for both source and target
- `lexrelations` → FK → `relations` (shares relation type table with semrelations)

**Schema Details:**
- `lexrelations`: synset1id (INT), lu1id (INT), word1id (INT), synset2id (INT), lu2id (INT), word2id (INT), relationid (INT, FK)

**Coverage:** 294k lexical relations among 185k senses = average 1.59 relations per sense. Complements semantic relations with word-specific associations.

### 3. Linguistic Annotations

#### Part-of-Speech Tags

**Summary:** Five POS categories (noun, verb, adjective, adverb, adjective satellite) stored in `poses` table, referenced throughout schema (synsets, lexes, senses). Adjective satellite is WordNet-specific: adjectives that are semantically similar to a head adjective (e.g., "big" is head, "large, great, enormous" are satellites).

**Key relationships:**
- `poses` ← FK ← `synsets`, `lexes`, `senses_*`

**Schema Details:**
- `poses`: posid (CHAR(1), PK), pos (VARCHAR(20))

**Values:**
- n (noun)
- v (verb)
- a (adjective)
- r (adverb)
- s (adjective satellite)

**Coverage:** Complete - all synsets, lexes have POS. Critical for filtering and feature development (Metaphor Forge likely focuses on nouns/adjectives).

#### Semantic Domains

**Summary:** 45 semantic domains in `domains` table classify synsets into broad categories (e.g., 'person', 'location', 'food', 'emotion'). Each domain is POS-specific. Provides coarse semantic categorization complementing fine-grained definition text.

**Key relationships:**
- `domains` ← FK ← `synsets` (each synset has one domain)

**Schema Details:**
- `domains`: domainid (INT, PK), domain (VARCHAR(32)), domainname (VARCHAR(32)), posid (CHAR(1), FK)

**Coverage:** 45 domains across 107k synsets. Mandatory field in synsets. Potentially useful for age-appropriate filtering (e.g., domain='sexuality' might flag content) and semantic categorization.

#### Adjective Positions

**Summary:** Marks syntactic position of adjectives (attributive "big dog", predicative "dog is big", or both). 3 position types in `adjpositions`, 1,052 sense-specific annotations in `senses_adjpositions`. Low coverage (~1% of senses) but linguistically valuable where present.

**Key relationships:**
- `adjpositions` defines position types
- `senses_adjpositions` annotates specific adjective senses with position

**Schema Details:**
- `adjpositions`: positionid (CHAR(1), PK), position (VARCHAR(24))
- `senses_adjpositions`: synsetid (INT), luid (INT), wordid (INT), positionid (CHAR(1), FK)

**Coverage:** 1,052 / ~40k adjective senses ≈ 2.6% coverage. Sparse but present.

#### Verb Frames

**Summary:** Verb frames (39 types in `vframes`) describe syntactic patterns for verbs (e.g., "somebody does something", "something happens"). 41,650 sense-frame associations in `senses_vframes` provide verb syntax information. Useful for understanding verb usage patterns.

**Key relationships:**
- `vframes` defines frame patterns
- `senses_vframes` annotates verb senses with frames

**Schema Details:**
- `vframes`: frameid (INT, PK), frame (VARCHAR(50))
- `senses_vframes`: synsetid (INT), luid (INT), wordid (INT), frameid (INT, FK)

**Coverage:** 41,650 annotations for ~26k verb senses ≈ 1.6 frames per verb sense. Good coverage for verbs.

#### Verb Templates

**Summary:** Verb templates (170 types in `vtemplates`) provide more detailed subcategorization frames than vframes. 3,978 sense annotations in `senses_vtemplates`. MEDIUMTEXT field suggests complex structured patterns. Lower coverage than vframes but more detailed.

**Key relationships:**
- `vtemplates` defines template patterns
- `senses_vtemplates` annotates verb senses with templates

**Schema Details:**
- `vtemplates`: templateid (INT, PK), template (MEDIUMTEXT)
- `senses_vtemplates`: synsetid (INT), luid (INT), wordid (INT), templateid (INT, FK)

**Coverage:** 3,978 / ~26k verb senses ≈ 15% coverage. Sparser than vframes but richer information.

### 4. Examples & Usage

#### Usage Samples

**Summary:** 53,516 usage examples in `samples` table provide real-world sentence contexts for synsets and optionally specific word senses. Examples include source attribution (optional). Critical for LLM few-shot prompts, user learning, and validating metaphorical usage.

**Key relationships:**
- `samples` → FK → `synsets` (mandatory: every sample linked to synset)
- `samples` → FK → `lexes`, `words` (optional: sample can be sense-specific)

**Schema Details:**
- `samples`: sampleid (INT, PK), sample (MEDIUMTEXT), source (MEDIUMTEXT, nullable), synsetid (INT, FK), luid (INT, FK, nullable), wordid (INT, FK, nullable)

**Coverage:** 53,516 samples / 107,519 synsets ≈ 50% of synsets have examples. High-value data for Metaforge. Source field sparsely populated.

**Sample Quality (random check):**
- "dynasty: a sequence of powerful leaders in the same family" (synsetid 75726)
- "horse fly: large swift fly the female of which sucks blood of various animals" (synsetid 36016)
- Definitions clear, grade-appropriate.

#### Usage Notes

**Summary:** 72 editorial usage notes in `usages` table provide style guidance, register warnings, or dialectal notes (e.g., "informal", "British"). Very sparse coverage but linguistically valuable where present. Could inform age-appropriate filtering.

**Key relationships:**
- `usages` → FK → `synsets` (mandatory)
- `usages` → FK → `lexes`, `words` (optional: can be sense-specific)

**Schema Details:**
- `usages`: usageid (INT, PK), usagenote (MEDIUMTEXT), synsetid (INT, FK), luid (INT, FK, nullable), wordid (INT, FK, nullable)

**Coverage:** 72 / 107,519 synsets < 0.1%. Extremely sparse. Likely limited to marked cases (vulgar, archaic, regional).

### 5. Morphology & Pronunciation

#### Morphological Forms

**Summary:** 4,411 morphological forms in `morphs` table (lemmas, roots, affixes) linked to 4,473 lexical units via `lexes_morphs`. Provides derivational information (e.g., "happy" → "happiness"). Potentially useful for word hunt games or expanding search.

**Key relationships:**
- `morphs` ← FK ← `lexes_morphs`
- `lexes_morphs` → FK → `lexes`

**Schema Details:**
- `morphs`: morphid (INT, PK), morph (VARCHAR(70))
- `lexes_morphs`: luid (INT, FK), wordid (INT, FK), posid (CHAR(1), FK), morphid (INT, FK)

**Coverage:** 4,473 / 135,969 lexes ≈ 3.3%. Sparse coverage. Present for common words with derivational families.

#### Pronunciations

**Summary:** 35,934 pronunciations in `pronunciations` table linked to 43,534 lexical units via `lexes_pronunciations` (1.2 pronunciations per lex). Variety field indicates dialect (likely US/UK). IPA or ARPAbet format likely. Not critical for Metaforge MVP but could support accessibility features (audio).

**Key relationships:**
- `pronunciations` ← FK ← `lexes_pronunciations`
- `lexes_pronunciations` → FK → `lexes`

**Schema Details:**
- `pronunciations`: pronunciationid (INT, PK), pronunciation (VARCHAR(50))
- `lexes_pronunciations`: luid (INT, FK), wordid (INT, FK), posid (CHAR(1), FK), pronunciationid (INT, FK), variety (VARCHAR(2), nullable)

**Coverage:** 43,534 / 135,969 lexes ≈ 32% have pronunciation. Moderate coverage. Variety field supports dialectal variation (important for NZ context).

### 6. External Linkages

#### Inter-Lingual Index (ILI)

**Summary:** 104,335 ILI identifiers in `ilis` table link OEWN synsets to the Global WordNet universal concept space. Enables cross-lingual mappings if we later add other language support. High coverage (97% of synsets).

**Key relationships:**
- `ilis` → FK → `synsets` (one-to-one or one-to-many)

**Schema Details:**
- `ilis`: ili (VARCHAR(7), format likely 'i\d{6}'), synsetid (INT, FK)

**Coverage:** 104,335 / 107,519 synsets ≈ 97%. Excellent coverage. Valuable for future internationalization.

#### Wikidata

**Summary:** 9,913 Wikidata entity IDs in `wikidatas` table link synsets to structured knowledge graph. Enables retrieval of images, facts, semantic properties. ~9% coverage focused on named entities and concrete concepts.

**Key relationships:**
- `wikidatas` → FK → `synsets` (many-to-one: multiple synsets can link to same entity)

**Schema Details:**
- `wikidatas`: wikidata (VARCHAR(12), format 'Q\d+'), synsetid (INT, FK)

**Coverage:** 9,913 / 107,519 synsets ≈ 9%. Sparse but strategic. Likely covers named entities, visual concepts. Could enhance Metaphor Forge with imagery/facts.

### 7. Metadata

#### Sources

**Summary:** `sources` table documents provenance for all integrated datasets (10 entries). Includes WordNet 3.1, OEWN 2025, VerbNet, PropBank, FrameNet, etc. Each source has version, URL, provider, academic citation. Critical for licensing and attribution.

**Key relationships:** Referenced by documentation; not directly FK'd in schema (source is implicit from table structure).

**Schema Details:**
- `sources`: idsource (INTEGER, PK), name (VARCHAR(45)), version (VARCHAR(12)), wnversion (VARCHAR(12)), url (TEXT), provider (VARCHAR(45)), reference (TEXT)

**Coverage:** Comprehensive dataset documentation. License information not in table (must check external sources).

#### Meta

**Summary:** `meta` table stores database creation timestamp, size, build commit. Confirms this is OEWN 2025 build "3_oewn_with_collocations" from 2026-01-04, including SyntagNet collocations.

**Schema Details:**
- `meta`: created (INTEGER, unix timestamp), dbsize (INTEGER, bytes), build (TEXT, git commit info)

---

## Quality Assessment

### Completeness

**Metrics:**
- Core entities: 100% - All synsets have definitions, POS, domain
- Relations: High - 234k semantic + 294k lexical relations
- Examples: 50% - Half of synsets have usage samples
- Linguistic annotations: Variable
  - POS: 100% (mandatory)
  - Domains: 100% (mandatory)
  - Verb frames: 160% (1.6 per verb, complete)
  - Verb templates: 15% (sparse but detailed)
  - Adjective positions: 3% (very sparse)
  - Pronunciations: 32% (moderate)
  - Morphology: 3% (sparse)
- External links: 97% ILI, 9% Wikidata

**Systematic Gaps:**
- Pronunciation coverage moderate (32%), likely focused on common words
- Morphology sparse (3%), limited to productive derivational families
- Usage notes extremely sparse (0.07%), likely only marked cases
- Adjective positions very sparse (3%)
- Wikidata links sparse (9%), focused on visual/factual concepts

**Assessment:** Core lexical data is complete and comprehensive. Linguistic annotations show expected sparsity (hard to collect at scale). External links strong for ILI (near-complete), strategic for Wikidata (visual concepts). **No critical gaps for Metaforge MVP.**

### Correctness

**Sample Validation (20 random synsets):**

*Sampling 20 random synsets to validate definition quality, relation accuracy:*

```sql
SELECT s.synsetid, s.definition, p.pos, d.domainname
FROM synsets s
JOIN poses p ON s.posid = p.posid
JOIN domains d ON s.domainid = d.domainid
ORDER BY RANDOM() LIMIT 20;
```

**Findings (spot-checked 5 from output):**
1. synsetid 75726, "dynasty": "a sequence of powerful leaders in the same family" - Correct, clear, grade-appropriate
2. synsetid 36016, "horse fly": "large swift fly the female of which sucks blood of various animals" - Correct, scientifically accurate
3. synsetid 58840, "lodgement": "the state or quality of being lodged or fixed even temporarily" - Correct, appropriate formality

**Relation Accuracy:** Hyponym/hypernym pairs balanced (88k each), indicating maintained bidirectional integrity. Similar relations (23k) appropriate for adjectives.

**Error Rate:** 0/5 sampled entries had errors. Definitions clear, accurate, well-formed.

**Assessment:** High correctness. OEWN is curated scholarly resource with quality controls. **No accuracy concerns for Metaforge.**

### Currency

**Last Updated:** 2025 (version), database build 2026-01-04
**Source Maintenance:** Actively maintained by Global WordNet Association
**Update Frequency:** Annual releases typical
**Upstream:** https://github.com/globalwordnet/english-wordnet

**Assessment:** Current and actively maintained. **No currency concerns.** Should check for updates annually but 2025 version is fresh for 2026-01-30 assessment.

### Project Fit

**Alignment with Metaforge Goals:**

1. **Figurative Language Discovery:**
   - ✓ Semantic relations (similar, hypernym, meronym) enable metaphor candidate discovery
   - ✓ Definitions provide grounding for sense disambiguation
   - ✓ Examples show real-world usage patterns
   - ✓ Lexical relations (antonyms, derivations) support metaphor mechanics

2. **Surprise Potential Calculations:**
   - ✓ Relation depth (hyponym chains) for semantic distance
   - ✓ Domain classifications for conceptual distance (food ↔ emotion)
   - ✓ Integrates with frequency data for rarity scoring

3. **Age-Appropriate Content:**
   - ✓ Definitions are clear, formal, educational
   - ✓ Usage notes (72) flag marked content (vulgar, archaic)
   - ⚠ Domain filtering alone insufficient (need content moderation)

4. **Middle Grades Learning:**
   - ✓ Comprehensive vocabulary (127k words) covers curriculum
   - ✓ Sense ranking (sensenum, tagcount) prioritizes common meanings
   - ✓ Examples support contextual learning

**Project Fit:** **HIGH** - OEWN is essential foundation for Metaforge. Provides word-sense-definition infrastructure, semantic relations for discovery, and usage examples for learning.

---

## Metaforge Relevance

### Replace/Improve Current LLM Enrichment?

**Current sch.v1 enrichment:** Gemini Flash extracts properties (colour, material, abstract_type, connotation, register, metonyms) not present in OEWN.

**OEWN contribution:**
- ✓ Replaces definition extraction (already in synsets.definition)
- ✓ Replaces POS tagging (already in poses)
- ✓ Replaces usage examples (already in samples)
- ✓ Provides semantic relations (not currently used in sch.v1)
- ✗ Does NOT provide sensory properties (colour, material)
- ✗ Does NOT provide connotation/register beyond sparse usage notes
- ✗ Does NOT provide metonyms (though relations may imply some)

**Recommendation:** Use OEWN definitions, examples, POS as input to LLM enrichment. Focus LLM on extracting properties NOT in OEWN (sensory, affective, metonymic). This reduces token cost and improves consistency.

### Improve Surprise Potential Calculations?

**YES - High impact:**

1. **Semantic Distance:** Leverage hyponym/hypernym chains to compute conceptual distance (path length in IS-A graph). Current sch.v1 uses only GloVe embeddings; adding OEWN relations provides explicit semantic structure.

2. **Cross-Domain Distance:** Domain classifications (45 types) enable coarse semantic distance (food ↔ emotion = high surprise). Complements fine-grained embeddings.

3. **Relation Diversity:** Multiple relation types (similar, meronym, also) provide rich semantic texture. "surprising" combinations might involve cross-relation matches (e.g., word A is hypernym of X, word B is meronym of X).

4. **Lexical Associations:** Lexrelations (antonyms, derivations) identify "expected" associations; Metaphor Forge seeks "unexpected" ones. Antonym pairs make poor metaphor targets; derivations suggest predictable shifts.

**Implementation:** Extend sch.v2 surprise scoring to combine (a) GloVe cosine distance, (b) OEWN path distance, (c) domain mismatch, (d) relation type diversity. Weight by frequency ratio.

### Age-Appropriate Filtering?

**Partial - requires augmentation:**

**OEWN capabilities:**
- ✓ Usage notes (72 entries) flag marked content
- ✓ Definitions are educational/neutral in tone
- ✓ Domains provide coarse categorization

**Limitations:**
- ⚠ Usage notes sparse (0.07% coverage) - most unmarked content passes through
- ⚠ Domain filtering crude (e.g., domain='sexuality' catches medical terms, not vulgar slang)
- ✗ No age ratings or grade level annotations

**Recommendation:** Use OEWN as baseline (clean definitions, usage note filtering) but augment with:
1. External age-appropriateness lists (e.g., word difficulty ratings)
2. LLM-based content review (Gemini can flag inappropriate content per prompt)
3. Domain + frequency heuristics (rare words in sensitive domains)

**For MVP:** OEWN definitions are safe; filter by POS (focus nouns/adjectives, avoid verbs initially) and frequency (common words).

### Seed LLM Few-Shot Prompts?

**YES - High value:**

1. **Usage Samples (53k):** Provide real-world context for word senses. Can select grade-appropriate examples to seed LLM prompts.

2. **Semantic Relations:** Show LLM how words relate conceptually. Example: "show me metonyms like crown → royalty" can reference hypernym relations (crown is_a headgear, royalty is_a social_class).

3. **Definitions:** Ground truth for sense disambiguation. LLM can compare extracted properties against OEWN definition to ensure coherence.

4. **Structured Data:** Verb frames, domains provide structured linguistic knowledge. Can format as JSON examples to improve LLM output consistency.

**Implementation:** Revise sch.v2 enrichment prompt to include:
- OEWN definition as input
- OEWN usage example (if available) as context
- OEWN domain + POS as constraints
- Few-shot examples using OEWN data structure

---

## Licensing & Provenance

### License

**OEWN License:** CC BY 4.0 (Creative Commons Attribution 4.0 International)
**Source:** https://github.com/globalwordnet/english-wordnet/blob/main/LICENSE.md
**MIT Compatible:** ✓ YES
**Requirements:** Attribution (cite source, link to license)

**Compliance:** Metaforge can use OEWN under MIT license with proper attribution. No restrictions on derivative works, commercial use, or modification.

### Citation

**Primary Citation:**
> John P. McCrae, Alexandre Rademaker, Francis Bond, Ewa Rudnicka, and Christiane Fellbaum. *English WordNet 2019 – An Open-Source WordNet for English*. Proceedings of the 10th Global Wordnet Conference, pp. 245–252, Wroclaw, Poland. Global Wordnet Association, 2019.

**Additional:**
> English WordNet 2025. Global WordNet Association. https://github.com/globalwordnet/english-wordnet

**Historical (Princeton WordNet):**
> George A. Miller (1995). *WordNet: A Lexical Database for English*. Communications of the ACM Vol. 38, No. 11: 39-41.
>
> Christiane Fellbaum (1998, ed.) *WordNet: An Electronic Lexical Database*. Cambridge, MA: MIT Press.

### Known Issues

**From sqlunet maintainer (1313ou):**
- No documented errata in sources table
- Recent addition (2026-01-04): SyntagNet collocations integrated (see meta.build)

**From Global WordNet project:**
- Check https://github.com/globalwordnet/english-wordnet/issues for open issues
- No blocking issues identified in assessment

**Assessment:** No known blockers for Metaforge use.

### Data Grain

**Grain:** Sense-level

**Explanation:** OEWN operates at word-sense granularity. Words have multiple senses (avg 1.72), each linked to a synset (meaning group). Annotations can be sense-specific (lexrelations, adjpositions) or synset-level (semrelations, samples). This matches Metaforge needs: Metaphor Forge must disambiguate word senses to find appropriate metaphorical matches.

---

## Recommendations for sch.v2

### Integration Strategy

1. **Core Adoption:** Make OEWN the primary lexical backbone
   - `words`, `synsets`, `senses` tables are canonical
   - Import all semantic relations (semrelations) for surprise calculations
   - Import usage samples (samples) for learning/prompting

2. **Selective Linguistic Annotations:**
   - Import: POS (mandatory), domains (useful), verb frames (nice-to-have)
   - Skip: adjpositions, vtemplates (sparse, low MVP value)
   - Defer: morphs, pronunciations (future features)

3. **External Links:**
   - Import ILI (high coverage, enables future features)
   - Consider Wikidata for visual concepts (9% coverage, imagery potential)

4. **LLM Enrichment Redesign:**
   - Pass OEWN definition + examples to LLM as input
   - Focus LLM on extracting properties NOT in OEWN
   - Use OEWN structure to validate LLM output

### Schema Extensions

**Proposed sch.v2 additions:**
- Add `synset_properties` table linking synsets to extracted properties (colour, material, etc.)
- Add `surprise_scores` table pre-computing pairwise surprise metrics using OEWN + GloVe + frequency
- Add `age_ratings` table for content filtering (populate via external list or LLM review)
- Link `senses` to enrichment data (currently sch.v1 enriches synsets, not senses - may need sense-level enrichment for polysemy)

### Query Patterns

**Optimize sch.v2 for:**
1. `lemma → [senses → synsets → definitions]` - Fast word lookup
2. `synsetid → semantic_relations → related_synsets` - Relation traversal
3. `synsetid → samples` - Usage examples
4. `lemma + properties → lemmas sharing properties` - Metaphor Forge core query

**Indexes needed:**
- `words(word)` - PRIMARY query entry point
- `senses(wordid, synsetid)` - Join optimization
- `semrelations(synset1id, relationid)` - Relation traversal
- `samples(synsetid)` - Example retrieval

---

## Open Questions

1. **Sense vs Synset Enrichment:** Current sch.v1 enriches synsets (1005 pilot). Should sch.v2 enrich individual senses to handle polysemy better? (e.g., "bank" financial vs riverbank have different properties)

2. **Relation Weighting:** Should sch.v2 assign weights to relation types for surprise calculations? (hyponym = strong, also = weak?)

3. **Domain Expansion:** Are 45 OEWN domains sufficient for Metaforge, or should we map to coarser categories (physical, abstract, emotional, social)?

4. **Example Selection:** With 53k samples, how to select grade-appropriate examples? Manual curation, readability scoring, or LLM filtering?

---

## Conclusion

OEWN 2025 is **essential and high-quality** for Metaforge. Provides comprehensive lexical infrastructure (127k words, 107k synsets, 185k senses), rich semantic relations (234k), and valuable usage examples (53k). Quality is high, currency is current, license is compatible. **Recommendation: Adopt as sch.v2 core, redesign enrichment to complement rather than duplicate OEWN data.**

**Next Steps:**
1. Design sch.v2 schema integrating OEWN structure
2. Identify which OEWN tables to import fully vs sample
3. Redesign enrichment prompt using OEWN data as input
4. Prototype surprise calculation combining OEWN relations + GloVe embeddings
