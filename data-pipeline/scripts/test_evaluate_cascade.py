"""Tests for evaluate_cascade.py — M03 cascade evaluator.

S01 scope: concreteness gate + Ortony rank composition only.
Domain-distance re-rank stage is intentionally not exercised here —
that lands in S02 with its own test module-extension or sibling tests.

Fixture DB mirrors the schema slice the cascade actually reads:
synset_properties_curated, property_vocab_curated, lemmas (for the
existing scoring path) plus synset_concreteness (M03's new input).
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from evaluate_cascade import (
    CascadeConfig,
    CascadeResult,
    evaluate_cascade_pair,
    evaluate_cohort,
)


# --- Fixture DB --------------------------------------------------------------

def _build_fixture_db() -> sqlite3.Connection:
    """Build a tiny in-memory DB carrying the schema slice the cascade reads.

    Mirrors test_evaluate_aptness's fixture and adds synset_concreteness.
    Synset-id naming convention here:
      * S_TOPIC_*   = abstract concepts (low concreteness, ~2.0)
      * S_VEHICLE_* = concrete things (high concreteness, ~4.5)
      * S_NOPROPS   = a synset with no curated properties (for the no-properties path)
      * S_NOCONC    = a synset missing from synset_concreteness (fail-closed path)
    """
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
        CREATE TABLE synset_concreteness (
            synset_id TEXT PRIMARY KEY,
            score     REAL NOT NULL,
            source    TEXT NOT NULL
        );
    """)

    conn.executescript("""
        INSERT INTO lemmas VALUES
            ('anger',   'S_TOPIC_ANGER'),
            ('fire',    'S_VEHICLE_FIRE'),
            ('hope',    'S_TOPIC_HOPE'),
            ('light',   'S_VEHICLE_LIGHT'),
            ('grief',   'S_TOPIC_GRIEF'),
            ('similar', 'S_TOPIC_SIMILAR'),
            ('alike',   'S_TOPIC_ALIKE'),
            ('orphan',  'S_NOPROPS'),
            ('noconc',  'S_NOCONC');
        INSERT INTO property_vocab_curated VALUES
            (1, 'S_TOPIC_ANGER',    'anger',    'n', 1),
            (2, 'S_VEHICLE_FIRE',   'fire',     'n', 1),
            (3, 'S_TOPIC_HOPE',     'hope',     'n', 1),
            (4, 'S_VEHICLE_LIGHT',  'light',    'n', 1),
            (5, 'S_TOPIC_GRIEF',    'grief',    'n', 1),
            (6, 'S_TOPIC_SIMILAR',  'similar',  'a', 1),
            (7, 'S_TOPIC_ALIKE',    'alike',    'a', 1),
            (8, 'S_NOCONC',         'noconc',   'n', 1);
        INSERT INTO synset_properties_curated VALUES
            ('S_TOPIC_ANGER',   1, 1, 'exact', 1.0, 0.9),
            ('S_TOPIC_ANGER',   1, 2, 'exact', 1.0, 0.6),
            ('S_VEHICLE_FIRE',  2, 1, 'exact', 1.0, 0.85),
            ('S_VEHICLE_FIRE',  2, 3, 'exact', 1.0, 0.7),
            ('S_TOPIC_HOPE',    3, 4, 'exact', 1.0, 0.5),
            ('S_VEHICLE_LIGHT', 4, 4, 'exact', 1.0, 0.6),
            ('S_VEHICLE_LIGHT', 4, 5, 'exact', 1.0, 0.4),
            ('S_TOPIC_GRIEF',   5, 6, 'exact', 1.0, 0.7),
            ('S_TOPIC_SIMILAR', 6, 7, 'exact', 1.0, 0.5),
            ('S_TOPIC_ALIKE',   7, 7, 'exact', 1.0, 0.5),
            ('S_NOCONC',        8, 8, 'exact', 1.0, 0.5);
        INSERT INTO synset_concreteness (synset_id, score, source) VALUES
            ('S_TOPIC_ANGER',    2.0, 'brysbaert'),
            ('S_VEHICLE_FIRE',   4.5, 'brysbaert'),
            ('S_TOPIC_HOPE',     1.8, 'brysbaert'),
            ('S_VEHICLE_LIGHT',  4.2, 'fasttext_regression'),
            ('S_TOPIC_GRIEF',    1.5, 'brysbaert'),
            ('S_TOPIC_SIMILAR',  2.0, 'brysbaert'),
            ('S_TOPIC_ALIKE',    2.1, 'brysbaert'),
            ('S_NOPROPS',        3.0, 'brysbaert');
            -- S_NOCONC intentionally absent from synset_concreteness
    """)
    conn.commit()
    return conn


