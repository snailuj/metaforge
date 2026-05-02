"""Tests for evaluate_aptness.py — the discriminative aptness evaluator."""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from evaluate_aptness import (
    PairScore,
    aggregate_metrics,
    classify_aptness,
    evaluate,
    load_apt_pairs,
    load_inapt_controls,
    lookup_primary_synset,
    score_pair,
)


# --- In-memory fixture DB ----------------------------------------------------

def _build_fixture_db() -> sqlite3.Connection:
    """Build a tiny in-memory DB mirroring the relevant schema slice."""
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
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
    """)

    # anger and fire share salient cluster 1 (heat/intensity), differ on others
    conn.executescript("""
        INSERT INTO lemmas VALUES
            ('anger', 'S001'), ('fire', 'S002'),
            ('approach', 'S003'), ('coming', 'S004'),
            ('orphan', 'S999');
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
    """)
    conn.commit()
    return conn


# --- Lookup ------------------------------------------------------------------

def test_lookup_primary_synset_resolves_curated_lemma():
    conn = _build_fixture_db()
    assert lookup_primary_synset(conn, "anger") == "S001"


def test_lookup_primary_synset_falls_back_to_lemmas_table():
    conn = _build_fixture_db()
    # 'orphan' is in lemmas but not in curated vocab
    assert lookup_primary_synset(conn, "orphan") == "S999"


def test_lookup_primary_synset_returns_none_for_unknown_lemma():
    conn = _build_fixture_db()
    assert lookup_primary_synset(conn, "zzznotaword") is None


def test_lookup_primary_synset_is_case_insensitive():
    conn = _build_fixture_db()
    assert lookup_primary_synset(conn, "Anger") == "S001"


# --- Scoring -----------------------------------------------------------------

def test_score_pair_with_overlap_returns_scored():
    conn = _build_fixture_db()
    result = score_pair(conn, "anger", "fire")
    assert result.status == "scored"
    assert result.score is not None
    assert result.score > 0.0


def test_score_pair_without_overlap_is_scored_zero():
    """Both synsets resolve and have curated properties — no shared clusters
    is a real evaluation outcome (score 0.0), not a coverage gap."""
    conn = _build_fixture_db()
    # approach (cluster 4) and coming (cluster 5) share no clusters
    result = score_pair(conn, "approach", "coming")
    assert result.status == "scored"
    assert result.score == 0.0


def test_score_pair_with_unresolvable_word_is_unresolved():
    conn = _build_fixture_db()
    result = score_pair(conn, "anger", "zzznotaword")
    assert result.status == "unresolved"
    assert result.score is None


def test_score_pair_with_no_curated_properties_is_no_properties():
    """A resolved synset that lacks curated properties is a coverage gap,
    not a real zero score — must be flagged distinctly so it can be excluded
    from the apt mean."""
    conn = _build_fixture_db()
    # 'orphan' resolves via lemmas table to S999 — but S999 has no rows in
    # synset_properties_curated. Pairing it with a real word must yield
    # a no_properties status rather than scored=0.0.
    result = score_pair(conn, "anger", "orphan")
    assert result.status == "no_properties"
    assert result.score is None


def test_score_pair_is_symmetric():
    conn = _build_fixture_db()
    a = score_pair(conn, "anger", "fire")
    b = score_pair(conn, "fire", "anger")
    assert a.status == b.status
    assert a.score == b.score


def test_pair_score_rejects_inconsistent_status_score_combos():
    """The dataclass enforces "score is None iff status != 'scored'".

    Without the runtime check, a caller could construct a PairScore that
    silently breaks the invariant the cohort logic relies on (e.g. a
    'scored' result with score=None would crash _score_cohort, an
    'unresolved' with a real score would deflate counters).
    """
    # Legal constructions
    PairScore(status="scored", score=0.5)
    PairScore(status="unresolved", score=None)
    PairScore(status="no_properties", score=None)

    # Illegal: scored without a score
    with pytest.raises(ValueError, match="scored.*score"):
        PairScore(status="scored", score=None)

    # Illegal: unresolved with a score
    with pytest.raises(ValueError, match="unresolved.*score"):
        PairScore(status="unresolved", score=0.5)

    # Illegal: no_properties with a score
    with pytest.raises(ValueError, match="no_properties.*score"):
        PairScore(status="no_properties", score=0.0)


# --- Loaders -----------------------------------------------------------------

def test_load_apt_pairs_reads_metaphor_pairs_v2(tmp_path):
    pairs_file = tmp_path / "pairs.json"
    pairs_file.write_text(json.dumps([
        {"source": "anger", "target": "fire", "tier": "strong"},
        {"source": "hope", "target": "light", "tier": "strong"},
    ]))
    pairs = load_apt_pairs(str(pairs_file))
    assert len(pairs) == 2
    assert pairs[0] == {"source": "anger", "target": "fire", "tier": "strong"}


def test_load_inapt_controls_reads_jsonl(tmp_path):
    controls_file = tmp_path / "controls.jsonl"
    controls_file.write_text(
        '{"target": "approach", "paraphrase": "coming", "label": "inapt"}\n'
        '{"target": "leading", "paraphrase": "heading", "label": "inapt"}\n'
    )
    controls = load_inapt_controls(str(controls_file))
    assert len(controls) == 2
    assert controls[0]["target"] == "approach"
    assert controls[0]["paraphrase"] == "coming"


def test_load_inapt_controls_filters_non_inapt(tmp_path):
    """Defensive: even if mixed labels appear, only inapt rows count."""
    controls_file = tmp_path / "mixed.jsonl"
    controls_file.write_text(
        '{"target": "a", "paraphrase": "b", "label": "inapt"}\n'
        '{"target": "c", "paraphrase": "d", "label": "apt"}\n'
    )
    controls = load_inapt_controls(str(controls_file))
    assert len(controls) == 1


def test_load_inapt_controls_skips_malformed_lines_with_warning(tmp_path, caplog):
    """A truncated/garbage line must not abort loading — warn and continue.

    Producer (preprocess_munch.write_jsonl) is generally trustworthy, but
    consumer-supplied JSONL or a previously-crashed run can leave a partial
    line. Loader must tolerate it.
    """
    import logging as _logging

    controls_file = tmp_path / "controls.jsonl"
    controls_file.write_text(
        '{"target": "a", "paraphrase": "b", "label": "inapt"}\n'
        '{this is not json\n'
        '{"target": "c", "paraphrase": "d", "label": "inapt"}\n'
    )

    with caplog.at_level(_logging.WARNING, logger="evaluate_aptness"):
        controls = load_inapt_controls(str(controls_file))

    assert len(controls) == 2
    assert controls[0]["target"] == "a"
    assert controls[1]["target"] == "c"

    # A warning was emitted that names the line number (line 2).
    warnings = [r for r in caplog.records if r.levelno == _logging.WARNING]
    assert warnings, "expected at least one warning for the malformed line"
    assert any("2" in w.getMessage() for w in warnings), (
        f"expected line number 2 in warning; got: {[w.getMessage() for w in warnings]}"
    )


# --- Classification & aggregation -------------------------------------------

def test_classify_aptness_uses_threshold():
    apt_scores = [0.5, 0.7, 0.9]
    inapt_scores = [0.0, 0.1, 0.2]
    threshold = 0.3
    result = classify_aptness(apt_scores, inapt_scores, threshold)
    assert result["aptness_rate"] == 1.0  # all 3 apt scores > threshold
    assert result["false_positive_rate"] == 0.0  # no inapt > threshold


def test_classify_aptness_handles_empty():
    result = classify_aptness([], [], 0.5)
    assert result["aptness_rate"] == 0.0
    assert result["false_positive_rate"] == 0.0


def test_aggregate_metrics_computes_separation():
    apt_scores = [0.6, 0.8]
    inapt_scores = [0.1, 0.2]
    agg = aggregate_metrics(apt_scores, inapt_scores)
    assert agg["mean_apt_score"] == pytest.approx(0.7)
    assert agg["mean_inapt_score"] == pytest.approx(0.15)
    assert agg["separation_score"] == pytest.approx(0.55)


def test_aggregate_metrics_handles_missing_inapt():
    """When inapt is empty, mean_inapt is 0 and separation reduces to mean_apt."""
    agg = aggregate_metrics([0.5, 0.7], [])
    assert agg["mean_apt_score"] == pytest.approx(0.6)
    assert agg["mean_inapt_score"] == 0.0
    assert agg["separation_score"] == pytest.approx(0.6)


def test_aggregate_metrics_zero_when_both_empty():
    agg = aggregate_metrics([], [])
    assert agg["mean_apt_score"] == 0.0
    assert agg["mean_inapt_score"] == 0.0
    assert agg["separation_score"] == 0.0


# --- End-to-end --------------------------------------------------------------

def test_evaluate_produces_required_json_shape(tmp_path):
    """Smoke test: evaluate() returns the contractual JSON shape."""
    conn = _build_fixture_db()

    pairs_file = tmp_path / "pairs.json"
    pairs_file.write_text(json.dumps([
        {"source": "anger", "target": "fire", "tier": "strong"},
    ]))
    controls_file = tmp_path / "controls.jsonl"
    controls_file.write_text(
        '{"target": "approach", "paraphrase": "coming", "label": "inapt"}\n'
    )

    result = evaluate(
        conn=conn,
        pairs_file=str(pairs_file),
        controls_file=str(controls_file),
    )

    # Required top-level keys
    assert "aptness_rate" in result
    assert "separation_score" in result
    assert "per_pair_scores" in result
    assert "aggregate" in result
    assert "config" in result

    # per_pair_scores has both classes
    classes = {p["class"] for p in result["per_pair_scores"]}
    assert classes == {"apt", "inapt"}

    # apt > inapt for our crafted fixture → separation > 0
    assert result["separation_score"] > 0.0


def test_evaluate_excludes_no_properties_pairs_from_apt_mean(tmp_path):
    """A pair where one side has no curated properties must be reported via
    apt_no_properties counter and must NOT enter apt_scores (would deflate
    mean_apt and shrink separation_score)."""
    conn = _build_fixture_db()

    pairs_file = tmp_path / "pairs.json"
    pairs_file.write_text(json.dumps([
        # Real apt pair with overlap → should score positive
        {"source": "anger", "target": "fire", "tier": "strong"},
        # 'orphan' has no curated properties → coverage gap, NOT zero
        {"source": "anger", "target": "orphan", "tier": "strong"},
    ]))
    controls_file = tmp_path / "controls.jsonl"
    controls_file.write_text("")

    result = evaluate(
        conn=conn,
        pairs_file=str(pairs_file),
        controls_file=str(controls_file),
    )

    agg = result["aggregate"]
    # n_apt counts only scored pairs, not no-properties pairs
    assert agg["n_apt"] == 1
    assert agg["apt_no_properties"] == 1
    assert agg["apt_unresolved"] == 0
    # mean_apt reflects only the real scored pair (anger/fire), not 0.0
    # from the orphan pair conflation.
    assert agg["mean_apt_score"] > 0.0

    # per_pair scores carry the status distinction
    apt_pp = [p for p in result["per_pair_scores"] if p["class"] == "apt"]
    statuses = sorted(p["status"] for p in apt_pp)
    assert statuses == ["no_properties", "scored"]
