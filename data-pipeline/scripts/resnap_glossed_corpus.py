"""Re-snap the already-glossed corpus with the FastText embedding snapper ($0).

The gloss-backfill captured a model gloss per node and snapped via token overlap.
This pass keeps those glosses and re-snaps each non-topic node by FastText cosine
similarity (snap_by_gloss_embed), falling back to token overlap then the existing
synset on no embed. No model calls — just the one-time vector load + cosine.

Outputs NEW *_embed.jsonl files next to the inputs (originals untouched).
chain_signature is preserved, so verdicts/labels stay valid.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from gloss_backfill import resnap_chain_record
from metaphor_graph import snap_by_gloss_embed, snap_by_gloss


def make_embed_snap(conn, vectors):
    """snap_fn(head, gloss): embedding snap, fall back to token overlap."""
    def snap(head, gloss):
        return (snap_by_gloss_embed(conn, head, gloss, vectors)
                or snap_by_gloss(conn, head, gloss))
    return snap


def resnap_file(in_path: str, out_path: str, snap_fn) -> dict:
    n = changed = 0
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(in_path) as fin, open(out_path, "w") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("schema_version") != "chain.v1" or not isinstance(r.get("chain"), list):
                continue
            before = r.get("vehicle_synset_id")
            out = resnap_chain_record(r, snap_fn)
            if out.get("vehicle_synset_id") != before:
                changed += 1
            fout.write(json.dumps(out) + "\n")
            n += 1
    return {"in": in_path, "out": out_path, "records": n, "vehicle_changed": changed}


def main(argv=None) -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))
    from utils import load_fasttext_vectors, FASTTEXT_VEC

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", required=True)
    ap.add_argument("--vec", default=str(FASTTEXT_VEC))
    ap.add_argument("inputs", nargs="+",
                    help="glossed JSONL files; each emits a sibling *_embed.jsonl")
    args = ap.parse_args(argv)

    t0 = time.monotonic()
    print(f"loading FastText vectors from {args.vec} ...")
    vectors = load_fasttext_vectors(args.vec)
    print(f"loaded in {time.monotonic() - t0:.0f}s")
    conn = sqlite3.connect(args.db)
    snap = make_embed_snap(conn, vectors)

    for inp in args.inputs:
        out = inp.replace(".jsonl", "_embed.jsonl")
        res = resnap_file(inp, out, snap)
        print(f"  {Path(inp).name}: {res['records']} records, "
              f"{res['vehicle_changed']} vehicles re-snapped -> {Path(out).name}")
    conn.close()
    print(f"done in {time.monotonic() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
