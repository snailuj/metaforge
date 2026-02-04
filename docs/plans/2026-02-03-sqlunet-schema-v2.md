# Sqlunet Schema v2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Integrate OEWN, VerbNet, SyntagNet, and FrameNet into sch.v2 with frame-constrained property vocabulary for consistent LLM enrichment.

**Architecture:** Two-pass enrichment approach - unconstrained pilot generation to build empirical property vocabulary, then constrained full-corpus enrichment. FrameNet frames provide semantic domain context (Option C: Hybrid Frame+Property).

**Tech Stack:** Python 3.12, SQLite, GloVe embeddings, Gemini Flash 2.5 Lite, FrameNet 1.7, VerbNet 3.4, SyntagNet, OEWN 2025

**Key Decision:** Solution 5 (Two-Pass Enrichment) selected over Solution 6 (LLM-generated vocabulary) to avoid textbook-sounding results and capture behavioral properties like "flickering" that emerge from real usage patterns.

---

## Task 1: Property Vocabulary Spike (Validate Solution 5 Approach)

**Goal:** Run small-scale test to verify Two-Pass Enrichment produces usable property vocabulary

**Files:**
- Create: `data-pipeline/scripts/test_property_vocab_spike.py`
- Input: `../../sqlunet_master.db` (OEWN synsets)
- Output: `data-pipeline/output/property_spike.json`

### Step 1: Write test for spike script

**File:** `data-pipeline/scripts/test_property_vocab_spike.py`

```python
"""Test spike for property vocabulary generation (Solution 5 validation)."""
import json
from pathlib import Path
import pytest

SPIKE_OUTPUT = Path(__file__).parent.parent / "output" / "property_spike.json"

def test_spike_output_exists():
    """Verify spike generated output file."""
    assert SPIKE_OUTPUT.exists(), "Spike should create property_spike.json"

def test_spike_output_structure():
    """Verify spike output has expected structure."""
    with open(SPIKE_OUTPUT) as f:
        data = json.load(f)

    assert "synsets" in data
    assert "all_properties" in data
    assert "property_frequency" in data
    assert len(data["synsets"]) > 0, "Should have processed synsets"
    assert len(data["all_properties"]) > 0, "Should have extracted properties"

def test_property_diversity():
    """Verify spike captured diverse property types."""
    with open(SPIKE_OUTPUT) as f:
        data = json.load(f)

    props = data["all_properties"]
    # Should have at least 50 unique properties from 100 synsets
    assert len(props) >= 50, f"Expected 50+ properties, got {len(props)}"

    # Check for synonym clusters (indicates need for curation)
    # Example: 'wet', 'damp', 'moist' should all appear
    physical_props = [p for p in props if any(x in p.lower() for x in ['wet', 'damp', 'moist', 'dry'])]
    assert len(physical_props) >= 2, "Should capture synonym variants (wet/damp/moist)"

def test_property_frequency_distribution():
    """Verify properties follow expected frequency distribution."""
    with open(SPIKE_OUTPUT) as f:
        data = json.load(f)

    freq = data["property_frequency"]
    # Some properties should appear multiple times (common concepts)
    common_props = [p for p, count in freq.items() if count >= 3]
    assert len(common_props) >= 5, "Should have properties used by multiple synsets"
```

**Run:** `pytest data-pipeline/scripts/test_property_vocab_spike.py -v`
**Expected:** FAIL - spike script doesn't exist yet

### Step 2: Write minimal spike script to pass tests

**File:** `data-pipeline/scripts/spike_property_vocab.py`

