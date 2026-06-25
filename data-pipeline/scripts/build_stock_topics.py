#!/usr/bin/env python3
"""Assemble the broad "stock" topic pool for emit-the-sense generation.

Unlike build_handpicked_topics (a hand-authored gem list), this enriches
essentially the whole *usable* noun lexicon: every distinct single-word
curated-noun lemma whose familiarity rarity is `common` or `unusual`
(the `rare` tail is obscure-technical — venthole/chlamydia — and dropped).

Each lemma is resolved to its dominant noun sense + WordNet gloss via the
shared resolver (build_handpicked_topics.resolve, trust_curation=True so
metaphor-rich nouns with many rare verb senses — ache/hunger/doom — survive).
Output is the vetted-topics shape the generation runner consumes:
    {"n": N, "topics": [{"word", "topic_synset_id", "gloss"}, ...]}

Deterministic, idempotent, no LLM spend. Dedupes against already-generated
cohorts so a fresh run never re-bills covered topics.
"""
from __future__ import annotations

import argparse
import glob
import json
import sqlite3
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_handpicked_topics import resolve  # noqa: E402  (shared noun-sense resolver)

RARITY_KEEP = ("common", "unusual")


def tagcount_dominant(conn, lemma):
    """(synset_id, gloss) for the highest-SemCor-tagcount NOUN sense, or None.

    This is the dominant-everyday-sense prior: `year` -> "a period of 365 days"
    (tagcount 426), not the least-polysemous "graduating class" (tagcount 1).
    Returns None when SemCor never tagged any noun sense of the lemma."""
    row = conn.execute(
        """
        SELECT sa.synset_id, s.definition
        FROM sense_attributes sa
        JOIN synsets s ON s.synset_id = sa.synset_id
        WHERE sa.lemma = ? AND s.pos = 'n' AND sa.tagcount IS NOT NULL
        ORDER BY sa.tagcount DESC, sa.synset_id ASC
        LIMIT 1
        """,
        (lemma,),
    ).fetchone()
    return (str(row[0]), row[1]) if row else None


def load_covered(paths: list[str]) -> set[str]:
    """topic_synset_ids already present in any chain.v1 JSONL or topics JSON."""
    covered: set[str] = set()
    for pat in paths:
        for f in glob.glob(pat, recursive=True):
            try:
                text = Path(f).read_text()
            except OSError:
                continue
            stripped = text.lstrip()
            if stripped.startswith("{") and '"topics"' in stripped[:200]:
                # a vetted-topics JSON file
                try:
                    for t in json.loads(text).get("topics", []):
                        covered.add(str(t["topic_synset_id"]))
                except (json.JSONDecodeError, KeyError, TypeError):
                    pass
                continue
            for line in text.splitlines():  # chain.v1 JSONL
                line = line.strip()
                if not line:
                    continue
                try:
                    covered.add(str(json.loads(line)["topic_synset_id"]))
                except (json.JSONDecodeError, KeyError, TypeError):
                    pass
    return covered


def candidate_lemmas(conn, rarity_keep) -> list[tuple[str, str, int]]:
    """Distinct single-word curated-noun lemmas in the kept rarity bands,
    ordered most-recognisable first (common before unusual, then BNC freq)."""
    placeholders = ",".join("?" for _ in rarity_keep)
    rows = conn.execute(
        f"""
        SELECT DISTINCT c.lemma,
               COALESCE(f.rarity, 'unusual') AS rarity,
               COALESCE(b.freq, 0)           AS freq
        FROM property_vocab_curated c
        LEFT JOIN frequencies      f ON f.lemma = c.lemma
        LEFT JOIN bnc_frequencies  b ON b.lemma = c.lemma AND b.pos = 'n'
        WHERE c.pos = 'n'
          AND INSTR(c.lemma, '_') = 0
          AND INSTR(c.lemma, ' ') = 0
          AND COALESCE(f.rarity, 'unusual') IN ({placeholders})
        """,
        tuple(rarity_keep),
    ).fetchall()
    rank = {"common": 0, "unusual": 1, "rare": 2}
    rows.sort(key=lambda r: (rank.get(r[1], 1), -r[2], r[0]))
    return rows


def build(conn, covered: set[str], rarity_keep, limit: int | None, require_tagcount: bool):
    topics, seen_sids = [], set()
    dropped = {"no_noun": 0, "no_tagcount": 0, "covered": 0, "dup_synset": 0}
    for lemma, _rarity, _freq in candidate_lemmas(conn, rarity_keep):
        # SemCor tagcount gives the dominant-everyday sense; fall back to the
        # least-polysemous resolver only when SemCor never tagged the lemma.
        resolved = tagcount_dominant(conn, lemma)
        tagged = resolved is not None
        if not tagged:
            if require_tagcount:
                dropped["no_tagcount"] += 1
                continue
            sid, gloss = resolve(conn, lemma, trust_curation=True)
            resolved = (str(sid), gloss) if sid is not None else None
        if resolved is None:
            dropped["no_noun"] += 1
            continue
        sid, gloss = resolved
        if sid in covered:
            dropped["covered"] += 1
            continue
        if sid in seen_sids:
            dropped["dup_synset"] += 1
            continue
        seen_sids.add(sid)
        topics.append({"word": lemma, "topic_synset_id": sid, "gloss": gloss,
                       "semcor_tagged": tagged})
        if limit and len(topics) >= limit:
            break
    return topics, dropped


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument(
        "--exclude", nargs="*", default=[],
        help="Glob(s) of chain.v1 JSONL or vetted-topics JSON to dedupe against.",
    )
    ap.add_argument("--rarity", default=",".join(RARITY_KEEP),
                    help="Comma-separated rarity bands to keep.")
    ap.add_argument("--require-tagcount", action="store_true",
                    help="Keep only lemmas with a SemCor-tagged noun sense "
                         "(the clean, dominant-sense-resolvable core).")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    rarity_keep = tuple(r.strip() for r in args.rarity.split(",") if r.strip())
    covered = load_covered(args.exclude)
    conn = sqlite3.connect(args.db)
    try:
        topics, dropped = build(conn, covered, rarity_keep, args.limit, args.require_tagcount)
    finally:
        conn.close()

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    json.dump({"n": len(topics), "topics": topics}, open(args.output, "w"), indent=2)
    print(f"kept {len(topics)} topics -> {args.output}")
    print(f"excluded {len(covered)} already-covered synsets; dropped {dropped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
