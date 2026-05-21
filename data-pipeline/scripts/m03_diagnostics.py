"""M03 pre-flight diagnostics — concreteness-delta + centroid-distance
distributions on the apt vs inapt cohort.

These two distributions set the M03 cascade's initial sweep ranges:

  * **Concreteness gate threshold range** is informed by the apt-pair
    signed concreteness delta distribution. If apt pairs cluster at
    delta ≈ 1.5 Brysbaert points and inapt at ≈ 0, a gate threshold
    of 1.0 should preserve most apt while culling many inapt.
  * **Domain-distance re-rank ``d_target``** is initialised at the
    median apt-pair centroid cosine distance; ``d_window`` from the
    spread.

They also produce Tier-3 Lakoff-prediction-test data — the predictions
are claims about the world (apt metaphors show concrete-source asymmetry;
apt metaphors cluster at intermediate domain distance), not artefacts
of the harness. The diagnostic prints both per-cohort summaries and the
hypothesis-test statistics so the M03 roadmap's Tier-3 criteria can be
evaluated independently of any cascade-implementation work.

Operationally read-only against the M03 baseline DB
(``lexicon_v2.db.pre-purge-20260517``). Designed to run in seconds.
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import struct
import sys
import statistics
from pathlib import Path
from typing import Iterable

sys.path.insert(0, str(Path(__file__).parent))
from evaluate_aptness import (
    lookup_primary_synset,
    load_apt_pairs,
    load_inapt_controls,
    DEFAULT_PAIRS,
    DEFAULT_CONTROLS,
)
from utils import OUTPUT_DIR

log = logging.getLogger(__name__)

PIPELINE_DIR = Path(__file__).parent.parent
DEFAULT_DB = PIPELINE_DIR / "output" / "lexicon_v2.db.pre-purge-20260517"


# --- Cohort iteration --------------------------------------------------------

def _iter_apt(apt_pairs: list[dict]) -> Iterable[tuple[str, str, dict]]:
    """Yield (source_lemma, target_lemma, raw_row) for each apt pair.

    metaphor_pairs_v2.json uses 'source' for the abstract concept being
    explained and 'target' for the concrete vehicle — i.e. for the
    metaphor "ANGER IS FIRE", row['source'] == 'anger' and
    row['target'] == 'fire'. Lakoff prediction #1 expects
    concreteness(target) > concreteness(source) on apt pairs.
    """
    for row in apt_pairs:
        s = (row.get("source") or "").strip()
        t = (row.get("target") or "").strip()
        if s and t:
            yield s, t, row


def _iter_inapt(inapt_controls: list[dict]) -> Iterable[tuple[str, str, dict]]:
    """Yield (target_lemma, paraphrase_lemma, raw_row) for each inapt control.

    munch_inapt.jsonl uses 'target' (the metaphor word in context) and
    'paraphrase' (the unrelated substitute). No inherent Lakoff
    directionality — the cohort exists as a discriminative reference.
    """
    for row in inapt_controls:
        t = (row.get("target") or "").strip()
        p = (row.get("paraphrase") or "").strip()
        if t and p:
            yield t, p, row


# --- Concreteness diagnostics ------------------------------------------------

def _concreteness(conn: sqlite3.Connection, synset_id: str) -> tuple[float | None, str | None]:
    """Return (score, source) for a synset, or (None, None) if missing."""
    row = conn.execute(
        "SELECT score, source FROM synset_concreteness WHERE synset_id = ?",
        (synset_id,),
    ).fetchone()
    return (float(row[0]), row[1]) if row else (None, None)


def concreteness_delta_diagnostic(
    conn: sqlite3.Connection,
    apt_pairs: list[dict],
    inapt_controls: list[dict],
    brysbaert_only: bool = False,
) -> dict:
    """Compute signed concreteness deltas per cohort.

    For apt pairs the signed delta is concreteness(target) - concreteness(source).
    Lakoff prediction #1 says this is significantly > 0 on apt pairs (apt
    metaphors map concrete vehicles to abstract concepts).

    For inapt pairs the signed delta is concreteness(target) -
    concreteness(paraphrase). No Lakoff direction expected here; the
    distribution serves as the null reference.

    Set ``brysbaert_only=True`` to restrict to Brysbaert ground-truth
    rows and exclude FastText-regression-imputed scores. Useful for the
    "is imputed concreteness trustworthy enough to drive the gate?" check.
    """
    def _collect(
        iterator,
        a_label: str, b_label: str,
        cohort_label: str,
    ) -> dict:
        deltas: list[float] = []
        a_scores: list[float] = []
        b_scores: list[float] = []
        skipped_missing = 0
        skipped_unresolved = 0
        skipped_non_brysbaert = 0
        for word_a, word_b, _row in iterator:
            sa = lookup_primary_synset(conn, word_a)
            sb = lookup_primary_synset(conn, word_b)
            if sa is None or sb is None:
                skipped_unresolved += 1
                continue
            ca, src_a = _concreteness(conn, sa)
            cb, src_b = _concreteness(conn, sb)
            if ca is None or cb is None:
                skipped_missing += 1
                continue
            if brysbaert_only and (src_a != "brysbaert" or src_b != "brysbaert"):
                skipped_non_brysbaert += 1
                continue
            deltas.append(cb - ca)
            a_scores.append(ca)
            b_scores.append(cb)
        return {
            "cohort": cohort_label,
            "a_label": a_label,
            "b_label": b_label,
            "n_total_pairs": skipped_unresolved + skipped_missing + skipped_non_brysbaert + len(deltas),
            "n_scored": len(deltas),
            "skipped_unresolved": skipped_unresolved,
            "skipped_missing_concreteness": skipped_missing,
            "skipped_non_brysbaert": skipped_non_brysbaert,
            "signed_delta": _summarise(deltas),
            "a_distribution": _summarise(a_scores),
            "b_distribution": _summarise(b_scores),
        }

    return {
        "brysbaert_only": brysbaert_only,
        "apt": _collect(_iter_apt(apt_pairs), "source", "target", "apt"),
        "inapt": _collect(_iter_inapt(inapt_controls), "target", "paraphrase", "inapt"),
    }


# --- Centroid-distance diagnostics -------------------------------------------

def _centroid(conn: sqlite3.Connection, synset_id: str) -> list[float] | None:
    """Return the 300-d centroid vector for a synset, or None if missing.

    synset_centroids.centroid is a packed float32 BLOB (300 floats =
    1200 bytes). Decoded into a Python list for diagnostic use.
    """
    row = conn.execute(
        "SELECT centroid FROM synset_centroids WHERE synset_id = ?",
        (synset_id,),
    ).fetchone()
    if row is None or row[0] is None or len(row[0]) == 0:
        # Harmonised with evaluate_cascade._centroid (evaluate_cascade.py:174):
        # both siblings return None silently for empty BLOBs. The cascade's
        # matching guard could log.debug on this path for parity, but the
        # M03 diagnostic prefers a silent skip to match the cascade's
        # production behaviour exactly.
        return None
    blob = row[0]
    if len(blob) % 4 != 0:
        log.warning("malformed centroid blob for %s: %d bytes (not multiple of 4)",
                    synset_id, len(blob))
        return None
    n_floats = len(blob) // 4
    return list(struct.unpack(f"{n_floats}f", blob))


def _cosine_distance(va: list[float], vb: list[float]) -> float | None:
    """Cosine distance in [0, 2]; None on zero-norm or dim-mismatch.

    Contract harmonised with evaluate_cascade._cosine_distance — both
    sibling implementations return None for undefined cosine. NaN was the
    previous return value here and produced divergent behaviour; a future
    extract-to-shared-helper would expose the inconsistency.
    """
    if len(va) != len(vb):
        return None
    dot = sum(a * b for a, b in zip(va, vb))
    na = sum(a * a for a in va) ** 0.5
    nb = sum(b * b for b in vb) ** 0.5
    if na == 0.0 or nb == 0.0:
        return None
    cos_sim = dot / (na * nb)
    cos_sim = max(-1.0, min(1.0, cos_sim))
    return 1.0 - cos_sim


def centroid_distance_diagnostic(
    conn: sqlite3.Connection,
    apt_pairs: list[dict],
    inapt_controls: list[dict],
) -> dict:
    """Compute cosine-distance distribution per cohort.

    Lakoff prediction #2 expects apt pairs to cluster at intermediate
    distance — neither too close (tautological) nor too far (nonsensical).
    Operationally: the apt distance distribution should be measurably
    different from the inapt distribution. A KS-test (run in caller code)
    formalises whether the difference is significant.
    """
    def _collect(iterator, cohort_label: str) -> dict:
        distances: list[float] = []
        skipped_missing = 0
        skipped_unresolved = 0
        skipped_missing_cosine = 0
        for word_a, word_b, _row in iterator:
            sa = lookup_primary_synset(conn, word_a)
            sb = lookup_primary_synset(conn, word_b)
            if sa is None or sb is None:
                skipped_unresolved += 1
                continue
            va = _centroid(conn, sa)
            vb = _centroid(conn, sb)
            if va is None or vb is None:
                skipped_missing += 1
                continue
            d = _cosine_distance(va, vb)
            if d is None:
                skipped_missing_cosine += 1
                continue
            distances.append(d)
        return {
            "cohort": cohort_label,
            "n_total_pairs": skipped_unresolved + skipped_missing + skipped_missing_cosine + len(distances),
            "n_scored": len(distances),
            "skipped_unresolved": skipped_unresolved,
            "skipped_missing_centroid": skipped_missing,
            "skipped_missing_cosine": skipped_missing_cosine,
            "distance": _summarise(distances),
        }

    return {
        "apt": _collect(_iter_apt(apt_pairs), "apt"),
        "inapt": _collect(_iter_inapt(inapt_controls), "inapt"),
    }


# --- Summaries ---------------------------------------------------------------

def _summarise(values: list[float]) -> dict:
    """Return distribution summary stats for a list of floats."""
    if not values:
        return {
            "n": 0, "mean": None, "stdev": None,
            "min": None, "p05": None, "p25": None, "median": None,
            "p75": None, "p95": None, "max": None,
        }
    sorted_v = sorted(values)
    return {
        "n": len(values),
        "mean": round(statistics.fmean(values), 4),
        "stdev": round(statistics.pstdev(values), 4) if len(values) > 1 else 0.0,
        "min": round(sorted_v[0], 4),
        "p05": round(sorted_v[int(0.05 * (len(sorted_v) - 1))], 4),
        "p25": round(sorted_v[int(0.25 * (len(sorted_v) - 1))], 4),
        "median": round(statistics.median(values), 4),
        "p75": round(sorted_v[int(0.75 * (len(sorted_v) - 1))], 4),
        "p95": round(sorted_v[int(0.95 * (len(sorted_v) - 1))], 4),
        "max": round(sorted_v[-1], 4),
    }


# --- CLI ---------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="M03 pre-flight diagnostics — concreteness-delta + "
                    "centroid-distance distributions on apt vs inapt.",
    )
    parser.add_argument(
        "--db", type=Path, default=DEFAULT_DB,
        help=f"DB to read against (default: {DEFAULT_DB.name})",
    )
    parser.add_argument(
        "--pairs", type=str, default=str(DEFAULT_PAIRS),
        help=f"Apt pairs JSON (default: {DEFAULT_PAIRS.name})",
    )
    parser.add_argument(
        "--controls", type=str, default=str(DEFAULT_CONTROLS),
        help=f"Inapt controls JSONL (default: {DEFAULT_CONTROLS.name})",
    )
    parser.add_argument(
        "--output", type=Path, default=OUTPUT_DIR / "m03_preflight_diagnostics.json",
        help="Output JSON path for the structured result",
    )
    parser.add_argument(
        "--brysbaert-only", action="store_true",
        help="Restrict concreteness diagnostic to Brysbaert ground-truth scores.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if not args.db.exists():
        log.error("DB not found: %s", args.db)
        sys.exit(1)

    conn = sqlite3.connect(args.db)
    try:
        apt_pairs = load_apt_pairs(args.pairs)
        inapt_controls = load_inapt_controls(args.controls)
        log.info(
            "Loaded %d apt pairs, %d inapt controls from %s / %s",
            len(apt_pairs), len(inapt_controls), args.pairs, args.controls,
        )

        # Concreteness — both with imputed scores AND Brysbaert-only.
        concreteness_full = concreteness_delta_diagnostic(
            conn, apt_pairs, inapt_controls, brysbaert_only=False,
        )
        concreteness_bry = concreteness_delta_diagnostic(
            conn, apt_pairs, inapt_controls, brysbaert_only=True,
        )
        centroid = centroid_distance_diagnostic(conn, apt_pairs, inapt_controls)

        result = {
            "db": str(args.db),
            "pairs": args.pairs,
            "controls": args.controls,
            "concreteness_delta": {
                "all_sources": concreteness_full,
                "brysbaert_only": concreteness_bry,
            },
            "centroid_distance": centroid,
        }

        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2)
        log.info("Wrote %s", args.output)

        # Console summary
        _print_summary(result)
    finally:
        conn.close()


def _print_summary(result: dict) -> None:
    """Human-readable summary to stdout — for ops use after the JSON lands."""
    print()
    print("=" * 72)
    print("M03 pre-flight — concreteness-delta distribution (signed)")
    print("=" * 72)
    for label, data in [
        ("ALL SOURCES (Brysbaert + FastText imputed)", result["concreteness_delta"]["all_sources"]),
        ("BRYSBAERT ONLY",                            result["concreteness_delta"]["brysbaert_only"]),
    ]:
        print(f"\n  {label}")
        for cohort_key in ("apt", "inapt"):
            c = data[cohort_key]
            d = c["signed_delta"]
            print(
                f"    {cohort_key:>5}: n={c['n_scored']}/{c['n_total_pairs']} "
                f"(unresolved={c['skipped_unresolved']}, "
                f"missing_concreteness={c['skipped_missing_concreteness']}, "
                f"non_brysbaert={c['skipped_non_brysbaert']})"
            )
            if d["n"]:
                print(
                    f"           mean={d['mean']:+.4f}  median={d['median']:+.4f}  "
                    f"stdev={d['stdev']:.4f}  p05={d['p05']:+.4f}  p95={d['p95']:+.4f}"
                )

    print()
    print("=" * 72)
    print("M03 pre-flight — centroid cosine-distance distribution")
    print("=" * 72)
    for cohort_key in ("apt", "inapt"):
        c = result["centroid_distance"][cohort_key]
        d = c["distance"]
        print(
            f"\n  {cohort_key:>5}: n={c['n_scored']}/{c['n_total_pairs']} "
            f"(unresolved={c['skipped_unresolved']}, "
            f"missing_centroid={c['skipped_missing_centroid']})"
        )
        if d["n"]:
            print(
                f"         mean={d['mean']:.4f}  median={d['median']:.4f}  "
                f"stdev={d['stdev']:.4f}  p05={d['p05']:.4f}  p95={d['p95']:.4f}"
            )


if __name__ == "__main__":
    main()
