# VerbNet - Dataset Assessment

**Version:** 3.4
**Source ID:** 10 (in sources table)
**Tables:** 20 (vn_* prefix)
**Assessment Date:** 2026-01-30

---

## Executive Summary

VerbNet 3.4 provides hierarchical semantic classification of 4,637 verbs into 609 classes with detailed syntax-semantics mappings. Includes 1,780 thematic roles, 1,539 syntactic frames, 867 semantic representations, and 1,599 usage examples. Links to WordNet via 9,827 sense mappings. **Project Fit: MEDIUM-HIGH** - VerbNet directly supports verb metaphor extraction (design explicitly includes verbs: "illuminate.v.01", "whisper.v.01"). Semantic classes group verbs by behavior (exactly what property extraction needs), thematic roles inform argument structure, and semantic predicates (motion, cause, contact) map to extractable properties ("flows", "reveals", "connects").

**Key Statistics:**
- Classes: 609 semantic verb classes
- Verbs: 4,637 (7,073 class memberships - verbs can belong to multiple classes)
- WordNet Links: 9,827 sense mappings (quality-scored)
- Frames: 1,539 syntactic frames (348 framenames, 450 subnames)
- Examples: 1,599 usage examples
- Roles: 1,780 role instances (39 role types: Agent, Patient, Theme, etc.)
- Semantics: 867 semantic representations, 163 predicates

---

## Datatypes

### 1. Verb Classes (Semantic Classification)

**Summary:** 609 hierarchical verb classes (e.g., "amuse-31.1", "sound_emission-43.2") group verbs by shared semantic/syntactic behaviour. Classes have numeric tags following Levin's taxonomy (Levin 1993). Classes can have subclasses (indicated by hyphenated suffixes). 7,073 class memberships for 4,637 verbs indicate multi-class participation common.

**Key relationships:**
- `vn_classes` ← FK ← `vn_members` (many-to-many with vn_words)
- `vn_classes` ← FK ← `vn_roles` (classes define thematic roles)
- `vn_classes` ← FK ← `vn_classes_frames` (classes have syntactic frames)

**Coverage:** Top classes have 100-300 members (e.g., other_cos-45.4: 296 members, amuse-31.1: 246 members). Long tail of specialized classes. Comprehensive coverage of English verbs.

### 2. Verb Members & WordNet Linkage

**Summary:** 4,637 verbs in `vn_words` linked to OEWN `words` table. 7,073 memberships in `vn_members` map verbs to classes. 9,827 sense-level mappings in `vn_members_senses` link VerbNet classes to specific WordNet synsets with quality scores (0.0-1.0 confidence).

**Key relationships:**
- `vn_words` → FK → `words` (OEWN integration)
- `vn_members` joins `vn_words` ↔ `vn_classes`
- `vn_members_senses` links (classid, vnwordid) to WordNet (wordid, synsetid, sensekey) with quality score

**Coverage:** 9,827 sense mappings for 4,637 verbs ≈ 2.1 senses per verb. Quality field enables filtering low-confidence mappings. Good WordNet integration.

### 3. Thematic Roles

**Summary:** 1,780 role instances in `vn_roles` define participant structure for verb classes using 39 role types (Agent, Patient, Theme, Instrument, etc.). Roles have optional selectional restrictions (81 restriction types in `vn_restrtypes`, 103 restriction instances in `vn_restrs`).

**Key relationships:**
- `vn_roles` → FK → `vn_classes`, `vn_roletypes`, `vn_restrs`
- `vn_roletypes` defines 39 standard role labels
- `vn_restrs` encodes semantic constraints (e.g., [+animate], [+concrete])

**Coverage:** 1,780 roles / 609 classes ≈ 2.9 roles per class. Selectional restrictions present for subset (103 instances). Standard thematic role inventory.

### 4. Syntactic Frames

**Summary:** 1,539 syntactic frames in `vn_frames` define surface realizations of verb classes (e.g., "NP V NP PP", "NP V S"). Each frame has syntax (806 unique patterns in `vn_syntaxes`), semantics (867 representations in `vn_semantics`), and optional examples (1,600 frame-example links). Frame names (348) and subnames (450) provide human-readable labels.

**Key relationships:**
- `vn_frames` → FK → `vn_framenames`, `vn_framesubnames`, `vn_syntaxes`, `vn_semantics`
- `vn_frames` ← FK ← `vn_classes_frames` (classes have multiple frames)
- `vn_frames` ← FK ← `vn_frames_examples` (frames illustrated by examples)

