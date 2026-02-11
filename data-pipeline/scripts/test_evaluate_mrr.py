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
            source_word="anger",
            target_word="fire",
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
            source_word="anger",
            target_word="fire",
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
            source_word="anger",
            target_word="fire",
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


# --- 13. collect_required_synset_ids ------------------------------------------

def test_collect_required_synset_ids():
    """collect_required_synset_ids resolves metaphor pairs to synset IDs."""
    from evaluate_mrr import collect_required_synset_ids

    conn = _make_db_with_lemmas()
    pairs = [
        {"source": "anger", "target": "fire", "tier": "strong"},
        {"source": "grief", "target": "anchor", "tier": "strong"},
        {"source": "xyznotaword", "target": "fire", "tier": "medium"},
    ]

    ids = collect_required_synset_ids(conn, pairs)

    # anger has syn-anger-01, syn-anger-02; fire has syn-fire-01, syn-fire-02
    # grief has syn-grief-01; anchor has syn-anchor-01
    # xyznotaword has nothing — but fire still contributes from the 3rd pair
    assert ids == {
        "syn-anger-01", "syn-anger-02",
        "syn-fire-01", "syn-fire-02",
        "syn-grief-01", "syn-anchor-01",
    }


# --- 14. evaluate enrich mode calls run_enrichment with resolved IDs ---------

def test_evaluate_enrich_mode_passes_synset_ids(tmp_path):
    """In enrich mode, evaluate() runs enrichment with metaphor pair synset IDs."""
    from evaluate_mrr import evaluate

    # Write minimal metaphor pairs
    pairs_file = tmp_path / "pairs.json"
    pairs_file.write_text(json.dumps([
        {"source": "anger", "target": "fire", "tier": "strong"},
    ]))

    # Write minimal baseline SQL that has lemmas + synsets tables
    baseline_sql = tmp_path / "baseline.sql"
    baseline_sql.write_text(
        "CREATE TABLE lemmas (lemma TEXT, synset_id TEXT, PRIMARY KEY (lemma, synset_id));\n"
        "INSERT INTO lemmas VALUES ('anger', 'syn-anger-01');\n"
        "INSERT INTO lemmas VALUES ('fire', 'syn-fire-01');\n"
        "CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, definition TEXT);\n"
        "INSERT INTO synsets VALUES ('syn-anger-01', 'a strong emotion');\n"
        "INSERT INTO synsets VALUES ('syn-fire-01', 'combustion');\n"
    )

    # Fake enrichment JSON that run_enrichment would produce
    fake_enrichment = {
        "synsets": [
            {"id": "syn-anger-01", "lemma": "anger", "definition": "a strong emotion",
             "pos": "n", "properties": ["hot", "intense", "burning"]},
            {"id": "syn-fire-01", "lemma": "fire", "definition": "combustion",
             "pos": "n", "properties": ["hot", "bright", "burning"]},
        ],
        "config": {"model": "haiku"},
    }
    fake_enrichment_path = tmp_path / "enrichment.json"
    fake_enrichment_path.write_text(json.dumps(fake_enrichment))

    captured_ids = {}

    def mock_run_enrichment(**kwargs):
        captured_ids["synset_ids"] = kwargs.get("required_synset_ids")
        captured_ids["size"] = kwargs.get("size")
        captured_ids["model"] = kwargs.get("model")
        # Write output file
        output_path = kwargs.get("output_file")
        if output_path:
            Path(output_path).write_text(json.dumps(fake_enrichment))
        return str(fake_enrichment_path)

    mock_secondary = {"unique_properties": 3, "hapax_count": 2,
                       "hapax_rate": 0.67, "avg_properties_per_synset": 3.0}

    with patch("evaluate_mrr.BASELINE_SQL", baseline_sql), \
         patch("evaluate_mrr.EVAL_WORK_DB", tmp_path / "eval_work.db"), \
         patch("evaluate_mrr.OUTPUT_DIR", tmp_path), \
         patch("evaluate_mrr.run_enrichment", mock_run_enrichment), \
         patch("evaluate_mrr.run_pipeline"), \
         patch("evaluate_mrr.compute_secondary_metrics", return_value=mock_secondary), \
         patch("evaluate_mrr.start_server") as mock_server, \
         patch("evaluate_mrr.wait_for_health"), \
         patch("evaluate_mrr.stop_server"), \
         patch("evaluate_mrr.query_forge_rank", return_value=3):

        mock_proc = MagicMock()
        mock_server.return_value = mock_proc

        results = evaluate(
            enrichment_file=None,
            pairs_file=str(pairs_file),
            enrich_size=500,
            enrich_model="haiku",
        )

    # Verify run_enrichment was called with the resolved synset IDs
    assert captured_ids["synset_ids"] == {"syn-anger-01", "syn-fire-01"}
    assert captured_ids["size"] == 500
    assert captured_ids["model"] == "haiku"
    assert results["mrr"] > 0


