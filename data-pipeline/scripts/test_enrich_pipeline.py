"""Tests for enrich_pipeline.py — consolidated downstream enrichment pipeline.

All tests use in-memory SQLite — no real DB or FastText vectors needed.
"""
import json
import sqlite3
import struct
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from enrich_pipeline import (
    MAX_PROPERTIES_PER_SYNSET,
    _extract_property_text,  # noqa: F401 — exported for downstream test coverage
    _fasttext_cache,
    _ensure_v2_schema,
    curate_properties,
    filter_mwe,
    load_fasttext_vectors,
    populate_lemma_metadata,
    populate_synset_properties,
    store_lemma_embeddings,
    run_pipeline,
)
from utils import EMBEDDING_DIM


# --- Helpers ------------------------------------------------------------------

SCHEMA_SQL = """
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

CREATE TABLE property_vocabulary (
    property_id INTEGER PRIMARY KEY,
    text TEXT NOT NULL UNIQUE,
    embedding BLOB,
    is_oov INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'pilot'
);

CREATE TABLE enrichment (
    synset_id TEXT PRIMARY KEY,
    connotation TEXT CHECK (connotation IN ('positive', 'neutral', 'negative')),
    register TEXT CHECK (register IN ('formal', 'neutral', 'informal', 'slang')),
    usage_example TEXT,
    model_used TEXT,
    extracted_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE synset_properties (
    synset_id TEXT NOT NULL,
    property_id INTEGER NOT NULL,
    salience REAL NOT NULL DEFAULT 1.0,
    property_type TEXT,
    relation TEXT,
    PRIMARY KEY (synset_id, property_id)
);

CREATE TABLE lemma_metadata (
    lemma       TEXT NOT NULL,
    synset_id   TEXT NOT NULL,
    register    TEXT CHECK (register IN ('formal', 'neutral', 'informal', 'slang')),
    connotation TEXT CHECK (connotation IN ('positive', 'neutral', 'negative')),
    PRIMARY KEY (lemma, synset_id)
);

CREATE TABLE frequencies (
    lemma TEXT PRIMARY KEY,
    familiarity REAL
);

CREATE TABLE relations (
    source_synset TEXT NOT NULL,
    target_synset TEXT NOT NULL,
    relation_type TEXT NOT NULL
);
"""


def _make_vec(*values) -> tuple:
    """Create a 300d vector with given initial values, rest zeros."""
    full = list(values) + [0.0] * (EMBEDDING_DIM - len(values))
    return tuple(full)


def _make_blob(*values) -> bytes:
    """Create a 300d embedding blob with given initial values, rest zeros."""
    vec = _make_vec(*values)
    return struct.pack(f"{EMBEDDING_DIM}f", *vec)


