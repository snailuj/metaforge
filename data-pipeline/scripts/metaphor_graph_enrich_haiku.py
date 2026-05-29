# data-pipeline/scripts/metaphor_graph_enrich_haiku.py
"""Ingest existing Haiku Phase 2 apt JSONL into metaphor_bridges as proposer='haiku_v1'.

Reuses metaphor_graph.insert_bridge_with_raw_path so snap-failure semantics are
identical to the rest of the metaphor-graph pipeline. Idempotent via the
schema's UNIQUE (topic_synset_id, vehicle_synset_id, proposer, path_hash)
constraint — duplicate inserts are caught by sqlite3.IntegrityError and
counted as bridges_skipped_existing.
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from metaphor_graph import (  # noqa: E402
    BridgeSnapFailure,
    insert_bridge_with_raw_path,
    lookup_primary_synset,
)

log = logging.getLogger(__name__)


def ingest_haiku_apt(
    conn: sqlite3.Connection,
    snapped_topics_json_path: str,
    haiku_apt_jsonl_path: str,
    *,
    proposer: str = "haiku_v1",
) -> dict:
    snapped = json.loads(Path(snapped_topics_json_path).read_text())
    topic_to_sid = {t["word"]: t["topic_synset_id"] for t in snapped["snapped"]}

    bridges_inserted = 0
    bridges_skipped_existing = 0
    bridges_skipped_snap_failure = 0
    snap_failures: list[dict] = []
    topics_processed = 0

    proposed_at = datetime.now(timezone.utc).isoformat()

    with open(haiku_apt_jsonl_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            topic = entry["topic"]
            topic_sid = topic_to_sid.get(topic)
            if topic_sid is None:
                continue
            topics_processed += 1
            for m in entry.get("metaphors", []):
                vehicle_raw = m["vehicle"]
                # Endpoint resolution: route the vehicle through the endpoint
                # resolver (curated → lemmas → lemmatised variants) rather than
                # snap_concept_string, which is property-vocab-only and silently
                # drops creative vehicles absent from the curated set. The
                # shared-feature PATH concepts inside insert_bridge_with_raw_path
                # remain on snap_concept_string — they are properties.
                vehicle_sid = lookup_primary_synset(conn, vehicle_raw)
                if vehicle_sid is None:
                    bridges_skipped_snap_failure += 1
                    snap_failures.append({"topic": topic, "vehicle": vehicle_raw, "failing_concepts": ["<vehicle>"]})
                    continue
                for feat in m.get("shared_features", []):
                    concept = feat["concept"]
                    # insert_bridge is idempotent: it returns the existing
                    # bridge_id for a duplicate rather than raising. We detect a
                    # no-op by the row count staying flat across the call, so the
                    # report can distinguish fresh inserts from skipped existing
                    # bridges without depending on an IntegrityError that the
                    # writer's pre-check makes unreachable.
                    before = conn.execute(
                        "SELECT COUNT(*) FROM metaphor_bridges"
                    ).fetchone()[0]
                    try:
                        insert_bridge_with_raw_path(
                            conn,
                            topic_synset_id=topic_sid,
                            vehicle_synset_id=vehicle_sid,
                            proposer=proposer,
                            proposed_at=proposed_at,
                            raw_path=[concept],
                        )
                    except BridgeSnapFailure:
                        bridges_skipped_snap_failure += 1
                        snap_failures.append({"topic": topic, "vehicle": vehicle_raw, "failing_concepts": [concept]})
                        continue
                    except sqlite3.IntegrityError:
                        bridges_skipped_existing += 1
                        continue
                    after = conn.execute(
                        "SELECT COUNT(*) FROM metaphor_bridges"
                    ).fetchone()[0]
                    if after > before:
                        bridges_inserted += 1
                    else:
                        bridges_skipped_existing += 1

    report = {
        "proposer": proposer,
        "topics_processed": topics_processed,
        "bridges_inserted": bridges_inserted,
        "bridges_skipped_existing": bridges_skipped_existing,
        "bridges_skipped_snap_failure": bridges_skipped_snap_failure,
        "snap_failures": snap_failures,
    }
    log.info("ingest_haiku_apt: %s", report)
    return report
