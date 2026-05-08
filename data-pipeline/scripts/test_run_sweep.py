"""Tests for run_sweep.py — the aptness parameter sweep harness."""
from __future__ import annotations

import json
import logging
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


def test_load_sweep_config_rejects_empty_variations_list(tmp_path):
    """An empty ``variations: []`` list is a silent no-op footgun: the
    sweep would emit no rows and main() would still return 0, masking a
    misconfigured CI/scheduler run. Reject at the schema boundary so
    downstream code (renderer, exit-code logic) can rely on a non-empty
    invariant. The error must name the config path AND point the
    operator at the canonical example."""
    cfg_file = tmp_path / "empty.json"
    cfg_file.write_text(json.dumps({
        "name": "x",
        "db": "db.sqlite",
        "pairs": "p.json",
        "controls": "c.jsonl",
        "variations": [],
    }))
    with pytest.raises(ValueError) as exc:
        load_sweep_config(str(cfg_file))
    msg = str(exc.value)
    assert str(cfg_file) in msg
    assert "baseline_v2.yaml" in msg


def test_load_sweep_config_rejects_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_sweep_config(str(tmp_path / "nope.json"))


def test_load_sweep_config_rejects_unknown_top_level_key(tmp_path):
    """A typo in a top-level config key (e.g. `scorring`) must fail
    fast with a message naming the offending key and the config path."""
    cfg_file = tmp_path / "sweep.json"
    cfg_file.write_text(json.dumps({
        "name": "x",
        "db": "db.sqlite",
        "pairs": "p.json",
        "controls": "c.jsonl",
        "scorring": "jaccard_salience",  # typo
        "variations": [{"name": "v1"}],
    }))
    with pytest.raises(ValueError) as exc:
        load_sweep_config(str(cfg_file))
    msg = str(exc.value)
    assert "scorring" in msg
    assert str(cfg_file) in msg


def test_load_sweep_config_rejects_unknown_variation_key(tmp_path):
    """A typo inside a variation entry must fail fast."""
    cfg_file = tmp_path / "sweep.json"
    cfg_file.write_text(json.dumps({
        "name": "x",
        "db": "db.sqlite",
        "pairs": "p.json",
        "controls": "c.jsonl",
        "variations": [
            {"name": "v1", "scorring": "jaccard_salience"},  # typo
        ],
    }))
    with pytest.raises(ValueError) as exc:
        load_sweep_config(str(cfg_file))
    assert "scorring" in str(exc.value)


def test_load_sweep_config_rejects_unknown_scoring_at_boundary(tmp_path):
    """A typo in `scoring` (e.g. ``jaccard_salinece``) must fail at
    config-load, not later inside ``_run_one_variation`` after the sweep
    has begun churning. Failing late wastes setup, leaves partial sweep
    artefacts and confuses error attribution — the boundary validator
    already strict-checks every other enumerated field, so ``scoring``
    should be no different."""
    import evaluate_aptness  # noqa: PLC0415 — local import to read registry under test

    cfg_file = tmp_path / "sweep.json"
    cfg_file.write_text(json.dumps({
        "name": "x",
        "db": "db.sqlite",
        "pairs": "p.json",
        "controls": "c.jsonl",
        "variations": [
            {"name": "v1", "scoring": "not_a_real_scorer"},
        ],
    }))
    with pytest.raises(ValueError) as exc:
        load_sweep_config(str(cfg_file))
    msg = str(exc.value)
    # Path of the offending config (helps the operator find the file).
    assert str(cfg_file) in msg
    # Variation name (helps locate the offending row in a large sweep).
    assert "v1" in msg
    # The bad value, quoted, so the operator can grep for it.
    assert "not_a_real_scorer" in msg
    # Mention the registered scoring fns so the operator sees valid options.
    for fn_name in evaluate_aptness.SCORING_FNS:
        assert fn_name in msg


def test_load_sweep_config_requires_variation_name(tmp_path):
    """Each variation must declare a non-empty `name`."""
    cfg_file = tmp_path / "sweep.json"
    cfg_file.write_text(json.dumps({
        "name": "x",
        "db": "db.sqlite",
        "pairs": "p.json",
        "controls": "c.jsonl",
        "variations": [{"scoring": "jaccard_salience"}],
    }))
    with pytest.raises(ValueError) as exc:
        load_sweep_config(str(cfg_file))
    msg = str(exc.value)
    # Mention the offending variation by index (0)
    assert "0" in msg
    assert "name" in msg


