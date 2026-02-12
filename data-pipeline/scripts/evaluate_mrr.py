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
import logging
import os
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

import requests

sys.path.insert(0, str(Path(__file__).parent))
from enrich_pipeline import run_pipeline
from enrich_properties import run_enrichment
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


def collect_required_synset_ids(
    conn: sqlite3.Connection, pairs: list[dict]
) -> set[str]:
    """Resolve all metaphor pair lemmas to synset IDs.

    Unlike resolve_pair_synsets, this collects synset IDs from ALL pairs
    including one-sided ones (where only source or only target is found).
    This ensures the enrichment covers every word that could contribute.
    """
    ids = set()
    for pair in pairs:
        ids.update(_lookup_synsets(conn, pair["source"]))
        ids.update(_lookup_synsets(conn, pair["target"]))
    return ids


# --- Query the Forge API -----------------------------------------------------

def query_forge_rank(
    source_word: str,
    target_word: str,
    target_synsets: set[str],
    port: int = 9090,
    threshold: float = 0.7,
    limit: int = 200,
) -> Optional[int]:
    """Query /forge/suggest and find the rank of the target.

    The API takes a word (lemma), not a synset_id.  We match the target
    by both word and synset_id — word match catches cases where the API
    picked a different synset for the same lemma.

    Returns 1-based rank or None if not found / error.
    """
    url = f"http://localhost:{port}/forge/suggest"
    params = {"word": source_word, "threshold": threshold, "limit": limit}
    try:
        resp = requests.get(url, params=params, timeout=30)
    except requests.RequestException as exc:
        log.error("Request failed for %r: %s", source_word, exc)
        return None

    if resp.status_code != 200:
        log.warning("API %d for %r: %s", resp.status_code, source_word, resp.text[:200])
        return None

    data = resp.json()
    suggestions = data.get("suggestions", [])

    for i, s in enumerate(suggestions):
        if s.get("synset_id") in target_synsets or s.get("word") == target_word:
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
    enrichment_file: str = None,
    pairs_file: str = None,
    threshold: float = 0.7,
    limit: int = 200,
    port: int = 9090,
    output_file: str = None,
    enrich_size: int = None,
    enrich_model: str = "haiku",
    enrich_batch_size: int = 20,
    enrich_delay: float = 1.0,
    prompt_template: str = None,
    coverage_threshold: float = 0.9,
    verbose: bool = False,
) -> dict:
    """Run full MRR evaluation.

    1. Load metaphor pairs and resolve synset IDs
    2. Restore baseline into temp DB
    3. Run enrichment (LLM if --enrich, or from pre-computed file)
    4. Start Go API, query pairs, compute MRR
    5. Output results

    Two modes:
      --enrichment FILE  Use a pre-computed enrichment JSON
      --enrich --size N  Run LLM enrichment, guaranteeing metaphor pair
                         synsets are included in the enrichment set
    """
    if enrichment_file is None and enrich_size is None:
        raise ValueError("Provide --enrichment FILE or --enrich --size N")

    if pairs_file is None:
        pairs_file = str(DEFAULT_PAIRS)

    mode = "enrich" if enrich_size is not None else "file"
    print(f"=== MRR Evaluation ===")
    print(f"  Mode: {mode}")
    if enrichment_file:
        print(f"  Enrichment: {enrichment_file}")
    else:
        print(f"  Enrich: size={enrich_size}, model={enrich_model}")
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
    print(f"  Required synset IDs: {len(all_synset_ids)}")

    # Step 2: Get enrichment JSON (LLM or pre-computed)
    enrichment_coverage = None
    enrichment_succeeded = None
    enrichment_failed = None
    if enrich_size is not None:
        print(f"  Running LLM enrichment (size={enrich_size}, "
              f"required={len(all_synset_ids)})...")
        enrich_result = run_enrichment(
            size=enrich_size,
            batch_size=enrich_batch_size,
            model=enrich_model,
            delay=enrich_delay,
            output_file=OUTPUT_DIR / "eval_enrichment.json",
            required_synset_ids=all_synset_ids,
            prompt_template=prompt_template,
            verbose=verbose,
        )
        enrichment_file = enrich_result.output_file
        enrichment_coverage = enrich_result.coverage
        enrichment_succeeded = enrich_result.succeeded
        enrichment_failed = enrich_result.failed
        print(f"  Enrichment coverage: {enrichment_coverage:.2%} "
              f"({enrichment_succeeded}/{enrich_result.requested})")

    # Step 3: Run downstream pipeline on the work DB
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

        # Step 4: Query each testable pair (API takes word, not synset_id)
        ranks = []
        per_pair = []
        for pair in testable:
            rank = query_forge_rank(
                source_word=pair["source"],
                target_word=pair["target"],
                target_synsets=pair["target_synsets"],
                port=port,
                threshold=threshold,
                limit=limit,
            )

            rr = 1.0 / rank if rank is not None else 0.0
            ranks.append(rank)
            per_pair.append({
                "source": pair["source"],
                "target": pair["target"],
                "rank": rank,
                "reciprocal_rank": rr,
                "tier": pair.get("tier", ""),
            })
            print(f"    {pair['source']} → {pair['target']}: rank={rank}, rr={rr:.3f}")

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

    # Determine validity based on enrichment coverage
    valid = True
    invalid_reason = None
    if enrichment_coverage is not None and enrichment_coverage < coverage_threshold:
        valid = False
        invalid_reason = (
            f"Enrichment coverage {enrichment_coverage:.2%} "
            f"below threshold {coverage_threshold:.0%}"
        )

    results = {
        "mrr": round(mrr, 4),
        "testable_pairs": len(testable),
        "skipped_pairs": len(skipped),
        "per_pair": per_pair,
        "skipped": skipped,
        "secondary": secondary,
        "valid": valid,
        "config": {
            "enrichment_file": enrichment_file,
            "threshold": threshold,
            "limit": limit,
        },
    }

    if enrichment_coverage is not None:
        results["enrichment_coverage"] = round(enrichment_coverage, 4)
        results["enrichment_succeeded"] = enrichment_succeeded
        results["enrichment_failed"] = enrichment_failed

    if invalid_reason:
        results["invalid_reason"] = invalid_reason

    if output_file:
        with open(output_file, "w") as f:
            json.dump(results, f, indent=2)
        print(f"  Results written to {output_file}")

    return results


def main():
    parser = argparse.ArgumentParser(description="MRR evaluation for enrichment quality")

    # Enrichment source: pre-computed file OR live LLM run
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--enrichment",
        help="Pre-computed enrichment JSON file",
    )
    source.add_argument(
        "--enrich", action="store_true",
        help="Run LLM enrichment (requires --size)",
    )

    # Enrich-mode options
    parser.add_argument(
        "--size", type=int, default=None,
        help="Enrichment size (required with --enrich)",
    )
    parser.add_argument(
        "--model", type=str, default="haiku",
        help="Claude model for enrichment (default: haiku)",
    )
    parser.add_argument(
        "--batch-size", type=int, default=20,
        help="Synsets per LLM call (default: 20)",
    )
    parser.add_argument(
        "--delay", type=float, default=1.0,
        help="Seconds between batches (default: 1.0)",
    )

    # Common options
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

    if args.enrich and args.size is None:
        parser.error("--enrich requires --size")

    evaluate(
        enrichment_file=args.enrichment,
        pairs_file=args.pairs,
        threshold=args.threshold,
        limit=args.limit,
        port=args.port,
        output_file=args.output,
        enrich_size=args.size if args.enrich else None,
        enrich_model=args.model,
        enrich_batch_size=args.batch_size,
        enrich_delay=args.delay,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
