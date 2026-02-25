# P3 Discriminative Evaluation — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a two-tier eval harness that measures structural discrimination (cross-domain > same-domain) and LLM-judged aptness, alongside existing MRR regression.

**Architecture:** A new `evaluate_discrimination.py` script follows the same patterns as `evaluate_mrr.py` — queries the running Go API, analyses the response JSON, writes a results JSON. Pure Python, no new dependencies beyond `requests` (already used). LLM judge (Tier 3) deferred to a separate task after Tier 2 is solid.

**Tech Stack:** Python 3, sqlite3, requests, pytest. Go API running on localhost.

**Design doc:** `docs/plans/2026-02-25-P3-discriminative-eval-design.md`

---

### Task 1: Select source words for evaluation

Build a function that picks ~50 source words with good forge coverage from the DB.

**Files:**
- Create: `data-pipeline/scripts/evaluate_discrimination.py`
- Test: `data-pipeline/scripts/test_evaluate_discrimination.py`

**Step 1: Write the failing test**

```python
"""Tests for evaluate_discrimination.py — structural discrimination eval."""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from evaluate_discrimination import select_source_words


def _make_test_db():
    """In-memory DB with lemmas + synsets + curated properties."""
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

        -- Word "blaze" (noun): 2 synsets, 5 curated properties each
        INSERT INTO synsets VALUES ('s1', 'n', 'a strong flame');
        INSERT INTO synsets VALUES ('s2', 'n', 'a bright light');
        INSERT INTO lemmas VALUES ('blaze', 's1');
        INSERT INTO lemmas VALUES ('blaze', 's2');
        INSERT INTO property_vocab_curated VALUES (1, 'hot');
        INSERT INTO property_vocab_curated VALUES (2, 'bright');
        INSERT INTO property_vocab_curated VALUES (3, 'dangerous');
        INSERT INTO property_vocab_curated VALUES (4, 'consuming');
        INSERT INTO property_vocab_curated VALUES (5, 'radiant');
        INSERT INTO synset_properties_curated VALUES ('s1', 1, 1, 1.0);
        INSERT INTO synset_properties_curated VALUES ('s1', 2, 2, 1.0);
        INSERT INTO synset_properties_curated VALUES ('s1', 3, 3, 1.0);
        INSERT INTO synset_properties_curated VALUES ('s1', 4, 4, 1.0);
        INSERT INTO synset_properties_curated VALUES ('s1', 5, 5, 1.0);
        INSERT INTO synset_properties_curated VALUES ('s2', 1, 1, 1.0);
        INSERT INTO synset_properties_curated VALUES ('s2', 2, 2, 1.0);
        INSERT INTO synset_properties_curated VALUES ('s2', 5, 5, 1.0);

        -- Word "dim" (adjective): 1 synset, 1 property (too few)
        INSERT INTO synsets VALUES ('s3', 's', 'lacking light');
        INSERT INTO lemmas VALUES ('dim', 's3');
        INSERT INTO synset_properties_curated VALUES ('s3', 2, 2, 1.0);

        -- Word "glow" (verb): 1 synset, 3 properties
        INSERT INTO synsets VALUES ('s4', 'v', 'emit light');
        INSERT INTO lemmas VALUES ('glow', 's4');
        INSERT INTO synset_properties_curated VALUES ('s4', 1, 1, 1.0);
        INSERT INTO synset_properties_curated VALUES ('s4', 2, 2, 1.0);
        INSERT INTO synset_properties_curated VALUES ('s4', 5, 5, 1.0);
    """)
    conn.commit()
    return conn


def test_select_source_words_filters_by_min_properties():
    conn = _make_test_db()
    words = select_source_words(conn, min_properties=3, max_words=50)
    # "blaze" has 5+3=8 props across synsets, "glow" has 3, "dim" has 1 (excluded)
    assert "blaze" in words
    assert "glow" in words
    assert "dim" not in words


def test_select_source_words_respects_max():
    conn = _make_test_db()
    words = select_source_words(conn, min_properties=1, max_words=2)
    assert len(words) <= 2


def test_select_source_words_returns_list_of_strings():
    conn = _make_test_db()
    words = select_source_words(conn, min_properties=1, max_words=50)
    assert isinstance(words, list)
    assert all(isinstance(w, str) for w in words)
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest data-pipeline/scripts/test_evaluate_discrimination.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'evaluate_discrimination'` or `ImportError`

