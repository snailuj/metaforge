"""Noun-POS sense inventory, vec: admission gate, and grading fan ranking.

Public surface:
  noun_inventory(conn, phrase, head) -> list[dict]
      Noun-only candidate senses for the full phrase, falling back to the head
      lemma. Each dict: {synset_id, sensenum, tagcount, definition, pos}.
      Ranked by (tagcount DESC, sensenum ASC).

  vec_gate(conn, phrase, head) -> bool
      True iff vec: admission is allowed — i.e. noun_inventory is empty for
      both the full phrase and the head lemma (spec §2.3). Logs every True
      admission at INFO so operator can verify the flow.

  rank_fan(senses, intended_synset_id) -> list[dict]
      Grading display ordering: intended sense first (when present), then
      remainder by (tagcount DESC, sensenum ASC) — the order already imposed
      by noun_inventory.
"""
from __future__ import annotations

import logging
import sqlite3

log = logging.getLogger(__name__)

# SQL: noun senses for a single lemma, joined to sense_attributes for tagcount
# and sensenum. sensenum falls back to 9999 when absent so the secondary sort
# puts unattested senses last rather than first.
_NOUN_SENSES_SQL = """
SELECT
    s.synset_id,
    COALESCE(sa.sensenum, 9999)  AS sensenum,
    COALESCE(sa.tagcount, 0)     AS tagcount,
    s.definition,
    s.pos
FROM lemmas l
JOIN synsets s ON s.synset_id = l.synset_id
LEFT JOIN sense_attributes sa
    ON  LOWER(sa.lemma)    = LOWER(l.lemma)
    AND sa.synset_id       = l.synset_id
WHERE s.pos = 'n'
  AND LOWER(l.lemma) = LOWER(?)
ORDER BY COALESCE(sa.tagcount, 0) DESC,
         COALESCE(sa.sensenum, 9999) ASC
"""


def _query_noun_senses(conn: sqlite3.Connection, lemma: str) -> list[dict]:
    """Raw DB lookup for one lemma normalised to lower-case."""
    rows = conn.execute(_NOUN_SENSES_SQL, (lemma.strip().lower(),)).fetchall()
    return [
        {
            "synset_id": row[0],
            "sensenum":  row[1],
            "tagcount":  row[2],
            "definition": row[3],
            "pos":        row[4],
        }
        for row in rows
    ]


def noun_inventory(conn: sqlite3.Connection, phrase: str, head: str) -> list[dict]:
    """Noun-POS candidate senses for `phrase`, falling back to `head`.

    Tries the full phrase first; if that yields nothing, tries the head lemma.
    Returns an empty list only when neither the phrase nor the head has any
    noun sense in the lexicon — the signal `vec_gate` relies on.
    """
    candidates = _query_noun_senses(conn, phrase)
    if candidates:
        return candidates
    if phrase.strip().lower() != head.strip().lower():
        candidates = _query_noun_senses(conn, head)
    return candidates


def vec_gate(conn: sqlite3.Connection, phrase: str, head: str) -> bool:
    """True iff vec: node admission is warranted — no noun sense for phrase or head.

    Logs every True case so admissions are traceable in the operator's run log.
    """
    result = len(noun_inventory(conn, phrase, head)) == 0
    if result:
        log.info("vec: admission — no noun senses for phrase=%r head=%r", phrase, head)
    return result


def rank_fan(senses: list[dict], intended_synset_id: str | None) -> list[dict]:
    """Order the grading display fan: intended sense first, rest by tagcount.

    `senses` is expected to arrive already ordered by (tagcount DESC, sensenum ASC)
    from noun_inventory. This function only promotes the intended sense to
    position 0; the relative order of all other senses is preserved.

    When `intended_synset_id` is None or not found in the list, the input order
    is returned unchanged.
    """
    if not intended_synset_id:
        return list(senses)
    top = [s for s in senses if s["synset_id"] == intended_synset_id]
    rest = [s for s in senses if s["synset_id"] != intended_synset_id]
    return top + rest