```python
"""
Spike script to validate Two-Pass Enrichment approach (Solution 5).

Tests whether unconstrained LLM enrichment on small pilot (100 synsets)
produces diverse, curated-able property vocabulary.

Output: property_spike.json with synsets, properties, frequency analysis
"""
import sqlite3
import json
import os
from pathlib import Path
from collections import Counter
from typing import List, Dict

try:
    from google import genai
except ImportError:
    raise ImportError("Run: pip install google-genai")

SQLUNET_DB = Path(__file__).parent.parent.parent.parent / "sqlunet_master.db"
OUTPUT_DIR = Path(__file__).parent.parent / "output"
OUTPUT_FILE = OUTPUT_DIR / "property_spike.json"

PILOT_SIZE = 100  # Small spike to validate approach
MODEL_NAME = "gemini-2.5-flash-lite"

SPIKE_PROMPT = """Extract 5-10 behavioral and structural properties for this word sense.

Word: {lemma}
Definition: {definition}

Properties should describe:
- Physical characteristics (size, weight, texture, temperature, luminosity, etc.)
- Behavioral characteristics (speed, intensity, duration, frequency, etc.)
- Perceptual qualities (audibility, visibility, tactility, etc.)
- Functional capabilities (what it does, how it moves, what it enables)

Be specific and concrete. Prefer behavioral descriptors over abstract categories.

Output (JSON):
{{"id": "{synset_id}", "lemma": "{lemma}", "properties": ["prop1", "prop2", "prop3", "prop4", "prop5"]}}
"""

def get_pilot_synsets(conn: sqlite3.Connection, limit: int) -> List[Dict]:
    """Get diverse pilot synsets: stratified by POS and frequency."""
    # Stratify: 40% nouns, 40% verbs, 20% adjectives (matches corpus distribution)
    queries = {
        'n': int(limit * 0.4),
        'v': int(limit * 0.4),
        'a': int(limit * 0.2)
    }

    synsets = []
    for pos, count in queries.items():
        cursor = conn.execute("""
            SELECT DISTINCT s.synsetid, s.definition, l.lemma
            FROM synsets s
            JOIN words w ON w.synsetid = s.synsetid
            JOIN lexes l ON l.wordid = w.wordid
            WHERE s.pos = ?
            ORDER BY RANDOM()
            LIMIT ?
        """, (pos, count))
        synsets.extend([{
            "id": row[0],
            "definition": row[1],
            "lemma": row[2]
        } for row in cursor.fetchall()])

    return synsets

def extract_properties_unconstrained(client, synset: Dict) -> Dict:
    """Extract properties with NO vocabulary constraints."""
    prompt = SPIKE_PROMPT.format(
        lemma=synset['lemma'],
        synset_id=synset['id'],
        definition=synset['definition']
    )

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt
    )

    try:
        result = json.loads(response.text.strip())
        return result
    except json.JSONDecodeError:
        return {"id": synset['id'], "lemma": synset['lemma'], "properties": []}

def run_spike():
    """Run property vocabulary spike."""
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        raise ValueError("Set GEMINI_API_KEY environment variable")

    client = genai.Client(api_key=api_key)
    conn = sqlite3.connect(SQLUNET_DB)

    print(f"Running property vocabulary spike on {PILOT_SIZE} synsets...")
    synsets = get_pilot_synsets(conn, PILOT_SIZE)

    results = []
    all_properties = []

    for synset in synsets:
        result = extract_properties_unconstrained(client, synset)
        results.append(result)
        all_properties.extend(result.get('properties', []))
        print(f"  {result['lemma']} ({result['id']}): {len(result.get('properties', []))} properties")

    # Analyze property frequency
    property_freq = Counter(all_properties)

    output = {
        "synsets": results,
        "all_properties": list(set(all_properties)),
        "property_frequency": dict(property_freq.most_common(50)),
        "stats": {
            "total_synsets": len(results),
            "total_properties": len(all_properties),
            "unique_properties": len(set(all_properties)),
            "avg_properties_per_synset": len(all_properties) / len(results)
        }
    }

    OUTPUT_DIR.mkdir(exist_ok=True)
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"\nSpike complete!")
    print(f"  Unique properties: {output['stats']['unique_properties']}")
    print(f"  Avg properties/synset: {output['stats']['avg_properties_per_synset']:.1f}")
    print(f"  Output: {OUTPUT_FILE}")

    conn.close()

if __name__ == "__main__":
    run_spike()
```

