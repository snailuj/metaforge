"""Tests for the batch driver."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from metaphor_graph import apply_schema
from metaphor_graph_enrich_run import run_batches, chunk_topics


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:", isolation_level=None, autocommit=True)
    c.execute("PRAGMA foreign_keys = ON")
    c.executescript("""
        CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, pos TEXT NOT NULL, gloss TEXT);
        CREATE TABLE lemmas (lemma TEXT NOT NULL, synset_id TEXT NOT NULL REFERENCES synsets(synset_id));
        CREATE TABLE property_vocab_curated (synset_id TEXT NOT NULL UNIQUE REFERENCES synsets(synset_id), lemma TEXT NOT NULL);
    """)
    apply_schema(c)
    yield c
    c.close()


def test_chunk_topics_partitions_evenly():
    snapped = {"snapped": [{"word": f"t{i}"} for i in range(50)]}
    chunks = chunk_topics(snapped, batch_size=20)
    assert len(chunks) == 3
    assert [len(c) for c in chunks] == [20, 20, 10]


def test_run_batches_invokes_each_proposer_per_batch(conn, tmp_path):
    snapped_path = tmp_path / "snapped.json"
    snapped_path.write_text(json.dumps({
        "snapped": [{"word": f"t{i}", "gloss": "g", "source": "s", "topic_synset_id": f"s_t{i}"}
                    for i in range(5)],
        "dropped": [],
    }))
    progress_path = tmp_path / "progress.md"

    mocks = {
        "ingest_haiku_apt": MagicMock(return_value={"proposer": "haiku_v1", "bridges_inserted": 3}),
        "ingest_inapt": MagicMock(return_value={"proposer": "haiku_v1_inapt_synthesised", "bridges_inserted": 2}),
        "ingest_cascade": MagicMock(return_value={"proposer": "cascade_v1", "bridges_inserted": 5}),
        "ingest_sonnet": MagicMock(return_value={"proposer": "haiku_sonnet_v1", "bridges_inserted": 4}),
    }
    report = run_batches(
        conn,
        str(snapped_path),
        batch_size=20,
        progress_md_path=str(progress_path),
        ingest_fns=mocks,
    )

    assert report["batches_run"] == 1
    assert report["totals"]["haiku_v1"] == 3
    assert report["totals"]["cascade_v1"] == 5
    for k, m in mocks.items():
        assert m.call_count == 1, f"{k} should be called once per batch"
    md = progress_path.read_text()
    assert "batch 1" in md.lower()
    assert "haiku_v1" in md and "cascade_v1" in md


def test_run_batches_appends_progress_on_rerun(conn, tmp_path):
    snapped_path = tmp_path / "snapped.json"
    snapped_path.write_text(json.dumps({
        "snapped": [{"word": "t1", "gloss": "g", "source": "s", "topic_synset_id": "s_t1"}],
        "dropped": [],
    }))
    progress_path = tmp_path / "progress.md"
    mocks = {k: MagicMock(return_value={"proposer": k, "bridges_inserted": 0})
             for k in ["ingest_haiku_apt", "ingest_inapt", "ingest_cascade", "ingest_sonnet"]}
    run_batches(conn, str(snapped_path), batch_size=20,
                progress_md_path=str(progress_path), ingest_fns=mocks)
    run_batches(conn, str(snapped_path), batch_size=20,
                progress_md_path=str(progress_path), ingest_fns=mocks)
    md = progress_path.read_text()
    assert md.count("batch 1") == 2
