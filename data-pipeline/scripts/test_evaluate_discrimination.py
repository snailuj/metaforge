"""Tests for evaluate_discrimination.py — structural discrimination eval."""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from unittest.mock import patch, MagicMock
from evaluate_discrimination import select_source_words, query_forge_results, classify_by_domain


def _make_test_db():
    """In-memory DB with lemmas + synsets + curated properties + relations."""
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE synsets (
            synset_id TEXT PRIMARY KEY,
            pos TEXT NOT NULL,
            definition TEXT
        );
        CREATE TABLE lemmas (
            lemma TEXT NOT NULL,
            synset_id TEXT NOT NULL,
            PRIMARY KEY (lemma, synset_id)
        );
        CREATE TABLE synset_properties_curated (
            synset_id TEXT NOT NULL,
            vocab_id INTEGER NOT NULL,
            cluster_id INTEGER,
            salience_sum REAL DEFAULT 1.0
        );
        CREATE TABLE property_vocab_curated (
            vocab_id INTEGER PRIMARY KEY,
            property TEXT NOT NULL
        );
        CREATE TABLE relations (
            source_synset TEXT NOT NULL,
            target_synset TEXT NOT NULL,
            relation_type TEXT NOT NULL
        );

        -- Properties
        INSERT INTO property_vocab_curated VALUES (1, 'hot');
        INSERT INTO property_vocab_curated VALUES (2, 'bright');
        INSERT INTO property_vocab_curated VALUES (3, 'dangerous');
        INSERT INTO property_vocab_curated VALUES (4, 'consuming');
        INSERT INTO property_vocab_curated VALUES (5, 'radiant');
        INSERT INTO property_vocab_curated VALUES (6, 'gentle');
        INSERT INTO property_vocab_curated VALUES (7, 'quick');

        -- "blaze" (noun): 2 synsets, 5+3 curated properties
        INSERT INTO synsets VALUES ('100', 'n', 'a strong flame');
        INSERT INTO synsets VALUES ('200', 'n', 'a bright light');
        INSERT INTO lemmas VALUES ('blaze', '100');
        INSERT INTO lemmas VALUES ('blaze', '200');
        INSERT INTO synset_properties_curated VALUES ('100', 1, 1, 1.0);
        INSERT INTO synset_properties_curated VALUES ('100', 2, 2, 1.0);
        INSERT INTO synset_properties_curated VALUES ('100', 3, 3, 1.0);
        INSERT INTO synset_properties_curated VALUES ('100', 4, 4, 1.0);
        INSERT INTO synset_properties_curated VALUES ('100', 5, 5, 1.0);
        INSERT INTO synset_properties_curated VALUES ('200', 1, 1, 1.0);
        INSERT INTO synset_properties_curated VALUES ('200', 2, 2, 1.0);
        INSERT INTO synset_properties_curated VALUES ('200', 5, 5, 1.0);

        -- "dim" (adjective): 1 synset, 1 property (too few — excluded)
        INSERT INTO synsets VALUES ('300', 's', 'lacking light');
        INSERT INTO lemmas VALUES ('dim', '300');
        INSERT INTO synset_properties_curated VALUES ('300', 2, 2, 1.0);

        -- "glow" (verb): 1 synset, 3 properties
        INSERT INTO synsets VALUES ('400', 'v', 'emit light');
        INSERT INTO lemmas VALUES ('glow', '400');
        INSERT INTO synset_properties_curated VALUES ('400', 1, 1, 1.0);
        INSERT INTO synset_properties_curated VALUES ('400', 2, 2, 1.0);
        INSERT INTO synset_properties_curated VALUES ('400', 5, 5, 1.0);

        -- "swift" (adjective): 1 synset, 3 properties
        INSERT INTO synsets VALUES ('500', 'a', 'moving very fast');
        INSERT INTO lemmas VALUES ('swift', '500');
        INSERT INTO synset_properties_curated VALUES ('500', 6, 6, 1.0);
        INSERT INTO synset_properties_curated VALUES ('500', 7, 7, 1.0);
        INSERT INTO synset_properties_curated VALUES ('500', 2, 2, 1.0);
    """)
    conn.commit()
    return conn


def test_select_source_words_filters_by_min_properties():
    conn = _make_test_db()
    words = select_source_words(conn, min_properties=3)
    lemmas = [w["lemma"] for w in words]
    assert "blaze" in lemmas
    assert "glow" in lemmas
    assert "swift" in lemmas
    assert "dim" not in lemmas  # only 1 property


def test_select_source_words_returns_pos():
    conn = _make_test_db()
    words = select_source_words(conn, min_properties=1)
    for w in words:
        assert "lemma" in w
        assert "pos" in w
        assert "primary_synset_id" in w


def test_select_source_words_uses_primary_synset():
    conn = _make_test_db()
    words = select_source_words(conn, min_properties=3)
    blaze = next(w for w in words if w["lemma"] == "blaze")
    # primary synset = lowest synset_id = '100'
    assert blaze["primary_synset_id"] == "100"


def test_select_source_words_respects_pos_quotas():
    conn = _make_test_db()
    words = select_source_words(
        conn, min_properties=3,
        noun_quota=1, verb_quota=1, adj_quota=1,
    )
    lemmas = [w["lemma"] for w in words]
    # Should get at most 1 noun, 1 verb, 1 adj
    assert len(words) <= 3
    # blaze=noun, glow=verb, swift=adj — all should fit
    assert "blaze" in lemmas
    assert "glow" in lemmas
    assert "swift" in lemmas


def _make_forge_response(suggestions):
    return {"source": "anger", "suggestions": suggestions}


def test_query_forge_results_returns_suggestions():
    resp_data = _make_forge_response([
        {"word": "fire", "domain_distance": 0.8, "composite_score": 3.0,
         "synset_id": "s1", "tier": "legendary", "overlap_count": 4,
         "salience_sum": 4.0, "shared_properties": ["hot", "intense"]},
    ])
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = resp_data

    with patch("evaluate_discrimination.requests.get", return_value=mock_resp):
        results = query_forge_results("anger", port=8080, limit=100)

    assert len(results) == 1
    assert results[0]["word"] == "fire"


def test_query_forge_results_returns_empty_on_error():
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.text = "not found"

    with patch("evaluate_discrimination.requests.get", return_value=mock_resp):
        results = query_forge_results("nonexistent", port=8080, limit=100)

    assert results == []


def test_classify_by_domain_widened_thresholds():
    suggestions = [
        {"word": "fire", "domain_distance": 0.8, "composite_score": 3.0},
        {"word": "rage", "domain_distance": 0.2, "composite_score": 2.5},
        {"word": "storm", "domain_distance": 0.75, "composite_score": 2.8},
        {"word": "fury", "domain_distance": 0.15, "composite_score": 2.3},
        {"word": "wave", "domain_distance": 0.5, "composite_score": 2.0},    # ambiguous
        {"word": "cloud", "domain_distance": 0.65, "composite_score": 1.8},  # ambiguous
    ]

    cross, same = classify_by_domain(
        suggestions, cross_threshold=0.7, same_threshold=0.3
    )

    # fire (0.8), storm (0.75) are cross-domain
    assert len(cross) == 2
    # rage (0.2), fury (0.15) are same-domain
    assert len(same) == 2
    # wave (0.5), cloud (0.65) are ambiguous — excluded from both


def test_classify_by_domain_excludes_none_distances():
    suggestions = [
        {"word": "fire", "domain_distance": 0.8, "composite_score": 3.0},
        {"word": "mystery", "composite_score": 2.5},  # no domain_distance key
        {"word": "rage", "domain_distance": None, "composite_score": 2.3},
    ]

    cross, same = classify_by_domain(suggestions)

    # Only "fire" has a valid distance > 0.7
    assert len(cross) == 1
    assert cross[0]["word"] == "fire"
    # None/missing should NOT count as same-domain (distance 0)
    assert len(same) == 0
