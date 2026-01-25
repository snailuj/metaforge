# Sprint Zero Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the data pipeline and Metaphor Forge API to prove out the core infrastructure before 3D work.

**Architecture:** Python scripts preprocess data into SQLite + binary embeddings. Go API serves `/forge/suggest` endpoint. LLM extraction via Gemini Flash 2.5 Lite with extended enrichment fields.

**Tech Stack:** Python 3.11+ (data pipeline), Go 1.21+ (API), SQLite (database), Gemini Flash 2.5 Lite (LLM extraction)

---

## Prerequisites

Before starting, download these data sources:

| Source | URL | Size |
|--------|-----|------|
| Open English WordNet | https://en-word.net/static/english-wordnet-2020.db.gz | ~25MB |
| GloVe 100d | https://nlp.stanford.edu/data/glove.6B.zip | ~822MB (extract `glove.6B.100d.txt`) |
| SUBTLEX-UK | https://www.ugent.be/pp/experimentele-psychologie/en/research/documents/subtlexuk | ~2MB |

Place in `data-pipeline/raw/` directory.

---

## LLM Cost Estimates

**Model selection:** Start with cheapest, escalate if quality insufficient.

| Model | Input $/M | Output $/M | Pilot (1k) | Full (120k) |
|-------|-----------|------------|------------|-------------|
| gemini-2.5-flash-lite | $0.10 | $0.40 | ~$0.08 | ~$9 |
| gemini-2.5-flash | $0.30 | $2.50 | ~$0.43 | ~$50 |

**Strategy:** Try Lite first. If quality poor, climb the value chain.

---

## Task 1: Project Structure

**Files:**
- Create: `api/go.mod`
- Create: `api/cmd/metaforge/main.go`
- Create: `data-pipeline/requirements.txt`
- Create: `data-pipeline/scripts/__init__.py`

### Step 1.1: Create Go module

```bash
mkdir -p api/cmd/metaforge api/internal
cd api && go mod init github.com/snailuj/metaforge
```

### Step 1.2: Create minimal main.go

```go
// api/cmd/metaforge/main.go
package main

import "fmt"

func main() {
    fmt.Println("Metaforge API starting...")
}
```

### Step 1.3: Verify Go builds

Run: `cd api && go build ./cmd/metaforge`
Expected: No errors, binary created

### Step 1.4: Create Python environment

```bash
mkdir -p data-pipeline/scripts data-pipeline/raw data-pipeline/output
cd data-pipeline
python -m venv .venv
source .venv/bin/activate
```

### Step 1.5: Create requirements.txt

```text
# data-pipeline/requirements.txt
pytest>=7.0.0
google-generativeai>=0.8.0
tqdm>=4.0.0
```

### Step 1.6: Install dependencies

Run: `pip install -r requirements.txt`
Expected: All packages install successfully

### Step 1.7: Commit

```bash
git add api/ data-pipeline/
git commit -m "feat: scaffold Go API and Python data pipeline"
```

---

## Task 2: WordNet SQLite Import

**Files:**
- Create: `data-pipeline/scripts/01_import_wordnet.py`
- Create: `data-pipeline/scripts/test_01_import_wordnet.py`
- Output: `data-pipeline/output/lexicon.db`

### Step 2.1: Write failing test for synset extraction

```python
# data-pipeline/scripts/test_01_import_wordnet.py
import pytest
import sqlite3
from pathlib import Path

def test_lexicon_db_has_synsets():
    """Lexicon DB should contain synsets with definitions."""
    db_path = Path(__file__).parent.parent / "output" / "lexicon.db"
    assert db_path.exists(), "lexicon.db not found - run 01_import_wordnet.py first"

    conn = sqlite3.connect(db_path)
    cursor = conn.execute("SELECT COUNT(*) FROM synsets")
    count = cursor.fetchone()[0]
    conn.close()

    assert count > 100000, f"Expected >100k synsets, got {count}"

def test_synset_has_required_fields():
    """Each synset should have id, pos, and definition."""
    db_path = Path(__file__).parent.parent / "output" / "lexicon.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(
        "SELECT synset_id, pos, definition FROM synsets LIMIT 1"
    )
    row = cursor.fetchone()
    conn.close()

    assert row is not None
    synset_id, pos, definition = row
    assert synset_id is not None
    assert pos in ('n', 'v', 'a', 'r', 's')
    assert len(definition) > 0
```

### Step 2.2: Run test to verify it fails

Run: `cd data-pipeline && python -m pytest scripts/test_01_import_wordnet.py -v`
Expected: FAIL - lexicon.db not found

### Step 2.3: Write WordNet import script

