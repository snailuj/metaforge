# PredicateMatrix Dataset Assessment

**Date:** 2026-01-30
**Dataset:** PredicateMatrix (unified predicate mappings)
**Source:** sqlunet_master.db (6 tables, `pm_*` prefix)

---

## 1. Schema Analysis

### Core Tables & Relationships

```
pm_pms (115,779)  ← Main mapping table
├── pmid (mapping ID)
├── pmroleid → pm_roles.pmroleid
├── word (lemma)
├── sensekey (WordNet sense key)
├── synsetid → OEWN synsets
├── vnclass, vnclassid, vnrole, vnroleid → VerbNet
├── pbroleset, pbrolesetid, pbrole, pbroleid → PropBank
├── fnframe, fnframeid, fnfe, fnfeid, fnlu, fnluid → FrameNet
└── source, wsource (mapping source metadata)

pm_predicates (7,562)
├── predicateid
└── predicate (e.g., "abandon.01", "illuminate.01")

pm_roles (?)
├── pmroleid
├── predicateid → pm_predicates
├── role (e.g., "0", "1", "Agent", "Theme")
└── pos (part of speech)

pm_vn, pm_pb, pm_fn (resource-specific tables)
```

### Coverage Statistics

| Resource | Entries | Percentage | Notes |
|----------|---------|------------|-------|
| WordNet (synsetid) | 104,714 | 90% | 4,625 distinct synsets |
| PropBank (pbrolesetid) | 89,638 | 77% | 7,562 predicates |
| VerbNet (vnclassid) | 83,146 | 72% | ~435 classes |
| FrameNet (fnframeid) | 69,522 | 60% | Incomplete (e.g., illuminate missing) |

**Total Mappings:** 115,779 (predicate-role-resource tuples)
**Unique Words:** 4,571
**Unique Synsets:** 4,625

---

## 2. Quality Assessment

### Coverage

✅ **Comprehensive Cross-Resource Linking:**
- 90% of mappings have WordNet synset links
- 77% link to PropBank
- 72% link to VerbNet
- 60% link to FrameNet

**Example: "abandon"**
- VerbNet: 51.2
- PropBank: abandon.01
- FrameNet: Abandonment, Departing, Quitting_a_place (multiple frames)
- WordNet: synset links present

**Example: "whisper"**
- VerbNet: 37.3, 43.2 (multiple classes)
- PropBank: whisper.01
- FrameNet: Communication_manner, Make_noise
- WordNet: synset links present

### Quality Indicators

✅ **Strengths:**
- **Unified View:** Single table linking WordNet, VerbNet, PropBank, FrameNet
- **Many-to-Many Mappings:** Words can map to multiple frames/classes (e.g., whisper → 2 VerbNet classes, 2 FrameNet frames)
- **Role-Level Granularity:** Maps not just predicates, but specific roles (Agent, Theme, etc.)
- **High WordNet Coverage:** 90% of mappings link to WordNet synsets

⚠️ **Weaknesses:**
- **Verb-Focused:** Only 4,571 words vs OEWN (127k) - heavy verb bias
- **Incomplete FrameNet Links:** "illuminate" has NO FrameNet link despite FrameNet having Location_of_light frame
- **PropBank-Centric Naming:** Uses PropBank rolesets (abandon.01) as canonical predicate IDs
- **Dependent on Deferred Resources:** 77% PropBank, 60% FrameNet - we deferred both for MVP

---

## 3. Metaforge Relevance

### Use Cases

#### 1. Cross-Resource Synset Enrichment (MEDIUM VALUE - BLOCKED)

**Scenario:** Use PredicateMatrix to enrich OEWN synsets with VerbNet/PropBank/FrameNet links.

**Workflow:**
1. Look up synset → PredicateMatrix → get VerbNet class + FrameNet frame
2. Enrich LLM prompts with cross-resource semantic context
3. Use VerbNet class for verb metaphor grounding
4. Use FrameNet frame for property extraction

**Verdict:** **Blocked by deferred integrations** - PredicateMatrix's value depends on:
- VerbNet (✅ integrating selectively for MVP)
- PropBank (❌ deferred for MVP)
- FrameNet (❌ deferred for MVP)

Without PropBank and FrameNet, PredicateMatrix provides limited value beyond what we get from direct VerbNet integration.

#### 2. Validate Resource Consistency (LOW VALUE)

**Scenario:** Use PredicateMatrix to check that VerbNet/PropBank/FrameNet mappings are consistent.

**Verdict:** **Research task, not MVP feature** - validation is useful for data quality, but not a user-facing requirement.

#### 3. "Find Similar Across Resources" (LOW VALUE)

**Scenario:** User searches for a verb → show related verbs across VerbNet/PropBank/FrameNet.

**Verdict:** **Not in design** - Metaforge's MVP focuses on metaphor forging and semantic surprise, not cross-resource exploration.

---

## 4. Integration Feasibility

### Complexity Assessment

**Schema Complexity: MEDIUM-HIGH**

- 6 tables with intricate foreign keys across 4 external resources
- Requires OEWN, VerbNet, PropBank, FrameNet to be fully integrated
- 115k mappings (manageable but non-trivial)

**Data Volume:**

