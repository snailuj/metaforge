# Dual-Prompt Enrichment Strategy — Design

**Date:** 2026-03-06
**Branch:** `feat/steal-shamelessly`
**Depends on:** P2 concreteness gate (merged), P3 discrimination eval (complete)

---

## Problem

The current Variant C enrichment prompt produces vivid, sense-aware properties but has two systematic quality issues:

1. **LLM reporting bias** — physical/sensory traits are under-represented. The LLM favours "interesting" abstract properties over "obvious" physical ones. Volcano gets `magmatic, pyroclastic, geological` instead of `hot, molten, conical`. This starves the concreteness gate and downstream metaphor matching of the grounding signal they need.

2. **Multi-word expression leakage** — despite a "1-2 words maximum" constraint, hyphenated compounds slip through: `dormant-active`, `breach-making`, `lava-formed`, `ground-shaking`. These fail vocabulary snapping and are effectively lost.

**Evidence:** Discrimination metrics are near-random (mean rank_auc=0.537, cross-domain ratio=0.334). The concreteness gate improved MRR by only +0.5% from regression fill — the bottleneck isn't filtering, it's property quality.

---

## Strategy

Two-phase enrichment: a stronger single prompt with post-hoc audit and targeted gap-fill.

```
Phase 1: Full re-enrichment
  v2 prompt (modified) → 10-15 properties per synset
  Single-word only, min 4 physical for nouns
                                ↓
Phase 2: Post-hoc audit
  Classify type distribution per synset
  Flag synsets below POS-dependent thresholds
                                ↓
Phase 3: Gap-fill pass (flagged synsets only)
  Show existing properties → ask for missing physical/sensory
  No duplicates, single words only
```

### Why not two prompts per synset?

The design council recommended separate "physics" and "vibes" prompts (2x API cost). We chose a single improved prompt with post-hoc audit instead because:

- The v2 prompt already captures `type` per property — we get physical/abstract classification for free
- A minimum physical count in the prompt nudges coverage without doubling cost
- The post-hoc audit reveals the *actual* extent of the bias before committing to a second pass
- Gap-fill only targets synsets that genuinely need it, which may be a small fraction

If the audit shows widespread physical gaps (>40% of nouns flagged), we can revisit the dual-prompt approach. Data first, then decide.

---

## Phase 1: Modified v2 Prompt

### Changes to `BATCH_PROMPT_V2`

Three modifications to the existing v2 prompt in `enrich_properties.py`:

#### 1. Single-word constraint

Replace "1-2 words maximum" with a strict single-word rule.

```
Every property MUST be exactly one word. No hyphens, no compounds, no multi-word
expressions. No exceptions.

GOOD: flickering, frigid, shrill, dense, molten, conical, pungent
BAD: cold metal (two words), high-pitched (hyphenated), dormant-active (compound),
     lava-formed (compound), gently flickering (two words)

If you need to express "cold metal", choose ONE word that captures it: frigid, metallic, or icy.
```

#### 2. Minimum physical count

Add an explicit floor for physical property coverage:

```
At least 4 of your properties must have type "physical" (texture, weight, temperature,
luminosity, sound, colour, shape, size, material). If the concept genuinely has fewer
than 4 physical qualities, include as many as truly apply — but most concrete nouns
have at least 4.
```

#### 3. Physical-grounding examples

Add examples that demonstrate good physical property extraction alongside the existing candle example. Emphasis on the kind of "obvious" physical traits the LLM tends to omit:

```
Word: volcano
Definition: a mountain formed by volcanic material
Properties: [
  {"text": "hot", "salience": 0.95, "type": "physical", ...},
  {"text": "conical", "salience": 0.8, "type": "physical", ...},
  {"text": "towering", "salience": 0.85, "type": "physical", ...},
  {"text": "molten", "salience": 0.9, "type": "physical", ...},
  {"text": "ashy", "salience": 0.7, "type": "physical", ...},
  {"text": "eruptive", "salience": 0.85, "type": "behaviour", ...},
  {"text": "destructive", "salience": 0.75, "type": "effect", ...},
  ...
]
(NOT: magmatic, pyroclastic, geological — these are taxonomic labels, not experiential)
```

### v1 → v2 transition

This re-enrichment switches production from Variant C (v1, flat property strings) to the modified v2 prompt (structured properties with salience, type, relation). The v2 schema is already supported by the import pipeline (`enrich_pipeline.py` handles `--schema-version v2`).

---

## Phase 2: Post-hoc Audit

### New script: `audit_physical_coverage.py`

After enrichment import, audit the type distribution per synset:

1. For each enriched synset, count properties where `type == "physical"`
2. Look up POS from the `synsets` table
3. Flag synsets below POS-dependent thresholds:

| POS | Min physical | Rationale |
|-----|-------------|-----------|
| Noun | >= 4 | Nouns are the primary metaphor vehicles; physical grounding is critical |
| Verb | >= 2 | Verbs have physical dimensions (speed, force, rhythm) but fewer than nouns |
| Adjective | >= 2 | Adjectives describe qualities — sensory ones are especially valuable |

4. Output: JSON report with:
   - Total synsets audited
   - Flagged count and percentage per POS
   - Per-synset details: ID, word, POS, physical count, existing properties

### Decision gate

Review the audit report before proceeding to Phase 3. If:
- **< 20% nouns flagged:** gap-fill is targeted and cheap — proceed
- **20-40% flagged:** gap-fill is moderate cost — proceed but consider batching
- **> 40% flagged:** the prompt isn't nudging hard enough — revisit the v2 prompt modifications before gap-filling