```python
# data-pipeline/scripts/01_import_wordnet.py
"""
Import Open English WordNet SQLite into our lexicon database.
Extracts synsets, lemmas, and relationships.
"""
import sqlite3
import gzip
from pathlib import Path
from tqdm import tqdm

RAW_DIR = Path(__file__).parent.parent / "raw"
OUTPUT_DIR = Path(__file__).parent.parent / "output"

def create_schema(conn: sqlite3.Connection):
    """Create lexicon database schema."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS synsets (
            synset_id TEXT PRIMARY KEY,
            pos TEXT NOT NULL,
            definition TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS lemmas (
            lemma TEXT NOT NULL,
            synset_id TEXT NOT NULL,
            FOREIGN KEY (synset_id) REFERENCES synsets(synset_id),
            PRIMARY KEY (lemma, synset_id)
        );

        CREATE TABLE IF NOT EXISTS relations (
            source_synset TEXT NOT NULL,
            target_synset TEXT NOT NULL,
            relation_type TEXT NOT NULL,
            FOREIGN KEY (source_synset) REFERENCES synsets(synset_id),
            FOREIGN KEY (target_synset) REFERENCES synsets(synset_id)
        );

        CREATE INDEX IF NOT EXISTS idx_lemmas_lemma ON lemmas(lemma);
        CREATE INDEX IF NOT EXISTS idx_relations_source ON relations(source_synset);
        CREATE INDEX IF NOT EXISTS idx_relations_type ON relations(relation_type);
    """)

def import_wordnet():
    """Import WordNet data into lexicon.db."""
    OUTPUT_DIR.mkdir(exist_ok=True)

    # Source WordNet DB
    wn_db_path = RAW_DIR / "english-wordnet-2020.db"
    if not wn_db_path.exists():
        gz_path = RAW_DIR / "english-wordnet-2020.db.gz"
        if gz_path.exists():
            print(f"Decompressing {gz_path}...")
            with gzip.open(gz_path, 'rb') as f_in:
                with open(wn_db_path, 'wb') as f_out:
                    f_out.write(f_in.read())
        else:
            raise FileNotFoundError(f"WordNet DB not found at {wn_db_path} or {gz_path}")

    # Connect to source and destination
    src_conn = sqlite3.connect(wn_db_path)
    dst_conn = sqlite3.connect(OUTPUT_DIR / "lexicon.db")

    create_schema(dst_conn)

    # Import synsets
    print("Importing synsets...")
    cursor = src_conn.execute("""
        SELECT id, pos, definition FROM synsets
    """)
    synsets = cursor.fetchall()

    dst_conn.executemany(
        "INSERT OR REPLACE INTO synsets (synset_id, pos, definition) VALUES (?, ?, ?)",
        tqdm(synsets, desc="Synsets")
    )

    # Import lemmas (words)
    print("Importing lemmas...")
    cursor = src_conn.execute("""
        SELECT lemma, synset_id FROM senses
    """)
    lemmas = cursor.fetchall()

    dst_conn.executemany(
        "INSERT OR REPLACE INTO lemmas (lemma, synset_id) VALUES (?, ?)",
        tqdm(lemmas, desc="Lemmas")
    )

    # Import relations (synonymy, antonymy, hypernymy, etc.)
    print("Importing relations...")
    cursor = src_conn.execute("""
        SELECT source_synset, target_synset, relation_type FROM synset_relations
    """)
    relations = cursor.fetchall()

    dst_conn.executemany(
        "INSERT INTO relations (source_synset, target_synset, relation_type) VALUES (?, ?, ?)",
        tqdm(relations, desc="Relations")
    )

    dst_conn.commit()

    # Report stats
    synset_count = dst_conn.execute("SELECT COUNT(*) FROM synsets").fetchone()[0]
    lemma_count = dst_conn.execute("SELECT COUNT(*) FROM lemmas").fetchone()[0]
    relation_count = dst_conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0]

    print(f"\nImported:")
    print(f"  {synset_count:,} synsets")
    print(f"  {lemma_count:,} lemmas")
    print(f"  {relation_count:,} relations")

    src_conn.close()
    dst_conn.close()

if __name__ == "__main__":
    import_wordnet()
```

### Step 2.4: Run import script

Run: `cd data-pipeline && python scripts/01_import_wordnet.py`
Expected: Imports synsets, lemmas, relations with progress bars

### Step 2.5: Run test to verify it passes

Run: `cd data-pipeline && python -m pytest scripts/test_01_import_wordnet.py -v`
Expected: PASS

### Step 2.6: Commit

```bash
git add data-pipeline/
git commit -m "feat: import WordNet synsets to lexicon.db"
```

---

## Task 3: Frequency Data Import

**Files:**
- Create: `data-pipeline/scripts/02_import_frequency.py`
- Create: `data-pipeline/scripts/test_02_import_frequency.py`
- Modify: `data-pipeline/output/lexicon.db` (add frequency table)

### Step 3.1: Write failing test for frequency data

```python
# data-pipeline/scripts/test_02_import_frequency.py
import pytest
import sqlite3
from pathlib import Path

def test_frequency_table_exists():
    """Lexicon DB should have word frequency data."""
    db_path = Path(__file__).parent.parent / "output" / "lexicon.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='frequencies'"
    )
    result = cursor.fetchone()
    conn.close()
    assert result is not None, "frequencies table not found"

def test_frequency_has_rarity_tiers():
    """Words should have rarity classification."""
    db_path = Path(__file__).parent.parent / "output" / "lexicon.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(
        "SELECT DISTINCT rarity FROM frequencies"
    )
    rarities = {row[0] for row in cursor.fetchall()}
    conn.close()

    expected = {'common', 'uncommon', 'rare', 'archaic'}
    assert rarities == expected, f"Expected {expected}, got {rarities}"

def test_common_word_is_common():
    """High-frequency words should be classified as common."""
    db_path = Path(__file__).parent.parent / "output" / "lexicon.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(
        "SELECT rarity FROM frequencies WHERE lemma = 'the'"
    )
    result = cursor.fetchone()
    conn.close()
    assert result is not None, "'the' not found in frequencies"
    assert result[0] == 'common', f"'the' should be common, got {result[0]}"
```

### Step 3.2: Run test to verify it fails

Run: `cd data-pipeline && python -m pytest scripts/test_02_import_frequency.py -v`
Expected: FAIL - frequencies table not found

### Step 3.3: Write frequency import script

