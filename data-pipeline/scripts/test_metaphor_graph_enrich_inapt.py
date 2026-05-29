# data-pipeline/scripts/test_metaphor_graph_enrich_inapt.py
"""Tests for metaphor_graph_enrich_inapt: synthesise + ingest."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from metaphor_graph import apply_schema
from metaphor_graph_enrich_inapt import synthesise_paths, ingest_inapt


@pytest.fixture
def conn():
    # metaphor_graph writers require a transactional connection (they rely on
    # `with conn:` rollback for all-or-nothing semantics), so use SQLite's
    # default transactional mode rather than autocommit.
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys = ON")
    c.executescript("""
        CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, pos TEXT NOT NULL, gloss TEXT);
        CREATE TABLE lemmas (lemma TEXT NOT NULL, synset_id TEXT NOT NULL REFERENCES synsets(synset_id));
        CREATE TABLE property_vocab_curated (vocab_id INTEGER PRIMARY KEY, synset_id TEXT NOT NULL UNIQUE REFERENCES synsets(synset_id), lemma TEXT NOT NULL);
        INSERT INTO synsets VALUES
          ('s_anger', 'n', 'a'), ('s_passion', 'n', 'p'), ('s_heat', 'n', 'h'),
          ('s_intensity', 'n', 'i');
        INSERT INTO lemmas VALUES
          ('anger', 's_anger'), ('passion', 's_passion'),
          ('heat', 's_heat'), ('intensity', 's_intensity');
        INSERT INTO property_vocab_curated VALUES
          (1, 's_anger', 'anger'), (2, 's_passion', 'passion'),
          (3, 's_heat', 'heat'), (4, 's_intensity', 'intensity');
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


@pytest.fixture
def inapt_jsonl(tmp_path):
    p = tmp_path / "inapt.jsonl"
    p.write_text(json.dumps({
        "topic": "anger",
        "inapt_metaphors": [
            {"vehicle": "passion", "inapt_reason_type": "single_dimension",
             "explanation": "Shares heat but passion is constructive."},
        ],
        "_gloss": "g",
    }) + "\n")
    return str(p)


def test_synthesise_writes_log_and_skips_existing(snapped_path, inapt_jsonl, tmp_path):
    log_path = tmp_path / "synth.jsonl"
    client = MagicMock()
    client.prompt_json.return_value = {"weak_concept": "heat"}

    report = synthesise_paths(client, snapped_path, inapt_jsonl, str(log_path))
    assert report["calls_made"] == 1
    assert report["entries_logged"] == 1
    line = json.loads(log_path.read_text().strip())
    assert line == {"topic": "anger", "vehicle": "passion",
                    "inapt_reason_type": "single_dimension",
                    "weak_concept": "heat",
                    "explanation": "Shares heat but passion is constructive."}

    client.prompt_json.reset_mock()
    report2 = synthesise_paths(client, snapped_path, inapt_jsonl, str(log_path))
    assert report2["calls_made"] == 0
    assert report2["entries_logged"] == 0


def test_ingest_inapt_inserts_bridges_from_log(conn, snapped_path, tmp_path):
    log_path = tmp_path / "synth.jsonl"
    log_path.write_text(json.dumps({
        "topic": "anger", "vehicle": "passion",
        "inapt_reason_type": "single_dimension",
        "weak_concept": "heat",
        "explanation": "Shares heat but passion is constructive.",
    }) + "\n")

    report = ingest_inapt(conn, snapped_path, str(log_path))
    assert report["bridges_inserted"] == 1
    assert report["proposer"] == "haiku_v1_inapt_synthesised"
    row = conn.execute(
        "SELECT proposer, rationale FROM metaphor_bridges"
    ).fetchone()
    assert row[0] == "haiku_v1_inapt_synthesised"
    assert "Shares heat" in row[1]


def test_ingest_inapt_idempotent(conn, snapped_path, tmp_path):
    log_path = tmp_path / "synth.jsonl"
    log_path.write_text(json.dumps({
        "topic": "anger", "vehicle": "passion",
        "inapt_reason_type": "single_dimension",
        "weak_concept": "heat",
        "explanation": "x",
    }) + "\n")
    ingest_inapt(conn, snapped_path, str(log_path))
    r2 = ingest_inapt(conn, snapped_path, str(log_path))
    assert r2["bridges_inserted"] == 0
    assert r2["bridges_skipped_existing"] == 1
