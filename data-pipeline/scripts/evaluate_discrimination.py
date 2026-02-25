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
