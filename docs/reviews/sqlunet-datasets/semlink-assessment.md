# SemLink Dataset Assessment

**Date:** 2026-01-30
**Dataset:** SemLink 2.0 (VerbNet-PropBank mappings)
**Source:** sqlunet_master.db (2 tables, `sl_*` prefix)

---

## 1. Schema Analysis

### Core Tables & Relationships

```
sl_pbrolesets_vnclasses (5,591)
├── pbrolesetid → pb_rolesets.rolesetid
├── vnclassid → vn_classes.classid
├── pbroleset (e.g., "abandon.01")
└── vnclass (e.g., "51.2")

sl_pbroles_vnroles (12,558)
├── pbrolesetid → pb_rolesets.rolesetid
├── pbroleid → pb_roles.roleid
├── vnclassid → vn_classes.classid
├── vnroleid → vn_roles.roleid
├── vnroletypeid → vn_roletypes.roletypeid
├── pbroleset (e.g., "abandon.01")
├── pbarg (e.g., "0", "1", "2" - PropBank argument number)
├── vnclass (e.g., "51.2")
└── vntheta (e.g., "Agent", "Theme", "Patient")
```

### Mapping Coverage

- **PropBank Rolesets Mapped:** 4,450 (out of 11,000 total = 40%)
- **VerbNet Classes Mapped:** 435 (out of 609 total = 71%)
- **Role Mappings:** 12,558 (PropBank arg → VerbNet theta role)

---

## 2. Quality Assessment

### Coverage

✅ **Strengths:**
- **Comprehensive VerbNet Coverage:** 71% of VerbNet classes (435/609) are linked to PropBank
- **Detailed Role Mappings:** 12,558 fine-grained mappings (PropBank arg0/1/2 → VerbNet Agent/Theme/Patient)
- **High-Quality Links:** Manually curated mappings between two major verb resources

### Quality Indicators

**Sample Mappings:**

| PropBank Roleset | VerbNet Class | Arg Mappings |
|------------------|---------------|--------------|
| abandon.01 | 51.2 | arg0 → Theme |
| abase.01 | 45.4 | arg0 → Agent, arg1 → Patient, arg2 → Instrument |
| FedEx.01 | 11.1-1 | arg0 → Agent, arg1 → Theme, arg2 → Destination |

✅ **Mapping quality is high** - theta roles are semantically sensible.

⚠️ **Limitations:**
- **PropBank-only:** No VerbNet-FrameNet or PropBank-FrameNet mappings in sqlunet
- **Partial Coverage:** Only 40% of PropBank rolesets mapped (4,450/11,000)
- **Verb-only:** SemLink is specific to verbs (no noun/adjective cross-resource linking)

---

## 3. Metaforge Relevance

### Use Cases

#### 1. Bridge PropBank Examples to VerbNet Classes (MEDIUM VALUE - DEFERRED)

**Scenario:** We want to use PropBank's 23k corpus examples to enrich VerbNet semantic classes.

**Workflow:**
1. Look up PropBank roleset → VerbNet class via SemLink
2. Use PropBank examples as additional training data for VerbNet class semantics
3. Enrich LLM prompts with both VerbNet definitions AND PropBank corpus examples

**Verdict:** **Deferred with PropBank** - We decided to skip PropBank for MVP due to age-filtering burden (23k corpus examples). SemLink's primary value is bridging PropBank→VerbNet, so without PropBank integration, SemLink has limited utility.

#### 2. Validate VerbNet Role Consistency (LOW VALUE)

**Scenario:** Use SemLink mappings to validate that VerbNet's theta roles are consistently applied across classes.

**Example:** Check that "Agent" roles in VerbNet align with PropBank arg0 patterns.

**Verdict:** **Not needed** - VerbNet's roles are already well-structured. Validation is a research task, not an MVP requirement.

#### 3. Cross-Resource Lookup (LOW VALUE)

**Scenario:** User searches for a PropBank roleset → show corresponding VerbNet class.

**Verdict:** **Not needed** - Metaforge's UI is synset-centric (OEWN-based), not PropBank-centric. No PropBank search feature planned.

---

## 4. Integration Feasibility

### Complexity Assessment

