"""Tests for run_sweep.py — the aptness parameter sweep harness."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import run_sweep
from run_sweep import (
    SCHEMA_VERSION,
    load_mrr_reference,
    load_sweep_config,
    render_markdown_report,
    run_sweep as run_sweep_fn,
)


# --- Fixture DB (mirrors test_evaluate_aptness pattern) ----------------------

FIXTURE_SCHEMA = """
    CREATE TABLE lemmas (
        lemma TEXT NOT NULL,
        synset_id TEXT NOT NULL,
        PRIMARY KEY (lemma, synset_id)
    );
    CREATE TABLE property_vocab_curated (
        vocab_id  INTEGER PRIMARY KEY,
        synset_id TEXT NOT NULL,
        lemma     TEXT NOT NULL,
        pos       TEXT NOT NULL,
        polysemy  INTEGER NOT NULL,
        UNIQUE(synset_id)
    );
    CREATE TABLE synset_properties_curated (
        synset_id    TEXT NOT NULL,
        vocab_id     INTEGER NOT NULL,
        cluster_id   INTEGER NOT NULL,
        snap_method  TEXT NOT NULL,
        snap_score   REAL,
        salience_sum REAL NOT NULL DEFAULT 1.0,
        PRIMARY KEY (synset_id, cluster_id)
    );
"""

FIXTURE_DATA = """
    INSERT INTO lemmas VALUES
        ('anger', 'S001'), ('fire', 'S002'),
        ('approach', 'S003'), ('coming', 'S004');
    INSERT INTO property_vocab_curated VALUES
        (1, 'S001', 'anger',    'n', 1),
        (2, 'S002', 'fire',     'n', 1),
        (3, 'S003', 'approach', 'n', 1),
        (4, 'S004', 'coming',   'n', 1);
    INSERT INTO synset_properties_curated VALUES
        ('S001', 1, 1, 'exact', 1.0, 0.9),
        ('S001', 1, 2, 'exact', 1.0, 0.6),
        ('S002', 2, 1, 'exact', 1.0, 0.85),
        ('S002', 2, 3, 'exact', 1.0, 0.7),
        ('S003', 3, 4, 'exact', 1.0, 0.5),
        ('S004', 4, 5, 'exact', 1.0, 0.5);