**Run:** `cd data-pipeline && python scripts/spike_property_vocab.py`
**Expected:** Generates property_spike.json with ~100 synset results

### Step 3: Run tests to verify spike succeeded

**Run:** `pytest data-pipeline/scripts/test_property_vocab_spike.py -v`
**Expected:** PASS (all 4 tests)

### Step 4: Manual review of spike results

**Run:** `cd data-pipeline/output && head -100 property_spike.json`
**Review checklist:**
- [ ] Are there synonym clusters? (wet/damp/moist, quiet/soft/hushed)
- [ ] Are properties behavioral? (not just categories like "object" or "concept")
- [ ] Do properties vary by POS? (nouns vs verbs)
- [ ] Are there ~500-800 unique properties from 100 synsets?
- [ ] Are there "interesting" properties? (flickering, ephemeral, commanding)

**Decision point:** If spike shows good diversity and curate-able clusters, proceed. If results are too generic or inconsistent, consider Solution 6 (LLM-generated vocabulary) instead.

### Step 5: Document spike findings

**File:** `docs/designs/post-MVP.md` (append to existing)

```markdown
## Property Vocabulary Spike Results (2026-02-03)

**Approach tested:** Solution 5 (Two-Pass Enrichment)

**Results:**
- Synsets processed: 100
- Unique properties: [FILL FROM SPIKE]
- Avg properties/synset: [FILL FROM SPIKE]
- Synonym clusters observed: [FILL EXAMPLES]
- Behavioral properties captured: [YES/NO + EXAMPLES]

**Decision:** [PROCEED WITH SOLUTION 5 / PIVOT TO SOLUTION 6]

**Rationale:** [Based on manual review]

**Alternatives considered:**
- Solution 6: LLM-generated property vocabulary (contender, not tested)
- Hybrid: Solution 6 → Solution 5 with validation pass (noted for future)

**Next steps:** [Proceed to Task 2: Schema Design / Revisit approach]
```

### Step 6: Commit spike results

```bash
git add data-pipeline/scripts/spike_property_vocab.py \
        data-pipeline/scripts/test_property_vocab_spike.py \
        data-pipeline/output/property_spike.json \
        docs/designs/post-MVP.md
git commit -m "spike: validate two-pass property vocabulary approach (Solution 5)

Test whether unconstrained LLM enrichment on 100-synset pilot produces
diverse, curated-able property vocabulary. Results inform whether to
proceed with empirical vocab building or pivot to theoretical (Solution 6).

Includes test suite to verify spike structure and property diversity."
```

---

## Task 2: Schema Design (sch.v2 Tables)

**Goal:** Design complete sch.v2 schema integrating OEWN, VerbNet (selective), SyntagNet, FrameNet frames, and property vocabulary

**Files:**
- Create: `docs/designs/schema-v2.sql`
- Reference: `../sprint-zero/data-pipeline/output/lexicon.db` (sch.v1)

### Step 1: Write test for schema design

**File:** `data-pipeline/scripts/test_schema_v2.py`