- 115,779 mappings (moderate size)
- But only 4,571 words (3.6% of OEWN vocabulary)

### Proposed Integration Strategy

#### Option A: Full Integration (Blocked Until Post-MVP)

**Prerequisites:**
- ✅ OEWN integrated (MVP)
- ✅ VerbNet integrated (MVP, selective)
- ❌ PropBank integrated (deferred)
- ❌ FrameNet integrated (deferred)

**Verdict:** **Cannot integrate fully until PropBank/FrameNet are added** - 77% of mappings link to PropBank, 60% to FrameNet.

#### Option B: Partial Integration (VerbNet-Only Subset)

**Scenario:** Import only PredicateMatrix entries linking OEWN synsets → VerbNet classes.

**Workflow:**
1. Filter pm_pms for entries with synsetid AND vnclassid
2. Import as `synset_vnclass` bridge table
3. Use to look up VerbNet class for OEWN synsets

**Benefits:**
- Bridges OEWN → VerbNet directly (useful for verb synsets)
- No dependency on PropBank/FrameNet

**Drawbacks:**
- **Redundant with direct VerbNet integration** - VerbNet already links to WordNet via sense keys
- Only 4,625 synsets covered (4% of OEWN's 107k synsets)
- Adds schema complexity for minimal gain

#### Option C: Skip for MVP (Recommended)

**Rationale:**
- PredicateMatrix's value is **cross-resource lookup**, but we deferred PropBank/FrameNet
- VerbNet → WordNet links already exist in VerbNet tables
- Only 4,571 words covered (3.6% of OEWN) - too limited for broad enrichment

**Decision:** **SKIP PredicateMatrix for MVP**, revisit Post-MVP if/when PropBank and FrameNet are integrated.

---

## 5. Comparison with Other Datasets

| Dataset | PredicateMatrix Overlap | Relevance |
|---------|-------------------------|-----------|
| **OEWN** | 4,625 synsets (4% of 107k) | ✅ High synset coverage in PM |
| **VerbNet** | 83,146 mappings (72%) | ✅ High VerbNet coverage |
| **PropBank** | 89,638 mappings (77%) | ❌ PropBank deferred for MVP |
| **FrameNet** | 69,522 mappings (60%) | ❌ FrameNet deferred for MVP |

**Key Insight:** PredicateMatrix is most valuable when **all four resources are integrated**. With PropBank and FrameNet deferred, PM's utility is limited.

---

## 6. Integration Recommendation

### VERDICT: **LOW Relevance - Defer to Post-MVP**

**Rationale:**

❌ **Dependent on Deferred Resources:**
- 77% of mappings link to PropBank (deferred)
- 60% of mappings link to FrameNet (deferred)
- Without PropBank/FrameNet, PredicateMatrix provides minimal value

⚠️ **Limited Coverage:**
- Only 4,571 words (3.6% of OEWN)
- Only 4,625 synsets (4% of OEWN synsets)
- Verb-focused, limited noun/adjective coverage

✅ **Potential Post-MVP Value:**
- If PropBank + FrameNet are integrated, PredicateMatrix enables unified cross-resource lookup
- Could simplify schema by using PM as canonical linking table

### Recommended Strategy: **Defer to Post-MVP**

**For MVP (sch.v2):**
- **SKIP PredicateMatrix** - too dependent on PropBank/FrameNet
- Use direct OEWN → VerbNet links via VerbNet sense keys

**For Post-MVP:**
- **Revisit if PropBank + FrameNet integrated** - PredicateMatrix becomes valuable as unified linking layer
- Could replace individual SemLink tables with single PredicateMatrix lookup
- Integration cost is moderate (6 tables, 115k rows)

---

## 7. Open Questions

1. **FrameNet Completeness:** Why does PredicateMatrix lack FrameNet links for some verbs (e.g., illuminate) that ARE in FrameNet? Data quality issue or version mismatch?

2. **VerbNet Redundancy:** Does PredicateMatrix offer anything beyond VerbNet's existing WordNet sense key links? Or is it purely a convenience layer?

3. **Noun/Adjective Coverage:** PredicateMatrix has only 4,571 words (mostly verbs). Would it help with noun/adjective property extraction, or is it verb-only?

4. **Post-MVP Strategy:** If we integrate FrameNet + PropBank, should we:
   - Use PredicateMatrix as canonical linking table?
   - Or build our own sch.v2 cross-resource links?

---

## 8. Decision Log

| Decision | Rationale | Date |
|----------|-----------|------|
| **Defer PredicateMatrix to Post-MVP** | 77% PropBank links, 60% FrameNet links - both resources deferred for MVP | 2026-01-30 |
| **Limited verb coverage** | Only 4,571 words, 4,625 synsets (3-4% of OEWN) - too narrow for broad enrichment | 2026-01-30 |
| **Revisit with PropBank + FrameNet** | PM becomes valuable unified linking layer if all four resources integrated | 2026-01-30 |

---

## Next Steps

1. ✅ Complete Phase 1 dataset assessments (SyntagNet remaining)
2. Document PredicateMatrix as "deferred with PropBank + FrameNet" in Phase 1 summary
3. Note: PM could simplify Post-MVP schema if all resources integrated
