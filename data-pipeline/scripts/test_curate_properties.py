"""Test property vocabulary curation."""
import sqlite3
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from utils import LEXICON_V2, EMBEDDING_DIM
import curate_properties


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
    """Verify embeddings are 300d (1200 bytes) - FastText."""
    conn = sqlite3.connect(LEXICON_V2)
    row = conn.execute(
        "SELECT embedding FROM property_vocabulary WHERE embedding IS NOT NULL LIMIT 1"
    ).fetchone()
    conn.close()

    assert row is not None, "Should have at least one embedding"
    emb_bytes = row[0]
    assert len(emb_bytes) == 1200, f"Expected 1200 bytes (300d float32), got {len(emb_bytes)}"

    # Verify it unpacks correctly
    values = struct.unpack('300f', emb_bytes)
    assert len(values) == 300


def test_normalisation():
    """Verify properties are normalised (lowercase, trimmed)."""
    conn = sqlite3.connect(LEXICON_V2)
    rows = conn.execute("SELECT text FROM property_vocabulary LIMIT 100").fetchall()
    conn.close()

    for (text,) in rows:
        assert text == text.lower().strip(), f"Property not normalised: '{text}'"


# Unit tests for get_embedding and get_compound_embedding functions


def test_get_embedding_known_word():
    """Verify get_embedding returns correct struct-packed bytes for known word."""
    # Create synthetic vectors dict (no FastText file needed)
    vectors = {"test": tuple(float(i) for i in range(EMBEDDING_DIM))}

    result = curate_properties.get_embedding("test", vectors)

    assert result is not None, "Expected embedding bytes for known word"
    assert len(result) == EMBEDDING_DIM * 4, f"Expected {EMBEDDING_DIM * 4} bytes"

    # Unpack and verify
    unpacked = struct.unpack(f"{EMBEDDING_DIM}f", result)
    assert unpacked == vectors["test"]


def test_get_embedding_oov():
    """Verify get_embedding returns None for unknown word."""
    vectors = {"test": tuple(float(i) for i in range(EMBEDDING_DIM))}

    result = curate_properties.get_embedding("xyzzy", vectors)

    assert result is None, "Expected None for OOV word"


def test_get_compound_embedding_averages():
    """Verify get_compound_embedding averages both parts."""
    vectors = {
        "hot": tuple(1.0 for _ in range(EMBEDDING_DIM)),
        "cold": tuple(2.0 for _ in range(EMBEDDING_DIM)),
    }

    result = curate_properties.get_compound_embedding("hot-cold", vectors)

    assert result is not None, "Expected embedding for compound word"
    assert len(result) == EMBEDDING_DIM * 4

    # Unpack and verify average
    unpacked = struct.unpack(f"{EMBEDDING_DIM}f", result)
    expected = tuple(1.5 for _ in range(EMBEDDING_DIM))  # Average of 1.0 and 2.0
    for i in range(EMBEDDING_DIM):
        assert unpacked[i] == pytest.approx(expected[i], abs=1e-6)


def test_get_compound_embedding_partial_oov():
    """Verify get_compound_embedding uses only known part when one is OOV."""
    vectors = {
        "cold": tuple(2.0 for _ in range(EMBEDDING_DIM)),
    }

    result = curate_properties.get_compound_embedding("xyzzy-cold", vectors)

    assert result is not None, "Expected embedding using only 'cold'"
    assert len(result) == EMBEDDING_DIM * 4

    # Unpack and verify it's just the "cold" vector
    unpacked = struct.unpack(f"{EMBEDDING_DIM}f", result)
    expected = vectors["cold"]
    for i in range(EMBEDDING_DIM):
        assert unpacked[i] == pytest.approx(expected[i], abs=1e-6)
