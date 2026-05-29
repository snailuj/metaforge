"""Tests for metaphor_graph_enrich_topics.snap_topics."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from metaphor_graph import apply_schema
from metaphor_graph_enrich_topics import snap_topics


@pytest.fixture
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:", isolation_level=None, autocommit=True)
    c.execute("PRAGMA foreign_keys = ON")
    c.executescript("""
        CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, pos TEXT NOT NULL, gloss TEXT);
        CREATE TABLE lemmas (lemma TEXT NOT NULL, synset_id TEXT NOT NULL REFERENCES synsets(synset_id));
        CREATE TABLE property_vocab_curated (vocab_id INTEGER PRIMARY KEY, synset_id TEXT NOT NULL UNIQUE REFERENCES synsets(synset_id), lemma TEXT NOT NULL);
        INSERT INTO synsets VALUES ('s_anger', 'n', 'anger gloss'), ('s_time', 'n', 'time gloss');
        INSERT INTO lemmas VALUES ('anger', 's_anger'), ('time', 's_time');
        INSERT INTO property_vocab_curated VALUES (1, 's_anger', 'anger'), (2, 's_time', 'time');
    """)
    apply_schema(c)
    yield c
    c.close()


def test_snap_topics_partitions_input(conn, tmp_path):
    topics_path = tmp_path / "topics.json"
    topics_path.write_text(json.dumps({
        "phase": "2",
        "topics": [
            {"word": "anger", "gloss": "a strong feeling", "source": "phase_1b_spine"},
            {"word": "time", "gloss": "an indefinite period", "source": "phase_1b_spine"},
            {"word": "qwertyfake", "gloss": "not real", "source": "test"},
        ],
    }))
    output_path = tmp_path / "snapped.json"

    report = snap_topics(conn, str(topics_path), str(output_path))

    assert report["input_count"] == 3
    assert report["snapped_count"] == 2
    assert report["snap_rate"] == pytest.approx(2 / 3)

    written = json.loads(output_path.read_text())
    assert {t["word"] for t in written["snapped"]} == {"anger", "time"}
    assert all("topic_synset_id" in t for t in written["snapped"])
    assert {t["word"] for t in written["dropped"]} == {"qwertyfake"}
    assert all(t["reason"] == "no_curated_synset" for t in written["dropped"])


def test_snap_topics_idempotent_rewrites_output(conn, tmp_path):
    topics_path = tmp_path / "topics.json"
    topics_path.write_text(json.dumps({"topics": [{"word": "anger", "gloss": "g", "source": "s"}]}))
    output_path = tmp_path / "snapped.json"

    snap_topics(conn, str(topics_path), str(output_path))
    snap_topics(conn, str(topics_path), str(output_path))

    written = json.loads(output_path.read_text())
    assert len(written["snapped"]) == 1