def test_load_sweep_config_rejects_duplicate_variation_names(tmp_path):
    """Variation names must be unique within a sweep."""
    cfg_file = tmp_path / "sweep.json"
    cfg_file.write_text(json.dumps({
        "name": "x",
        "db": "db.sqlite",
        "pairs": "p.json",
        "controls": "c.jsonl",
        "variations": [
            {"name": "v1", "scoring": "jaccard_salience"},
            {"name": "v1", "scoring": "jaccard_raw"},
        ],
    }))
    with pytest.raises(ValueError) as exc:
        load_sweep_config(str(cfg_file))
    assert "v1" in str(exc.value)


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


def test_load_mrr_reference_includes_path_on_invalid_json(tmp_path):
    """A corrupt mrr_reference must surface the file path so the
    operator knows which artefact to fix."""
    ref_file = tmp_path / "ref.json"
    ref_file.write_text("not json")
    with pytest.raises(ValueError) as exc:
        load_mrr_reference(str(ref_file))
    assert str(ref_file) in str(exc.value)


def test_load_sweep_config_includes_path_on_invalid_yaml(tmp_path):
    """A corrupt YAML config must include the file path in the error."""
    pytest.importorskip("yaml")
    cfg_file = tmp_path / "broken.yaml"
    # Unbalanced brackets — yaml.safe_load raises YAMLError.
    cfg_file.write_text("name: x\nvariations: [a, b, c\n")
    with pytest.raises(ValueError) as exc:
        load_sweep_config(str(cfg_file))
    assert str(cfg_file) in str(exc.value)


def test_load_sweep_config_includes_path_on_invalid_json(tmp_path):
    """A corrupt JSON config must include the file path in the error."""
    cfg_file = tmp_path / "broken.json"
    cfg_file.write_text("{not valid json")
    with pytest.raises(ValueError) as exc:
        load_sweep_config(str(cfg_file))
    assert str(cfg_file) in str(exc.value)


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
    assert "| rank |" in md  # header row (rank is now leading column)
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
    # be the one with the largest separation_score. Column layout is
    # | rank | name | ... | so the name lives at index 2 of the split.
    first_data_name = data_lines[0].split("|")[2].strip()
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
    assert bad["error_type"] == "ValueError"
    assert (
        "nonexistent_formula" in bad["error_message"]
        or "Unknown scoring" in bad["error_message"]
    )

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


def test_variation_result_is_tagged_union(tmp_path):
    """Every variation row carries a `status` discriminator and the
    status-specific payload keys are present per branch.

    Pins the OkVariationResult / FailedVariationResult contract so a
    consumer can narrow on `row["status"]` and trust the payload shape.
    """
    from typing import cast

    _, cfg = _base_config(tmp_path, [
        {"name": "ok1", "scoring": "jaccard_salience"},
        {"name": "bad", "scoring": "nonexistent_formula"},
    ])
    cfg_path = tmp_path / "sweep.json"
    cfg_path.write_text(json.dumps(cfg))

    result = run_sweep_fn(cfg, config_path=str(cfg_path))

    ok_keys = {
        "status", "name", "scoring", "threshold_percentile", "threshold",
        "aptness_rate", "separation_score", "mean_apt_score",
        "mean_inapt_score", "n_apt", "n_inapt", "duration_ms",
    }
    failed_keys = {
        "status", "name", "scoring", "threshold_percentile",
        "error_type", "error_message", "duration_ms",
    }

    for row in result["variations"]:
        row = cast(dict, row)
        assert row["status"] in ("ok", "failed")
        if row["status"] == "ok":
            missing = ok_keys - row.keys()
            assert not missing, f"ok row missing keys: {missing}"
            # Discriminator narrows: separation_score is real on ok rows.
            assert isinstance(row["separation_score"], float)
        else:
            missing = failed_keys - row.keys()
            assert not missing, f"failed row missing keys: {missing}"
            # Failure rows expose error_type + error_message (not legacy `error`).
            assert isinstance(row["error_type"], str)
            assert isinstance(row["error_message"], str)


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


# --- main() exit-code escalation --------------------------------------------

