"""Tests for evaluate_discrimination.py — structural discrimination eval."""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from unittest.mock import patch, MagicMock
from evaluate_discrimination import (
    select_source_words, query_forge_results, classify_by_domain,
    compute_rank_auc, compute_word_metrics, lookup_synonyms,
    aggregate_metrics, evaluate_discrimination,
)


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


def test_query_forge_results_returns_none_on_error():
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.text = "not found"

    with patch("evaluate_discrimination.requests.get", return_value=mock_resp):
        results = query_forge_results("nonexistent", port=8080, limit=100)

    assert results is None


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


def test_compute_rank_auc_perfect_separation():
    # All cross-domain ranked above all same-domain
    cross_ranks = [1, 2, 3]
    same_ranks = [4, 5, 6]
    auc = compute_rank_auc(cross_ranks, same_ranks)
    assert auc == pytest.approx(1.0)


def test_compute_rank_auc_no_separation():
    # Same-domain ranked above cross-domain
    cross_ranks = [4, 5, 6]
    same_ranks = [1, 2, 3]
    auc = compute_rank_auc(cross_ranks, same_ranks)
    assert auc == pytest.approx(0.0)


def test_compute_rank_auc_random():
    # Interleaved — roughly 0.5
    cross_ranks = [1, 3, 5]
    same_ranks = [2, 4, 6]
    auc = compute_rank_auc(cross_ranks, same_ranks)
    # Each cross-domain beats: 1 beats all 3, 3 beats 2, 5 beats 1 = 6/9
    assert auc == pytest.approx(6 / 9, abs=0.01)


def test_compute_rank_auc_empty():
    assert compute_rank_auc([], [1, 2]) is None
    assert compute_rank_auc([1, 2], []) is None


def test_compute_word_metrics_basic():
    suggestions = [
        # Ranked 1-10 by position (pre-sorted by API)
        {"word": "fire",    "domain_distance": 0.8,  "composite_score": 3.5},
        {"word": "volcano", "domain_distance": 0.9,  "composite_score": 3.2},
        {"word": "rage",    "domain_distance": 0.2,  "composite_score": 3.0},
        {"word": "storm",   "domain_distance": 0.75, "composite_score": 2.9},
        {"word": "fury",    "domain_distance": 0.15, "composite_score": 2.8},
        {"word": "blaze",   "domain_distance": 0.5,  "composite_score": 2.7},  # ambiguous
        {"word": "ire",     "domain_distance": 0.1,  "composite_score": 2.6},
        {"word": "wave",    "domain_distance": 0.8,  "composite_score": 2.5},
        {"word": "wrath",   "domain_distance": 0.18, "composite_score": 2.4},
        {"word": "crack",   "domain_distance": 0.75, "composite_score": 2.3},
    ]
    synonyms = {"rage", "fury", "ire", "wrath"}

    m = compute_word_metrics(suggestions, synonyms)

    # top 10 cross-domain (>0.7): fire(1), volcano(2), storm(4), wave(8), crack(10) = 5/10
    assert m["cross_domain_ratio_top10"] == pytest.approx(0.5)
    # synonym contamination: rage(3), fury(5), ire(7), wrath(9) = 4/10
    assert m["synonym_contamination_top10"] == pytest.approx(0.4)
    # rank_auc: cross ranks [1,2,4,8,10] vs same ranks [3,5,7,9]
    # Each cross-domain rank vs each same-domain rank: how often cross < same
    assert m["rank_auc"] is not None
    assert 0.0 <= m["rank_auc"] <= 1.0
    assert m["total_results"] == 10


def test_compute_word_metrics_empty():
    m = compute_word_metrics([], set())
    assert m["cross_domain_ratio_top10"] == 0.0
    assert m["synonym_contamination_top10"] == 0.0
    assert m["rank_auc"] is None
    assert m["total_results"] == 0


def test_lookup_synonyms_same_synset():
    conn = _make_test_db()
    conn.executemany("INSERT INTO lemmas VALUES (?, ?)", [
        ("flame", "100"),
        ("flare", "100"),
        ("gleam", "200"),
    ])
    conn.commit()

    syns = lookup_synonyms(conn, "blaze")
    assert "flame" in syns
    assert "flare" in syns
    assert "gleam" in syns
    assert "blaze" not in syns  # exclude self


def test_lookup_synonyms_includes_similar_to():
    conn = _make_test_db()
    # Add a similar_to relation from blaze's synset 100 to a new synset 600
    conn.executescript("""
        INSERT INTO synsets VALUES ('600', 'n', 'an intense fire');
        INSERT INTO lemmas VALUES ('inferno', '600');
        INSERT INTO relations VALUES ('100', '600', '40');
    """)
    conn.commit()

    syns = lookup_synonyms(conn, "blaze")
    assert "inferno" in syns  # via similar_to relation