```python
# data-pipeline/scripts/02_import_frequency.py
"""
Import word frequency data from SUBTLEX-UK and classify into rarity tiers.

Rarity tiers based on Zipf frequency:
- common: Zipf >= 5 (very high frequency)
- uncommon: 4 <= Zipf < 5
- rare: 3 <= Zipf < 4
- archaic: Zipf < 3
"""
import sqlite3
import csv
from pathlib import Path
from tqdm import tqdm

RAW_DIR = Path(__file__).parent.parent / "raw"
OUTPUT_DIR = Path(__file__).parent.parent / "output"

# Zipf frequency thresholds
COMMON_THRESHOLD = 5.0
UNCOMMON_THRESHOLD = 4.0
RARE_THRESHOLD = 3.0

def classify_rarity(zipf: float) -> str:
    """Classify word rarity based on Zipf frequency."""
    if zipf >= COMMON_THRESHOLD:
        return 'common'
    elif zipf >= UNCOMMON_THRESHOLD:
        return 'uncommon'
    elif zipf >= RARE_THRESHOLD:
        return 'rare'
    else:
        return 'archaic'

def import_frequency():
    """Import SUBTLEX-UK frequency data."""
    # SUBTLEX-UK file (adjust filename as needed)
    freq_file = RAW_DIR / "SUBTLEX-UK.txt"
    if not freq_file.exists():
        # Try alternative names
        for name in ["SUBTLEX-UK.csv", "subtlex-uk.txt", "subtlex-uk.csv"]:
            alt = RAW_DIR / name
            if alt.exists():
                freq_file = alt
                break
        else:
            raise FileNotFoundError(f"SUBTLEX-UK not found in {RAW_DIR}")

    conn = sqlite3.connect(OUTPUT_DIR / "lexicon.db")

    # Create frequency table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS frequencies (
            lemma TEXT PRIMARY KEY,
            frequency INTEGER NOT NULL,
            zipf REAL NOT NULL,
            rarity TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_freq_rarity ON frequencies(rarity)")

    # Parse SUBTLEX-UK (tab or comma separated)
    print(f"Reading {freq_file}...")
    with open(freq_file, 'r', encoding='utf-8') as f:
        # Detect delimiter
        first_line = f.readline()
        delimiter = '\t' if '\t' in first_line else ','
        f.seek(0)

        reader = csv.DictReader(f, delimiter=delimiter)

        # Find relevant columns (SUBTLEX-UK has: Spelling, FreqCount, ... Zipf)
        rows = []
        for row in tqdm(reader, desc="Parsing frequencies"):
            lemma = row.get('Spelling') or row.get('Word') or row.get('spelling')
            zipf = row.get('Zipf') or row.get('SUBTLWF') or row.get('Lg10WF')
            freq = row.get('FreqCount') or row.get('FREQcount') or row.get('Freq')

            if lemma and zipf:
                try:
                    zipf_val = float(zipf)
                    freq_val = int(float(freq)) if freq else 0
                    rarity = classify_rarity(zipf_val)
                    rows.append((lemma.lower(), freq_val, zipf_val, rarity))
                except ValueError:
                    continue

    print(f"Inserting {len(rows):,} frequency entries...")
    conn.executemany(
        "INSERT OR REPLACE INTO frequencies (lemma, frequency, zipf, rarity) VALUES (?, ?, ?, ?)",
        rows
    )
    conn.commit()

    # Report stats
    stats = conn.execute("""
        SELECT rarity, COUNT(*) FROM frequencies GROUP BY rarity ORDER BY COUNT(*) DESC
    """).fetchall()

    print("\nRarity distribution:")
    for rarity, count in stats:
        print(f"  {rarity}: {count:,}")

    conn.close()

if __name__ == "__main__":
    import_frequency()
```

### Step 3.4: Run import script

Run: `cd data-pipeline && python scripts/02_import_frequency.py`
Expected: Imports frequency data with rarity classifications

### Step 3.5: Run test to verify it passes

Run: `cd data-pipeline && python -m pytest scripts/test_02_import_frequency.py -v`
Expected: PASS

### Step 3.6: Commit

```bash
git add data-pipeline/
git commit -m "feat: import frequency data with rarity tiers"
```

---

## Task 4: GloVe Embeddings

**Files:**
- Create: `data-pipeline/scripts/03_process_embeddings.py`
- Create: `data-pipeline/scripts/test_03_embeddings.py`
- Output: `data-pipeline/output/embeddings.bin`, `data-pipeline/output/embeddings.idx`

### Step 4.1: Write failing test for embeddings

```python
# data-pipeline/scripts/test_03_embeddings.py
import pytest
import struct
from pathlib import Path

def test_embeddings_file_exists():
    """Binary embeddings file should exist."""
    emb_path = Path(__file__).parent.parent / "output" / "embeddings.bin"
    assert emb_path.exists(), "embeddings.bin not found"

def test_embeddings_has_header():
    """Embeddings file should have vocab size and dimension in header."""
    emb_path = Path(__file__).parent.parent / "output" / "embeddings.bin"

    with open(emb_path, 'rb') as f:
        vocab_size, dim = struct.unpack('II', f.read(8))

    assert vocab_size > 10000, f"Expected >10k words, got {vocab_size}"
    assert dim == 100, f"Expected 100 dimensions, got {dim}"

def test_index_file_exists():
    """Word index file should exist."""
    index_path = Path(__file__).parent.parent / "output" / "embeddings.idx"
    assert index_path.exists(), "embeddings.idx not found"
```

### Step 4.2: Run test to verify it fails

Run: `cd data-pipeline && python -m pytest scripts/test_03_embeddings.py -v`
Expected: FAIL - embeddings.bin not found

### Step 4.3: Write embeddings processing script

```python
# data-pipeline/scripts/03_process_embeddings.py
"""
Process GloVe embeddings into binary format for fast loading.

Output format:
- embeddings.bin: Binary vectors (header: vocab_size, dim as uint32, then float32 vectors)
- embeddings.idx: JSON word-to-offset index
"""
import struct
import json
from pathlib import Path
from tqdm import tqdm

RAW_DIR = Path(__file__).parent.parent / "raw"
OUTPUT_DIR = Path(__file__).parent.parent / "output"

DIM = 100  # Using GloVe 100d

def process_embeddings():
    """Convert GloVe text format to binary."""
    glove_path = RAW_DIR / "glove.6B.100d.txt"
    if not glove_path.exists():
        raise FileNotFoundError(f"GloVe file not found at {glove_path}")

    OUTPUT_DIR.mkdir(exist_ok=True)

    # First pass: count lines
    print("Counting vocabulary...")
    with open(glove_path, 'r', encoding='utf-8') as f:
        vocab_size = sum(1 for _ in f)
    print(f"Found {vocab_size:,} words")

    # Second pass: write binary
    emb_path = OUTPUT_DIR / "embeddings.bin"
    idx_path = OUTPUT_DIR / "embeddings.idx"

    word_index = {}

    with open(glove_path, 'r', encoding='utf-8') as f_in:
        with open(emb_path, 'wb') as f_out:
            # Write header
            f_out.write(struct.pack('II', vocab_size, DIM))

            for i, line in enumerate(tqdm(f_in, total=vocab_size, desc="Processing")):
                parts = line.strip().split()
                word = parts[0]

                # Record offset (after header)
                offset = 8 + (i * DIM * 4)  # 8 byte header + position
                word_index[word] = offset

                # Parse and write vector
                try:
                    vector = [float(x) for x in parts[1:DIM+1]]
                    if len(vector) != DIM:
                        continue
                    f_out.write(struct.pack(f'{DIM}f', *vector))
                except ValueError:
                    continue

    # Write index
    with open(idx_path, 'w', encoding='utf-8') as f:
        json.dump(word_index, f)

    print(f"\nOutput:")
    print(f"  {emb_path}: {emb_path.stat().st_size / 1024 / 1024:.1f} MB")
    print(f"  {idx_path}: {idx_path.stat().st_size / 1024:.1f} KB")

if __name__ == "__main__":
    process_embeddings()
```

