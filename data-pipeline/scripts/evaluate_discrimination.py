"""Structural discrimination evaluation for Metaforge forge output.

Measures whether the forge ranks cross-domain candidates higher than
same-domain candidates — the core signal that metaphors beat synonyms.

Usage:
    python evaluate_discrimination.py --db PATH [--port 8080] [-o results.json]
"""
import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path
from typing import Optional

import requests

sys.path.insert(0, str(Path(__file__).parent))
from utils import get_git_commit
from utils import LEXICON_V2

log = logging.getLogger(__name__)


# POS codes in our DB: 'n'=noun, 'v'=verb, 'a'=adjective head, 's'=adjective satellite
_NOUN_POS = ('n',)
_VERB_POS = ('v',)
_ADJ_POS = ('a', 's')


def select_source_words(
    conn: sqlite3.Connection,
    min_properties: int = 3,
    noun_quota: int = 20,
    verb_quota: int = 15,
    adj_quota: int = 15,
) -> list[dict]:
    """Select source words with POS-stratified quotas.

    For each lemma, picks the primary synset (lowest synset_id) and
    counts distinct curated properties across ALL synsets. Filters by
    min_properties, then fills quotas per POS category.

    Returns list of dicts with keys: lemma, pos, primary_synset_id.
    """
    rows = conn.execute("""
        SELECT
            l.lemma,
            MIN(CAST(l.synset_id AS INTEGER)) AS primary_sid,
            COUNT(DISTINCT spc.vocab_id) AS prop_count
        FROM lemmas l
        JOIN synset_properties_curated spc ON l.synset_id = spc.synset_id
        GROUP BY l.lemma
        HAVING prop_count >= ?
        ORDER BY prop_count DESC
    """, (min_properties,)).fetchall()

    # Look up POS for primary synset
    candidates = []
    for lemma, primary_sid, prop_count in rows:
        pos_row = conn.execute(
            "SELECT pos FROM synsets WHERE synset_id = ?",
            (str(primary_sid),)
        ).fetchone()
        if pos_row:
            candidates.append({
                "lemma": lemma,
                "pos": pos_row[0],
                "primary_synset_id": str(primary_sid),
            })

    # Fill POS quotas
    result = []
    counts = {"n": 0, "v": 0, "a": 0}
    quotas = {"n": noun_quota, "v": verb_quota, "a": adj_quota}

    for c in candidates:
        pos = c["pos"]
        # Map satellite adjectives to adjective bucket
        bucket = "a" if pos in _ADJ_POS else pos
        if bucket not in quotas:
            continue
        if counts[bucket] < quotas[bucket]:
            counts[bucket] += 1
            result.append(c)

    return result


def query_forge_results(
    word: str, port: int = 8080, limit: int = 100,
) -> list[dict] | None:
    """Query /forge/suggest and return the suggestions list.

    Returns None on error (distinguishes from genuinely empty results).
    """
    url = f"http://localhost:{port}/forge/suggest"
    try:
        resp = requests.get(url, params={"word": word, "limit": limit}, timeout=30)
    except requests.RequestException as exc:
        log.error("Request failed for %r: %s", word, exc)
        return None

    if resp.status_code != 200:
        log.warning("API %d for %r: %s", resp.status_code, word, resp.text[:200])
        return None

    try:
        return resp.json().get("suggestions", [])
    except (ValueError, AttributeError) as exc:
        log.error("Malformed JSON response for %r: %s", word, exc)
        return None


def _get_distance(suggestion: dict) -> Optional[float]:
    """Extract domain_distance, returning None if missing or not a number."""
    d = suggestion.get("domain_distance")
    if d is None or not isinstance(d, (int, float)):
        return None
    return float(d)


def classify_by_domain(
    suggestions: list[dict],
    cross_threshold: float = 0.7,
    same_threshold: float = 0.3,
) -> tuple[list[dict], list[dict]]:
    """Split suggestions into cross-domain and same-domain sets.

    Suggestions with missing/None domain_distance or values between
    the thresholds are excluded (ambiguous zone).
    """
    cross = []
    same = []
    for s in suggestions:
        d = _get_distance(s)
        if d is None:
            continue
        if d > cross_threshold:
            cross.append(s)
        elif d < same_threshold:
            same.append(s)
    return cross, same