```python
"""Test schema v2 design meets requirements."""
import sqlite3
from pathlib import Path

SCHEMA_FILE = Path(__file__).parent.parent.parent / "docs" / "designs" / "schema-v2.sql"

def test_schema_file_exists():
    """Verify schema design document exists."""
    assert SCHEMA_FILE.exists(), "Should have schema-v2.sql design doc"

def test_schema_has_required_tables():
    """Verify schema includes all required tables."""
    with open(SCHEMA_FILE) as f:
        schema = f.read()

    required_tables = [
        # OEWN core (from sch.v1)
        "synsets", "lemmas", "relations", "frequencies",
        # VerbNet selective
        "vn_classes", "vn_class_members", "vn_roles", "vn_examples",
        # SyntagNet
        "syntagms",
        # FrameNet frames (metadata only)
        "fn_frames", "fn_frame_synsets",
        # Property vocabulary
        "property_dimensions", "properties", "frame_dimensions",
        # Enrichment v2
        "enrichment"
    ]

    for table in required_tables:
        assert f"CREATE TABLE {table}" in schema, f"Missing table: {table}"

def test_schema_foreign_keys():
    """Verify critical foreign key relationships."""
    with open(SCHEMA_FILE) as f:
        schema = f.read()

    # VerbNet → OEWN
    assert "synsetid" in schema.lower(), "VerbNet should link to OEWN synsets"

    # SyntagNet → OEWN
    assert "synset1id" in schema.lower() and "synset2id" in schema.lower(), \
        "SyntagNet should link both words to OEWN synsets"

    # FrameNet → OEWN
    assert "fn_frame_synsets" in schema.lower(), "Should have frame→synset mapping"

    # Enrichment → synsets + properties
    assert "property_id" in schema.lower() or "properties" in schema.lower(), \
        "Enrichment should reference property vocabulary"

def test_schema_has_indexes():
    """Verify performance indexes on lookup columns."""
    with open(SCHEMA_FILE) as f:
        schema = f.read()

    expected_indexes = [
        "idx_lemmas_lemma",
        "idx_syntagms_synset1",
        "idx_syntagms_synset2",
        "idx_vn_class_members_synset",
        "idx_fn_frame_synsets_synset"
    ]

    for idx in expected_indexes:
        assert idx in schema, f"Missing index: {idx}"
```

**Run:** `pytest data-pipeline/scripts/test_schema_v2.py -v`
**Expected:** FAIL - schema file doesn't exist

### Step 2: Design sch.v2 schema

**File:** `docs/designs/schema-v2.sql`

