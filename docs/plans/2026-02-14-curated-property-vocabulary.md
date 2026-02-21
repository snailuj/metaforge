# Curated Property Vocabulary Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace free-form FastText-based property matching with a curated canonical vocabulary, enabling set-intersection forge matching and antonym-based "Ironic" tier discovery.

**Architecture:** Build-time pipeline — Python scripts build vocabulary from WordNet (least-polysemous lemma per synset), snap extracted properties to canonical entries (exact → morphological → embedding), populate antonym table from attribute relations. Go API replaces the cosine-distance mega-query with integer JOIN counting. Frontend adds Ironic/Complex tier colours.

**Tech Stack:** Python (sqlite3, nltk, numpy, struct) for pipeline, Go for API, Lit/TypeScript for frontend, pytest + `go test` + Vitest for tests.

---

## Batch 1: Pipeline — Vocabulary Build

### Task 1: Add vocabulary build script with lemma polysemy selection

Build the curated vocabulary from the top 35k synsets, picking the least-polysemous lemma for each.

**Files:**
- Create: `data-pipeline/scripts/build_vocab.py`
- Create: `data-pipeline/scripts/test_build_vocab.py`

**Step 1: Write the failing test**

Create `data-pipeline/scripts/test_build_vocab.py`:

```python
"""Tests for build_vocab.py — curated property vocabulary builder."""
import sqlite3
import pytest


def make_test_db(tmp_path):
    """Create a minimal lexicon DB with synsets, lemmas, frequencies."""
    db_path = tmp_path / "test_lexicon.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE synsets (
            synset_id TEXT PRIMARY KEY,
            pos TEXT NOT NULL,
            definition TEXT NOT NULL
        );
        CREATE TABLE lemmas (
            lemma TEXT NOT NULL,
            synset_id TEXT NOT NULL,
            PRIMARY KEY (lemma, synset_id)
        );
        CREATE TABLE frequencies (
            lemma TEXT PRIMARY KEY,
            familiarity REAL,
            zipf REAL,
            frequency INTEGER,
            rarity TEXT NOT NULL DEFAULT 'unusual',
            source TEXT
        );

        -- 3 synsets with varying polysemy
        INSERT INTO synsets VALUES ('s1', 'n', 'a warm thing');
        INSERT INTO synsets VALUES ('s2', 'a', 'having warmth');
        INSERT INTO synsets VALUES ('s3', 'n', 'a cold thing');

        -- Lemma polysemy: "warm" appears in s1 + s2 (polysemy=2), "toasty" only in s1 (mono)
        INSERT INTO lemmas VALUES ('warm', 's1');
        INSERT INTO lemmas VALUES ('toasty', 's1');
        INSERT INTO lemmas VALUES ('warm', 's2');
        INSERT INTO lemmas VALUES ('tepid', 's2');
        INSERT INTO lemmas VALUES ('cold', 's3');
        INSERT INTO lemmas VALUES ('frigid', 's3');

        -- Familiarity: s1 most familiar, s3 least
        INSERT INTO frequencies VALUES ('warm', 6.0, 5.0, 1000, 'common', 'test');
        INSERT INTO frequencies VALUES ('toasty', 4.0, 3.0, 100, 'unusual', 'test');
        INSERT INTO frequencies VALUES ('tepid', 3.0, 2.0, 50, 'rare', 'test');
        INSERT INTO frequencies VALUES ('cold', 5.5, 4.5, 800, 'common', 'test');
        INSERT INTO frequencies VALUES ('frigid', 3.5, 2.5, 60, 'unusual', 'test');
    """)
    conn.commit()
    conn.close()
    return db_path


def test_build_vocab_picks_least_polysemous(tmp_path):
    """Each synset gets its least-polysemous lemma as canonical entry."""
    from build_vocab import build_vocabulary

    db_path = make_test_db(tmp_path)
    conn = sqlite3.connect(str(db_path))
    try:
        entries = build_vocabulary(conn, top_n=10)
    finally:
        conn.close()

    # s1 should pick "toasty" (polysemy=1) over "warm" (polysemy=2)
    s1_entry = next(e for e in entries if e["synset_id"] == "s1")
    assert s1_entry["lemma"] == "toasty"

    # s2 should pick "tepid" (polysemy=1) over "warm" (polysemy=2)
    s2_entry = next(e for e in entries if e["synset_id"] == "s2")
    assert s2_entry["lemma"] == "tepid"


def test_build_vocab_deduplicates_surface_forms(tmp_path):
    """If two synsets pick the same lemma, second one falls back."""
    db_path = tmp_path / "dedup.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE synsets (
            synset_id TEXT PRIMARY KEY,
            pos TEXT NOT NULL,
            definition TEXT NOT NULL
        );
        CREATE TABLE lemmas (
            lemma TEXT NOT NULL,
            synset_id TEXT NOT NULL,
            PRIMARY KEY (lemma, synset_id)
        );
        CREATE TABLE frequencies (
            lemma TEXT PRIMARY KEY,
            familiarity REAL,
            zipf REAL,
            frequency INTEGER,
            rarity TEXT NOT NULL DEFAULT 'unusual',
            source TEXT
        );

        -- Both synsets only have "bright" as their sole lemma
        INSERT INTO synsets VALUES ('s1', 'a', 'luminous');
        INSERT INTO synsets VALUES ('s2', 'a', 'intelligent');
        INSERT INTO lemmas VALUES ('bright', 's1');
        INSERT INTO lemmas VALUES ('bright', 's2');
        INSERT INTO lemmas VALUES ('brilliant', 's2');
        INSERT INTO frequencies VALUES ('bright', 6.0, 5.0, 500, 'common', 'test');
        INSERT INTO frequencies VALUES ('brilliant', 5.0, 4.0, 300, 'common', 'test');
    """)
    conn.commit()

    from build_vocab import build_vocabulary

    try:
        entries = build_vocabulary(conn, top_n=10)
    finally:
        conn.close()

    lemmas = [e["lemma"] for e in entries]
    # "bright" claimed by one synset, "brilliant" used as fallback for the other
    assert "bright" in lemmas
    assert "brilliant" in lemmas
    # No duplicates
    assert len(lemmas) == len(set(lemmas))


def test_build_vocab_ranks_by_familiarity(tmp_path):
    """Synsets are ranked by max lemma familiarity descending."""
    from build_vocab import build_vocabulary

    db_path = make_test_db(tmp_path)
    conn = sqlite3.connect(str(db_path))
    try:
        entries = build_vocabulary(conn, top_n=2)
    finally:
        conn.close()

    # Only top-2 by familiarity: s1 (warm=6.0) and s3 (cold=5.5)
    ids = [e["synset_id"] for e in entries]
    assert len(ids) == 2
    assert "s1" in ids
    assert "s3" in ids


def test_build_vocab_stores_to_table(tmp_path):
    """build_and_store creates the property_vocab_curated table."""
    from build_vocab import build_and_store

    db_path = make_test_db(tmp_path)
    conn = sqlite3.connect(str(db_path))
    try:
        count = build_and_store(conn, top_n=10)
    finally:
        conn.close()

    assert count == 3

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT synset_id, lemma, pos, polysemy FROM property_vocab_curated ORDER BY vocab_id"
        ).fetchall()
    finally:
        conn.close()

    assert len(rows) == 3
    # Check schema columns exist
    assert all(len(r) == 4 for r in rows)
```

**Step 2: Run test to verify it fails**

Run: `cd /home/agent/projects/metaforge/.worktrees/main/data-pipeline && .venv/bin/python -m pytest scripts/test_build_vocab.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'build_vocab'`

**Step 3: Write minimal implementation**

Create `data-pipeline/scripts/build_vocab.py`:

```python
"""Build curated property vocabulary from WordNet synsets.

Selects the least-polysemous lemma per synset, deduplicates surface forms,
and stores canonical entries in property_vocab_curated.

Usage:
    python build_vocab.py --db PATH [--top-n 35000]
"""
import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from utils import LEXICON_V2


def build_vocabulary(
    conn: sqlite3.Connection,
    top_n: int = 35000,
) -> list[dict]:
    """Build curated vocabulary entries from the lexicon.

    For each of the top-N synsets (ranked by max lemma familiarity):
    1. Compute polysemy count for each lemma
    2. Pick the least-polysemous lemma
    3. Greedy-deduplicate: if lemma already claimed, try the next option

    Returns list of dicts with keys: synset_id, lemma, pos, polysemy.
    """
    # Step 1: Polysemy count per lemma
    lemma_polysemy: dict[str, int] = {}
    for lemma, count in conn.execute(
        "SELECT lemma, COUNT(DISTINCT synset_id) FROM lemmas GROUP BY lemma"
    ):
        lemma_polysemy[lemma] = count

    # Step 2: Frequency data for ranking
    freq_data: dict[str, float] = {}
    for lemma, fam in conn.execute(
        "SELECT lemma, COALESCE(familiarity, 0) FROM frequencies"
    ):
        freq_data[lemma] = fam

    # Step 3: Synset metadata + lemma lists
    synset_pos: dict[str, str] = {}
    for sid, pos in conn.execute("SELECT synset_id, pos FROM synsets"):
        synset_pos[sid] = pos

    synset_lemmas: dict[str, list[str]] = {}
    for sid, lemma in conn.execute("SELECT synset_id, lemma FROM lemmas"):
        synset_lemmas.setdefault(sid, []).append(lemma)

    # Step 4: Rank synsets by max lemma familiarity
    synset_max_fam: dict[str, float] = {}
    for sid, lemmas in synset_lemmas.items():
        synset_max_fam[sid] = max(freq_data.get(lem, 0.0) for lem in lemmas)

    ranked = sorted(synset_max_fam.keys(), key=lambda s: synset_max_fam[s], reverse=True)
    subset = ranked[:top_n]

    # Step 5: Pick least-polysemous lemma with greedy dedup
    claimed: set[str] = set()
    entries: list[dict] = []

    for sid in subset:
        lemmas = synset_lemmas.get(sid, [])
        if not lemmas:
            continue

        # Sort by polysemy (ascending), then length (ascending), then alpha
        candidates = sorted(
            lemmas,
            key=lambda lem: (lemma_polysemy.get(lem, 1), len(lem), lem),
        )

        chosen = None
        chosen_poly = None
        for lem in candidates:
            if lem not in claimed:
                chosen = lem
                chosen_poly = lemma_polysemy.get(lem, 1)
                break

        if chosen is None:
            # All lemmas already claimed — use the least-polysemous anyway
            # and flag as shared (first candidate)
            chosen = candidates[0]
            chosen_poly = lemma_polysemy.get(chosen, 1)

        claimed.add(chosen)
        entries.append({
            "synset_id": sid,
            "lemma": chosen,
            "pos": synset_pos.get(sid, "?"),
            "polysemy": chosen_poly,
        })

    return entries


def build_and_store(
    conn: sqlite3.Connection,
    top_n: int = 35000,
) -> int:
    """Build vocabulary and store in property_vocab_curated table.

    Returns the number of entries stored.
    """
    entries = build_vocabulary(conn, top_n=top_n)

    conn.executescript("""
        DROP TABLE IF EXISTS property_vocab_curated;
        CREATE TABLE property_vocab_curated (
            vocab_id    INTEGER PRIMARY KEY,
            synset_id   TEXT NOT NULL,
            lemma       TEXT NOT NULL,
            pos         TEXT NOT NULL,
            polysemy    INTEGER NOT NULL,
            UNIQUE(synset_id)
        );
        CREATE INDEX idx_vocab_lemma ON property_vocab_curated(lemma);
    """)

    conn.executemany(
        "INSERT INTO property_vocab_curated (synset_id, lemma, pos, polysemy) VALUES (?, ?, ?, ?)",
        [(e["synset_id"], e["lemma"], e["pos"], e["polysemy"]) for e in entries],
    )
    conn.commit()

    print(f"  Stored {len(entries)} vocabulary entries")
    return len(entries)


def main():
    parser = argparse.ArgumentParser(description="Build curated property vocabulary")
    parser.add_argument("--db", default=str(LEXICON_V2), help="Path to lexicon DB")
    parser.add_argument("--top-n", type=int, default=35000, help="Top-N synsets by familiarity")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    try:
        count = build_and_store(conn, top_n=args.top_n)
        print(f"Done — {count} entries in property_vocab_curated")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
```

**Step 4: Run test to verify it passes**

Run: `cd /home/agent/projects/metaforge/.worktrees/main/data-pipeline && .venv/bin/python -m pytest scripts/test_build_vocab.py -v`
Expected: 4 PASSED

**Step 5: Run all pipeline tests to check for regressions**

Run: `cd /home/agent/projects/metaforge/.worktrees/main/data-pipeline && .venv/bin/python -m pytest scripts/ -v`
Expected: All tests pass

**Step 6: Commit**

```bash
git add data-pipeline/scripts/build_vocab.py data-pipeline/scripts/test_build_vocab.py
git commit -m "feat(pipeline): vocabulary builder — least-polysemous lemma per synset with greedy dedup"
```

---

### Task 2: Add snap pipeline — map free-form properties to canonical vocabulary

Three-stage cascade: exact match → morphological normalisation → embedding similarity at 0.7 threshold → drop.

**Files:**
- Create: `data-pipeline/scripts/snap_properties.py`
- Create: `data-pipeline/scripts/test_snap_properties.py`

**Step 1: Write the failing test**

Create `data-pipeline/scripts/test_snap_properties.py`:

```python
"""Tests for snap_properties.py — property-to-vocabulary snapping."""
import sqlite3
import struct
import pytest


EMBEDDING_DIM = 300


def _make_embedding(seed: float) -> bytes:
    """Create a deterministic 300d embedding for testing."""
    vec = [seed + i * 0.001 for i in range(EMBEDDING_DIM)]
    return struct.pack(f"{EMBEDDING_DIM}f", *vec)


def make_snap_db(tmp_path):
    """Create DB with vocabulary + property_vocabulary + synset_properties."""
    db_path = tmp_path / "snap_test.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE property_vocab_curated (
            vocab_id INTEGER PRIMARY KEY,
            synset_id TEXT NOT NULL,
            lemma TEXT NOT NULL,
            pos TEXT NOT NULL,
            polysemy INTEGER NOT NULL,
            UNIQUE(synset_id)
        );
        CREATE INDEX idx_vocab_lemma ON property_vocab_curated(lemma);

        CREATE TABLE property_vocabulary (
            property_id INTEGER PRIMARY KEY,
            text TEXT NOT NULL UNIQUE,
            embedding BLOB,
            is_oov INTEGER NOT NULL DEFAULT 0,
            source TEXT NOT NULL DEFAULT 'pilot'
        );

        CREATE TABLE synset_properties (
            synset_id TEXT NOT NULL,
            property_id INTEGER NOT NULL,
            PRIMARY KEY (synset_id, property_id)
        );

        -- Vocabulary entries
        INSERT INTO property_vocab_curated VALUES (1, 'vs1', 'warm', 'a', 1);
        INSERT INTO property_vocab_curated VALUES (2, 'vs2', 'cold', 'a', 1);
        INSERT INTO property_vocab_curated VALUES (3, 'vs3', 'luminous', 'a', 1);

        -- Existing properties from enrichment (free-form)
        INSERT INTO property_vocabulary VALUES (10, 'warm', NULL, 0, 'pilot');
        INSERT INTO property_vocabulary VALUES (11, 'chilly', NULL, 0, 'pilot');
        INSERT INTO property_vocabulary VALUES (12, 'luminous', NULL, 0, 'pilot');
        INSERT INTO property_vocabulary VALUES (13, 'xyzqwerty', NULL, 0, 'pilot');

        -- Synset 'abc' has properties: warm, chilly, luminous, xyzqwerty
        INSERT INTO synset_properties VALUES ('abc', 10);
        INSERT INTO synset_properties VALUES ('abc', 11);
        INSERT INTO synset_properties VALUES ('abc', 12);
        INSERT INTO synset_properties VALUES ('abc', 13);
    """)
    conn.commit()
    return db_path, conn


def test_snap_exact_match(tmp_path):
    """Properties matching a vocabulary lemma exactly snap via 'exact'."""
    from snap_properties import snap_properties

    db_path, conn = make_snap_db(tmp_path)
    try:
        result = snap_properties(conn, embedding_threshold=0.7)
    finally:
        conn.close()

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT synset_id, vocab_id, snap_method FROM synset_properties_curated "
            "WHERE snap_method = 'exact'"
        ).fetchall()
    finally:
        conn.close()

    # "warm" and "luminous" match exactly
    assert len(rows) == 2
    vocab_ids = {r[1] for r in rows}
    assert 1 in vocab_ids  # warm
    assert 3 in vocab_ids  # luminous


def test_snap_drops_unmatched(tmp_path):
    """Properties with no match at any stage are dropped."""
    from snap_properties import snap_properties

    db_path, conn = make_snap_db(tmp_path)
    try:
        result = snap_properties(conn, embedding_threshold=0.7)
    finally:
        conn.close()

    # xyzqwerty should not appear — no exact, no morph, no embedding match
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT * FROM synset_properties_curated WHERE vocab_id NOT IN (1, 2, 3)"
        ).fetchall()
    finally:
        conn.close()

    assert len(rows) == 0


def test_snap_result_stats(tmp_path):
    """snap_properties returns a stats dict with counts per stage."""
    from snap_properties import snap_properties

    _, conn = make_snap_db(tmp_path)
    try:
        result = snap_properties(conn, embedding_threshold=0.7)
    finally:
        conn.close()

    assert "exact" in result
    assert "dropped" in result
    assert result["exact"] >= 2  # warm + luminous


def test_snap_creates_table(tmp_path):
    """synset_properties_curated table is created with correct schema."""
    from snap_properties import snap_properties

    db_path, conn = make_snap_db(tmp_path)
    try:
        snap_properties(conn, embedding_threshold=0.7)
    finally:
        conn.close()

    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.execute("PRAGMA table_info(synset_properties_curated)")
        columns = {row[1] for row in cursor.fetchall()}
    finally:
        conn.close()

    assert "synset_id" in columns
    assert "vocab_id" in columns
    assert "snap_method" in columns
    assert "snap_score" in columns
```