**Step 3: Write minimal implementation**

```python
"""Structural discrimination evaluation for Metaforge forge output.

Measures whether the forge ranks cross-domain candidates higher than
same-domain candidates — the core signal that metaphors beat synonyms.

Usage:
    python evaluate_discrimination.py --db PATH [--port 8080] [-o results.json]
"""
import sqlite3


def select_source_words(
    conn: sqlite3.Connection,
    min_properties: int = 3,
    max_words: int = 50,
) -> list[str]:
    """Select source words with sufficient curated property coverage.

    Picks lemmas that have at least `min_properties` distinct curated
    properties across all their synsets. Returns up to `max_words`,
    ordered by property count descending (richest words first).
    """
    rows = conn.execute("""
        SELECT l.lemma, COUNT(DISTINCT spc.vocab_id) AS prop_count
        FROM lemmas l
        JOIN synset_properties_curated spc ON l.synset_id = spc.synset_id
        GROUP BY l.lemma
        HAVING prop_count >= ?
        ORDER BY prop_count DESC
        LIMIT ?
    """, (min_properties, max_words)).fetchall()

    return [row[0] for row in rows]
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest data-pipeline/scripts/test_evaluate_discrimination.py -v`
Expected: 3 PASS

**Step 5: Commit**

```bash
git add data-pipeline/scripts/evaluate_discrimination.py data-pipeline/scripts/test_evaluate_discrimination.py
git commit -m "feat(eval): add source word selection for discrimination eval"
```

---

### Task 2: Query forge and classify results by domain distance

Fetch forge results for a source word and classify each as cross-domain or same-domain based on domain_distance thresholds.

**Files:**
- Modify: `data-pipeline/scripts/evaluate_discrimination.py`
- Modify: `data-pipeline/scripts/test_evaluate_discrimination.py`

**Step 1: Write the failing test**

```python
from unittest.mock import patch, MagicMock
from evaluate_discrimination import query_forge_results, classify_by_domain


def _make_forge_response(suggestions):
    return {"source": "anger", "suggestions": suggestions}


def test_query_forge_results_returns_suggestions():
    resp_data = _make_forge_response([
        {"word": "fire", "domain_distance": 0.6, "composite_score": 3.0,
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
    assert results[0]["domain_distance"] == 0.6


def test_query_forge_results_returns_empty_on_error():
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.text = "not found"

    with patch("evaluate_discrimination.requests.get", return_value=mock_resp):
        results = query_forge_results("nonexistent", port=8080, limit=100)

    assert results == []


def test_classify_by_domain():
    suggestions = [
        {"word": "fire", "domain_distance": 0.7, "composite_score": 3.0},
        {"word": "rage", "domain_distance": 0.2, "composite_score": 2.5},
        {"word": "storm", "domain_distance": 0.6, "composite_score": 2.8},
        {"word": "fury", "domain_distance": 0.15, "composite_score": 2.3},
        {"word": "wave", "domain_distance": 0.4, "composite_score": 2.0},  # ambiguous
    ]

    cross, same = classify_by_domain(
        suggestions, cross_threshold=0.5, same_threshold=0.3
    )

    assert len(cross) == 2  # fire (0.7), storm (0.6)
    assert len(same) == 2   # rage (0.2), fury (0.15)
    # "wave" (0.4) is ambiguous — excluded from both
    assert all(s["domain_distance"] > 0.5 for s in cross)
    assert all(s["domain_distance"] < 0.3 for s in same)
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest data-pipeline/scripts/test_evaluate_discrimination.py::test_query_forge_results_returns_suggestions -v`
Expected: FAIL with `ImportError: cannot import name 'query_forge_results'`

**Step 3: Write minimal implementation**

Add to `evaluate_discrimination.py`:

```python
import logging
import requests

log = logging.getLogger(__name__)


def query_forge_results(
    word: str, port: int = 8080, limit: int = 100,
) -> list[dict]:
    """Query /forge/suggest and return the suggestions list.

    Returns empty list on error or missing word.
    """
    url = f"http://localhost:{port}/forge/suggest"
    try:
        resp = requests.get(url, params={"word": word, "limit": limit}, timeout=30)
    except requests.RequestException as exc:
        log.error("Request failed for %r: %s", word, exc)
        return []

    if resp.status_code != 200:
        log.warning("API %d for %r: %s", resp.status_code, word, resp.text[:200])
        return []

    return resp.json().get("suggestions", [])


def classify_by_domain(
    suggestions: list[dict],
    cross_threshold: float = 0.5,
    same_threshold: float = 0.3,
) -> tuple[list[dict], list[dict]]:
    """Split suggestions into cross-domain and same-domain sets.

    Suggestions with domain_distance between the thresholds are
    excluded (ambiguous zone).
    """
    cross = [s for s in suggestions if s.get("domain_distance", 0) > cross_threshold]
    same = [s for s in suggestions if s.get("domain_distance", 0) < same_threshold]
    return cross, same
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest data-pipeline/scripts/test_evaluate_discrimination.py -v`
Expected: 6 PASS (3 old + 3 new)

**Step 5: Commit**

```bash
git add data-pipeline/scripts/evaluate_discrimination.py data-pipeline/scripts/test_evaluate_discrimination.py
git commit -m "feat(eval): query forge and classify results by domain distance"
```

---

### Task 3: Compute per-word discrimination metrics

For a single source word, compute cross_domain_ratio_top10, median_score_ratio, and synonym_contamination.

**Files:**
- Modify: `data-pipeline/scripts/evaluate_discrimination.py`
- Modify: `data-pipeline/scripts/test_evaluate_discrimination.py`

**Step 1: Write the failing test**

```python
from evaluate_discrimination import compute_word_metrics


def test_compute_word_metrics_basic():
    suggestions = [
        # top 10 by position in list (pre-sorted by API)
        {"word": "fire", "domain_distance": 0.7, "composite_score": 3.5},
        {"word": "volcano", "domain_distance": 0.8, "composite_score": 3.2},
        {"word": "rage", "domain_distance": 0.2, "composite_score": 3.0},
        {"word": "storm", "domain_distance": 0.6, "composite_score": 2.9},
        {"word": "fury", "domain_distance": 0.15, "composite_score": 2.8},
        {"word": "blaze", "domain_distance": 0.55, "composite_score": 2.7},
        {"word": "ire", "domain_distance": 0.1, "composite_score": 2.6},
        {"word": "wave", "domain_distance": 0.65, "composite_score": 2.5},
        {"word": "wrath", "domain_distance": 0.18, "composite_score": 2.4},
        {"word": "crack", "domain_distance": 0.7, "composite_score": 2.3},
        # beyond top 10
        {"word": "boom", "domain_distance": 0.9, "composite_score": 2.0},
    ]
    synonyms = {"rage", "fury", "ire", "wrath"}

    m = compute_word_metrics(suggestions, synonyms)

    # top 10: fire(C), volcano(C), rage(S), storm(C), fury(S), blaze(C), ire(S), wave(C), wrath(S), crack(C)
    # Cross-domain (dist > 0.5): fire, volcano, storm, blaze, wave, crack = 6/10
    assert m["cross_domain_ratio_top10"] == pytest.approx(0.6)
    # Synonym contamination: rage, fury, ire, wrath = 4/10
    assert m["synonym_contamination_top10"] == pytest.approx(0.4)
    # median_score_ratio: cross median / same median
    # cross scores: 3.5, 3.2, 2.9, 2.7, 2.5, 2.3 → median = (2.9+2.7)/2 = 2.8
    # same scores: 3.0, 2.8, 2.6, 2.4 → median = (2.8+2.6)/2 = 2.7
    assert m["median_score_ratio"] == pytest.approx(2.8 / 2.7, rel=0.01)
    assert m["total_results"] == 11


def test_compute_word_metrics_no_same_domain():
    suggestions = [
        {"word": "fire", "domain_distance": 0.7, "composite_score": 3.0},
        {"word": "storm", "domain_distance": 0.6, "composite_score": 2.5},
    ]

    m = compute_word_metrics(suggestions, set())

    assert m["cross_domain_ratio_top10"] == pytest.approx(1.0)
    assert m["synonym_contamination_top10"] == pytest.approx(0.0)
    assert m["median_score_ratio"] is None  # no same-domain to compare


def test_compute_word_metrics_empty():
    m = compute_word_metrics([], set())

    assert m["cross_domain_ratio_top10"] == 0.0
    assert m["synonym_contamination_top10"] == 0.0
    assert m["median_score_ratio"] is None
    assert m["total_results"] == 0
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest data-pipeline/scripts/test_evaluate_discrimination.py::test_compute_word_metrics_basic -v`
Expected: FAIL with `ImportError: cannot import name 'compute_word_metrics'`

