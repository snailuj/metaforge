"""MRR evaluation orchestrator for Metaforge enrichment quality.

Evaluates enrichment quality by measuring how well the Forge API
can suggest metaphor targets from curated source→target pairs.

MRR (Mean Reciprocal Rank): for each pair, query /forge/suggest with
the source word and find the rank of the target. MRR = mean(1/rank).

Usage:
    python evaluate_mrr.py --enrichment FILE [--pairs FILE] [--threshold 0.7]
                           [--limit 200] [--port 9090] [--output FILE]
"""
import argparse
import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import requests

sys.path.insert(0, str(Path(__file__).parent))
from enrich_pipeline import run_pipeline
from utils import OUTPUT_DIR, FASTTEXT_VEC


# --- Default paths -----------------------------------------------------------

PIPELINE_DIR = Path(__file__).parent.parent
FIXTURES_DIR = PIPELINE_DIR / "fixtures"
DEFAULT_PAIRS = FIXTURES_DIR / "metaphor_pairs.json"
BASELINE_SQL = OUTPUT_DIR / "baseline_lexicon.sql"
EVAL_WORK_DB = OUTPUT_DIR / "eval_work.db"
API_DIR = PIPELINE_DIR.parent / "api"


# --- Load and validate metaphor pairs ----------------------------------------

def load_metaphor_pairs(path: str) -> list[dict]:
    """Load metaphor pairs JSON, validate required fields."""
    with open(path) as f:
        pairs = json.load(f)

    for i, pair in enumerate(pairs):
        if "source" not in pair:
            raise ValueError(f"Pair {i}: missing 'source' field")
        if "target" not in pair:
            raise ValueError(f"Pair {i}: missing 'target' field")

    return pairs


# --- Resolve synset IDs for metaphor pairs -----------------------------------

def resolve_pair_synsets(
    conn: sqlite3.Connection, pairs: list[dict]
) -> tuple[list[dict], list[dict], set[str]]:
    """Resolve lemma → synset IDs for each pair.

    Returns:
        testable: pairs with synsets found for both source and target
        skipped: pairs missing synsets (with reason)
        all_synset_ids: set of all synset IDs needed for enrichment
    """
    testable = []
    skipped = []
    all_synset_ids = set()

    for pair in pairs:
        source_synsets = _lookup_synsets(conn, pair["source"])
        target_synsets = _lookup_synsets(conn, pair["target"])

        if not source_synsets:
            skipped.append({
                "source": pair["source"],
                "target": pair["target"],
                "reason": "source not found",
            })
            continue
        if not target_synsets:
            skipped.append({
                "source": pair["source"],
                "target": pair["target"],
                "reason": "target not found",
            })
            continue

        all_synset_ids.update(source_synsets)
        all_synset_ids.update(target_synsets)

        testable.append({
            **pair,
            "source_synsets": source_synsets,
            "target_synsets": target_synsets,
        })

    return testable, skipped, all_synset_ids


def _lookup_synsets(conn: sqlite3.Connection, lemma: str) -> set[str]:
    """Look up synset IDs for a lemma."""
    rows = conn.execute(
        "SELECT synset_id FROM lemmas WHERE lemma = ?", (lemma,)
    ).fetchall()
    return {r[0] for r in rows}


# --- Query the Forge API -----------------------------------------------------

def query_forge_rank(
    source_synset: str,
    target_synsets: set[str],
    port: int = 9090,
    threshold: float = 0.7,
    limit: int = 200,
) -> Optional[int]:
    """Query /forge/suggest and find the rank of any target synset.

    Returns 1-based rank or None if not found / error.
    """
    try:
        resp = requests.get(
            f"http://localhost:{port}/forge/suggest",
            params={
                "synset_id": source_synset,
                "threshold": threshold,
                "limit": limit,
            },
            timeout=30,
        )
    except requests.RequestException:
        return None

    if resp.status_code != 200:
        return None

    data = resp.json()
    suggestions = data.get("suggestions", [])

    for i, s in enumerate(suggestions):
        if s.get("synset_id") in target_synsets:
            return i + 1  # 1-based rank

    return None


# --- MRR computation ---------------------------------------------------------

def compute_mrr(ranks: list[Optional[int]]) -> float:
    """Compute MRR from a list of ranks (None → reciprocal rank 0)."""
    if not ranks:
        return 0.0

    rr_sum = sum(1.0 / r if r is not None else 0.0 for r in ranks)
    return rr_sum / len(ranks)


# --- Secondary metrics -------------------------------------------------------

def compute_secondary_metrics(conn: sqlite3.Connection) -> dict:
    """Compute secondary quality metrics from the enriched DB."""
    unique = conn.execute(
        "SELECT COUNT(*) FROM property_vocabulary"
    ).fetchone()[0]

    # Hapax: properties appearing in exactly 1 synset
    hapax = conn.execute("""
        SELECT COUNT(*) FROM (
            SELECT property_id, COUNT(synset_id) as cnt
            FROM synset_properties
            GROUP BY property_id
            HAVING cnt = 1
        )
    """).fetchone()[0]

    total_synsets = conn.execute(
        "SELECT COUNT(DISTINCT synset_id) FROM synset_properties"
    ).fetchone()[0]

    total_links = conn.execute(
        "SELECT COUNT(*) FROM synset_properties"
    ).fetchone()[0]

    avg_props = total_links / total_synsets if total_synsets > 0 else 0

    return {
        "unique_properties": unique,
        "hapax_count": hapax,
        "hapax_rate": hapax / unique if unique > 0 else 0,
        "avg_properties_per_synset": avg_props,
    }