---

## Phase 3: Gap-fill Pass

### Gap-fill prompt

A separate, targeted prompt for flagged synsets only:

```
You are adding missing physical and sensory properties to word senses that lack them.

Below are word senses with their EXISTING properties. Your job is to add ONLY
physical/sensory properties that are missing. Do NOT duplicate any existing property.

Physical/sensory properties describe: texture, weight, temperature, luminosity,
sound, colour, shape, size, material, smell, taste, motion.

CONSTRAINTS:
- Every property MUST be exactly one word. No hyphens, no compounds.
- Only add properties with type "physical".
- Do NOT repeat or rephrase any existing property.
- Add 3-6 physical properties per synset — enough to ground it, not more.
- Use the same JSON format as the existing properties (text, salience, type, relation).

{batch_items}

Output ONLY a valid JSON array (no markdown, no explanation):
[{"id": "...", "properties": [...]}, ...]
```

### Batch item format

Each batch item includes existing properties so the LLM can avoid duplicates:

```
ID: oewn-volcano-n-01
Word: volcano
Definition: a mountain formed by volcanic material
Existing properties: eruptive, destructive, imposing, steep, mountainous
```

### Merge strategy

Gap-fill properties are appended to the synset's existing properties in the enrichment JSON. They are distinguished by a marker in the enrichment metadata (not per-property — the whole gap-fill batch gets its own enrichment file with a `source: "gap_fill"` tag).

The import pipeline (`enrich.sh --from-json`) already handles multiple enrichment JSONs and merges them. Gap-fill JSONs are imported after the primary enrichment.

---

## Quality Constraints (all prompts)

These constraints apply to both the modified v2 prompt and the gap-fill prompt:

| Constraint | Enforcement |
|-----------|------------|
| Single word only | Prompt instruction + post-import validation (reject multi-word, reject hyphens) |
| No taxonomic labels | Prompt examples showing bad outputs (`magmatic` → `molten`) |
| Sense disambiguation | Existing v2 mechanism (definition-driven, examples) |
| 10-15 properties per synset | Prompt instruction, truncation at `MAX_PROPERTIES_PER_SYNSET = 15` |
| Salience scoring | v2 format: 0.0-1.0 per property |
| Type annotation | v2 format: physical/behaviour/effect/functional/emotional/social |

### Post-import validation

Add a validation step to `enrich_pipeline.py` that:
- Rejects properties containing spaces or hyphens (log warning, skip property)
- Logs a summary of rejected properties per batch for monitoring

---

## Evaluation

### Success criteria

Run the full eval suite after re-enrichment and compare against current baseline:

| Metric | Current | Target | Notes |
|--------|---------|--------|-------|
| MRR | 0.0374 | >= 0.0374 | Guardrail — must not regress |
| rank_auc | 0.537 | > 0.60 | Primary KPI — discrimination must improve |
| cross-domain ratio | 0.334 | > 0.40 | Cross-domain candidates should increase |
| Snap rate | (unmeasured) | Measure before/after | Single-word constraint should improve this |
| Physical coverage (nouns) | (unmeasured) | >= 4 per noun (p90) | Audit will establish baseline |

### Evaluation sequence

1. Re-enrich with modified v2 prompt
2. Import + snap + rebuild
3. Run MRR eval (regression check)
4. Run discrimination eval (rank_auc, cross-domain ratio)
5. Run physical coverage audit
6. If needed: gap-fill pass → re-import → re-eval

---

## Cost Estimate

| Phase | Synsets | Calls | Model | Approx cost |
|-------|---------|-------|-------|-------------|
| Phase 1: Re-enrichment | ~20k | ~1000 batches of 20 | sonnet | Depends on token pricing |
| Phase 3: Gap-fill | Unknown (audit-dependent) | Fraction of Phase 1 | sonnet | << Phase 1 |

Phase 3 cost depends on audit results. Could be 5% of Phase 1 (if prompt nudge works well) or up to 40% (if reporting bias persists despite nudge).

---

## Files Affected

| File | Change |
|------|--------|
| `data-pipeline/scripts/enrich_properties.py` | Modify `BATCH_PROMPT_V2`, add single-word constraint, physical minimum, examples |
| `data-pipeline/scripts/enrich_pipeline.py` | Add post-import validation (reject multi-word/hyphenated properties) |
| `data-pipeline/scripts/audit_physical_coverage.py` | **New** — post-hoc audit script |
| `data-pipeline/scripts/gap_fill_physical.py` | **New** — gap-fill enrichment script |
| `data-pipeline/scripts/test_audit_physical_coverage.py` | **New** — tests for audit |
| `data-pipeline/scripts/test_gap_fill_physical.py` | **New** — tests for gap-fill |
| `data-pipeline/CLAUDE.md` | Document Phase 3 gap-fill as Operation 6 |
| `docs/designs/cascade-scoring-roadmap.md` | Update P2/P3 status, add dual-prompt phase |

---

## Council Review Reference

This design implements recommendation #2 from the P2 design council review (`docs/designs/20260225-cascade-scoring-P2-design-council-review.md`):

> **Dual-Prompt Strategy:** To ensure your Ortony Salience calculations are grounded, update your extraction pipeline to hit the LLM twice per synset. One prompt should focus exclusively on Sensory/Physical/Taxonomic properties (The Physics), and the second on Abstract/Functional/Relational properties (The Vibes).

We deviate from the council's "always two prompts" recommendation by using a single improved prompt with post-hoc audit, only running a second pass where the data shows it's needed. This is more cost-effective and data-driven.