### Step 4.4: Run embeddings processing

Run: `cd data-pipeline && python scripts/03_process_embeddings.py`
Expected: Creates embeddings.bin and embeddings.idx

### Step 4.5: Run test to verify it passes

Run: `cd data-pipeline && python -m pytest scripts/test_03_embeddings.py -v`
Expected: PASS

### Step 4.6: Commit

```bash
git add data-pipeline/
git commit -m "feat: process GloVe embeddings to binary format"
```

---

## Task 5: Gemini Extended Enrichment (Pilot)

**Files:**
- Create: `data-pipeline/scripts/04_extract_enrichment.py`
- Create: `data-pipeline/scripts/test_04_enrichment.py`
- Modify: `data-pipeline/output/lexicon.db` (add enrichment table)

### Step 5.1: Write failing test for enrichment

```python
# data-pipeline/scripts/test_04_enrichment.py
import pytest
import sqlite3
import json
from pathlib import Path

def test_enrichment_table_exists():
    """Enrichment table should exist in lexicon.db."""
    db_path = Path(__file__).parent.parent / "output" / "lexicon.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='enrichment'"
    )
    result = cursor.fetchone()
    conn.close()
    assert result is not None, "enrichment table not found"

def test_pilot_synsets_have_enrichment():
    """Pilot synsets should have extracted enrichment data."""
    db_path = Path(__file__).parent.parent / "output" / "lexicon.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.execute("SELECT COUNT(*) FROM enrichment")
    count = cursor.fetchone()[0]
    conn.close()

    # Pilot is 1000 synsets
    assert count >= 500, f"Expected >=500 enrichment entries, got {count}"

def test_enrichment_has_all_fields():
    """Enrichment should include properties, metonyms, connotation, register, example."""
    db_path = Path(__file__).parent.parent / "output" / "lexicon.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.execute("""
        SELECT synset_id, properties, metonyms, connotation, register, usage_example
        FROM enrichment LIMIT 10
    """)

    for row in cursor:
        synset_id, props, metonyms, connotation, register, example = row

        # Properties required
        props_list = json.loads(props)
        assert isinstance(props_list, list), f"{synset_id}: properties should be list"
        assert len(props_list) >= 3, f"{synset_id}: expected 3+ properties"

        # Connotation should be valid value
        assert connotation in ('positive', 'neutral', 'negative', None), \
            f"{synset_id}: invalid connotation {connotation}"

        # Register should be valid value
        assert register in ('formal', 'neutral', 'informal', 'slang', None), \
            f"{synset_id}: invalid register {register}"

    conn.close()
```

### Step 5.2: Run test to verify it fails

Run: `cd data-pipeline && python -m pytest scripts/test_04_enrichment.py -v`
Expected: FAIL - enrichment table not found

### Step 5.3: Write extended enrichment extraction script

