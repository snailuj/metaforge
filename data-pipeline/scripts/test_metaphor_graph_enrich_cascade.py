# data-pipeline/scripts/test_metaphor_graph_enrich_cascade.py
"""Tests for metaphor_graph_enrich_cascade.ingest_cascade.

Subprocess and HTTP layer are dependency-injected so tests don't need to
spin up Go.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from metaphor_graph import apply_schema
from metaphor_graph_enrich_cascade import ingest_cascade


@pytest.fixture
def conn():
    # metaphor_graph writers require a transactional connection (autocommit=False)
    # with FK enforcement on — the plan's autocommit fixture trips the
    # _require_transactional guard, so we open a transactional connection here.
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys = ON")
    c.executescript("""
        CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, pos TEXT NOT NULL, gloss TEXT);
        CREATE TABLE lemmas (lemma TEXT NOT NULL, synset_id TEXT NOT NULL REFERENCES synsets(synset_id));
        CREATE TABLE property_vocab_curated (vocab_id INTEGER PRIMARY KEY, synset_id TEXT NOT NULL UNIQUE REFERENCES synsets(synset_id), lemma TEXT NOT NULL);
        INSERT INTO synsets VALUES
          ('s_anger', 'n', 'a'), ('s_fire', 'n', 'f'),
          ('s_heat', 'n', 'h'), ('s_destruction', 'n', 'd');
        INSERT INTO lemmas VALUES
          ('anger', 's_anger'), ('fire', 's_fire'),
          ('heat', 's_heat'), ('destruction', 's_destruction');
        INSERT INTO property_vocab_curated VALUES
          (1, 's_anger', 'anger'), (2, 's_fire', 'fire'),
          (3, 's_heat', 'heat'), (4, 's_destruction', 'destruction');
    """)
    apply_schema(c)
    yield c
    c.close()


@pytest.fixture
def snapped_path(tmp_path):
    p = tmp_path / "snapped.json"
    p.write_text(json.dumps({
        "snapped": [{"word": "anger", "gloss": "g", "source": "s", "topic_synset_id": "s_anger"}],
        "dropped": [],
    }))
    return str(p)


def test_ingest_cascade_inserts_one_bridge_per_shared_property(conn, snapped_path):
    fetcher = MagicMock(return_value={
        "candidates": [
            {"vehicle": "fire", "shared_properties": [
                {"property": "heat"},
                {"property": "destruction"},
            ]},
        ],
    })
    report = ingest_cascade(conn, snapped_path, suggest_fn=fetcher, limit=10)

    assert report["bridges_inserted"] == 2
    assert report["proposer"] == "cascade_v1"
    fetcher.assert_called_once_with(topic="anger", limit=10)
    rows = conn.execute("SELECT vehicle_synset_id FROM metaphor_bridges ORDER BY bridge_id").fetchall()
    assert [r[0] for r in rows] == ["s_fire", "s_fire"]


def test_ingest_cascade_handles_empty_response(conn, snapped_path):
    fetcher = MagicMock(return_value={"candidates": []})
    report = ingest_cascade(conn, snapped_path, suggest_fn=fetcher, limit=10)
    assert report["bridges_inserted"] == 0
    assert report["topics_processed"] == 1
    assert report["topics_empty_response"] == 1


def test_ingest_cascade_idempotent(conn, snapped_path):
    fetcher = MagicMock(return_value={
        "candidates": [{"vehicle": "fire", "shared_properties": [{"property": "heat"}]}],
    })
    ingest_cascade(conn, snapped_path, suggest_fn=fetcher, limit=10)
    r2 = ingest_cascade(conn, snapped_path, suggest_fn=fetcher, limit=10)
    assert r2["bridges_inserted"] == 0
    assert r2["bridges_skipped_existing"] == 1
