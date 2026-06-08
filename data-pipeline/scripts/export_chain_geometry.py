"""Export per-chain path geometry for the grading signal report.

The grading sidecar has no DB/numpy, so the within-topic concordance features
(max_hop_cos, std_hop_cos, path_total_cos ...) are precomputed here against the
typed lexicon and served as data-pipeline/grading/chain_geometry_provisional.jsonl
(keyed by chain_signature). Re-run this after generating new chains.

Reuses the production centroid primitives so the geometry matches the cascade's
notion of semantic distance (no drift).
"""

import argparse
import glob
import json
import logging
import sqlite3
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from evaluate_cascade import _centroid, _cosine_distance  # noqa: E402

log = logging.getLogger(__name__)

_HERE = Path(__file__).resolve()
DEFAULT_DB = str(_HERE.parents[1] / "output" / "lexicon_v2.db")
DEFAULT_CHAINS = sorted(glob.glob(str(_HERE.parents[1] / "grading" / "*chains*.jsonl")))
DEFAULT_OUTPUT = str(_HERE.parents[1] / "grading" / "chain_geometry_provisional.jsonl")


def _node_ids(chain: dict) -> list[str]:
    return [s.get("synset_id") for s in chain.get("chain", []) if s.get("synset_id")]


def chain_geometry(conn: sqlite3.Connection, node_ids: list[str]) -> dict:
    """Centroid hop-distance geometry along one chain path (skips missing centroids)."""
    cents = {n: _centroid(conn, n) for n in set(node_ids)}
    hops = []
    for a, b in zip(node_ids, node_ids[1:]):
        va, vb = cents.get(a), cents.get(b)
        if va is not None and vb is not None:
            d = _cosine_distance(va, vb)
            if d is not None:
                hops.append(d)
    endpoint = None
    if len(node_ids) >= 2:
        va, vb = cents.get(node_ids[0]), cents.get(node_ids[-1])
        if va is not None and vb is not None:
            endpoint = _cosine_distance(va, vb)
    arr = np.array(hops) if hops else None
    return {
        "n_hops": max(0, len(node_ids) - 1),
        "max_hop_cos": float(arr.max()) if arr is not None else None,
        "min_hop_cos": float(arr.min()) if arr is not None else None,
        "mean_hop_cos": float(arr.mean()) if arr is not None else None,
        "std_hop_cos": float(arr.std()) if arr is not None and len(arr) > 1 else None,
        "path_total_cos": float(arr.sum()) if arr is not None else None,
        "endpoint_cos_dist": endpoint,
    }


def export(conn: sqlite3.Connection, chain_paths: list[str], output: str) -> int:
    """Write geometry for every distinct chain (first signature wins). Returns row count."""
    seen: set[str] = set()
    n = 0
    with open(output, "w", encoding="utf-8") as fh:
        for path in chain_paths:
            with open(path, encoding="utf-8") as src:
                for line in src:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        chain = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    sig = chain.get("chain_signature")
                    if not sig or sig in seen or not chain.get("chain"):
                        continue
                    seen.add(sig)
                    fh.write(json.dumps({"chain_signature": sig, **chain_geometry(conn, _node_ids(chain))}) + "\n")
                    n += 1
    return n


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Precompute per-chain path geometry for the signal report.")
    p.add_argument("--db", default=DEFAULT_DB)
    p.add_argument("--chains", nargs="*", default=DEFAULT_CHAINS)
    p.add_argument("-o", "--output", default=DEFAULT_OUTPUT)
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    conn = sqlite3.connect(args.db)
    try:
        centroids = conn.execute("SELECT COUNT(*) FROM synset_centroids").fetchone()[0]
        log.info("db=%s centroids=%d chains=%d", args.db, centroids, len(args.chains))
        n = export(conn, args.chains, args.output)
    finally:
        conn.close()
    log.info("wrote %d chain-geometry rows -> %s", n, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