```python
# data-pipeline/scripts/04_extract_enrichment.py
"""
Extract enriched data from synsets using Gemini Flash.

Extracts in a single call:
- Structural properties (for metaphor matching)
- Metonyms (2-3 per word)
- Connotation (positive/neutral/negative)
- Register (formal/neutral/informal/slang)
- Usage example (1-2 sentences)

Uses Gemini Flash 2.5 Lite by default. Escalate to Flash 2.5 or 3.0 if quality poor.
"""
import sqlite3
import json
import os
import time
from pathlib import Path
from typing import List, Dict, Optional
from tqdm import tqdm

try:
    import google.generativeai as genai
except ImportError:
    raise ImportError("Run: pip install google-generativeai")

RAW_DIR = Path(__file__).parent.parent / "raw"
OUTPUT_DIR = Path(__file__).parent.parent / "output"

BATCH_SIZE = 30  # Synsets per API call
RATE_LIMIT_DELAY = 1.0  # Seconds between calls

# Model selection - start with cheapest, escalate if quality poor
# Options: "gemini-2.5-flash-lite", "gemini-2.5-flash"
MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")

EXTRACTION_PROMPT = """You are extracting enriched linguistic data from word senses.

For each word sense, extract:
1. **properties**: 5-10 abstract/structural properties describing what it DOES, how it BEHAVES, or what ROLE it plays. Focus on properties that could apply to things in OTHER domains.
2. **metonyms**: 2-3 words commonly used as metonyms for this concept (e.g., "crown" for "monarchy"). Return empty array if none.
3. **connotation**: "positive", "neutral", or "negative"
4. **register**: "formal", "neutral", "informal", or "slang"
5. **usage_example**: One natural sentence using this word sense.

Return JSONL (one JSON object per line).

---

Input:
anchor.n.01 | a mechanical device that prevents a vessel from moving
river.n.01 | a large natural stream of water
grief.n.01 | intense sorrow caused by loss

Output:
{"id": "anchor.n.01", "properties": ["holds_in_place", "prevents_drift", "provides_stability", "heavy", "deployed_deliberately"], "metonyms": [], "connotation": "neutral", "register": "neutral", "usage_example": "The captain ordered the crew to drop anchor in the sheltered bay."}
{"id": "river.n.01", "properties": ["flows", "carries_things", "has_source_and_destination", "shaped_by_terrain", "can_overflow", "erodes_over_time"], "metonyms": [], "connotation": "neutral", "register": "neutral", "usage_example": "The river wound through the valley, carving its path over centuries."}
{"id": "grief.n.01", "properties": ["heavy", "comes_in_waves", "holds_in_place", "isolating", "gradually_subsides", "requires_processing"], "metonyms": ["tears", "mourning"], "connotation": "negative", "register": "neutral", "usage_example": "Her grief was overwhelming in the weeks after the funeral."}

---

Input:
{batch}

Output:
"""

def get_synsets_for_pilot(conn: sqlite3.Connection, limit: int = 1000) -> List[Dict]:
    """Get pilot synsets: high frequency + good POS coverage."""
    cursor = conn.execute("""
        SELECT s.synset_id, s.definition
        FROM synsets s
        JOIN lemmas l ON s.synset_id = l.synset_id
        JOIN frequencies f ON l.lemma = f.lemma
        WHERE s.pos IN ('n', 'v', 'a')
        GROUP BY s.synset_id
        ORDER BY MAX(f.zipf) DESC
        LIMIT ?
    """, (limit,))

    return [{"id": row[0], "definition": row[1]} for row in cursor.fetchall()]

def extract_batch(model, synsets: List[Dict]) -> List[Dict]:
    """Extract enrichment for a batch of synsets."""
    batch_input = "\n".join(
        f"{s['id']} | {s['definition']}" for s in synsets
    )

    prompt = EXTRACTION_PROMPT.replace("{batch}", batch_input)

    response = model.generate_content(prompt)

    # Parse JSONL output
    results = []
    for line in response.text.strip().split('\n'):
        line = line.strip()
        if line.startswith('{'):
            try:
                obj = json.loads(line)
                if 'id' in obj and 'properties' in obj:
                    results.append(obj)
            except json.JSONDecodeError:
                continue

    return results

def extract_enrichment():
    """Main extraction pipeline."""
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        raise ValueError("Set GEMINI_API_KEY environment variable")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(MODEL_NAME)

    print(f"Using model: {MODEL_NAME}")

    conn = sqlite3.connect(OUTPUT_DIR / "lexicon.db")

    # Create enrichment table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS enrichment (
            synset_id TEXT PRIMARY KEY,
            properties TEXT NOT NULL,
            metonyms TEXT,
            connotation TEXT,
            register TEXT,
            usage_example TEXT,
            model_used TEXT,
            extracted_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_enrichment_synset ON enrichment(synset_id)")

    # Get pilot synsets
    synsets = get_synsets_for_pilot(conn, limit=1000)
    print(f"Processing {len(synsets)} synsets...")

    success_count = 0
    error_count = 0

    # Process in batches
    for i in tqdm(range(0, len(synsets), BATCH_SIZE), desc="Batches"):
        batch = synsets[i:i + BATCH_SIZE]

        try:
            results = extract_batch(model, batch)

            # Store results
            for r in results:
                conn.execute("""
                    INSERT OR REPLACE INTO enrichment
                    (synset_id, properties, metonyms, connotation, register, usage_example, model_used)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    r['id'],
                    json.dumps(r.get('properties', [])),
                    json.dumps(r.get('metonyms', [])),
                    r.get('connotation'),
                    r.get('register'),
                    r.get('usage_example'),
                    MODEL_NAME
                ))
                success_count += 1

            conn.commit()

        except Exception as e:
            print(f"\nError on batch {i}: {e}")
            error_count += len(batch)
            continue

        # Rate limiting
        time.sleep(RATE_LIMIT_DELAY)

    # Report
    print(f"\nExtracted enrichment for {success_count} synsets")
    print(f"Errors: {error_count}")

    # Sample output for quality review
    print("\n--- Sample output for quality review ---")
    cursor = conn.execute("""
        SELECT synset_id, properties, metonyms, connotation, register, usage_example
        FROM enrichment LIMIT 5
    """)
    for row in cursor:
        print(f"\n{row[0]}:")
        print(f"  Properties: {row[1]}")
        print(f"  Metonyms: {row[2]}")
        print(f"  Connotation: {row[3]}, Register: {row[4]}")
        print(f"  Example: {row[5]}")

    conn.close()

if __name__ == "__main__":
    extract_enrichment()
```

### Step 5.4: Run extraction (requires GEMINI_API_KEY)

Run: `GEMINI_API_KEY=your_key python scripts/04_extract_enrichment.py`
Expected: Extracts enrichment for ~1000 synsets, shows sample output

### Step 5.5: Review quality and escalate if needed

If quality is poor with Lite:
```bash
# Try Flash 2.5 (standard)
GEMINI_MODEL=gemini-2.5-flash GEMINI_API_KEY=your_key python scripts/04_extract_enrichment.py
```

### Step 5.6: Run test to verify it passes

Run: `cd data-pipeline && python -m pytest scripts/test_04_enrichment.py -v`
Expected: PASS

### Step 5.7: Commit

```bash
git add data-pipeline/
git commit -m "feat: extract extended enrichment via Gemini Flash"
```

---

## Task 6: Go API - Database Layer

**Files:**
- Create: `api/internal/db/db.go`
- Create: `api/internal/db/db_test.go`

### Step 6.1: Write failing test for DB connection

```go
// api/internal/db/db_test.go
package db

import (
    "testing"
)

func TestOpenDatabase(t *testing.T) {
    db, err := Open("../../data-pipeline/output/lexicon.db")
    if err != nil {
        t.Fatalf("Failed to open database: %v", err)
    }
    defer db.Close()

    var count int
    err = db.QueryRow("SELECT COUNT(*) FROM synsets").Scan(&count)
    if err != nil {
        t.Fatalf("Failed to query synsets: %v", err)
    }

    if count < 100000 {
        t.Errorf("Expected >100k synsets, got %d", count)
    }
}

func TestGetSynsetWithEnrichment(t *testing.T) {
    db, err := Open("../../data-pipeline/output/lexicon.db")
    if err != nil {
        t.Fatalf("Failed to open database: %v", err)
    }
    defer db.Close()

    synset, err := GetSynset(db, "grief.n.01")
    if err != nil {
        t.Fatalf("Failed to get synset: %v", err)
    }

    if synset.ID != "grief.n.01" {
        t.Errorf("Expected grief.n.01, got %s", synset.ID)
    }

    if len(synset.Properties) == 0 {
        t.Error("Expected properties from enrichment")
    }
}
```

### Step 6.2: Run test to verify it fails

