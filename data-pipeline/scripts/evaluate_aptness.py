"""Discriminative aptness evaluator for Metaforge metaphor pairings.

Scores (target, vehicle) pairs as apt or inapt by measuring weighted
property overlap in the curated vocabulary. Calibrates the
classification threshold against the MUNCH inapt control distribution
(95th percentile by default) and reports:

  * separation_score   = mean(apt) − mean(inapt)
  * aptness_rate       = fraction of apt pairs scoring above threshold
  * per_pair_scores    = full per-pair detail (class, score, resolved)
  * aggregate          = means + sample sizes
  * config             = thresholds + commit + db path

The score uses salience-weighted Jaccard over shared cluster_ids in
synset_properties_curated. This favours pairs that share *salient*
property clusters (the basis for metaphorical mapping) over pairs that
merely co-occur via low-salience filler properties.

Usage:
    python evaluate_aptness.py \\
        --pairs    data-pipeline/fixtures/metaphor_pairs_v2.json \\
        --controls data-pipeline/fixtures/munch_inapt.jsonl \\
        --db       data-pipeline/output/lexicon_v2.db \\
        --output   data-pipeline/output/aptness_eval.json
"""
import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
from utils import LEXICON_V2, get_git_commit

log = logging.getLogger(__name__)

PIPELINE_DIR = Path(__file__).parent.parent
FIXTURES_DIR = PIPELINE_DIR / "fixtures"
DEFAULT_PAIRS = FIXTURES_DIR / "metaphor_pairs_v2.json"
DEFAULT_CONTROLS = FIXTURES_DIR / "munch_inapt.jsonl"


# --- Synset resolution -------------------------------------------------------

def lookup_primary_synset(conn: sqlite3.Connection, lemma: str) -> Optional[str]:
    """Resolve a lemma to its primary synset_id.

    Prefers the curated vocabulary entry (least-polysemous lemma per synset).
    Falls back to the first synset in the lemmas table when curated vocab
    has no entry. Returns None if the lemma is unknown.
    """
    if not lemma:
        return None
    needle = lemma.strip().lower()

    row = conn.execute(
        "SELECT synset_id FROM property_vocab_curated "
        "WHERE LOWER(lemma) = ? "
        "ORDER BY polysemy ASC LIMIT 1",
        (needle,),
    ).fetchone()
    if row:
        return row[0]

    row = conn.execute(
        "SELECT synset_id FROM lemmas "
        "WHERE LOWER(lemma) = ? "
        "ORDER BY synset_id LIMIT 1",
        (needle,),
    ).fetchone()
    return row[0] if row else None


def _get_properties(conn: sqlite3.Connection, synset_id: str) -> dict[int, float]:
    """Return {cluster_id: salience_sum} for a synset's curated properties."""
    rows = conn.execute(
        "SELECT cluster_id, salience_sum "
        "FROM synset_properties_curated WHERE synset_id = ?",
        (synset_id,),
    ).fetchall()
    return {int(cid): float(sal) for cid, sal in rows}


# --- Pair scoring ------------------------------------------------------------

def score_pair(
    conn: sqlite3.Connection, word_a: str, word_b: str,
) -> Optional[float]:
    """Score a (word_a, word_b) pair by salience-weighted property overlap.

    Returns:
        float in [0, 1]: weighted Jaccard over shared property clusters
        None: either word does not resolve to a synset
        0.0:  both resolve but at least one has no curated properties,
              or there is no cluster overlap
    """
    sa = lookup_primary_synset(conn, word_a)
    sb = lookup_primary_synset(conn, word_b)
    if sa is None or sb is None:
        return None

    pa = _get_properties(conn, sa)
    pb = _get_properties(conn, sb)
    if not pa or not pb:
        return 0.0

    shared = set(pa) & set(pb)
    if not shared:
        return 0.0

    union = set(pa) | set(pb)
    num = sum(min(pa[c], pb[c]) for c in shared)
    den = sum(max(pa.get(c, 0.0), pb.get(c, 0.0)) for c in union)
    return num / den if den > 0 else 0.0


