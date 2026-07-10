"""Tests for sense_inventory — noun-POS sense lookup, vec: gate, fan ranking,
and the precompute CLI (build_sense_inventories).

Fixture DB mirrors the table shapes present in lexicon_v2.db: synsets, lemmas,
sense_attributes. In-memory for unit tests; file-backed for the CLI idempotency
test.
"""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sense_inventory as si


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _build_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, pos TEXT, definition TEXT);
        CREATE TABLE lemmas (lemma TEXT, synset_id TEXT);
        CREATE TABLE sense_attributes (lemma TEXT, synset_id TEXT,
                                       sensenum INTEGER, tagcount INTEGER);
    """)
    rows = [
        ("100", "n", "a brief look"), ("101", "v", "look quickly"),
        ("102", "n", "a deflection"), ("200", "n", "an open sore"),
    ]
    conn.executemany("INSERT INTO synsets VALUES (?,?,?)", rows)
    conn.executemany("INSERT INTO lemmas VALUES (?,?)",
                     [("glance", "100"), ("glance", "101"), ("glance", "102"),
                      ("wound", "200")])
    conn.executemany("INSERT INTO sense_attributes VALUES (?,?,?,?)",
                     [("glance", "100", 1, 9), ("glance", "101", 2, 4),
                      ("glance", "102", 3, 0), ("wound", "200", 1, 2)])


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    _build_schema(conn)
    return conn


def _dump_fixture_to(path: Path) -> None:
    """Persist the fixture to a file-backed SQLite DB (for CLI idempotency test)."""
    conn = sqlite3.connect(str(path))
    _build_schema(conn)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# noun_inventory
# ---------------------------------------------------------------------------

def test_noun_inventory_filters_to_nouns_and_ranks_by_tagcount():
    inv = si.noun_inventory(_db(), "glance", "glance")
    assert [s["synset_id"] for s in inv] == ["100", "102"]  # verb 101 excluded
    assert inv[0]["tagcount"] == 9


def test_noun_inventory_falls_back_to_head_for_multiword():
    inv = si.noun_inventory(_db(), "buried wound", "wound")
    assert [s["synset_id"] for s in inv] == ["200"]


def test_noun_inventory_returns_required_keys():
    inv = si.noun_inventory(_db(), "glance", "glance")
    for entry in inv:
        for key in ("synset_id", "sensenum", "tagcount", "definition", "pos"):
            assert key in entry, f"missing key '{key}' in {entry}"


def test_noun_inventory_empty_for_unknown_phrase_and_head():
    inv = si.noun_inventory(_db(), "pressed flower", "flower")
    assert inv == []


# ---------------------------------------------------------------------------
# vec_gate
# ---------------------------------------------------------------------------

def test_vec_gate_true_only_when_no_noun_candidates_anywhere():
    conn = _db()
    assert si.vec_gate(conn, "pressed flower", "flower") is True   # neither known
    assert si.vec_gate(conn, "buried wound", "wound") is False     # head has a noun sense
    assert si.vec_gate(conn, "glance", "glance") is False


# ---------------------------------------------------------------------------
# rank_fan
# ---------------------------------------------------------------------------

def test_rank_fan_puts_intended_first_then_tagcount():
    inv = si.noun_inventory(_db(), "glance", "glance")
    fan = si.rank_fan(inv, intended_synset_id="102")
    assert [s["synset_id"] for s in fan] == ["102", "100"]
    assert si.rank_fan(inv, None)[0]["synset_id"] == "100"


def test_rank_fan_with_no_intended_preserves_tagcount_order():
    inv = si.noun_inventory(_db(), "glance", "glance")
    fan = si.rank_fan(inv, None)
    assert fan[0]["synset_id"] == "100"  # tagcount 9 > 0


def test_rank_fan_intended_not_in_list_does_not_raise():
    inv = si.noun_inventory(_db(), "glance", "glance")
    # "999" not present — just returns in tagcount order
    fan = si.rank_fan(inv, intended_synset_id="999")
    assert [s["synset_id"] for s in fan] == ["100", "102"]


# ---------------------------------------------------------------------------
# build_sense_inventories
# ---------------------------------------------------------------------------

def test_build_inventories_idempotent(tmp_path):
    import build_sense_inventories as bsi
    chains = tmp_path / "chains.jsonl"
    chains.write_text(json.dumps({
        "schema_version": "chain.v1", "chain_signature": "0" * 64,
        "topic": "grief", "vehicle": "scar",
        "chain": [{"phrase": "glance", "head": "glance", "synset_id": "100"}],
    }) + "\n")
    out = tmp_path / "inv.jsonl"
    db = tmp_path / "d.db"
    _dump_fixture_to(db)
    r1 = bsi.build(str(db), [str(chains)], str(out))
    text1 = out.read_text()
    r2 = bsi.build(str(db), [str(chains)], str(out))
    assert out.read_text() == text1 and r1 == r2