**Schema Complexity: LOW**

- Only 2 tables with straightforward foreign keys
- Minimal integration cost if needed

**Data Volume:**

- 5,591 roleset-class mappings (lightweight)
- 12,558 role mappings (manageable)

### Proposed Integration Strategy

#### Option A: Defer with PropBank (Recommended)

**Rationale:**
- SemLink's primary value is bridging PropBank→VerbNet
- We deferred PropBank for MVP (age-filtering burden)
- Without PropBank, SemLink has no immediate use case

**Decision:** **SKIP SemLink for MVP**, revisit in Post-MVP if PropBank is integrated.

#### Option B: Lightweight Integration (Low Priority)

**If PropBank is added Post-MVP:**

Import SemLink to enable:
1. PropBank roleset → VerbNet class lookup
2. Use PropBank's 23k examples to augment VerbNet's 1.6k examples
3. Enrich LLM prompts with cross-resource context

**Cost:** Minimal schema complexity (2 tables)

---

## 5. Comparison with Other Datasets

| Dataset | Purpose | SemLink Relevance |
|---------|---------|-------------------|
| **OEWN** | Word-sense-definition core | ❌ No overlap (OEWN ≠ PropBank) |
| **VerbNet** | Verb semantic classes | ✅ SemLink bridges PropBank→VerbNet |
| **PropBank** | Verb corpus examples | ✅ SemLink required for integration |
| **FrameNet** | Frame semantics | ⚠️ No FrameNet mappings in sqlunet |

**Key Insight:** SemLink is **dependent on PropBank integration**. Without PropBank, SemLink has no value.

---

## 6. Integration Recommendation

### VERDICT: **LOW Relevance - Defer with PropBank**

**Rationale:**

❌ **Dependent on PropBank:**
- SemLink's primary use case is bridging PropBank examples to VerbNet classes
- We deferred PropBank for MVP (age-filtering burden on 23k examples)
- Without PropBank, SemLink has no immediate application

✅ **Low Integration Cost:**
- Only 2 tables, 18k total rows
- If PropBank is added Post-MVP, SemLink integration is trivial

⚠️ **No FrameNet Mappings:**
- sqlunet's SemLink only covers VerbNet-PropBank
- No VerbNet-FrameNet or PropBank-FrameNet links (despite SemLink 2.0 supporting these)

### Recommended Strategy: **Defer to Post-MVP**

**For MVP (sch.v2):**
- **SKIP SemLink** - no PropBank to bridge
- Focus on OEWN + VerbNet selective integration

**For Post-MVP:**
- **Revisit if PropBank is integrated** - SemLink enables using PropBank's 23k examples to enrich VerbNet classes
- Integration cost is minimal (2 tables, straightforward schema)

---

## 7. Open Questions

1. **FrameNet Mappings:** SemLink 2.0 includes VerbNet-FrameNet mappings. Why are they missing from sqlunet? Would they be valuable for grounding FrameNet frames to VerbNet classes?

2. **PropBank Revisit:** If Post-MVP testing shows need for more verb examples, should we:
   - Integrate PropBank + SemLink together?
   - Use SemLink to selectively import only PropBank examples for VerbNet classes (avoiding full PropBank integration)?

3. **Example Augmentation:** Could SemLink enable using PropBank examples WITHOUT full PropBank schema integration? (e.g., just import examples as text, use SemLink to tag them with VerbNet classes)

---

## 8. Decision Log

| Decision | Rationale | Date |
|----------|-----------|------|
| **Defer SemLink to Post-MVP** | Dependent on PropBank integration; no immediate use case without PropBank | 2026-01-30 |
| **Low integration cost** | Only 2 tables, 18k rows - trivial to add later if needed | 2026-01-30 |
| **Revisit with PropBank** | If PropBank added Post-MVP, SemLink enables example augmentation for VerbNet classes | 2026-01-30 |

---

## Next Steps

1. ✅ Complete Phase 1 dataset assessments (PredicateMatrix, SyntagNet remaining)
2. Document SemLink as "deferred with PropBank" in Phase 1 summary
3. Note: SemLink is quick-win integration if PropBank proves valuable Post-MVP
