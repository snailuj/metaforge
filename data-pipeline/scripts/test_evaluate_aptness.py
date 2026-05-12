"""Tests for evaluate_aptness.py — the discriminative aptness evaluator."""
import json
import math
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import evaluate_aptness
from evaluate_aptness import (
    DEFAULT_SCORING,
    SCORING_FNS,
    PairScore,
    _cosine_salience,
    _jaccard_raw,
    _jaccard_salience,
    _ortony_imbalance,
    _ortony_vehicle_salience,
    _random_uniform,
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


def test_load_inapt_controls_skips_non_dict_jsonl_lines_with_warning(tmp_path, caplog):
    """JSONL lines that parse to non-dict values must be skipped, not crash.

    `json.loads` succeeds on `null`, bare strings, lists, ints — none of which
    support `.get("label")`. Without an isinstance gate, the loader raises
    AttributeError and aborts the whole load. Documented intent is to tolerate
    garbled input, so non-dict lines must be warned and skipped just like a
    JSONDecodeError.
    """
    import logging as _logging

    controls_file = tmp_path / "controls.jsonl"
    controls_file.write_text(
        '{"target": "a", "paraphrase": "b", "label": "inapt"}\n'
        'null\n'
        '"a string"\n'
        '[1, 2, 3]\n'
        '{"target": "c", "paraphrase": "d", "label": "inapt"}\n'
    )

    with caplog.at_level(_logging.WARNING, logger="evaluate_aptness"):
        controls = load_inapt_controls(str(controls_file))

    # Valid records still loaded despite the non-dict noise.
    assert len(controls) == 2
    assert controls[0]["target"] == "a"
    assert controls[1]["target"] == "c"

    warnings = [r for r in caplog.records if r.levelno == _logging.WARNING]
    # One warning per non-dict line (lines 2, 3, 4).
    assert len(warnings) >= 3, (
        f"expected >=3 warnings for non-dict lines; got {len(warnings)}: "
        f"{[w.getMessage() for w in warnings]}"
    )
    messages = [w.getMessage() for w in warnings]
    # Each warning must reference both the file path and the offending line number.
    assert any(str(controls_file) in m and "2" in m for m in messages), (
        f"expected warning mentioning {controls_file} and line 2; got: {messages}"
    )
    assert any(str(controls_file) in m and "3" in m for m in messages), (
        f"expected warning mentioning {controls_file} and line 3; got: {messages}"
    )
    assert any(str(controls_file) in m and "4" in m for m in messages), (
        f"expected warning mentioning {controls_file} and line 4; got: {messages}"
    )


def test_random_uniform_docstring_documents_union_size_dependency():
    """Regression marker: the null-reference scorer's docstring must flag
    the cohort-level union-size assumption.

    Without this caveat a downstream reader interpreting
    ``separation_score - random_uniform_separation`` as "real signal above
    null" can be misled when apt and inapt cohorts have systematically
    different union-size distributions. We pin the keyword presence so
    the warning cannot silently regress to a bare "deterministic null".
    """
    doc = _random_uniform.__doc__ or ""
    lower = doc.lower()
    # The two key concepts that must appear:
    assert "union-size" in lower or "union size" in lower, (
        "expected the docstring to mention 'union-size' / 'union size'"
    )
    assert "cohort" in lower, "expected the docstring to mention 'cohort'"
    # And the sanity-floor framing — not a calibrated null hypothesis test.
    assert "sanity" in lower or "calibrated" in lower, (
        "expected the docstring to frame this as a sanity-floor reference, "
        "not a calibrated null hypothesis test"
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


# --- Scoring registry --------------------------------------------------------

def test_scoring_registry_contains_required_formulas():
    """Slice S02 contract: registry must expose at least these three names.

    Sweep configs and the default flag rely on exact key strings; this
    test guards against accidental rename / removal during refactor.
    """
    for name in ("jaccard_salience", "jaccard_raw", "cosine_salience"):
        assert name in SCORING_FNS, f"missing scoring formula: {name}"
    assert DEFAULT_SCORING == "jaccard_salience"


# Each formula is exercised on three crafted vector pairs:
#   1. known overlap with asymmetric salience
#   2. no overlap (disjoint cluster_ids)
#   3. salience-asymmetric overlap (same clusters, different weights)


def test_jaccard_salience_known_overlap():
    pa = {1: 0.9, 2: 0.6}
    pb = {1: 0.85, 3: 0.7}
    # shared = {1}: num = min(0.9,0.85) = 0.85
    # union = {1,2,3}: den = max(0.9,0.85)+max(0.6,0)+max(0,0.7) = 0.9+0.6+0.7 = 2.2
    assert _jaccard_salience(pa, pb) == pytest.approx(0.85 / 2.2)


def test_jaccard_salience_no_overlap_is_zero():
    pa = {1: 1.0, 2: 1.0}
    pb = {3: 1.0, 4: 1.0}
    assert _jaccard_salience(pa, pb) == 0.0


def test_jaccard_salience_asymmetric_weights():
    """Same clusters, asymmetric saliences — score reflects min/max ratio."""
    pa = {1: 1.0, 2: 1.0}
    pb = {1: 0.1, 2: 0.1}
    # shared = {1,2}, num = 0.1+0.1 = 0.2, den = 1.0+1.0 = 2.0
    assert _jaccard_salience(pa, pb) == pytest.approx(0.2 / 2.0)


def test_jaccard_raw_known_overlap_ignores_salience():
    """Raw Jaccard counts cluster overlap only — saliences must not matter."""
    pa = {1: 0.9, 2: 0.6}
    pb = {1: 0.001, 3: 0.7}
    # |inter|=1 (cluster 1), |union|=3 → 1/3
    assert _jaccard_raw(pa, pb) == pytest.approx(1.0 / 3.0)


def test_jaccard_raw_no_overlap_is_zero():
    assert _jaccard_raw({1: 1.0}, {2: 1.0}) == 0.0


def test_jaccard_raw_is_invariant_to_salience_asymmetry():
    """Identical cluster sets → 1.0 regardless of weight values."""
    assert _jaccard_raw({1: 0.9, 2: 0.6}, {1: 0.001, 2: 0.001}) == 1.0


def test_cosine_salience_known_overlap():
    pa = {1: 1.0, 2: 0.0}
    pb = {1: 1.0, 2: 0.0}
    # Identical vectors → cosine = 1.0
    assert _cosine_salience(pa, pb) == pytest.approx(1.0)


def test_cosine_salience_no_overlap_is_zero():
    """Disjoint cluster_ids → zero-padded vectors are orthogonal → cos=0."""
    assert _cosine_salience({1: 1.0}, {2: 1.0}) == 0.0


def test_cosine_salience_asymmetric_weights():
    """Different magnitudes but same direction → cosine still 1.0."""
    pa = {1: 1.0, 2: 1.0}
    pb = {1: 0.5, 2: 0.5}
    assert _cosine_salience(pa, pb) == pytest.approx(1.0)


def test_cosine_salience_zero_norm_returns_zero():
    """All-zero salience on either side → zero norm → score 0.0 (not NaN)."""
    assert _cosine_salience({1: 0.0, 2: 0.0}, {1: 1.0, 2: 1.0}) == 0.0
    assert _cosine_salience({}, {}) == 0.0


# --- ortony_vehicle_salience (asymmetric) -----------------------------------

# Formula contract: normalised vehicle-side coverage —
#   f(pa, pb) = (Σ_{c ∈ pa ∩ pb} pb[c]) / (Σ_{c ∈ pb} pb[c])
# Reads as "what fraction of the vehicle's salience mass is captured by
# properties also present in the topic". Bounded [0, 1] by construction
# (numerator is a subset-sum of the denominator). Asymmetric: swapping
# (pa, pb) normalises by a different mass and so produces a different
# score whenever salience distributions differ — that asymmetry is the
# defining behavioural property versus the three symmetric variants.


def test_ortony_vehicle_salience_registered_in_scoring_fns():
    """M02-S01 contract: ortony_vehicle_salience exposed alongside the S03 set."""
    assert "ortony_vehicle_salience" in SCORING_FNS
    assert SCORING_FNS["ortony_vehicle_salience"] is _ortony_vehicle_salience


def test_ortony_vehicle_salience_known_overlap():
    """Crafted case verifies the normalised-coverage formula end-to-end."""
    pa = {1: 0.9, 2: 0.6}
    pb = {1: 0.85, 3: 0.7}
    # shared = {1}: num = pb[1] = 0.85
    # vehicle mass = pb[1]+pb[3] = 0.85+0.7 = 1.55
    assert _ortony_vehicle_salience(pa, pb) == pytest.approx(0.85 / 1.55)


def test_ortony_vehicle_salience_no_overlap_is_zero():
    """Disjoint cluster_ids → empty intersection → numerator 0 → score 0."""
    assert _ortony_vehicle_salience({1: 1.0, 2: 1.0}, {3: 1.0, 4: 1.0}) == 0.0


def test_ortony_vehicle_salience_is_asymmetric():
    """Swapping (pa, pb) must change the score when salience distributions
    differ — this is the defining property of the formula vs the three
    symmetric variants.

    pa has high salience on cluster 1 (its shared cluster).
    pb has cluster 1 as a small fraction of its total mass.
    → score(pa,pb) is small (1 contributes only ~14% of pb's mass).
    → score(pb,pa) is large (1 contributes ~90% of pa's mass).
    """
    pa = {1: 0.9, 2: 0.1}
    pb = {1: 0.1, 3: 0.6}
    forward = _ortony_vehicle_salience(pa, pb)
    backward = _ortony_vehicle_salience(pb, pa)
    assert forward != backward
    # Sanity-check direction matches the docstring rationale above:
    assert forward == pytest.approx(0.1 / 0.7)
    assert backward == pytest.approx(0.9 / 1.0)


def test_ortony_vehicle_salience_in_unit_interval():
    """Score is bounded [0, 1] because the numerator is a subset-sum of
    the denominator. Spot-check against an extreme: vehicle fully
    contained in topic → score = 1.0."""
    pa = {1: 0.9, 2: 0.6, 3: 0.4}
    pb = {1: 0.5, 2: 0.5}
    # shared = {1,2}: num = pb[1]+pb[2] = 1.0
    # vehicle mass = 1.0 → score = 1.0
    assert _ortony_vehicle_salience(pa, pb) == pytest.approx(1.0)


def test_ortony_vehicle_salience_zero_vehicle_mass_returns_zero():
    """All-zero salience on the vehicle side → denominator 0 → score 0.0
    (not NaN, not ZeroDivisionError). Mirrors the cosine_salience
    zero-norm guard so the registry stays uniformly safe."""
    assert _ortony_vehicle_salience({1: 1.0}, {1: 0.0, 2: 0.0}) == 0.0
    assert _ortony_vehicle_salience({}, {}) == 0.0


# --- ortony_imbalance (asymmetric, equal-salience penalised) ----------------

# Formula contract: imbalance-weighted vehicle dominance —
#   f(pa, pb) = (Σ_{c ∈ pa ∩ pb} pb[c] × max(0, pb[c] − pa[c]))
#              / (Σ_{c ∈ pb} pb[c]²)
# Reads as "fraction of the vehicle's imbalance-weighted prominence captured
# by properties on which the vehicle is more salient than the topic". Bounded
# [0, 1]: per shared term ≤ pb[c]², numerator's shared-only sum ≤ Σ_{c ∈ pb}
# pb[c]² which is the denominator. Asymmetric: swapping (pa, pb) changes
# both the per-term subtraction direction AND the normaliser.
#
# Difference from ortony_vehicle_salience: equal-salience properties
# contribute zero here (max(0, pb − pa) = 0 when pb = pa). This directly
# targets the MUNCH-bias mechanism — paraphrase pairs that share equally-
# salient surface properties cannot move the score in this formula.


def test_ortony_imbalance_registered_in_scoring_fns():
    """M02-S02 contract: ortony_imbalance exposed alongside the rest."""
    assert "ortony_imbalance" in SCORING_FNS
    assert SCORING_FNS["ortony_imbalance"] is _ortony_imbalance


def test_ortony_imbalance_known_overlap():
    """Crafted case — verifies the imbalance-weighted formula end-to-end."""
    pa = {1: 0.3, 2: 0.0}
    pb = {1: 0.9, 3: 0.5}
    # shared = {1}: term = pb[1] × max(0, pb[1] − pa[1])
    #                     = 0.9 × max(0, 0.9 − 0.3) = 0.9 × 0.6 = 0.54
    # vehicle squared-mass = pb[1]² + pb[3]² = 0.81 + 0.25 = 1.06
    # score = 0.54 / 1.06
    assert _ortony_imbalance(pa, pb) == pytest.approx(0.54 / 1.06)


def test_ortony_imbalance_equal_salience_contributes_zero():
    """Property equally salient in topic and vehicle contributes zero —
    that's the formula's whole point. If shared properties are *only*
    equally salient, the score collapses to 0."""
    pa = {1: 0.7, 2: 0.3}
    pb = {1: 0.7, 2: 0.3}
    # shared = {1, 2}; each term = pb × max(0, pb − pa) = pb × 0 = 0
    assert _ortony_imbalance(pa, pb) == 0.0


def test_ortony_imbalance_no_overlap_is_zero():
    assert _ortony_imbalance({1: 1.0, 2: 1.0}, {3: 1.0, 4: 1.0}) == 0.0


def test_ortony_imbalance_is_asymmetric():
    """Swapping (pa, pb) changes both the subtraction direction and the
    normaliser, so the score must differ for asymmetric inputs."""
    pa = {1: 0.1, 2: 0.0}
    pb = {1: 0.9, 2: 0.5}
    forward = _ortony_imbalance(pa, pb)
    backward = _ortony_imbalance(pb, pa)
    assert forward != backward
    # Forward: shared = {1, 2}
    #   term1 = 0.9 × max(0, 0.9 − 0.1) = 0.9 × 0.8 = 0.72
    #   term2 = 0.5 × max(0, 0.5 − 0.0) = 0.5 × 0.5 = 0.25
    #   denom = 0.81 + 0.25 = 1.06
    #   forward = 0.97 / 1.06
    assert forward == pytest.approx(0.97 / 1.06)
    # Backward: pa'={1:0.9, 2:0.5}, pb'={1:0.1, 2:0.0}
    #   term1 = 0.1 × max(0, 0.1 − 0.9) = 0.1 × 0 = 0
    #   term2 = 0.0 × max(0, 0.0 − 0.5) = 0.0 × 0 = 0
    #   backward = 0 / (0.01 + 0.0) = 0.0
    assert backward == 0.0


def test_ortony_imbalance_topic_dominates_returns_zero():
    """When the topic is uniformly MORE salient on every shared cluster,
    every max(0, pb − pa) clamps to 0 → score is 0."""
    pa = {1: 0.9, 2: 0.8}
    pb = {1: 0.1, 2: 0.05}
    # Every shared term clamps to 0
    assert _ortony_imbalance(pa, pb) == 0.0


def test_ortony_imbalance_in_unit_interval():
    """Bounded [0, 1]: the maximum is achieved when every vehicle cluster
    is shared, pa[c]=0 on every shared cluster — then numerator = Σ pb[c]²
    = denominator → score = 1.0."""
    pa = {1: 0.0, 2: 0.0}
    pb = {1: 0.9, 2: 0.5}
    # shared = {1, 2}, terms = pb² each, denom = Σ pb², ratio = 1.0
    assert _ortony_imbalance(pa, pb) == pytest.approx(1.0)


def test_ortony_imbalance_zero_vehicle_mass_returns_zero():
    """All-zero vehicle saliences → squared-mass denominator is 0 → score
    0.0 (not NaN). Mirrors the zero-norm guard on the sibling formulas."""
    assert _ortony_imbalance({1: 1.0}, {1: 0.0, 2: 0.0}) == 0.0
    assert _ortony_imbalance({}, {}) == 0.0


# --- random_uniform null control --------------------------------------------

def test_random_uniform_registered_in_scoring_fns():
    """Slice S03 contract: random_uniform is exposed alongside the S02 trio."""
    assert "random_uniform" in SCORING_FNS
    assert SCORING_FNS["random_uniform"] is _random_uniform


def test_random_uniform_returns_float_in_unit_interval():
    pa = {1: 0.9, 2: 0.6}
    pb = {1: 0.85, 3: 0.7}
    score = _random_uniform(pa, pb)
    assert isinstance(score, float)
    assert 0.0 <= score < 1.0


def test_random_uniform_is_deterministic():
    """Same inputs must yield the same float across calls (and processes)."""
    pa = {1: 0.9, 2: 0.6}
    pb = {1: 0.85, 3: 0.7}
    first = _random_uniform(pa, pb)
    second = _random_uniform(pa, pb)
    assert first == second


def test_random_uniform_is_order_symmetric():
    """score(pa, pb) == score(pb, pa) — sort the union, don't concatenate."""
    pa = {1: 0.9, 2: 0.6}
    pb = {1: 0.85, 3: 0.7}
    assert _random_uniform(pa, pb) == _random_uniform(pb, pa)


def test_random_uniform_ignores_salience_values():
    """Score depends only on the union of cluster_ids — saliences are noise.

    Reinforces the null-control intent: same cluster topology ⇒ same score
    regardless of weighting.
    """
    pa = {1: 0.9, 2: 0.6}
    pb = {1: 0.001, 2: 0.001}
    pa_alt = {1: 0.1, 2: 0.99}
    pb_alt = {1: 0.5, 2: 0.5}
    assert _random_uniform(pa, pb) == _random_uniform(pa_alt, pb_alt)


def test_random_uniform_distinct_pairs_yield_distinct_scores():
    """Two clearly different (pa, pb) pairs produce different scores
    (with overwhelming probability — 64-bit blake2b digest collision is
    cryptographically negligible)."""
    pair1_a, pair1_b = {1: 1.0}, {2: 1.0}        # union = {1, 2}
    pair2_a, pair2_b = {3: 1.0}, {4: 1.0}        # union = {3, 4}
    pair3_a, pair3_b = {1: 1.0, 2: 1.0}, {5: 1.0}  # union = {1, 2, 5}
    s1 = _random_uniform(pair1_a, pair1_b)
    s2 = _random_uniform(pair2_a, pair2_b)
    s3 = _random_uniform(pair3_a, pair3_b)
    assert s1 != s2
    assert s1 != s3
    assert s2 != s3


def test_score_pair_with_random_uniform_is_scored_status():
    """Status invariant: with non-empty pa & pb the result is 'scored',
    never accidentally 'no_properties'."""
    conn = _build_fixture_db()
    result = score_pair(conn, "anger", "fire", scoring_fn=_random_uniform)
    assert result.status == "scored"
    assert result.score is not None
    assert 0.0 <= result.score < 1.0


def test_score_pair_with_random_uniform_no_overlap_still_scored():
    """approach (cluster 4) and coming (cluster 5) share no clusters but both
    have curated properties — under random_uniform this is still 'scored'
    (a real outcome on the union {4, 5}), not a 0.0 forced by overlap logic.
    """
    conn = _build_fixture_db()
    result = score_pair(conn, "approach", "coming", scoring_fn=_random_uniform)
    assert result.status == "scored"
    assert result.score is not None
    assert 0.0 <= result.score < 1.0


def test_evaluate_dispatches_random_uniform(tmp_path):
    """evaluate(scoring='random_uniform') runs end-to-end and records the
    name in config."""
    conn = _build_fixture_db()
    pairs_file, controls_file = _write_fixture_files(tmp_path)
    result = evaluate(
        conn=conn,
        pairs_file=str(pairs_file),
        controls_file=str(controls_file),
        scoring="random_uniform",
    )
    assert result["config"]["scoring"] == "random_uniform"
    # The single apt pair is anger/fire — both resolve and have properties,
    # so it must contribute a scored entry, not unresolved/no_properties.
    assert result["aggregate"]["n_apt"] == 1
    assert result["aggregate"]["apt_no_properties"] == 0


def test_main_cli_dispatch_random_uniform(tmp_path, monkeypatch):
    """CLI: --scoring random_uniform writes the chosen name into the output."""
    pairs_file = tmp_path / "pairs.json"
    pairs_file.write_text(json.dumps([
        {"source": "anger", "target": "fire", "tier": "strong"},
    ]))
    controls_file = tmp_path / "controls.jsonl"
    controls_file.write_text(
        '{"target": "approach", "paraphrase": "coming", "label": "inapt"}\n'
    )
    fake_db = tmp_path / "fake.db"
    fake_db.write_bytes(b"")
    output_file = tmp_path / "out.json"

    fixture_conn = _build_fixture_db()
    monkeypatch.setattr(
        evaluate_aptness.sqlite3, "connect", lambda *a, **kw: fixture_conn,
    )
    monkeypatch.setattr(sys, "argv", [
        "evaluate_aptness.py",
        "--pairs", str(pairs_file),
        "--controls", str(controls_file),
        "--db", str(fake_db),
        "--scoring", "random_uniform",
        "--output", str(output_file),
    ])

    evaluate_aptness.main()

    written = json.loads(output_file.read_text())
    assert written["config"]["scoring"] == "random_uniform"


def test_score_pair_dispatches_to_chosen_scoring_fn():
    """score_pair must use the supplied scoring_fn, not just the default."""
    conn = _build_fixture_db()
    salience = score_pair(conn, "anger", "fire", scoring_fn=_jaccard_salience)
    raw = score_pair(conn, "anger", "fire", scoring_fn=_jaccard_raw)
    cosine = score_pair(conn, "anger", "fire", scoring_fn=_cosine_salience)

    # All three must be 'scored' for this overlap-bearing pair
    assert salience.status == raw.status == cosine.status == "scored"
    # The three formulas yield distinct scores on the asymmetric fixture
    # (anger has salience {1:0.9, 2:0.6}, fire has {1:0.85, 3:0.7})
    assert salience.score != raw.score
    assert salience.score != cosine.score


def test_score_pair_default_scoring_matches_jaccard_salience():
    """Backwards compatibility: omitting scoring_fn must reproduce the old
    salience-weighted Jaccard score exactly."""
    conn = _build_fixture_db()
    default = score_pair(conn, "anger", "fire")
    explicit = score_pair(conn, "anger", "fire", scoring_fn=_jaccard_salience)
    assert default.score == explicit.score


def test_score_pair_status_unchanged_across_scoring_formulas():
    """Status semantics (unresolved / no_properties) must be invariant —
    coverage gaps stay coverage gaps regardless of scoring formula."""
    conn = _build_fixture_db()
    for fn in SCORING_FNS.values():
        assert score_pair(conn, "zzznotaword", "fire", scoring_fn=fn).status == "unresolved"
        assert score_pair(conn, "anger", "orphan", scoring_fn=fn).status == "no_properties"


# --- evaluate() with scoring parameter ---------------------------------------

def _write_fixture_files(tmp_path):
    pairs_file = tmp_path / "pairs.json"
    pairs_file.write_text(json.dumps([
        {"source": "anger", "target": "fire", "tier": "strong"},
    ]))
    controls_file = tmp_path / "controls.jsonl"
    controls_file.write_text(
        '{"target": "approach", "paraphrase": "coming", "label": "inapt"}\n'
    )
    return pairs_file, controls_file


def test_evaluate_records_scoring_name_in_config(tmp_path):
    conn = _build_fixture_db()
    pairs_file, controls_file = _write_fixture_files(tmp_path)
    result = evaluate(
        conn=conn,
        pairs_file=str(pairs_file),
        controls_file=str(controls_file),
        scoring="jaccard_raw",
    )
    assert result["config"]["scoring"] == "jaccard_raw"


def test_evaluate_default_scoring_is_jaccard_salience(tmp_path):
    """Omitting scoring= must keep the historic default."""
    conn = _build_fixture_db()
    pairs_file, controls_file = _write_fixture_files(tmp_path)
    result = evaluate(
        conn=conn,
        pairs_file=str(pairs_file),
        controls_file=str(controls_file),
    )
    assert result["config"]["scoring"] == "jaccard_salience"


def test_evaluate_rejects_unknown_scoring_name(tmp_path):
    """Typo in a sweep config must fail fast, not silently fall back."""
    conn = _build_fixture_db()
    pairs_file, controls_file = _write_fixture_files(tmp_path)
    with pytest.raises(ValueError, match="Unknown scoring name"):
        evaluate(
            conn=conn,
            pairs_file=str(pairs_file),
            controls_file=str(controls_file),
            scoring="not_a_real_formula",
        )


def test_evaluate_different_scorings_produce_different_results(tmp_path):
    """Sanity: swapping scoring formula visibly changes the outputs."""
    conn = _build_fixture_db()
    pairs_file, controls_file = _write_fixture_files(tmp_path)

    salience = evaluate(
        conn=conn,
        pairs_file=str(pairs_file),
        controls_file=str(controls_file),
        scoring="jaccard_salience",
    )
    cosine = evaluate(
        conn=conn,
        pairs_file=str(pairs_file),
        controls_file=str(controls_file),
        scoring="cosine_salience",
    )
    assert salience["config"]["scoring"] != cosine["config"]["scoring"]
    # mean_apt_score should differ since the formulas score differently
    assert (
        salience["aggregate"]["mean_apt_score"]
        != cosine["aggregate"]["mean_apt_score"]
    )


# --- CLI dispatch ------------------------------------------------------------

def test_main_cli_dispatch_writes_scoring_to_output(tmp_path, monkeypatch, capsys):
    """End-to-end: invoke main() with --scoring and assert the JSON written
    to --output records the chosen scoring name in config.

    Uses the in-memory fixture DB by monkeypatching sqlite3.connect — the
    real on-disk DB would slow the test and is unnecessary for verifying
    CLI dispatch.
    """
    pairs_file = tmp_path / "pairs.json"
    pairs_file.write_text(json.dumps([
        {"source": "anger", "target": "fire", "tier": "strong"},
    ]))
    controls_file = tmp_path / "controls.jsonl"
    controls_file.write_text(
        '{"target": "approach", "paraphrase": "coming", "label": "inapt"}\n'
    )
    fake_db = tmp_path / "fake.db"
    fake_db.write_bytes(b"")  # passes the is_file() existence check
    output_file = tmp_path / "out.json"

    fixture_conn = _build_fixture_db()
    monkeypatch.setattr(
        evaluate_aptness.sqlite3, "connect", lambda *a, **kw: fixture_conn,
    )

    monkeypatch.setattr(sys, "argv", [
        "evaluate_aptness.py",
        "--pairs", str(pairs_file),
        "--controls", str(controls_file),
        "--db", str(fake_db),
        "--scoring", "jaccard_raw",
        "--output", str(output_file),
    ])

    evaluate_aptness.main()

    assert output_file.exists()
    written = json.loads(output_file.read_text())
    assert written["config"]["scoring"] == "jaccard_raw"


def test_main_cli_rejects_unregistered_scoring(tmp_path, monkeypatch):
    """argparse `choices=` must reject an unknown --scoring value before
    any DB work happens."""
    fake_db = tmp_path / "fake.db"
    fake_db.write_bytes(b"")
    monkeypatch.setattr(sys, "argv", [
        "evaluate_aptness.py",
        "--db", str(fake_db),
        "--scoring", "not_a_real_formula",
    ])
    with pytest.raises(SystemExit):
        evaluate_aptness.main()


# --- ScoringFn contract ------------------------------------------------------

def test_scoring_fn_alias_uses_mapping_not_dict():
    """ScoringFn must accept any Mapping[int, float], not just dict.

    Module docstring promises Mapping inputs — the alias should match so
    a custom scoring fn typed as ``Mapping[int, float]`` is assignable to
    ``ScoringFn`` and can be registered + dispatched via the public API.
    """
    import typing
    from collections.abc import Mapping

    # Inspect the alias args. Callable aliases stringify args, so check
    # via typing.get_args — the parameter types should be Mapping-based.
    args = typing.get_args(evaluate_aptness.ScoringFn)
    # Callable[[A, B], R] → get_args returns ([A, B], R)
    assert args, "ScoringFn alias has no resolvable args"
    param_types = args[0]
    for pt in param_types:
        origin = typing.get_origin(pt)
        # Must be a subtype of collections.abc.Mapping (not dict).
        assert origin is Mapping, (
            f"ScoringFn parameter origin must be Mapping, got {origin!r}"
        )


def test_custom_mapping_typed_scoring_fn_dispatches_via_public_api():
    """A scoring fn typed as Mapping[int, float] must register + dispatch."""
    from collections.abc import Mapping

    def _mean_min_score(
        pa: Mapping[int, float], pb: Mapping[int, float],
    ) -> float:
        shared = set(pa) & set(pb)
        if not shared:
            return 0.0
        return sum(min(pa[c], pb[c]) for c in shared) / len(shared)

    SCORING_FNS["_test_mean_min"] = _mean_min_score
    try:
        conn = _build_fixture_db()
        try:
            result = score_pair(
                conn, "anger", "fire",
                scoring_fn=SCORING_FNS["_test_mean_min"],
            )
        finally:
            conn.close()
        assert result.status == "scored"
        assert result.score is not None
        assert 0.0 <= result.score <= 1.0
    finally:
        SCORING_FNS.pop("_test_mean_min", None)
