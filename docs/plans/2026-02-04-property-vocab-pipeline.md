# Property Vocabulary Pipeline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build property vocabulary from 2k pilot enrichment, add GloVe embeddings for fuzzy matching, import OEWN/VerbNet/SyntagNet into lexicon_v2.db.

**Architecture:** Two-pass enrichment with embedding-based matching. No FrameNet constraints — embeddings handle synonym clustering and similarity matching. Properties stored with GloVe 100d vectors for runtime fuzzy comparison.

**Tech Stack:** Python 3.12, SQLite, GloVe 100d embeddings, Gemini Flash 2.5, VerbNet 3.4, SyntagNet, OEWN 2025

**Key Decisions:**
- FrameNet skipped (embeddings provide flexibility without domain constraints)
- Embeddings on properties enable fuzzy matching and confidence scoring
- Light curation (remove garbage, flag OOV) instead of synonym collapse

**Completed:**
- Task 1: 100-synset spike ✅ (729 unique properties, sense disambiguation working)
- Task 2: Schema design ✅ (lexicon_v2.db created with property_vocabulary table)

---

## Task 3: OEWN Core Import

**Goal:** Import synsets, lemmas, relations, and frequencies from sqlunet_master.db into lexicon_v2.db

**Files:**
- Create: `data-pipeline/scripts/import_oewn.py`
- Create: `data-pipeline/scripts/test_import_oewn.py`
- Input: `../../sqlunet_master.db` (107k synsets, 127k words)
- Output: `data-pipeline/output/lexicon_v2.db`

### Step 1: Write test for OEWN import

**File:** `data-pipeline/scripts/test_import_oewn.py`

```python
"""Test OEWN import to lexicon_v2.db."""
import sqlite3
from pathlib import Path
import pytest

LEXICON_V2 = Path(__file__).parent.parent / "output" / "lexicon_v2.db"

def test_synsets_imported():
    """Verify synsets table populated."""
    conn = sqlite3.connect(LEXICON_V2)
    count = conn.execute("SELECT COUNT(*) FROM synsets").fetchone()[0]
    conn.close()
    assert count > 100000, f"Expected 100k+ synsets, got {count}"

def test_lemmas_imported():
    """Verify lemmas table populated."""
    conn = sqlite3.connect(LEXICON_V2)
    count = conn.execute("SELECT COUNT(*) FROM lemmas").fetchone()[0]
    conn.close()
    assert count > 200000, f"Expected 200k+ lemma-synset pairs, got {count}"

def test_relations_imported():
    """Verify relations table populated."""
    conn = sqlite3.connect(LEXICON_V2)
    count = conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0]
    conn.close()
    assert count > 200000, f"Expected 200k+ relations, got {count}"

def test_sample_lookup():
    """Verify we can look up a known word."""
    conn = sqlite3.connect(LEXICON_V2)
    result = conn.execute("""
        SELECT s.definition
        FROM lemmas l
        JOIN synsets s ON s.synset_id = l.synset_id
        WHERE l.lemma = 'candle'
        LIMIT 1
    """).fetchone()
    conn.close()
    assert result is not None, "Should find 'candle'"
    assert 'wax' in result[0].lower() or 'light' in result[0].lower()
```

**Run:** `pytest data-pipeline/scripts/test_import_oewn.py -v`
**Expected:** FAIL - tables empty

### Step 2: Write OEWN import script

**File:** `data-pipeline/scripts/import_oewn.py`

```python
"""Import OEWN core data from sqlunet_master.db to lexicon_v2.db."""
import sqlite3
from pathlib import Path

SQLUNET_DB = Path(__file__).parent.parent.parent.parent.parent / "sqlunet_master.db"
LEXICON_V2 = Path(__file__).parent.parent / "output" / "lexicon_v2.db"


def import_synsets(src: sqlite3.Connection, dst: sqlite3.Connection):
    """Import synsets table."""
    print("Importing synsets...")
    cursor = src.execute("""
        SELECT synsetid, posid, definition
        FROM synsets
    """)

    rows = [(str(row[0]), row[1], row[2]) for row in cursor]
    dst.executemany(
        "INSERT OR IGNORE INTO synsets (synset_id, pos, definition) VALUES (?, ?, ?)",
        rows
    )
    print(f"  Imported {len(rows)} synsets")


def import_lemmas(src: sqlite3.Connection, dst: sqlite3.Connection):
    """Import lemma-synset mappings."""
    print("Importing lemmas...")
    cursor = src.execute("""
        SELECT DISTINCT w.word, se.synsetid
        FROM words w
        JOIN senses se ON se.wordid = w.wordid
    """)

    rows = [(row[0], str(row[1])) for row in cursor]
    dst.executemany(
        "INSERT OR IGNORE INTO lemmas (lemma, synset_id) VALUES (?, ?)",
        rows
    )
    print(f"  Imported {len(rows)} lemma-synset pairs")


def import_relations(src: sqlite3.Connection, dst: sqlite3.Connection):
    """Import semantic relations."""
    print("Importing relations...")
    cursor = src.execute("""
        SELECT synset1id, synset2id, relationid
        FROM semrelations
    """)

    rows = [(str(row[0]), str(row[1]), str(row[2])) for row in cursor]
    dst.executemany(
        "INSERT OR IGNORE INTO relations (source_synset, target_synset, relation_type) VALUES (?, ?, ?)",
        rows
    )
    print(f"  Imported {len(rows)} relations")


def main():
    if not SQLUNET_DB.exists():
        raise FileNotFoundError(f"Source DB not found: {SQLUNET_DB}")
    if not LEXICON_V2.exists():
        raise FileNotFoundError(f"Target DB not found: {LEXICON_V2}")

    src = sqlite3.connect(SQLUNET_DB)
    dst = sqlite3.connect(LEXICON_V2)

    import_synsets(src, dst)
    import_lemmas(src, dst)
    import_relations(src, dst)

    dst.commit()
    src.close()
    dst.close()
    print("OEWN import complete!")


if __name__ == "__main__":
    main()
```

