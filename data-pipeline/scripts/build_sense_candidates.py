"""Precompute candidate senses per endpoint lemma for the sense-check UI.

The grading sidecar is DB-free, so the candidate-sense list the operator picks the
intended sense from is precomputed here and served as
data-pipeline/grading/sense_candidates_provisional.jsonl (one row per lemma:
{lemma, senses:[{synset_id, pos, gloss, tagcount}]}). Senses come from the lexicon's
lemmas⋈synsets; tagcount is the SemCor dominant-sense prior (NULL where untagged),
used only to ORDER the list (most-frequent first) — the rare sense is often the
better metaphor, so this is a hint, not an auto-fix. Re-run after generating chains.
"""

import argparse
import glob
import json
import logging
import sqlite3
from pathlib import Path

log = logging.getLogger(__name__)

_HERE = Path(__file__).resolve()
DEFAULT_DB = str(_HERE.parents[1] / "output" / "lexicon_v2.db")
DEFAULT_CHAINS = sorted(
    glob.glob(str(_HERE.parents[1] / "grading" / "**" / "chain-topics_*.jsonl"), recursive=True)
    + glob.glob(str(_HERE.parents[1] / "grading" / "*chains*.jsonl"))
)
DEFAULT_OUTPUT = str(_HERE.parents[1] / "grading" / "sense_candidates_provisional.jsonl")

# All senses of a lemma + the SemCor tagcount (NULL where untagged), most-frequent
# first. MAX() collapses any duplicate sense_attributes rows for one lemma+synset.
_SENSES_SQL = """
SELECT l.synset_id, s.pos, s.definition,
       (SELECT MAX(sa.tagcount) FROM sense_attributes sa
        WHERE sa.synset_id = l.synset_id AND sa.lemma = l.lemma) AS tagcount
FROM lemmas l
JOIN synsets s ON s.synset_id = l.synset_id
WHERE l.lemma = ?
ORDER BY (tagcount IS NULL), tagcount DESC, l.synset_id
"""


def collect_lemmas(chain_paths: list[str]) -> set[str]:
    """Endpoint lemmas (topic + vehicle) referenced by the chains."""
    lemmas: set[str] = set()
    for path in chain_paths:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    chain = json.loads(line)
                except json.JSONDecodeError:
                    continue
                for key in ("topic", "vehicle"):
                    if chain.get(key):
                        lemmas.add(chain[key])
    return lemmas


def export(conn: sqlite3.Connection, chain_paths: list[str], output: str) -> int:
    """Write {lemma, senses:[...]} for each endpoint lemma with >=1 sense."""
    lemmas = collect_lemmas(chain_paths)
    n = 0
    with open(output, "w", encoding="utf-8") as fh:
        for lemma in sorted(lemmas):
            rows = conn.execute(_SENSES_SQL, (lemma,)).fetchall()
            if not rows:
                continue
            senses = [{"synset_id": r[0], "pos": r[1], "gloss": r[2], "tagcount": r[3]}
                      for r in rows]
            fh.write(json.dumps({"lemma": lemma, "senses": senses}) + "\n")
            n += 1
    return n


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Precompute candidate senses for sense-check.")
    p.add_argument("--db", default=DEFAULT_DB)
    p.add_argument("--chains", nargs="*", default=DEFAULT_CHAINS)
    p.add_argument("-o", "--output", default=DEFAULT_OUTPUT)
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    conn = sqlite3.connect(args.db)
    try:
        n = export(conn, args.chains, args.output)
    finally:
        conn.close()
    log.info("wrote %d lemma candidate rows -> %s", n, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