**Coverage:** 2,435 class-frame associations, 1,600 frame-example links. Rich syntactic documentation. 1,539 frames / 609 classes ≈ 2.5 frames per class.

### 5. Semantic Representations

**Summary:** 867 semantic representations in `vn_semantics` use predicate logic to express meaning (e.g., "motion(during(E), Theme)", "cause(Agent, E)"). 163 predicates in `vn_predicates` define semantic primitives. 2,845 predicate-semantics links decompose representations.

**Key relationships:**
- `vn_semantics` ← FK ← `vn_frames` (each frame has semantic representation)
- `vn_predicates` ← FK ← `vn_predicates_semantics` → FK → `vn_semantics`

**Coverage:** Formal semantic representations for all frames. Predicate decomposition enables reasoning about verb meaning.

### 6. Usage Examples

**Summary:** 1,599 usage examples in `vn_examples` illustrate verb usage. 1,600 frame-example links in `vn_frames_examples` associate examples with frames. Examples show verbs in context with typical argument structures.

**Key relationships:**
- `vn_examples` ← FK ← `vn_frames_examples` → FK → `vn_frames`

**Coverage:** 1,599 examples / 4,637 verbs ≈ 34% have examples. Frame-level (not verb-level) examples.

### 7. Groupings

**Summary:** 3,219 groupings in `vn_groupings` organize verbs within classes. 4,217 member-grouping links in `vn_members_groupings`. Purpose unclear from schema - possibly subclass organization or syntactic variants.

**Key relationships:**
- `vn_groupings` ← FK ← `vn_members_groupings` joins with `vn_members`

**Coverage:** 4,217 links for 7,073 members ≈ 60% have groupings. Structure suggests internal organization within classes.

---

## Quality Assessment

### Completeness

**Metrics:**
- Verb coverage: 4,637 verbs (comprehensive for English verbs)
- Class structure: 609 classes (based on Levin 1993 taxonomy)
- WordNet linkage: 9,827 sense mappings (quality-scored)
- Syntactic documentation: 1,539 frames, 806 syntax patterns
- Semantic documentation: 867 semantic representations, 163 predicates
- Examples: 1,599 (34% of verbs)
- Thematic roles: 1,780 roles, 39 types
- Selectional restrictions: 103 instances (sparse but targeted)

**Systematic Gaps:**
- Examples sparse (34% coverage)
- Groupings purpose undocumented (schema lacks comments)
- Verb-centric: no noun/adjective coverage

**Assessment:** Complete for verbs. High-quality linguistic resource. **Gap for Metaforge: no noun/adjective data.**

### Correctness

**Sample Validation:**
Checked 5 random verb-class mappings:
1. "fizz" → entity_specific_modes_being-47.2 (sound emission) ✓ Correct
2. "cope" → cope-83-1-1 (handling situations) ✓ Correct
3. "carbonize" → other_cos-45.4 (change of state) ✓ Correct
4. "walk over" → subjugate-42.3 (dominate) ✓ Correct metaphorical usage
5. "dong" → sound_emission-43.2 ✓ Correct

Role types (Agent, Patient, Theme, Beneficiary, etc.) standard thematic role inventory from linguistic theory. No errors observed.

**Assessment:** High correctness. Academically curated resource. No accuracy concerns.

### Currency

**Last Updated:** 3.4 (version)
**Source Maintenance:** University of Colorado (Martha Palmer lab)
**Update Frequency:** Periodic releases (3.0 → 3.1 → 3.2 → 3.3 → 3.4)
**Upstream:** http://verbs.colorado.edu/~mpalmer/projects/verbnet.html

**Assessment:** Mature resource (15+ years development). Version 3.4 recent. Active research community. **Currency adequate.**

### Project Fit

**Alignment with Metaforge Goals:**

1. **Figurative Language Discovery:**
   - ✓ **Direct support** - Metaphor Forge design explicitly includes verb metaphors ("illuminate.v.01", "whisper.v.01")
   - ✓ **Behavioral properties** - Semantic classes group verbs by shared behavior (motion, causation, communication), exactly matching property extraction needs
   - ✓ **Thematic roles** - Agent/Patient/Theme structure informs metaphor quality (e.g., "ideas flee" works because ideas can be Theme of motion verbs)
   - ✓ **Cross-domain mapping** - VerbNet classes enable finding verbs with similar behavior patterns across domains

