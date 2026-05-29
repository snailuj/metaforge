# data-pipeline/scripts/metaphor_graph_enrich_sonnet.py
"""Sonnet editorial-rewrite pass + ingest.

Per topic, send Sonnet the full Haiku apt entry (topic, gloss, all Haiku
vehicles + their shared_features) with a prompt instructing full editorial
rewrite: substitute weak vehicles, sharpen paths, return polished list of 10
vehicles each with 3-6 one-word path concepts. Audit JSONL records Sonnet's
verbatim response so post-hoc inspection of editorial decisions is possible
even if the schema or ingest semantics change.
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

from metaphor_graph import BridgeSnapFailure, insert_bridge_with_raw_path, lookup_primary_synset  # noqa: E402

log = logging.getLogger(__name__)

SONNET_EDIT_PROMPT = """You are a literary metaphor editor reviewing a junior writer's draft.

Topic: {topic}
Gloss: {gloss}

Draft metaphors (vehicle + the dimensions the junior writer thought were shared):
{draft_json}

Your task: full editorial rewrite. Substitute weak vehicles. Sharpen the shared
dimensions. Aim for vivid cross-domain mappings that a literary writer would
actually use — not dead-metaphor cliches and not single-dimension surface
similarities.

Return 10 vehicles, each with 3-6 one-word path concepts (lowercase, no
punctuation). Each path concept is a curated dimension along which topic and
vehicle structurally match.

Return JSON:
{{
  "topic": "{topic}",
  "vehicles": [
    {{"vehicle": "<single english word>", "path_concepts": ["<word>", ...]}}
  ]
}}
"""


def _load_audited_topics(audit_jsonl_path: str) -> set[str]:
    """Topics already present in the audit log — skipped on re-runs so Sonnet
    is not re-spent (mirrors synthesise_paths' log-skip in the inapt ingest)."""
    seen: set[str] = set()
    p = Path(audit_jsonl_path)
    if not p.exists():
        return seen
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        seen.add(entry["topic"])
    return seen


def run_sonnet_edits(
    claude_client,
    snapped_topics_json_path: str,
    haiku_apt_jsonl_path: str,
    audit_jsonl_path: str,
) -> dict:
    snapped = json.loads(Path(snapped_topics_json_path).read_text())
    topic_set = {t["word"] for t in snapped["snapped"]}
    seen = _load_audited_topics(audit_jsonl_path)

    calls_made = 0
    with open(audit_jsonl_path, "a") as audit:
        with open(haiku_apt_jsonl_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                topic = entry["topic"]
                if topic not in topic_set:
                    continue
                if topic in seen:
                    continue
                draft = [{"vehicle": m["vehicle"], "dimensions": [s["concept"] for s in m.get("shared_features", [])]}
                         for m in entry.get("metaphors", [])]
                prompt = SONNET_EDIT_PROMPT.format(
                    topic=topic,
                    gloss=entry.get("_gloss", ""),
                    draft_json=json.dumps(draft, indent=2),
                )
                resp = claude_client.prompt_json(prompt)
                calls_made += 1
                audit.write(json.dumps(resp) + "\n")
                audit.flush()
                seen.add(topic)
    return {"calls_made": calls_made}


def ingest_sonnet(
    conn: sqlite3.Connection,
    snapped_topics_json_path: str,
    audit_jsonl_path: str,
    *,
    proposer: str = "haiku_sonnet_v1",
) -> dict:
    snapped = json.loads(Path(snapped_topics_json_path).read_text())
    topic_to_sid = {t["word"]: t["topic_synset_id"] for t in snapped["snapped"]}

    bridges_inserted = 0
    bridges_skipped_existing = 0
    bridges_skipped_snap_failure = 0
    snap_failures: list[dict] = []
    topics_processed = 0

    proposed_at = datetime.now(timezone.utc).isoformat()

    with open(audit_jsonl_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            topic_sid = topic_to_sid.get(entry["topic"])
            if topic_sid is None:
                continue
            topics_processed += 1
            for v in entry.get("vehicles", []):
                vehicle_raw = v["vehicle"]
                vehicle_sid = lookup_primary_synset(conn, vehicle_raw)
                if vehicle_sid is None:
                    bridges_skipped_snap_failure += 1
                    snap_failures.append({"topic": entry["topic"], "vehicle": vehicle_raw,
                                          "failing_concepts": ["<vehicle>"]})
                    continue
                for concept in v.get("path_concepts", []):
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
                        snap_failures.append({"topic": entry["topic"], "vehicle": vehicle_raw,
                                              "failing_concepts": [concept]})
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
        "bridges_inserted": bridges_inserted,
        "bridges_skipped_existing": bridges_skipped_existing,
        "bridges_skipped_snap_failure": bridges_skipped_snap_failure,
        "snap_failures": snap_failures,
    }