def _write_sweep_config(tmp_path: Path, variations: list[dict]) -> tuple[Path, Path]:
    """Build a sweep config JSON file plus its referenced fixtures.

    Returns (config_path, output_path) so the test can drive ``main()`` and
    assert on the integer return value without relying on ``sys.exit``.
    """
    _, cfg = _base_config(tmp_path, variations)
    cfg_path = tmp_path / "sweep.json"
    cfg_path.write_text(json.dumps(cfg))
    output_path = tmp_path / "results.json"
    return cfg_path, output_path


def test_main_exits_zero_when_all_variations_succeed(tmp_path):
    cfg_path, output_path = _write_sweep_config(tmp_path, [
        {"name": "v1", "scoring": "jaccard_salience"},
        {"name": "v2", "scoring": "jaccard_raw"},
    ])
    rc = run_sweep.main(argv=[
        "--config", str(cfg_path),
        "--output", str(output_path),
    ])
    assert rc == 0


def test_main_exits_two_when_all_variations_fail(tmp_path):
    cfg_path, output_path = _write_sweep_config(tmp_path, [
        {"name": "bad1", "scoring": "nonexistent_a"},
        {"name": "bad2", "scoring": "nonexistent_b"},
    ])
    rc = run_sweep.main(argv=[
        "--config", str(cfg_path),
        "--output", str(output_path),
    ])
    assert rc == 2


def test_main_exits_one_when_some_variations_fail(tmp_path):
    cfg_path, output_path = _write_sweep_config(tmp_path, [
        {"name": "good", "scoring": "jaccard_salience"},
        {"name": "bad",  "scoring": "nonexistent_formula"},
    ])
    rc = run_sweep.main(argv=[
        "--config", str(cfg_path),
        "--output", str(output_path),
    ])
    assert rc == 1


def test_main_logs_error_when_all_variations_fail(tmp_path, caplog):
    cfg_path, output_path = _write_sweep_config(tmp_path, [
        {"name": "bad1", "scoring": "nonexistent_a"},
        {"name": "bad2", "scoring": "nonexistent_b"},
    ])
    with caplog.at_level(logging.ERROR, logger="run_sweep"):
        run_sweep.main(argv=[
            "--config", str(cfg_path),
            "--output", str(output_path),
        ])
    error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert error_records, "expected an ERROR-level record on total failure"
    assert any("ALL" in r.getMessage() for r in error_records)


def test_render_markdown_report_drops_per_row_mrr_ref_column(tmp_path):
    """The per-row mrr_ref column duplicates the global reference shown
    in the header block — drop it from the table to reduce noise. The
    global reference must still be visible in the header."""
    db_path, cfg = _base_config(tmp_path, [
        {"name": "v1", "scoring": "jaccard_salience"},
    ])
    ref_file = tmp_path / "baseline.json"
    ref_file.write_text(json.dumps({"mrr": {"value": 0.0123}}))
    cfg["mrr_reference"] = str(ref_file)
    cfg_path = tmp_path / "sweep.json"
    cfg_path.write_text(json.dumps(cfg))

    result = run_sweep_fn(cfg, config_path=str(cfg_path))
    md = render_markdown_report(result)

    # Find the table header line — first line starting with "| " that
    # isn't the markdown separator.
    header_line = next(
        line for line in md.splitlines()
        if line.startswith("| ") and "---" not in line
    )
    assert "mrr_ref" not in header_line
    # Global reference still surfaces in the header block.
    assert "0.0123" in md
    assert "MRR reference" in md


def test_render_markdown_report_includes_summary_line(tmp_path):
    """Summary line above the table tells operators at a glance which
    variation won and how many failed."""
    _, cfg = _base_config(tmp_path, [
        {"name": "v1", "scoring": "jaccard_salience"},
        {"name": "v2", "scoring": "jaccard_raw"},
    ])
    cfg_path = tmp_path / "sweep.json"
    cfg_path.write_text(json.dumps(cfg))
    result = run_sweep_fn(cfg, config_path=str(cfg_path))
    md = render_markdown_report(result)

    assert "succeeded" in md
    assert "Best by separation_score" in md


