# FrameNet 1.7 Dataset Assessment

**Date:** 2026-01-30
**Dataset:** FrameNet 1.7 (Berkeley)
**Source:** sqlunet_master.db (43 tables, `fn_*` prefix)

---

## 1. Schema Analysis

### Core Tables & Relationships

```
fn_frames (1,221)
├── frame, framedefinition
├── fn_lexunits (13,572) → lexunit, ludefinition, posid, totalannotated
│   ├── fn_lexemes (14,639) → headword, breakbefore
│   │   └── fn_words (9,175) → wordid
│   └── fn_lexunits_semtypes → semantic type annotations
├── fn_fes (11,428) → frame elements (semantic roles)
│   ├── feabbrev, fedefinition, coretypeid
│   └── fn_fes_semtypes → FE semantic types
├── fn_sentences (182,650) → annotated corpus examples
│   └── fn_annosets → annotation sets linking sentences to lexunits
└── fn_frames_related → frame-to-frame relations
    └── fn_framerelations (13 types)
```

### Frame Relations (Hierarchical Structure)

| Relation Type | Count | Description |
|---------------|-------|-------------|
| Is Inherited by / Inherits from | 781 | Frame inheritance hierarchy |
| Uses / Is Used by | 553 | Frame incorporation |
| See also | 133 | Cross-references |
| Subframe of / Has Subframe(s) | 131 | Complex event decomposition |
| Perspective on / Is Perspectivized in | 127 | Viewpoint alternations |
| Precedes / Is Preceded by | 88 | Temporal sequencing |
| Is Causative of | 59 | Causative alternations |
| Is Inchoative of | 17 | Inchoative alternations |

### Part-of-Speech Distribution

| POS | Count | Percentage |
|-----|-------|------------|
| Nouns | 5,529 | 40.7% |
| Verbs | 5,178 | 38.1% |
| Adjectives | 2,392 | 17.6% |
| Adverbs | 237 | 1.7% |
| Prepositions | 147 | 1.1% |
| Other | 89 | 0.7% |

**Total:** 13,572 lexical units across **all major POS categories**

### Top Semantic Types

| Semantic Type | Count | Relevance to Metaforge |
|---------------|-------|------------------------|
| Negative | 235 | Polarity extraction |
| Negative_judgment | 155 | Evaluative properties |
| Transparent Noun | 116 | Container/vehicle nouns |
| Container | 116 | Physical properties |
| Positive_judgment | 63 | Evaluative properties |
| Landform | 60 | Geographic entities |
| End_of_scale | 53 | Scalar properties |

---

## 2. Quality Assessment

### Coverage