# --- Config defaults ---------------------------------------------------------

def test_cascade_config_defaults_match_preflight_findings():
    """Defaults must align with the M03 pre-flight diagnostic conclusions.

    See docs/roadmap/M03-S01-preflight-findings.md — apt-cohort signed
    delta median is +2.03, so a default threshold around the lower end
    of the sweep range (1.0) is reasonable. Default ortony scoring is
    the M02 symmetric reference (jaccard_salience). Composition is
    multiplicative (the roadmap default).
    """
    cfg = CascadeConfig()
    assert cfg.concreteness_threshold == 1.0
    assert cfg.ortony_scoring == "jaccard_salience"
    assert cfg.composition == "multiplicative"


# --- CascadeConfig __post_init__ validation ---------------------------------

def test_cascade_config_rejects_invalid_composition():
    with pytest.raises(ValueError, match="composition must be"):
        CascadeConfig(composition="bogus")


def test_cascade_config_rejects_invalid_ortony_scoring():
    with pytest.raises(ValueError, match="not in SCORING_FNS"):
        CascadeConfig(ortony_scoring="bogus")


def test_cascade_config_rejects_nonpositive_d_cap():
    with pytest.raises(ValueError, match="d_cap must be > 0"):
        CascadeConfig(d_cap=0.0)
    with pytest.raises(ValueError, match="d_cap must be > 0"):
        CascadeConfig(d_cap=-0.5)


def test_cascade_config_rejects_negative_alpha():
    with pytest.raises(ValueError, match="alpha must be >= 0"):
        CascadeConfig(alpha=-0.1)


# --- Concreteness gate behaviour ---------------------------------------------

def test_gate_passes_when_vehicle_more_concrete_than_topic_above_threshold():
    """anger (2.0) → fire (4.5): delta = +2.5, default threshold = 1.0 → pass."""
    conn = _build_fixture_db()
    result = evaluate_cascade_pair(
        conn, "S_TOPIC_ANGER", "S_VEHICLE_FIRE", CascadeConfig(),
    )
    assert result.gate_passed is True
    assert result.status == "scored"
    assert result.ortony_score is not None and result.ortony_score > 0.0


def test_gate_drops_when_signed_delta_below_threshold():
    """anger (2.0) → similar (2.0): delta = 0.0, default threshold = 1.0 → drop.

    'similar' as a vehicle would fail the directionality test even though
    it shares lemma type — this is the inapt-cohort-style behaviour.
    """
    conn = _build_fixture_db()
    result = evaluate_cascade_pair(
        conn, "S_TOPIC_ANGER", "S_TOPIC_SIMILAR", CascadeConfig(),
    )
    assert result.gate_passed is False
    assert result.status == "gate_dropped"
    assert result.final_score == 0.0
    # Ortony score never computed on dropped pairs.
    assert result.ortony_score is None


def test_gate_drops_when_vehicle_is_LESS_concrete_than_topic():
    """fire (4.5) → anger (2.0): delta = -2.5, threshold = 1.0 → drop.

    Critical regression: the gate must be SIGNED, not absolute. An
    abs(Δ) gate would PASS this pair. Lakoff #1 says the asymmetry
    is directional — vehicle must be more concrete than topic.
    """
    conn = _build_fixture_db()
    result = evaluate_cascade_pair(
        conn, "S_VEHICLE_FIRE", "S_TOPIC_ANGER", CascadeConfig(),
    )
    assert result.gate_passed is False, (
        "signed gate must reject vehicle-less-concrete-than-topic; "
        "an absolute-delta gate would let this through"
    )
    assert result.status == "gate_dropped"


def test_no_gate_when_threshold_is_negative_infinity():
    """threshold = -inf reduces to no gate — every pair with both
    concreteness scores passes through, even reverse-direction ones."""
    import math
    conn = _build_fixture_db()
    cfg = CascadeConfig(concreteness_threshold=-math.inf)
    result = evaluate_cascade_pair(
        conn, "S_VEHICLE_FIRE", "S_TOPIC_ANGER", cfg,
    )
    assert result.gate_passed is True, (
        "threshold=-inf must reduce to no-gate baseline so we can A/B "
        "cascade-vs-M02 cleanly"
    )
    assert result.status == "scored"