def test_render_markdown_report_includes_rank_column(tmp_path):
    """The first column of the per-row table is an explicit rank so the
    operator does not have to count rows to find the winner."""
    _, cfg = _base_config(tmp_path, [
        {"name": "v1", "scoring": "jaccard_salience"},
        {"name": "v2", "scoring": "jaccard_raw"},
    ])
    cfg_path = tmp_path / "sweep.json"
    cfg_path.write_text(json.dumps(cfg))
    result = run_sweep_fn(cfg, config_path=str(cfg_path))
    md = render_markdown_report(result)

    header_line = next(
        line for line in md.splitlines()
        if line.startswith("| ") and "---" not in line
    )
    # rank column appears before name
    assert "rank" in header_line
    # First ok data row begins with rank 1.
    data_lines = [
        line for line in md.splitlines()
        if line.startswith("| ") and "---" not in line
        and "rank" not in line
    ]
    first_cell = data_lines[0].split("|")[1].strip()
    assert first_cell == "1"


def test_render_markdown_report_emits_failures_section_when_any_failed(tmp_path):
    """When any variation fails, the report appends a Failures section
    listing each failure with error_type and error_message."""
    _, cfg = _base_config(tmp_path, [
        {"name": "good", "scoring": "jaccard_salience"},
        {"name": "bad", "scoring": "nonexistent_formula"},
    ])
    cfg_path = tmp_path / "sweep.json"
    cfg_path.write_text(json.dumps(cfg))
    result = run_sweep_fn(cfg, config_path=str(cfg_path))
    md = render_markdown_report(result)

    assert "## Failures" in md
    assert "bad" in md
    assert "error_type" in md
    assert "ValueError" in md


def test_render_markdown_report_omits_failures_section_when_all_ok(tmp_path):
    """No failures → no Failures section (avoids empty boilerplate)."""
    _, cfg = _base_config(tmp_path, [
        {"name": "v1", "scoring": "jaccard_salience"},
    ])
    cfg_path = tmp_path / "sweep.json"
    cfg_path.write_text(json.dumps(cfg))
    result = run_sweep_fn(cfg, config_path=str(cfg_path))
    md = render_markdown_report(result)

    assert "## Failures" not in md


def test_render_markdown_report_failed_row_uses_em_dash_consistently(tmp_path):
    """Failed rows use a consistent em-dash placeholder for numeric
    cells and a bare ``failed`` token in the status cell — the full
    error appears in the Failures appendix, not inline.

    Use ``jaccard_raw`` as the failed scoring (a registered name) so we
    can distinguish "scoring cell echoes the input" from "error message
    leaked into the row" — a bad scoring spelling would otherwise be
    indistinguishable from the inlined error.
    """
    _, cfg = _base_config(tmp_path, [
        {"name": "good", "scoring": "jaccard_salience"},
        # Bogus scoring name forces status=failed via the harness's
        # exception-isolation path, which is the contract we want to pin.
        {"name": "bad", "scoring": "definitely_not_real"},
    ])
    cfg_path = tmp_path / "sweep.json"
    cfg_path.write_text(json.dumps(cfg))
    result = run_sweep_fn(cfg, config_path=str(cfg_path))
    md = render_markdown_report(result)

    # Locate the failed row by name + status token.
    failed_lines = [
        line for line in md.splitlines()
        if line.startswith("| ") and "| bad |" in line and "failed" in line
        and "---" not in line
    ]
    assert failed_lines, "expected a markdown row for the failed variation"
    failed_line = failed_lines[0]
    cells = [c.strip() for c in failed_line.split("|")[1:-1]]
    # Status cell must be the bare token "failed" (no error inline).
    assert cells[-1] == "failed"
    # All numeric cells (everything between scoring and status) are em-dashes.
    # Layout: | rank | name | scoring | threshold | aptness_rate |
    #         separation | mean_apt | mean_inapt | n_apt | n_inapt | status |
    numeric_cells = cells[3:-1]  # drop rank/name/scoring and status
    assert all(c == "—" for c in numeric_cells), (
        f"expected all numeric cells == '—', got {numeric_cells}"
    )
    # Rank cell on a failed row is also em-dash.
    assert cells[0] == "—"
    # No error-type / error-message text leaks into the row.
    assert "ValueError" not in failed_line
    assert "Unknown scoring" not in failed_line


