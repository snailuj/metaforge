# data-pipeline/scripts/test_metaphor_graph_enrich_haiku.py
"""Tests for metaphor_graph_enrich_haiku.ingest_haiku_apt."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from metaphor_graph import apply_schema
from metaphor_graph_enrich_haiku import ingest_haiku_apt


@pytest.fixture
def conn() -> sqlite3.Connection:
    # metaphor_graph writers require a transactional connection (they rely on
    # `with conn:` rollback for all-or-nothing semantics), so the connection
    # must NOT be in autocommit mode — the plan's fixture flags are a defect.
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys = ON")
    c.executescript("""
        CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, pos TEXT NOT NULL, gloss TEXT);
        CREATE TABLE lemmas (lemma TEXT NOT NULL, synset_id TEXT NOT NULL REFERENCES synsets(synset_id));
        CREATE TABLE property_vocab_curated (vocab_id INTEGER PRIMARY KEY, synset_id TEXT NOT NULL UNIQUE REFERENCES synsets(synset_id), lemma TEXT NOT NULL);
        INSERT INTO synsets VALUES
          ('s_anger', 'n', 'anger'), ('s_fire', 'n', 'fire'),
          ('s_heat', 'n', 'heat'), ('s_destruction', 'n', 'destruction'),
          ('s_passion', 'n', 'passion');
        INSERT INTO lemmas VALUES
          ('anger', 's_anger'), ('fire', 's_fire'),
          ('heat', 's_heat'), ('destruction', 's_destruction'),
          ('passion', 's_passion');
        INSERT INTO property_vocab_curated VALUES
          (1, 's_anger', 'anger'), (2, 's_fire', 'fire'),
          (3, 's_heat', 'heat'), (4, 's_destruction', 'destruction'),
          (5, 's_passion', 'passion');
    """)
    apply_schema(c)
    yield c
    c.close()


@pytest.fixture
def snapped_topics_path(tmp_path):
    p = tmp_path / "snapped.json"
    p.write_text(json.dumps({
        "snapped": [{"word": "anger", "gloss": "g", "source": "s", "topic_synset_id": "s_anger"}],
        "dropped": [],
    }))
    return str(p)


@pytest.fixture
def haiku_apt_jsonl(tmp_path):
    p = tmp_path / "haiku_apt.jsonl"
    p.write_text(json.dumps({
        "topic": "anger",
        "metaphors": [
            {"vehicle": "fire", "shared_features": [
                {"dimension": "sensorimotor", "concept": "heat"},
                {"dimension": "functional", "concept": "destruction"},
            ]},
            {"vehicle": "passion", "shared_features": [
                {"dimension": "sensorimotor", "concept": "heat"},
            ]},
        ],
        "_gloss": "a strong feeling",
    }) + "\n")
    return str(p)


def test_ingest_inserts_one_bridge_per_shared_feature(conn, snapped_topics_path, haiku_apt_jsonl):
    report = ingest_haiku_apt(conn, snapped_topics_path, haiku_apt_jsonl)

    assert report["topics_processed"] == 1
    assert report["bridges_inserted"] == 3  # 2 for fire + 1 for passion
    assert report["bridges_skipped_snap_failure"] == 0

    rows = conn.execute(
        "SELECT topic_synset_id, vehicle_synset_id, proposer FROM metaphor_bridges ORDER BY bridge_id"
    ).fetchall()
    assert all(r[0] == "s_anger" for r in rows)
    assert all(r[2] == "haiku_v1" for r in rows)
    vehicles = sorted(r[1] for r in rows)
    assert vehicles == ["s_fire", "s_fire", "s_passion"]


def test_ingest_is_idempotent(conn, snapped_topics_path, haiku_apt_jsonl):
    ingest_haiku_apt(conn, snapped_topics_path, haiku_apt_jsonl)
    second = ingest_haiku_apt(conn, snapped_topics_path, haiku_apt_jsonl)

    assert second["bridges_inserted"] == 0
    assert second["bridges_skipped_existing"] == 3
    n = conn.execute("SELECT COUNT(*) FROM metaphor_bridges").fetchone()[0]
    assert n == 3


def test_ingest_skips_snap_failures(conn, snapped_topics_path, tmp_path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text(json.dumps({
        "topic": "anger",
        "metaphors": [{"vehicle": "qwertyfake", "shared_features": [{"dimension": "x", "concept": "heat"}]}],
        "_gloss": "g",
    }) + "\n")
    report = ingest_haiku_apt(conn, snapped_topics_path, str(bad))
    assert report["bridges_skipped_snap_failure"] == 1
    assert report["bridges_inserted"] == 0
    assert report["snap_failures"][0]["vehicle"] == "qwertyfake"


def test_ingest_skips_topics_not_in_snapped_set(conn, snapped_topics_path, tmp_path):
    p = tmp_path / "haiku_apt.jsonl"
    p.write_text(
        json.dumps({"topic": "unsnapped_topic", "metaphors": [
            {"vehicle": "fire", "shared_features": [{"dimension": "x", "concept": "heat"}]}
        ], "_gloss": "g"}) + "\n"
    )
    report = ingest_haiku_apt(conn, snapped_topics_path, str(p))
    assert report["topics_processed"] == 0
    assert report["bridges_inserted"] == 0
