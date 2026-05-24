"""Tests for metaphor_spike_1a.py — Phase 1a runner.

Uses no DB and no LLM calls. Every test is pure-function.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import sqlite3

from metaphor_spike_1a import (
    TOPICS,
    build_apt_prompt,
    build_inapt_prompt,
    validate_apt_response,
    validate_inapt_response,
    AptValidation,
    InaptValidation,
    check_concept_snap_rate,
    ConceptSnapResult,
)


def test_topics_count():
    assert len(TOPICS) == 5


def test_topics_have_word_and_gloss():
    for t in TOPICS:
        assert "word" in t, f"missing 'word' key: {t}"
        assert "gloss" in t, f"missing 'gloss' key: {t}"
        assert t["word"].strip(), "word must be non-empty"
        assert t["gloss"].strip(), "gloss must be non-empty"


def test_topic_words_are_single_tokens():
    """Topic words must not contain spaces — they are lemma keys."""
    for t in TOPICS:
        assert " " not in t["word"], f"topic word must be single token: {t['word']!r}"


def test_apt_prompt_contains_topic_and_gloss():
    prompt = build_apt_prompt("fire", "rapid oxidation producing heat and light")
    assert "fire" in prompt
    assert "rapid oxidation producing heat and light" in prompt
    # Must not echo the gloss placeholder literally
    assert "<TOPIC>" not in prompt
    assert "<GLOSS>" not in prompt


def test_inapt_prompt_contains_topic_and_gloss():
    prompt = build_inapt_prompt("fire", "rapid oxidation producing heat and light")
    assert "fire" in prompt
    assert "rapid oxidation producing heat and light" in prompt
    assert "<TOPIC>" not in prompt
    assert "<GLOSS>" not in prompt


def test_apt_and_inapt_prompts_are_different():
    apt = build_apt_prompt("grief", "deep sorrow")
    inapt = build_inapt_prompt("grief", "deep sorrow")
    assert apt != inapt


def test_validate_apt_response_valid():
    raw = {
        "topic": "anger",
        "metaphors": [
            {
                "vehicle": "fire",
                "shared_features": [
                    {"dimension": "sensorimotor", "concept": "heat"},
                    {"dimension": "behaviour", "concept": "spreading"},
                ],
                "confidence": 0.95,
            }
        ],
    }
    v = validate_apt_response(raw)
    assert v.schema_ok
    assert v.n_vehicles == 1
    assert v.n_concepts == 2
    assert v.n_single_word_concepts == 2
    assert v.concept_violations == []


def test_validate_apt_response_multi_word_concept():
    """A concept containing a space must be counted as a violation."""
    raw = {
        "topic": "anger",
        "metaphors": [
            {
                "vehicle": "fire",
                "shared_features": [
                    {"dimension": "sensorimotor", "concept": "must be tamed"},
                ],
                "confidence": 0.9,
            }
        ],
    }
    v = validate_apt_response(raw)
    assert v.schema_ok
    assert v.n_concepts == 1
    assert v.n_single_word_concepts == 0
    assert "must be tamed" in v.concept_violations


def test_validate_apt_response_bad_dimension():
    """An invalid dimension value makes schema_ok False."""
    raw = {
        "topic": "anger",
        "metaphors": [
            {
                "vehicle": "fire",
                "shared_features": [
                    {"dimension": "other", "concept": "heat"},
                ],
                "confidence": 0.9,
            }
        ],
    }
    v = validate_apt_response(raw)
    assert not v.schema_ok


def test_validate_apt_response_missing_metaphors_key():
    raw = {"topic": "anger"}
    v = validate_apt_response(raw)
    assert not v.schema_ok


def test_validate_inapt_response_valid():
    raw = {
        "topic": "anger",
        "inapt_metaphors": [
            {
                "vehicle": "fury",
                "inapt_reason_type": "same_domain",
                "explanation": "near-synonym",
            }
        ],
    }
    v = validate_inapt_response(raw)
    assert v.schema_ok
    assert v.n_vehicles == 1


def test_validate_inapt_response_bad_reason_type():
    raw = {
        "topic": "anger",
        "inapt_metaphors": [
            {
                "vehicle": "fury",
                "inapt_reason_type": "made_up_tag",
                "explanation": "near-synonym",
            }
        ],
    }
    v = validate_inapt_response(raw)
    assert not v.schema_ok


def test_validate_inapt_response_missing_key():
    raw = {"topic": "anger"}
    v = validate_inapt_response(raw)
    assert not v.schema_ok


def test_validate_apt_response_non_dict_metaphor_entry():
    """A non-dict element in the metaphors list must not crash the validator."""
    raw = {"topic": "anger", "metaphors": [None, "fire", 42]}
    v = validate_apt_response(raw)
    assert not v.schema_ok
    # Should not have raised — validator returns gracefully


def test_validate_apt_response_non_string_concept():
    """A non-string concept value must not crash the validator."""
    raw = {
        "topic": "anger",
        "metaphors": [
            {
                "vehicle": "fire",
                "shared_features": [
                    {"dimension": "sensorimotor", "concept": None},
                    {"dimension": "behaviour", "concept": 42},
                ],
                "confidence": 0.9,
            }
        ],
    }
    v = validate_apt_response(raw)
    assert not v.schema_ok
    # n_concepts should still count the entries
    assert v.n_concepts == 2


def test_validate_apt_response_non_dict_shared_feature():
    """A non-dict shared_feature element must not crash the validator."""
    raw = {
        "topic": "anger",
        "metaphors": [
            {
                "vehicle": "fire",
                "shared_features": [None, "intense", {"dimension": "sensorimotor", "concept": "heat"}],
                "confidence": 0.9,
            }
        ],
    }
    v = validate_apt_response(raw)
    assert not v.schema_ok


def test_validate_inapt_response_non_dict_entry():
    """A non-dict element in inapt_metaphors must not crash the validator."""
    raw = {"topic": "anger", "inapt_metaphors": [None, "fury", 42]}
    v = validate_inapt_response(raw)
    assert not v.schema_ok


def _make_lemmas_db(words: list[str]) -> sqlite3.Connection:
    """In-memory DB with a lemmas table populated for the given words."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE lemmas (lemma TEXT NOT NULL, synset_id TEXT NOT NULL, "
        "PRIMARY KEY (lemma, synset_id))"
    )
    for i, w in enumerate(words):
        conn.execute("INSERT INTO lemmas VALUES (?, ?)", (w, f"s-{i}"))
    conn.commit()
    return conn


