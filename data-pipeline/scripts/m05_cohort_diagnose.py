#!/usr/bin/env python3
"""M05 cohort pre-flight diagnostic.

For each (topic, vehicle) pair in the Lakoff cohort, queries the DB
directly (no API) to determine why the API might drop the pair when
the sweep runs. The output JSON lets the sweep runner attribute each
post-API drop to a typed bucket — separating "the data isn't there to
resolve this pair" from "the data is there but candidate generation
filtered it out".

The latter is the only honest place to read γ's gate-level
discrimination signal.

Buckets per topic / vehicle (first failure wins):

  Topic side:
    topic_no_lemma                   — word not in `lemmas`
    topic_no_curated_no_centroid     — lemma resolves but no synset has
                                       curated properties AND no synset has
                                       a centroid (can't drive either path)

  Vehicle side:
    vehicle_no_lemma                 — word not in `lemmas`
    vehicle_no_concreteness          — lemma resolves but no synset has a
                                       concreteness row (gate would reject)
    vehicle_no_curated_no_centroid   — has concreteness but neither
                                       candidate-gen path can reach it

  `clean` if no failure on that side.

Per-pair attribution (priority: topic first, then vehicle, then clean):

  pre_topic_<bucket>     — pair blocked by topic-side data gap
  pre_vehicle_<bucket>   — pair blocked by vehicle-side data gap
  preflight_clean        — both sides resolvable; any API drop is a real
                           candidate-gen / no-overlap signal

Usage:
    python data-pipeline/scripts/m05_cohort_diagnose.py \\
        --db data-pipeline/output/lexicon_v2.db \\
        --pairs data-pipeline/fixtures/lakoff_apt.jsonl \\
        --controls data-pipeline/fixtures/lakoff_inapt.jsonl \\
        --output data-pipeline/output/m05_cohort_diagnostics.json
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class WordDiagnostic:
    """Per-word DB-availability tags. ``bucket`` is the first failure
    encountered (in priority order) or ``"clean"``.
    """

    word: str
    has_lemma: bool
    synset_ids: list[str]
    n_synsets_with_concreteness: int
    n_synsets_with_curated_properties: int
    n_synsets_with_centroid: int
    bucket: str


@dataclass
class PairDiagnostic:
    topic: str
    vehicle: str
    topic_bucket: str
    vehicle_bucket: str
    attribution: str  # pre_topic_<x> / pre_vehicle_<x> / preflight_clean


@dataclass
class CohortReport:
    cohort_name: str
    n_pairs: int
    pair_diagnostics: list[PairDiagnostic] = field(default_factory=list)
    attribution_histogram: dict[str, int] = field(default_factory=dict)


def _synsets_for_word(conn: sqlite3.Connection, word: str) -> list[str]:
    rows = conn.execute("SELECT synset_id FROM lemmas WHERE lemma = ?", (word,)).fetchall()
    return [r[0] for r in rows]


def _count_with_concreteness(conn: sqlite3.Connection, synset_ids: list[str]) -> int:
    if not synset_ids:
        return 0
    placeholders = ",".join("?" * len(synset_ids))
    row = conn.execute(
        f"SELECT COUNT(DISTINCT synset_id) FROM synset_concreteness WHERE synset_id IN ({placeholders})",
        synset_ids,
    ).fetchone()
    return int(row[0]) if row else 0


def _count_with_curated_properties(conn: sqlite3.Connection, synset_ids: list[str]) -> int:
    if not synset_ids:
        return 0
    placeholders = ",".join("?" * len(synset_ids))
    row = conn.execute(
        f"SELECT COUNT(DISTINCT synset_id) FROM synset_properties_curated WHERE synset_id IN ({placeholders})",
        synset_ids,
    ).fetchone()
    return int(row[0]) if row else 0


def _count_with_centroid(conn: sqlite3.Connection, synset_ids: list[str]) -> int:
    if not synset_ids:
        return 0
    placeholders = ",".join("?" * len(synset_ids))
    row = conn.execute(
        f"SELECT COUNT(DISTINCT synset_id) FROM synset_centroids WHERE synset_id IN ({placeholders})",
        synset_ids,
    ).fetchone()
    return int(row[0]) if row else 0


def diagnose_topic(conn: sqlite3.Connection, word: str) -> WordDiagnostic:
    """First-failure bucketing for a topic word."""
    synsets = _synsets_for_word(conn, word)
    n_conc = _count_with_concreteness(conn, synsets)
    n_curated = _count_with_curated_properties(conn, synsets)
    n_centroid = _count_with_centroid(conn, synsets)

    if not synsets:
        bucket = "topic_no_lemma"
    elif n_curated == 0 and n_centroid == 0:
        bucket = "topic_no_curated_no_centroid"
    else:
        bucket = "clean"

    return WordDiagnostic(
        word=word,
        has_lemma=bool(synsets),
        synset_ids=synsets,
        n_synsets_with_concreteness=n_conc,
        n_synsets_with_curated_properties=n_curated,
        n_synsets_with_centroid=n_centroid,
        bucket=bucket,
    )


def diagnose_vehicle(conn: sqlite3.Connection, word: str) -> WordDiagnostic:
    """First-failure bucketing for a vehicle word."""
    synsets = _synsets_for_word(conn, word)
    n_conc = _count_with_concreteness(conn, synsets)
    n_curated = _count_with_curated_properties(conn, synsets)
    n_centroid = _count_with_centroid(conn, synsets)

    if not synsets:
        bucket = "vehicle_no_lemma"
    elif n_conc == 0:
        bucket = "vehicle_no_concreteness"
    elif n_curated == 0 and n_centroid == 0:
        bucket = "vehicle_no_curated_no_centroid"
    else:
        bucket = "clean"

    return WordDiagnostic(
        word=word,
        has_lemma=bool(synsets),
        synset_ids=synsets,
        n_synsets_with_concreteness=n_conc,
        n_synsets_with_curated_properties=n_curated,
        n_synsets_with_centroid=n_centroid,
        bucket=bucket,
    )


def attribute_pair(topic_diag: WordDiagnostic, vehicle_diag: WordDiagnostic) -> str:
    """Priority: topic-side block → vehicle-side block → preflight_clean.

    Topic-side blocks win because if the API can't generate candidates
    at all, the vehicle side never gets a chance to participate.
    """
    if topic_diag.bucket != "clean":
        return f"pre_{topic_diag.bucket}"
    if vehicle_diag.bucket != "clean":
        return f"pre_{vehicle_diag.bucket}"
    return "preflight_clean"


def load_cohort(path: Path) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        topic = obj.get("topic")
        vehicle = obj.get("vehicle")
        if not topic or not vehicle:
            raise ValueError(f"cohort row missing topic/vehicle: {line!r}")
        pairs.append((topic, vehicle))
    return pairs


def diagnose_cohort(
    conn: sqlite3.Connection, cohort_name: str, pairs: list[tuple[str, str]]
) -> CohortReport:
    # Cache per-word diagnostics — the cohort is dense (anger appears
    # ~30x across apt+inapt), so this is a ~5x speedup.
    topic_cache: dict[str, WordDiagnostic] = {}
    vehicle_cache: dict[str, WordDiagnostic] = {}
    report = CohortReport(cohort_name=cohort_name, n_pairs=len(pairs))
    hist: Counter[str] = Counter()

    for topic, vehicle in pairs:
        if topic not in topic_cache:
            topic_cache[topic] = diagnose_topic(conn, topic)
        if vehicle not in vehicle_cache:
            vehicle_cache[vehicle] = diagnose_vehicle(conn, vehicle)
        td = topic_cache[topic]
        vd = vehicle_cache[vehicle]
        attribution = attribute_pair(td, vd)
        hist[attribution] += 1
        report.pair_diagnostics.append(
            PairDiagnostic(
                topic=topic,
                vehicle=vehicle,
                topic_bucket=td.bucket,
                vehicle_bucket=vd.bucket,
                attribution=attribution,
            )
        )
    report.attribution_histogram = dict(hist)
    return report


def emit_summary(reports: list[CohortReport]) -> None:
    """Operator-facing stderr summary so the diagnose run is interpretable
    without opening the JSON."""
    print("\nM05 cohort pre-flight diagnostic summary:\n", file=sys.stderr)
    for r in reports:
        print(f"  Cohort: {r.cohort_name} (n={r.n_pairs})", file=sys.stderr)
        total = max(r.n_pairs, 1)
        for bucket, count in sorted(r.attribution_histogram.items(), key=lambda kv: -kv[1]):
            pct = 100.0 * count / total
            print(f"    {bucket:42s} {count:4d}  ({pct:5.1f}%)", file=sys.stderr)
        print("", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", type=Path, required=True, help="SQLite DB to query")
    ap.add_argument("--pairs", type=Path, required=True, help="JSONL — apt cohort pairs")
    ap.add_argument("--controls", type=Path, required=True, help="JSONL — inapt control pairs")
    ap.add_argument("--output", type=Path, required=True, help="JSON output path")
    args = ap.parse_args(argv)

    if not args.db.exists():
        print(f"ERROR: DB not found: {args.db}", file=sys.stderr)
        return 2

    apt_pairs = load_cohort(args.pairs)
    inapt_pairs = load_cohort(args.controls)

    # Read-only mode — the diagnostic does not write to the DB and we
    # explicitly want to fail if anything tries.
    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    try:
        apt_report = diagnose_cohort(conn, "apt", apt_pairs)
        inapt_report = diagnose_cohort(conn, "inapt", inapt_pairs)
    finally:
        conn.close()

    payload = {
        "db": str(args.db),
        "apt": {
            "n_pairs": apt_report.n_pairs,
            "attribution_histogram": apt_report.attribution_histogram,
            "pair_diagnostics": [asdict(p) for p in apt_report.pair_diagnostics],
        },
        "inapt": {
            "n_pairs": inapt_report.n_pairs,
            "attribution_histogram": inapt_report.attribution_histogram,
            "pair_diagnostics": [asdict(p) for p in inapt_report.pair_diagnostics],
        },
    }
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True))
    print(f"Wrote diagnostics to {args.output}", file=sys.stderr)
    emit_summary([apt_report, inapt_report])
    return 0


if __name__ == "__main__":
    sys.exit(main())