# --- Loaders -----------------------------------------------------------------

def load_apt_pairs(path: str) -> list[dict]:
    """Load apt metaphor pairs from metaphor_pairs_v2.json."""
    with open(path) as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"{path}: expected a JSON array of pairs")
    return data


def load_inapt_controls(path: str) -> list[dict]:
    """Load MUNCH inapt controls from a JSONL file.

    Filters defensively to label == 'inapt'. The MUNCH dataset has known
    quirks (see MEM021) — preprocessing already produced an inapt-only
    file, but we re-filter here so the evaluator is robust to either
    source format.
    """
    rows: list[dict] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("label") == "inapt":
                rows.append(row)
    return rows


# --- Aggregation -------------------------------------------------------------

def _percentile(values: list[float], pct: float) -> float:
    """Return the requested percentile via linear interpolation. 0 if empty."""
    if not values:
        return 0.0
    if pct <= 0:
        return min(values)
    if pct >= 100:
        return max(values)
    s = sorted(values)
    rank = (pct / 100.0) * (len(s) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(s) - 1)
    frac = rank - lo
    return s[lo] * (1 - frac) + s[hi] * frac


def classify_aptness(
    apt_scores: list[float],
    inapt_scores: list[float],
    threshold: float,
) -> dict:
    """Apply a threshold and report aptness + false-positive rates."""
    if not apt_scores:
        aptness_rate = 0.0
    else:
        aptness_rate = sum(1 for s in apt_scores if s > threshold) / len(apt_scores)

    if not inapt_scores:
        fp_rate = 0.0
    else:
        fp_rate = sum(1 for s in inapt_scores if s > threshold) / len(inapt_scores)

    return {
        "threshold": threshold,
        "aptness_rate": aptness_rate,
        "false_positive_rate": fp_rate,
    }


def aggregate_metrics(
    apt_scores: list[float], inapt_scores: list[float],
) -> dict:
    """Mean scores and separation score for the two cohorts.

    separation_score = mean_apt − mean_inapt. A positive value means
    the evaluator scores genuine metaphor pairs higher on average than
    MUNCH inapt confusions.
    """
    mean_apt = sum(apt_scores) / len(apt_scores) if apt_scores else 0.0
    mean_inapt = (
        sum(inapt_scores) / len(inapt_scores) if inapt_scores else 0.0
    )
    return {
        "mean_apt_score": round(mean_apt, 6),
        "mean_inapt_score": round(mean_inapt, 6),
        "separation_score": round(mean_apt - mean_inapt, 6),
        "n_apt": len(apt_scores),
        "n_inapt": len(inapt_scores),
    }


# --- Orchestrator ------------------------------------------------------------

def _score_cohort(
    conn: sqlite3.Connection,
    pairs: list[dict],
    word_a_key: str,
    word_b_key: str,
    cls: str,
) -> tuple[list[float], list[dict], int]:
    """Score every pair in a cohort, returning (scores, per_pair, unresolved)."""
    scores: list[float] = []
    per_pair: list[dict] = []
    unresolved = 0
    for p in pairs:
        a = p.get(word_a_key)
        b = p.get(word_b_key)
        s = score_pair(conn, a, b) if a and b else None
        if s is None:
            unresolved += 1
            per_pair.append({
                "class": cls,
                "word_a": a,
                "word_b": b,
                "score": None,
                "resolved": False,
            })
            continue
        scores.append(s)
        per_pair.append({
            "class": cls,
            "word_a": a,
            "word_b": b,
            "score": round(s, 6),
            "resolved": True,
        })
    return scores, per_pair, unresolved