def test_concept_snap_all_known():
    conn = _make_lemmas_db(["heat", "spreading", "destruction"])
    concepts = ["heat", "spreading", "destruction"]
    result = check_concept_snap_rate(conn, concepts)
    assert result.n_concepts == 3
    assert result.n_snapped == 3
    assert result.snap_rate == 1.0
    assert result.unsnapped == []


def test_concept_snap_partial():
    conn = _make_lemmas_db(["heat"])
    concepts = ["heat", "unknownxyz", "alsounkown"]
    result = check_concept_snap_rate(conn, concepts)
    assert result.n_concepts == 3
    assert result.n_snapped == 1
    assert round(result.snap_rate, 4) == round(1 / 3, 4)
    assert "unknownxyz" in result.unsnapped
    assert "alsounkown" in result.unsnapped


def test_concept_snap_empty_list():
    conn = _make_lemmas_db([])
    result = check_concept_snap_rate(conn, [])
    assert result.n_concepts == 0
    assert result.n_snapped == 0
    assert result.snap_rate == 0.0


def test_concept_snap_handles_none_and_non_string_inputs():
    """Non-string entries (None, ints) are silently filtered, like whitespace-only."""
    conn = _make_lemmas_db(["heat"])
    concepts = ["heat", None, 42, "  ", "unknownxyz"]
    result = check_concept_snap_rate(conn, concepts)
    # Only "heat" + "unknownxyz" survive the filter — count of 2 unique
    assert result.n_concepts == 2
    assert result.n_snapped == 1
    assert "unknownxyz" in result.unsnapped


def test_concept_snap_case_insensitive():
    """Lookup is case-insensitive — HEAT matches the lowercase lemma."""
    conn = _make_lemmas_db(["heat"])
    result = check_concept_snap_rate(conn, ["HEAT", "Heat"])
    assert result.n_concepts == 1  # dedup collapses to "heat"
    assert result.n_snapped == 1
