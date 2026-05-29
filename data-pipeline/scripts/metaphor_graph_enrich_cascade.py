# data-pipeline/scripts/metaphor_graph_enrich_cascade.py
"""Cascade ingest: query Go /forge/suggest per topic, ingest as proposer='cascade_v1'.

The Go binary lifecycle (start on free port, wait healthy, kill) is delegated
to a suggest_fn callable so tests can substitute a mock. The CLI entrypoint
provides the real implementation: subprocess Popen + requests.get poll.
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

from metaphor_graph import BridgeSnapFailure, insert_bridge_with_raw_path, snap_concept_string  # noqa: E402

log = logging.getLogger(__name__)


def ingest_cascade(
    conn: sqlite3.Connection,
    snapped_topics_json_path: str,
    *,
    suggest_fn: Callable[..., dict],
    limit: int = 10,
    proposer: str = "cascade_v1",
) -> dict:
    snapped = json.loads(Path(snapped_topics_json_path).read_text())
    bridges_inserted = 0
    bridges_skipped_existing = 0
    bridges_skipped_snap_failure = 0
    snap_failures: list[dict] = []
    topics_processed = 0
    topics_empty_response = 0

    proposed_at = datetime.now(timezone.utc).isoformat()

    for t in snapped["snapped"]:
        topics_processed += 1
        resp = suggest_fn(topic=t["word"], limit=limit)
        candidates = resp.get("candidates", [])
        if not candidates:
            topics_empty_response += 1
            continue
        for c in candidates:
            vehicle_raw = c["vehicle"]
            vehicle_sid = snap_concept_string(conn, vehicle_raw)
            if vehicle_sid is None:
                bridges_skipped_snap_failure += 1
                snap_failures.append({"topic": t["word"], "vehicle": vehicle_raw,
                                      "failing_concepts": ["<vehicle>"]})
                continue
            for sp in c.get("shared_properties", []):
                prop = sp["property"] if isinstance(sp, dict) else sp
                # insert_bridge is idempotent: it returns the existing bridge_id
                # for a duplicate rather than raising. We detect a no-op by the
                # row count staying flat across the call, so the report can
                # distinguish fresh inserts from skipped existing bridges without
                # depending on an IntegrityError that the writer's pre-check makes
                # unreachable. Mirrors metaphor_graph_enrich_haiku.
                before = conn.execute(
                    "SELECT COUNT(*) FROM metaphor_bridges"
                ).fetchone()[0]
                try:
                    insert_bridge_with_raw_path(
                        conn,
                        topic_synset_id=t["topic_synset_id"],
                        vehicle_synset_id=vehicle_sid,
                        proposer=proposer,
                        proposed_at=proposed_at,
                        raw_path=[prop],
                    )
                except BridgeSnapFailure:
                    bridges_skipped_snap_failure += 1
                    snap_failures.append({"topic": t["word"], "vehicle": vehicle_raw,
                                          "failing_concepts": [prop]})
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

    return {
        "proposer": proposer,
        "topics_processed": topics_processed,
        "topics_empty_response": topics_empty_response,
        "bridges_inserted": bridges_inserted,
        "bridges_skipped_existing": bridges_skipped_existing,
        "bridges_skipped_snap_failure": bridges_skipped_snap_failure,
        "snap_failures": snap_failures,
    }


def make_go_suggest_fn(binary_path: str, db_path: str, port: int = 9192) -> Callable[..., dict]:
    """Start Go binary, return a suggest_fn that queries /forge/suggest.

    Caller is responsible for terminating via the returned fn's `_proc` attr.
    """
    import requests  # local import — tests do not need this dependency
    proc = subprocess.Popen(
        [binary_path, "--db", db_path, "--port", str(port)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            r = requests.get(f"{base}/health", timeout=1)
            if r.status_code == 200:
                break
        except requests.RequestException:
            time.sleep(0.2)
    else:
        proc.terminate()
        raise RuntimeError("Go binary did not become healthy within 30s")

    def fn(*, topic: str, limit: int) -> dict:
        r = requests.get(f"{base}/forge/suggest", params={"word": topic, "limit": limit}, timeout=30)
        r.raise_for_status()
        return r.json()

    fn._proc = proc  # type: ignore[attr-defined]
    return fn
