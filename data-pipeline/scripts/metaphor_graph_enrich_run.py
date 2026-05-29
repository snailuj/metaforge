"""Batch driver: walks the 200-topic cohort in 10 batches of 20, calling each
ingest fn per batch and writing an append-only progress markdown.

Ingest fns are dependency-injected so tests don't spin up subprocesses or
LLM clients. The CLI entrypoint binds the real implementations.
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

log = logging.getLogger(__name__)


def chunk_topics(snapped: dict, *, batch_size: int) -> list[list[dict]]:
    topics = snapped["snapped"]
    return [topics[i:i + batch_size] for i in range(0, len(topics), batch_size)]


def _write_progress_row(progress_md_path: str, batch_idx: int, batch_reports: dict[str, dict]) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    lines = [f"\n## batch {batch_idx} — {ts}\n"]
    lines.append("| proposer | bridges_inserted | skipped_existing | snap_failures |")
    lines.append("|---|---|---|---|")
    for proposer, rep in batch_reports.items():
        lines.append(
            f"| {proposer} | {rep.get('bridges_inserted', 0)} | "
            f"{rep.get('bridges_skipped_existing', 0)} | "
            f"{rep.get('bridges_skipped_snap_failure', 0)} |"
        )
    with open(progress_md_path, "a") as f:
        f.write("\n".join(lines) + "\n")


def run_batches(
    conn: sqlite3.Connection,
    snapped_topics_json_path: str,
    *,
    batch_size: int,
    progress_md_path: str,
    ingest_fns: dict[str, Callable[..., dict]],
) -> dict:
    snapped = json.loads(Path(snapped_topics_json_path).read_text())
    batches = chunk_topics(snapped, batch_size=batch_size)

    totals: dict[str, int] = {"haiku_v1": 0, "haiku_v1_inapt_synthesised": 0,
                              "cascade_v1": 0, "haiku_sonnet_v1": 0}

    for idx, batch in enumerate(batches, start=1):
        log.info("running batch %d (%d topics)", idx, len(batch))

        batch_snapped_path = f"{snapped_topics_json_path}.batch{idx}"
        Path(batch_snapped_path).write_text(json.dumps({"snapped": batch, "dropped": []}))

        try:
            batch_reports = {
                "haiku_v1": ingest_fns["ingest_haiku_apt"](conn, batch_snapped_path),
                "haiku_v1_inapt_synthesised": ingest_fns["ingest_inapt"](conn, batch_snapped_path),
                "cascade_v1": ingest_fns["ingest_cascade"](conn, batch_snapped_path),
                "haiku_sonnet_v1": ingest_fns["ingest_sonnet"](conn, batch_snapped_path),
            }
        finally:
            Path(batch_snapped_path).unlink(missing_ok=True)

        for proposer, rep in batch_reports.items():
            totals[proposer] = totals.get(proposer, 0) + rep.get("bridges_inserted", 0)

        _write_progress_row(progress_md_path, idx, batch_reports)

    return {"batches_run": len(batches), "totals": totals}
