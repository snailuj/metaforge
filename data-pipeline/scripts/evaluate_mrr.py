"""MRR evaluation orchestrator for Metaforge enrichment quality.

Evaluates enrichment quality by measuring how well the Forge API
can suggest metaphor targets from curated source→target pairs.

MRR (Mean Reciprocal Rank): for each pair, query /forge/suggest with
the source word and find the rank of the target. MRR = mean(1/rank).

Usage:
    python evaluate_mrr.py --enrichment FILE [--pairs FILE]
                           [--limit 200] [--port 9090] [--output FILE]
"""
import argparse
import json
import logging
import os
import shutil
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
DEFAULT_PAIRS = FIXTURES_DIR / "metaphor_pairs_v2.json"
DEFAULT_BASELINE_SQL = OUTPUT_DIR / "lexicon_v2.sql"
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
    limit: int = 200,
) -> Optional[int]:
    """Query /forge/suggest and find the rank of the target.

    The API takes a word (lemma), not a synset_id.  We match the target
    by both word and synset_id — word match catches cases where the API
    picked a different synset for the same lemma.

    Returns 1-based rank or None if not found / error.
    """
    url = f"http://localhost:{port}/forge/suggest"
    params = {"word": source_word, "limit": limit}
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
    """Compute secondary quality metrics from the curated vocabulary."""
    unique = conn.execute(
        "SELECT COUNT(*) FROM property_vocab_curated"
    ).fetchone()[0]

    # Hapax: properties appearing in exactly 1 synset
    hapax = conn.execute("""
        SELECT COUNT(*) FROM (
            SELECT vocab_id, COUNT(synset_id) as cnt
            FROM synset_properties_curated
            GROUP BY vocab_id
            HAVING cnt = 1
        )
    """).fetchone()[0]

    total_synsets = conn.execute(
        "SELECT COUNT(DISTINCT synset_id) FROM synset_properties_curated"
    ).fetchone()[0]

    total_links = conn.execute(
        "SELECT COUNT(*) FROM synset_properties_curated"
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
    eval_subset: list[str] = None,
    db: str = None,
    baseline_sql: str = None,
) -> dict:
    """Run full MRR evaluation.

    Three modes:
      --db PATH          Use a pre-built DB directly (skip restore/enrich/pipeline)
      --enrichment FILE  Restore baseline, run pipeline with pre-computed enrichment
      --enrich --size N  Restore baseline, run LLM enrichment + pipeline

    The --db mode is useful for re-running just the server + query step
    against an already-built database (e.g. after a crash).
    """
    if pairs_file is None:
        pairs_file = str(DEFAULT_PAIRS)

    # --- Mode: pre-built DB (eval-only, no pipeline) ---
    if db is not None:
        db_path = str(Path(db).resolve())
        print(f"=== MRR Evaluation (eval-only) ===")
        print(f"  DB: {db_path}")
        print(f"  Pairs: {pairs_file}")

        pairs = load_metaphor_pairs(pairs_file)
        if eval_subset:
            subset_set = set(eval_subset)
            pairs = [p for p in pairs if f"{p['source']}:{p['target']}" in subset_set]

        conn = sqlite3.connect(db_path)
        testable, skipped, all_synset_ids = resolve_pair_synsets(conn, pairs)
        conn.close()
        print(f"  Testable pairs: {len(testable)}, skipped: {len(skipped)}")

        enrichment_coverage = None
        enrichment_succeeded = None
        enrichment_failed = None

    # --- Mode: restore + enrich/pipeline ---
    else:
        if shutil.which("sqlite3") is None:
            raise RuntimeError(
                "sqlite3 CLI not found on PATH. "
                "Install it (e.g. apt install sqlite3) before running evaluation."
            )

        if enrichment_file is None and enrich_size is None:
            raise ValueError("Provide --db PATH, --enrichment FILE, or --enrich --size N")

        baseline = baseline_sql or str(DEFAULT_BASELINE_SQL)

        mode = "enrich" if enrich_size is not None else "file"
        print(f"=== MRR Evaluation ===")
        print(f"  Mode: {mode}")
        print(f"  Baseline: {baseline}")
        if enrichment_file:
            print(f"  Enrichment: {enrichment_file}")
        else:
            print(f"  Enrich: size={enrich_size}, model={enrich_model}")
        print(f"  Pairs: {pairs_file}")

        # Step 1: Load pairs and resolve synsets from baseline
        pairs = load_metaphor_pairs(pairs_file)

        if eval_subset:
            subset_set = set(eval_subset)
            pairs = [p for p in pairs if f"{p['source']}:{p['target']}" in subset_set]

        print("  Restoring baseline for synset resolution...")
        db_path = str(EVAL_WORK_DB)
        if EVAL_WORK_DB.exists():
            EVAL_WORK_DB.unlink()
        subprocess.run(
            ["sqlite3", db_path],
            input=Path(baseline).read_text(),
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
                resume=True,
                output_file=OUTPUT_DIR / "eval_enrichment.json",
                required_synset_ids=all_synset_ids,
                prompt_template=prompt_template,
                verbose=verbose,
                db_path=db_path,
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

    # Start API server
    print(f"  Starting API server on port {port}...")
    server = start_server(db_path, port)
    try:
        try:
            wait_for_health(port, timeout=60)
        except TimeoutError:
            # Dump server output to help diagnose startup failures
            rc = server.poll()
            print(f"  Server failed to become healthy (exit code: {rc})")
            try:
                stdout_out, stderr_out = server.communicate(timeout=5)
                if stdout_out:
                    print(f"  Server stdout:\n{stdout_out[:2000]}")
                if stderr_out:
                    print(f"  Server stderr:\n{stderr_out[:2000]}")
            except Exception:
                pass
            raise
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

    # Enrichment source: pre-built DB, pre-computed file, or live LLM run
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--db",
        help="Pre-built DB — skip restore/enrich/pipeline, run eval only",
    )
    source.add_argument(
        "--enrichment",
        help="Pre-computed enrichment JSON file",
    )
    source.add_argument(
        "--enrich", action="store_true",
        help="Run LLM enrichment (requires --size)",
    )

    parser.add_argument(
        "--baseline-sql",
        default=None,
        help=f"SQL dump to restore as baseline (default: {DEFAULT_BASELINE_SQL})",
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
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable verbose/debug logging",
    )
    args = parser.parse_args()

    if args.enrich and args.size is None:
        parser.error("--enrich requires --size")

    evaluate(
        enrichment_file=args.enrichment,
        pairs_file=args.pairs,
        limit=args.limit,
        port=args.port,
        output_file=args.output,
        enrich_size=args.size if args.enrich else None,
        enrich_model=args.model,
        enrich_batch_size=args.batch_size,
        enrich_delay=args.delay,
        verbose=args.verbose,
        db=args.db,
        baseline_sql=args.baseline_sql,
    )


if __name__ == "__main__":
    # Parse --verbose/-v early so we can set log level before main()
    log_level = logging.DEBUG if "-v" in sys.argv or "--verbose" in sys.argv else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")
    main()