Run: `cd api && go test ./internal/db/... -v`
Expected: FAIL - package not found

### Step 6.3: Write database layer

```go
// api/internal/db/db.go
package db

import (
    "database/sql"
    "encoding/json"
    "fmt"

    _ "github.com/mattn/go-sqlite3"
)

// Synset represents a WordNet synset with enrichment
type Synset struct {
    ID           string   `json:"id"`
    POS          string   `json:"pos"`
    Definition   string   `json:"definition"`
    Properties   []string `json:"properties,omitempty"`
    Metonyms     []string `json:"metonyms,omitempty"`
    Connotation  string   `json:"connotation,omitempty"`
    Register     string   `json:"register,omitempty"`
    UsageExample string   `json:"usage_example,omitempty"`
    Rarity       string   `json:"rarity,omitempty"`
}

// Open opens the lexicon database
func Open(path string) (*sql.DB, error) {
    return sql.Open("sqlite3", path+"?mode=ro")
}

// GetSynset retrieves a synset by ID with enrichment
func GetSynset(db *sql.DB, synsetID string) (*Synset, error) {
    var s Synset
    var propsJSON, metonymsJSON sql.NullString

    err := db.QueryRow(`
        SELECT s.synset_id, s.pos, s.definition,
               e.properties, e.metonyms, e.connotation, e.register, e.usage_example
        FROM synsets s
        LEFT JOIN enrichment e ON s.synset_id = e.synset_id
        WHERE s.synset_id = ?
    `, synsetID).Scan(&s.ID, &s.POS, &s.Definition,
        &propsJSON, &metonymsJSON, &s.Connotation, &s.Register, &s.UsageExample)

    if err != nil {
        return nil, fmt.Errorf("synset not found: %s", synsetID)
    }

    if propsJSON.Valid {
        json.Unmarshal([]byte(propsJSON.String), &s.Properties)
    }
    if metonymsJSON.Valid {
        json.Unmarshal([]byte(metonymsJSON.String), &s.Metonyms)
    }

    return &s, nil
}

// GetSynsetsWithSharedProperties finds synsets sharing properties with source
func GetSynsetsWithSharedProperties(db *sql.DB, sourceID string) ([]SynsetMatch, error) {
    source, err := GetSynset(db, sourceID)
    if err != nil {
        return nil, err
    }

    if len(source.Properties) == 0 {
        return nil, fmt.Errorf("source synset has no properties")
    }

    rows, err := db.Query(`
        SELECT synset_id, properties FROM enrichment WHERE synset_id != ?
    `, sourceID)
    if err != nil {
        return nil, err
    }
    defer rows.Close()

    sourceProps := make(map[string]bool)
    for _, p := range source.Properties {
        sourceProps[p] = true
    }

    var matches []SynsetMatch
    for rows.Next() {
        var id, propsJSON string
        if err := rows.Scan(&id, &propsJSON); err != nil {
            continue
        }

        var props []string
        if err := json.Unmarshal([]byte(propsJSON), &props); err != nil {
            continue
        }

        var shared []string
        for _, p := range props {
            if sourceProps[p] {
                shared = append(shared, p)
            }
        }

        if len(shared) > 0 {
            matches = append(matches, SynsetMatch{
                SynsetID:         id,
                SharedProperties: shared,
                OverlapCount:     len(shared),
            })
        }
    }

    return matches, nil
}

// SynsetMatch represents a candidate match
type SynsetMatch struct {
    SynsetID         string   `json:"synset_id"`
    SharedProperties []string `json:"shared_properties"`
    OverlapCount     int      `json:"overlap_count"`
    Distance         float64  `json:"distance"`
    Tier             string   `json:"tier"`
}
```

### Step 6.4: Add sqlite3 dependency

Run: `cd api && go get github.com/mattn/go-sqlite3`

### Step 6.5: Run test to verify it passes

Run: `cd api && go test ./internal/db/... -v`
Expected: PASS

### Step 6.6: Commit

```bash
git add api/
git commit -m "feat: add Go database layer with enrichment support"
```

---

## Task 7: Go API - Embeddings Layer

**Files:**
- Create: `api/internal/embeddings/embeddings.go`
- Create: `api/internal/embeddings/embeddings_test.go`

### Step 7.1: Write failing test for embeddings

```go
// api/internal/embeddings/embeddings_test.go
package embeddings

import (
    "testing"
)

func TestLoadEmbeddings(t *testing.T) {
    e, err := Load(
        "../../data-pipeline/output/embeddings.bin",
        "../../data-pipeline/output/embeddings.idx",
    )
    if err != nil {
        t.Fatalf("Failed to load embeddings: %v", err)
    }
    defer e.Close()

    if e.VocabSize() < 10000 {
        t.Errorf("Expected >10k vocab, got %d", e.VocabSize())
    }
}

func TestDistance(t *testing.T) {
    e, err := Load(
        "../../data-pipeline/output/embeddings.bin",
        "../../data-pipeline/output/embeddings.idx",
    )
    if err != nil {
        t.Fatalf("Failed to load embeddings: %v", err)
    }
    defer e.Close()

    distKingQueen, _ := e.Distance("king", "queen")
    distKingBanana, _ := e.Distance("king", "banana")

    if distKingQueen >= distKingBanana {
        t.Errorf("Expected king-queen closer than king-banana")
    }
}
```

### Step 7.2: Run test to verify it fails

Run: `cd api && go test ./internal/embeddings/... -v`
Expected: FAIL - package not found

### Step 7.3: Write embeddings layer

