"""Tests for metaphor_spike_1a.py — Phase 1a runner.

Uses no DB and no LLM calls. Every test is pure-function.
"""
from __future__ import annotations

import json
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
    write_jsonl_line,
    score_apt_vehicles,
    ScoredVehicle,
    PRODUCTION_CASCADE_CONFIG,
    GateMetrics,
    compute_gate_metrics,
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


def test_write_jsonl_line(tmp_path):
    out = tmp_path / "out.jsonl"
    write_jsonl_line(out, {"topic": "anger", "vehicle": "fire"})
    write_jsonl_line(out, {"topic": "anger", "vehicle": "storm"})
    lines = out.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"topic": "anger", "vehicle": "fire"}
    assert json.loads(lines[1]) == {"topic": "anger", "vehicle": "storm"}


def test_write_jsonl_line_creates_parent(tmp_path):
    out = tmp_path / "subdir" / "out.jsonl"
    write_jsonl_line(out, {"x": 1})
    assert out.exists()


def _make_cascade_db() -> sqlite3.Connection:
    """Minimal schema for cascade scoring. Includes all tables the cascade
    and lookup_primary_synset touch."""
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE lemmas (
            lemma TEXT NOT NULL,
            synset_id TEXT NOT NULL,
            PRIMARY KEY (lemma, synset_id)
        );
        CREATE TABLE property_vocab_curated (
            vocab_id INTEGER PRIMARY KEY,
            lemma TEXT NOT NULL,
            polysemy INTEGER NOT NULL DEFAULT 1,
            synset_id TEXT NOT NULL
        );
        CREATE TABLE synset_concreteness (
            synset_id TEXT PRIMARY KEY,
            score REAL NOT NULL,
            source TEXT NOT NULL
        );
        CREATE TABLE synset_properties_curated (
            synset_id   TEXT NOT NULL,
            vocab_id    INTEGER NOT NULL,
            cluster_id  INTEGER NOT NULL,
            snap_method TEXT NOT NULL,
            snap_score  REAL,
            salience_sum REAL NOT NULL DEFAULT 1.0,
            PRIMARY KEY (synset_id, cluster_id)
        );
        CREATE TABLE property_vocabulary (
            vocab_id INTEGER PRIMARY KEY,
            text TEXT NOT NULL,
            cluster_id INTEGER NOT NULL DEFAULT 0
        );
    """)
    # topic: grief (abstract, low concreteness)
    conn.execute("INSERT INTO lemmas VALUES ('grief', 'syn-grief')")
    conn.execute("INSERT INTO property_vocab_curated VALUES (1, 'grief', 1, 'syn-grief')")
    conn.execute("INSERT INTO synset_concreteness VALUES ('syn-grief', 1.5, 'test')")
    # vehicle: storm (concrete, higher concreteness)
    conn.execute("INSERT INTO lemmas VALUES ('storm', 'syn-storm')")
    conn.execute("INSERT INTO property_vocab_curated VALUES (2, 'storm', 1, 'syn-storm')")
    conn.execute("INSERT INTO synset_concreteness VALUES ('syn-storm', 4.5, 'test')")
    # Give both synsets a shared property so Ortony finds overlap
    conn.execute("INSERT INTO property_vocabulary VALUES (10, 'intense', 0)")
    conn.execute("INSERT INTO synset_properties_curated VALUES ('syn-grief', 10, 0, 'exact', 1.0, 0.9)")
    conn.execute("INSERT INTO synset_properties_curated VALUES ('syn-storm', 10, 0, 'exact', 1.0, 0.9)")
    conn.commit()
    return conn


def test_score_apt_vehicles_scored_pair():
    conn = _make_cascade_db()
    apt_response = {
        "topic": "grief",
        "metaphors": [
            {
                "vehicle": "storm",
                "shared_features": [{"dimension": "emotional", "concept": "intensity"}],
                "confidence": 0.85,
            }
        ],
    }
    scored = score_apt_vehicles(conn, apt_response, PRODUCTION_CASCADE_CONFIG)
    assert len(scored) == 1
    sv = scored[0]
    assert sv.topic == "grief"
    assert sv.vehicle == "storm"
    # Fixture: storm concreteness 4.5 - grief concreteness 1.5 = 3.0 >= gate 1.0,
    # both have shared property -> cascade should fully score.
    assert sv.cascade_status == "scored"
    assert sv.final_score is not None
    assert sv.gate_passed is True
    assert sv.synset_topic == "syn-grief"
    assert sv.synset_vehicle == "syn-storm"


def test_score_apt_vehicles_unknown_vehicle():
    """Vehicle not in lemmas → unresolved, still returns a row."""
    conn = _make_cascade_db()
    apt_response = {
        "topic": "grief",
        "metaphors": [
            {
                "vehicle": "notaword99xyz",
                "shared_features": [{"dimension": "emotional", "concept": "loss"}],
                "confidence": 0.5,
            }
        ],
    }
    scored = score_apt_vehicles(conn, apt_response, PRODUCTION_CASCADE_CONFIG)
    assert len(scored) == 1
    assert scored[0].cascade_status == "unresolved"
    assert scored[0].final_score is None


def test_write_jsonl_line_skips_non_serialisable(tmp_path, caplog):
    """A non-JSON-serialisable payload logs a warning and is skipped."""
    import logging as _logging
    out = tmp_path / "out.jsonl"
    write_jsonl_line(out, {"good": "value"})
    # Set is not JSON-serialisable
    with caplog.at_level(_logging.WARNING):
        write_jsonl_line(out, {"bad": {1, 2, 3}})
    write_jsonl_line(out, {"another": "value"})
    lines = out.read_text().strip().splitlines()
    # Good lines are written; the bad one is skipped silently (no crash).
    assert len(lines) == 2
    assert "non-serialisable" in caplog.text.lower()


def test_compute_gate_metrics_all_pass():
    validations = [
        AptValidation(
            schema_ok=True,
            n_vehicles=3,
            n_concepts=6,
            n_single_word_concepts=6,
            concept_violations=[],
            schema_errors=[],
        ),
        AptValidation(
            schema_ok=True,
            n_vehicles=2,
            n_concepts=4,
            n_single_word_concepts=4,
            concept_violations=[],
            schema_errors=[],
        ),
    ]
    snap = ConceptSnapResult(n_concepts=10, n_snapped=10, snap_rate=1.0, unsnapped=[])
    m = compute_gate_metrics(validations, snap)
    assert m.parse_ok_rate == 1.0  # both parsed (no parse failure injected)
    assert m.schema_ok_rate == 1.0
    assert m.single_word_rate == 1.0
    assert m.snap_rate == 1.0


def test_compute_gate_metrics_mixed():
    validations = [
        AptValidation(
            schema_ok=True,
            n_vehicles=2,
            n_concepts=4,
            n_single_word_concepts=3,  # one multi-word violation
            concept_violations=["must be tamed"],
            schema_errors=[],
        ),
        AptValidation(
            schema_ok=False,  # schema failure
            n_vehicles=0,
            n_concepts=0,
            n_single_word_concepts=0,
            concept_violations=[],
            schema_errors=["missing 'metaphors' key"],
        ),
    ]
    snap = ConceptSnapResult(n_concepts=4, n_snapped=3, snap_rate=0.75, unsnapped=["xyz"])
    m = compute_gate_metrics(validations, snap)
    assert m.schema_ok_rate == 0.5  # 1/2
    assert m.single_word_rate == round(3 / 4, 6)  # 3 of 4 concepts single-word
    assert m.snap_rate == 0.75


def test_compute_gate_metrics_zero_concepts():
    validations = [
        AptValidation(
            schema_ok=False,
            n_vehicles=0,
            n_concepts=0,
            n_single_word_concepts=0,
            concept_violations=[],
            schema_errors=["missing key"],
        )
    ]
    snap = ConceptSnapResult(n_concepts=0, n_snapped=0, snap_rate=0.0, unsnapped=[])
    m = compute_gate_metrics(validations, snap)
    assert m.single_word_rate == 0.0
    assert m.snap_rate == 0.0