### Step 3: Run import

**Run:** `python data-pipeline/scripts/import_oewn.py`
**Expected:** Imports ~107k synsets, ~200k+ lemmas, ~200k+ relations

### Step 4: Run tests to verify

**Run:** `pytest data-pipeline/scripts/test_import_oewn.py -v`
**Expected:** PASS (all 4 tests)

### Step 5: Commit

```bash
git add data-pipeline/scripts/import_oewn.py data-pipeline/scripts/test_import_oewn.py
git commit -m "feat: import OEWN core data to lexicon_v2.db

Import synsets (107k), lemmas (200k+), and relations (200k+) from
sqlunet_master.db. Forms the foundation for property enrichment."
```

---

## Task 4: 2k Pilot Enrichment

**Goal:** Run property extraction on 2000 synsets to build empirical vocabulary

**Files:**
- Modify: `data-pipeline/scripts/spike_property_vocab.py` (already supports --pilot-size)
- Output: `data-pipeline/output/property_pilot_2k.json`

### Step 1: Update output file path for pilot

**File:** `data-pipeline/scripts/spike_property_vocab.py`

Add argument for output file:

```python
parser.add_argument(
    "--output", "-o",
    type=str,
    default=None,
    help="Output file path (default: property_spike.json or property_pilot_<size>.json)"
)
```

Update `run_spike()` to use custom output path:

```python
output_file = args.output or OUTPUT_DIR / f"property_pilot_{pilot_size}.json"
```

### Step 2: Run 2k pilot

**Run:** `python data-pipeline/scripts/spike_property_vocab.py --pilot-size 2000 --batch-size 20 --output data-pipeline/output/property_pilot_2k.json`

**Expected:**
- ~2000 synsets processed
- ~1500-2500 unique properties (based on 729 from 100 synsets)
- Output saved to property_pilot_2k.json

### Step 3: Verify output

**Run:**
```bash
python3 -c "
import json
with open('data-pipeline/output/property_pilot_2k.json') as f:
    d = json.load(f)
print(f'Synsets: {d[\"stats\"][\"total_synsets\"]}')
print(f'Unique props: {d[\"stats\"][\"unique_properties\"]}')
print(f'Avg per synset: {d[\"stats\"][\"avg_properties_per_synset\"]}')
"
```

**Expected:** ~2000 synsets, ~1500-2500 unique properties

### Step 4: Commit

```bash
git add data-pipeline/output/property_pilot_2k.json
git commit -m "data: 2k pilot property extraction for vocabulary curation

2000 synsets enriched with Gemini Flash 2.5, producing empirical
property vocabulary for curation. Sense disambiguation via polysemous
few-shot examples."
```

---

## Task 5: Property Vocabulary Curation

**Goal:** Normalise properties, add GloVe embeddings, flag OOV, populate property_vocabulary table

**Files:**
- Create: `data-pipeline/scripts/curate_properties.py`
- Create: `data-pipeline/scripts/test_curate_properties.py`
- Input: `data-pipeline/output/property_pilot_2k.json`
- Input: `../../.worktrees/sprint-zero/data-pipeline/output/embeddings.bin` (GloVe 100d)
- Output: `data-pipeline/output/lexicon_v2.db` (property_vocabulary table)

### Step 1: Write test for property curation

**File:** `data-pipeline/scripts/test_curate_properties.py`