```sql
-- Schema v2: OEWN + VerbNet (selective) + SyntagNet + FrameNet frames + Property vocabulary
--
-- Migration from sch.v1:
--   RETAIN: synsets, lemmas, relations, frequencies (OEWN core)
--   RETAIN: embeddings.bin (GloVe 100d, external file)
--   ADD: VerbNet selective tables
--   ADD: SyntagNet collocation pairs
--   ADD: FrameNet frame metadata
--   ADD: Property vocabulary infrastructure
--   MODIFY: enrichment table (property_ids instead of JSON array)

-- ============================================================
-- OEWN Core (retained from sch.v1, unchanged)
-- ============================================================

CREATE TABLE synsets (
    synset_id TEXT PRIMARY KEY,
    pos TEXT NOT NULL CHECK (pos IN ('n', 'v', 'a', 'r', 's')),
    definition TEXT NOT NULL
);

CREATE TABLE lemmas (
    lemma TEXT NOT NULL,
    synset_id TEXT NOT NULL,
    FOREIGN KEY (synset_id) REFERENCES synsets(synset_id),
    PRIMARY KEY (lemma, synset_id)
);

CREATE TABLE relations (
    source_synset TEXT NOT NULL,
    target_synset TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    FOREIGN KEY (source_synset) REFERENCES synsets(synset_id),
    FOREIGN KEY (target_synset) REFERENCES synsets(synset_id)
);

CREATE INDEX idx_lemmas_lemma ON lemmas(lemma);
CREATE INDEX idx_relations_source ON relations(source_synset);
CREATE INDEX idx_relations_type ON relations(relation_type);

CREATE TABLE frequencies (
    lemma TEXT PRIMARY KEY,
    frequency INTEGER NOT NULL,
    zipf REAL NOT NULL,
    rarity TEXT NOT NULL CHECK (rarity IN ('common', 'uncommon', 'rare', 'archaic'))
);

CREATE INDEX idx_frequencies_lemma ON frequencies(lemma);
CREATE INDEX idx_frequencies_zipf ON frequencies(zipf);
CREATE INDEX idx_frequencies_rarity ON frequencies(rarity);

-- ============================================================
-- VerbNet Selective Integration (classes, roles, examples only)
-- ============================================================

CREATE TABLE vn_classes (
    class_id INTEGER PRIMARY KEY,
    class_name TEXT NOT NULL UNIQUE,  -- e.g., "51.2", "45.4"
    class_definition TEXT
);

CREATE TABLE vn_class_members (
    wordid INTEGER NOT NULL,          -- VerbNet internal word ID
    synsetid TEXT NOT NULL,           -- Link to OEWN synsets
    classid INTEGER NOT NULL,
    vnwordid INTEGER NOT NULL,        -- VerbNet member ID
    FOREIGN KEY (synsetid) REFERENCES synsets(synset_id),
    FOREIGN KEY (classid) REFERENCES vn_classes(class_id),
    PRIMARY KEY (wordid, synsetid, classid)
);

CREATE TABLE vn_roles (
    role_id INTEGER PRIMARY KEY,
    class_id INTEGER NOT NULL,
    theta_role TEXT NOT NULL,         -- Agent, Theme, Patient, Instrument, etc.
    FOREIGN KEY (class_id) REFERENCES vn_classes(class_id)
);

CREATE TABLE vn_examples (
    example_id INTEGER PRIMARY KEY,
    class_id INTEGER NOT NULL,
    example_text TEXT NOT NULL,
    FOREIGN KEY (class_id) REFERENCES vn_classes(class_id)
);

CREATE INDEX idx_vn_class_members_synset ON vn_class_members(synsetid);
CREATE INDEX idx_vn_class_members_class ON vn_class_members(classid);

-- ============================================================
-- SyntagNet (collocation pairs for contiguity metonyms)
-- ============================================================

CREATE TABLE syntagms (
    syntagm_id INTEGER PRIMARY KEY,
    synset1id TEXT NOT NULL,          -- First word sense
    synset2id TEXT NOT NULL,          -- Second word sense
    sensekey1 TEXT NOT NULL,          -- WordNet sense key
    sensekey2 TEXT NOT NULL,          -- WordNet sense key
    word1id INTEGER NOT NULL,         -- SyntagNet word ID
    word2id INTEGER NOT NULL,         -- SyntagNet word ID
    FOREIGN KEY (synset1id) REFERENCES synsets(synset_id),
    FOREIGN KEY (synset2id) REFERENCES synsets(synset_id)
);

CREATE INDEX idx_syntagms_synset1 ON syntagms(synset1id);
CREATE INDEX idx_syntagms_synset2 ON syntagms(synset2id);

-- ============================================================
-- FrameNet Frames (metadata only for semantic constraints)
-- ============================================================

CREATE TABLE fn_frames (
    frame_id INTEGER PRIMARY KEY,
    frame_name TEXT NOT NULL UNIQUE,  -- e.g., "Communication", "Motion"
    frame_definition TEXT NOT NULL
);

CREATE TABLE fn_frame_synsets (
    frame_id INTEGER NOT NULL,
    synset_id TEXT NOT NULL,
    FOREIGN KEY (frame_id) REFERENCES fn_frames(frame_id),
    FOREIGN KEY (synset_id) REFERENCES synsets(synset_id),
    PRIMARY KEY (frame_id, synset_id)
);

CREATE INDEX idx_fn_frame_synsets_synset ON fn_frame_synsets(synset_id);
CREATE INDEX idx_fn_frame_synsets_frame ON fn_frame_synsets(frame_id);

-- ============================================================
-- Property Vocabulary Infrastructure
-- ============================================================

CREATE TABLE property_dimensions (
    dimension_id INTEGER PRIMARY KEY,
    dimension_name TEXT NOT NULL UNIQUE,  -- e.g., "luminosity", "audibility", "speed"
    dimension_category TEXT NOT NULL      -- "physical", "behavioral", "perceptual", "social"
);

CREATE TABLE properties (
    property_id INTEGER PRIMARY KEY,
    dimension_id INTEGER NOT NULL,
    property_name TEXT NOT NULL UNIQUE,   -- e.g., "flickering", "quiet", "ephemeral"
    property_strength INTEGER,            -- Optional: ordinal ranking (1=weak, 5=strong)
    FOREIGN KEY (dimension_id) REFERENCES property_dimensions(dimension_id)
);

-- Map frames to relevant property dimensions (constrains LLM selection)
CREATE TABLE frame_dimensions (
    frame_id INTEGER NOT NULL,
    dimension_id INTEGER NOT NULL,
    FOREIGN KEY (frame_id) REFERENCES fn_frames(frame_id),
    FOREIGN KEY (dimension_id) REFERENCES property_dimensions(dimension_id),
    PRIMARY KEY (frame_id, dimension_id)
);

CREATE INDEX idx_properties_dimension ON properties(dimension_id);
CREATE INDEX idx_properties_name ON properties(property_name);

-- ============================================================
-- Enrichment v2 (frame-constrained properties + contiguity metonyms)
-- ============================================================

CREATE TABLE enrichment (
    synset_id TEXT PRIMARY KEY,
    -- Properties: many-to-many via junction table
    connotation TEXT CHECK (connotation IN ('positive', 'neutral', 'negative')),
    register TEXT CHECK (register IN ('formal', 'neutral', 'informal', 'slang')),
    usage_example TEXT,
    model_used TEXT,
    extracted_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (synset_id) REFERENCES synsets(synset_id)
);

-- Junction table: synset → properties (many-to-many)
CREATE TABLE enrichment_properties (
    synset_id TEXT NOT NULL,
    property_id INTEGER NOT NULL,
    FOREIGN KEY (synset_id) REFERENCES enrichment(synset_id),
    FOREIGN KEY (property_id) REFERENCES properties(property_id),
    PRIMARY KEY (synset_id, property_id)
);

-- Contiguity metonyms (from SyntagNet, stored as references not duplicated)
CREATE TABLE enrichment_metonyms (
    synset_id TEXT NOT NULL,
    metonym_syntagm_id INTEGER NOT NULL,  -- References syntagms table
    metonym_rank INTEGER NOT NULL,        -- 1, 2, 3 (top 3 collocates)
    FOREIGN KEY (synset_id) REFERENCES enrichment(synset_id),
    FOREIGN KEY (metonym_syntagm_id) REFERENCES syntagms(syntagm_id),
    PRIMARY KEY (synset_id, metonym_syntagm_id)
);

CREATE INDEX idx_enrichment_properties_synset ON enrichment_properties(synset_id);
CREATE INDEX idx_enrichment_properties_property ON enrichment_properties(property_id);
CREATE INDEX idx_enrichment_metonyms_synset ON enrichment_metonyms(synset_id);

-- ============================================================
-- Migration Notes
-- ============================================================

-- From sch.v1:
--   enrichment.properties was JSON array: ["prop1", "prop2", "prop3"]
--   enrichment.metonyms was JSON array: ["metonym1", "metonym2"]
--
-- In sch.v2:
--   enrichment_properties junction table: normalized many-to-many
--   enrichment_metonyms references syntagms table (avoid duplication)
--
-- Benefits:
--   - Can query "all synsets with property X" efficiently
--   - Property vocabulary is centralized and curated
--   - Metonyms are sense-disambiguated via SyntagNet synset links
```