def test_gate_threshold_boundary_is_inclusive():
    """delta == threshold should PASS (inclusive comparison).

    Pre-flight findings used >= for the gate predicate; keep that
    contract so a swept threshold at the exact apt-median doesn't
    half-include half-exclude pairs at that exact value.
    """
    conn = _build_fixture_db()
    cfg = CascadeConfig(concreteness_threshold=2.5)
    # delta = 4.5 - 2.0 = 2.5 exactly
    result = evaluate_cascade_pair(
        conn, "S_TOPIC_ANGER", "S_VEHICLE_FIRE", cfg,
    )
    assert result.gate_passed is True


# --- Missing-concreteness fail-closed ---------------------------------------

def test_missing_concreteness_on_topic_fails_closed():
    """Topic missing from synset_concreteness → gate must reject.

    Fail-closed because the gate cannot prove the direction holds
    without both scores. The roadmap allows the rebuild stage to
    backfill imputed scores later, but until both are present the
    cascade cannot make the Lakoff judgement.
    """
    conn = _build_fixture_db()
    result = evaluate_cascade_pair(
        conn, "S_NOCONC", "S_VEHICLE_FIRE", CascadeConfig(),
    )
    assert result.gate_passed is False
    assert result.status == "missing_concreteness"
    assert result.final_score is None


def test_missing_concreteness_on_vehicle_fails_closed():
    conn = _build_fixture_db()
    result = evaluate_cascade_pair(
        conn, "S_TOPIC_ANGER", "S_NOCONC", CascadeConfig(),
    )
    assert result.gate_passed is False
    assert result.status == "missing_concreteness"
    assert result.final_score is None


# --- Post-gate Ortony scoring ------------------------------------------------

def test_post_gate_no_properties_yields_no_properties_status():
    """Gate passes but vehicle has no properties → no Ortony score possible.

    Distinct from gate_dropped: the gate let it through, the scoring
    stage couldn't run. Operators triaging cohort attrition need to
    distinguish these two reasons.
    """
    conn = _build_fixture_db()
    # Synth a row that passes the gate but has no curated properties.
    # S_NOPROPS has concreteness=3.0; pair with S_TOPIC_GRIEF (1.5) →
    # delta = +1.5 ≥ 1.0 default → gate passes.
    result = evaluate_cascade_pair(
        conn, "S_TOPIC_GRIEF", "S_NOPROPS", CascadeConfig(),
    )
    assert result.gate_passed is True
    assert result.status == "no_properties"
    assert result.ortony_score is None
    assert result.final_score is None


def test_post_gate_uses_configured_ortony_scoring_fn():
    """The cascade must honour CascadeConfig.ortony_scoring — wired
    through to the existing M02 SCORING_FNS registry. Default is
    jaccard_salience; jaccard_raw is the unweighted control.
    """
    conn = _build_fixture_db()
    salience = evaluate_cascade_pair(
        conn, "S_TOPIC_ANGER", "S_VEHICLE_FIRE",
        CascadeConfig(ortony_scoring="jaccard_salience"),
    )
    raw = evaluate_cascade_pair(
        conn, "S_TOPIC_ANGER", "S_VEHICLE_FIRE",
        CascadeConfig(ortony_scoring="jaccard_raw"),
    )
    # The two scoring functions produce different scores on overlapping
    # property sets (proof that the choice is being honoured).
    assert salience.ortony_score is not None
    assert raw.ortony_score is not None
    assert salience.ortony_score != raw.ortony_score


def test_post_gate_unknown_ortony_scoring_raises_valueerror():
    """Fail fast on typos in sweep configs — same contract as
    evaluate_aptness.evaluate, which raises with the registered list.
    Construction-time __post_init__ catches this before any DB work."""
    with pytest.raises(ValueError, match="not in SCORING_FNS"):
        CascadeConfig(ortony_scoring="not_a_real_scoring_fn")


# --- Result-shape contract ---------------------------------------------------