def lookup_synonyms(conn: sqlite3.Connection, lemma: str) -> set[str]:
    """Return synonyms and near-synonyms for a word.

    Combines two sources:
    1. Same-synset lemmas (WordNet synonyms)
    2. Lemmas in synsets linked via similar_to (relation_type 40)

    Excludes the input lemma itself.
    """
    rows = conn.execute("""
        -- Same-synset synonyms
        SELECT DISTINCT l2.lemma
        FROM lemmas l1
        JOIN lemmas l2 ON l1.synset_id = l2.synset_id
        WHERE l1.lemma = ? AND l2.lemma != ?

        UNION

        -- similar_to relation (type 40) synonyms
        SELECT DISTINCT l2.lemma
        FROM lemmas l1
        JOIN relations r ON l1.synset_id = r.source_synset AND r.relation_type = '40'
        JOIN lemmas l2 ON r.target_synset = l2.synset_id
        WHERE l1.lemma = ? AND l2.lemma != ?
    """, (lemma, lemma, lemma, lemma)).fetchall()

    return {row[0] for row in rows}


def compute_rank_auc(
    cross_ranks: list[int], same_ranks: list[int],
) -> Optional[float]:
    """Compute rank-based AUC: P(random cross-domain outranks random same-domain).

    This is the Mann-Whitney U statistic normalised to [0, 1].
    1.0 = perfect separation (all cross-domain ranked above all same-domain).
    0.5 = random (no discrimination).
    0.0 = inverted (all same-domain ranked above all cross-domain).

    Returns None if either list is empty.
    """
    if not cross_ranks or not same_ranks:
        return None

    wins = 0
    total = len(cross_ranks) * len(same_ranks)

    for c in cross_ranks:
        for s in same_ranks:
            if c < s:   # lower rank = better position
                wins += 1
            elif c == s:
                wins += 0.5

    return wins / total


def compute_word_metrics(
    suggestions: list[dict],
    synonyms: set[str],
    cross_threshold: float = 0.7,
    same_threshold: float = 0.3,
) -> dict:
    """Compute discrimination metrics for a single source word's results.

    Primary metric: rank_auc — probability that a random cross-domain
    result outranks a random same-domain result.

    Args:
        suggestions: forge results (pre-sorted by API ranking)
        synonyms: set of known synonym lemmas for the source word
        cross_threshold: domain_distance above which = cross-domain
        same_threshold: domain_distance below which = same-domain
    """
    if not suggestions:
        return {
            "cross_domain_ratio_top10": 0.0,
            "synonym_contamination_top10": 0.0,
            "rank_auc": None,
            "total_results": 0,
        }

    top10 = suggestions[:10]
    n = len(top10)

    # Cross-domain ratio in top 10
    cross_top10 = [
        s for s in top10
        if _get_distance(s) is not None and _get_distance(s) > cross_threshold
    ]
    cross_ratio = len(cross_top10) / n if n > 0 else 0.0

    # Synonym contamination in top 10
    syn_top10 = [s for s in top10 if s.get("word", "") in synonyms]
    syn_ratio = len(syn_top10) / n if n > 0 else 0.0

    # Rank-based AUC across ALL results
    cross_ranks = []
    same_ranks = []
    for rank, s in enumerate(suggestions, 1):
        d = _get_distance(s)
        if d is None:
            continue
        if d > cross_threshold:
            cross_ranks.append(rank)
        elif d < same_threshold:
            same_ranks.append(rank)

    rank_auc = compute_rank_auc(cross_ranks, same_ranks)

    return {
        "cross_domain_ratio_top10": cross_ratio,
        "synonym_contamination_top10": syn_ratio,
        "rank_auc": rank_auc,
        "total_results": len(suggestions),
    }


def aggregate_metrics(per_word: list[dict]) -> dict:
    """Aggregate per-word discrimination metrics into a summary.

    Primary metric: mean_rank_auc — averaged across words that have
    enough results to compute AUC. Higher = better cross-domain separation.
    """
    if not per_word:
        return {
            "mean_rank_auc": None,
            "mean_cross_domain_ratio": 0.0,
            "mean_synonym_contamination": 0.0,
            "words_evaluated": 0,
            "words_with_results": 0,
        }

    n = len(per_word)
    with_results = [w for w in per_word if w["total_results"] > 0]

    mean_cross = sum(w["cross_domain_ratio_top10"] for w in per_word) / n
    mean_syn = sum(w["synonym_contamination_top10"] for w in per_word) / n

    aucs = [w["rank_auc"] for w in per_word if w["rank_auc"] is not None]
    mean_auc = sum(aucs) / len(aucs) if aucs else None

    return {
        "mean_rank_auc": round(mean_auc, 4) if mean_auc is not None else None,
        "mean_cross_domain_ratio": round(mean_cross, 4),
        "mean_synonym_contamination": round(mean_syn, 4),
        "words_evaluated": n,
        "words_with_results": len(with_results),
    }