"""


def _build_fixture_db_file(path: Path) -> None:
    """Materialise the fixture DB at ``path`` so sqlite3.connect(path) works.

    The harness opens its own connections per variation, so an in-memory
    fixture isn't reachable — write the same schema+data to a real file
    that lives only for the test's duration (tmp_path is auto-cleaned).
    """
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(FIXTURE_SCHEMA)
        conn.executescript(FIXTURE_DATA)
        conn.commit()
    finally:
        conn.close()


def _write_pairs_and_controls(tmp_path: Path) -> tuple[Path, Path]:
    pairs_file = tmp_path / "pairs.json"
    pairs_file.write_text(json.dumps([
        {"source": "anger", "target": "fire", "tier": "strong"},
    ]))
    controls_file = tmp_path / "controls.jsonl"
    controls_file.write_text(
        '{"target": "approach", "paraphrase": "coming", "label": "inapt"}\n'
    )
    return pairs_file, controls_file


def _base_config(tmp_path: Path, variations: list[dict]) -> tuple[Path, dict]:
    """Build a minimal sweep config + materialised inputs in tmp_path."""
    db_path = tmp_path / "fixture.db"
    _build_fixture_db_file(db_path)
    pairs_file, controls_file = _write_pairs_and_controls(tmp_path)
    cfg = {
        "name": "test_sweep",
        "db": str(db_path),
        "pairs": str(pairs_file),
        "controls": str(controls_file),
        "variations": variations,
    }
    return db_path, cfg


# --- Config loading ----------------------------------------------------------

def test_load_sweep_config_reads_json(tmp_path):
    cfg_file = tmp_path / "sweep.json"
    cfg_file.write_text(json.dumps({
        "name": "x",
        "db": "db.sqlite",
        "pairs": "p.json",
        "controls": "c.jsonl",
        "variations": [{"name": "v1", "scoring": "jaccard_salience"}],
    }))
    cfg = load_sweep_config(str(cfg_file))
    assert cfg["name"] == "x"
    assert len(cfg["variations"]) == 1


def test_load_sweep_config_rejects_missing_variations(tmp_path):
    cfg_file = tmp_path / "bad.json"
    cfg_file.write_text(json.dumps({"name": "x"}))
    with pytest.raises(ValueError, match="variations"):
        load_sweep_config(str(cfg_file))


def test_load_sweep_config_rejects_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_sweep_config(str(tmp_path / "nope.json"))


def test_load_sweep_config_rejects_unknown_extension(tmp_path):
    cfg_file = tmp_path / "sweep.txt"
    cfg_file.write_text("name: x")
    with pytest.raises(ValueError, match="Unsupported config extension"):
        load_sweep_config(str(cfg_file))


# --- MRR reference loading ---------------------------------------------------

def test_load_mrr_reference_returns_none_when_path_missing():
    assert load_mrr_reference(None) is None


def test_load_mrr_reference_reads_nested_baseline_shape(tmp_path):
    """Matches eval_baseline_v2.json: ``{"mrr": {"value": 0.0073, ...}}``."""
    ref_file = tmp_path / "baseline.json"
    ref_file.write_text(json.dumps({"mrr": {"value": 0.0073, "hit_count": 35}}))
    assert load_mrr_reference(str(ref_file)) == pytest.approx(0.0073)


def test_load_mrr_reference_reads_flat_shape(tmp_path):
    """Forward compat: a flattened ``{"mrr": 0.123}`` should still resolve."""
    ref_file = tmp_path / "flat.json"
    ref_file.write_text(json.dumps({"mrr": 0.123}))
    assert load_mrr_reference(str(ref_file)) == pytest.approx(0.123)


def test_load_mrr_reference_raises_on_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_mrr_reference(str(tmp_path / "nope.json"))


# --- End-to-end sweep --------------------------------------------------------

def test_two_variation_sweep_ranks_by_separation_score(tmp_path):
    """Slice S02 must-have: harness returns variations ranked by
    separation_score DESC and emits a markdown table with header + 2 rows."""
    _, cfg = _base_config(tmp_path, [
        {"name": "salience", "scoring": "jaccard_salience"},
        {"name": "raw", "scoring": "jaccard_raw"},
    ])
    cfg_path = tmp_path / "sweep.json"
    cfg_path.write_text(json.dumps(cfg))

    result = run_sweep_fn(cfg, config_path=str(cfg_path))

    # Provenance present
    assert result["schema_version"] == SCHEMA_VERSION
    assert result["git_commit"]
    assert result["timestamp"].endswith("Z")
    assert result["config_path"] == str(cfg_path)

    assert len(result["variations"]) == 2
    # Both succeeded
    assert all(v["status"] == "ok" for v in result["variations"])
    # Variations carry name from config
    names = {v["name"] for v in result["variations"]}
    assert names == {"salience", "raw"}

    # Markdown table check
    md = render_markdown_report(result)
    assert "| name |" in md  # header row
    # Two data rows for the two variations
    data_lines = [line for line in md.splitlines()
                  if line.startswith("| ") and "scoring" not in line and "---" not in line]
    assert len(data_lines) == 2

    # Ranking: separation_score DESC means the first data row has
    # the higher separation_score.
    ok_rows = [v for v in result["variations"] if v["status"] == "ok"]
    sorted_descending = sorted(
        ok_rows, key=lambda v: v["separation_score"], reverse=True,
    )
    # Find the row order in markdown — the first ok variation should
    # be the one with the largest separation_score.
    first_data_name = data_lines[0].split("|")[1].strip()
    assert first_data_name == sorted_descending[0]["name"]


def test_unknown_scoring_marks_variation_failed_without_aborting(tmp_path):
    """Failure isolation must-have: a bad variation does not crash the sweep."""
    _, cfg = _base_config(tmp_path, [
        {"name": "good", "scoring": "jaccard_salience"},
        {"name": "bad",  "scoring": "nonexistent_formula"},
        {"name": "also_good", "scoring": "jaccard_raw"},
    ])
    cfg_path = tmp_path / "sweep.json"
    cfg_path.write_text(json.dumps(cfg))

    result = run_sweep_fn(cfg, config_path=str(cfg_path))

    statuses = {v["name"]: v["status"] for v in result["variations"]}
    assert statuses == {"good": "ok", "bad": "failed", "also_good": "ok"}

    bad = next(v for v in result["variations"] if v["name"] == "bad")
    assert bad["error"]
    assert "nonexistent_formula" in bad["error"] or "Unknown scoring" in bad["error"]

    # Failed row pinned to the bottom of the markdown table
    md = render_markdown_report(result)
    data_lines = [
        line for line in md.splitlines()
        if line.startswith("| ") and "---" not in line and "name |" not in line
    ]
    assert "bad" in data_lines[-1]
    assert "failed" in data_lines[-1]


def test_mrr_reference_populates_report_column(tmp_path):
    """When mrr_reference is set, markdown report shows the value;
    when omitted the column shows n/a."""
    db_path, cfg = _base_config(tmp_path, [
        {"name": "v1", "scoring": "jaccard_salience"},
    ])
    ref_file = tmp_path / "baseline.json"
    ref_file.write_text(json.dumps({"mrr": {"value": 0.0123}}))
    cfg["mrr_reference"] = str(ref_file)

    cfg_path = tmp_path / "sweep.json"
    cfg_path.write_text(json.dumps(cfg))

    result = run_sweep_fn(cfg, config_path=str(cfg_path))
    assert result["mrr_reference_value"] == pytest.approx(0.0123)

    md = render_markdown_report(result)
    assert "0.0123" in md
    assert "n/a" not in md.split("| name |")[1].splitlines()[2]  # data row

    # Without mrr_reference the column says n/a
    cfg.pop("mrr_reference")
    result_noref = run_sweep_fn(cfg, config_path=str(cfg_path))
    md_noref = render_markdown_report(result_noref)
    assert "n/a" in md_noref


def test_sweep_validates_required_inputs(tmp_path):
    """Missing db / pairs / controls path fails fast before any work runs."""
    cfg = {
        "name": "broken",
        "db": str(tmp_path / "nope.db"),
        "pairs": str(tmp_path / "nope.json"),
        "controls": str(tmp_path / "nope.jsonl"),
        "variations": [{"name": "v1"}],
    }
    with pytest.raises(FileNotFoundError):
        run_sweep_fn(cfg, config_path="cfg.json")


def test_per_variation_isolation_uses_fresh_connection(tmp_path):
    """Each variation opens its own DB connection so a failure in one
    cannot leak transaction state into another."""
    _, cfg = _base_config(tmp_path, [
        {"name": "v1", "scoring": "jaccard_salience"},
        {"name": "v2", "scoring": "jaccard_salience"},
    ])
    opened = []
    real_connect = sqlite3.connect

    def tracking_connect(path, *args, **kwargs):
        opened.append(path)
        return real_connect(path, *args, **kwargs)

    import run_sweep as rs_mod
    orig = rs_mod.sqlite3.connect
    rs_mod.sqlite3.connect = tracking_connect  # type: ignore[assignment]
    try:
        rs_mod.run_sweep(cfg, config_path="cfg.json")
    finally:
        rs_mod.sqlite3.connect = orig  # type: ignore[assignment]

    # Two variations → two opens (one per variation, isolation requirement)
    assert len(opened) == 2