```python
"""Test property vocabulary curation."""
import sqlite3
import struct
from pathlib import Path
import pytest

LEXICON_V2 = Path(__file__).parent.parent / "output" / "lexicon_v2.db"

def test_properties_imported():
    """Verify property_vocabulary table populated."""
    conn = sqlite3.connect(LEXICON_V2)
    count = conn.execute("SELECT COUNT(*) FROM property_vocabulary").fetchone()[0]
    conn.close()
    assert count > 500, f"Expected 500+ properties, got {count}"

def test_embeddings_present():
    """Verify embeddings added for non-OOV properties."""
    conn = sqlite3.connect(LEXICON_V2)
    with_emb = conn.execute(
        "SELECT COUNT(*) FROM property_vocabulary WHERE embedding IS NOT NULL"
    ).fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM property_vocabulary").fetchone()[0]
    conn.close()

    coverage = with_emb / total if total > 0 else 0
    assert coverage > 0.7, f"Expected 70%+ embedding coverage, got {coverage:.1%}"

def test_oov_flagged():
    """Verify OOV properties are flagged."""
    conn = sqlite3.connect(LEXICON_V2)
    oov_count = conn.execute(
        "SELECT COUNT(*) FROM property_vocabulary WHERE is_oov = 1"
    ).fetchone()[0]
    conn.close()
    # Some OOV expected (compound words, rare terms)
    assert oov_count >= 0, "OOV count should be non-negative"

def test_embedding_dimension():
    """Verify embeddings are 100d (400 bytes)."""
    conn = sqlite3.connect(LEXICON_V2)
    row = conn.execute(
        "SELECT embedding FROM property_vocabulary WHERE embedding IS NOT NULL LIMIT 1"
    ).fetchone()
    conn.close()

    assert row is not None, "Should have at least one embedding"
    emb_bytes = row[0]
    assert len(emb_bytes) == 400, f"Expected 400 bytes (100d float32), got {len(emb_bytes)}"

    # Verify it unpacks correctly
    values = struct.unpack('100f', emb_bytes)
    assert len(values) == 100

def test_normalisation():
    """Verify properties are normalised (lowercase, trimmed)."""
    conn = sqlite3.connect(LEXICON_V2)
    rows = conn.execute("SELECT text FROM property_vocabulary LIMIT 100").fetchall()
    conn.close()

    for (text,) in rows:
        assert text == text.lower().strip(), f"Property not normalised: '{text}'"
```

**Run:** `pytest data-pipeline/scripts/test_curate_properties.py -v`
**Expected:** FAIL - property_vocabulary empty

### Step 2: Write curation script

**File:** `data-pipeline/scripts/curate_properties.py`

```python
"""Curate property vocabulary: normalise, add embeddings, flag OOV."""
import json
import sqlite3
import struct
from pathlib import Path
from collections import Counter
from typing import Dict, Optional
import re

PILOT_FILE = Path(__file__).parent.parent / "output" / "property_pilot_2k.json"
LEXICON_V2 = Path(__file__).parent.parent / "output" / "lexicon_v2.db"
EMBEDDINGS_BIN = Path(__file__).parent.parent.parent.parent / "sprint-zero" / "data-pipeline" / "output" / "embeddings.bin"
EMBEDDINGS_IDX = Path(__file__).parent.parent.parent.parent / "sprint-zero" / "data-pipeline" / "output" / "embeddings.idx"

EMBEDDING_DIM = 100


def load_glove_index(idx_path: Path) -> Dict[str, int]:
    """Load word -> offset mapping from embeddings.idx."""
    index = {}
    with open(idx_path, 'r') as f:
        for line in f:
            parts = line.strip().split('\t')
            if len(parts) == 2:
                word, offset = parts
                index[word] = int(offset)
    return index


def get_embedding(word: str, index: Dict[str, int], bin_path: Path) -> Optional[bytes]:
    """Get embedding bytes for a word, or None if OOV."""
    if word not in index:
        return None

    offset = index[word]
    with open(bin_path, 'rb') as f:
        f.seek(offset)
        return f.read(EMBEDDING_DIM * 4)  # 100 floats * 4 bytes


def get_compound_embedding(text: str, index: Dict[str, int], bin_path: Path) -> Optional[bytes]:
    """Get averaged embedding for compound/hyphenated words."""
    # Split on hyphen or space
    parts = re.split(r'[-\s]', text)
    parts = [p.strip() for p in parts if p.strip()]

    if not parts:
        return None

    embeddings = []
    for part in parts:
        emb = get_embedding(part, index, bin_path)
        if emb:
            values = struct.unpack(f'{EMBEDDING_DIM}f', emb)
            embeddings.append(values)

    if not embeddings:
        return None

    # Average the embeddings
    avg = [sum(e[i] for e in embeddings) / len(embeddings) for i in range(EMBEDDING_DIM)]
    return struct.pack(f'{EMBEDDING_DIM}f', *avg)


def normalise(text: str) -> str:
    """Normalise property text."""
    return text.lower().strip()


def main():
    if not PILOT_FILE.exists():
        raise FileNotFoundError(f"Pilot file not found: {PILOT_FILE}")
    if not EMBEDDINGS_BIN.exists():
        raise FileNotFoundError(f"Embeddings not found: {EMBEDDINGS_BIN}")

    print("Loading pilot data...")
    with open(PILOT_FILE) as f:
        pilot = json.load(f)

    print("Loading GloVe index...")
    glove_index = load_glove_index(EMBEDDINGS_IDX)
    print(f"  {len(glove_index)} words in GloVe vocabulary")

    # Collect all unique properties
    all_props = set()
    for synset in pilot['synsets']:
        for prop in synset.get('properties', []):
            all_props.add(normalise(prop))

    print(f"  {len(all_props)} unique properties to process")

    # Process each property
    conn = sqlite3.connect(LEXICON_V2)

    oov_count = 0
    emb_count = 0

    for prop in sorted(all_props):
        # Try direct lookup first
        emb = get_embedding(prop, glove_index, EMBEDDINGS_BIN)

        # Try compound if direct fails
        if emb is None and ('-' in prop or ' ' in prop):
            emb = get_compound_embedding(prop, glove_index, EMBEDDINGS_BIN)

        is_oov = 1 if emb is None else 0
        if is_oov:
            oov_count += 1
        else:
            emb_count += 1

        conn.execute("""
            INSERT OR REPLACE INTO property_vocabulary (text, embedding, is_oov, source)
            VALUES (?, ?, ?, 'pilot')
        """, (prop, emb, is_oov))

    conn.commit()
    conn.close()

    print(f"\nCuration complete!")
    print(f"  Properties with embeddings: {emb_count}")
    print(f"  OOV properties: {oov_count}")
    print(f"  Coverage: {emb_count / len(all_props):.1%}")


if __name__ == "__main__":
    main()
```