def test_cascade_result_carries_diagnostic_fields():
    """CascadeResult must expose ortony_score, gate_passed, and the
    cosine_distance/re_rank_bonus fields (the latter two are populated
    in S02; in S01 they're explicitly None). Without these slots, the
    sweep harness can't surface ablation slices in a single run.
    """
    conn = _build_fixture_db()
    result = evaluate_cascade_pair(
        conn, "S_TOPIC_ANGER", "S_VEHICLE_FIRE", CascadeConfig(),
    )
    assert hasattr(result, "final_score")
    assert hasattr(result, "gate_passed")
    assert hasattr(result, "ortony_score")
    assert hasattr(result, "cosine_distance")
    assert hasattr(result, "re_rank_bonus")
    assert hasattr(result, "status")


def test_s01_scope_re_rank_fields_none_when_centroids_missing():
    """When neither synset has a centroid, the re-rank stage fails open:
    cosine_distance is None, re_rank_bonus is None, and final_score
    falls back to the Ortony score with no multiplier applied.

    Fail-open is the documented behaviour from the pre-flight findings —
    on the pre-purge DB only 18-19% of cohort pairs have both centroids,
    so failing closed would gut the cascade's reach.
    """
    conn = _build_fixture_db()
    # The fixture DB doesn't carry synset_centroids — exercising the
    # missing-centroid path on both sides.
    result = evaluate_cascade_pair(
        conn, "S_TOPIC_ANGER", "S_VEHICLE_FIRE", CascadeConfig(),
    )
    assert result.cosine_distance is None
    assert result.re_rank_bonus is None
    assert result.final_score == result.ortony_score


# --- S02: domain-distance re-rank --------------------------------------------

def _build_fixture_db_with_centroids() -> sqlite3.Connection:
    """Extension of the S01 fixture with synset_centroids populated.

    Centroids are stored as packed float32 BLOBs of dim 300 in the real
    DB (FastText embedding dim). Tests use a smaller dim (3) — the
    cascade's cosine_distance computation reads the BLOB length and
    decodes accordingly, so any consistent dim works for the contract.
    Pairwise cosine distances are chosen so the test cases have
    legible numbers (orthogonal vectors → distance 1.0; identical →
    distance 0.0; aligned at 60° → cos = 0.5 → distance 0.5).
    """
    import struct
    conn = _build_fixture_db()
    conn.executescript("""
        CREATE TABLE synset_centroids (
            synset_id      TEXT PRIMARY KEY,
            centroid       BLOB NOT NULL,
            property_count INTEGER NOT NULL
        );
    """)

    def _blob(vec):
        return struct.pack(f"{len(vec)}f", *vec)

    # Pairwise distances we care about:
    #   ANGER vs FIRE       — orthogonal (d=1.0)            — apt-like far
    #   HOPE  vs LIGHT      — identical direction (d=0.0)   — degenerate close
    #   GRIEF vs SIMILAR    — 60° (d=0.5)                   — mid-band
    #   ALIKE has no centroid (missing-centroid path)
    rows = [
        ("S_TOPIC_ANGER",    [1.0, 0.0, 0.0], 5),
        ("S_VEHICLE_FIRE",   [0.0, 1.0, 0.0], 5),
        ("S_TOPIC_HOPE",     [1.0, 0.0, 0.0], 5),
        ("S_VEHICLE_LIGHT",  [1.0, 0.0, 0.0], 5),
        ("S_TOPIC_GRIEF",    [1.0, 0.0, 0.0], 5),
        ("S_TOPIC_SIMILAR",  [0.5, 0.866, 0.0], 5),
        # S_TOPIC_ALIKE intentionally absent — fail-open path
        ("S_NOPROPS",        [0.7, 0.7, 0.0], 5),
        ("S_NOCONC",         [0.0, 0.0, 1.0], 5),
    ]
    conn.executemany(
        "INSERT INTO synset_centroids (synset_id, centroid, property_count) VALUES (?, ?, ?)",
        [(sid, _blob(vec), n) for sid, vec, n in rows],
    )
    conn.commit()
    return conn


def test_re_rank_computes_cosine_distance_when_both_centroids_present():
    """anger ⊥ fire → cosine_distance = 1.0 (orthogonal vectors).

    The pair's centroids point along x and y axes respectively. The
    cascade must decode the BLOBs, compute 1 - dot/(|a|·|b|), and
    surface the distance in CascadeResult.cosine_distance.
    """
    conn = _build_fixture_db_with_centroids()
    result = evaluate_cascade_pair(
        conn, "S_TOPIC_ANGER", "S_VEHICLE_FIRE", CascadeConfig(),
    )
    assert result.cosine_distance is not None
    assert abs(result.cosine_distance - 1.0) < 1e-5


