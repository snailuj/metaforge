"""Tests for the Phase 1b-specific runner additions.

Most primitives (validators, snap-rate, gate metrics, JSONL writer,
cascade scoring) are imported from Phase 1a and already exhaustively
tested in test_metaphor_spike_1a.py. Phase 1b adds:

- Gold-example baked templates (single .format() pass)
- score_inapt_vehicles (mirrors apt scoring, preserves inapt_reason_type)
- compute_discrimination (apt vs inapt cohort metrics + per-reason)

These are what this file covers.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sqlite3
import pytest

import metaphor_spike_1b as m
from metaphor_spike_1a import ScoredVehicle


# ---------------------------------------------------------------------------
# TOPICS
# ---------------------------------------------------------------------------

def test_phase1b_has_twenty_topics():
    assert len(m.TOPICS) == 20


def test_phase1b_topics_all_have_word_and_gloss():
    for t in m.TOPICS:
        assert "word" in t and t["word"], t
        assert "gloss" in t and t["gloss"], t


def test_phase1b_topics_are_unique():
    words = [t["word"] for t in m.TOPICS]
    assert len(set(words)) == len(words)


def test_phase1b_topics_disjoint_from_gold_examples():
    """The 3 Sonnet gold-example topics (love, knowledge, fear) must
    not appear in the 20 test topics — otherwise Haiku just regurgitates."""
    gold_words = {t["word"] for t in m._GOLD_TOPICS}
    test_words = {t["word"] for t in m.TOPICS}
    overlap = gold_words & test_words
    assert overlap == set(), f"leakage: gold examples in test set: {overlap}"


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

def test_apt_prompt_substitutes_topic_and_gloss():
    p = m.build_apt_prompt("anger", "a strong feeling of displeasure")
    assert "Input: anger (a strong feeling of displeasure)" in p
    assert p.rstrip().endswith("Output:")


def test_apt_prompt_contains_all_three_gold_examples():
    p = m.build_apt_prompt("anger", "gloss")
    assert "Input: love" in p
    assert "Input: knowledge" in p
    assert "Input: fear" in p


def test_apt_prompt_has_no_unresolved_format_braces():
    p = m.build_apt_prompt("anger", "gloss")
    # After substitution there should be no doubled braces left over.
    assert "{{" not in p
    assert "}}" not in p


def test_inapt_prompt_contains_failure_mode_vocabulary():
    p = m.build_inapt_prompt("anger", "gloss")
    for mode in ("single_dimension", "same_domain", "wrong_concreteness",
                 "dead_metaphor", "synonym_or_hypernym"):
        assert mode in p


def test_inapt_prompt_substitutes_topic_and_gloss():
    p = m.build_inapt_prompt("doubt", "uncertainty about the truth of something")
    assert "Input: doubt (uncertainty about the truth of something)" in p


# ---------------------------------------------------------------------------
# score_inapt_vehicles — uses in-memory DB with a tiny seeded schema.
# ---------------------------------------------------------------------------

@pytest.fixture
def stub_conn(monkeypatch):
    """In-memory SQLite + stubbed lookup/scoring to exercise score_inapt_vehicles
    without depending on the full lexicon_v2 schema."""
    conn = sqlite3.connect(":memory:")

    def fake_lookup(_conn, lemma):
        return f"sid:{lemma}" if lemma else None

    class FakeCR:
        def __init__(self, status, score, gate):
            self.status = status
            self.final_score = score
            self.gate_passed = gate

    def fake_cascade(_conn, sid_a, sid_b, _cfg):
        # Anything with sid:fail returns gate_dropped (no score).
        if "fail" in (sid_a + sid_b):
            return FakeCR("gate_dropped", None, False)
        return FakeCR("scored", 0.42, True)

    monkeypatch.setattr(m, "lookup_primary_synset", fake_lookup)
    monkeypatch.setattr(m, "evaluate_cascade_pair", fake_cascade)
    yield conn
    conn.close()


def test_score_inapt_preserves_reason_type(stub_conn):
    response = {
        "topic": "anger",
        "inapt_metaphors": [
            {"vehicle": "fury", "inapt_reason_type": "same_domain", "explanation": "x"},
            {"vehicle": "calendar", "inapt_reason_type": "single_dimension", "explanation": "x"},
        ],
    }
    result = m.score_inapt_vehicles(stub_conn, response, m.PRODUCTION_CASCADE_CONFIG)
    assert len(result) == 2
    assert result[0].inapt_reason_type == "same_domain"
    assert result[1].inapt_reason_type == "single_dimension"
    assert all(r.cascade_status == "scored" for r in result)


def test_score_inapt_handles_unresolved_vehicle(stub_conn, monkeypatch):
    def lookup_with_miss(_conn, lemma):
        return None if lemma == "ghost" else f"sid:{lemma}"
    monkeypatch.setattr(m, "lookup_primary_synset", lookup_with_miss)

    response = {
        "topic": "anger",
        "inapt_metaphors": [
            {"vehicle": "ghost", "inapt_reason_type": "wrong_concreteness", "explanation": "x"},
        ],
    }
    result = m.score_inapt_vehicles(stub_conn, response, m.PRODUCTION_CASCADE_CONFIG)
    assert len(result) == 1
    assert result[0].cascade_status == "unresolved"
    assert result[0].inapt_reason_type == "wrong_concreteness"


def test_score_inapt_skips_non_dict_entries(stub_conn):
    response = {
        "topic": "anger",
        "inapt_metaphors": [
            "not a dict",
            {"vehicle": "fury", "inapt_reason_type": "same_domain", "explanation": "x"},
        ],
    }
    result = m.score_inapt_vehicles(stub_conn, response, m.PRODUCTION_CASCADE_CONFIG)
    assert len(result) == 1
    assert result[0].vehicle == "fury"


# ---------------------------------------------------------------------------
# compute_discrimination
# ---------------------------------------------------------------------------

def _sv_apt(score: float, status: str = "scored") -> ScoredVehicle:
    return ScoredVehicle(
        topic="t", vehicle="v",
        synset_topic="s1", synset_vehicle="s2",
        cascade_status=status, final_score=score, gate_passed=True,
    )


def _sv_inapt(score: float, reason: str, status: str = "scored") -> m.ScoredInaptVehicle:
    return m.ScoredInaptVehicle(
        topic="t", vehicle="v",
        synset_topic="s1", synset_vehicle="s2",
        cascade_status=status, final_score=score, gate_passed=False,
        inapt_reason_type=reason,
    )


def test_discrimination_separation_positive_when_apt_higher():
    apt = [_sv_apt(0.8), _sv_apt(0.7), _sv_apt(0.6)]
    inapt = [_sv_inapt(0.3, "same_domain"), _sv_inapt(0.4, "single_dimension")]
    d = m.compute_discrimination(apt, inapt)
    assert d.separation_score > 0
    assert d.mean_apt_score > d.mean_inapt_score


def test_discrimination_excludes_unscored_from_mean():
    apt = [_sv_apt(0.8), _sv_apt(None, status="gate_dropped"), _sv_apt(0.6)]
    inapt = [_sv_inapt(0.3, "same_domain")]
    d = m.compute_discrimination(apt, inapt)
    assert d.n_apt_scored == 2
    assert d.mean_apt_score == pytest.approx(0.7)


def test_discrimination_per_reason_breakdown_groups_by_tag():
    inapt = [
        _sv_inapt(0.2, "same_domain"),
        _sv_inapt(0.3, "same_domain"),
        _sv_inapt(0.7, "single_dimension"),
    ]
    d = m.compute_discrimination([_sv_apt(0.9)], inapt)
    assert "same_domain" in d.per_reason_breakdown
    assert d.per_reason_breakdown["same_domain"]["n_scored"] == 2
    assert d.per_reason_breakdown["same_domain"]["mean_score"] == pytest.approx(0.25)
    assert d.per_reason_breakdown["single_dimension"]["n_scored"] == 1


def test_discrimination_empty_cohorts_safe():
    d = m.compute_discrimination([], [])
    assert d.n_apt_scored == 0
    assert d.n_inapt_scored == 0
    assert d.separation_score == 0.0
    assert d.aptness_rate == 0.0