### Step 3: Run curation

**Run:** `python data-pipeline/scripts/curate_properties.py`
**Expected:** Properties imported with embeddings, OOV flagged

### Step 4: Run tests

**Run:** `pytest data-pipeline/scripts/test_curate_properties.py -v`
**Expected:** PASS (all 5 tests)

### Step 5: Review OOV properties

**Run:**
```bash
sqlite3 data-pipeline/output/lexicon_v2.db "SELECT text FROM property_vocabulary WHERE is_oov = 1 ORDER BY text;"
```

**Manual review:** Check if any OOV properties should be split or corrected.

### Step 6: Commit

```bash
git add data-pipeline/scripts/curate_properties.py data-pipeline/scripts/test_curate_properties.py
git commit -m "feat: curate property vocabulary with GloVe embeddings

Normalise properties from 2k pilot, add GloVe 100d embeddings for fuzzy
matching. OOV properties flagged for review. Compound words handled via
averaged component embeddings."
```

---

## Task 6: VerbNet Selective Import

**Goal:** Import VerbNet classes, roles, and examples (skip syntactic frames)

**Files:**
- Create: `data-pipeline/scripts/import_verbnet.py`
- Create: `data-pipeline/scripts/test_import_verbnet.py`
- Input: `../../sqlunet_master.db` (VerbNet tables)
- Output: `data-pipeline/output/lexicon_v2.db`

### Step 1: Write test for VerbNet import

**File:** `data-pipeline/scripts/test_import_verbnet.py`

```python
"""Test VerbNet selective import."""
import sqlite3
from pathlib import Path
import pytest

LEXICON_V2 = Path(__file__).parent.parent / "output" / "lexicon_v2.db"

def test_classes_imported():
    """Verify vn_classes table populated."""
    conn = sqlite3.connect(LEXICON_V2)
    count = conn.execute("SELECT COUNT(*) FROM vn_classes").fetchone()[0]
    conn.close()
    assert count > 200, f"Expected 200+ VerbNet classes, got {count}"

def test_class_members_imported():
    """Verify vn_class_members links verbs to classes."""
    conn = sqlite3.connect(LEXICON_V2)
    count = conn.execute("SELECT COUNT(*) FROM vn_class_members").fetchone()[0]
    conn.close()
    assert count > 1000, f"Expected 1000+ class memberships, got {count}"

def test_roles_imported():
    """Verify vn_roles table populated."""
    conn = sqlite3.connect(LEXICON_V2)
    count = conn.execute("SELECT COUNT(*) FROM vn_roles").fetchone()[0]
    conn.close()
    assert count > 500, f"Expected 500+ theta roles, got {count}"

def test_examples_imported():
    """Verify vn_examples table populated."""
    conn = sqlite3.connect(LEXICON_V2)
    count = conn.execute("SELECT COUNT(*) FROM vn_examples").fetchone()[0]
    conn.close()
    assert count > 1000, f"Expected 1000+ examples, got {count}"
```