def _synthetic_sweep_result(variations: list[dict]) -> dict:
    """Build a minimal sweep_result dict for render_markdown_report tests
    that don't need the full run_sweep pipeline. Saves the cost of fixture
    DB construction when we only care about the report-rendering branches.
    """
    return {
        "name": "synthetic",
        "schema_version": SCHEMA_VERSION,
        "timestamp": "2026-01-01T00:00:00Z",
        "git_commit": "deadbeef",
        "config_path": "synthetic.json",
        "db_path": "synthetic.db",
        "mrr_reference_path": None,
        "mrr_reference_value": None,
        "duration_ms": 0.0,
        "variations": variations,
    }


def test_render_markdown_report_summary_for_all_failed_with_rows():
    """When every variation failed BUT there is at least one failed row,
    the Summary should still reference the Failures appendix AND the
    appendix must actually render. Pins the existing intended behaviour
    so the empty-variations fix does not regress this branch.
    """
    failed_row = {
        "name": "bad",
        "scoring": "nonexistent_formula",
        "status": "failed",
        "error_type": "ValueError",
        "error_message": "Unknown scoring formula: nonexistent_formula",
    }
    result = _synthetic_sweep_result(variations=[failed_row])
    md = render_markdown_report(result)

    # Existing all-failed message survives.
    assert "All variations failed — see Failures below." in md
    # And the appendix the message points at actually renders.
    assert "## Failures" in md
    assert "bad" in md
    assert "ValueError" in md


@pytest.mark.parametrize("missing_key", ["db", "pairs", "controls"])
def test_load_sweep_config_rejects_missing_required_paths(tmp_path, missing_key):
    """Each of `db`, `pairs`, `controls` is a Required[] member of the
    SweepConfig schema. Presence must be enforced at the schema boundary
    (load_sweep_config), not deferred to run_sweep — otherwise the
    `cast(SweepConfig, data)` at the end of the loader lies, and the
    error catalogue splits into two formats. The error must follow the
    iter-6 path-prefixed lowercase pattern AND point at the canonical
    example so the operator can crib the shape."""
    full_cfg = {
        "name": "x",
        "db": "db.sqlite",
        "pairs": "p.json",
        "controls": "c.jsonl",
        "variations": [{"name": "v1", "scoring": "jaccard_salience"}],
    }
    full_cfg.pop(missing_key)
    cfg_file = tmp_path / "sweep.json"
    cfg_file.write_text(json.dumps(full_cfg))

    with pytest.raises(ValueError) as exc:
        load_sweep_config(str(cfg_file))
    msg = str(exc.value)
    assert f"sweep config {cfg_file}: missing required key {missing_key!r}" in msg
    assert "baseline_v2.yaml" in msg


def test_load_sweep_config_missing_db_error_mentions_baseline(tmp_path):
    """A missing top-level required key (e.g. ``db``) must point the
    operator at the canonical example so they can crib the shape."""
    cfg_file = tmp_path / "sweep.json"
    cfg_file.write_text(json.dumps({
        "name": "x",
        "pairs": "p.json",
        "controls": "c.jsonl",
        "variations": [{"name": "v1", "scoring": "jaccard_salience"}],
    }))
    with pytest.raises(ValueError) as exc:
        load_sweep_config(str(cfg_file))
    assert "baseline_v2.yaml" in str(exc.value)


def test_load_sweep_config_rejects_threshold_percentile_below_zero(tmp_path):
    """`_percentile` clamps pct<=0 to the min sample silently. Reject at
    the schema boundary so a typo (`-5` for `5`) cannot quietly degrade
    a sweep variation to a min-sample threshold without operator notice."""
    cfg_file = tmp_path / "sweep.json"
    cfg_file.write_text(json.dumps({
        "name": "x",
        "db": "db.sqlite",
        "pairs": "p.json",
        "controls": "c.jsonl",
        "variations": [{
            "name": "v1",
            "scoring": "jaccard_salience",
            "threshold_percentile": -5,
        }],
    }))
    with pytest.raises(ValueError) as exc:
        load_sweep_config(str(cfg_file))
    msg = str(exc.value)
    assert "threshold_percentile" in msg
    assert "-5" in msg
    assert "0" in msg and "100" in msg  # documents the valid range