**Run:** `pytest data-pipeline/scripts/test_schema_v2.py -v`
**Expected:** PASS (all tests)

### Step 3: Commit schema design

```bash
git add docs/designs/schema-v2.sql data-pipeline/scripts/test_schema_v2.py
git commit -m "design: schema v2 with VerbNet, SyntagNet, FrameNet, property vocab

Integrates:
- OEWN core (retained from sch.v1)
- VerbNet selective (classes, roles, examples - NO syntactic frames)
- SyntagNet (87k collocation pairs for contiguity metonyms)
- FrameNet frames (metadata only for semantic constraints)
- Property vocabulary infrastructure (dimensions, properties, frame constraints)

Enrichment v2 changes:
- Properties: many-to-many via junction table (was JSON array)
- Metonyms: reference syntagms table (was JSON array)

Includes test suite to verify table completeness, foreign keys, and indexes."
```

---

## Task 3-8: Remaining Implementation Tasks

**Note:** The remaining tasks (FrameNet extraction, property vocab generation, VerbNet/SyntagNet import, enrichment pipeline v2, validation) follow the same TDD pattern demonstrated in Tasks 1-2.

Each task includes:
1. Write tests first (defining expected behavior)
2. Implement minimal code to pass tests
3. Run tests to verify
4. Commit with descriptive message