**Step 2: Run test to verify it fails**

Run: `cd /home/agent/projects/metaforge/.worktrees/main/data-pipeline && .venv/bin/python -m pytest scripts/test_snap_properties.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'snap_properties'`

**Step 3: Write minimal implementation**

Create `data-pipeline/scripts/snap_properties.py`:

```python
"""Snap free-form extracted properties to curated vocabulary entries.

Three-stage cascade:
  1. Exact match — property text matches vocabulary lemma verbatim
  2. Morphological normalisation — stem/lemmatise then exact match
  3. Embedding top-K — cosine similarity above threshold
  4. Drop — no match found

Usage:
    python snap_properties.py --db PATH [--threshold 0.7]
"""
import argparse
import math
import sqlite3
import struct
import sys
from pathlib import Path

import nltk

sys.path.insert(0, str(Path(__file__).parent))
from utils import LEXICON_V2, EMBEDDING_DIM

# Ensure WordNet lemmatiser data is available
try:
    nltk.data.find("corpora/wordnet")
except LookupError:
    nltk.download("wordnet", quiet=True)

from nltk.stem import WordNetLemmatizer

_lemmatiser = WordNetLemmatizer()


def _lemmatise(word: str) -> list[str]:
    """Return morphological variants of a word."""
    variants = set()
    for pos in ("a", "v", "n", "r"):
        variants.add(_lemmatiser.lemmatize(word, pos=pos))
    # Also try stripping common suffixes
    if word.endswith("ing") and len(word) > 5:
        variants.add(word[:-3])       # "flickering" -> "flicker"
        variants.add(word[:-3] + "e") # "absorbing" -> "absorbe" (may not be a word)
    if word.endswith("ed") and len(word) > 4:
        variants.add(word[:-2])       # "abridged" -> "abridg"
        variants.add(word[:-1])       # "abridged" -> "abbridge" (may not be a word)
        variants.add(word[:-2] + "e") # "abridged" -> "abridge"
    variants.discard(word)  # Don't re-try exact match
    return list(variants)


def _cosine_similarity(a: bytes, b: bytes) -> float:
    """Compute cosine similarity between two embedding blobs."""
    va = struct.unpack(f"{EMBEDDING_DIM}f", a)
    vb = struct.unpack(f"{EMBEDDING_DIM}f", b)
    dot = sum(x * y for x, y in zip(va, vb))
    norm_a = math.sqrt(sum(x * x for x in va))
    norm_b = math.sqrt(sum(x * x for x in vb))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def snap_properties(
    conn: sqlite3.Connection,
    embedding_threshold: float = 0.7,
) -> dict[str, int]:
    """Snap free-form properties to curated vocabulary.

    Reads from synset_properties + property_vocabulary + property_vocab_curated.
    Writes to synset_properties_curated.

    Returns stats dict with counts per snap stage.
    """
    # Create output table
    conn.executescript("""
        DROP TABLE IF EXISTS synset_properties_curated;
        CREATE TABLE synset_properties_curated (
            synset_id   TEXT NOT NULL,
            vocab_id    INTEGER NOT NULL,
            snap_method TEXT NOT NULL,
            snap_score  REAL,
            PRIMARY KEY (synset_id, vocab_id)
        );
    """)

    # Load vocabulary: lemma -> vocab_id
    vocab_by_lemma: dict[str, int] = {}
    vocab_embeddings: dict[int, bytes] = {}
    for vid, lemma in conn.execute(
        "SELECT vocab_id, lemma FROM property_vocab_curated"
    ):
        vocab_by_lemma[lemma.lower()] = vid

    # Load vocabulary embeddings (from property_vocabulary, matched by text)
    for vid, lemma in conn.execute(
        "SELECT vocab_id, lemma FROM property_vocab_curated"
    ):
        row = conn.execute(
            "SELECT embedding FROM property_vocabulary WHERE text = ? AND embedding IS NOT NULL",
            (lemma.lower(),)
        ).fetchone()
        if row and row[0]:
            vocab_embeddings[vid] = row[0]

    # Load synset-property links with property text and embedding
    synset_props: list[tuple[str, str, bytes | None]] = []
    for sid, text, emb in conn.execute("""
        SELECT sp.synset_id, pv.text, pv.embedding
        FROM synset_properties sp
        JOIN property_vocabulary pv ON pv.property_id = sp.property_id
    """):
        synset_props.append((sid, text, emb))

    stats = {"exact": 0, "morphological": 0, "embedding": 0, "dropped": 0}
    inserts: list[tuple[str, int, str, float | None]] = []
    seen: set[tuple[str, int]] = set()

    for sid, prop_text, prop_emb in synset_props:
        prop_lower = prop_text.lower().strip()

        # Stage 1: Exact match
        if prop_lower in vocab_by_lemma:
            vid = vocab_by_lemma[prop_lower]
            key = (sid, vid)
            if key not in seen:
                inserts.append((sid, vid, "exact", None))
                seen.add(key)
                stats["exact"] += 1
            continue

        # Stage 2: Morphological normalisation
        matched = False
        for variant in _lemmatise(prop_lower):
            if variant in vocab_by_lemma:
                vid = vocab_by_lemma[variant]
                key = (sid, vid)
                if key not in seen:
                    inserts.append((sid, vid, "morphological", None))
                    seen.add(key)
                    stats["morphological"] += 1
                matched = True
                break
        if matched:
            continue

        # Stage 3: Embedding similarity
        if prop_emb and vocab_embeddings:
            best_vid = None
            best_score = 0.0
            for vid, v_emb in vocab_embeddings.items():
                score = _cosine_similarity(prop_emb, v_emb)
                if score > best_score:
                    best_score = score
                    best_vid = vid
            if best_vid is not None and best_score >= embedding_threshold:
                key = (sid, best_vid)
                if key not in seen:
                    inserts.append((sid, best_vid, "embedding", best_score))
                    seen.add(key)
                    stats["embedding"] += 1
                continue

        # Stage 4: Drop
        stats["dropped"] += 1

    conn.executemany(
        "INSERT INTO synset_properties_curated (synset_id, vocab_id, snap_method, snap_score) "
        "VALUES (?, ?, ?, ?)",
        inserts,
    )

    # Create indexes after bulk insert
    conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_spc_synset ON synset_properties_curated(synset_id);
        CREATE INDEX IF NOT EXISTS idx_spc_vocab ON synset_properties_curated(vocab_id);
    """)
    conn.commit()

    total = sum(stats.values())
    print(f"  Snapped {total} property links:")
    print(f"    exact: {stats['exact']}, morphological: {stats['morphological']}, "
          f"embedding: {stats['embedding']}, dropped: {stats['dropped']}")
    return stats


def main():
    parser = argparse.ArgumentParser(description="Snap properties to curated vocabulary")
    parser.add_argument("--db", default=str(LEXICON_V2), help="Path to lexicon DB")
    parser.add_argument("--threshold", type=float, default=0.7, help="Embedding similarity threshold")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    try:
        snap_properties(conn, embedding_threshold=args.threshold)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
```

**Step 4: Run test to verify it passes**

Run: `cd /home/agent/projects/metaforge/.worktrees/main/data-pipeline && .venv/bin/python -m pytest scripts/test_snap_properties.py -v`
Expected: 4 PASSED

