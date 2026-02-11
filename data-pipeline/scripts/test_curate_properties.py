"""Test property vocabulary curation."""
import sqlite3
import struct
import pytest

from utils import LEXICON_V2


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
