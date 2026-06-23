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
    # Transactional connection: metaphor_graph writers reject autocommit (they
    # rely on `with conn:` rollback). The run_batches tests pass conn only to
    # mocked ingest fns, but the integration test invokes a real writer.
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys = ON")
    c.executescript("""
        CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, pos TEXT NOT NULL, gloss TEXT);
        CREATE TABLE lemmas (lemma TEXT NOT NULL, synset_id TEXT NOT NULL REFERENCES synsets(synset_id));
        CREATE TABLE property_vocab_curated (vocab_id INTEGER PRIMARY KEY, synset_id TEXT NOT NULL UNIQUE REFERENCES synsets(synset_id), lemma TEXT NOT NULL);
    """)
    apply_schema(c)
    yield c
    c.close()


def test_cli_imports_resolve():
    """main() lazily imports claude_client from the repo-root lib/ dir. The
    module must put lib/ on sys.path at import time or the CLI entrypoint dies
    with ModuleNotFoundError at runtime (regression: dry-run 2026-05-29 — the
    unit tests inject mocks and never exercise main()'s real imports).
    """
    import metaphor_graph_enrich_run  # noqa: F401 — runs module-level path inserts
    from claude_client import prompt_json  # noqa: F401
    from metaphor_graph_enrich_haiku import ingest_haiku_apt  # noqa: F401
    from metaphor_graph_enrich_inapt import synthesise_paths, ingest_inapt  # noqa: F401
    from metaphor_graph_enrich_cascade import ingest_cascade, make_go_suggest_fn  # noqa: F401
    from metaphor_graph_enrich_sonnet import run_sonnet_edits, ingest_sonnet  # noqa: F401


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


def test_run_batches_isolates_a_failing_proposer(conn, tmp_path):
    """One proposer raising must not abort the batch: the other three still run,
    the failure is recorded, and the run completes. (Dry-run regression: a cascade
    404 aborted the whole run before the sonnet ingest.)"""
    snapped_path = tmp_path / "snapped.json"
    snapped_path.write_text(json.dumps({
        "snapped": [{"word": "t1", "gloss": "g", "source": "s", "topic_synset_id": "s_t1"}],
        "dropped": [],
    }))
    progress_path = tmp_path / "progress.md"

    def boom(conn, path):
        raise RuntimeError("forge 404")

    mocks = {
        "ingest_haiku_apt": MagicMock(return_value={"proposer": "haiku_v1", "bridges_inserted": 3}),
        "ingest_inapt": MagicMock(return_value={"proposer": "haiku_v1_inapt_synthesised", "bridges_inserted": 2}),
        "ingest_cascade": boom,  # raises
        "ingest_sonnet": MagicMock(return_value={"proposer": "haiku_sonnet_v1", "bridges_inserted": 4}),
    }

    report = run_batches(conn, str(snapped_path), batch_size=20,
                         progress_md_path=str(progress_path), ingest_fns=mocks)

    # Did not propagate; the three healthy proposers still ran.
    assert report["batches_run"] == 1
    assert report["totals"]["haiku_v1"] == 3
    assert report["totals"]["haiku_sonnet_v1"] == 4  # ran despite cascade failing first
    assert report["totals"]["cascade_v1"] == 0
    mocks["ingest_sonnet"].assert_called_once()
    # Failure recorded in the progress markdown.
    md = progress_path.read_text()
    assert "cascade_v1" in md


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


def test_integration_no_judgments_means_no_metaphor_link_rows(conn, tmp_path):
    """After Stage A runs end-to-end against mocked proposers, the graph_edges
    view should expose zero metaphor_link rows because no judgments exist.

    This is the load-bearing invariant: Stage A populates the proposal pool;
    Stage B (eyeballer) is what turns proposals into graph structure.
    """
    snapped_path = tmp_path / "snapped.json"
    # graph_edges UNIONs has_property / metonym_of / antonym_of sources; those
    # tables must exist (empty is fine) or the view query errors. Stubbed here
    # rather than in the shared fixture so the run_batches tests stay minimal.
    conn.executescript("""
        CREATE TABLE synset_properties_curated (
            synset_id TEXT NOT NULL, vocab_id INTEGER NOT NULL, cluster_id INTEGER NOT NULL,
            snap_method TEXT NOT NULL, snap_score REAL, salience_sum REAL NOT NULL DEFAULT 1.0,
            PRIMARY KEY (synset_id, cluster_id));
        CREATE TABLE syntagms (
            syntagm_id INTEGER PRIMARY KEY, synset1id TEXT NOT NULL, synset2id TEXT NOT NULL,
            sensekey1 TEXT NOT NULL DEFAULT '', sensekey2 TEXT NOT NULL DEFAULT '',
            word1id INTEGER NOT NULL DEFAULT 0, word2id INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE synset_metonyms (
            synset_id TEXT NOT NULL, metonym_syntagm_id INTEGER NOT NULL, metonym_rank INTEGER NOT NULL,
            PRIMARY KEY (synset_id, metonym_syntagm_id));
        CREATE TABLE property_antonyms (
            vocab_id_a INTEGER NOT NULL, vocab_id_b INTEGER NOT NULL,
            PRIMARY KEY (vocab_id_a, vocab_id_b));
        INSERT INTO synsets VALUES
          ('s_anger', 'n', 'a'), ('s_fire', 'n', 'f'), ('s_heat', 'n', 'h');
        INSERT INTO lemmas VALUES
          ('anger', 's_anger'), ('fire', 's_fire'), ('heat', 's_heat');
        INSERT INTO property_vocab_curated VALUES
          (1, 's_anger', 'anger'), (2, 's_fire', 'fire'), (3, 's_heat', 'heat');
    """)
    from metaphor_graph import insert_bridge_with_raw_path, apply_graph_view
    apply_graph_view(conn)
    insert_bridge_with_raw_path(
        conn, topic_synset_id="s_anger", vehicle_synset_id="s_fire",
        proposer="cascade_v1", proposed_at="2026-05-29T00:00:00Z",
        raw_path=["heat"],
    )
    n_bridges = conn.execute("SELECT COUNT(*) FROM metaphor_bridges").fetchone()[0]
    n_metaphor_links = conn.execute(
        "SELECT COUNT(*) FROM graph_edges WHERE relation = 'metaphor_link'"
    ).fetchone()[0]
    assert n_bridges == 1
    assert n_metaphor_links == 0