def test_re_rank_bonus_saturates_at_d_cap():
    """When d >= d_cap, re_rank_bonus must saturate at 1.0 (not exceed).

    The monotonic-up-to-cap shape gives bonus = clip(d / d_cap, 0, 1).
    A pair with d=1.0 against d_cap=0.5 produces ratio 2.0 → clip 1.0.
    """
    conn = _build_fixture_db_with_centroids()
    cfg = CascadeConfig(d_cap=0.5)
    result = evaluate_cascade_pair(
        conn, "S_TOPIC_ANGER", "S_VEHICLE_FIRE", cfg,
    )
    assert result.re_rank_bonus == 1.0


def test_re_rank_bonus_linearly_below_cap():
    """d=0.5, d_cap=1.0 → bonus = 0.5. Linear ramp up to cap."""
    from dataclasses import replace
    conn = _build_fixture_db_with_centroids()
    # S_TOPIC_GRIEF (1.5) vs S_TOPIC_SIMILAR (2.0) — concreteness delta = 0.5
    # which is below default threshold 1.0; lower threshold so the gate
    # passes and we get to the re-rank stage.
    cfg = replace(CascadeConfig(d_cap=1.0), concreteness_threshold=0.0)
    result = evaluate_cascade_pair(
        conn, "S_TOPIC_GRIEF", "S_TOPIC_SIMILAR", cfg,
    )
    assert result.cosine_distance is not None
    assert abs(result.cosine_distance - 0.5) < 1e-3
    assert result.re_rank_bonus is not None
    assert abs(result.re_rank_bonus - 0.5) < 1e-3


def test_re_rank_bonus_is_zero_when_distance_is_zero():
    """Identical-direction centroids → distance 0 → bonus 0.

    hope and light have identical centroid vectors in the fixture
    (both [1,0,0]). Distance = 0. The re_rank reward should give
    these pairs no bonus — they're too-close (degenerate).
    """
    conn = _build_fixture_db_with_centroids()
    # Lower threshold so hope (1.8) vs light (4.2) gate passes (delta = 2.4).
    result = evaluate_cascade_pair(
        conn, "S_TOPIC_HOPE", "S_VEHICLE_LIGHT", CascadeConfig(),
    )
    assert result.cosine_distance is not None
    assert abs(result.cosine_distance) < 1e-5
    assert result.re_rank_bonus == 0.0


def test_re_rank_fail_open_when_either_centroid_missing():
    """One side missing from synset_centroids → re_rank_bonus = None,
    cosine_distance = None, final_score = ortony_score (no multiplier).

    Fail-open: the Ortony score still stands. Penalising lack of data
    would conflate algorithmic effect with coverage effect, and
    pre-flight showed 81-82% of cohort pairs land here on the
    pre-purge DB.
    """
    conn = _build_fixture_db_with_centroids()
    cfg = CascadeConfig(concreteness_threshold=0.0)  # let the gate through
    # S_TOPIC_ANGER has a centroid; S_TOPIC_ALIKE does not.
    result = evaluate_cascade_pair(
        conn, "S_TOPIC_ANGER", "S_TOPIC_ALIKE", cfg,
    )
    assert result.gate_passed is True
    assert result.cosine_distance is None
    assert result.re_rank_bonus is None
    # final_score falls back to ortony_score (or no_properties if there's no overlap).
    assert result.status in ("scored", "no_properties")
    if result.status == "scored":
        assert result.final_score == result.ortony_score


def test_re_rank_multiplicative_composition_lifts_score():
    """Multiplicative: final = ortony * (1 + alpha * bonus).

    With alpha=1.0 and bonus=1.0 (saturation), final should be 2 × ortony.
    """
    conn = _build_fixture_db_with_centroids()
    cfg = CascadeConfig(d_cap=0.5, alpha=1.0, composition="multiplicative")
    result = evaluate_cascade_pair(
        conn, "S_TOPIC_ANGER", "S_VEHICLE_FIRE", cfg,
    )
    assert result.ortony_score is not None
    assert result.final_score is not None
    expected = result.ortony_score * (1.0 + 1.0 * 1.0)  # bonus saturated at 1.0
    assert abs(result.final_score - expected) < 1e-6


