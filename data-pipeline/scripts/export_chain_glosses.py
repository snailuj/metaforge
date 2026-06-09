"""Export per-synset gloss + POS for the synsets appearing in grading chains.

The grading sidecar is DB-free, so the gloss/POS the grader needs to disambiguate
a topic's sense (is "antique" a noun or an adjective?) is precomputed here from
the lexicon's synsets table and served as
data-pipeline/grading/chain_glosses_provisional.jsonl (one row per synset_id:
{synset_id, pos, definition}). Re-run after generating new chains.
"""

import argparse
import glob
import json
import logging
import sqlite3
import sys
from pathlib import Path

log = logging.getLogger(__name__)

_HERE = Path(__file__).resolve()
DEFAULT_DB = str(_HERE.parents[1] / "output" / "lexicon_v2.db")
DEFAULT_CHAINS = sorted(glob.glob(str(_HERE.parents[1] / "grading" / "*chains*.jsonl")))
DEFAULT_OUTPUT = str(_HERE.parents[1] / "grading" / "chain_glosses_provisional.jsonl")


def collect_synset_ids(chain_paths: list[str]) -> set[str]:
    """All synset_ids referenced by the chains: endpoints + every step."""
    ids: set[str] = set()
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
                for key in ("topic_synset_id", "vehicle_synset_id"):
                    if chain.get(key):
                        ids.add(chain[key])
                for step in chain.get("chain", []):
                    if step.get("synset_id"):
                        ids.add(step["synset_id"])
    return ids


def export(conn: sqlite3.Connection, chain_paths: list[str], output: str) -> int:
    """Write {synset_id, pos, definition} for each chain synset present in synsets."""
    ids = collect_synset_ids(chain_paths)
    n = 0
    with open(output, "w", encoding="utf-8") as fh:
        for synset_id in sorted(ids):
            row = conn.execute(
                "SELECT pos, definition FROM synsets WHERE synset_id = ?", (synset_id,)
            ).fetchone()
            if row is None:
                continue
            fh.write(json.dumps({"synset_id": synset_id, "pos": row[0], "definition": row[1]}) + "\n")
            n += 1
    return n


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Precompute synset gloss/POS for the grading signal UI.")
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
    log.info("wrote %d gloss rows -> %s", n, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