def test_lookup_synonyms_no_results():
    conn = _make_test_db()
    syns = lookup_synonyms(conn, "nonexistent")
    assert syns == set()


def test_aggregate_metrics():
    per_word = [
        {
            "word": "anger", "pos": "n",
            "cross_domain_ratio_top10": 0.6,
            "synonym_contamination_top10": 0.3,
            "rank_auc": 0.8,
            "total_results": 20,
        },
        {
            "word": "fire", "pos": "n",
            "cross_domain_ratio_top10": 0.8,
            "synonym_contamination_top10": 0.1,
            "rank_auc": 0.9,
            "total_results": 15,
        },
        {
            "word": "glow", "pos": "v",
            "cross_domain_ratio_top10": 0.4,
            "synonym_contamination_top10": 0.5,
            "rank_auc": None,  # too few results to compute
            "total_results": 2,
        },
    ]

    agg = aggregate_metrics(per_word)

    assert agg["mean_rank_auc"] == pytest.approx(0.85, abs=0.01)  # (0.8+0.9)/2
    assert agg["mean_cross_domain_ratio"] == pytest.approx(0.6, abs=0.01)
    assert agg["mean_synonym_contamination"] == pytest.approx(0.3, abs=0.01)
    assert agg["words_evaluated"] == 3
    assert agg["words_with_results"] == 3


def test_aggregate_metrics_empty():
    agg = aggregate_metrics([])
    assert agg["mean_rank_auc"] is None
    assert agg["mean_cross_domain_ratio"] == 0.0
    assert agg["words_evaluated"] == 0


def test_evaluate_discrimination_orchestrator():
    """Integration test with mocked API responses."""
    conn = _make_test_db()
    conn.executemany("INSERT INTO lemmas VALUES (?, ?)", [
        ("flame", "100"),
        ("gleam", "200"),
    ])
    conn.commit()

    def mock_get(url, params=None, timeout=None):
        word = params.get("word", "")
        resp = MagicMock()
        resp.status_code = 200

        if word == "blaze":
            resp.json.return_value = {
                "source": "blaze",
                "suggestions": [
                    {"word": "inferno", "domain_distance": 0.2, "composite_score": 3.0,
                     "synset_id": "x1", "tier": "legendary", "overlap_count": 5,
                     "salience_sum": 5.0, "shared_properties": ["hot"]},
                    {"word": "passion", "domain_distance": 0.8, "composite_score": 2.8,
                     "synset_id": "x2", "tier": "strong", "overlap_count": 3,
                     "salience_sum": 3.0, "shared_properties": ["intense"]},
                ],
            }
        elif word == "glow":
            resp.json.return_value = {
                "source": "glow",
                "suggestions": [
                    {"word": "warmth", "domain_distance": 0.8, "composite_score": 2.5,
                     "synset_id": "x3", "tier": "strong", "overlap_count": 3,
                     "salience_sum": 3.0, "shared_properties": ["warm"]},
                ],
            }
        elif word == "swift":
            resp.json.return_value = {
                "source": "swift",
                "suggestions": [
                    {"word": "arrow", "domain_distance": 0.75, "composite_score": 2.0,
                     "synset_id": "x4", "tier": "strong", "overlap_count": 2,
                     "salience_sum": 2.0, "shared_properties": ["quick"]},
                ],
            }
        else:
            resp.status_code = 404
            resp.text = "not found"
            resp.json.return_value = {"error": "not found"}

        return resp

    with patch("evaluate_discrimination.requests.get", side_effect=mock_get):
        results = evaluate_discrimination(
            conn=conn, port=8080, limit=100, min_properties=3,
        )

    # 5 words: blaze, glow, swift (base) + flame, gleam (added lemmas for synsets 100, 200)
    assert results["aggregate"]["words_evaluated"] == 5
    assert "per_word" in results
    assert isinstance(results["per_word"], list)
    assert all("word" in w for w in results["per_word"])
    assert "git_commit" in results


def test_evaluate_discrimination_includes_config():
    conn = _make_test_db()

    with patch("evaluate_discrimination.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "not found"
        mock_get.return_value = mock_resp

        results = evaluate_discrimination(
            conn=conn, port=9090, limit=50, min_properties=3,
        )

    assert results["config"]["limit"] == 50
    assert results["config"]["cross_threshold"] == 0.7
    assert results["config"]["same_threshold"] == 0.3