2. **Surprise Potential Calculations:**
   - ✓ **Class distance** - Verbs from distant classes (sound_emission vs cognition) create high surprise
   - ✓ **Role violations** - Thematic role mismatches increase surprise ("ideas flee" - abstract Theme with motion verb)
   - ✓ **Semantic predicates** - 163 semantic primitives (motion, contact, cause) provide formal distance metrics

3. **Age-Appropriate Content:**
   - ✓ Academic resource, formal examples
   - ✓ Examples are clear, educational (1,599 usage samples)
   - ⚠ No explicit age ratings or content warnings

4. **Middle Grades Learning:**
   - ✓ Verb examples contextualize action metaphors
   - ✓ Class-based organization helps students understand verb meaning patterns
   - ⚠ Technical linguistic terminology (thematic roles) would need simplification for student-facing features

**Project Fit:** **MEDIUM-HIGH** - VerbNet directly supports verb metaphor extraction per design spec. Semantic classes and thematic roles align with property-based matching. **Recommended for MVP** with selective integration (classes, roles, examples; skip syntactic frames).

---

## Metaforge Relevance

### Replace/Improve Current LLM Enrichment?

**Current sch.v1 enrichment:** Extracts behavioral properties for synsets. Design includes verbs (illuminate.v.01, whisper.v.01) but sch.v1 pilot enriched only 1,005 synsets without POS-specific handling.

**VerbNet contribution:**
- ✓ **Semantic classes** provide pre-existing behavioral groupings (sound_emission, motion, causation) - exactly what LLM extracts
- ✓ **Semantic predicates** (163 types) formalize verb behavior: motion(Theme), cause(Agent, Event), contact(Agent, Patient)
- ✓ **Thematic roles** show argument structure: which roles required/optional for each verb class
- ✓ **Usage examples** (1,599) demonstrate verbs in context for few-shot prompts
- ✓ **Could reduce LLM load:** Use VerbNet classes as input to LLM, focus LLM on domain-specific properties not captured by formal semantics

**Recommendation:** **Use VerbNet to inform verb enrichment.** Pass VerbNet class + semantic predicates to LLM as structured input. Focus LLM on extracting properties that transcend VerbNet's formal semantics (e.g., metaphorical associations, connotations). Example: VerbNet knows "whisper" is communication, LLM extracts "intimate", "secretive", "requires_closeness".

### Improve Surprise Potential Calculations?

**YES - Direct applicability for verb metaphors:**

1. **Verb Class Distance:** Measure semantic distance between verb classes
   - Same class (cut/sever in separate-23.1) = low surprise, high coherence
   - Different classes (whisper/illuminate: communication vs light_emission) = high surprise
   - Class hierarchy provides graduated distance (subclasses closer than cross-hierarchy)

2. **Thematic Role Violations:** Identify unexpected argument structures
   - "ideas flee" - abstract noun (Idea) as Theme of motion verb = surprise (typically concrete Themes)
   - Selectional restrictions (81 types) define expected argument semantics ([+animate], [+concrete])
   - Metaphor often violates selectional restrictions productively

3. **Semantic Predicate Mismatch:** Formal semantics provide distance metric
   - Physical predicates (motion, contact) applied to abstract domains = metaphorical
   - 163 predicates organized by semantic type enable systematic distance calculation

4. **Cross-Domain Mapping:** Verb classes inherently domain-associated
   - sound_emission verbs (fizz, dong, whisper) with cognition/emotion targets = high surprise
   - Change-of-state verbs (carbonize, freeze) with social/emotional targets = metaphorical

**Recommendation:** **Integrate VerbNet class distance into sch.v2 surprise scoring.** Combine with GloVe embeddings and frequency ratios for comprehensive surprise metric. VerbNet provides explicit semantic structure complementing distributional embeddings.

### Age-Appropriate Filtering?

**Minimal value:**
- ✓ Examples are formal, academic (safe for middle grades)
- ✗ No age ratings, readability scores, or content warnings
- ✗ Selectional restrictions are semantic ([+animate]), not content-based

**Recommendation:** **No value for MVP filtering.** VerbNet does not address age-appropriateness.

### Seed LLM Few-Shot Prompts?

**YES - High value for verb enrichment:**

1. **Semantic Class Context:** Provide LLM with VerbNet class membership
   - Input: "whisper.v.01 | VerbNet class: manner_speaking-37.3 | semantic predicates: [communicate(Agent, Topic, Recipient), manner(quiet)]"
   - Guides LLM toward behavior-focused properties rather than physical-only attributes

2. **Usage Examples:** 1,599 examples demonstrate verbs in typical contexts
   - Shows argument structure patterns (who does what to whom)
   - Contextualizes abstract verbs (harder to define than concrete nouns)

