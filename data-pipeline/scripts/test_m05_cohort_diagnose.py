"""Tests for m05_cohort_diagnose.py — pre-flight DB bucketing for the
γ-sweep cohort. Uses an in-memory SQLite with a minimal schema mirror.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from m05_cohort_diagnose import (
    attribute_pair,
    diagnose_cohort,
    diagnose_topic,
    diagnose_vehicle,
    load_cohort,
)


def _setup_db() -> sqlite3.Connection:
    """Minimal schema mirror of the real DB — only what the diagnose
    script reads. Keeps tests self-contained and fast."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE lemmas (
            lemma TEXT NOT NULL,
            synset_id TEXT NOT NULL,
            PRIMARY KEY (lemma, synset_id)
        );
        CREATE TABLE synset_concreteness (
            synset_id TEXT PRIMARY KEY,
            score REAL NOT NULL,
            source TEXT NOT NULL
        );
        CREATE TABLE synset_properties_curated (
            synset_id   TEXT NOT NULL,
            vocab_id    INTEGER NOT NULL,
            cluster_id  INTEGER NOT NULL,
            snap_method TEXT NOT NULL,
            snap_score  REAL,
            salience_sum REAL NOT NULL DEFAULT 1.0,
            PRIMARY KEY (synset_id, cluster_id)
        );
        CREATE TABLE synset_centroids (
            synset_id      TEXT PRIMARY KEY,
            centroid       BLOB NOT NULL,
            property_count INTEGER NOT NULL
        );
        """
    )
    return conn


def test_topic_no_lemma_bucket():
    conn = _setup_db()
    diag = diagnose_topic(conn, "nonexistent_word")
    assert diag.bucket == "topic_no_lemma"
    assert not diag.has_lemma
    assert diag.synset_ids == []


def test_topic_no_curated_no_centroid_bucket():
    """Topic resolves but neither candidate-gen path is open."""
    conn = _setup_db()
    conn.executescript(
        """
        INSERT INTO lemmas VALUES ('orphan', 's-1');
        INSERT INTO synset_concreteness VALUES ('s-1', 3.0, 'test');
        """
    )
    diag = diagnose_topic(conn, "orphan")
    assert diag.bucket == "topic_no_curated_no_centroid"
    assert diag.has_lemma
    assert diag.synset_ids == ["s-1"]
    assert diag.n_synsets_with_curated_properties == 0
    assert diag.n_synsets_with_centroid == 0


def test_topic_clean_via_curated_only():
    """One candidate path open is enough — curated alone."""
    conn = _setup_db()
    conn.executescript(
        """
        INSERT INTO lemmas VALUES ('w', 's-1');
        INSERT INTO synset_properties_curated VALUES ('s-1', 1, 1, 'exact', 1.0, 1.0);
        """
    )
    diag = diagnose_topic(conn, "w")
    assert diag.bucket == "clean"


def test_topic_clean_via_centroid_only():
    """One candidate path open is enough — centroid alone."""
    conn = _setup_db()
    conn.executescript(
        """
        INSERT INTO lemmas VALUES ('w', 's-1');
        INSERT INTO synset_centroids VALUES ('s-1', x'00', 5);
        """
    )
    diag = diagnose_topic(conn, "w")
    assert diag.bucket == "clean"


def test_vehicle_no_lemma_bucket():
    conn = _setup_db()
    diag = diagnose_vehicle(conn, "nonexistent_word")
    assert diag.bucket == "vehicle_no_lemma"


def test_vehicle_no_concreteness_bucket():
    """Vehicle resolves but no concreteness anywhere — gate would reject."""
    conn = _setup_db()
    conn.executescript(
        """
        INSERT INTO lemmas VALUES ('w', 's-1');
        INSERT INTO synset_properties_curated VALUES ('s-1', 1, 1, 'exact', 1.0, 1.0);
        """
    )
    diag = diagnose_vehicle(conn, "w")
    assert diag.bucket == "vehicle_no_concreteness"


def test_vehicle_no_curated_no_centroid_bucket():
    """Has concreteness but neither candidate-gen path is reachable."""
    conn = _setup_db()
    conn.executescript(
        """
        INSERT INTO lemmas VALUES ('w', 's-1');
        INSERT INTO synset_concreteness VALUES ('s-1', 3.0, 'test');
        """
    )
    diag = diagnose_vehicle(conn, "w")
    assert diag.bucket == "vehicle_no_curated_no_centroid"


def test_vehicle_clean_via_curated_only():
    conn = _setup_db()
    conn.executescript(
        """
        INSERT INTO lemmas VALUES ('w', 's-1');
        INSERT INTO synset_concreteness VALUES ('s-1', 3.0, 'test');
        INSERT INTO synset_properties_curated VALUES ('s-1', 1, 1, 'exact', 1.0, 1.0);
        """
    )
    diag = diagnose_vehicle(conn, "w")
    assert diag.bucket == "clean"


def test_vehicle_clean_via_centroid_only():
    conn = _setup_db()
    conn.executescript(
        """
        INSERT INTO lemmas VALUES ('w', 's-1');
        INSERT INTO synset_concreteness VALUES ('s-1', 3.0, 'test');
        INSERT INTO synset_centroids VALUES ('s-1', x'00', 5);
        """
    )
    diag = diagnose_vehicle(conn, "w")
    assert diag.bucket == "clean"


def test_vehicle_clean_takes_max_across_synsets():
    """One vehicle synset can carry the resolution path even if siblings fail.
    Regression guard for the COUNT(DISTINCT synset_id) > 0 semantics."""
    conn = _setup_db()
    conn.executescript(
        """
        INSERT INTO lemmas VALUES ('w', 's-1');
        INSERT INTO lemmas VALUES ('w', 's-2');
        -- only s-2 has concreteness + curated; s-1 has nothing
        INSERT INTO synset_concreteness VALUES ('s-2', 3.0, 'test');
        INSERT INTO synset_properties_curated VALUES ('s-2', 1, 1, 'exact', 1.0, 1.0);
        """
    )
    diag = diagnose_vehicle(conn, "w")
    assert diag.bucket == "clean"
    assert diag.n_synsets_with_concreteness == 1
    assert diag.n_synsets_with_curated_properties == 1


def test_attribute_pair_topic_block_wins():
    """Priority: topic-side block hides vehicle-side resolution."""
    from m05_cohort_diagnose import WordDiagnostic

    bad_topic = WordDiagnostic("t", False, [], 0, 0, 0, "topic_no_lemma")
    good_vehicle = WordDiagnostic("v", True, ["s-1"], 1, 1, 0, "clean")
    assert attribute_pair(bad_topic, good_vehicle) == "pre_topic_no_lemma"


def test_attribute_pair_vehicle_block_when_topic_clean():
    from m05_cohort_diagnose import WordDiagnostic

    good_topic = WordDiagnostic("t", True, ["s-1"], 1, 1, 0, "clean")
    bad_vehicle = WordDiagnostic("v", True, ["s-2"], 0, 1, 0, "vehicle_no_concreteness")
    assert attribute_pair(good_topic, bad_vehicle) == "pre_vehicle_no_concreteness"


def test_attribute_pair_both_clean():
    from m05_cohort_diagnose import WordDiagnostic

    t = WordDiagnostic("t", True, ["s-1"], 1, 1, 0, "clean")
    v = WordDiagnostic("v", True, ["s-2"], 1, 1, 0, "clean")
    assert attribute_pair(t, v) == "preflight_clean"


def test_load_cohort_jsonl(tmp_path: Path):
    p = tmp_path / "cohort.jsonl"
    p.write_text(
        '{"topic": "anger", "vehicle": "fire", "lakoff_class": "ANGER IS FIRE"}\n'
        '{"topic": "idea", "vehicle": "light"}\n'
        "\n"  # blank line tolerance
    )
    rows = load_cohort(p)
    assert rows == [("anger", "fire"), ("idea", "light")]


def test_load_cohort_rejects_missing_fields(tmp_path: Path):
    p = tmp_path / "bad.jsonl"
    p.write_text('{"topic": "anger"}\n')
    with pytest.raises(ValueError, match="missing topic/vehicle"):
        load_cohort(p)


def test_diagnose_cohort_aggregates_histogram():
    """End-to-end: build a small DB, run a small cohort, check the
    attribution_histogram tallies and pair_diagnostics are coherent."""
    conn = _setup_db()
    conn.executescript(
        """
        -- Topic: anger — clean (has curated)
        INSERT INTO lemmas VALUES ('anger', 's-anger');
        INSERT INTO synset_properties_curated VALUES ('s-anger', 1, 1, 'exact', 1.0, 1.0);

        -- Vehicle: fire — clean (concreteness + curated)
        INSERT INTO lemmas VALUES ('fire', 's-fire');
        INSERT INTO synset_concreteness VALUES ('s-fire', 4.5, 'test');
        INSERT INTO synset_properties_curated VALUES ('s-fire', 2, 2, 'exact', 1.0, 1.0);

        -- Vehicle: ghost — no concreteness
        INSERT INTO lemmas VALUES ('ghost', 's-ghost');
        INSERT INTO synset_properties_curated VALUES ('s-ghost', 3, 3, 'exact', 1.0, 1.0);

        -- Vehicle: nonsense — no lemma at all (don't insert anything)
        """
    )
    pairs = [
        ("anger", "fire"),     # preflight_clean
        ("anger", "ghost"),    # pre_vehicle_no_concreteness
        ("anger", "nonsense"), # pre_vehicle_no_lemma
        ("xxxnone", "fire"),   # pre_topic_no_lemma
    ]
    report = diagnose_cohort(conn, "test", pairs)
    assert report.n_pairs == 4
    assert report.attribution_histogram["preflight_clean"] == 1
    assert report.attribution_histogram["pre_vehicle_no_concreteness"] == 1
    assert report.attribution_histogram["pre_vehicle_no_lemma"] == 1
    assert report.attribution_histogram["pre_topic_no_lemma"] == 1
    # Per-pair coherence: each entry has matching topic+vehicle+attribution
    assert {(p.topic, p.vehicle, p.attribution) for p in report.pair_diagnostics} == {
        ("anger", "fire", "preflight_clean"),
        ("anger", "ghost", "pre_vehicle_no_concreteness"),
        ("anger", "nonsense", "pre_vehicle_no_lemma"),
        ("xxxnone", "fire", "pre_topic_no_lemma"),
    }


class _SpyConn:
    """Lightweight proxy that counts execute() calls without subclassing
    sqlite3.Connection (whose attributes are read-only on Python 3.12+)."""

    def __init__(self, wrapped: sqlite3.Connection) -> None:
        self._wrapped = wrapped
        self.execute_count = 0

    def execute(self, *args, **kwargs):
        self.execute_count += 1
        return self._wrapped.execute(*args, **kwargs)


def test_diagnose_cohort_caches_word_lookups():
    """Repeated words across pairs must not re-hit the DB. We verify by
    counting executions on a spy connection."""
    raw = _setup_db()
    raw.executescript(
        """
        INSERT INTO lemmas VALUES ('anger', 's-anger');
        INSERT INTO synset_properties_curated VALUES ('s-anger', 1, 1, 'exact', 1.0, 1.0);
        INSERT INTO lemmas VALUES ('fire', 's-fire');
        INSERT INTO synset_concreteness VALUES ('s-fire', 4.5, 'test');
        INSERT INTO synset_properties_curated VALUES ('s-fire', 2, 2, 'exact', 1.0, 1.0);
        """
    )
    spy = _SpyConn(raw)

    # 3 pairs all sharing the same topic and vehicle — without caching
    # this would issue 3x as many queries.
    pairs = [("anger", "fire")] * 3
    report = diagnose_cohort(spy, "test", pairs)
    # 4 queries per unique word (lemmas + 3 has-X counts) × 2 unique words = 8.
    # Without caching: 8 × 3 = 24.
    assert spy.execute_count == 8, f"expected 8 queries (4 per word, 2 unique), got {spy.execute_count}"
    assert report.attribution_histogram["preflight_clean"] == 3