**Run:** `pytest data-pipeline/scripts/test_import_verbnet.py -v`
**Expected:** FAIL - tables empty

### Step 2: Explore sqlunet VerbNet schema

**Run:**
```bash
sqlite3 ../../sqlunet_master.db ".tables" | grep -i vn
sqlite3 ../../sqlunet_master.db ".schema vnclasses"
```

Identify exact table/column names for VerbNet data.

### Step 3: Write VerbNet import script

**File:** `data-pipeline/scripts/import_verbnet.py`

```python
"""Import VerbNet selective data (classes, roles, examples - skip frames)."""
import sqlite3
from pathlib import Path

SQLUNET_DB = Path(__file__).parent.parent.parent.parent.parent / "sqlunet_master.db"
LEXICON_V2 = Path(__file__).parent.parent / "output" / "lexicon_v2.db"


def import_classes(src: sqlite3.Connection, dst: sqlite3.Connection):
    """Import VerbNet classes."""
    print("Importing VerbNet classes...")
    # Adjust table/column names based on Step 2 exploration
    cursor = src.execute("SELECT classid, class FROM vnclasses")
    rows = [(row[0], row[1], None) for row in cursor]
    dst.executemany(
        "INSERT OR IGNORE INTO vn_classes (class_id, class_name, class_definition) VALUES (?, ?, ?)",
        rows
    )
    print(f"  Imported {len(rows)} classes")


def import_class_members(src: sqlite3.Connection, dst: sqlite3.Connection):
    """Import class membership (verb -> class links)."""
    print("Importing class memberships...")
    cursor = src.execute("""
        SELECT wordid, synsetid, classid, vnwordid
        FROM vnwords
        WHERE synsetid IS NOT NULL
    """)
    rows = list(cursor)
    dst.executemany(
        "INSERT OR IGNORE INTO vn_class_members (wordid, synsetid, classid, vnwordid) VALUES (?, ?, ?, ?)",
        rows
    )
    print(f"  Imported {len(rows)} memberships")


def import_roles(src: sqlite3.Connection, dst: sqlite3.Connection):
    """Import theta roles per class."""
    print("Importing theta roles...")
    cursor = src.execute("""
        SELECT roleid, classid, roletype
        FROM vnroles
    """)
    rows = list(cursor)
    dst.executemany(
        "INSERT OR IGNORE INTO vn_roles (role_id, class_id, theta_role) VALUES (?, ?, ?)",
        rows
    )
    print(f"  Imported {len(rows)} roles")


def import_examples(src: sqlite3.Connection, dst: sqlite3.Connection):
    """Import usage examples."""
    print("Importing examples...")
    cursor = src.execute("""
        SELECT exampleid, classid, example
        FROM vnexamples
    """)
    rows = list(cursor)
    dst.executemany(
        "INSERT OR IGNORE INTO vn_examples (example_id, class_id, example_text) VALUES (?, ?, ?)",
        rows
    )
    print(f"  Imported {len(rows)} examples")


def main():
    if not SQLUNET_DB.exists():
        raise FileNotFoundError(f"Source DB not found: {SQLUNET_DB}")
    if not LEXICON_V2.exists():
        raise FileNotFoundError(f"Target DB not found: {LEXICON_V2}")

    src = sqlite3.connect(SQLUNET_DB)
    dst = sqlite3.connect(LEXICON_V2)

    import_classes(src, dst)
    import_class_members(src, dst)
    import_roles(src, dst)
    import_examples(src, dst)

    dst.commit()
    src.close()
    dst.close()
    print("VerbNet import complete!")


if __name__ == "__main__":
    main()
```

### Step 4: Run import and tests

**Run:** `python data-pipeline/scripts/import_verbnet.py`
**Run:** `pytest data-pipeline/scripts/test_import_verbnet.py -v`
**Expected:** PASS

### Step 5: Commit

```bash
git add data-pipeline/scripts/import_verbnet.py data-pipeline/scripts/test_import_verbnet.py
git commit -m "feat: import VerbNet classes, roles, examples

Selective import: classes (600+), class memberships, theta roles,
and usage examples. Syntactic frames deliberately skipped (too detailed
for metaphor matching)."
```

---

## Task 7: SyntagNet Import

**Goal:** Import 87k collocation pairs for contiguity metonyms

**Files:**
- Create: `data-pipeline/scripts/import_syntagnet.py`
- Create: `data-pipeline/scripts/test_import_syntagnet.py`
- Input: `../../sqlunet_master.db` (SyntagNet tables)
- Output: `data-pipeline/output/lexicon_v2.db`