def test_re_rank_additive_composition_lifts_score():
    """Additive: final = ortony + alpha * bonus.

    Same setup as the multiplicative test, but composition='additive'.
    With alpha=1.0 and bonus=1.0, final = ortony + 1.0.
    """
    conn = _build_fixture_db_with_centroids()
    cfg = CascadeConfig(d_cap=0.5, alpha=1.0, composition="additive")
    result = evaluate_cascade_pair(
        conn, "S_TOPIC_ANGER", "S_VEHICLE_FIRE", cfg,
    )
    assert result.ortony_score is not None
    assert result.final_score is not None
    expected = result.ortony_score + 1.0 * 1.0
    assert abs(result.final_score - expected) < 1e-6


def test_re_rank_alpha_zero_recovers_ortony_only():
    """alpha=0.0 → no re-rank effect. final_score equals ortony_score
    even when bonus is non-zero. Required for clean ablation —
    sweeping alpha=0 isolates the gate-only effect from gate+re-rank.
    """
    conn = _build_fixture_db_with_centroids()
    cfg = CascadeConfig(d_cap=0.5, alpha=0.0, composition="multiplicative")
    result = evaluate_cascade_pair(
        conn, "S_TOPIC_ANGER", "S_VEHICLE_FIRE", cfg,
    )
    assert result.ortony_score is not None
    assert abs(result.final_score - result.ortony_score) < 1e-6
    # bonus still computed for diagnostics — alpha just gates whether it lands.
    assert result.re_rank_bonus == 1.0


def test_re_rank_unknown_composition_raises_valueerror():
    """Same fail-fast contract as ortony_scoring — typo in config
    crashes immediately rather than silently picking a default.
    Construction-time __post_init__ catches this before any DB work."""
    with pytest.raises(ValueError, match="composition"):
        CascadeConfig(composition="not_a_real_mode")


def test_re_rank_skipped_when_gate_drops():
    """Gate-dropped pairs short-circuit before the re-rank stage —
    cosine_distance and re_rank_bonus stay None on dropped pairs.
    Saves the centroid BLOB decode on rejected pairs.
    """
    conn = _build_fixture_db_with_centroids()
    # similar vs anger — both abstract, no signed delta → gate drops.
    result = evaluate_cascade_pair(
        conn, "S_TOPIC_ANGER", "S_TOPIC_SIMILAR", CascadeConfig(),
    )
    assert result.gate_passed is False
    assert result.status == "gate_dropped"
    assert result.cosine_distance is None
    assert result.re_rank_bonus is None
    assert result.final_score == 0.0


# --- evaluate_cohort: cohort-level evaluation contract ---------------------

def _write_fixture_cohorts(tmp_path):
    """Stage tiny apt-pairs JSON + inapt-controls JSONL files.

    Apt: 2 pairs that should pass the gate (both topic→vehicle pairs
    have concrete vehicles, matching the fixture DB).
    Inapt: 2 pairs that should be gate-dropped (target/paraphrase both
    abstract; delta ≈ 0).
    Plus 1 inapt with an unresolved lemma (cohort-attrition counter).
    """
    import json as _json
    pairs_path = tmp_path / "apt.json"
    controls_path = tmp_path / "inapt.jsonl"
    pairs_path.write_text(_json.dumps([
        {"source": "anger", "target": "fire",  "tier": "strong", "domain": "emotion"},
        {"source": "hope",  "target": "light", "tier": "strong", "domain": "emotion"},
    ]))
    controls_path.write_text(
        '{"target": "similar", "paraphrase": "alike",  "label": "inapt"}\n'
        '{"target": "anger",   "paraphrase": "alike",  "label": "inapt"}\n'
        '{"target": "ghost",   "paraphrase": "phantom","label": "inapt"}\n'
    )
    return str(pairs_path), str(controls_path)