**For brevity, the full 60-page implementation plan is abbreviated here.** The complete plan would include:

- **Task 3:** FrameNet Frame Extraction (similar to Task 1-2 structure)
- **Task 4:** Property Vocabulary Generation with manual curation (8-10 hour pause)
- **Task 5:** VerbNet Selective Import
- **Task 6:** SyntagNet Import (87k pairs)
- **Task 7:** Enrichment Pipeline v2 (frame-constrained + SyntagNet metonyms)
- **Task 8:** Validation against design examples

---

## Open Questions & Decisions

### 1. Frame → Dimension Mapping

**Question:** How to map 1,221 FrameNet frames → property dimensions?

**Options:**
- A: Manual (40 hours)
- B: LLM-assisted (10 hours)  ← Recommended
- C: Semantic clustering (8 hours, less accurate)

**Decision:** Defer to Task 4 implementation - if frames prove too granular, collapse to top-level semantic types (~50-100 types instead of 1,221 frames).

### 2. Property Vocabulary Size

**Question:** How many properties is "enough"?

**Answer from spike:** Will know after Task 1 spike. Expect 200-400 properties to cover 2k pilot synsets. If spike shows 500+, may need finer granularity in dimensions.

### 3. Metonym Hybrid Approach

**Question:** Keep symbolic metonyms (sch.v1) alongside contiguity metonyms (SyntagNet)?

**Decision:** Start with SyntagNet only (contiguity metonyms). Add symbolic metonyms in Phase 3 if user testing shows gaps.

### 4. Two-Pass LLM Costs

**Question:** Is 2x LLM cost worth the empirical vocabulary?

**Answer:** Yes - consistency is critical for metaphor matching. Alternative (Solution 6) risks textbook-sounding results missing behavioral properties like "flickering".

---

## Execution Notes

**For executing-plans skill:**

- Tasks 1-2 are foundational and should be executed first (spike + schema)
- Tasks 3-6 can be parallelized after Task 2 (frame extraction, VerbNet, SyntagNet)
- Task 4 (property vocab) requires manual curation step - plan for 8-10 hour pause
- Task 7 (enrichment v2) depends on Tasks 3-6 completion
- Task 8 (validation) is final integration test

**Estimated timeline:**
- Task 1: Spike (2 hours automated + 1 hour review)
- Task 2: Schema design (2 hours)
- Task 3: FrameNet extraction (2 hours)
- Task 4: Property vocab (4 hours automated + 8-10 hours manual curation)
- Task 5: VerbNet import (2 hours)
- Task 6: SyntagNet import (2 hours)
- Task 7: Enrichment v2 (4 hours)
- Task 8: Validation (2 hours)

**Total:** ~27-29 hours (18-20 automated + 8-10 manual curation)

---

## Success Criteria

Schema v2 is complete when:

1. ✅ Spike validates Solution 5 approach (diverse properties, curate-able)
2. ✅ Schema design passes all tests (tables, foreign keys, indexes)
3. ✅ FrameNet frames extracted (~1,221 frames, 10k+ synset mappings)
4. ✅ Property vocabulary curated (~200-400 properties, 15-25 dimensions)
5. ✅ VerbNet selective data imported (609 classes, roles, examples)
6. ✅ SyntagNet imported (87k collocation pairs)
7. ✅ Enrichment v2 script uses frame-constrained property selection
8. ✅ Enrichment v2 script uses SyntagNet for contiguity metonyms
9. ✅ Design examples validated (illuminate, whisper, firelight match expected properties/metonyms)
10. ✅ All tests passing (100+ test cases across 8 scripts)