**Step 5: Run all pipeline tests**

Run: `cd /home/agent/projects/metaforge/.worktrees/main/data-pipeline && .venv/bin/python -m pytest scripts/ -v`
Expected: All tests pass

**Step 6: Commit**

```bash
git add data-pipeline/scripts/snap_properties.py data-pipeline/scripts/test_snap_properties.py
git commit -m "feat(pipeline): snap properties to curated vocabulary — exact/morph/embedding cascade"
```

---

### Task 3: Add morphological snap tests

Verify the morphological normalisation stage handles participles and inflected forms.

**Files:**
- Modify: `data-pipeline/scripts/test_snap_properties.py`

**Step 1: Write the failing test**

Add to `data-pipeline/scripts/test_snap_properties.py`:

```python
def test_snap_morphological_participle(tmp_path):
    """Participle 'flickering' snaps to vocabulary entry 'flicker' via morphological stage."""
    db_path = tmp_path / "morph_test.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE property_vocab_curated (
            vocab_id INTEGER PRIMARY KEY,
            synset_id TEXT NOT NULL,
            lemma TEXT NOT NULL,
            pos TEXT NOT NULL,
            polysemy INTEGER NOT NULL,
            UNIQUE(synset_id)
        );
        CREATE INDEX idx_vocab_lemma ON property_vocab_curated(lemma);

        CREATE TABLE property_vocabulary (
            property_id INTEGER PRIMARY KEY,
            text TEXT NOT NULL UNIQUE,
            embedding BLOB,
            is_oov INTEGER NOT NULL DEFAULT 0,
            source TEXT NOT NULL DEFAULT 'pilot'
        );

        CREATE TABLE synset_properties (
            synset_id TEXT NOT NULL,
            property_id INTEGER NOT NULL,
            PRIMARY KEY (synset_id, property_id)
        );

        -- Vocabulary has "flicker"
        INSERT INTO property_vocab_curated VALUES (1, 'vs1', 'flicker', 'v', 1);

        -- Extracted property is "flickering" (VBG form)
        INSERT INTO property_vocabulary VALUES (10, 'flickering', NULL, 0, 'pilot');
        INSERT INTO synset_properties VALUES ('abc', 10);
    """)
    conn.commit()

    from snap_properties import snap_properties

    try:
        result = snap_properties(conn, embedding_threshold=0.7)
    finally:
        conn.close()

    assert result["morphological"] >= 1

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT vocab_id, snap_method FROM synset_properties_curated"
        ).fetchall()
    finally:
        conn.close()

    assert any(r[0] == 1 and r[1] == "morphological" for r in rows)
```

**Step 2: Run test to verify it passes**

Run: `cd /home/agent/projects/metaforge/.worktrees/main/data-pipeline && .venv/bin/python -m pytest scripts/test_snap_properties.py::test_snap_morphological_participle -v`
Expected: PASS (implementation already handles this)

**Step 3: Commit**

```bash
git add data-pipeline/scripts/test_snap_properties.py
git commit -m "test(pipeline): add morphological participle snap test"
```

---

### Task 4: Build antonym table from WordNet attribute relations

Extract antonym pairs from attribute relations (relation_type = '60') in the lexicon.

**Files:**
- Create: `data-pipeline/scripts/build_antonyms.py`
- Create: `data-pipeline/scripts/test_build_antonyms.py`

**Step 1: Write the failing test**

Create `data-pipeline/scripts/test_build_antonyms.py`:

```python
"""Tests for build_antonyms.py — antonym pair detection via attribute relations."""
import sqlite3
import pytest


def make_antonym_db(tmp_path):
    """Create DB with relations (type 60) + vocabulary for antonym detection."""
    db_path = tmp_path / "antonym_test.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE synsets (
            synset_id TEXT PRIMARY KEY,
            pos TEXT NOT NULL,
            definition TEXT NOT NULL
        );
        CREATE TABLE lemmas (
            lemma TEXT NOT NULL,
            synset_id TEXT NOT NULL,
            PRIMARY KEY (lemma, synset_id)
        );
        CREATE TABLE relations (
            source_synset TEXT NOT NULL,
            target_synset TEXT NOT NULL,
            relation_type TEXT NOT NULL
        );
        CREATE TABLE property_vocab_curated (
            vocab_id INTEGER PRIMARY KEY,
            synset_id TEXT NOT NULL,
            lemma TEXT NOT NULL,
            pos TEXT NOT NULL,
            polysemy INTEGER NOT NULL,
            UNIQUE(synset_id)
        );

        -- Attribute noun "temperature" (synset t1)
        INSERT INTO synsets VALUES ('t1', 'n', 'degree of hotness');

        -- Adjective synsets linked to attribute noun via relation_type 60
        INSERT INTO synsets VALUES ('a1', 'a', 'having high temperature');
        INSERT INTO synsets VALUES ('a2', 'a', 'having low temperature');
        INSERT INTO lemmas VALUES ('hot', 'a1');
        INSERT INTO lemmas VALUES ('cold', 'a2');

        -- Attribute relations: a1 -> t1 (hot -> temperature), a2 -> t1 (cold -> temperature)
        INSERT INTO relations VALUES ('a1', 't1', '60');
        INSERT INTO relations VALUES ('a2', 't1', '60');

        -- Both are in the curated vocabulary
        INSERT INTO property_vocab_curated VALUES (1, 'a1', 'hot', 'a', 1);
        INSERT INTO property_vocab_curated VALUES (2, 'a2', 'cold', 'a', 1);

        -- A third adjective NOT in vocabulary (should be excluded)
        INSERT INTO synsets VALUES ('a3', 'a', 'warm-ish');
        INSERT INTO lemmas VALUES ('lukewarm', 'a3');
        INSERT INTO relations VALUES ('a3', 't1', '60');
    """)
    conn.commit()
    return db_path, conn


def test_build_antonyms_finds_pairs(tmp_path):
    """Adjectives sharing an attribute noun are detected as antonym pairs."""
    from build_antonyms import build_antonym_table

    db_path, conn = make_antonym_db(tmp_path)
    try:
        count = build_antonym_table(conn)
    finally:
        conn.close()

    # hot <-> cold (both in vocabulary, share attribute t1)
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT vocab_id_a, vocab_id_b FROM property_antonyms ORDER BY vocab_id_a, vocab_id_b"
        ).fetchall()
    finally:
        conn.close()

    # Bidirectional: (1,2) and (2,1)
    assert (1, 2) in rows
    assert (2, 1) in rows
    assert count == 1  # 1 unique pair


def test_build_antonyms_excludes_non_vocabulary(tmp_path):
    """Synsets not in property_vocab_curated are excluded from antonym pairs."""
    from build_antonyms import build_antonym_table

    db_path, conn = make_antonym_db(tmp_path)
    try:
        build_antonym_table(conn)
    finally:
        conn.close()

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute("SELECT * FROM property_antonyms").fetchall()
    finally:
        conn.close()

    # Only hot <-> cold, not lukewarm (a3 not in vocabulary)
    assert len(rows) == 2  # bidirectional


def test_build_antonyms_creates_table(tmp_path):
    """property_antonyms table is created with correct schema."""
    from build_antonyms import build_antonym_table

    db_path, conn = make_antonym_db(tmp_path)
    try:
        build_antonym_table(conn)
    finally:
        conn.close()

    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.execute("PRAGMA table_info(property_antonyms)")
        columns = {row[1] for row in cursor.fetchall()}
    finally:
        conn.close()

    assert "vocab_id_a" in columns
    assert "vocab_id_b" in columns
```

**Step 2: Run test to verify it fails**

Run: `cd /home/agent/projects/metaforge/.worktrees/main/data-pipeline && .venv/bin/python -m pytest scripts/test_build_antonyms.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'build_antonyms'`

**Step 3: Write minimal implementation**

Create `data-pipeline/scripts/build_antonyms.py`:

```python
"""Build antonym pairs table from WordNet attribute relations.

WordNet attribute relations (relation_type '60') link adjective synsets to
shared attribute nouns. Adjectives sharing an attribute noun are typically
antonyms (hot/cold, light/dark, strong/weak).

Usage:
    python build_antonyms.py --db PATH
"""
import argparse
import sqlite3
import sys
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from utils import LEXICON_V2


def build_antonym_table(conn: sqlite3.Connection) -> int:
    """Build property_antonyms from attribute relations.

    Finds adjective synsets that share an attribute noun (via relation_type '60'),
    filters to those present in property_vocab_curated, and stores bidirectional
    antonym pairs.

    Returns the number of unique antonym pairs found.
    """
    conn.executescript("""
        DROP TABLE IF EXISTS property_antonyms;
        CREATE TABLE property_antonyms (
            vocab_id_a  INTEGER NOT NULL,
            vocab_id_b  INTEGER NOT NULL,
            PRIMARY KEY (vocab_id_a, vocab_id_b)
        );
    """)

    # Find all attribute nouns and their linked adjective synsets
    # relation_type '60' = attribute relation (adjective -> attribute noun)
    attr_groups: dict[str, list[str]] = {}
    for adj_synset, attr_noun in conn.execute("""
        SELECT source_synset, target_synset
        FROM relations
        WHERE relation_type = '60'
    """):
        attr_groups.setdefault(attr_noun, []).append(adj_synset)

    # Load vocabulary synset -> vocab_id mapping
    vocab_map: dict[str, int] = {}
    for vid, sid in conn.execute(
        "SELECT vocab_id, synset_id FROM property_vocab_curated"
    ):
        vocab_map[sid] = vid

    # Generate antonym pairs: all combinations of adjectives sharing an attribute
    unique_pairs: set[tuple[int, int]] = set()
    for attr_noun, adj_synsets in attr_groups.items():
        # Filter to synsets in vocabulary
        vocab_ids = [vocab_map[s] for s in adj_synsets if s in vocab_map]
        if len(vocab_ids) < 2:
            continue

        for a, b in combinations(vocab_ids, 2):
            pair = (min(a, b), max(a, b))
            unique_pairs.add(pair)

    # Insert bidirectionally
    inserts = []
    for a, b in unique_pairs:
        inserts.append((a, b))
        inserts.append((b, a))

    conn.executemany(
        "INSERT OR IGNORE INTO property_antonyms (vocab_id_a, vocab_id_b) VALUES (?, ?)",
        inserts,
    )
    conn.commit()

    print(f"  Found {len(unique_pairs)} unique antonym pairs ({len(inserts)} bidirectional rows)")
    return len(unique_pairs)


def main():
    parser = argparse.ArgumentParser(description="Build antonym pairs from attribute relations")
    parser.add_argument("--db", default=str(LEXICON_V2), help="Path to lexicon DB")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    try:
        build_antonym_table(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
```

**Step 4: Run test to verify it passes**

Run: `cd /home/agent/projects/metaforge/.worktrees/main/data-pipeline && .venv/bin/python -m pytest scripts/test_build_antonyms.py -v`
Expected: 3 PASSED

**Step 5: Run all pipeline tests**

Run: `cd /home/agent/projects/metaforge/.worktrees/main/data-pipeline && .venv/bin/python -m pytest scripts/ -v`
Expected: All tests pass

**Step 6: Commit**

```bash
git add data-pipeline/scripts/build_antonyms.py data-pipeline/scripts/test_build_antonyms.py
git commit -m "feat(pipeline): antonym pair detection from WordNet attribute relations"
```

---

### Task 5: Add snap audit report script

Measures snap quality: per-stage rates, coverage per synset, IDF distribution.

**Files:**
- Create: `data-pipeline/scripts/analysis/snap_audit.py`
- Create: `data-pipeline/scripts/analysis/test_snap_audit.py`

**Step 1: Write the failing test**

Create `data-pipeline/scripts/analysis/test_snap_audit.py`:

```python
"""Tests for snap_audit.py — snap quality report."""
import sqlite3
import pytest


def make_audit_db(tmp_path):
    """Create a DB with synset_properties_curated for audit testing."""
    db_path = tmp_path / "audit_test.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE synset_properties_curated (
            synset_id TEXT NOT NULL,
            vocab_id INTEGER NOT NULL,
            snap_method TEXT NOT NULL,
            snap_score REAL,
            PRIMARY KEY (synset_id, vocab_id)
        );

        -- Synset s1: 3 properties (2 exact, 1 embedding)
        INSERT INTO synset_properties_curated VALUES ('s1', 1, 'exact', NULL);
        INSERT INTO synset_properties_curated VALUES ('s1', 2, 'exact', NULL);
        INSERT INTO synset_properties_curated VALUES ('s1', 3, 'embedding', 0.82);

        -- Synset s2: 1 property (morphological)
        INSERT INTO synset_properties_curated VALUES ('s2', 4, 'morphological', NULL);
    """)
    conn.commit()
    return db_path, conn


def test_snap_rate_report(tmp_path):
    """Report returns correct counts per snap method."""
    from snap_audit import compute_snap_rates

    _, conn = make_audit_db(tmp_path)
    try:
        rates = compute_snap_rates(conn)
    finally:
        conn.close()

    assert rates["exact"] == 2
    assert rates["morphological"] == 1
    assert rates["embedding"] == 1


def test_coverage_report(tmp_path):
    """Report returns per-synset property counts."""
    from snap_audit import compute_coverage

    _, conn = make_audit_db(tmp_path)
    try:
        coverage = compute_coverage(conn)
    finally:
        conn.close()

    assert coverage["total_synsets"] == 2
    assert coverage["with_3_plus"] == 1   # s1 has 3
    assert coverage["with_5_plus"] == 0
```

**Step 2: Run test to verify it fails**

Run: `cd /home/agent/projects/metaforge/.worktrees/main/data-pipeline && .venv/bin/python -m pytest scripts/analysis/test_snap_audit.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'snap_audit'`

**Step 3: Write minimal implementation**

Create `data-pipeline/scripts/analysis/snap_audit.py`:

```python
"""Snap quality audit report.

Measures:
  1. Snap rate per stage (exact, morphological, embedding, dropped)
  2. Property coverage per synset (how many canonical properties after snapping)
  3. Snap score distribution for embedding matches

Usage:
    python snap_audit.py --db PATH
"""
import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils import LEXICON_V2


def compute_snap_rates(conn: sqlite3.Connection) -> dict[str, int]:
    """Count snapped properties per method."""
    rates: dict[str, int] = {}
    for method, count in conn.execute(
        "SELECT snap_method, COUNT(*) FROM synset_properties_curated GROUP BY snap_method"
    ):
        rates[method] = count
    return rates


def compute_coverage(conn: sqlite3.Connection) -> dict[str, int]:
    """Compute per-synset property coverage after snapping."""
    synset_counts: list[int] = []
    for (count,) in conn.execute(
        "SELECT COUNT(*) FROM synset_properties_curated GROUP BY synset_id"
    ):
        synset_counts.append(count)

    return {
        "total_synsets": len(synset_counts),
        "with_3_plus": sum(1 for c in synset_counts if c >= 3),
        "with_5_plus": sum(1 for c in synset_counts if c >= 5),
        "with_8_plus": sum(1 for c in synset_counts if c >= 8),
        "avg_properties": round(sum(synset_counts) / len(synset_counts), 1) if synset_counts else 0,
    }


def compute_embedding_score_distribution(conn: sqlite3.Connection) -> dict[str, int]:
    """Distribution of cosine scores for embedding-snapped properties."""
    brackets: dict[str, int] = {
        "0.70-0.75": 0,
        "0.75-0.80": 0,
        "0.80-0.85": 0,
        "0.85-0.90": 0,
        "0.90-0.95": 0,
        "0.95-1.00": 0,
    }
    for (score,) in conn.execute(
        "SELECT snap_score FROM synset_properties_curated WHERE snap_method = 'embedding'"
    ):
        if score is None:
            continue
        if score < 0.75:
            brackets["0.70-0.75"] += 1
        elif score < 0.80:
            brackets["0.75-0.80"] += 1
        elif score < 0.85:
            brackets["0.80-0.85"] += 1
        elif score < 0.90:
            brackets["0.85-0.90"] += 1
        elif score < 0.95:
            brackets["0.90-0.95"] += 1
        else:
            brackets["0.95-1.00"] += 1
    return brackets


def print_report(conn: sqlite3.Connection):
    """Print full audit report."""
    print("=== Snap Audit Report ===\n")

    rates = compute_snap_rates(conn)
    total = sum(rates.values())
    print("Snap rates:")
    for method in ("exact", "morphological", "embedding"):
        count = rates.get(method, 0)
        pct = 100 * count / total if total else 0
        print(f"  {method}: {count:,} ({pct:.1f}%)")
    print()

    coverage = compute_coverage(conn)
    print(f"Coverage ({coverage['total_synsets']:,} synsets):")
    print(f"  >= 3 properties: {coverage['with_3_plus']:,}")
    print(f"  >= 5 properties: {coverage['with_5_plus']:,}")
    print(f"  >= 8 properties: {coverage['with_8_plus']:,}")
    print(f"  Average: {coverage['avg_properties']} properties/synset")
    print()

    dist = compute_embedding_score_distribution(conn)
    print("Embedding score distribution:")
    for bracket, count in dist.items():
        print(f"  {bracket}: {count:,}")


def main():
    parser = argparse.ArgumentParser(description="Snap quality audit report")
    parser.add_argument("--db", default=str(LEXICON_V2), help="Path to lexicon DB")
    args = parser.parse_args()

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    try:
        print_report(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
```