### Step 1: Write test for SyntagNet import

**File:** `data-pipeline/scripts/test_import_syntagnet.py`

```python
"""Test SyntagNet import."""
import sqlite3
from pathlib import Path
import pytest

LEXICON_V2 = Path(__file__).parent.parent / "output" / "lexicon_v2.db"

def test_syntagms_imported():
    """Verify syntagms table populated."""
    conn = sqlite3.connect(LEXICON_V2)
    count = conn.execute("SELECT COUNT(*) FROM syntagms").fetchone()[0]
    conn.close()
    assert count > 80000, f"Expected 80k+ syntagms, got {count}"

def test_syntagm_structure():
    """Verify syntagms have both synset links."""
    conn = sqlite3.connect(LEXICON_V2)
    row = conn.execute("""
        SELECT synset1id, synset2id, sensekey1, sensekey2
        FROM syntagms LIMIT 1
    """).fetchone()
    conn.close()

    assert row is not None
    assert row[0] is not None, "synset1id should not be null"
    assert row[1] is not None, "synset2id should not be null"

def test_syntagm_synset_links_valid():
    """Verify syntagms link to real synsets."""
    conn = sqlite3.connect(LEXICON_V2)
    # Check a sample of syntagms have valid synset references
    orphans = conn.execute("""
        SELECT COUNT(*) FROM syntagms st
        LEFT JOIN synsets s1 ON s1.synset_id = st.synset1id
        LEFT JOIN synsets s2 ON s2.synset_id = st.synset2id
        WHERE s1.synset_id IS NULL OR s2.synset_id IS NULL
    """).fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM syntagms").fetchone()[0]
    conn.close()

    orphan_rate = orphans / total if total > 0 else 0
    assert orphan_rate < 0.1, f"Expected <10% orphan syntagms, got {orphan_rate:.1%}"
```

**Run:** `pytest data-pipeline/scripts/test_import_syntagnet.py -v`
**Expected:** FAIL - table empty

### Step 2: Explore sqlunet SyntagNet schema

**Run:**
```bash
sqlite3 ../../sqlunet_master.db ".tables" | grep -i sn
sqlite3 ../../sqlunet_master.db ".schema snsyntagms"
```

### Step 3: Write SyntagNet import script

**File:** `data-pipeline/scripts/import_syntagnet.py`

```python
"""Import SyntagNet collocation pairs."""
import sqlite3
from pathlib import Path

SQLUNET_DB = Path(__file__).parent.parent.parent.parent.parent / "sqlunet_master.db"
LEXICON_V2 = Path(__file__).parent.parent / "output" / "lexicon_v2.db"


def import_syntagms(src: sqlite3.Connection, dst: sqlite3.Connection):
    """Import SyntagNet collocation pairs."""
    print("Importing SyntagNet syntagms...")
    # Adjust table/column names based on Step 2 exploration
    cursor = src.execute("""
        SELECT syntagmid, synset1id, synset2id, sensekey1, sensekey2, word1id, word2id
        FROM snsyntagms
    """)

    rows = [(row[0], str(row[1]), str(row[2]), row[3], row[4], row[5], row[6])
            for row in cursor]

    dst.executemany("""
        INSERT OR IGNORE INTO syntagms
        (syntagm_id, synset1id, synset2id, sensekey1, sensekey2, word1id, word2id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, rows)
    print(f"  Imported {len(rows)} syntagms")


def main():
    if not SQLUNET_DB.exists():
        raise FileNotFoundError(f"Source DB not found: {SQLUNET_DB}")
    if not LEXICON_V2.exists():
        raise FileNotFoundError(f"Target DB not found: {LEXICON_V2}")

    src = sqlite3.connect(SQLUNET_DB)
    dst = sqlite3.connect(LEXICON_V2)

    import_syntagms(src, dst)

    dst.commit()
    src.close()
    dst.close()
    print("SyntagNet import complete!")


if __name__ == "__main__":
    main()
```

### Step 4: Run import and tests

**Run:** `python data-pipeline/scripts/import_syntagnet.py`
**Run:** `pytest data-pipeline/scripts/test_import_syntagnet.py -v`
**Expected:** PASS

### Step 5: Commit

```bash
git add data-pipeline/scripts/import_syntagnet.py data-pipeline/scripts/test_import_syntagnet.py
git commit -m "feat: import SyntagNet collocation pairs

87k+ syntagms providing corpus-derived word associations for
contiguity-based metonyms. Each pair links two synsets that
frequently co-occur in text."
```

---

## Task 8: Populate synset_properties Junction Table

**Goal:** Link enriched synsets to their properties via the junction table

**Files:**
- Create: `data-pipeline/scripts/populate_synset_properties.py`
- Create: `data-pipeline/scripts/test_synset_properties.py`
- Input: `data-pipeline/output/property_pilot_2k.json`
- Output: `data-pipeline/output/lexicon_v2.db` (synset_properties table)