# --- Server management -------------------------------------------------------

def build_server_command(db_path: str, port: int = 9090) -> list[str]:
    """Build the Go API server command."""
    return [
        "go", "run", "./cmd/metaforge",
        "--db", db_path,
        "--port", str(port),
    ]


def start_server(db_path: str, port: int = 9090) -> subprocess.Popen:
    """Start the Go API server as a subprocess."""
    cmd = build_server_command(db_path, port)
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(API_DIR),
    )
    return proc


def stop_server(proc: subprocess.Popen) -> None:
    """Stop the server gracefully with SIGTERM."""
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def wait_for_health(
    port: int = 9090, timeout: float = 30.0, interval: float = 0.5
) -> None:
    """Wait for the server health endpoint to respond 200."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = requests.get(f"http://localhost:{port}/health", timeout=2)
            if resp.status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(interval)

    raise TimeoutError(f"Server on port {port} not healthy after {timeout}s")


# --- Main orchestrator -------------------------------------------------------

def evaluate(
    enrichment_file: str,
    pairs_file: str = None,
    threshold: float = 0.7,
    limit: int = 200,
    port: int = 9090,
    output_file: str = None,
) -> dict:
    """Run full MRR evaluation.

    1. Load metaphor pairs and resolve synset IDs
    2. Restore baseline into temp DB
    3. Run enrichment pipeline
    4. Start Go API, query pairs, compute MRR
    5. Output results
    """
    if pairs_file is None:
        pairs_file = str(DEFAULT_PAIRS)

    print(f"=== MRR Evaluation ===")
    print(f"  Enrichment: {enrichment_file}")
    print(f"  Pairs: {pairs_file}")

    # Step 1: Load pairs and resolve synsets from baseline
    pairs = load_metaphor_pairs(pairs_file)

    # Restore baseline for synset lookup
    print("  Restoring baseline for synset resolution...")
    db_path = str(EVAL_WORK_DB)
    if EVAL_WORK_DB.exists():
        EVAL_WORK_DB.unlink()
    subprocess.run(
        ["sqlite3", db_path],
        input=Path(BASELINE_SQL).read_text(),
        text=True,
        check=True,
    )

    conn = sqlite3.connect(db_path)
    testable, skipped, all_synset_ids = resolve_pair_synsets(conn, pairs)
    conn.close()
    print(f"  Testable pairs: {len(testable)}, skipped: {len(skipped)}")

    # Step 2: Run enrichment pipeline on the work DB
    print("  Running enrichment pipeline...")
    run_pipeline(
        db_path=db_path,
        enrichment_file=enrichment_file,
        fasttext_vec=str(FASTTEXT_VEC),
    )

    # Step 3: Start API server
    print(f"  Starting API server on port {port}...")
    server = start_server(db_path, port)
    try:
        wait_for_health(port, timeout=60)
        print("  Server ready.")

        # Step 4: Query each testable pair
        ranks = []
        per_pair = []
        for pair in testable:
            best_rank = None
            for src_synset in pair["source_synsets"]:
                r = query_forge_rank(
                    source_synset=src_synset,
                    target_synsets=pair["target_synsets"],
                    port=port,
                    threshold=threshold,
                    limit=limit,
                )
                if r is not None and (best_rank is None or r < best_rank):
                    best_rank = r

            rr = 1.0 / best_rank if best_rank is not None else 0.0
            ranks.append(best_rank)
            per_pair.append({
                "source": pair["source"],
                "target": pair["target"],
                "rank": best_rank,
                "reciprocal_rank": rr,
                "tier": pair.get("tier", ""),
            })
            print(f"    {pair['source']} → {pair['target']}: rank={best_rank}, rr={rr:.3f}")

        # Step 5: Compute MRR
        mrr = compute_mrr(ranks)
        print(f"\n  MRR = {mrr:.4f}")

    finally:
        print("  Stopping server...")
        stop_server(server)

    # Step 6: Secondary metrics
    conn = sqlite3.connect(db_path)
    secondary = compute_secondary_metrics(conn)
    conn.close()

    results = {
        "mrr": round(mrr, 4),
        "testable_pairs": len(testable),
        "skipped_pairs": len(skipped),
        "per_pair": per_pair,
        "skipped": skipped,
        "secondary": secondary,
        "config": {
            "enrichment_file": enrichment_file,
            "threshold": threshold,
            "limit": limit,
        },
    }

    if output_file:
        with open(output_file, "w") as f:
            json.dump(results, f, indent=2)
        print(f"  Results written to {output_file}")

    return results


def main():
    parser = argparse.ArgumentParser(description="MRR evaluation for enrichment quality")
    parser.add_argument(
        "--enrichment", required=True,
        help="Enrichment JSON file (from enrich_properties.py)",
    )
    parser.add_argument(
        "--pairs", default=None,
        help=f"Metaphor pairs JSON (default: {DEFAULT_PAIRS})",
    )
    parser.add_argument(
        "--threshold", type=float, default=0.7,
        help="Cosine distance threshold (default: 0.7)",
    )
    parser.add_argument(
        "--limit", type=int, default=200,
        help="Max suggestions per query (default: 200)",
    )
    parser.add_argument(
        "--port", type=int, default=9090,
        help="API server port (default: 9090)",
    )
    parser.add_argument(
        "--output", "-o", default=None,
        help="Output results JSON file",
    )
    args = parser.parse_args()

    evaluate(
        enrichment_file=args.enrichment,
        pairs_file=args.pairs,
        threshold=args.threshold,
        limit=args.limit,
        port=args.port,
        output_file=args.output,
    )


if __name__ == "__main__":
    main()
