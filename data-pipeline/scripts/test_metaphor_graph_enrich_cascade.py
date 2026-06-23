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
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from metaphor_graph import apply_schema
from metaphor_graph_enrich_cascade import ingest_cascade, make_go_suggest_fn


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
        CREATE TABLE property_vocab_curated (vocab_id INTEGER PRIMARY KEY, synset_id TEXT NOT NULL UNIQUE REFERENCES synsets(synset_id), lemma TEXT NOT NULL, pos TEXT, polysemy INTEGER);
        INSERT INTO synsets VALUES
          ('s_anger', 'n', 'a'), ('s_fire', 'n', 'f'),
          ('s_heat', 'n', 'h'), ('s_destruction', 'n', 'd'),
          ('s_palimpsest', 'n', 'p');
        INSERT INTO lemmas VALUES
          ('anger', 's_anger'), ('fire', 's_fire'),
          ('heat', 's_heat'), ('destruction', 's_destruction'),
          ('palimpsest', 's_palimpsest');
        INSERT INTO property_vocab_curated VALUES
          (1, 's_anger', 'rage', 'n', 1), (2, 's_fire', 'fire', 'n', 1),
          (3, 's_heat', 'heat', 'n', 1), (4, 's_destruction', 'destruction', 'n', 1);
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
        "suggestions": [
            {"word":"fire", "shared_properties": [
                {"property": "heat"},
                {"property": "destruction"},
            ]},
        ],
    })
    report = ingest_cascade(conn, snapped_path, suggest_fn=fetcher, limit=10)

    assert report["bridges_inserted"] == 2
    assert report["proposer"] == "cascade_v1"
    # Go receives the curated lemma of the pre-flight synset, not the raw word.
    fetcher.assert_called_once_with(topic="rage", limit=10)
    rows = conn.execute("SELECT vehicle_synset_id FROM metaphor_bridges ORDER BY bridge_id").fetchall()
    assert [r[0] for r in rows] == ["s_fire", "s_fire"]


def test_ingest_cascade_handles_empty_response(conn, snapped_path):
    fetcher = MagicMock(return_value={"suggestions": []})
    report = ingest_cascade(conn, snapped_path, suggest_fn=fetcher, limit=10)
    assert report["bridges_inserted"] == 0
    assert report["topics_processed"] == 1
    assert report["topics_empty_response"] == 1


def test_ingest_cascade_idempotent(conn, snapped_path):
    fetcher = MagicMock(return_value={
        "suggestions": [{"word":"fire", "shared_properties": [{"property": "heat"}]}],
    })
    ingest_cascade(conn, snapped_path, suggest_fn=fetcher, limit=10)
    r2 = ingest_cascade(conn, snapped_path, suggest_fn=fetcher, limit=10)
    assert r2["bridges_inserted"] == 0
    assert r2["bridges_skipped_existing"] == 1


def test_make_go_suggest_fn_runs_cascade_scorer():
    """The Go binary must be started with --cascade (M03 scorer), not the legacy default."""
    captured: dict = {}

    class _FakeProc:
        def terminate(self):
            pass

    def _fake_popen(argv, *args, **kwargs):
        captured["argv"] = argv
        return _FakeProc()

    class _FakeResp:
        status_code = 200

    with patch("subprocess.Popen", side_effect=_fake_popen), \
         patch("requests.get", return_value=_FakeResp()):
        make_go_suggest_fn("/tmp/metaforge", "/tmp/db", port=9999)

    assert "--cascade" in captured["argv"]


def test_ingest_cascade_passes_curated_lemma_when_present(conn, snapped_path):
    """topic_synset_id with a curated lemma → Go receives the lemma, not the raw word."""
    seen: list[str] = []

    def _fetch(*, topic, limit):
        seen.append(topic)
        return {"suggestions": []}

    ingest_cascade(conn, snapped_path, suggest_fn=_fetch, limit=10)
    # s_anger's curated lemma is "rage"; raw word is "anger".
    assert seen == ["rage"]


def test_ingest_cascade_falls_back_to_raw_word_without_curated_lemma(conn, tmp_path):
    """topic_synset_id absent from property_vocab_curated → Go receives the raw word."""
    p = tmp_path / "snapped.json"
    p.write_text(json.dumps({
        "snapped": [{"word": "palimpsest", "gloss": "g", "source": "s",
                     "topic_synset_id": "s_palimpsest"}],
        "dropped": [],
    }))
    seen: list[str] = []

    def _fetch(*, topic, limit):
        seen.append(topic)
        return {"suggestions": []}

    ingest_cascade(conn, str(p), suggest_fn=_fetch, limit=10)
    assert seen == ["palimpsest"]


def test_ingest_cascade_resolves_exotic_vehicle(conn, snapped_path):
    """Vehicle in synsets+lemmas but not curated still produces a bridge."""
    fetcher = MagicMock(return_value={
        "suggestions": [{"word":"palimpsest", "shared_properties": [{"property": "heat"}]}],
    })
    report = ingest_cascade(conn, snapped_path, suggest_fn=fetcher, limit=10)
    assert report["bridges_inserted"] == 1
    rows = conn.execute("SELECT vehicle_synset_id FROM metaphor_bridges").fetchall()
    assert [r[0] for r in rows] == ["s_palimpsest"]


def test_ingest_cascade_isolates_per_topic_errors(conn, tmp_path):
    """A suggest_fn raising for one topic must not abort the loop."""
    p = tmp_path / "snapped.json"
    p.write_text(json.dumps({
        "snapped": [
            {"word": "anger", "gloss": "g", "source": "s", "topic_synset_id": "s_anger"},
            {"word": "fire", "gloss": "g", "source": "s", "topic_synset_id": "s_fire"},
        ],
        "dropped": [],
    }))

    def _fetch(*, topic, limit):
        if topic == "rage":  # s_anger's curated lemma
            raise RuntimeError("boom")
        return {"suggestions": [{"word":"palimpsest",
                                "shared_properties": [{"property": "heat"}]}]}

    report = ingest_cascade(conn, str(p), suggest_fn=_fetch, limit=10)
    assert report["topics_errored"] == 1
    assert report["bridges_inserted"] == 1  # the fire topic still processed
    rows = conn.execute("SELECT vehicle_synset_id FROM metaphor_bridges").fetchall()
    assert [r[0] for r in rows] == ["s_palimpsest"]
