# P3 Discriminative Evaluation — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a two-tier eval harness that measures structural discrimination (cross-domain > same-domain) and LLM-judged aptness, alongside existing MRR regression.

**Architecture:** A new `evaluate_discrimination.py` script follows the same patterns as `evaluate_mrr.py` — queries the running Go API, analyses the response JSON, writes a results JSON. Pure Python, no new dependencies beyond `requests` (already used). LLM judge (Tier 3) deferred to a separate task after Tier 2 is solid.

**Tech Stack:** Python 3, sqlite3, requests, pytest. Go API running on localhost.

**Design doc:** `docs/plans/2026-02-25-P3-discriminative-eval-design.md`
**Council review:** `docs/designs/20260225-cascade-scoring-P3-design-council-review.md`

### Council refinements incorporated

1. **Rank-based AUC separation** as primary Tier 2 metric (replaces `median_score_ratio`)
2. **Wider threshold gap** — same <0.3, cross >0.7 (symmetric ambiguity zone)
3. **Handle None/missing distances** — exclude from counts, don't default to 0
4. **POS-stratified source word selection** — fixed quotas (20N/15V/15A)
5. **Primary synset focus** — cap at lowest synset_id per lemma to avoid polysemy mud
6. **Expanded synonym detection** — same-synset + `similar_to` (relation_type 40) lemmas
7. **Blind LLM judge** — noted for Tier 3: no scores or tiers in prompt
8. **`git_commit` in output JSON** — for tracking across runs

---

### Task 1: Select source words with POS stratification

Build a function that picks ~50 source words with good forge coverage, stratified by POS (20 nouns, 15 verbs, 15 adjectives), focusing on the primary synset per lemma.

**Files:**
- Create: `data-pipeline/scripts/evaluate_discrimination.py`
- Create: `data-pipeline/scripts/test_evaluate_discrimination.py`

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
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest data-pipeline/scripts/test_evaluate_discrimination.py -v`
Expected: FAIL with `ModuleNotFoundError` or `ImportError`

**Step 3: Write minimal implementation**

```python
"""Structural discrimination evaluation for Metaforge forge output.

Measures whether the forge ranks cross-domain candidates higher than
same-domain candidates — the core signal that metaphors beat synonyms.

Usage:
    python evaluate_discrimination.py --db PATH [--port 8080] [-o results.json]
"""
import sqlite3


# POS codes in our DB: 'n'=noun, 'v'=verb, 'a'=adjective head, 's'=adjective satellite
_NOUN_POS = ('n',)
_VERB_POS = ('v',)
_ADJ_POS = ('a', 's')


def select_source_words(
    conn: sqlite3.Connection,
    min_properties: int = 3,
    noun_quota: int = 20,
    verb_quota: int = 15,
    adj_quota: int = 15,
) -> list[dict]:
    """Select source words with POS-stratified quotas.

    For each lemma, picks the primary synset (lowest synset_id) and
    counts distinct curated properties across ALL synsets. Filters by
    min_properties, then fills quotas per POS category.

    Returns list of dicts with keys: lemma, pos, primary_synset_id.
    """
    rows = conn.execute("""
        SELECT
            l.lemma,
            MIN(CAST(l.synset_id AS INTEGER)) AS primary_sid,
            COUNT(DISTINCT spc.vocab_id) AS prop_count
        FROM lemmas l
        JOIN synset_properties_curated spc ON l.synset_id = spc.synset_id
        GROUP BY l.lemma
        HAVING prop_count >= ?
        ORDER BY prop_count DESC
    """, (min_properties,)).fetchall()

    # Look up POS for primary synset
    candidates = []
    for lemma, primary_sid, prop_count in rows:
        pos_row = conn.execute(
            "SELECT pos FROM synsets WHERE synset_id = ?",
            (str(primary_sid),)
        ).fetchone()
        if pos_row:
            candidates.append({
                "lemma": lemma,
                "pos": pos_row[0],
                "primary_synset_id": str(primary_sid),
            })

    # Fill POS quotas
    result = []
    counts = {"n": 0, "v": 0, "a": 0}
    quotas = {"n": noun_quota, "v": verb_quota, "a": adj_quota}

    for c in candidates:
        pos = c["pos"]
        # Map satellite adjectives to adjective bucket
        bucket = "a" if pos in _ADJ_POS else pos
        if bucket not in quotas:
            continue
        if counts[bucket] < quotas[bucket]:
            counts[bucket] += 1
            result.append(c)

    return result
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest data-pipeline/scripts/test_evaluate_discrimination.py -v`
Expected: 4 PASS

**Step 5: Commit**

```bash
git add data-pipeline/scripts/evaluate_discrimination.py data-pipeline/scripts/test_evaluate_discrimination.py
git commit -m "feat(eval): POS-stratified source word selection with primary synset focus"
```

---

### Task 2: Query forge and classify results by domain distance

Fetch forge results for a source word and classify each as cross-domain or same-domain. Use widened thresholds (same <0.3, cross >0.7). Handle None/missing distances by excluding them.

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
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest data-pipeline/scripts/test_evaluate_discrimination.py::test_query_forge_results_returns_suggestions -v`
Expected: FAIL with `ImportError`