# --- 15. evaluate threads prompt_template to run_enrichment -------------------

def test_evaluate_threads_prompt_template(tmp_path):
    """evaluate() passes prompt_template through to run_enrichment()."""
    from evaluate_mrr import evaluate

    pairs_file = tmp_path / "pairs.json"
    pairs_file.write_text(json.dumps([
        {"source": "anger", "target": "fire", "tier": "strong"},
    ]))

    baseline_sql = tmp_path / "baseline.sql"
    baseline_sql.write_text(
        "CREATE TABLE lemmas (lemma TEXT, synset_id TEXT, PRIMARY KEY (lemma, synset_id));\n"
        "INSERT INTO lemmas VALUES ('anger', 'syn-anger-01');\n"
        "INSERT INTO lemmas VALUES ('fire', 'syn-fire-01');\n"
        "CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, definition TEXT);\n"
        "INSERT INTO synsets VALUES ('syn-anger-01', 'a strong emotion');\n"
        "INSERT INTO synsets VALUES ('syn-fire-01', 'combustion');\n"
    )

    fake_enrichment = {
        "synsets": [
            {"id": "syn-anger-01", "lemma": "anger", "definition": "a strong emotion",
             "pos": "n", "properties": ["hot", "intense"]},
            {"id": "syn-fire-01", "lemma": "fire", "definition": "combustion",
             "pos": "n", "properties": ["hot", "bright"]},
        ],
        "config": {"model": "haiku"},
    }
    fake_enrichment_path = tmp_path / "enrichment.json"
    fake_enrichment_path.write_text(json.dumps(fake_enrichment))

    captured = {}

    def mock_run_enrichment(**kwargs):
        captured["prompt_template"] = kwargs.get("prompt_template")
        output_path = kwargs.get("output_file")
        if output_path:
            Path(output_path).write_text(json.dumps(fake_enrichment))
        return str(fake_enrichment_path)

    mock_secondary = {"unique_properties": 2, "hapax_count": 1,
                       "hapax_rate": 0.5, "avg_properties_per_synset": 2.0}

    custom_prompt = "Custom: {batch_items}\nJSON: [{{}}]"

    with patch("evaluate_mrr.BASELINE_SQL", baseline_sql), \
         patch("evaluate_mrr.EVAL_WORK_DB", tmp_path / "eval_work.db"), \
         patch("evaluate_mrr.OUTPUT_DIR", tmp_path), \
         patch("evaluate_mrr.run_enrichment", mock_run_enrichment), \
         patch("evaluate_mrr.run_pipeline"), \
         patch("evaluate_mrr.compute_secondary_metrics", return_value=mock_secondary), \
         patch("evaluate_mrr.start_server") as mock_server, \
         patch("evaluate_mrr.wait_for_health"), \
         patch("evaluate_mrr.stop_server"), \
         patch("evaluate_mrr.query_forge_rank", return_value=1):

        mock_server.return_value = MagicMock()

        evaluate(
            enrichment_file=None,
            pairs_file=str(pairs_file),
            enrich_size=500,
            enrich_model="haiku",
            prompt_template=custom_prompt,
        )

    assert captured["prompt_template"] == custom_prompt