def test_load_sweep_config_rejects_threshold_percentile_above_hundred(tmp_path):
    """Symmetric to the below-zero case — pct>=100 clamps to max sample
    silently in `_percentile`. Reject at schema boundary."""
    cfg_file = tmp_path / "sweep.json"
    cfg_file.write_text(json.dumps({
        "name": "x",
        "db": "db.sqlite",
        "pairs": "p.json",
        "controls": "c.jsonl",
        "variations": [{
            "name": "v1",
            "scoring": "jaccard_salience",
            "threshold_percentile": 250.0,
        }],
    }))
    with pytest.raises(ValueError) as exc:
        load_sweep_config(str(cfg_file))
    msg = str(exc.value)
    assert "threshold_percentile" in msg
    assert "250" in msg


def test_load_sweep_config_accepts_threshold_percentile_boundary_values(tmp_path):
    """0 and 100 are the inclusive bounds — both must load without error
    so callers can sweep the full percentile range."""
    cfg_file = tmp_path / "sweep.json"
    cfg_file.write_text(json.dumps({
        "name": "x",
        "db": "db.sqlite",
        "pairs": "p.json",
        "controls": "c.jsonl",
        "variations": [
            {"name": "lo", "scoring": "jaccard_salience", "threshold_percentile": 0},
            {"name": "hi", "scoring": "jaccard_salience", "threshold_percentile": 100},
        ],
    }))
    cfg = load_sweep_config(str(cfg_file))
    assert cfg["variations"][0]["threshold_percentile"] == 0
    assert cfg["variations"][1]["threshold_percentile"] == 100


def test_load_sweep_config_rejects_bool_threshold_percentile(tmp_path):
    """In Python, `bool` is a subclass of `int`, so `True`/`False` would
    sneak through `isinstance(tp, (int, float))` and validate as 1/0
    silently. The validator deliberately rejects bool — pin the
    behaviour with a test so a future "simplification" cannot
    silently undo the guard."""
    cfg_file = tmp_path / "sweep.json"
    cfg_file.write_text(json.dumps({
        "name": "x",
        "db": "db.sqlite",
        "pairs": "p.json",
        "controls": "c.jsonl",
        "variations": [{
            "name": "v1",
            "scoring": "jaccard_salience",
            "threshold_percentile": True,
        }],
    }))
    with pytest.raises(ValueError) as exc:
        load_sweep_config(str(cfg_file))
    msg = str(exc.value)
    assert "threshold_percentile" in msg
    assert "bool" in msg


def test_load_sweep_config_rejects_non_numeric_threshold_percentile(tmp_path):
    """A string in `threshold_percentile` is a YAML quoting mistake; reject
    with a typed error rather than letting it fail later in `_percentile`."""
    cfg_file = tmp_path / "sweep.json"
    cfg_file.write_text(json.dumps({
        "name": "x",
        "db": "db.sqlite",
        "pairs": "p.json",
        "controls": "c.jsonl",
        "variations": [{
            "name": "v1",
            "scoring": "jaccard_salience",
            "threshold_percentile": "ninety-five",
        }],
    }))
    with pytest.raises(ValueError) as exc:
        load_sweep_config(str(cfg_file))
    assert "threshold_percentile" in str(exc.value)


def test_run_sweep_argparse_lists_scoring_formulas_in_help():
    """The ``run_sweep --help`` output should mention at least one
    registered scoring formula so an operator knows which keys are
    valid in `scoring:` without having to grep the source."""
    import evaluate_aptness as ea
    parser = run_sweep._build_arg_parser()
    help_text = parser.format_help()
    registered = sorted(ea.SCORING_FNS.keys())
    assert any(name in help_text for name in registered), (
        f"expected at least one of {registered} in help text:\n{help_text}"
    )


def test_main_logs_warning_when_some_variations_fail(tmp_path, caplog):
    cfg_path, output_path = _write_sweep_config(tmp_path, [
        {"name": "good", "scoring": "jaccard_salience"},
        {"name": "bad",  "scoring": "nonexistent_formula"},
    ])
    with caplog.at_level(logging.WARNING, logger="run_sweep"):
        run_sweep.main(argv=[
            "--config", str(cfg_path),
            "--output", str(output_path),
        ])
    finish_warnings = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "sweep finish" in r.getMessage()
    ]
    assert finish_warnings, "expected a WARNING 'sweep finish' record on partial failure"