3. **Thematic Role Templates:** Structure few-shot examples around roles
   - Example: "illuminate.v.01 (Agent illuminates Theme with Instrument) → properties: [reveals_hidden_things, enables_seeing, requires_source]"
   - Shows LLM how verb structure relates to extractable properties

4. **Semantic Primitives as Anchors:** Use predicates to ground property extraction
   - "motion verbs share: [changes_location, has_source_and_destination, can_be_fast_or_slow]"
   - Provides consistency across verbs in same class

**Implementation Strategy:**
- Enhance sch.v2 enrichment prompt to include VerbNet class + predicates for verbs
- Add few-shot examples showing verb class → property mapping
- Use VerbNet examples to validate LLM output (does extracted property align with verb class semantics?)

**Recommendation:** **Integrate VerbNet data into verb enrichment prompts.** Reduces hallucination risk by grounding LLM in formal semantics while preserving flexibility for metaphorical properties.

---

## Licensing & Provenance

### License

**VerbNet License:** Custom Academic License (freely available for research/education)
**Source:** http://verbs.colorado.edu/~mpalmer/projects/verbnet.html
**MIT Compatible:** ✓ YES (academic use, non-commercial friendly, attribution required)
**Requirements:** Citation required

**Compliance:** Metaforge can use VerbNet under MIT license with proper citation. No restrictions for educational app.

### Citation

**Primary Citation:**
> Karin Kipper, Anna Korhonen, Neville Ryant, Martha Palmer. *A Large-scale Classification of English Verbs*. Language Resources and Evaluation Journal, 42(1), pp. 21-40, Springer Netherland, 2008.

**Additional:**
> Karin Kipper Schuler, Anna Korhonen, Susan W. Brown. *VerbNet overview, extensions, mappings and apps*. Tutorial, NAACL-HLT 2009, Boulder, Colorado.

### Known Issues

**From sources table:** None documented.

**From research community:**
- Known issue: Some verbs have multiple classes with overlapping meanings (granularity debates)
- Minor gaps in low-frequency verb coverage

**Assessment:** No blocking issues. Mature, stable resource.

### Data Grain

**Grain:** Sense-level (via WordNet linkage) + Class-level

**Explanation:** VerbNet operates at two granularities:
1. **Class-level:** Verbs grouped by semantic/syntactic behaviour (609 classes)
2. **Sense-level:** Classes linked to specific WordNet synsets (9,827 mappings with quality scores)

This dual grain enables both coarse semantic grouping and fine-grained sense disambiguation.

---

## Recommendations for sch.v2

### Integration Strategy

**MVP - Selective Integration:**
- **Decision: INTEGRATE VerbNet selectively for verb metaphor support**
- Rationale: Design explicitly includes verb metaphors (illuminate.v.01, whisper.v.01). VerbNet provides semantic structure that reduces LLM hallucination and improves property quality.

**Import Priority:**

1. **CORE (High Value):**
   - `vn_classes` - Semantic verb classes (609 classes)
   - `vn_members` + `vn_members_senses` - Verb-class mappings with WordNet links (9,827 sense mappings)
   - `vn_words` - Verb vocabulary linked to OEWN
   - `vn_examples` + `vn_frames_examples` - Usage examples (1,599)

2. **VALUABLE (Medium Value):**
   - `vn_roles` + `vn_roletypes` - Thematic role structure (1,780 roles, 39 types)
   - `vn_restrs` + `vn_restrtypes` - Selectional restrictions (103 instances, 81 types)
   - `vn_semantics` + `vn_predicates` - Semantic representations (867, 163 predicates)

3. **SKIP (Low MVP Value):**
   - `vn_frames`, `vn_syntaxes`, `vn_framenames`, `vn_framesubnames` - Syntactic frame apparatus (1,539 frames) - too detailed for metaphor extraction
   - `vn_groupings` - Internal organization structure (purpose unclear)
   - `vn_classes_frames` - Class-frame mappings (not needed without frame details)

**Rationale:** Import semantic structure (classes, roles, predicates) to inform LLM enrichment. Skip syntactic detail (frame patterns) - overkill for behavioral property extraction.

### Schema Extensions for sch.v2

**Proposed additions:**

1. **verb_classes** table (from vn_classes):
   - classid, class_name, class_tag
   - Simplified from VerbNet structure, core semantic grouping

2. **verb_class_members** table (from vn_members + vn_members_senses):
   - Link verbs to classes with WordNet sense mapping
   - Include quality score for confidence filtering
   - FK to words, synsets, verb_classes