### Step 1: Write test

**File:** `data-pipeline/scripts/test_synset_properties.py`

```python
"""Test synset_properties junction table."""
import sqlite3
from pathlib import Path
import pytest

LEXICON_V2 = Path(__file__).parent.parent / "output" / "lexicon_v2.db"

def test_junction_populated():
    """Verify synset_properties has entries."""
    conn = sqlite3.connect(LEXICON_V2)
    count = conn.execute("SELECT COUNT(*) FROM synset_properties").fetchone()[0]
    conn.close()
    assert count > 10000, f"Expected 10k+ synset-property links, got {count}"

def test_properties_queryable():
    """Verify we can query properties for a synset."""
    conn = sqlite3.connect(LEXICON_V2)
    row = conn.execute("""
        SELECT sp.synset_id, pv.text, pv.embedding IS NOT NULL as has_emb
        FROM synset_properties sp
        JOIN property_vocabulary pv ON pv.property_id = sp.property_id
        LIMIT 1
    """).fetchone()
    conn.close()

    assert row is not None, "Should have at least one synset-property link"
```

### Step 2: Write population script

**File:** `data-pipeline/scripts/populate_synset_properties.py`

```python
"""Populate synset_properties junction table from pilot data."""
import json
import sqlite3
from pathlib import Path

PILOT_FILE = Path(__file__).parent.parent / "output" / "property_pilot_2k.json"
LEXICON_V2 = Path(__file__).parent.parent / "output" / "lexicon_v2.db"


def main():
    print("Loading pilot data...")
    with open(PILOT_FILE) as f:
        pilot = json.load(f)

    conn = sqlite3.connect(LEXICON_V2)

    # Build property_id lookup
    prop_ids = {}
    for row in conn.execute("SELECT property_id, text FROM property_vocabulary"):
        prop_ids[row[1]] = row[0]

    print(f"  {len(prop_ids)} properties in vocabulary")

    # Create enrichment entries and link properties
    links = 0
    for synset in pilot['synsets']:
        synset_id = synset['id']

        # Insert enrichment record
        conn.execute("""
            INSERT OR IGNORE INTO enrichment (synset_id, model_used)
            VALUES (?, 'gemini-2.5-flash')
        """, (synset_id,))

        # Link properties
        for prop in synset.get('properties', []):
            prop_norm = prop.lower().strip()
            if prop_norm in prop_ids:
                conn.execute("""
                    INSERT OR IGNORE INTO synset_properties (synset_id, property_id)
                    VALUES (?, ?)
                """, (synset_id, prop_ids[prop_norm]))
                links += 1

    conn.commit()
    conn.close()

    print(f"Created {links} synset-property links")


if __name__ == "__main__":
    main()
```

### Step 3: Run and test

**Run:** `python data-pipeline/scripts/populate_synset_properties.py`
**Run:** `pytest data-pipeline/scripts/test_synset_properties.py -v`
**Expected:** PASS

### Step 4: Commit

```bash
git add data-pipeline/scripts/populate_synset_properties.py data-pipeline/scripts/test_synset_properties.py
git commit -m "feat: populate synset_properties junction table

Link pilot synsets to their extracted properties. Enables querying
'all synsets with property X' and 'all properties for synset Y'."
```

---

## Task 9: Validation

**Goal:** Verify the complete pipeline against design examples

**Files:**
- Create: `data-pipeline/scripts/test_validation.py`

### Step 1: Write validation tests

**File:** `data-pipeline/scripts/test_validation.py`

