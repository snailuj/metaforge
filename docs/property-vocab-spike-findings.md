# Property Vocabulary Spike Findings

Design decisions, spike results, and implementation outcomes.

---

## 2k Pilot Results (2026-02-04) - FINAL

**Status:** SUCCESS - Solution 5 validated at scale

### Results

| Metric | 100 Pilot | 2k Pilot |
|--------|-----------|----------|
| Synsets processed | 100 | 2,000 |
| Total properties | 757 | 17,123 |
| Unique properties | 605 | 5,069 |
| Avg properties/synset | 7.6 | 8.56 |

### FastText Embedding Coverage

| Metric | Value |
|--------|-------|
| Properties with embeddings | 5,024 |
| OOV properties | 42 |
| Coverage rate | 99.2% |

### Top Recurring Properties (2k Pilot)

| Property | Count | Property | Count |
|----------|-------|----------|-------|
| functional | 66 | physical | 38 |
| active | 52 | natural | 36 |
| practical | 49 | emotional | 35 |
| dynamic | 42 | complex | 34 |
| intentional | 41 | variable | 33 |

### Key Decision: FrameNet Integration Obviated

The 2k pilot demonstrates that FastText embeddings provide sufficient semantic consistency without FrameNet frame constraints:

1. **99.2% embedding coverage** - Only 42 OOV properties out of 5,069
2. **Semantic similarity works** - Validation tests confirm warm/hot, quiet/silent, fast/rapid cluster correctly (cosine similarity > 0.5)
3. **Property diversity excellent** - Behavioural properties like "flickering", "ephemeral", "cascading" captured

**Decision:** FrameNet integration (Task 3 in original plan) is DEFERRED to post-MVP. The fn_frames, fn_frame_synsets, property_dimensions, and frame_dimensions tables remain empty by design.

---

## Initial Spike Results (2026-02-03)

**Approach tested:** Solution 5 (Two-Pass Enrichment)

### Results

| Metric | Value |
|--------|-------|
| Synsets processed | 100 |
| Total properties | 757 |
| Unique properties | 605 |
| Avg properties/synset | 7.6 |
| Overlap rate | ~20% |

### Top Recurring Properties

| Property | Count |
|----------|-------|
| sequential | 6 |
| abstract | 5 |
| flexible | 4 |
| persistent | 4 |
| violent | 4 |
| visual | 4 |
| deliberate | 3 |
| heavy | 3 |
| chemical | 3 |

### Sample Outputs

**supple** (adjective):
`['flexible', 'pliant', 'bendy', 'elastic', 'yielding', 'malleable', 'adaptable', 'smooth']`

**roar** (verb):
`['loud', 'turbulent', 'disorderly', 'chaotic', 'boisterous', 'uncontrolled', 'violent', 'energetic']`

**collapse** (verb):
`['sudden', 'uncontrolled', 'involuntary', 'weakening', 'fading', 'terminal', 'abrupt']`

### Observations

1. **Synonym clusters present:** flexible/pliant/bendy, loud/boisterous, sudden/abrupt
2. **Behavioural properties captured:** Short 1-2 word categorical terms
3. **POS variation observed:** Verbs get action properties, adjectives get quality properties
4. **Interesting properties found:** flickering-style terms present (ephemeral, transformative, etc.)

### Prompt Refinement

Initial prompt produced full sentences (901 unique, 0% overlap). Refined prompt with:
- System role (Linguistic Data Scientist)
- Few-shot examples (candle, whisper, fragile)
- Explicit "1-2 words" constraint

Refinement reduced unique properties to 605 with 20% overlap -- suitable for curation.

### Decision

**PROCEED WITH SOLUTION 5**

Rationale: Spike validates that unconstrained LLM enrichment with refined prompt produces:
- Short, categorical properties
- Sufficient overlap for curation
- Behavioural descriptors (not just categories)

### Next Steps

1. Run full 2k pilot enrichment
2. Manual curation of property vocabulary (~8-10 hours)
3. Re-run enrichment constrained to curated vocabulary

### Alternatives Noted

- **Solution 6:** LLM-generated theoretical vocabulary (viable fallback if curation proves impractical)
- **Hybrid:** Solution 6 seed vocabulary + Solution 5 empirical refinement