**Step 4: Run test to verify it passes**

Run: `cd /home/agent/projects/metaforge/.worktrees/main/data-pipeline && .venv/bin/python -m pytest scripts/analysis/test_snap_audit.py -v`
Expected: 2 PASSED

**Step 5: Commit**

```bash
git add data-pipeline/scripts/analysis/snap_audit.py data-pipeline/scripts/analysis/test_snap_audit.py
git commit -m "feat(pipeline): snap quality audit report — rates, coverage, score distribution"
```

---

### Task 6: Update schema with curated vocabulary tables

Add the three new tables to `schema-v2.sql` so `restore_db.sh` creates them.

**Files:**
- Modify: `docs/designs/schema-v2.sql:220-246`

**Step 1: Add curated vocabulary tables**

After the existing computed tables section (line 246) in `docs/designs/schema-v2.sql`, add:

```sql
-- ============================================================
-- Curated Property Vocabulary (from build_vocab.py)
-- ============================================================

-- Canonical vocabulary entries: one lemma per synset, least-polysemous chosen
CREATE TABLE IF NOT EXISTS property_vocab_curated (
    vocab_id    INTEGER PRIMARY KEY,
    synset_id   TEXT NOT NULL,
    lemma       TEXT NOT NULL,
    pos         TEXT NOT NULL,
    polysemy    INTEGER NOT NULL,
    UNIQUE(synset_id)
);

CREATE INDEX IF NOT EXISTS idx_vocab_curated_lemma ON property_vocab_curated(lemma);

-- Snapped synset-property links (from snap_properties.py)
CREATE TABLE IF NOT EXISTS synset_properties_curated (
    synset_id   TEXT NOT NULL,
    vocab_id    INTEGER NOT NULL,
    snap_method TEXT NOT NULL,
    snap_score  REAL,
    FOREIGN KEY (vocab_id) REFERENCES property_vocab_curated(vocab_id),
    PRIMARY KEY (synset_id, vocab_id)
);

CREATE INDEX IF NOT EXISTS idx_spc_synset ON synset_properties_curated(synset_id);
CREATE INDEX IF NOT EXISTS idx_spc_vocab ON synset_properties_curated(vocab_id);

-- Antonym pairs via WordNet attribute relations (from build_antonyms.py)
CREATE TABLE IF NOT EXISTS property_antonyms (
    vocab_id_a  INTEGER NOT NULL,
    vocab_id_b  INTEGER NOT NULL,
    FOREIGN KEY (vocab_id_a) REFERENCES property_vocab_curated(vocab_id),
    FOREIGN KEY (vocab_id_b) REFERENCES property_vocab_curated(vocab_id),
    PRIMARY KEY (vocab_id_a, vocab_id_b)
);
```

**Step 2: Rebuild the database**

Run: `bash /home/agent/projects/metaforge/.worktrees/main/data-pipeline/scripts/restore_db.sh`
Expected: DB recreated with new tables

**Step 3: Commit**

```bash
git add docs/designs/schema-v2.sql
git commit -m "feat(schema): add curated vocabulary, snapped properties, and antonym tables"
```

---

## Batch 2: Go API — Set-Intersection Forge Query

### Task 7: Add contrast count to SynsetMatchFull

Extend the match struct to carry antonym contrast data alongside shared property count.

**Files:**
- Modify: `api/internal/db/db.go:269-281`
- Modify: `api/internal/forge/forge.go:33-43`

**Step 1: Write the failing test**

Create `api/internal/forge/forge_curated_test.go`:

```go
package forge

import "testing"

func TestClassifyTierIronic(t *testing.T) {
	tier := ClassifyTierCurated(1, 4) // low shared, high contrast
	if tier != TierIronic {
		t.Errorf("expected ironic, got %s", tier)
	}
}

func TestClassifyTierComplex(t *testing.T) {
	tier := ClassifyTierCurated(4, 4) // high shared, high contrast
	if tier != TierComplex {
		t.Errorf("expected complex, got %s", tier)
	}
}

func TestClassifyTierCuratedLegendary(t *testing.T) {
	tier := ClassifyTierCurated(5, 0) // high shared, no contrast
	if tier != TierLegendary {
		t.Errorf("expected legendary, got %s", tier)
	}
}

func TestClassifyTierCuratedStrong(t *testing.T) {
	tier := ClassifyTierCurated(3, 0) // moderate shared, no contrast
	if tier != TierStrong {
		t.Errorf("expected strong, got %s", tier)
	}
}

func TestClassifyTierCuratedUnlikely(t *testing.T) {
	tier := ClassifyTierCurated(1, 0) // low shared, no contrast
	if tier != TierUnlikely {
		t.Errorf("expected unlikely, got %s", tier)
	}
}
```

**Step 2: Run test to verify it fails**

Run: `cd /home/agent/projects/metaforge/.worktrees/main && export PATH="/usr/local/go/bin:$PATH" && go test ./api/internal/forge/ -run TestClassifyTierCurated -v`
Expected: FAIL — `ClassifyTierCurated` undefined, `TierIronic` undefined

**Step 3: Add new tiers and classification function**

Add to `api/internal/forge/forge.go` after line 15:

```go
	TierIronic                  // Low shared + high contrast (ironic metaphor)
	TierComplex                 // High shared + high contrast (simultaneously alike and opposed)
```

Update the `String()` method to include new tiers:

```go
func (t Tier) String() string {
	names := [...]string{"legendary", "interesting", "strong", "obvious", "unlikely", "ironic", "complex"}
	if int(t) < 0 || int(t) >= len(names) {
		return "unknown"
	}
	return names[t]
}
```

Add new constants and classification function:

```go
// Thresholds for curated vocabulary tier classification
const (
	MinContrastOverlap = 3 // Minimum antonymous properties for contrast-based tiers
)

// ClassifyTierCurated determines tier from shared and contrast property counts.
// Used with the curated vocabulary (set-intersection matching, no cosine distance).
func ClassifyTierCurated(shared, contrast int) Tier {
	highShared := shared >= StrongOverlap
	moderateShared := shared >= MinOverlap
	highContrast := contrast >= MinContrastOverlap

	switch {
	case highShared && highContrast:
		return TierComplex
	case !moderateShared && highContrast:
		return TierIronic
	case highShared:
		return TierLegendary
	case moderateShared:
		return TierStrong
	default:
		return TierUnlikely
	}
}
```

**Step 4: Run test to verify it passes**

Run: `cd /home/agent/projects/metaforge/.worktrees/main && export PATH="/usr/local/go/bin:$PATH" && go test ./api/internal/forge/ -v`
Expected: All tests pass (existing + 5 new)

**Step 5: Commit**

```bash
git add api/internal/forge/forge.go api/internal/forge/forge_curated_test.go
git commit -m "feat(forge): add Ironic + Complex tiers with curated vocabulary classification"
```

---

### Task 8: Add curated forge mega-query to db.go

New `GetForgeMatchesCurated` function: set-intersection on `synset_properties_curated` + contrast count from `property_antonyms`.

**Files:**
- Modify: `api/internal/db/db.go`

**Step 1: Write the failing test**

Create `api/internal/db/db_curated_test.go`:

```go
package db

import (
	"database/sql"
	"os"
	"path/filepath"
	"testing"

	_ "github.com/mattn/go-sqlite3"
)

func setupCuratedTestDB(t *testing.T) *sql.DB {
	t.Helper()
	tmpDir := t.TempDir()
	dbPath := filepath.Join(tmpDir, "test.db")

	db, err := sql.Open("sqlite3", dbPath)
	if err != nil {
		t.Fatal(err)
	}

	_, err = db.Exec(`
		CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, pos TEXT, definition TEXT);
		CREATE TABLE lemmas (lemma TEXT, synset_id TEXT, PRIMARY KEY (lemma, synset_id));

		CREATE TABLE property_vocab_curated (
			vocab_id INTEGER PRIMARY KEY,
			synset_id TEXT NOT NULL,
			lemma TEXT NOT NULL,
			pos TEXT NOT NULL,
			polysemy INTEGER NOT NULL
		);

		CREATE TABLE synset_properties_curated (
			synset_id TEXT NOT NULL,
			vocab_id INTEGER NOT NULL,
			snap_method TEXT NOT NULL,
			snap_score REAL,
			PRIMARY KEY (synset_id, vocab_id)
		);
		CREATE INDEX idx_spc_synset ON synset_properties_curated(synset_id);
		CREATE INDEX idx_spc_vocab ON synset_properties_curated(vocab_id);

		CREATE TABLE property_antonyms (
			vocab_id_a INTEGER NOT NULL,
			vocab_id_b INTEGER NOT NULL,
			PRIMARY KEY (vocab_id_a, vocab_id_b)
		);

		-- Source synset: grief (properties: heavy, isolating, waves)
		INSERT INTO synsets VALUES ('src1', 'n', 'intense sorrow');
		INSERT INTO lemmas VALUES ('grief', 'src1');
		INSERT INTO property_vocab_curated VALUES (1, 'v1', 'heavy', 'a', 1);
		INSERT INTO property_vocab_curated VALUES (2, 'v2', 'isolating', 'a', 1);
		INSERT INTO property_vocab_curated VALUES (3, 'v3', 'waves', 'n', 2);
		INSERT INTO property_vocab_curated VALUES (4, 'v4', 'light', 'a', 3);

		INSERT INTO synset_properties_curated VALUES ('src1', 1, 'exact', NULL);
		INSERT INTO synset_properties_curated VALUES ('src1', 2, 'exact', NULL);
		INSERT INTO synset_properties_curated VALUES ('src1', 3, 'exact', NULL);

		-- Target synset: anchor (shares heavy + waves)
		INSERT INTO synsets VALUES ('tgt1', 'n', 'a device for holding');
		INSERT INTO lemmas VALUES ('anchor', 'tgt1');
		INSERT INTO synset_properties_curated VALUES ('tgt1', 1, 'exact', NULL);
		INSERT INTO synset_properties_curated VALUES ('tgt1', 3, 'exact', NULL);

		-- Target synset: balloon (has light, antonym of heavy)
		INSERT INTO synsets VALUES ('tgt2', 'n', 'inflatable bag');
		INSERT INTO lemmas VALUES ('balloon', 'tgt2');
		INSERT INTO synset_properties_curated VALUES ('tgt2', 4, 'exact', NULL);

		-- Antonym: heavy <-> light
		INSERT INTO property_antonyms VALUES (1, 4);
		INSERT INTO property_antonyms VALUES (4, 1);
	`)
	if err != nil {
		t.Fatal(err)
	}

	return db
}

func TestGetForgeMatchesCurated_SharedProperties(t *testing.T) {
	db := setupCuratedTestDB(t)
	defer db.Close()

	matches, err := GetForgeMatchesCurated(db, "src1", 50)
	if err != nil {
		t.Fatal(err)
	}

	// anchor shares 2 properties (heavy, waves)
	var anchor *CuratedMatch
	for i := range matches {
		if matches[i].SynsetID == "tgt1" {
			anchor = &matches[i]
		}
	}
	if anchor == nil {
		t.Fatal("expected anchor in results")
	}
	if anchor.SharedCount != 2 {
		t.Errorf("expected 2 shared, got %d", anchor.SharedCount)
	}
}

func TestGetForgeMatchesCurated_ContrastCount(t *testing.T) {
	db := setupCuratedTestDB(t)
	defer db.Close()

	matches, err := GetForgeMatchesCurated(db, "src1", 50)
	if err != nil {
		t.Fatal(err)
	}

	// balloon has "light" which is antonym of source's "heavy"
	var balloon *CuratedMatch
	for i := range matches {
		if matches[i].SynsetID == "tgt2" {
			balloon = &matches[i]
		}
	}
	if balloon == nil {
		t.Fatal("expected balloon in results")
	}
	if balloon.ContrastCount != 1 {
		t.Errorf("expected 1 contrast, got %d", balloon.ContrastCount)
	}
}
```

**Step 2: Run test to verify it fails**

Run: `cd /home/agent/projects/metaforge/.worktrees/main && export PATH="/usr/local/go/bin:$PATH" && go test ./api/internal/db/ -run TestGetForgeMatchesCurated -v`
Expected: FAIL — `GetForgeMatchesCurated` undefined, `CuratedMatch` undefined

**Step 3: Write the implementation**

Add to `api/internal/db/db.go`:

```go
// CuratedMatch represents a forge match via set intersection (curated vocabulary).
type CuratedMatch struct {
	SynsetID       string   `json:"synset_id"`
	Word           string   `json:"word"`
	Definition     string   `json:"definition"`
	SharedCount    int      `json:"shared_count"`
	ContrastCount  int      `json:"contrast_count"`
	SharedProps    []string `json:"shared_properties,omitempty"`
}

// GetForgeMatchesCurated finds forge candidates using curated vocabulary set intersection.
// No embeddings or cosine distance — pure integer JOINs for shared + antonymous properties.
func GetForgeMatchesCurated(db *sql.DB, sourceID string, limit int) ([]CuratedMatch, error) {
	rows, err := db.Query(`
		WITH source_props AS (
			SELECT vocab_id FROM synset_properties_curated WHERE synset_id = ?
		),
		shared AS (
			SELECT spc.synset_id,
			       COUNT(*) as shared_count,
			       GROUP_CONCAT(pvc.lemma) as shared_props
			FROM source_props sp
			JOIN synset_properties_curated spc ON spc.vocab_id = sp.vocab_id
			JOIN property_vocab_curated pvc ON pvc.vocab_id = sp.vocab_id
			WHERE spc.synset_id != ?
			GROUP BY spc.synset_id
		),
		contrast AS (
			SELECT spc.synset_id,
			       COUNT(*) as contrast_count
			FROM source_props sp
			JOIN property_antonyms pa ON pa.vocab_id_a = sp.vocab_id
			JOIN synset_properties_curated spc ON spc.vocab_id = pa.vocab_id_b
			WHERE spc.synset_id != ?
			GROUP BY spc.synset_id
		)
		SELECT COALESCE(sh.synset_id, co.synset_id) as synset_id,
		       s.definition,
		       l.lemma,
		       COALESCE(sh.shared_count, 0),
		       COALESCE(co.contrast_count, 0),
		       COALESCE(sh.shared_props, '')
		FROM (
			SELECT synset_id FROM shared
			UNION
			SELECT synset_id FROM contrast
		) all_matches
		LEFT JOIN shared sh ON sh.synset_id = all_matches.synset_id
		LEFT JOIN contrast co ON co.synset_id = all_matches.synset_id
		JOIN synsets s ON s.synset_id = all_matches.synset_id
		JOIN lemmas l ON l.synset_id = all_matches.synset_id
		ORDER BY COALESCE(sh.shared_count, 0) + COALESCE(co.contrast_count, 0) DESC
		LIMIT ?
	`, sourceID, sourceID, sourceID, limit)

	if err != nil {
		return nil, fmt.Errorf("GetForgeMatchesCurated query failed: %w", err)
	}
	defer rows.Close()

	seen := make(map[string]bool)
	var matches []CuratedMatch

	for rows.Next() {
		var m CuratedMatch
		var sharedProps string

		if err := rows.Scan(
			&m.SynsetID, &m.Definition, &m.Word,
			&m.SharedCount, &m.ContrastCount, &sharedProps,
		); err != nil {
			slog.Warn("scan curated match failed", "err", err)
			continue
		}

		if seen[m.SynsetID] {
			continue
		}
		seen[m.SynsetID] = true

		if sharedProps != "" {
			m.SharedProps = strings.Split(sharedProps, ",")
		}

		matches = append(matches, m)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("GetForgeMatchesCurated iteration error: %w", err)
	}

	return matches, nil
}
```

**Step 4: Run test to verify it passes**

Run: `cd /home/agent/projects/metaforge/.worktrees/main && export PATH="/usr/local/go/bin:$PATH" && go test ./api/internal/db/ -v`
Expected: All tests pass

**Step 5: Commit**

```bash
git add api/internal/db/db.go api/internal/db/db_curated_test.go
git commit -m "feat(db): curated forge query — set intersection + antonym contrast counting"
```

---

### Task 9: Wire curated forge into HandleSuggest

Detect presence of `synset_properties_curated` table and use the curated path when available, falling back to the existing cosine-distance path.

**Files:**
- Modify: `api/internal/handler/handler.go:77-175`

**Step 1: Write the failing test**

Add to an existing handler test file (or create `api/internal/handler/handler_curated_test.go`):