**Step 3: Write minimal implementation**

Add to `evaluate_discrimination.py`:

```python
import logging
from typing import Optional

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


def _get_distance(suggestion: dict) -> Optional[float]:
    """Extract domain_distance, returning None if missing or not a number."""
    d = suggestion.get("domain_distance")
    if d is None or not isinstance(d, (int, float)):
        return None
    return float(d)


def classify_by_domain(
    suggestions: list[dict],
    cross_threshold: float = 0.7,
    same_threshold: float = 0.3,
) -> tuple[list[dict], list[dict]]:
    """Split suggestions into cross-domain and same-domain sets.

    Suggestions with missing/None domain_distance or values between
    the thresholds are excluded (ambiguous zone).
    """
    cross = []
    same = []
    for s in suggestions:
        d = _get_distance(s)
        if d is None:
            continue
        if d > cross_threshold:
            cross.append(s)
        elif d < same_threshold:
            same.append(s)
    return cross, same
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest data-pipeline/scripts/test_evaluate_discrimination.py -v`
Expected: 8 PASS (4 old + 4 new)

**Step 5: Commit**

```bash
git add data-pipeline/scripts/evaluate_discrimination.py data-pipeline/scripts/test_evaluate_discrimination.py
git commit -m "feat(eval): query forge + classify by domain with widened thresholds"
```

---

### Task 3: Compute rank-based AUC separation and per-word metrics

For a single source word, compute the primary metric: **rank AUC** (probability a random cross-domain result outranks a random same-domain result), plus cross_domain_ratio_top10 and synonym_contamination.

**Files:**
- Modify: `data-pipeline/scripts/evaluate_discrimination.py`
- Modify: `data-pipeline/scripts/test_evaluate_discrimination.py`

**Step 1: Write the failing test**

```python
from evaluate_discrimination import compute_rank_auc, compute_word_metrics


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
    # Each cross-domain beats: 1 beats all 3, 3 beats 2, 5 beats 0 = 5/9
    assert auc == pytest.approx(5 / 9, abs=0.01)


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
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest data-pipeline/scripts/test_evaluate_discrimination.py::test_compute_rank_auc_perfect_separation -v`
Expected: FAIL with `ImportError`

**Step 3: Write minimal implementation**

Add to `evaluate_discrimination.py`:

```python
def compute_rank_auc(
    cross_ranks: list[int], same_ranks: list[int],
) -> Optional[float]:
    """Compute rank-based AUC: P(random cross-domain outranks random same-domain).

    This is the Mann-Whitney U statistic normalised to [0, 1].
    1.0 = perfect separation (all cross-domain ranked above all same-domain).
    0.5 = random (no discrimination).
    0.0 = inverted (all same-domain ranked above all cross-domain).

    Returns None if either list is empty.
    """
    if not cross_ranks or not same_ranks:
        return None

    wins = 0
    total = len(cross_ranks) * len(same_ranks)

    for c in cross_ranks:
        for s in same_ranks:
            if c < s:   # lower rank = better position
                wins += 1
            elif c == s:
                wins += 0.5

    return wins / total


def compute_word_metrics(
    suggestions: list[dict],
    synonyms: set[str],
    cross_threshold: float = 0.7,
    same_threshold: float = 0.3,
) -> dict:
    """Compute discrimination metrics for a single source word's results.

    Primary metric: rank_auc — probability that a random cross-domain
    result outranks a random same-domain result.

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
            "rank_auc": None,
            "total_results": 0,
        }

    top10 = suggestions[:10]
    n = len(top10)

    # Cross-domain ratio in top 10
    cross_top10 = [
        s for s in top10
        if _get_distance(s) is not None and _get_distance(s) > cross_threshold
    ]
    cross_ratio = len(cross_top10) / n if n > 0 else 0.0

    # Synonym contamination in top 10
    syn_top10 = [s for s in top10 if s.get("word", "") in synonyms]
    syn_ratio = len(syn_top10) / n if n > 0 else 0.0

    # Rank-based AUC across ALL results
    cross_ranks = []
    same_ranks = []
    for rank, s in enumerate(suggestions, 1):
        d = _get_distance(s)
        if d is None:
            continue
        if d > cross_threshold:
            cross_ranks.append(rank)
        elif d < same_threshold:
            same_ranks.append(rank)

    rank_auc = compute_rank_auc(cross_ranks, same_ranks)

    return {
        "cross_domain_ratio_top10": cross_ratio,
        "synonym_contamination_top10": syn_ratio,
        "rank_auc": rank_auc,
        "total_results": len(suggestions),
    }
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest data-pipeline/scripts/test_evaluate_discrimination.py -v`
Expected: 15 PASS

**Step 5: Commit**

```bash
git add data-pipeline/scripts/evaluate_discrimination.py data-pipeline/scripts/test_evaluate_discrimination.py
git commit -m "feat(eval): rank-based AUC separation + per-word discrimination metrics"
```

---

### Task 4: Expanded synonym lookup (same-synset + similar_to)

Build a helper that returns same-synset lemmas AND `similar_to` (relation_type 40) lemmas for richer synonym detection.

**Files:**
- Modify: `data-pipeline/scripts/evaluate_discrimination.py`
- Modify: `data-pipeline/scripts/test_evaluate_discrimination.py`

**Step 1: Write the failing test**

```python
from evaluate_discrimination import lookup_synonyms


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
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest data-pipeline/scripts/test_evaluate_discrimination.py::test_lookup_synonyms_same_synset -v`
Expected: FAIL with `ImportError`

**Step 3: Write minimal implementation**

Add to `evaluate_discrimination.py`:

```python
def lookup_synonyms(conn: sqlite3.Connection, lemma: str) -> set[str]:
    """Return synonyms and near-synonyms for a word.

    Combines two sources:
    1. Same-synset lemmas (WordNet synonyms)
    2. Lemmas in synsets linked via similar_to (relation_type 40)

    Excludes the input lemma itself.
    """
    rows = conn.execute("""
        -- Same-synset synonyms
        SELECT DISTINCT l2.lemma
        FROM lemmas l1
        JOIN lemmas l2 ON l1.synset_id = l2.synset_id
        WHERE l1.lemma = ? AND l2.lemma != ?

        UNION

        -- similar_to relation (type 40) synonyms
        SELECT DISTINCT l2.lemma
        FROM lemmas l1
        JOIN relations r ON l1.synset_id = r.source_synset AND r.relation_type = '40'
        JOIN lemmas l2 ON r.target_synset = l2.synset_id
        WHERE l1.lemma = ? AND l2.lemma != ?
    """, (lemma, lemma, lemma, lemma)).fetchall()

    return {row[0] for row in rows}
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest data-pipeline/scripts/test_evaluate_discrimination.py -v`
Expected: 18 PASS

**Step 5: Commit**