```go
// api/internal/embeddings/embeddings.go
package embeddings

import (
    "encoding/binary"
    "encoding/json"
    "fmt"
    "math"
    "os"
)

type Embeddings struct {
    file      *os.File
    index     map[string]int64
    vocabSize uint32
    dimension uint32
}

func Load(binPath, idxPath string) (*Embeddings, error) {
    f, err := os.Open(binPath)
    if err != nil {
        return nil, fmt.Errorf("failed to open embeddings: %w", err)
    }

    var vocabSize, dim uint32
    binary.Read(f, binary.LittleEndian, &vocabSize)
    binary.Read(f, binary.LittleEndian, &dim)

    idxData, err := os.ReadFile(idxPath)
    if err != nil {
        f.Close()
        return nil, fmt.Errorf("failed to read index: %w", err)
    }

    var index map[string]int64
    json.Unmarshal(idxData, &index)

    return &Embeddings{
        file:      f,
        index:     index,
        vocabSize: vocabSize,
        dimension: dim,
    }, nil
}

func (e *Embeddings) Close() error {
    return e.file.Close()
}

func (e *Embeddings) VocabSize() int {
    return int(e.vocabSize)
}

func (e *Embeddings) GetVector(word string) ([]float32, error) {
    offset, ok := e.index[word]
    if !ok {
        return nil, fmt.Errorf("word not found: %s", word)
    }

    e.file.Seek(offset, 0)
    vec := make([]float32, e.dimension)
    binary.Read(e.file, binary.LittleEndian, &vec)
    return vec, nil
}

func (e *Embeddings) Distance(word1, word2 string) (float64, error) {
    v1, err := e.GetVector(word1)
    if err != nil {
        return 0, err
    }
    v2, err := e.GetVector(word2)
    if err != nil {
        return 0, err
    }
    return cosineDistance(v1, v2), nil
}

func cosineDistance(a, b []float32) float64 {
    var dot, normA, normB float64
    for i := range a {
        dot += float64(a[i] * b[i])
        normA += float64(a[i] * a[i])
        normB += float64(b[i] * b[i])
    }
    if normA == 0 || normB == 0 {
        return 1.0
    }
    return 1.0 - (dot / (math.Sqrt(normA) * math.Sqrt(normB)))
}
```

### Step 7.4: Run test to verify it passes

Run: `cd api && go test ./internal/embeddings/... -v`
Expected: PASS

### Step 7.5: Commit

```bash
git add api/
git commit -m "feat: add Go embeddings layer with cosine distance"
```

---

## Task 8: Go API - Forge Matching Algorithm

**Files:**
- Create: `api/internal/forge/forge.go`
- Create: `api/internal/forge/forge_test.go`

### Step 8.1: Write failing test for tier classification

```go
// api/internal/forge/forge_test.go
package forge

import (
    "testing"
)

func TestClassifyTier(t *testing.T) {
    tests := []struct {
        name     string
        distance float64
        overlap  int
        expected Tier
    }{
        {"legendary", 0.8, 4, TierLegendary},
        {"interesting", 0.8, 1, TierInteresting},
        {"strong", 0.8, 2, TierStrong},
        {"obvious", 0.3, 3, TierObvious},
        {"unlikely", 0.3, 1, TierUnlikely},
    }

    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            tier := ClassifyTier(tt.distance, tt.overlap)
            if tier != tt.expected {
                t.Errorf("ClassifyTier(%v, %d) = %v, want %v",
                    tt.distance, tt.overlap, tier, tt.expected)
            }
        })
    }
}
```

### Step 8.2: Run test to verify it fails

Run: `cd api && go test ./internal/forge/... -v`
Expected: FAIL - package not found

### Step 8.3: Write forge matching algorithm

```go
// api/internal/forge/forge.go
package forge

import "sort"

type Tier int

const (
    TierLegendary Tier = iota
    TierInteresting
    TierStrong
    TierObvious
    TierUnlikely
)

func (t Tier) String() string {
    return [...]string{"legendary", "interesting", "strong", "obvious", "unlikely"}[t]
}

const (
    HighDistanceThreshold = 0.6
    MinOverlap            = 2
    StrongOverlap         = 3
)

type Match struct {
    SynsetID         string   `json:"synset_id"`
    Word             string   `json:"word"`
    SharedProperties []string `json:"shared_properties"`
    OverlapCount     int      `json:"overlap_count"`
    Distance         float64  `json:"distance"`
    Tier             Tier     `json:"tier"`
    TierName         string   `json:"tier_name"`
}

func ClassifyTier(distance float64, overlap int) Tier {
    highDistance := distance > HighDistanceThreshold
    strongOverlap := overlap >= StrongOverlap
    minOverlap := overlap >= MinOverlap

    if highDistance && strongOverlap {
        return TierLegendary
    }
    if highDistance && !minOverlap {
        return TierInteresting
    }
    if highDistance && minOverlap {
        return TierStrong
    }
    if !highDistance && minOverlap {
        return TierObvious
    }
    return TierUnlikely
}

func SortByTier(matches []Match) []Match {
    sorted := make([]Match, len(matches))
    copy(sorted, matches)

    sort.Slice(sorted, func(i, j int) bool {
        if sorted[i].Tier != sorted[j].Tier {
            return sorted[i].Tier < sorted[j].Tier
        }
        if sorted[i].OverlapCount != sorted[j].OverlapCount {
            return sorted[i].OverlapCount > sorted[j].OverlapCount
        }
        return sorted[i].Distance > sorted[j].Distance
    })

    return sorted
}
```

### Step 8.4: Run test to verify it passes

Run: `cd api && go test ./internal/forge/... -v`
Expected: PASS

### Step 8.5: Commit

```bash
git add api/
git commit -m "feat: add 5-tier metaphor matching algorithm"
```

---

## Task 9: Go API - HTTP Endpoint

**Files:**
- Create: `api/internal/handler/forge.go`
- Create: `api/internal/handler/forge_test.go`
- Modify: `api/cmd/metaforge/main.go`

### Step 9.1: Write failing test for endpoint

```go
// api/internal/handler/forge_test.go
package handler

import (
    "encoding/json"
    "net/http"
    "net/http/httptest"
    "testing"
)

func TestForgeSuggestEndpoint(t *testing.T) {
    h, err := NewForgeHandler(
        "../../data-pipeline/output/lexicon.db",
        "../../data-pipeline/output/embeddings.bin",
        "../../data-pipeline/output/embeddings.idx",
    )
    if err != nil {
        t.Fatalf("Failed to create handler: %v", err)
    }

    req := httptest.NewRequest("GET", "/forge/suggest?source=grief", nil)
    w := httptest.NewRecorder()

    h.HandleSuggest(w, req)

    if w.Code != http.StatusOK {
        t.Fatalf("Expected 200, got %d: %s", w.Code, w.Body.String())
    }

    var resp SuggestResponse
    if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
        t.Fatalf("Failed to parse response: %v", err)
    }

    if len(resp.Suggestions) == 0 {
        t.Error("Expected suggestions, got none")
    }
}
```

