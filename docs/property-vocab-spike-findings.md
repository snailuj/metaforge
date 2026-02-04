# Post-MVP Notes

Design decisions, spike results, and future considerations.

---

## Property Vocabulary Spike Results (2026-02-03)

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