```bash
git add data-pipeline/scripts/evaluate_discrimination.py data-pipeline/scripts/test_evaluate_discrimination.py
git commit -m "feat(eval): expanded synonym lookup with similar_to relations"
```

---

### Task 5: Aggregate metrics across all source words

Combine per-word metrics into a summary report. Primary metric is mean rank AUC.

**Files:**
- Modify: `data-pipeline/scripts/evaluate_discrimination.py`
- Modify: `data-pipeline/scripts/test_evaluate_discrimination.py`

**Step 1: Write the failing test**

```python
from evaluate_discrimination import aggregate_metrics


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
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest data-pipeline/scripts/test_evaluate_discrimination.py::test_aggregate_metrics -v`
Expected: FAIL with `ImportError`

**Step 3: Write minimal implementation**

Add to `evaluate_discrimination.py`:

```python
def aggregate_metrics(per_word: list[dict]) -> dict:
    """Aggregate per-word discrimination metrics into a summary.

    Primary metric: mean_rank_auc — averaged across words that have
    enough results to compute AUC. Higher = better cross-domain separation.
    """
    if not per_word:
        return {
            "mean_rank_auc": None,
            "mean_cross_domain_ratio": 0.0,
            "mean_synonym_contamination": 0.0,
            "words_evaluated": 0,
            "words_with_results": 0,
        }

    n = len(per_word)
    with_results = [w for w in per_word if w["total_results"] > 0]

    mean_cross = sum(w["cross_domain_ratio_top10"] for w in per_word) / n
    mean_syn = sum(w["synonym_contamination_top10"] for w in per_word) / n

    aucs = [w["rank_auc"] for w in per_word if w["rank_auc"] is not None]
    mean_auc = sum(aucs) / len(aucs) if aucs else None

    return {
        "mean_rank_auc": round(mean_auc, 4) if mean_auc is not None else None,
        "mean_cross_domain_ratio": round(mean_cross, 4),
        "mean_synonym_contamination": round(mean_syn, 4),
        "words_evaluated": n,
        "words_with_results": len(with_results),
    }
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest data-pipeline/scripts/test_evaluate_discrimination.py -v`
Expected: 20 PASS

**Step 5: Commit**

```bash
git add data-pipeline/scripts/evaluate_discrimination.py data-pipeline/scripts/test_evaluate_discrimination.py
git commit -m "feat(eval): aggregate discrimination metrics with rank AUC primary"
```

---

### Task 6: Main orchestrator and CLI with git_commit tracking

Wire everything together: select words, query forge, compute metrics, write results JSON with git_commit.

**Files:**
- Modify: `data-pipeline/scripts/evaluate_discrimination.py`
- Modify: `data-pipeline/scripts/test_evaluate_discrimination.py`

**Step 1: Write the failing test**

```python
from evaluate_discrimination import evaluate_discrimination


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

    assert results["aggregate"]["words_evaluated"] >= 2
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
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest data-pipeline/scripts/test_evaluate_discrimination.py::test_evaluate_discrimination_orchestrator -v`
Expected: FAIL with `ImportError`

**Step 3: Write minimal implementation**

Add to `evaluate_discrimination.py`:

```python
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from utils import LEXICON_V2


def _get_git_commit() -> str:
    """Return short git commit hash, or 'unknown' if not in a repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def evaluate_discrimination(
    conn: sqlite3.Connection,
    port: int = 8080,
    limit: int = 100,
    min_properties: int = 3,
    noun_quota: int = 20,
    verb_quota: int = 15,
    adj_quota: int = 15,
    cross_threshold: float = 0.7,
    same_threshold: float = 0.3,
) -> dict:
    """Run structural discrimination evaluation.

    Selects POS-stratified source words, queries the forge for each,
    computes per-word rank AUC and metrics, aggregates into a summary.
    """
    words = select_source_words(
        conn, min_properties, noun_quota, verb_quota, adj_quota,
    )
    log.info("Selected %d source words for evaluation", len(words))

    per_word = []
    for w in words:
        suggestions = query_forge_results(w["lemma"], port=port, limit=limit)
        synonyms = lookup_synonyms(conn, w["lemma"])
        metrics = compute_word_metrics(
            suggestions, synonyms, cross_threshold, same_threshold,
        )
        metrics["word"] = w["lemma"]
        metrics["pos"] = w["pos"]
        per_word.append(metrics)

        log.info(
            "  %s (%s): %d results, cross=%.2f, syn=%.2f, auc=%s",
            w["lemma"], w["pos"], metrics["total_results"],
            metrics["cross_domain_ratio_top10"],
            metrics["synonym_contamination_top10"],
            f'{metrics["rank_auc"]:.3f}' if metrics["rank_auc"] is not None else "N/A",
        )

    agg = aggregate_metrics(per_word)

    return {
        "aggregate": agg,
        "per_word": per_word,
        "git_commit": _get_git_commit(),
        "config": {
            "limit": limit,
            "min_properties": min_properties,
            "noun_quota": noun_quota,
            "verb_quota": verb_quota,
            "adj_quota": adj_quota,
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
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--max-words", type=int, default=50,
                        help="Total words (split across POS quotas)")
    parser.add_argument("--output", "-o", default=None)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    # Split max-words into POS quotas (40/30/30 ratio)
    total = args.max_words
    noun_q = round(total * 0.4)
    verb_q = round(total * 0.3)
    adj_q = total - noun_q - verb_q

    conn = sqlite3.connect(args.db)
    results = evaluate_discrimination(
        conn=conn, port=args.port, limit=args.limit,
        noun_quota=noun_q, verb_quota=verb_q, adj_quota=adj_q,
    )
    conn.close()

    agg = results["aggregate"]
    print(f"\n=== Discrimination Eval ({results['git_commit']}) ===")
    print(f"  Words evaluated: {agg['words_evaluated']}")
    print(f"  Mean rank AUC: {agg['mean_rank_auc']:.4f}" if agg["mean_rank_auc"] else "  Mean rank AUC: N/A")
    print(f"  Mean cross-domain ratio (top 10): {agg['mean_cross_domain_ratio']:.4f}")
    print(f"  Mean synonym contamination (top 10): {agg['mean_synonym_contamination']:.4f}")

    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
        print(f"  Results written to {args.output}")


if __name__ == "__main__":
    main()
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest data-pipeline/scripts/test_evaluate_discrimination.py -v`
Expected: 22 PASS

**Step 5: Commit**

```bash
git add data-pipeline/scripts/evaluate_discrimination.py data-pipeline/scripts/test_evaluate_discrimination.py
git commit -m "feat(eval): discrimination eval orchestrator with git_commit tracking"
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
- `mean_rank_auc` > 0.5 (cross-domain results tend to outrank same-domain)
- `mean_cross_domain_ratio` > 0 (cross-domain results exist in top 10)
- `mean_synonym_contamination` < 1.0 (not all synonyms)
- Per-word breakdowns include POS labels and look reasonable
- `git_commit` is populated
- Output JSON is well-formed

**Step 3: Commit results**

```bash
git add data-pipeline/output/eval_discrimination.json
git commit -m "data: baseline discrimination eval results"
```

---

## Summary

| Task | What | Tests | Council refinement |
|------|------|-------|--------------------|
| 1 | POS-stratified source word selection + primary synset | 4 | §2: POS quotas, primary synset focus |
| 2 | Query forge + classify by domain (widened thresholds) | 4 | §1: symmetric thresholds, §3: handle None distances |
| 3 | Rank-based AUC + per-word metrics | 7 | §1: AUC replaces median_score_ratio |
| 4 | Expanded synonym lookup (same-synset + similar_to) | 3 | §1: similar_to expansion |
| 5 | Aggregate metrics | 2 | — |
| 6 | Orchestrator + CLI + git_commit | 2 | §3: git_commit tracking |
| 7 | Live smoke test | 0 (manual) | — |

**Total: 7 tasks, 22 tests, ~7 commits**

Tier 3 (LLM aptness judge) is a follow-up task after Tier 2 is validated against real data. Council note for Tier 3: **blind the judge** — do not pass composite scores or tier labels.