### Step 9.2: Run test to verify it fails

Run: `cd api && go test ./internal/handler/... -v`
Expected: FAIL - package not found

### Step 9.3: Write forge handler

```go
// api/internal/handler/forge.go
package handler

import (
    "database/sql"
    "encoding/json"
    "net/http"

    "github.com/snailuj/metaforge/internal/db"
    "github.com/snailuj/metaforge/internal/embeddings"
    "github.com/snailuj/metaforge/internal/forge"
)

type ForgeHandler struct {
    database *sql.DB
    emb      *embeddings.Embeddings
}

func NewForgeHandler(dbPath, embPath, idxPath string) (*ForgeHandler, error) {
    database, err := db.Open(dbPath)
    if err != nil {
        return nil, err
    }

    emb, err := embeddings.Load(embPath, idxPath)
    if err != nil {
        return nil, err
    }

    return &ForgeHandler{database: database, emb: emb}, nil
}

type SuggestResponse struct {
    Source      string        `json:"source"`
    Suggestions []forge.Match `json:"suggestions"`
}

func (h *ForgeHandler) HandleSuggest(w http.ResponseWriter, r *http.Request) {
    source := r.URL.Query().Get("source")
    if source == "" {
        http.Error(w, "missing source parameter", http.StatusBadRequest)
        return
    }

    synsetID, err := h.findSynsetForWord(source)
    if err != nil {
        http.Error(w, err.Error(), http.StatusNotFound)
        return
    }

    candidates, err := db.GetSynsetsWithSharedProperties(h.database, synsetID)
    if err != nil {
        http.Error(w, err.Error(), http.StatusInternalServerError)
        return
    }

    var matches []forge.Match
    for _, c := range candidates {
        word, _ := h.getWordForSynset(c.SynsetID)
        dist, _ := h.emb.Distance(source, word)
        if dist == 0 {
            dist = 0.5
        }

        tier := forge.ClassifyTier(dist, c.OverlapCount)
        matches = append(matches, forge.Match{
            SynsetID:         c.SynsetID,
            Word:             word,
            SharedProperties: c.SharedProperties,
            OverlapCount:     c.OverlapCount,
            Distance:         dist,
            Tier:             tier,
            TierName:         tier.String(),
        })
    }

    sorted := forge.SortByTier(matches)
    if len(sorted) > 50 {
        sorted = sorted[:50]
    }

    w.Header().Set("Content-Type", "application/json")
    json.NewEncoder(w).Encode(SuggestResponse{
        Source:      source,
        Suggestions: sorted,
    })
}

func (h *ForgeHandler) findSynsetForWord(word string) (string, error) {
    var synsetID string
    err := h.database.QueryRow(
        "SELECT synset_id FROM lemmas WHERE lemma = ? LIMIT 1", word,
    ).Scan(&synsetID)
    return synsetID, err
}

func (h *ForgeHandler) getWordForSynset(synsetID string) (string, error) {
    var word string
    err := h.database.QueryRow(
        "SELECT lemma FROM lemmas WHERE synset_id = ? LIMIT 1", synsetID,
    ).Scan(&word)
    return word, err
}
```

### Step 9.4: Update main.go

```go
// api/cmd/metaforge/main.go
package main

import (
    "fmt"
    "log"
    "net/http"

    "github.com/go-chi/chi/v5"
    "github.com/go-chi/chi/v5/middleware"
    "github.com/snailuj/metaforge/internal/handler"
)

func main() {
    dbPath := "../data-pipeline/output/lexicon.db"
    embPath := "../data-pipeline/output/embeddings.bin"
    idxPath := "../data-pipeline/output/embeddings.idx"

    forgeHandler, err := handler.NewForgeHandler(dbPath, embPath, idxPath)
    if err != nil {
        log.Fatalf("Failed to create handler: %v", err)
    }

    r := chi.NewRouter()
    r.Use(middleware.Logger)
    r.Use(middleware.Recoverer)

    r.Get("/forge/suggest", forgeHandler.HandleSuggest)

    fmt.Println("Metaforge API starting on :8080...")
    log.Fatal(http.ListenAndServe(":8080", r))
}
```

### Step 9.5: Add chi dependency

Run: `cd api && go get github.com/go-chi/chi/v5`

### Step 9.6: Run test to verify it passes

Run: `cd api && go test ./internal/handler/... -v`
Expected: PASS

### Step 9.7: Commit

```bash
git add api/
git commit -m "feat: add /forge/suggest HTTP endpoint"
```

---

## Task 10: End-to-End Verification

### Step 10.1: Start the API

```bash
cd api && go run ./cmd/metaforge
```

### Step 10.2: Test with curl

```bash
curl "http://localhost:8080/forge/suggest?source=grief"
```

Expected: JSON with tiered suggestions including shared properties, distances, and tier names.

### Step 10.3: Verify tier distribution

Check that results include multiple tiers.

### Step 10.4: Final commit

```bash
git add -A
git commit -m "feat: complete Sprint Zero - Metaphor Forge data pipeline"
```

---

## Deliverables Checklist

| Deliverable | Status |
|-------------|--------|
| Go project structure | ☐ |
| WordNet imported to SQLite | ☐ |
| Frequency data with rarity tiers | ☐ |
| GloVe embeddings in binary format | ☐ |
| Extended Gemini enrichment (1k pilot) | ☐ |
| 5-tier matching algorithm | ☐ |
| `/forge/suggest` endpoint working | ☐ |
| All tests passing | ☐ |

---

## Notes for Future Phases

1. **Full corpus enrichment** — If pilot quality is acceptable, run full 120k synsets (~$9 with Flash 2.5 Lite)
2. **Research spikes** — Pull and investigate Etymological WordNet, ConceptNet SymbolOf for additional data
3. **String handling** — Fluent integration for UI strings
4. **Forge UI** — Build frontend with tier colours, hint system, Grimoire
