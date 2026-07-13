"""Precompute a sense-inventory JSONL from a set of chain files.

Output: one JSON line per distinct normalised phrase that appears at any chain
step, keyed by `normalise_phrase(phrase)`:

    {"key": "glance", "senses": [{synset_id, sensenum, tagcount, definition, pos}, ...]}

Lines are written in lexicographic key order so the output is deterministic and
diffable. The file is written atomically (tmp → rename) so a partially-written
inventory is never observed by readers.

Usage:
    python build_sense_inventories.py \\
        --db  PATH/TO/lexicon_v2.db \\
        --chains GLOB_1 [GLOB_2 ...] \\
        --out PATH/TO/sense_inventories_provisional.jsonl
"""
from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "grading_sidecar"))

import sense_inventory as si
from models import normalise_phrase  # canonical canonicaliser — must stay in sync

log = logging.getLogger(__name__)


def _collect_phrases(chain_globs: list[str]) -> set[str]:
    """Yield the normalised key for every step across all chain files.

    Emits BOTH the phrase key and the head-lemma key. Multi-word phrases rarely
    have their own synset, so the UI's fan falls back to the head lemma's senses
    ('senses of "wound"' for the step 'buried wound') — that fallback is dead
    unless the head lemma is a key in this file, since it may never appear as a
    standalone single-word step elsewhere in the corpus.
    """
    keys: set[str] = set()
    for pattern in chain_globs:
        for path in glob.glob(pattern):
            try:
                with open(path, encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            rec = json.loads(line)
                        except json.JSONDecodeError:
                            log.warning("skipping malformed JSON line in %s", path)
                            continue
                        for step in rec.get("chain", []):
                            for token in (step.get("phrase"), step.get("head")):
                                if token:
                                    keys.add(normalise_phrase(token))
            except OSError as exc:
                log.warning("cannot read chain file %s: %s", path, exc)
    return keys


def build(db: str, chains: list[str], out: str) -> dict:
    """Build the sense inventory and write it atomically to `out`.

    Returns a summary dict: {phrases_queried, phrases_with_senses, vec_phrases}.
    Idempotent: calling with the same inputs produces byte-identical output.
    """
    conn = sqlite3.connect(db)
    try:
        phrases = _collect_phrases(chains)
        log.info("build_sense_inventories: %d distinct phrases collected", len(phrases))

        rows: list[dict] = []
        phrases_with_senses = 0
        vec_phrases = 0

        for key in sorted(phrases):
            # Use the normalised key as both phrase and head for the inventory
            # lookup (phrases here are already canonicalised; head fallback is
            # handled inside noun_inventory when phrase != head, but for a
            # pre-normalised single key we pass it for both arguments).
            senses = si.noun_inventory(conn, key, key)
            row = {"key": key, "senses": senses}
            rows.append(row)
            if senses:
                phrases_with_senses += 1
            else:
                vec_phrases += 1

        # Atomic write: stream to a tmp file, then os.replace (POSIX rename is
        # atomic on the same filesystem — partial writes are never visible).
        tmp = out + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        os.replace(tmp, out)

        summary = {
            "phrases_queried": len(phrases),
            "phrases_with_senses": phrases_with_senses,
            "vec_phrases": vec_phrases,
        }
        log.info("build_sense_inventories: done — %s", summary)
        return summary
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Precompute noun sense inventories from metaphor chain files."
    )
    parser.add_argument("--db", required=True, help="Path to lexicon_v2.db")
    parser.add_argument("--chains", nargs="+", required=True,
                        help="Glob pattern(s) for chain JSONL files")
    parser.add_argument("--out", required=True,
                        help="Output JSONL path (written atomically)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )

    summary = build(args.db, args.chains, args.out)
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