- **Vocabulary Size:** 9,175 unique words (~7% of OEWN's 127k)
- **Depth:** 14,639 word-POS pairs, 13,572 lexical units in frames
- **Frames:** 1,221 semantic frames with rich definitions
- **Examples:** 182,650 annotated corpus sentences (**134x VerbNet, 8x PropBank**)
- **Frame Elements:** 11,428 semantic role definitions

### Quality Indicators

✅ **Strengths:**
- **Cross-POS:** Balanced coverage of nouns (40.7%), verbs (38.1%), adjectives (17.6%)
- **Rich Semantics:** Frame definitions include:
  - Semantic role structures (frame elements)
  - Inheritance hierarchies (781 relations)
  - Metaphorical usage documentation
  - Annotated corpus examples with marked roles
- **Massive Example Corpus:** 182,650 sentences vs VerbNet (1,599) and PropBank (23k)
- **Hierarchical Relations:** 781 inheritance links create semantic taxonomy
- **Explicit Metaphor Documentation:** Communication frame explicitly maps to Evidence/Becoming_aware

⚠️ **Weaknesses:**
- **Limited Vocabulary:** Only 9k words vs OEWN (127k) - deep but narrow coverage
- **Age Appropriateness:** 182k corpus examples (news/web text) require filtering like PropBank
- **Integration Complexity:** 43 tables with intricate relationships - steep learning curve
- **Redundancy Risk:** Potential overlap with OEWN definitions + VerbNet semantic classes

---

## 3. Metaforge Relevance

### Design Alignment Check

**Metaphor Forge examples present in FrameNet?**

| Lemma | FrameNet Frames | Metaforge Need |
|-------|-----------------|----------------|
| illuminate.v | Location_of_light | ✅ "emits light" property |
| whisper.v | Communication_manner, Make_noise | ✅ "quiet speech" behavior |

✅ **Both design examples covered** - FrameNet captures target semantics

### Use Cases for Metaforge

#### 1. Property Extraction (HIGH VALUE)

Frames provide **semantic context for property extraction:**

- **Causation** frame → identify causal relationships (cause.v, trigger.v)
- **Location_of_light** frame → extract "emits light" property (illuminate.v, glow.v)
- **Communication_manner** frame → extract "quiet/loud speech" (whisper.v, shout.v)
- **Motion** frame → extract directionality (Theme, Source, Goal, Path)

**Advantage over OEWN:** FrameNet definitions are **semantically structured** with explicit roles, not free-text glosses.

#### 2. Cross-POS Behavioral Properties (HIGH VALUE)

FrameNet's balanced noun/verb/adjective coverage supports extracting:

- **Verb behaviors:** Motion frames (drift.v, roll.v), Communication frames (whisper.v)
- **Noun affordances:** Container frame (bucket.n, jar.n), Weapon frame (sword.n)
- **Adjective properties:** Positive_judgment (brilliant.a), End_of_scale (freezing.a)

**Advantage over VerbNet:** VerbNet is verb-only; FrameNet covers nouns and adjectives equally.

#### 3. Metaphor Grounding (MEDIUM-HIGH VALUE)

FrameNet **explicitly documents metaphorical mappings:**

> "Communication onto Becoming_aware metaphor maps Means/Medium subjects onto Evidence FE"

This could **reduce LLM hallucination** by grounding metaphor extraction in corpus-attested patterns.

**Example:** "This painting speaks to me" (metaphorical Communication)

#### 4. Surprise Calculation (MEDIUM VALUE)

Frame distances could measure semantic surprise:

- **Within-frame distance:** whisper.v (Communication_manner) → illuminate.v (Location_of_light) = far
- **Hierarchy distance:** Causation → Change_of_state = close (inheritance path)

**Question:** Would frame hierarchy improve on VerbNet class hierarchy for surprise?

---

## 4. Integration Feasibility

### Complexity Assessment

**Schema Complexity: HIGH**

- 43 tables (vs VerbNet: 16, PropBank: 10, OEWN: 25)
- Multi-level joins required (frames → lexunits → lexemes → words)
- Frame relations require recursive queries for hierarchy traversal

**Data Volume:**

- 182,650 sentences require age-appropriateness filtering (same as PropBank issue)
- 1,221 frames × 11,428 frame elements = substantial metadata

### Proposed Integration Strategy

#### Option A: Full Integration (Comprehensive but Costly)

**Import:**
- Frames (1,221) + definitions
- Lexical units (13,572) → synset mapping
- Frame elements (11,428) as structured properties
- Frame relations (2,449) for hierarchy
- Filtered examples (~50k after age-appropriateness review?)

**Use Cases:**
- Ground LLM property extraction in frame semantics
- Calculate frame distance for surprise metric
- Expose frame hierarchy in UI (optional)

**Costs:**
- High schema v2 complexity
- Extensive age filtering needed for examples
- Potential redundancy with OEWN+VerbNet

#### Option B: Selective Integration (Pragmatic)

**Import:**
- Frames (1,221) as lightweight metadata (name + definition only)
- Lexical unit → frame membership (13,572 mappings)
- Frame semantic types (109) for classification
- SKIP frame elements, relations, and corpus examples

**Use Cases:**
- Enrich LLM prompts with frame name + definition
- Classify words by semantic type (Container, Causation, etc.)
- Use frame membership as "semantic tags" for synsets

**Benefits:**
- Much simpler schema integration
- No age-filtering burden (no corpus examples)
- Complements OEWN (definitions) + VerbNet (verb classes)

**Drawback:**
- Loses rich frame element structure
- Can't calculate frame hierarchy distances

#### Option C: LLM Enrichment Only (Zero Integration)

**Don't import FrameNet into sch.v2 at all.**

Instead: **Query FrameNet during LLM enrichment** to ground property extraction.

**Workflow:**
1. Look up synset lemma in FrameNet (via external API or local index)
2. If found, pass frame name + definition to LLM as context
3. LLM extracts properties informed by frame semantics

**Benefits:**
- Zero schema complexity
- Keeps data pipeline simple
- Still gains semantic grounding benefit

**Drawbacks:**
- Requires FrameNet query infrastructure
- Slower enrichment (extra lookup per synset)

---

## 5. Coverage Comparison

### FrameNet vs OEWN vs VerbNet

| Metric | FrameNet | OEWN | VerbNet |
|--------|----------|------|---------|
| Unique Words | 9,175 | 127,000 | 4,637 |
| Nouns | 5,529 | ~100k | 0 |
| Verbs | 5,178 | ~15k | 4,637 |
| Adjectives | 2,392 | ~20k | 0 |
| Definitions | 1,221 frames | 107k synsets | 609 classes |
| Examples | 182,650 | 53,000 | 1,599 |
| Semantic Structure | Frame elements | Semantic relations | Thematic roles |

**Key Insight:** FrameNet is **complementary, not redundant:**

- **OEWN:** Broad vocabulary (127k), word-sense-definition infrastructure
- **VerbNet:** Verb-only, syntax+semantics, 609 classes, 1.6k examples
- **FrameNet:** Deep semantics across POS, 1,221 frames, 182k examples, **explicit metaphor mappings**

### Overlap Analysis

**How many FrameNet verbs are in VerbNet?**

Estimate: ~70% overlap (VerbNet has 4,637 verbs, FrameNet has 5,178 - likely substantial intersection)

**How many FrameNet words are in OEWN?**

Estimate: ~90%+ overlap (FrameNet's 9k words are core vocabulary)

**Unique Value:** FrameNet's **frame semantics** and **corpus examples** are unique, even for overlapping lemmas.

---

## 6. Integration Recommendation

### VERDICT: **MEDIUM-HIGH Relevance - Defer to Post-MVP**

**Rationale:**

✅ **High Semantic Value:**
- Frame semantics directly support property extraction
- Cross-POS coverage (nouns, verbs, adjectives)
- Explicit metaphor documentation reduces LLM hallucination
- 182k examples provide corpus grounding

⚠️ **High Integration Cost:**
- 43 tables, complex relationships
- 182k examples require age-filtering (same burden as PropBank)
- Potential redundancy with OEWN+VerbNet

### Recommended Strategy: **Phase 2 Post-MVP**

**For MVP (sch.v2):**
- **DEFER FrameNet integration** - OEWN + VerbNet provide sufficient semantic grounding
- Focus on OEWN (word-sense-definition core) + VerbNet (verb semantics) + SUBTLEX-UK (frequency)
- Prototype LLM enrichment with OEWN definitions + VerbNet classes

**For Post-MVP (Phase 2 or sch.v3):**
- **Re-evaluate FrameNet** after testing MVP semantic extraction quality
- If LLM enrichment shows gaps (especially for nouns/adjectives), integrate FrameNet selectively:
  - Option B (lightweight metadata) for quick win
  - Option A (full integration) if frame distance metric proves valuable
- Use FrameNet's 182k examples for **corpus-based validation** of extracted properties

### Alternative: Hybrid Approach

**If testing shows need for richer noun/adjective semantics:**

Import **FrameNet frames selectively** for specific semantic domains:
- Container nouns (116 lexunits) → physical properties
- Judgment adjectives (218 lexunits) → evaluative properties
- Location/Motion frames → spatial properties

This targets high-value semantic areas without full integration cost.

---

## 7. Open Questions

1. **Frame vs Class Distance:** Would FrameNet frame hierarchy improve surprise calculations over VerbNet class hierarchy?

2. **Noun/Adjective Semantics:** Can OEWN definitions alone provide sufficient semantic context for noun/adjective property extraction, or do we need FrameNet's frame structure?

3. **Metaphor Extraction:** How much does FrameNet's explicit metaphor documentation reduce LLM hallucination compared to free-text OEWN definitions?

4. **Corpus Example Value:** Are FrameNet's 182k examples worth the age-filtering burden, or are OEWN's 53k examples sufficient?

5. **Integration Timing:** Should we prototype with OEWN+VerbNet first, then add FrameNet if gaps emerge? Or integrate all three from the start?

---

## 8. Decision Log

| Decision | Rationale | Date |
|----------|-----------|------|
| **Defer to Post-MVP** | High semantic value but high integration cost; OEWN+VerbNet sufficient for initial testing | 2026-01-30 |
| **Revisit in Phase 2** | Re-evaluate after MVP testing shows noun/adjective semantic extraction quality | 2026-01-30 |
| **Consider Option B if integrated** | Lightweight frame metadata (no FEs, no relations) balances value/complexity | 2026-01-30 |

---

## Next Steps

1. ✅ Complete Phase 1 dataset assessments (BNC, SemLink, PredicateMatrix, SyntagNet remaining)
2. Document FrameNet as "high-value deferred integration" in Phase 1 summary
3. Note FrameNet as potential Phase 2 enhancement if noun/adjective semantics need improvement