def test_cohort_counters_track_rerank_application(tmp_path):
    """Cohort counters must surface rerank_applied vs rerank_skipped so
    operators can spot the 3948dedf-class silent fail-open regression.

    Contract: rerank_applied + rerank_skipped == counters["scored"].
    """
    conn = _build_fixture_db_with_centroids()
    pairs, controls = _write_fixture_cohorts(tmp_path)
    result = evaluate_cohort(
        conn, pairs_file=pairs, controls_file=controls,
        config=CascadeConfig(), threshold_percentile=95.0,
        db_path=":memory:",
    )
    agg = result["aggregate"]
    # Schema contract: counters present at aggregate level.
    assert "apt_rerank_applied" in agg
    assert "apt_rerank_skipped" in agg
    assert "inapt_rerank_applied" in agg
    assert "inapt_rerank_skipped" in agg
    # Conservation: applied + skipped == scored, per cohort.
    assert agg["apt_rerank_applied"] + agg["apt_rerank_skipped"] == agg["apt_scored"]
    assert agg["inapt_rerank_applied"] + agg["inapt_rerank_skipped"] == agg["inapt_scored"]


def test_evaluate_cohort_returns_shape_matching_evaluate_aptness(tmp_path):
    """The cohort result must carry the same top-level keys as
    evaluate_aptness.evaluate so the sweep harness can consume both
    evaluators through a single result-shape pathway.
    """
    conn = _build_fixture_db_with_centroids()
    pairs, controls = _write_fixture_cohorts(tmp_path)
    result = evaluate_cohort(
        conn, pairs_file=pairs, controls_file=controls,
        config=CascadeConfig(), threshold_percentile=95.0,
        db_path=":memory:",
    )
    # Shape parity with evaluate_aptness.evaluate
    assert "aptness_rate" in result
    assert "false_positive_rate" in result
    assert "separation_score" in result
    assert "aggregate" in result
    assert "per_pair_scores" in result
    assert "config" in result
    # Cascade-specific stats: ablation slices must be available.
    agg = result["aggregate"]
    assert "n_apt" in agg
    assert "n_inapt" in agg
    assert "apt_gate_dropped" in agg
    assert "inapt_gate_dropped" in agg
    assert "apt_missing_concreteness" in agg
    assert "inapt_missing_concreteness" in agg


def test_evaluate_cohort_routes_apt_pairs_through_gate(tmp_path):
    """Apt-cohort pairs are (source=topic, target=vehicle) — the cascade
    must use them in that order (vehicle as second arg) so the signed
    gate predicate gets the directionality right.
    """
    conn = _build_fixture_db_with_centroids()
    pairs, controls = _write_fixture_cohorts(tmp_path)
    result = evaluate_cohort(
        conn, pairs_file=pairs, controls_file=controls,
        config=CascadeConfig(), threshold_percentile=95.0,
        db_path=":memory:",
    )
    # Both apt pairs in the fixture have concrete vehicles → should pass
    # the gate. None should be gate-dropped.
    assert result["aggregate"]["apt_gate_dropped"] == 0


def test_evaluate_cohort_drops_inapt_at_the_gate(tmp_path):
    """Inapt-cohort pairs are (target, paraphrase) — both abstract
    lemmas in the fixture. The signed gate should reject them. (Anger
    vs alike: both have concreteness ≈ 2.0 in the fixture.)
    """
    conn = _build_fixture_db_with_centroids()
    pairs, controls = _write_fixture_cohorts(tmp_path)
    result = evaluate_cohort(
        conn, pairs_file=pairs, controls_file=controls,
        config=CascadeConfig(), threshold_percentile=95.0,
        db_path=":memory:",
    )
    # 'similar'+'alike' (both ≈2.0), 'anger'+'alike' (2.0/2.1), 'ghost'+'phantom' (unresolved)
    # → first two land in gate_dropped, third lands in unresolved.
    assert result["aggregate"]["inapt_gate_dropped"] >= 1


def test_evaluate_cohort_honours_no_gate_baseline(tmp_path):
    """concreteness_threshold = -inf reduces to no-gate — every pair
    that resolves with both concreteness scores reaches the Ortony
    stage. Required for the M02-baseline ablation slice.
    """
    import math
    conn = _build_fixture_db_with_centroids()
    pairs, controls = _write_fixture_cohorts(tmp_path)
    cfg = CascadeConfig(concreteness_threshold=-math.inf)
    result = evaluate_cohort(
        conn, pairs_file=pairs, controls_file=controls,
        config=cfg, threshold_percentile=95.0, db_path=":memory:",
    )
    # All pairs that resolve to both synsets+concreteness should pass
    # the gate when threshold = -inf.
    assert result["aggregate"]["apt_gate_dropped"] == 0
    assert result["aggregate"]["inapt_gate_dropped"] == 0


