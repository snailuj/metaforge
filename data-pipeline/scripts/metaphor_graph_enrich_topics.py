"""Pre-flight: snap topic strings from spike_2_topics.json to curated synset_ids.

Writes a partition of {snapped, dropped} to a JSON artefact consumed by all
downstream Stage A ingest scripts. Idempotent — re-running overwrites the
output file with the same partition.
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from metaphor_graph import snap_concept_string  # noqa: E402

log = logging.getLogger(__name__)


def snap_topics(
    conn: sqlite3.Connection,
    topics_json_path: str,
    output_json_path: str,
) -> dict:
    """Snap each topic's `word` to a curated synset_id via snap_concept_string.

    Returns the same dict written to output_json_path: counts, snap_rate, and
    the {snapped, dropped} partition.
    """
    with open(topics_json_path) as f:
        topics_in = json.load(f)["topics"]

    snapped: list[dict] = []
    dropped: list[dict] = []
    for t in topics_in:
        sid = snap_concept_string(conn, t["word"])
        if sid is None:
            dropped.append({**t, "reason": "no_curated_synset"})
        else:
            snapped.append({**t, "topic_synset_id": sid})

    report = {
        "input_count": len(topics_in),
        "snapped_count": len(snapped),
        "snap_rate": len(snapped) / max(1, len(topics_in)),
        "snapped": snapped,
        "dropped": dropped,
    }
    Path(output_json_path).write_text(json.dumps(report, indent=2))
    log.info(
        "snap_topics: snapped=%d dropped=%d snap_rate=%.3f",
        len(snapped), len(dropped), report["snap_rate"],
    )
    return report


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True)
    p.add_argument("--topics", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    conn = sqlite3.connect(args.db, isolation_level=None, autocommit=True)
    conn.execute("PRAGMA foreign_keys = ON")
    report = snap_topics(conn, args.topics, args.output)
    if report["snap_rate"] < 0.9:
        log.warning("snap rate %.3f below 0.9 threshold — cohort may need curation", report["snap_rate"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
