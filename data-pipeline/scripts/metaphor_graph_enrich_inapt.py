# data-pipeline/scripts/metaphor_graph_enrich_inapt.py
"""Two-phase inapt enrichment for the metaphor graph.

Phase A — synthesise: per (topic, inapt_vehicle, explanation) from the Haiku
Phase 2 inapt JSONL, ask a cheap LLM to extract a single weak-dimension
concept that captures *why* the metaphor is weak. Append the result to a
synth-log JSONL so subsequent runs do not re-spend the LLM call.

Phase B — ingest: walk the synth-log JSONL and insert one single-step
bridge per entry as proposer='haiku_v1_inapt_synthesised'. The bridge's
rationale carries the original explanation prose verbatim.
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
    compute_path_hash,
    insert_bridge_with_raw_path,
    lookup_primary_synset,
    snap_concept_string,
)

log = logging.getLogger(__name__)

WEAK_DIM_PROMPT = """You are extracting the single weak shared dimension from a failed metaphor.

Topic: {topic}
Vehicle: {vehicle}
Reason type: {inapt_reason_type}
Explanation: {explanation}

Identify the ONE concept (single English word, lowercase, no punctuation) that
captures the weak shared dimension cited in the explanation. This is the
dimension that makes someone *almost* see the metaphor before realising it
doesn't quite work.

Return JSON: {{"weak_concept": "..."}}
"""


def _load_existing_synth(log_path: str) -> set[tuple[str, str]]:
    seen = set()
    p = Path(log_path)
    if not p.exists():
        return seen
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        seen.add((entry["topic"], entry["vehicle"]))
    return seen


def synthesise_paths(
    claude_client,
    snapped_topics_json_path: str,
    inapt_jsonl_path: str,
    synth_log_path: str,
) -> dict:
    snapped = json.loads(Path(snapped_topics_json_path).read_text())
    topic_set = {t["word"] for t in snapped["snapped"]}
    seen = _load_existing_synth(synth_log_path)

    calls_made = 0
    entries_logged = 0

    with open(synth_log_path, "a") as out:
        with open(inapt_jsonl_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                topic = entry["topic"]
                if topic not in topic_set:
                    continue
                for m in entry.get("inapt_metaphors", []):
                    key = (topic, m["vehicle"])
                    if key in seen:
                        continue
                    prompt = WEAK_DIM_PROMPT.format(
                        topic=topic, vehicle=m["vehicle"],
                        inapt_reason_type=m["inapt_reason_type"],
                        explanation=m["explanation"],
                    )
                    resp = claude_client.prompt_json(prompt)
                    calls_made += 1
                    weak = resp["weak_concept"].strip().lower()
                    out.write(json.dumps({
                        "topic": topic, "vehicle": m["vehicle"],
                        "inapt_reason_type": m["inapt_reason_type"],
                        "weak_concept": weak,
                        "explanation": m["explanation"],
                    }) + "\n")
                    out.flush()
                    seen.add(key)
                    entries_logged += 1

    return {"calls_made": calls_made, "entries_logged": entries_logged}


def ingest_inapt(
    conn: sqlite3.Connection,
    snapped_topics_json_path: str,
    synth_log_path: str,
    *,
    proposer: str = "haiku_v1_inapt_synthesised",
) -> dict:
    snapped = json.loads(Path(snapped_topics_json_path).read_text())
    topic_to_sid = {t["word"]: t["topic_synset_id"] for t in snapped["snapped"]}

    bridges_inserted = 0
    bridges_skipped_existing = 0
    bridges_skipped_snap_failure = 0
    snap_failures: list[dict] = []
    topics_processed = 0

    proposed_at = datetime.now(timezone.utc).isoformat()

    with open(synth_log_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            topic_sid = topic_to_sid.get(entry["topic"])
            if topic_sid is None:
                continue
            topics_processed += 1
            # Endpoint (vehicle) resolution goes through the full resolver so
            # exotic vehicles absent from property_vocab_curated still resolve
            # via the lemmas table. The synthesised weak-dimension concept below
            # stays on snap_concept_string — it's a property, not an endpoint.
            vehicle_sid = lookup_primary_synset(conn, entry["vehicle"])
            if vehicle_sid is None:
                bridges_skipped_snap_failure += 1
                snap_failures.append({"topic": entry["topic"], "vehicle": entry["vehicle"],
                                      "failing_concepts": ["<vehicle>"]})
                continue
            # Snap the weak-dimension concept up front so we can both detect a
            # snap failure and compute the bridge's idempotency key. insert_bridge
            # silently returns the existing bridge_id on a duplicate (it does not
            # raise IntegrityError), so we must probe for the existing row here to
            # report an idempotent re-run as a skip rather than an insert.
            weak_sid = snap_concept_string(conn, entry["weak_concept"])
            if weak_sid is None:
                bridges_skipped_snap_failure += 1
                snap_failures.append({"topic": entry["topic"], "vehicle": entry["vehicle"],
                                      "failing_concepts": [entry["weak_concept"]]})
                continue
            path_hash = compute_path_hash([weak_sid])
            existing = conn.execute(
                "SELECT 1 FROM metaphor_bridges "
                "WHERE topic_synset_id = ? AND vehicle_synset_id = ? "
                "AND proposer = ? AND path_hash = ?",
                (topic_sid, vehicle_sid, proposer, path_hash),
            ).fetchone()
            if existing is not None:
                bridges_skipped_existing += 1
                continue
            try:
                insert_bridge_with_raw_path(
                    conn,
                    topic_synset_id=topic_sid,
                    vehicle_synset_id=vehicle_sid,
                    proposer=proposer,
                    proposed_at=proposed_at,
                    raw_path=[entry["weak_concept"]],
                    rationale=entry["explanation"],
                )
                bridges_inserted += 1
            except BridgeSnapFailure:
                bridges_skipped_snap_failure += 1
                snap_failures.append({"topic": entry["topic"], "vehicle": entry["vehicle"],
                                      "failing_concepts": [entry["weak_concept"]]})

    return {
        "proposer": proposer,
        "topics_processed": topics_processed,
        "bridges_inserted": bridges_inserted,
        "bridges_skipped_existing": bridges_skipped_existing,
        "bridges_skipped_snap_failure": bridges_skipped_snap_failure,
        "snap_failures": snap_failures,
    }
