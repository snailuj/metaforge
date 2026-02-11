"""End-to-end validation of lexicon_v2.db."""
import sqlite3
import struct
import math

import pytest

from utils import LEXICON_V2, EMBEDDING_DIM


def cosine_similarity(emb1: bytes, emb2: bytes) -> float:
    """Compute cosine similarity between two embedding blobs."""
    v1 = struct.unpack(f'{EMBEDDING_DIM}f', emb1)
    v2 = struct.unpack(f'{EMBEDDING_DIM}f', emb2)

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
        'synsets': 100000,      # OEWN: ~107k
        'lemmas': 180000,       # OEWN: ~185k
        'relations': 200000,    # OEWN: ~235k
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

    # Pairs we expect to be similar
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
    rows = conn.execute("""
        SELECT l1.lemma, l2.lemma
        FROM syntagms st
        JOIN lemmas l1 ON l1.synset_id = st.synset1id
        JOIN lemmas l2 ON l2.synset_id = st.synset2id
        LIMIT 5
    """).fetchall()

    conn.close()

    assert len(rows) >= 1, "Should have SyntagNet collocations"


def test_embedding_dimensions_consistent():
    """Verify all embeddings are 300d FastText."""
    conn = sqlite3.connect(LEXICON_V2)

    rows = conn.execute("""
        SELECT text, LENGTH(embedding) as emb_len
        FROM property_vocabulary
        WHERE embedding IS NOT NULL
        LIMIT 100
    """).fetchall()

    conn.close()

    expected_bytes = EMBEDDING_DIM * 4  # 300 floats * 4 bytes = 1200
    for text, emb_len in rows:
        assert emb_len == expected_bytes, f"Property '{text}' has {emb_len} bytes, expected {expected_bytes}"