```python
"""End-to-end validation of lexicon_v2.db."""
import sqlite3
import struct
from pathlib import Path
import pytest
import math

LEXICON_V2 = Path(__file__).parent.parent / "output" / "lexicon_v2.db"


def cosine_similarity(emb1: bytes, emb2: bytes) -> float:
    """Compute cosine similarity between two embedding blobs."""
    v1 = struct.unpack('100f', emb1)
    v2 = struct.unpack('100f', emb2)

    dot = sum(a * b for a, b in zip(v1, v2))
    mag1 = math.sqrt(sum(a * a for a in v1))
    mag2 = math.sqrt(sum(b * b for b in v2))

    if mag1 == 0 or mag2 == 0:
        return 0.0
    return dot / (mag1 * mag2)


def test_database_completeness():
    """Verify all expected tables have data."""
    conn = sqlite3.connect(LEXICON_V2)

    expected = {
        'synsets': 100000,
        'lemmas': 200000,
        'relations': 200000,
        'property_vocabulary': 500,
        'synset_properties': 10000,
        'vn_classes': 200,
        'syntagms': 80000,
    }

    for table, min_count in expected.items():
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        assert count >= min_count, f"{table}: expected {min_count}+, got {count}"

    conn.close()


def test_property_similarity_makes_sense():
    """Verify semantically similar properties have similar embeddings."""
    conn = sqlite3.connect(LEXICON_V2)

    # Get embeddings for properties we expect to be similar
    similar_pairs = [
        ('warm', 'hot'),
        ('quiet', 'silent'),
        ('fast', 'rapid'),
    ]

    for p1, p2 in similar_pairs:
        row1 = conn.execute(
            "SELECT embedding FROM property_vocabulary WHERE text = ?", (p1,)
        ).fetchone()
        row2 = conn.execute(
            "SELECT embedding FROM property_vocabulary WHERE text = ?", (p2,)
        ).fetchone()

        if row1 and row2 and row1[0] and row2[0]:
            sim = cosine_similarity(row1[0], row2[0])
            assert sim > 0.5, f"Expected {p1}/{p2} similarity > 0.5, got {sim:.2f}"

    conn.close()


def test_synset_property_query():
    """Verify we can query properties with embeddings for a synset."""
    conn = sqlite3.connect(LEXICON_V2)

    # Get a synset that has properties
    row = conn.execute("""
        SELECT sp.synset_id, COUNT(*) as prop_count
        FROM synset_properties sp
        GROUP BY sp.synset_id
        HAVING prop_count >= 5
        LIMIT 1
    """).fetchone()

    assert row is not None, "Should have synsets with 5+ properties"

    synset_id = row[0]

    # Get properties with embeddings
    props = conn.execute("""
        SELECT pv.text, pv.embedding
        FROM synset_properties sp
        JOIN property_vocabulary pv ON pv.property_id = sp.property_id
        WHERE sp.synset_id = ?
    """, (synset_id,)).fetchall()

    conn.close()

    assert len(props) >= 5
    emb_count = sum(1 for _, emb in props if emb is not None)
    assert emb_count >= 3, f"Expected 3+ properties with embeddings, got {emb_count}"


def test_verbnet_synset_link():
    """Verify VerbNet class members link to OEWN synsets."""
    conn = sqlite3.connect(LEXICON_V2)

    # Find a VerbNet member that links to a synset
    row = conn.execute("""
        SELECT vc.class_name, s.definition
        FROM vn_class_members vcm
        JOIN vn_classes vc ON vc.class_id = vcm.classid
        JOIN synsets s ON s.synset_id = vcm.synsetid
        LIMIT 1
    """).fetchone()

    conn.close()

    assert row is not None, "Should have VerbNet->synset links"


def test_syntagnet_provides_collocations():
    """Verify SyntagNet provides word associations."""
    conn = sqlite3.connect(LEXICON_V2)

    # Find syntagms with valid synset links
    row = conn.execute("""
        SELECT l1.lemma, l2.lemma
        FROM syntagms st
        JOIN lemmas l1 ON l1.synset_id = st.synset1id
        JOIN lemmas l2 ON l2.synset_id = st.synset2id
        LIMIT 5
    """).fetchall()

    conn.close()

    assert len(row) >= 1, "Should have SyntagNet collocations"
```

### Step 2: Run validation

**Run:** `pytest data-pipeline/scripts/test_validation.py -v`
**Expected:** PASS (all tests)

### Step 3: Commit

```bash
git add data-pipeline/scripts/test_validation.py
git commit -m "test: end-to-end validation of lexicon_v2.db

Verify database completeness, property embedding similarity,
synset-property queries, VerbNet links, and SyntagNet collocations."
```

---

## Success Criteria

Schema v2 pipeline is complete when:

1. ✅ 100-synset spike validates approach
2. ✅ Schema design with embeddings
3. ☐ OEWN imported (107k synsets, 200k+ lemmas/relations)
4. ☐ 2k pilot enrichment complete
5. ☐ Property vocabulary curated with embeddings (70%+ coverage)
6. ☐ VerbNet selective import (classes, roles, examples)
7. ☐ SyntagNet import (87k collocation pairs)
8. ☐ synset_properties junction table populated
9. ☐ All validation tests passing

---

## Execution Notes

**Dependencies:**
- Task 3 (OEWN) must complete before Task 4 (pilot uses synset data)
- Task 4 (pilot) must complete before Task 5 (curation uses pilot output)
- Task 5 (curation) must complete before Task 8 (junction table needs property_ids)
- Tasks 6, 7 can run in parallel after Task 3

**Manual steps:**
- After Task 5: Review OOV properties, decide if any need manual correction
- After Task 9: Spot-check sample queries for quality

**Venv:** Use sprint-zero venv for all scripts:
```bash
/home/msi/projects/metaforge/.worktrees/sprint-zero/data-pipeline/.venv/bin/python <script>
```