**Step 3: Write minimal implementation**

Add to `evaluate_discrimination.py`:

```python
import statistics
from typing import Optional


def compute_word_metrics(
    suggestions: list[dict],
    synonyms: set[str],
    cross_threshold: float = 0.5,
    same_threshold: float = 0.3,
) -> dict:
    """Compute discrimination metrics for a single source word's results.

    Args:
        suggestions: forge results (pre-sorted by API ranking)
        synonyms: set of known synonym lemmas for the source word
        cross_threshold: domain_distance above which = cross-domain
        same_threshold: domain_distance below which = same-domain
    """
    if not suggestions:
        return {
            "cross_domain_ratio_top10": 0.0,
            "synonym_contamination_top10": 0.0,
            "median_score_ratio": None,
            "total_results": 0,
        }

    top10 = suggestions[:10]
    n = len(top10)

    # Cross-domain ratio in top 10
    cross_top10 = [s for s in top10 if s.get("domain_distance", 0) > cross_threshold]
    cross_ratio = len(cross_top10) / n if n > 0 else 0.0

    # Synonym contamination in top 10
    syn_top10 = [s for s in top10 if s.get("word", "") in synonyms]
    syn_ratio = len(syn_top10) / n if n > 0 else 0.0

    # Median composite score: cross vs same (across ALL results, not just top 10)
    cross_all, same_all = classify_by_domain(
        suggestions, cross_threshold, same_threshold,
    )
    cross_scores = [s["composite_score"] for s in cross_all]
    same_scores = [s["composite_score"] for s in same_all]

    median_ratio: Optional[float] = None
    if cross_scores and same_scores:
        cross_median = statistics.median(cross_scores)
        same_median = statistics.median(same_scores)
        if same_median > 0:
            median_ratio = cross_median / same_median

    return {
        "cross_domain_ratio_top10": cross_ratio,
        "synonym_contamination_top10": syn_ratio,
        "median_score_ratio": median_ratio,
        "total_results": len(suggestions),
    }
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest data-pipeline/scripts/test_evaluate_discrimination.py -v`
Expected: 9 PASS

**Step 5: Commit**

```bash
git add data-pipeline/scripts/evaluate_discrimination.py data-pipeline/scripts/test_evaluate_discrimination.py
git commit -m "feat(eval): compute per-word discrimination metrics"
```

---

### Task 4: Look up WordNet synonyms for a lemma

Build a helper that returns same-synset lemmas for generating synonym controls.

**Files:**
- Modify: `data-pipeline/scripts/evaluate_discrimination.py`
- Modify: `data-pipeline/scripts/test_evaluate_discrimination.py`

**Step 1: Write the failing test**

```python
from evaluate_discrimination import lookup_synonyms


def test_lookup_synonyms():
    conn = _make_test_db()
    # "blaze" is in synsets s1 and s2. Need other lemmas in those synsets.
    conn.executemany("INSERT INTO lemmas VALUES (?, ?)", [
        ("flame", "s1"),
        ("flare", "s1"),
        ("gleam", "s2"),
    ])
    conn.commit()

    syns = lookup_synonyms(conn, "blaze")
    assert "flame" in syns
    assert "flare" in syns
    assert "gleam" in syns
    assert "blaze" not in syns  # exclude self


def test_lookup_synonyms_no_results():
    conn = _make_test_db()
    syns = lookup_synonyms(conn, "nonexistent")
    assert syns == set()
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest data-pipeline/scripts/test_evaluate_discrimination.py::test_lookup_synonyms -v`
Expected: FAIL with `ImportError`

