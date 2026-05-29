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

from metaphor_graph import (  # noqa: E402
    BridgeSnapFailure,
    insert_bridge_with_raw_path,
    lookup_primary_synset,
)

log = logging.getLogger(__name__)


def curated_lemma_for(conn: sqlite3.Connection, synset_id: str) -> str | None:
    """Return the curated-vocab lemma for a synset, or None if uncurated.

    Used to align the topic word handed to Go's exact-match lookup with the
    pre-flight synset: a Go-friendly surface form for the same sense. The
    bridge label itself stays pinned to topic_synset_id (single source of
    truth) — this only affects the *score* path through the cascade.
    """
    row = conn.execute(
        "SELECT lemma FROM property_vocab_curated WHERE synset_id = ?",
        (synset_id,),
    ).fetchone()
    return row[0] if row else None


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
    topics_errored = 0
    topic_failures: list[dict] = []

    proposed_at = datetime.now(timezone.utc).isoformat()

    for t in snapped["snapped"]:
        topics_processed += 1
        # Hand Go a surface form for the pre-flight sense. The bridge label
        # below stays pinned to topic_synset_id — this only steers the score.
        go_topic = curated_lemma_for(conn, t["topic_synset_id"]) or t["word"]
        try:
            resp = suggest_fn(topic=go_topic, limit=limit)
        except Exception as exc:  # noqa: BLE001 — one bad topic must not abort the batch
            topics_errored += 1
            topic_failures.append({"topic": t["word"], "error": str(exc)})
            log.warning("cascade suggest failed for topic %r (%s): %s",
                        t["word"], t["topic_synset_id"], exc)
            continue
        # Go /forge/suggest returns vehicles under "suggestions", each with the
        # vehicle lemma under "word" (verified against the live binary 2026-05-29
        # — the earlier "candidates"/"vehicle" assumption was a mock fiction that
        # silently yielded zero bridges).
        candidates = resp.get("suggestions", [])
        if not candidates:
            topics_empty_response += 1
            continue
        for c in candidates:
            vehicle_raw = c["word"]
            vehicle_sid = lookup_primary_synset(conn, vehicle_raw)
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
        "topics_errored": topics_errored,
        "bridges_inserted": bridges_inserted,
        "bridges_skipped_existing": bridges_skipped_existing,
        "bridges_skipped_snap_failure": bridges_skipped_snap_failure,
        "snap_failures": snap_failures,
        "topic_failures": topic_failures,
    }


def make_go_suggest_fn(binary_path: str, db_path: str, port: int = 9192) -> Callable[..., dict]:
    """Start Go binary, return a suggest_fn that queries /forge/suggest.

    Caller is responsible for terminating via the returned fn's `_proc` attr.
    """
    import requests  # local import — tests do not need this dependency
    # --cascade selects the M03 cascade scorer (S05 parity-tested winner
    # config defaults); without it the binary runs the legacy scorer. Do NOT
    # re-pass the knob flags — rely on the build's blessed defaults.
    proc = subprocess.Popen(
        [binary_path, "--db", db_path, "--port", str(port), "--cascade"],
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