def evaluate(
    conn: sqlite3.Connection,
    pairs_file: str,
    controls_file: str,
    threshold_percentile: float = 95.0,
    db_path: Optional[str] = None,
) -> dict:
    """Run the full evaluation. Returns the structured result dict."""
    apt_pairs = load_apt_pairs(pairs_file)
    inapt_controls = load_inapt_controls(controls_file)

    log.info(
        "Loaded %d apt pairs, %d inapt controls",
        len(apt_pairs), len(inapt_controls),
    )

    apt_scores, apt_pp, apt_unres = _score_cohort(
        conn, apt_pairs, "source", "target", "apt",
    )
    inapt_scores, inapt_pp, inapt_unres = _score_cohort(
        conn, inapt_controls, "target", "paraphrase", "inapt",
    )

    log.info(
        "Resolved: apt=%d/%d, inapt=%d/%d",
        len(apt_scores), len(apt_pairs),
        len(inapt_scores), len(inapt_controls),
    )

    threshold = _percentile(inapt_scores, threshold_percentile)
    classification = classify_aptness(apt_scores, inapt_scores, threshold)
    agg = aggregate_metrics(apt_scores, inapt_scores)

    return {
        "aptness_rate": round(classification["aptness_rate"], 6),
        "false_positive_rate": round(
            classification["false_positive_rate"], 6,
        ),
        "separation_score": agg["separation_score"],
        "aggregate": {
            **agg,
            "apt_unresolved": apt_unres,
            "inapt_unresolved": inapt_unres,
        },
        "per_pair_scores": apt_pp + inapt_pp,
        "config": {
            "threshold": round(threshold, 6),
            "threshold_percentile": threshold_percentile,
            "pairs_file": pairs_file,
            "controls_file": controls_file,
            "db": db_path,
            "git_commit": get_git_commit(),
        },
    }


# --- CLI ---------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Discriminative aptness evaluator for Metaforge",
    )
    parser.add_argument(
        "--pairs", default=str(DEFAULT_PAIRS),
        help=f"Apt metaphor pairs JSON (default: {DEFAULT_PAIRS})",
    )
    parser.add_argument(
        "--controls", default=str(DEFAULT_CONTROLS),
        help=f"MUNCH inapt controls JSONL (default: {DEFAULT_CONTROLS})",
    )
    parser.add_argument(
        "--db", default=str(LEXICON_V2),
        help=f"Lexicon DB path (default: {LEXICON_V2})",
    )
    parser.add_argument(
        "--threshold-percentile", type=float, default=95.0,
        help="Inapt percentile to use as classification threshold (default: 95)",
    )
    parser.add_argument(
        "--output", "-o", default=None,
        help="Optional output JSON file",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    conn = sqlite3.connect(args.db)
    try:
        result = evaluate(
            conn=conn,
            pairs_file=args.pairs,
            controls_file=args.controls,
            threshold_percentile=args.threshold_percentile,
            db_path=args.db,
        )
    finally:
        conn.close()

    print(json.dumps(result, indent=2))
    print(
        f"\n=== Aptness Eval ({result['config']['git_commit']}) ===",
        file=sys.stderr,
    )
    agg = result["aggregate"]
    print(
        f"  apt:   n={agg['n_apt']:>4}  mean={agg['mean_apt_score']:.4f}  "
        f"unresolved={agg['apt_unresolved']}",
        file=sys.stderr,
    )
    print(
        f"  inapt: n={agg['n_inapt']:>4}  mean={agg['mean_inapt_score']:.4f}  "
        f"unresolved={agg['inapt_unresolved']}",
        file=sys.stderr,
    )
    print(
        f"  separation_score = {result['separation_score']:.4f}",
        file=sys.stderr,
    )
    print(
        f"  threshold (p{args.threshold_percentile:g} of inapt) = "
        f"{result['config']['threshold']:.4f}",
        file=sys.stderr,
    )
    print(
        f"  aptness_rate         = {result['aptness_rate']:.4f}",
        file=sys.stderr,
    )
    print(
        f"  false_positive_rate  = {result['false_positive_rate']:.4f}",
        file=sys.stderr,
    )

    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2)
        print(f"  Results written to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
