"""Tests for build_synset_centroids — pipeline step that averages
property embeddings into per-synset centroids.

Critical regression target: this step was silently dropped from the
production pipeline in commit 3948dedf and the Go API quietly relied on
out-of-band manual runs to keep `synset_centroids` populated. The test
suite below pins the contract so a future refactor can't repeat that
silent drop.
"""
from __future__ import annotations

import sqlite3
import struct
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from build_synset_centroids import (
    build_synset_centroids,
    ensure_table,
)
from utils import EMBEDDING_DIM


def _pack(vec: list[float]) -> bytes:
    return struct.pack(f"{EMBEDDING_DIM}f", *vec)


def _build_fixture(properties_per_synset: dict[str, list[list[float]]]) -> sqlite3.Connection:
    """Build a minimal DB with the schema slice the centroid builder reads.

    `properties_per_synset` maps synset_id → list of property embedding
    vectors (each of dimension EMBEDDING_DIM, but tests can pass smaller
    vectors padded to fit by `_pack`).
    """
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE property_vocabulary (
            property_id INTEGER PRIMARY KEY,
            text        TEXT NOT NULL,
            embedding   BLOB
        );
        CREATE TABLE synset_properties (
            synset_id   TEXT NOT NULL,
            property_id INTEGER NOT NULL,
            salience    REAL NOT NULL DEFAULT 1.0,
            property_type TEXT,
            relation    TEXT,
            PRIMARY KEY (synset_id, property_id)
        );
    """)
    pid = 0
    for sid, vecs in properties_per_synset.items():
        for v in vecs:
            pid += 1
            # Pad / truncate to EMBEDDING_DIM for consistent struct sizing
            padded = list(v) + [0.0] * (EMBEDDING_DIM - len(v))
            padded = padded[:EMBEDDING_DIM]
            conn.execute(
                "INSERT INTO property_vocabulary (property_id, text, embedding) VALUES (?, ?, ?)",
                (pid, f"p{pid}", _pack(padded)),
            )
            conn.execute(
                "INSERT INTO synset_properties (synset_id, property_id) VALUES (?, ?)",
                (sid, pid),
            )
    conn.commit()
    return conn


def _unpack(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


def test_ensure_table_creates_synset_centroids_when_absent():
    """ensure_table is the idempotent CREATE — must produce the table
    on a fresh DB without ever DROPping. The original (deleted) script
    used DROP-then-CREATE which would lose centroids on mid-rebuild
    interrupt; we deliberately don't.
    """
    conn = sqlite3.connect(":memory:")
    ensure_table(conn)
    n = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='synset_centroids'"
    ).fetchone()[0]
    assert n == 1


def test_ensure_table_preserves_existing_rows():
    """A re-call to ensure_table on a populated table must NOT wipe data."""
    conn = sqlite3.connect(":memory:")
    ensure_table(conn)
    conn.execute(
        "INSERT INTO synset_centroids (synset_id, centroid, property_count) VALUES (?, ?, ?)",
        ("S1", _pack([1.0] + [0.0] * (EMBEDDING_DIM - 1)), 1),
    )
    conn.commit()
    ensure_table(conn)  # should be no-op
    n = conn.execute("SELECT COUNT(*) FROM synset_centroids").fetchone()[0]
    assert n == 1


def test_centroid_is_arithmetic_mean_of_property_embeddings():
    """Centroid for a synset with two property embeddings equals the
    elementwise arithmetic mean."""
    conn = _build_fixture({
        "S1": [
            [1.0, 0.0, 0.0],
            [3.0, 4.0, 0.0],
        ],
    })
    count = build_synset_centroids(conn)
    assert count == 1
    blob = conn.execute(
        "SELECT centroid FROM synset_centroids WHERE synset_id = 'S1'"
    ).fetchone()[0]
    vec = _unpack(blob)
    assert vec[0] == pytest.approx(2.0)   # mean of 1.0 and 3.0
    assert vec[1] == pytest.approx(2.0)   # mean of 0.0 and 4.0
    assert vec[2] == pytest.approx(0.0)   # mean of 0.0 and 0.0


def test_property_count_recorded_per_synset():
    conn = _build_fixture({
        "S1": [[1.0]],
        "S2": [[1.0], [2.0], [3.0]],
    })
    build_synset_centroids(conn)
    rows = dict(conn.execute(
        "SELECT synset_id, property_count FROM synset_centroids"
    ).fetchall())
    assert rows == {"S1": 1, "S2": 3}


def test_insert_or_replace_overwrites_stale_centroids():
    """Re-running build_synset_centroids on a DB whose properties have
    changed must update the stored centroid in place. Idempotency
    contract — without it, a mid-pipeline interrupt followed by a
    re-run would leave stale centroids while reporting success.
    """
    # First build with one property
    conn = _build_fixture({"S1": [[1.0, 0.0, 0.0]]})
    build_synset_centroids(conn)
    first = _unpack(
        conn.execute("SELECT centroid FROM synset_centroids WHERE synset_id='S1'").fetchone()[0]
    )
    assert first[0] == pytest.approx(1.0)

    # Insert a second property; rebuild. Centroid should update.
    conn.execute(
        "INSERT INTO property_vocabulary (property_id, text, embedding) VALUES (?, ?, ?)",
        (99, "p99", _pack([5.0] + [0.0] * (EMBEDDING_DIM - 1))),
    )
    conn.execute(
        "INSERT INTO synset_properties (synset_id, property_id) VALUES ('S1', 99)"
    )
    conn.commit()
    build_synset_centroids(conn)
    second = _unpack(
        conn.execute("SELECT centroid FROM synset_centroids WHERE synset_id='S1'").fetchone()[0]
    )
    assert second[0] == pytest.approx(3.0)   # mean of 1.0 and 5.0


def test_synsets_with_no_embedded_properties_are_skipped():
    """If every property of a synset has NULL embedding (entirely OOV
    property set), no centroid is computed — the synset is silently
    skipped rather than producing a zero-vector centroid that would
    later fail the cascade's cosine-undefined-on-zero-norm guard."""
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE property_vocabulary (
            property_id INTEGER PRIMARY KEY,
            text        TEXT NOT NULL,
            embedding   BLOB
        );
        CREATE TABLE synset_properties (
            synset_id   TEXT NOT NULL,
            property_id INTEGER NOT NULL,
            PRIMARY KEY (synset_id, property_id)
        );
        INSERT INTO property_vocabulary (property_id, text, embedding) VALUES (1, 'p1', NULL);
        INSERT INTO synset_properties (synset_id, property_id) VALUES ('S1', 1);
    """)
    conn.commit()
    count = build_synset_centroids(conn)
    assert count == 0
    n = conn.execute("SELECT COUNT(*) FROM synset_centroids").fetchone()[0]
    assert n == 0


def test_returns_zero_when_no_enriched_synsets():
    """Empty DB → zero centroids — and no crash on the empty-mean
    edge case."""
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE property_vocabulary (
            property_id INTEGER PRIMARY KEY,
            text        TEXT NOT NULL,
            embedding   BLOB
        );
        CREATE TABLE synset_properties (
            synset_id   TEXT NOT NULL,
            property_id INTEGER NOT NULL,
            PRIMARY KEY (synset_id, property_id)
        );
    """)
    count = build_synset_centroids(conn)
    assert count == 0