def _make_db() -> sqlite3.Connection:
    """Create an in-memory DB with the minimal schema for testing."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA_SQL)
    return conn


def _make_enrichment_data():
    """Create minimal enrichment JSON structure."""
    return {
        "synsets": [
            {
                "id": "syn001",
                "lemma": "candle",
                "definition": "stick of wax with a wick",
                "pos": "n",
                "properties": ["warm", "flickering", "luminous"],
            },
            {
                "id": "syn002",
                "lemma": "storm",
                "definition": "violent weather condition",
                "pos": "n",
                "properties": ["loud", "violent", "dark-grey"],
            },
        ],
        "config": {"model": "test-model"},
    }


def _make_vectors():
    """Create fake FastText vectors dict."""
    return {
        "warm": _make_vec(1.0, 0.0, 0.0),
        "flickering": _make_vec(0.8, 0.2, 0.0),
        "luminous": _make_vec(0.9, 0.1, 0.0),
        "loud": _make_vec(0.0, 1.0, 0.0),
        "violent": _make_vec(0.0, 0.8, 0.2),
        # "dark-grey" is NOT in vocab — compound word
        "dark": _make_vec(0.0, 0.0, 1.0),
        "grey": _make_vec(0.1, 0.0, 0.9),
    }


# --- 1. curate_properties inserts with embeddings ----------------------------

def test_curate_properties_inserts():
    conn = _make_db()
    data = _make_enrichment_data()
    vectors = _make_vectors()

    count = curate_properties(conn, data, vectors)

    rows = conn.execute("SELECT text, embedding, is_oov FROM property_vocabulary").fetchall()
    texts = {r[0] for r in rows}

    assert "warm" in texts
    assert "flickering" in texts
    assert "luminous" in texts
    assert "loud" in texts
    assert "violent" in texts
    assert count == len(texts)

    # Verify embeddings are present for in-vocab words
    warm_row = conn.execute(
        "SELECT embedding, is_oov FROM property_vocabulary WHERE text = 'warm'"
    ).fetchone()
    assert warm_row[0] is not None
    assert warm_row[1] == 0


# --- 2. curate_properties OOV flagged ----------------------------------------

def test_curate_properties_oov_flagged():
    conn = _make_db()
    # Use a property not in vectors
    data = {
        "synsets": [
            {"id": "s1", "properties": ["xyznonexistent"]},
        ],
    }
    vectors = _make_vectors()

    curate_properties(conn, data, vectors)

    row = conn.execute(
        "SELECT is_oov, embedding FROM property_vocabulary WHERE text = 'xyznonexistent'"
    ).fetchone()
    assert row[0] == 1  # is_oov
    assert row[1] is None  # no embedding


# --- 3. curate_properties compound embedding ---------------------------------

def test_curate_properties_compound_embedding():
    conn = _make_db()
    data = {
        "synsets": [
            {"id": "s1", "properties": ["dark-grey"]},
        ],
    }
    vectors = _make_vectors()

    curate_properties(conn, data, vectors)

    row = conn.execute(
        "SELECT embedding, is_oov FROM property_vocabulary WHERE text = 'dark-grey'"
    ).fetchone()
    # Should have an averaged embedding from "dark" and "grey"
    assert row[0] is not None
    assert row[1] == 0

    # Verify the averaging: dark=(0,0,1) grey=(0.1,0,0.9) → avg=(0.05,0,0.95)
    values = struct.unpack(f"{EMBEDDING_DIM}f", row[0])
    assert abs(values[0] - 0.05) < 0.01
    assert abs(values[2] - 0.95) < 0.01


# --- 4. populate_synset_properties -------------------------------------------

def test_populate_synset_properties():
    conn = _make_db()
    data = _make_enrichment_data()
    vectors = _make_vectors()

    curate_properties(conn, data, vectors)
    count = populate_synset_properties(conn, data, "test-model")

    # Check junction table entries
    rows = conn.execute("SELECT synset_id, property_id FROM synset_properties").fetchall()
    assert len(rows) > 0
    assert count == len(rows)

    # Check enrichment entries
    enrichment = conn.execute("SELECT synset_id, model_used FROM enrichment").fetchall()
    assert len(enrichment) == 2
    models = {r[1] for r in enrichment}
    assert "test-model" in models

    # Check syn001 has its 3 properties
    syn001_props = conn.execute(
        "SELECT COUNT(*) FROM synset_properties WHERE synset_id = 'syn001'"
    ).fetchone()[0]
    assert syn001_props == 3


# --- 5. run_pipeline end-to-end -----------------------------------------------

def test_run_pipeline_end_to_end(tmp_path):
    """Mock FastText loading, verify full pipeline produces correct tables."""
    # Write enrichment JSON
    data = _make_enrichment_data()
    enrichment_file = tmp_path / "enrichment.json"
    enrichment_file.write_text(json.dumps(data))

    # Create DB with schema
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA_SQL)
    conn.close()

    vectors = _make_vectors()

    with patch("enrich_pipeline.load_fasttext_vectors", return_value=vectors):
        stats = run_pipeline(str(db_path), [str(enrichment_file)], "dummy.vec")

    assert stats["properties_curated"] > 0
    assert stats["synset_links"] > 0
    assert "lemma_embeddings" in stats
    assert stats["lemma_embeddings"] >= 0

    # Verify tables populated
    conn = sqlite3.connect(str(db_path))
    prop_count = conn.execute("SELECT COUNT(*) FROM property_vocabulary").fetchone()[0]
    sp_count = conn.execute("SELECT COUNT(*) FROM synset_properties").fetchone()[0]
    lemma_emb_table = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='lemma_embeddings'"
    ).fetchone()[0]
    conn.close()

    assert prop_count > 0
    assert sp_count > 0
    assert lemma_emb_table == 1


# --- 9. curate_properties caps per synset ------------------------------------

def test_curate_properties_caps_per_synset():
    """Only MAX_PROPERTIES_PER_SYNSET properties per synset enter vocabulary."""
    conn = _make_db()
    # Generate 20 unique properties — all single words so they get embeddings
    props_20 = [f"prop{i}" for i in range(20)]
    data = {
        "synsets": [
            {"id": "s1", "properties": props_20},
        ],
    }
    # All 20 words in vectors so none are filtered by OOV
    vectors = {p: _make_vec(float(i)) for i, p in enumerate(props_20)}

    count = curate_properties(conn, data, vectors)

    assert count == MAX_PROPERTIES_PER_SYNSET


# --- 10. populate_synset_properties caps per synset --------------------------

def test_populate_synset_properties_caps_per_synset():
    """Junction table has at most MAX_PROPERTIES_PER_SYNSET rows per synset."""
    conn = _make_db()
    props_20 = [f"prop{i}" for i in range(20)]
    data = {
        "synsets": [
            {"id": "s1", "properties": props_20},
        ],
    }
    vectors = {p: _make_vec(float(i)) for i, p in enumerate(props_20)}

    curate_properties(conn, data, vectors)
    links = populate_synset_properties(conn, data, "test-model")

    row_count = conn.execute(
        "SELECT COUNT(*) FROM synset_properties WHERE synset_id = 's1'"
    ).fetchone()[0]

    assert links == MAX_PROPERTIES_PER_SYNSET
    assert row_count == MAX_PROPERTIES_PER_SYNSET


# --- 8. FastText vector caching -----------------------------------------------

@patch("enrich_pipeline.EMBEDDING_DIM", 3)
def test_load_fasttext_vectors_caches(tmp_path):
    """Second call with same path returns cached vectors without re-reading."""
    vec_file = tmp_path / "test.vec"
    vec_file.write_text("2 3\nhello 1.0 0.0 0.0\nworld 0.0 1.0 0.0\n")

    # Clear any prior cache state
    _fasttext_cache.clear()

    v1 = load_fasttext_vectors(str(vec_file))
    assert "hello" in v1

    # Delete the file — second call must use cache, not disk
    vec_file.unlink()

    v2 = load_fasttext_vectors(str(vec_file))
    assert v1 is v2

    _fasttext_cache.clear()


def test_load_fasttext_vectors_rejects_wrong_dimension(tmp_path):
    """Loading vectors with dimension != EMBEDDING_DIM raises ValueError."""
    vec_file = tmp_path / "wrong_dim.vec"
    vec_file.write_text("2 5\nhello 1.0 0.0 0.0 0.0 0.0\nworld 0.0 1.0 0.0 0.0 0.0\n")

    _fasttext_cache.clear()

    with pytest.raises(ValueError, match=r"dimension.*5.*300"):
        load_fasttext_vectors(str(vec_file))

    _fasttext_cache.clear()


# --- 14. filter_mwe — pure function tests ------------------------------------

def test_filter_mwe_single_word_unchanged():
    """Single-token property passes through unchanged."""
    assert filter_mwe("warm") == "warm"


def test_filter_mwe_strips_adjective():
    """Adjective stripped from 2-word MWE, leaving the noun."""
    assert filter_mwe("sluggish seep") == "seep"


def test_filter_mwe_strips_adverb():
    """Both adverb + adjective stripped → 0 remain → None."""
    assert filter_mwe("very likely") is None


def test_filter_mwe_discards_two_nouns():
    """Two nouns remain after stripping → discard (not exactly 1)."""
    assert filter_mwe("ghost outline") is None


def test_filter_mwe_keeps_hyphenated():
    """Hyphenated compound is 1 token → keep as-is."""
    assert filter_mwe("blood-red") == "blood-red"


def test_filter_mwe_strips_to_single_noun():
    """Adjective stripped from 'bright glow' → 'glow'."""
    assert filter_mwe("bright glow") == "glow"


# --- 15. curate_properties MWE filtering integration -------------------------

def test_curate_properties_filters_mwe():
    """MWE properties are filtered: 'sluggish seep' → 'seep', 'ghost outline' discarded."""
    conn = _make_db()
    data = {
        "synsets": [
            {
                "id": "s1",
                "properties": ["sluggish seep", "ghost outline", "warm"],
            },
        ],
    }
    vectors = {
        "seep": _make_vec(0.5, 0.5, 0.0),
        "warm": _make_vec(1.0, 0.0, 0.0),
        "ghost": _make_vec(0.0, 0.0, 1.0),
        "outline": _make_vec(0.0, 1.0, 0.0),
    }

    curate_properties(conn, data, vectors)

    texts = {r[0] for r in conn.execute("SELECT text FROM property_vocabulary").fetchall()}
    assert "seep" in texts        # sluggish (JJ) stripped → seep kept
    assert "warm" in texts        # single word kept
    assert "sluggish seep" not in texts  # MWE not stored raw
    assert "ghost outline" not in texts  # NN+NN → discarded


# --- 16. populate_synset_properties MWE filtering integration ----------------

def test_populate_applies_mwe_filter():
    """'sluggish seep' links to property_id for 'seep', not 'sluggish seep'."""
    conn = _make_db()
    data = {
        "synsets": [
            {
                "id": "s1",
                "properties": ["sluggish seep", "warm"],
            },
        ],
    }
    vectors = {
        "seep": _make_vec(0.5, 0.5, 0.0),
        "warm": _make_vec(1.0, 0.0, 0.0),
    }

    curate_properties(conn, data, vectors)
    links = populate_synset_properties(conn, data, "test-model")

    # Should have 2 links: seep + warm
    assert links == 2

    # Verify "seep" property_id is linked to s1
    seep_id = conn.execute(
        "SELECT property_id FROM property_vocabulary WHERE text = 'seep'"
    ).fetchone()[0]
    link = conn.execute(
        "SELECT * FROM synset_properties WHERE synset_id = 's1' AND property_id = ?",
        (seep_id,),
    ).fetchone()
    assert link is not None


# --- 17. run_pipeline creates curated tables ----------------------------------

def test_run_pipeline_creates_curated_tables(tmp_path):
    """run_pipeline() should create property_vocab_curated, synset_properties_curated,
    and property_antonyms tables via the curated pipeline integration."""
    data = _make_enrichment_data()
    enrichment_file = tmp_path / "enrichment.json"
    enrichment_file.write_text(json.dumps(data))

    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA_SQL)
    conn.close()

    vectors = _make_vectors()

    with patch("enrich_pipeline.load_fasttext_vectors", return_value=vectors):
        stats = run_pipeline(str(db_path), [str(enrichment_file)], "dummy.vec")

    # Curated tables must exist
    conn = sqlite3.connect(str(db_path))
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    conn.close()

    assert "property_vocab_curated" in tables
    assert "synset_properties_curated" in tables
    assert "property_antonyms" in tables

    # Stats dict must include curated keys
    assert "vocab_entries" in stats
    assert "snapped_properties" in stats
    assert "antonym_pairs" in stats


# --- 18. curate_properties preserves existing IDs on re-run -------------------

def test_curate_properties_preserves_existing_ids():
    """Re-running curate+populate with overlapping properties preserves IDs and links."""
    conn = _make_db()
    vectors = {
        "hot": _make_vec(1.0, 0.0, 0.0),
        "cold": _make_vec(0.0, 1.0, 0.0),
        "wet": _make_vec(0.0, 0.0, 1.0),
    }

    # --- Enrichment A: hot + cold for synset s1 ---
    data_a = {
        "synsets": [{"id": "s1", "properties": ["hot", "cold"]}],
        "config": {"model": "model-a"},
    }
    curate_properties(conn, data_a, vectors)
    populate_synset_properties(conn, data_a, "model-a")

    hot_id_before = conn.execute(
        "SELECT property_id FROM property_vocabulary WHERE text = 'hot'"
    ).fetchone()[0]
    cold_id_before = conn.execute(
        "SELECT property_id FROM property_vocabulary WHERE text = 'cold'"
    ).fetchone()[0]

    # --- Enrichment B: hot (overlap) + wet (new) for synset s2 ---
    data_b = {
        "synsets": [{"id": "s2", "properties": ["hot", "wet"]}],
        "config": {"model": "model-b"},
    }
    curate_properties(conn, data_b, vectors)
    populate_synset_properties(conn, data_b, "model-b")

    # Property IDs for hot and cold must be unchanged
    hot_id_after = conn.execute(
        "SELECT property_id FROM property_vocabulary WHERE text = 'hot'"
    ).fetchone()[0]
    cold_id_after = conn.execute(
        "SELECT property_id FROM property_vocabulary WHERE text = 'cold'"
    ).fetchone()[0]
    assert hot_id_after == hot_id_before, "hot property_id changed on re-run"
    assert cold_id_after == cold_id_before, "cold property_id changed on re-run"

    # s1 links still resolve via JOIN
    s1_props = conn.execute(
        """SELECT pv.text FROM synset_properties sp
           JOIN property_vocabulary pv ON pv.property_id = sp.property_id
           WHERE sp.synset_id = 's1'"""
    ).fetchall()
    s1_texts = {r[0] for r in s1_props}
    assert s1_texts == {"hot", "cold"}, f"s1 links broken: {s1_texts}"

    # s2 links also resolve
    s2_props = conn.execute(
        """SELECT pv.text FROM synset_properties sp
           JOIN property_vocabulary pv ON pv.property_id = sp.property_id
           WHERE sp.synset_id = 's2'"""
    ).fetchall()
    s2_texts = {r[0] for r in s2_props}
    assert s2_texts == {"hot", "wet"}, f"s2 links broken: {s2_texts}"

    # "wet" got a new property_id (distinct from hot and cold)
    wet_id = conn.execute(
        "SELECT property_id FROM property_vocabulary WHERE text = 'wet'"
    ).fetchone()[0]
    assert wet_id != hot_id_before
    assert wet_id != cold_id_before


# --- 19. store_lemma_embeddings -----------------------------------------------

def test_store_lemma_embeddings():
    """store_lemma_embeddings creates table and stores correct blobs for known lemmas."""
    conn = _make_db()
    # Insert some lemmas into the lemmas table
    conn.executemany(
        "INSERT INTO lemmas (lemma, synset_id) VALUES (?, ?)",
        [("anger", "s1"), ("fire", "s2"), ("xyznotinvectors", "s3")],
    )
    conn.commit()

    vectors = {
        "anger": _make_vec(0.5, 0.3, 0.1),
        "fire": _make_vec(0.9, 0.1, 0.0),
        # "xyznotinvectors" deliberately absent — OOV lemma
    }

    count = store_lemma_embeddings(conn, vectors)

    # Should store 2 embeddings (anger + fire), skip OOV
    assert count == 2

    # Table should exist
    table_check = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='lemma_embeddings'"
    ).fetchone()[0]
    assert table_check == 1

    # Verify correct blobs stored
    row = conn.execute(
        "SELECT embedding FROM lemma_embeddings WHERE lemma = 'anger'"
    ).fetchone()
    assert row is not None
    values = struct.unpack(f"{EMBEDDING_DIM}f", row[0])
    assert abs(values[0] - 0.5) < 0.01
    assert abs(values[1] - 0.3) < 0.01

    row = conn.execute(
        "SELECT embedding FROM lemma_embeddings WHERE lemma = 'fire'"
    ).fetchone()
    assert row is not None

    # OOV lemma should NOT be in the table
    row = conn.execute(
        "SELECT embedding FROM lemma_embeddings WHERE lemma = 'xyznotinvectors'"
    ).fetchone()
    assert row is None


def test_store_lemma_embeddings_deduplicates():
    """Lemmas appearing in multiple synsets are stored once."""
    conn = _make_db()
    conn.executemany(
        "INSERT INTO lemmas (lemma, synset_id) VALUES (?, ?)",
        [("bank", "s1"), ("bank", "s2"), ("river", "s3")],
    )
    conn.commit()

    vectors = {
        "bank": _make_vec(0.1, 0.2, 0.3),
        "river": _make_vec(0.4, 0.5, 0.6),
    }

    count = store_lemma_embeddings(conn, vectors)
    assert count == 2

    rows = conn.execute("SELECT COUNT(*) FROM lemma_embeddings").fetchone()[0]
    assert rows == 2


def test_store_lemma_embeddings_idempotent():
    """Re-running updates existing embeddings without error or duplicates."""
    conn = _make_db()
    conn.execute("INSERT INTO lemmas (lemma, synset_id) VALUES ('anger', 's1')")
    conn.commit()

    vectors_v1 = {"anger": _make_vec(0.1, 0.2, 0.3)}
    count1 = store_lemma_embeddings(conn, vectors_v1)
    assert count1 == 1

    # Re-run with updated vector — should replace, not duplicate
    vectors_v2 = {"anger": _make_vec(0.9, 0.8, 0.7)}
    count2 = store_lemma_embeddings(conn, vectors_v2)
    assert count2 == 1

    # Still exactly one row
    rows = conn.execute("SELECT COUNT(*) FROM lemma_embeddings").fetchone()[0]
    assert rows == 1

    # Value should be updated
    blob = conn.execute(
        "SELECT embedding FROM lemma_embeddings WHERE lemma = 'anger'"
    ).fetchone()[0]
    values = struct.unpack(f"{EMBEDDING_DIM}f", blob)
    assert abs(values[0] - 0.9) < 0.01, f"expected 0.9, got {values[0]}"


def test_store_lemma_embeddings_empty_lemmas():
    """Empty lemmas table returns 0 without error."""
    conn = _make_db()
    # lemmas table exists but is empty
    count = store_lemma_embeddings(conn, {"anger": _make_vec(1.0)})
    assert count == 0


def test_store_lemma_embeddings_empty_vectors():
    """Empty vectors dict returns 0 — all lemmas are OOV."""
    conn = _make_db()
    conn.execute("INSERT INTO lemmas (lemma, synset_id) VALUES ('anger', 's1')")
    conn.commit()

    count = store_lemma_embeddings(conn, {})
    assert count == 0


# --- 20. _ensure_v2_schema migration -----------------------------------------

def test_ensure_v2_schema_adds_columns():
    """_ensure_v2_schema adds salience, property_type, relation to synset_properties
    and creates lemma_metadata table."""
    conn = _make_db()
    # The test schema already has v2 columns, so create a minimal v1 schema
    conn.executescript("""
        DROP TABLE IF EXISTS synset_properties;
        CREATE TABLE synset_properties (
            synset_id TEXT NOT NULL,
            property_id INTEGER NOT NULL,
            PRIMARY KEY (synset_id, property_id)
        );
    """)
    _ensure_v2_schema(conn)

    # Check synset_properties has new columns
    cols = {r[1] for r in conn.execute("PRAGMA table_info(synset_properties)").fetchall()}
    assert "salience" in cols
    assert "property_type" in cols
    assert "relation" in cols

    # Check lemma_metadata table exists
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert "lemma_metadata" in tables


# --- 21. populate_lemma_metadata ----------------------------------------------

def test_populate_lemma_metadata_inserts():
    """populate_lemma_metadata stores per-lemma register and connotation."""
    conn = _make_db()
    data = {
        "synsets": [
            {
                "id": "syn001",
                "lemma": "candle",
                "properties": ["warm"],
                "lemma_metadata": [
                    {"lemma": "candle", "register": "neutral", "connotation": "positive"},
                    {"lemma": "taper", "register": "formal", "connotation": "neutral"},
                ],
            },
        ],
    }
    count = populate_lemma_metadata(conn, data)

    assert count == 2
    rows = conn.execute("SELECT lemma, synset_id, register, connotation FROM lemma_metadata").fetchall()
    assert len(rows) == 2
    by_lemma = {r[0]: r for r in rows}
    assert by_lemma["candle"][2] == "neutral"
    assert by_lemma["candle"][3] == "positive"
    assert by_lemma["taper"][2] == "formal"
    assert by_lemma["taper"][3] == "neutral"


# --- 22. _extract_property_text helper ----------------------------------------

def test_extract_property_text_v1_string():
    """_extract_property_text returns plain string as-is."""
    assert _extract_property_text("warm") == "warm"


def test_extract_property_text_v2_object():
    """_extract_property_text extracts .text from v2 structured object."""
    assert _extract_property_text({"text": "warm", "salience": 0.9}) == "warm"


def test_extract_property_text_missing_text():
    """_extract_property_text returns None for dict without .text key."""
    assert _extract_property_text({"salience": 0.9}) is None


# --- 23. curate_properties handles v2 structured objects ----------------------

def test_curate_properties_handles_v2_structured():
    """curate_properties extracts .text from v2 structured property objects."""
    conn = _make_db()
    data = {
        "synsets": [
            {
                "id": "syn001",
                "properties": [
                    {"text": "warm", "salience": 0.9, "type": "physical", "relation": "emits warmth"},
                    {"text": "luminous", "salience": 0.7, "type": "visual", "relation": "gives light"},
                    "cold",  # v1 plain string mixed in
                ],
            },
        ],
    }
    vectors = _make_vectors()
    count = curate_properties(conn, data, vectors)

    texts = {r[0] for r in conn.execute("SELECT text FROM property_vocabulary").fetchall()}
    assert "warm" in texts
    assert "luminous" in texts
    assert "cold" in texts


# --- 24. populate_synset_properties stores v2 salience/type/relation ----------

def test_populate_synset_properties_v2_stores_salience():
    """populate_synset_properties stores salience, property_type, relation from v2 objects."""
    conn = _make_db()
    data = {
        "synsets": [
            {
                "id": "syn001",
                "lemma": "candle",
                "definition": "stick of wax",
                "pos": "n",
                "usage_example": "She lit a candle.",
                "properties": [
                    {"text": "warm", "salience": 0.9, "type": "physical", "relation": "emits warmth"},
                    {"text": "luminous", "salience": 0.7, "type": "visual", "relation": "gives light"},
                ],
            },
        ],
        "config": {"model": "test-model"},
    }
    vectors = _make_vectors()
    curate_properties(conn, data, vectors)
    populate_synset_properties(conn, data, "test-model")

    rows = conn.execute(
        "SELECT synset_id, salience, property_type, relation FROM synset_properties WHERE synset_id = 'syn001'"
    ).fetchall()
    assert len(rows) == 2
    saliences = {r[1] for r in rows}
    assert 0.9 in saliences
    assert 0.7 in saliences
    types = {r[2] for r in rows}
    assert "physical" in types
    assert "visual" in types


# --- 25. populate_synset_properties stores usage_example ----------------------

def test_populate_synset_properties_populates_usage_example():
    """populate_synset_properties stores usage_example in enrichment table."""
    conn = _make_db()
    data = {
        "synsets": [
            {
                "id": "syn001",
                "lemma": "candle",
                "definition": "stick of wax",
                "pos": "n",
                "usage_example": "She lit a candle in the dark.",
                "properties": ["warm"],
            },
        ],
        "config": {"model": "test-model"},
    }
    vectors = _make_vectors()
    curate_properties(conn, data, vectors)
    populate_synset_properties(conn, data, "test-model")

    row = conn.execute(
        "SELECT usage_example FROM enrichment WHERE synset_id = 'syn001'"
    ).fetchone()
    assert row is not None
    assert row[0] == "She lit a candle in the dark."


# --- v2 enrichment prompt tests -----------------------------------------------

def test_format_batch_items_v2_includes_lemmas():
    """format_batch_items_v2 includes all lemmas per synset."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from enrich_properties import format_batch_items_v2

    synsets = [
        {
            "id": "oewn-candle-n",
            "lemma": "candle",
            "definition": "stick of wax with a wick",
            "pos": "n",
            "all_lemmas": ["candle", "taper"],
        },
    ]
    result = format_batch_items_v2(synsets)
    assert "ID: oewn-candle-n" in result
    assert "Word: candle" in result
    assert "Lemmas: candle, taper" in result
    assert "Definition: stick of wax with a wick" in result


