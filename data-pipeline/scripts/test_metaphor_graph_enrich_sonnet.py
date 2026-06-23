# data-pipeline/scripts/test_metaphor_graph_enrich_sonnet.py
"""Tests for metaphor_graph_enrich_sonnet: edit + ingest."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from metaphor_graph import apply_schema
from metaphor_graph_enrich_sonnet import run_sonnet_edits, ingest_sonnet


@pytest.fixture
def conn():
    # metaphor_graph writers reject autocommit connections by design, so the
    # connection must NOT be in autocommit mode — the plan's fixture flags are
    # a defect (same fix applied to the sibling Haiku test fixture).
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys = ON")
    c.executescript("""
        CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, pos TEXT NOT NULL, gloss TEXT);
        CREATE TABLE lemmas (lemma TEXT NOT NULL, synset_id TEXT NOT NULL REFERENCES synsets(synset_id));
        CREATE TABLE property_vocab_curated (vocab_id INTEGER PRIMARY KEY, synset_id TEXT NOT NULL UNIQUE REFERENCES synsets(synset_id), lemma TEXT NOT NULL, pos TEXT, polysemy INTEGER);
        INSERT INTO synsets VALUES
          ('s_anger', 'n', 'a'), ('s_fire', 'n', 'f'),
          ('s_heat', 'n', 'h'), ('s_intensity', 'n', 'i'),
          ('s_volcano', 'n', 'v'), ('s_palimpsest', 'n', 'p');
        INSERT INTO lemmas VALUES
          ('anger', 's_anger'), ('fire', 's_fire'),
          ('heat', 's_heat'), ('intensity', 's_intensity'),
          ('volcano', 's_volcano'), ('palimpsest', 's_palimpsest');
        INSERT INTO property_vocab_curated VALUES
          (1, 's_anger', 'anger', 'n', 1), (2, 's_fire', 'fire', 'n', 1),
          (3, 's_heat', 'heat', 'n', 1), (4, 's_intensity', 'intensity', 'n', 1),
          (5, 's_volcano', 'volcano', 'n', 1);
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
def haiku_apt_jsonl(tmp_path):
    p = tmp_path / "haiku_apt.jsonl"
    p.write_text(json.dumps({
        "topic": "anger",
        "metaphors": [{"vehicle": "fire", "shared_features": [{"dimension": "x", "concept": "heat"}]}],
        "_gloss": "a strong feeling",
    }) + "\n")
    return str(p)


def test_run_sonnet_edits_writes_audit_jsonl(snapped_path, haiku_apt_jsonl, tmp_path):
    audit = tmp_path / "sonnet_audit.jsonl"
    client = MagicMock()
    client.prompt_json.return_value = {
        "topic": "anger", "vehicles": [
            {"vehicle": "volcano", "path_concepts": ["heat", "intensity"]}
        ]
    }
    report = run_sonnet_edits(client, snapped_path, haiku_apt_jsonl, str(audit))

    assert report["calls_made"] == 1
    line = json.loads(audit.read_text().strip())
    assert line["topic"] == "anger"
    assert line["vehicles"][0]["vehicle"] == "volcano"


def test_ingest_sonnet_inserts_from_audit(conn, snapped_path, tmp_path):
    audit = tmp_path / "sonnet_audit.jsonl"
    audit.write_text(json.dumps({
        "topic": "anger",
        "vehicles": [
            {"vehicle": "volcano", "path_concepts": ["heat", "intensity"]}
        ],
    }) + "\n")
    report = ingest_sonnet(conn, snapped_path, str(audit))

    assert report["bridges_inserted"] == 2
    assert report["proposer"] == "haiku_sonnet_v1"
    rows = conn.execute("SELECT vehicle_synset_id, proposer FROM metaphor_bridges").fetchall()
    assert all(r[0] == "s_volcano" and r[1] == "haiku_sonnet_v1" for r in rows)


def test_ingest_sonnet_resolves_exotic_vehicle_via_lemmas(conn, snapped_path, tmp_path):
    # 'palimpsest' is in synsets + lemmas but NOT property_vocab_curated, so
    # the old snap_concept_string endpoint resolver dropped it. The endpoint
    # must now route through lookup_primary_synset, which resolves via lemmas.
    audit = tmp_path / "sonnet_audit.jsonl"
    audit.write_text(json.dumps({
        "topic": "anger",
        "vehicles": [{"vehicle": "palimpsest", "path_concepts": ["heat"]}],
    }) + "\n")
    report = ingest_sonnet(conn, snapped_path, str(audit))

    assert report["bridges_inserted"] == 1
    assert report["bridges_skipped_snap_failure"] == 0
    rows = conn.execute("SELECT vehicle_synset_id FROM metaphor_bridges").fetchall()
    assert rows[0][0] == "s_palimpsest"


def test_run_sonnet_edits_skips_already_audited_topics(snapped_path, haiku_apt_jsonl, tmp_path):
    # Reuse-skip: a second run against the same audit log must not re-spend
    # Sonnet on topics already present (mirrors synthesise_paths' log-skip).
    audit = tmp_path / "sonnet_audit.jsonl"
    client = MagicMock()
    client.prompt_json.return_value = {
        "topic": "anger",
        "vehicles": [{"vehicle": "volcano", "path_concepts": ["heat"]}],
    }

    r1 = run_sonnet_edits(client, snapped_path, haiku_apt_jsonl, str(audit))
    calls_after_first = client.prompt_json.call_count
    assert r1["calls_made"] == 1
    assert calls_after_first == 1

    r2 = run_sonnet_edits(client, snapped_path, haiku_apt_jsonl, str(audit))
    assert r2["calls_made"] == 0
    assert client.prompt_json.call_count == calls_after_first


def test_ingest_sonnet_idempotent(conn, snapped_path, tmp_path):
    audit = tmp_path / "sonnet_audit.jsonl"
    audit.write_text(json.dumps({
        "topic": "anger",
        "vehicles": [{"vehicle": "volcano", "path_concepts": ["heat"]}],
    }) + "\n")
    ingest_sonnet(conn, snapped_path, str(audit))
    r2 = ingest_sonnet(conn, snapped_path, str(audit))
    assert r2["bridges_inserted"] == 0
    assert r2["bridges_skipped_existing"] == 1