def test_summary_logs_all_malformed_synsets(caplog):
    """A synset whose every property embedding is malformed gets logged at WARNING."""
    import logging, sqlite3
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE property_vocabulary (
            property_id INTEGER PRIMARY KEY, text TEXT NOT NULL, embedding BLOB
        );
        CREATE TABLE synset_properties (
            synset_id TEXT NOT NULL, property_id INTEGER NOT NULL,
            PRIMARY KEY (synset_id, property_id)
        );
    """)
    # malformed embedding (multiple of float32 byte size but wrong shape)
    conn.execute("INSERT INTO property_vocabulary (property_id, text, embedding) VALUES (1, 'p1', ?)", (b"\x00\x00\x00\x00",))
    conn.execute("INSERT INTO synset_properties (synset_id, property_id) VALUES ('S_BAD', 1)")
    conn.commit()
    with caplog.at_level(logging.WARNING, logger="build_synset_centroids"):
        count = build_synset_centroids(conn)
    assert count == 0
    assert any("no usable embeddings" in r.message for r in caplog.records)


def test_run_pipeline_includes_centroid_step():
    """Regression target: the centroid step lives inside the canonical
    run_pipeline orchestrator. Without this test, a future refactor
    could silently drop the step again (as commit 3948dedf did the
    first time).
    """
    import enrich_pipeline
    import inspect
    src = inspect.getsource(enrich_pipeline.run_pipeline)
    assert "build_synset_centroids" in src, (
        "enrich_pipeline.run_pipeline must invoke build_synset_centroids — "
        "the centroid step was previously dropped in commit 3948dedf and "
        "is the Go API's required substrate. Don't lose it again."
    )