def test_extract_batch_v2_returns_structured_properties():
    """extract_batch with v2 prompt returns structured property objects."""
    from unittest.mock import patch
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from enrich_properties import extract_batch

    synsets = [
        {
            "id": "syn001",
            "lemma": "candle",
            "definition": "stick of wax with a wick",
            "pos": "n",
            "all_lemmas": ["candle", "taper"],
        },
    ]

    # Mock the LLM response to return v2 structured data
    mock_response = [
        {
            "id": "syn001",
            "usage_example": "She lit a candle in the dark.",
            "properties": [
                {"text": "warm", "salience": 0.9, "type": "physical", "relation": "candle emits warmth"},
                {"text": "flickering", "salience": 0.85, "type": "behaviour", "relation": "flame flickers"},
            ],
            "lemma_metadata": [
                {"lemma": "candle", "register": "neutral", "connotation": "positive"},
                {"lemma": "taper", "register": "formal", "connotation": "neutral"},
            ],
        },
    ]

    with patch("enrich_properties.prompt_json", return_value=mock_response):
        results = extract_batch(synsets, model="test")

    assert len(results) == 1
    r = results[0]
    assert r["id"] == "syn001"
    assert r["usage_example"] == "She lit a candle in the dark."
    assert len(r["properties"]) == 2
    # v2 properties are structured objects
    assert r["properties"][0]["text"] == "warm"
    assert r["properties"][0]["salience"] == 0.9
    assert len(r["lemma_metadata"]) == 2