def test_evaluate_cohort_config_block_records_cascade_params(tmp_path):
    """The result's config block must include the cascade hyperparameters
    (threshold, d_cap, alpha, composition, ortony_scoring) so a stored
    sweep result is self-describing.
    """
    conn = _build_fixture_db_with_centroids()
    pairs, controls = _write_fixture_cohorts(tmp_path)
    cfg = CascadeConfig(
        concreteness_threshold=1.5, ortony_scoring="jaccard_raw",
        d_cap=0.5, alpha=0.25, composition="additive",
    )
    result = evaluate_cohort(
        conn, pairs_file=pairs, controls_file=controls,
        config=cfg, threshold_percentile=90.0, db_path=":memory:",
    )
    rc = result["config"]
    assert rc["evaluator"] == "cascade"
    assert rc["concreteness_threshold"] == 1.5
    assert rc["ortony_scoring"] == "jaccard_raw"
    assert rc["d_cap"] == 0.5
    assert rc["alpha"] == 0.25
    assert rc["composition"] == "additive"
    assert rc["threshold_percentile"] == 90.0


def test_centroid_returns_none_on_malformed_blob_length():
    """A BLOB whose byte length isn't a multiple of 4 cannot be a packed
    float32 vector — surface as None (fail-open) with a WARNING so
    operators can spot bad rows without taking the cascade offline.
    """
    import sqlite3
    from evaluate_cascade import _centroid

    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE synset_centroids ("
        "synset_id TEXT PRIMARY KEY, centroid BLOB NOT NULL, "
        "property_count INTEGER NOT NULL);"
    )
    conn.execute(
        "INSERT INTO synset_centroids VALUES (?, ?, ?)",
        ("S1", b"\x00\x01\x02", 1),  # 3 bytes, not multiple of 4
    )
    conn.commit()
    assert _centroid(conn, "S1") is None


def test_cosine_distance_returns_none_on_dim_mismatch():
    """Mismatched dims must NOT silently truncate via zip() — the resulting
    distance would mask a real upstream bug (mixed embedding dims).
    """
    from evaluate_cascade import _cosine_distance
    assert _cosine_distance([1.0, 0.0, 0.0], [1.0, 0.0]) is None
    assert _cosine_distance([1.0], [1.0, 1.0, 1.0]) is None


def test_centroid_reraises_non_missing_table_operational_errors():
    """Genuine OperationalError (corruption, lock) must escalate, not fail-open.

    Standards-error-handling: silently swallowing a "database is locked"
    or corruption error would let the cascade produce systematically
    degraded scores with no signal. Only the "no such table" case (which
    appears on fixture DBs / pre-pipeline snapshots) is allowed to
    fail-open through return None.
    """
    import sqlite3
    from evaluate_cascade import _centroid

    class _LockedConn:
        """Stand-in conn whose execute() raises 'database is locked'."""
        def execute(self, *args, **kwargs):
            raise sqlite3.OperationalError("database is locked")

    with pytest.raises(sqlite3.OperationalError, match="database is locked"):
        _centroid(_LockedConn(), "S1")  # type: ignore[arg-type]


def test_re_rank_handles_zero_norm_centroid_as_missing():
    """A degenerate all-zero centroid (cosine undefined) must be treated
    as a missing centroid (fail-open). The cascade should not produce
    NaN scores or crash on a divide-by-zero.

    The real-DB shape would only emit a zero-norm centroid if a synset
    had no embeddable properties — rare but defensible to handle.
    """
    import struct
    conn = _build_fixture_db_with_centroids()
    # Insert a zero-norm centroid for a real synset.
    conn.execute(
        "UPDATE synset_centroids SET centroid = ? WHERE synset_id = ?",
        (struct.pack("3f", 0.0, 0.0, 0.0), "S_VEHICLE_FIRE"),
    )
    conn.commit()
    result = evaluate_cascade_pair(
        conn, "S_TOPIC_ANGER", "S_VEHICLE_FIRE", CascadeConfig(),
    )
    # Treat as missing centroid → fail-open path.
    assert result.cosine_distance is None
    assert result.re_rank_bonus is None
    assert result.final_score == result.ortony_score