**Step 3: Write minimal implementation**

Add to `evaluate_discrimination.py`:

```python
def lookup_synonyms(conn: sqlite3.Connection, lemma: str) -> set[str]:
    """Return same-synset lemmas for a word (WordNet synonyms).

    Excludes the input lemma itself.
    """
    rows = conn.execute("""
        SELECT DISTINCT l2.lemma
        FROM lemmas l1
        JOIN lemmas l2 ON l1.synset_id = l2.synset_id
        WHERE l1.lemma = ? AND l2.lemma != ?
    """, (lemma, lemma)).fetchall()

    return {row[0] for row in rows}
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest data-pipeline/scripts/test_evaluate_discrimination.py -v`
Expected: 11 PASS

**Step 5: Commit**

```bash
git add data-pipeline/scripts/evaluate_discrimination.py data-pipeline/scripts/test_evaluate_discrimination.py
git commit -m "feat(eval): add WordNet synonym lookup for controls"
```

---

### Task 5: Aggregate metrics across all source words

Combine per-word metrics into a single discrimination report with means and the MRR regression check.

**Files:**
- Modify: `data-pipeline/scripts/evaluate_discrimination.py`
- Modify: `data-pipeline/scripts/test_evaluate_discrimination.py`

**Step 1: Write the failing test**

```python
from evaluate_discrimination import aggregate_metrics


def test_aggregate_metrics():
    per_word = [
        {
            "word": "anger",
            "cross_domain_ratio_top10": 0.6,
            "synonym_contamination_top10": 0.3,
            "median_score_ratio": 1.1,
            "total_results": 20,
        },
        {
            "word": "fire",
            "cross_domain_ratio_top10": 0.8,
            "synonym_contamination_top10": 0.1,
            "median_score_ratio": 1.3,
            "total_results": 15,
        },
        {
            "word": "light",
            "cross_domain_ratio_top10": 0.4,
            "synonym_contamination_top10": 0.5,
            "median_score_ratio": None,  # no same-domain results
            "total_results": 5,
        },
    ]

    agg = aggregate_metrics(per_word)

    assert agg["mean_cross_domain_ratio"] == pytest.approx(0.6, abs=0.01)
    assert agg["mean_synonym_contamination"] == pytest.approx(0.3, abs=0.01)
    # median_score_ratio: mean of non-None values (1.1 + 1.3) / 2 = 1.2
    assert agg["mean_median_score_ratio"] == pytest.approx(1.2, abs=0.01)
    assert agg["words_evaluated"] == 3
    assert agg["words_with_results"] == 3


def test_aggregate_metrics_empty():
    agg = aggregate_metrics([])

    assert agg["mean_cross_domain_ratio"] == 0.0
    assert agg["words_evaluated"] == 0
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest data-pipeline/scripts/test_evaluate_discrimination.py::test_aggregate_metrics -v`
Expected: FAIL with `ImportError`

**Step 3: Write minimal implementation**

Add to `evaluate_discrimination.py`:

```python
def aggregate_metrics(per_word: list[dict]) -> dict:
    """Aggregate per-word discrimination metrics into a summary.

    Computes means across all evaluated words. Metrics with None values
    (e.g. median_score_ratio when no same-domain results exist) are
    excluded from the mean calculation.
    """
    if not per_word:
        return {
            "mean_cross_domain_ratio": 0.0,
            "mean_synonym_contamination": 0.0,
            "mean_median_score_ratio": None,
            "words_evaluated": 0,
            "words_with_results": 0,
        }

    n = len(per_word)
    with_results = [w for w in per_word if w["total_results"] > 0]

    mean_cross = sum(w["cross_domain_ratio_top10"] for w in per_word) / n
    mean_syn = sum(w["synonym_contamination_top10"] for w in per_word) / n

    ratios = [w["median_score_ratio"] for w in per_word if w["median_score_ratio"] is not None]
    mean_ratio = sum(ratios) / len(ratios) if ratios else None

    return {
        "mean_cross_domain_ratio": round(mean_cross, 4),
        "mean_synonym_contamination": round(mean_syn, 4),
        "mean_median_score_ratio": round(mean_ratio, 4) if mean_ratio is not None else None,
        "words_evaluated": n,
        "words_with_results": len(with_results),
    }
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest data-pipeline/scripts/test_evaluate_discrimination.py -v`
Expected: 13 PASS