# --- 26. run_pipeline v2 end-to-end -------------------------------------------

def test_run_pipeline_v2_end_to_end(tmp_path):
    """run_pipeline with v2 enrichment JSON stores salience, lemma_metadata, usage_example."""
    data = {
        "synsets": [
            {
                "id": "syn001",
                "lemma": "candle",
                "definition": "stick of wax with a wick",
                "pos": "n",
                "usage_example": "She lit a candle in the draught.",
                "properties": [
                    {"text": "warm", "salience": 0.9, "type": "physical", "relation": "emits warmth"},
                    {"text": "flickering", "salience": 0.85, "type": "behaviour", "relation": "flame flickers"},
                    {"text": "luminous", "salience": 0.7, "type": "visual", "relation": "gives light"},
                ],
                "lemma_metadata": [
                    {"lemma": "candle", "register": "neutral", "connotation": "positive"},
                ],
            },
            {
                "id": "syn002",
                "lemma": "storm",
                "definition": "violent weather condition",
                "pos": "n",
                "properties": [
                    {"text": "loud", "salience": 0.8, "type": "physical", "relation": "storm is loud"},
                    {"text": "violent", "salience": 0.95, "type": "behaviour", "relation": "storm is violent"},
                ],
                "lemma_metadata": [
                    {"lemma": "storm", "register": "neutral", "connotation": "negative"},
                ],
            },
        ],
        "config": {"model": "test-model", "schema_version": "v2"},
    }

    enrichment_file = tmp_path / "enrichment_v2.json"
    enrichment_file.write_text(json.dumps(data))

    db_path = tmp_path / "test_v2.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA_SQL)

    # Populate base tables so build_vocab produces curated entries that snap can match
    base_words = [
        ("oewn-warm-a", "a", "having warmth", "warm"),
        ("oewn-flickering-a", "a", "shining unsteadily", "flickering"),
        ("oewn-luminous-a", "a", "softly bright", "luminous"),
        ("oewn-loud-a", "a", "high in volume", "loud"),
        ("oewn-violent-a", "a", "acting with force", "violent"),
    ]
    for sid, pos, defn, lemma in base_words:
        conn.execute("INSERT INTO synsets VALUES (?, ?, ?)", (sid, pos, defn))
        conn.execute("INSERT INTO lemmas VALUES (?, ?)", (lemma, sid))
        conn.execute(
            "INSERT INTO frequencies (lemma, familiarity) VALUES (?, 5.0)",
            (lemma,),
        )
    conn.commit()
    conn.close()

    vectors = _make_vectors()

    with patch("enrich_pipeline.load_fasttext_vectors", return_value=vectors):
        stats = run_pipeline(str(db_path), [str(enrichment_file)], "dummy.vec")

    assert stats["properties_curated"] > 0
    assert stats["synset_links"] > 0
    assert stats["lemma_metadata"] == 2

    # Verify salience stored in synset_properties
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT salience, property_type FROM synset_properties WHERE synset_id = 'syn001'"
    ).fetchall()
    saliences = {r[0] for r in rows}
    assert 0.9 in saliences
    assert 0.85 in saliences

    # Verify usage_example stored in enrichment
    row = conn.execute(
        "SELECT usage_example FROM enrichment WHERE synset_id = 'syn001'"
    ).fetchone()
    assert row[0] == "She lit a candle in the draught."

    # Verify lemma_metadata populated
    meta_rows = conn.execute("SELECT lemma, register, connotation FROM lemma_metadata").fetchall()
    assert len(meta_rows) == 2
    by_lemma = {r[0]: r for r in meta_rows}
    assert by_lemma["candle"][1] == "neutral"
    assert by_lemma["storm"][2] == "negative"

    # Verify snapped properties have salience_sum
    spc_rows = conn.execute(
        "SELECT salience_sum FROM synset_properties_curated WHERE synset_id = 'syn001'"
    ).fetchall()
    assert len(spc_rows) > 0
    # All should have non-zero salience_sum
    for row in spc_rows:
        assert row[0] > 0

    conn.close()