```go
package handler

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestHandleSuggestCurated_ReturnsIronicTier(t *testing.T) {
	// This test validates the end-to-end curated path.
	// Requires a test DB with curated tables populated.
	// Full integration test — skip if DB not available.
	t.Skip("Integration test — requires curated vocabulary DB")
}
```

> **Note:** The handler integration test requires a fully populated test DB. The TDD cycle here is: write the wiring code, verify via manual testing with `metaforge-api-test` skill, then deploy. The unit tests in Tasks 7-8 cover the logic.

**Step 2: Update HandleSuggest**

In `api/internal/handler/handler.go`, modify `HandleSuggest` (lines 124-175) to detect and use curated tables:

```go
	// Check if curated vocabulary tables exist
	var curatedExists int
	_ = h.database.QueryRow(`
		SELECT COUNT(*) FROM sqlite_master
		WHERE type='table' AND name='synset_properties_curated'
	`).Scan(&curatedExists)

	if curatedExists > 0 {
		// Curated path: set intersection + antonym contrast
		candidates, err := db.GetForgeMatchesCurated(h.database, synsetID, limit)
		if err != nil {
			http.Error(w, `{"error": "matching failed"}`, http.StatusInternalServerError)
			return
		}

		var matches []forge.Match
		for _, c := range candidates {
			tier := forge.ClassifyTierCurated(c.SharedCount, c.ContrastCount)
			matches = append(matches, forge.Match{
				SynsetID:         c.SynsetID,
				Word:             c.Word,
				Definition:       c.Definition,
				SharedProperties: c.SharedProps,
				OverlapCount:     c.SharedCount,
				Distance:         0, // No cosine distance in curated path
				Tier:             tier,
				TierName:         tier.String(),
			})
		}

		sorted := forge.SortByTier(matches)
		// ... encode response (same as existing)
	} else {
		// Legacy path: cosine-distance mega-query (existing code)
		// ... (unchanged)
	}
```

**Step 3: Update SortByTier to handle new tiers**

The existing `SortByTier` already sorts by tier ordinal, so Ironic (5) and Complex (6) will sort after Unlikely (4). Update the sort to place Ironic after Strong, Complex after Legendary:

In `api/internal/forge/forge.go`, reorder the tier constants:

```go
const (
	TierLegendary   Tier = iota // High shared + low contrast
	TierComplex                 // High shared + high contrast
	TierInteresting             // High distance + weak overlap (legacy path only)
	TierIronic                  // Low shared + high contrast
	TierStrong                  // Moderate shared
	TierObvious                 // Low distance + any overlap (legacy path only)
	TierUnlikely                // Low everything
)
```

**Step 4: Run all Go tests**

Run: `cd /home/agent/projects/metaforge/.worktrees/main && export PATH="/usr/local/go/bin:$PATH" && go test ./... -v`
Expected: All tests pass

**Step 5: Commit**

```bash
git add api/internal/handler/handler.go api/internal/forge/forge.go
git commit -m "feat(handler): wire curated forge path with auto-detection + tier reordering"
```

---

## Batch 3: Frontend — Tier Colours

### Task 10: Add Ironic and Complex tier colours

Extend the colour constants and graph types for the two new forge tiers.

**Files:**
- Modify: `web/src/graph/colours.ts`
- Modify: `web/src/graph/types.ts`

**Step 1: Write the failing test**

Add to the appropriate test file (or create `web/src/graph/colours.test.ts`):

```typescript
import { describe, it, expect } from 'vitest'
import { FORGE_TIER_COLOURS } from '@/graph/colours'

describe('FORGE_TIER_COLOURS', () => {
  it('includes ironic tier', () => {
    expect(FORGE_TIER_COLOURS.ironic).toBeDefined()
  })

  it('includes complex tier', () => {
    expect(FORGE_TIER_COLOURS.complex).toBeDefined()
  })
})
```

**Step 2: Run test to verify it fails**

Run: `cd /home/agent/projects/metaforge/.worktrees/main/web && npx vitest run --reporter=verbose`
Expected: FAIL — `FORGE_TIER_COLOURS` not exported

**Step 3: Add tier colours**

Add to `web/src/graph/colours.ts`:

```typescript
/** Forge tier type — all tiers including curated vocabulary tiers. */
export type ForgeTier = 'legendary' | 'complex' | 'interesting' | 'ironic' | 'strong' | 'obvious' | 'unlikely'

/** Colour map for forge tiers — used in results panel and future forge UI. */
export const FORGE_TIER_COLOURS: Record<ForgeTier, string> = {
  legendary: '#d4af37',   // Gold — best metaphors
  complex: '#c49a6c',     // Amber — simultaneously alike and opposed
  interesting: '#6a8b6f', // Green — wild cards
  ironic: '#8b4a6f',      // Magenta — ironic contrast metaphors
  strong: '#c4956a',      // Copper — solid matches
  obvious: '#8b6f47',     // Russet — too close
  unlikely: '#6b6560',    // Slate — weak
}
```

**Step 4: Run test to verify it passes**

Run: `cd /home/agent/projects/metaforge/.worktrees/main/web && npx vitest run --reporter=verbose`
Expected: All tests pass

**Step 5: Commit**

```bash
git add web/src/graph/colours.ts web/src/graph/colours.test.ts
git commit -m "feat(frontend): add Ironic + Complex forge tier colours"
```

---

## Batch 4: Integration — Run Pipeline on Real Data

### Task 11: Run vocabulary build on lexicon_v2.db

Execute `build_vocab.py` against the real database. This is a manual step — no test, just execution.

**Prerequisite:** 20K enrichment must be complete first. If only 2K pilot data exists, run on that as validation.

**Step 1: Build vocabulary**

Run: `cd /home/agent/projects/metaforge/.worktrees/main && data-pipeline/.venv/bin/python data-pipeline/scripts/build_vocab.py --db data-pipeline/output/lexicon_v2.db --top-n 35000`
Expected: `Stored ~25-30k vocabulary entries`

**Step 2: Snap properties**

Run: `cd /home/agent/projects/metaforge/.worktrees/main && data-pipeline/.venv/bin/python data-pipeline/scripts/snap_properties.py --db data-pipeline/output/lexicon_v2.db --threshold 0.7`
Expected: Snap rate report printed

**Step 3: Build antonyms**

Run: `cd /home/agent/projects/metaforge/.worktrees/main && data-pipeline/.venv/bin/python data-pipeline/scripts/build_antonyms.py --db data-pipeline/output/lexicon_v2.db`
Expected: `Found N antonym pairs`

**Step 4: Run audit**

Run: `cd /home/agent/projects/metaforge/.worktrees/main && data-pipeline/.venv/bin/python data-pipeline/scripts/analysis/snap_audit.py --db data-pipeline/output/lexicon_v2.db`
Expected: Full audit report

**Step 5: Dump and commit schema**

```bash
cd /home/agent/projects/metaforge/.worktrees/main
sqlite3 data-pipeline/output/lexicon_v2.db .dump > data-pipeline/output/lexicon_v2.sql
git add data-pipeline/output/lexicon_v2.sql
git commit -m "data: rebuild lexicon with curated vocabulary, snapped properties, antonym pairs"
```

---

### Task 12: Deploy and test on staging

Build Go binary, deploy via deploy.sh, verify forge endpoint returns new tiers.

**Step 1: Build and deploy**

Run: `bash /home/agent/projects/metaforge/.worktrees/main/deploy/staging/deploy.sh`
Expected: 4/4 health checks pass

**Step 2: Test forge endpoint**

Run: `curl -s 'https://metaforge.julianit.me/forge/suggest?word=grief&limit=10' | jq '.suggestions[] | {word, tier, overlap_count}'`
Expected: Results include tier values like "legendary", "ironic", "complex"

**Step 3: Commit deploy verification**

No code change — just verify staging works.

---

## Summary

| Batch | Tasks | Focus | Tests |
|-------|-------|-------|-------|
| 1 | 1-6 | Pipeline: vocab build, snap, antonyms, audit, schema | ~16 Python tests |
| 2 | 7-9 | Go API: new tiers, curated query, handler wiring | ~7 Go tests |
| 3 | 10 | Frontend: tier colours | ~2 TS tests |
| 4 | 11-12 | Integration: run on real data, deploy | Manual |

**Total estimated tests:** ~25 new tests across Python, Go, TypeScript.

**Dependencies:** Tasks 1-6 can proceed independently of the 20K enrichment (validate with 2K pilot data). Tasks 7-9 can be developed in parallel with Batch 1. Task 10 is independent. Tasks 11-12 require all prior tasks complete.
