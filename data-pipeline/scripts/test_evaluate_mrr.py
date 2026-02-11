"""Tests for evaluate_mrr.py — MRR evaluation orchestrator.

All tests are fully mocked — no live API, no real DB, no FastText vectors.
"""
import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from evaluate_mrr import (
    load_metaphor_pairs,
    resolve_pair_synsets,
    query_forge_rank,
    compute_mrr,
    compute_secondary_metrics,
    build_server_command,
    wait_for_health,
)


# --- Helpers ------------------------------------------------------------------

SAMPLE_PAIRS = [
    {"source": "anger", "target": "fire", "tier": "strong"},
    {"source": "grief", "target": "anchor", "tier": "strong"},
    {"source": "xyznotaword", "target": "fire", "tier": "medium"},
]


def _make_db_with_lemmas():
    """Create in-memory DB with lemmas table for synset resolution."""
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE lemmas (
            lemma TEXT NOT NULL,
            synset_id TEXT NOT NULL,
            PRIMARY KEY (lemma, synset_id)
        )
    """)
    conn.executemany("INSERT INTO lemmas VALUES (?, ?)", [
        ("anger", "syn-anger-01"),
        ("anger", "syn-anger-02"),
        ("fire", "syn-fire-01"),
        ("fire", "syn-fire-02"),
        ("grief", "syn-grief-01"),
        ("anchor", "syn-anchor-01"),
    ])
    conn.commit()
    return conn


def _make_suggest_response(suggestions):
    """Build a mock /forge/suggest JSON response."""
    return {
        "source": "anger",
        "synset_id": "syn-anger-01",
        "definition": "a strong feeling",
        "properties": ["hot", "intense"],
        "threshold": 0.7,
        "suggestions": suggestions,
    }


# --- 1. load_metaphor_pairs --------------------------------------------------

def test_load_metaphor_pairs(tmp_path):
    pairs_file = tmp_path / "pairs.json"
    pairs_file.write_text(json.dumps(SAMPLE_PAIRS))

    pairs = load_metaphor_pairs(str(pairs_file))
    assert len(pairs) == 3
    assert pairs[0]["source"] == "anger"
    assert pairs[0]["target"] == "fire"
    assert pairs[0]["tier"] == "strong"


# --- 2. load_metaphor_pairs validates ----------------------------------------

def test_load_metaphor_pairs_validates(tmp_path):
    bad_file = tmp_path / "bad.json"
    bad_file.write_text(json.dumps([{"source": "anger"}]))  # missing target

    with pytest.raises(ValueError, match="target"):
        load_metaphor_pairs(str(bad_file))


# --- 3. resolve_pair_synsets --------------------------------------------------

def test_resolve_pair_synsets():
    conn = _make_db_with_lemmas()
    pairs = [
        {"source": "anger", "target": "fire", "tier": "strong"},
        {"source": "grief", "target": "anchor", "tier": "strong"},
        {"source": "xyznotaword", "target": "fire", "tier": "medium"},
    ]

    testable, skipped, all_synset_ids = resolve_pair_synsets(conn, pairs)

    assert len(testable) == 2  # anger→fire and grief→anchor
    assert len(skipped) == 1  # xyznotaword has no synset
    assert skipped[0]["reason"] == "source not found"

    # All synset IDs collected for enrichment targeting
    assert "syn-anger-01" in all_synset_ids
    assert "syn-fire-01" in all_synset_ids
    assert "syn-grief-01" in all_synset_ids
    assert "syn-anchor-01" in all_synset_ids


# --- 4. query_forge_rank found -----------------------------------------------

def test_query_forge_rank_found():
    response = _make_suggest_response([
        {"synset_id": "syn-other-01", "word": "blaze", "overlap_count": 3, "distance": 0.9, "tier": "strong"},
        {"synset_id": "syn-fire-01", "word": "fire", "overlap_count": 2, "distance": 0.8, "tier": "strong"},
        {"synset_id": "syn-fire-02", "word": "fire", "overlap_count": 1, "distance": 0.7, "tier": "obvious"},
    ])

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = response

    with patch("evaluate_mrr.requests.get", return_value=mock_resp):
        rank = query_forge_rank(
            source_synset="syn-anger-01",
            target_synsets={"syn-fire-01", "syn-fire-02"},
            port=9090,
            threshold=0.7,
            limit=200,
        )

    # syn-fire-01 is at index 1 (0-indexed), so rank = 2
    assert rank == 2


# --- 5. query_forge_rank absent -----------------------------------------------

def test_query_forge_rank_absent():
    response = _make_suggest_response([
        {"synset_id": "syn-other-01", "word": "blaze", "overlap_count": 3, "distance": 0.9, "tier": "strong"},
    ])

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = response

    with patch("evaluate_mrr.requests.get", return_value=mock_resp):
        rank = query_forge_rank(
            source_synset="syn-anger-01",
            target_synsets={"syn-fire-01"},
            port=9090,
        )

    assert rank is None


# --- 6. query_forge_rank API error --------------------------------------------

def test_query_forge_rank_api_error():
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"

    with patch("evaluate_mrr.requests.get", return_value=mock_resp):
        rank = query_forge_rank(
            source_synset="syn-anger-01",
            target_synsets={"syn-fire-01"},
            port=9090,
        )

    assert rank is None


# --- 7. compute_mrr known values ---------------------------------------------

def test_compute_mrr_known():
    # Ranks [1, 2, 5] → RR = [1, 0.5, 0.2] → MRR = 1.7/3 ≈ 0.567
    ranks = [1, 2, 5]
    mrr = compute_mrr(ranks)
    assert abs(mrr - (1.0 + 0.5 + 0.2) / 3) < 0.001


# --- 8. compute_mrr with missing ranks (None → 0) ----------------------------

def test_compute_mrr_with_missing():
    ranks = [1, None, 5]
    mrr = compute_mrr(ranks)
    # RR = [1.0, 0.0, 0.2] → MRR = 1.2/3 = 0.4
    assert abs(mrr - 0.4) < 0.001


# --- 9. compute_secondary_metrics --------------------------------------------

def test_compute_secondary_metrics():
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE property_vocabulary (
            property_id INTEGER PRIMARY KEY,
            text TEXT NOT NULL UNIQUE,
            is_oov INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE synset_properties (
            synset_id TEXT NOT NULL,
            property_id INTEGER NOT NULL,
            PRIMARY KEY (synset_id, property_id)
        )
    """)
    # 4 properties: "warm" in 1 synset, "hot" in 1 synset, "bright" in 2 synsets, "loud" in 1 synset
    conn.executemany("INSERT INTO property_vocabulary VALUES (?, ?, 0)", [
        (1, "warm"), (2, "hot"), (3, "bright"), (4, "loud"),
    ])
    conn.executemany("INSERT INTO synset_properties VALUES (?, ?)", [
        ("s1", 1), ("s1", 3),
        ("s2", 2), ("s2", 3), ("s2", 4),
    ])
    conn.commit()

    metrics = compute_secondary_metrics(conn)

    assert metrics["unique_properties"] == 4
    # Hapax: properties appearing in exactly 1 synset = warm, hot, loud = 3 out of 4
    assert metrics["hapax_count"] == 3
    assert abs(metrics["hapax_rate"] - 0.75) < 0.01
    assert metrics["avg_properties_per_synset"] == 2.5  # (2 + 3) / 2


# --- 10. build_server_command -------------------------------------------------

def test_build_server_command():
    cmd = build_server_command(
        db_path="/tmp/test.db", port=9090
    )
    assert cmd[0] == "go"
    assert "run" in cmd
    assert "./cmd/metaforge" in cmd
    assert "--db" in cmd
    assert "/tmp/test.db" in cmd
    assert "--port" in cmd
    assert "9090" in cmd


# --- 11. wait_for_health timeout ----------------------------------------------

def test_wait_for_health_timeout():
    mock_resp = MagicMock()
    mock_resp.status_code = 500

    with patch("evaluate_mrr.requests.get", return_value=mock_resp):
        with pytest.raises(TimeoutError):
            wait_for_health(port=9090, timeout=0.1, interval=0.05)


# --- 12. wait_for_health success ----------------------------------------------

def test_wait_for_health_success():
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("evaluate_mrr.requests.get", return_value=mock_resp):
        wait_for_health(port=9090, timeout=2.0, interval=0.1)
        # Should not raise
