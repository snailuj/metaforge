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
    evaluate_aptness.evaluate, which raises with the registered list."""
    conn = _build_fixture_db()
    with pytest.raises(ValueError, match="Unknown"):
        evaluate_cascade_pair(
            conn, "S_TOPIC_ANGER", "S_VEHICLE_FIRE",
            CascadeConfig(ortony_scoring="not_a_real_scoring_fn"),
        )


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


def test_s01_scope_re_rank_fields_are_none_until_s02_lands():
    """S01 ships the cascade scaffold + gate; S02 will compute
    cosine_distance + re_rank_bonus. Until then these fields must be
    None so a sweep config that mistakenly tries to use them gets a
    clear type error rather than a silent zero.
    """
    conn = _build_fixture_db()
    result = evaluate_cascade_pair(
        conn, "S_TOPIC_ANGER", "S_VEHICLE_FIRE", CascadeConfig(),
    )
    assert result.cosine_distance is None
    assert result.re_rank_bonus is None
    # final_score in S01 == ortony_score (no re-rank multiplier applied yet).
    assert result.final_score == result.ortony_score