**Step 5: Commit**

```bash
git add data-pipeline/scripts/evaluate_discrimination.py data-pipeline/scripts/test_evaluate_discrimination.py
git commit -m "feat(eval): aggregate discrimination metrics across source words"
```

---

### Task 6: Main orchestrator and CLI

Wire everything together: select words, query forge, compute metrics, write results JSON.

**Files:**
- Modify: `data-pipeline/scripts/evaluate_discrimination.py`
- Modify: `data-pipeline/scripts/test_evaluate_discrimination.py`

**Step 1: Write the failing test**

```python
from evaluate_discrimination import evaluate_discrimination


def test_evaluate_discrimination_orchestrator():
    """Integration test with mocked API responses."""
    conn = _make_test_db()
    # Add synonym data
    conn.executemany("INSERT INTO lemmas VALUES (?, ?)", [
        ("flame", "s1"),
        ("gleam", "s2"),
    ])
    conn.commit()

    # Mock forge responses for "blaze" and "glow"
    def mock_get(url, params=None, timeout=None):
        word = params.get("word", "")
        resp = MagicMock()
        resp.status_code = 200

        if word == "blaze":
            resp.json.return_value = {
                "source": "blaze",
                "suggestions": [
                    {"word": "inferno", "domain_distance": 0.3, "composite_score": 3.0,
                     "synset_id": "x1", "tier": "legendary", "overlap_count": 5,
                     "salience_sum": 5.0, "shared_properties": ["hot"]},
                    {"word": "passion", "domain_distance": 0.7, "composite_score": 2.8,
                     "synset_id": "x2", "tier": "strong", "overlap_count": 3,
                     "salience_sum": 3.0, "shared_properties": ["intense"]},
                ],
            }
        elif word == "glow":
            resp.json.return_value = {
                "source": "glow",
                "suggestions": [
                    {"word": "warmth", "domain_distance": 0.6, "composite_score": 2.5,
                     "synset_id": "x3", "tier": "strong", "overlap_count": 3,
                     "salience_sum": 3.0, "shared_properties": ["warm"]},
                ],
            }
        else:
            resp.status_code = 404
            resp.text = "not found"
            resp.json.return_value = {"error": "not found"}

        return resp

    with patch("evaluate_discrimination.requests.get", side_effect=mock_get):
        results = evaluate_discrimination(
            conn=conn, port=8080, limit=100,
            min_properties=3, max_words=50,
        )

    assert results["aggregate"]["words_evaluated"] >= 2
    assert "per_word" in results
    assert isinstance(results["per_word"], list)
    assert all("word" in w for w in results["per_word"])
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest data-pipeline/scripts/test_evaluate_discrimination.py::test_evaluate_discrimination_orchestrator -v`
Expected: FAIL with `ImportError`

**Step 3: Write minimal implementation**

Add to `evaluate_discrimination.py`:

```python
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from utils import LEXICON_V2


def evaluate_discrimination(
    conn: sqlite3.Connection,
    port: int = 8080,
    limit: int = 100,
    min_properties: int = 3,
    max_words: int = 50,
    cross_threshold: float = 0.5,
    same_threshold: float = 0.3,
) -> dict:
    """Run structural discrimination evaluation.

    Selects source words, queries the forge for each, computes per-word
    metrics, and aggregates into a summary.
    """
    words = select_source_words(conn, min_properties, max_words)
    log.info("Selected %d source words for evaluation", len(words))

    per_word = []
    for word in words:
        suggestions = query_forge_results(word, port=port, limit=limit)
        synonyms = lookup_synonyms(conn, word)
        metrics = compute_word_metrics(
            suggestions, synonyms, cross_threshold, same_threshold,
        )
        metrics["word"] = word
        per_word.append(metrics)

        log.info(
            "  %s: %d results, cross_ratio=%.2f, syn_contam=%.2f",
            word, metrics["total_results"],
            metrics["cross_domain_ratio_top10"],
            metrics["synonym_contamination_top10"],
        )

    agg = aggregate_metrics(per_word)

    return {
        "aggregate": agg,
        "per_word": per_word,
        "config": {
            "limit": limit,
            "min_properties": min_properties,
            "max_words": max_words,
            "cross_threshold": cross_threshold,
            "same_threshold": same_threshold,
        },
    }


def main():
    parser = argparse.ArgumentParser(
        description="Structural discrimination evaluation for forge output"
    )
    parser.add_argument(
        "--db", default=str(LEXICON_V2),
        help=f"Path to lexicon_v2.db (default: {LEXICON_V2})",
    )
    parser.add_argument("--port", type=int, default=8080, help="API port (default: 8080)")
    parser.add_argument("--limit", type=int, default=100, help="Max results per query (default: 100)")
    parser.add_argument("--max-words", type=int, default=50, help="Source words to evaluate (default: 50)")
    parser.add_argument("--output", "-o", default=None, help="Output JSON file")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    conn = sqlite3.connect(args.db)
    results = evaluate_discrimination(
        conn=conn, port=args.port, limit=args.limit, max_words=args.max_words,
    )
    conn.close()

    print(f"\n=== Discrimination Eval ===")
    print(f"  Words evaluated: {results['aggregate']['words_evaluated']}")
    print(f"  Mean cross-domain ratio (top 10): {results['aggregate']['mean_cross_domain_ratio']:.4f}")
    print(f"  Mean synonym contamination (top 10): {results['aggregate']['mean_synonym_contamination']:.4f}")
    ratio = results["aggregate"]["mean_median_score_ratio"]
    print(f"  Mean median score ratio (cross/same): {ratio:.4f}" if ratio else "  Mean median score ratio: N/A")

    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
        print(f"  Results written to {args.output}")


if __name__ == "__main__":
    main()
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest data-pipeline/scripts/test_evaluate_discrimination.py -v`
Expected: 14 PASS

**Step 5: Commit**

```bash
git add data-pipeline/scripts/evaluate_discrimination.py data-pipeline/scripts/test_evaluate_discrimination.py
git commit -m "feat(eval): discrimination eval orchestrator and CLI"
```

---

### Task 7: Live smoke test against running API

Run the eval script against the live API and verify it produces sensible output.

**Files:** None (manual verification)

**Step 1: Run against live API**

Run:
```bash
cd /home/agent/projects/metaforge/.worktrees/feat--steal-shamelessly
python data-pipeline/scripts/evaluate_discrimination.py \
  --db data-pipeline/output/lexicon_v2.db \
  --port 8080 --max-words 10 --limit 20 \
  -o data-pipeline/output/eval_discrimination.json -v
```

**Step 2: Verify output**

Check that:
- Script completes without errors
- `mean_cross_domain_ratio` > 0 (cross-domain results exist)
- `mean_synonym_contamination` < 1.0 (not all synonyms)
- Per-word breakdowns look reasonable
- Output JSON is well-formed

**Step 3: Commit results**

```bash
git add data-pipeline/output/eval_discrimination.json
git commit -m "data: baseline discrimination eval results"
```

---

## Summary

| Task | What | Tests added |
|------|------|-------------|
| 1 | Source word selection | 3 |
| 2 | Query forge + classify by domain | 3 |
| 3 | Per-word metrics | 3 |
| 4 | Synonym lookup | 2 |
| 5 | Aggregate metrics | 2 |
| 6 | Orchestrator + CLI | 1 |
| 7 | Live smoke test | 0 (manual) |

**Total: 7 tasks, 14 tests, ~6 commits**

Tier 3 (LLM aptness judge) is a follow-up task after Tier 2 is validated against real data.
