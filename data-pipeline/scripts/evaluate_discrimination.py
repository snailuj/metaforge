"""Structural discrimination evaluation for Metaforge forge output.

Measures whether the forge ranks cross-domain candidates higher than
same-domain candidates — the core signal that metaphors beat synonyms.

Usage:
    python evaluate_discrimination.py --db PATH [--port 8080] [-o results.json]
"""
import logging
import sqlite3
from typing import Optional

import requests

log = logging.getLogger(__name__)


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