3. **verb_semantics** table (from vn_semantics + vn_predicates):
   - Store semantic primitives for each class
   - Simplified representation: just predicate names, not full logic
   - Used as input to LLM enrichment prompts

4. **verb_roles** table (optional, from vn_roles + vn_roletypes):
   - Store thematic role structure
   - Could inform future features (argument structure analysis)
   - Lower priority for MVP

**Integration with existing sch.v2:**
- Link `verb_class_members` to OEWN `senses` table via WordNet sense mappings
- Use verb_classes + verb_semantics as input to synset enrichment for verbs
- Extend surprise calculation to include verb class distance

### Query Patterns for sch.v2

**Optimize for:**

1. **Verb lookup with class context:**
   ```sql
   lemma → words → senses → verb_class_members → verb_classes → semantics
   ```
   Purpose: Get semantic class and predicates for verb enrichment input

2. **Class-based verb discovery:**
   ```sql
   verb_class → verb_class_members → words
   ```
   Purpose: Find verbs with similar behavioral semantics

3. **Surprise calculation - verb class distance:**
   ```sql
   (verb1_synsetid → verb_class, verb2_synsetid → verb_class) → class_distance
   ```
   Purpose: Measure semantic distance between verb metaphor candidates

4. **Property intersection with class constraints:**
   ```sql
   property + verb_class → synsets with property in class
   ```
   Purpose: Metaphor Forge filtering by semantic class

**Indexes needed:**
- `verb_class_members(wordid, classid)` - Verb lookup
- `verb_class_members(synsetid)` - Synset to class mapping
- `verb_classes(classid)` - Class details
- `verb_semantics(classid)` - Semantic predicate lookup

---

## Open Questions

1. **Enrichment Strategy:** Should we enrich verbs at synset-level (current sch.v1) or class-level (leverage VerbNet's grouping)? Class-level would reduce API costs (609 classes vs thousands of verb synsets) but lose sense-specific nuance.

2. **Class Granularity:** VerbNet has 609 classes with hierarchical structure. Should sch.v2 preserve full hierarchy or collapse to top-level classes for simplicity?

3. **Semantic Predicate Usage:** Should we use VerbNet's formal semantic predicates (motion(Theme), cause(Agent, Event)) directly in surprise calculations, or just use them to inform LLM property extraction?

4. **Thematic Role Display:** Should Metaphor Forge expose thematic role information to students (educational value) or keep it behind the scenes (complexity management)?

5. **Cross-Dataset Integration:** VerbNet links to PropBank (via SemLink) and FrameNet (via PredicateMatrix). Should we integrate these mappings for richer verb semantics, or is VerbNet alone sufficient for MVP?

---

## Conclusion

VerbNet 3.4 is **high-quality and MEDIUM-HIGH relevance** for Metaforge MVP. Provides comprehensive verb semantics (4,637 verbs, 609 classes, thematic roles, semantic predicates) that directly support the design's explicit inclusion of verb metaphors (illuminate.v.01, whisper.v.01). Semantic classes group verbs by behavior—exactly what property extraction needs. Quality is excellent, license compatible, currency adequate. **Recommendation: INTEGRATE selectively for MVP. Import verb classes, class memberships, WordNet links, and semantic primitives. Skip syntactic frame details (overkill for metaphor extraction).**

**Decision Impact:**
- **Supports design requirements:** Enables verb metaphor extraction per metaphor-forge.md spec
- **Reduces LLM hallucination:** Grounds verb enrichment in formal semantic classes and predicates
- **Improves surprise calculations:** Adds verb class distance metric to complement GloVe embeddings
- **Moderate complexity:** Import 8 core tables (skip 12 syntactic detail tables), adds ~15k rows to sch.v2
- **API cost reduction potential:** Could enrich at class level (609 classes) vs synset level (thousands)

**Trade-offs:**
- **PRO:** Formal semantic structure improves enrichment quality and consistency
- **PRO:** Pre-existing verb groupings align perfectly with behavioral property extraction
- **CON:** Adds complexity to data pipeline (8 additional tables, WordNet sense mapping)
- **CON:** Requires POS-aware enrichment strategy (verbs handled differently from nouns/adjectives)

**Next Steps:**
1. Assess PropBank (verb argument structure, complements VerbNet with corpus examples)
2. Assess FrameNet (frame semantics, includes verbs but also nouns/adjectives - high potential)
3. Design sch.v2 enrichment strategy: class-level vs synset-level for verbs
4. Prototype verb class distance metric for surprise calculations
