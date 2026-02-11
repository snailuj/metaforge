"""Test VerbNet selective import."""
import sqlite3
import pytest

from utils import LEXICON_V2


def test_classes_imported():
    """Verify vn_classes table populated."""
    conn = sqlite3.connect(LEXICON_V2)
    count = conn.execute("SELECT COUNT(*) FROM vn_classes").fetchone()[0]
    conn.close()
    assert count > 500, f"Expected 500+ VerbNet classes, got {count}"


def test_class_members_imported():
    """Verify vn_class_members links verbs to classes."""
    conn = sqlite3.connect(LEXICON_V2)
    count = conn.execute("SELECT COUNT(*) FROM vn_class_members").fetchone()[0]
    conn.close()
    assert count > 5000, f"Expected 5000+ class memberships, got {count}"


def test_roles_imported():
    """Verify vn_roles table populated."""
    conn = sqlite3.connect(LEXICON_V2)
    count = conn.execute("SELECT COUNT(*) FROM vn_roles").fetchone()[0]
    conn.close()
    assert count > 1000, f"Expected 1000+ theta roles, got {count}"


def test_examples_imported():
    """Verify vn_examples table populated."""
    conn = sqlite3.connect(LEXICON_V2)
    count = conn.execute("SELECT COUNT(*) FROM vn_examples").fetchone()[0]
    conn.close()
    assert count > 1000, f"Expected 1000+ examples, got {count}"


def test_class_member_synset_links():
    """Verify class members link to valid OEWN synsets."""
    conn = sqlite3.connect(LEXICON_V2)
    # Check a sample has valid synset reference
    row = conn.execute("""
        SELECT vc.class_name, s.definition
        FROM vn_class_members vcm
        JOIN vn_classes vc ON vc.class_id = vcm.classid
        JOIN synsets s ON s.synset_id = vcm.synsetid
        LIMIT 1
    """).fetchone()
    conn.close()
    assert row is not None, "Should have VerbNet->synset links"