def evaluate_discrimination(
    conn: sqlite3.Connection,
    port: int = 8080,
    limit: int = 100,
    min_properties: int = 3,
    noun_quota: int = 20,
    verb_quota: int = 15,
    adj_quota: int = 15,
    cross_threshold: float = 0.7,
    same_threshold: float = 0.3,
) -> dict:
    """Run structural discrimination evaluation.

    Selects POS-stratified source words, queries the forge for each,
    computes per-word rank AUC and metrics, aggregates into a summary.
    """
    words = select_source_words(
        conn, min_properties, noun_quota, verb_quota, adj_quota,
    )
    log.info("Selected %d source words for evaluation", len(words))

    per_word = []
    api_failures = 0
    for w in words:
        suggestions = query_forge_results(w["lemma"], port=port, limit=limit)
        if suggestions is None:
            api_failures += 1
            suggestions = []
        synonyms = lookup_synonyms(conn, w["lemma"])
        metrics = compute_word_metrics(
            suggestions, synonyms, cross_threshold, same_threshold,
        )
        metrics["word"] = w["lemma"]
        metrics["pos"] = w["pos"]
        per_word.append(metrics)

        log.info(
            "  %s (%s): %d results, cross=%.2f, syn=%.2f, auc=%s",
            w["lemma"], w["pos"], metrics["total_results"],
            metrics["cross_domain_ratio_top10"],
            metrics["synonym_contamination_top10"],
            f'{metrics["rank_auc"]:.3f}' if metrics["rank_auc"] is not None else "N/A",
        )

    if api_failures > 0:
        failure_pct = api_failures / len(words) * 100
        log.warning(
            "API failures: %d/%d words (%.1f%%) — results may be unreliable",
            api_failures, len(words), failure_pct,
        )

    agg = aggregate_metrics(per_word)
    agg["api_failures"] = api_failures

    return {
        "aggregate": agg,
        "per_word": per_word,
        "git_commit": get_git_commit(),
        "config": {
            "limit": limit,
            "min_properties": min_properties,
            "noun_quota": noun_quota,
            "verb_quota": verb_quota,
            "adj_quota": adj_quota,
            "cross_threshold": cross_threshold,
            "same_threshold": same_threshold,
        },
    }


def main():
    parser = argparse.ArgumentParser(
        description="Structural discrimination evaluation for forge output"
    )
    parser.add_argument(
        "--db", default=str(LEXICON_V2),
        help=f"Path to lexicon_v2.db (default: {LEXICON_V2})",
    )
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--max-words", type=int, default=50,
                        help="Total words (split across POS quotas)")
    parser.add_argument("--output", "-o", default=None)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    # Split max-words into POS quotas (40/30/30 ratio)
    total = args.max_words
    noun_q = round(total * 0.4)
    verb_q = round(total * 0.3)
    adj_q = total - noun_q - verb_q

    conn = sqlite3.connect(args.db)
    results = evaluate_discrimination(
        conn=conn, port=args.port, limit=args.limit,
        noun_quota=noun_q, verb_quota=verb_q, adj_quota=adj_q,
    )
    conn.close()

    agg = results["aggregate"]
    print(f"\n=== Discrimination Eval ({results['git_commit']}) ===")
    print(f"  Words evaluated: {agg['words_evaluated']}")
    print(f"  Mean rank AUC: {agg['mean_rank_auc']:.4f}" if agg["mean_rank_auc"] else "  Mean rank AUC: N/A")
    print(f"  Mean cross-domain ratio (top 10): {agg['mean_cross_domain_ratio']:.4f}")
    print(f"  Mean synonym contamination (top 10): {agg['mean_synonym_contamination']:.4f}")

    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
        print(f"  Results written to {args.output}")


if __name__ == "__main__":
    main()
