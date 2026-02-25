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
