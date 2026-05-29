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
# Repo-root lib/ holds claude_client, imported lazily in main(). Mirror the
# convention in enrich_properties.py so the CLI entrypoint resolves it.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))

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

        # Per-proposer isolation: one proposer raising (e.g. a forge 404) must
        # not abort the batch or the remaining proposers/batches. Record the
        # failure and continue — the run is idempotent, so a later targeted
        # re-run fills the gap without redoing successful proposers.
        proposer_fns = (
            ("haiku_v1", "ingest_haiku_apt"),
            ("haiku_v1_inapt_synthesised", "ingest_inapt"),
            ("cascade_v1", "ingest_cascade"),
            ("haiku_sonnet_v1", "ingest_sonnet"),
        )
        batch_reports: dict[str, dict] = {}
        try:
            for proposer, fn_key in proposer_fns:
                try:
                    batch_reports[proposer] = ingest_fns[fn_key](conn, batch_snapped_path)
                except Exception as exc:  # noqa: BLE001 — isolate any proposer failure
                    log.error("proposer %s failed in batch %d: %s", proposer, idx, exc, exc_info=True)
                    batch_reports[proposer] = {"proposer": proposer, "error": str(exc), "bridges_inserted": 0}
        finally:
            Path(batch_snapped_path).unlink(missing_ok=True)

        for proposer, rep in batch_reports.items():
            totals[proposer] = totals.get(proposer, 0) + rep.get("bridges_inserted", 0)

        _write_progress_row(progress_md_path, idx, batch_reports)

    return {"batches_run": len(batches), "totals": totals}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True)
    p.add_argument("--snapped-topics", required=True,
                   help="Path to metaphor_graph_topics_snapped.json")
    p.add_argument("--haiku-apt-jsonl", required=True)
    p.add_argument("--haiku-inapt-jsonl", required=True)
    p.add_argument("--inapt-synth-log", required=True,
                   help="Path to haiku_v1_inapt_synthesised_paths.jsonl (created if missing)")
    p.add_argument("--sonnet-audit", required=True)
    p.add_argument("--go-binary", required=True)
    p.add_argument("--progress-md", required=True)
    p.add_argument("--batch-size", type=int, default=20)
    p.add_argument("--port", type=int, default=9192)
    args = p.parse_args()

    from claude_client import prompt_json
    from metaphor_graph_enrich_haiku import ingest_haiku_apt
    from metaphor_graph_enrich_inapt import synthesise_paths, ingest_inapt
    from metaphor_graph_enrich_cascade import ingest_cascade, make_go_suggest_fn
    from metaphor_graph_enrich_sonnet import run_sonnet_edits, ingest_sonnet

    class _CC:
        def prompt_json(self, prompt: str) -> dict:
            return prompt_json(prompt, model="claude-haiku-4-5-20251001")

    cc_haiku = _CC()

    class _CC_Sonnet:
        def prompt_json(self, prompt: str) -> dict:
            return prompt_json(prompt, model="claude-sonnet-4-6")

    cc_sonnet = _CC_Sonnet()

    synthesise_paths(cc_haiku, args.snapped_topics, args.haiku_inapt_jsonl, args.inapt_synth_log)
    run_sonnet_edits(cc_sonnet, args.snapped_topics, args.haiku_apt_jsonl, args.sonnet_audit)

    suggest_fn = make_go_suggest_fn(args.go_binary, args.db, port=args.port)
    try:
        # Transactional connection (NOT autocommit): metaphor_graph writers call
        # _require_transactional and self-commit via `with conn:` per insert. An
        # autocommit connection would raise at the first bridge insert.
        conn = sqlite3.connect(args.db)
        conn.execute("PRAGMA foreign_keys = ON")

        def _haiku_ingest(c, snapped_path):
            return ingest_haiku_apt(c, snapped_path, args.haiku_apt_jsonl)
        def _inapt_ingest(c, snapped_path):
            return ingest_inapt(c, snapped_path, args.inapt_synth_log)
        def _cascade_ingest(c, snapped_path):
            return ingest_cascade(c, snapped_path, suggest_fn=suggest_fn)
        def _sonnet_ingest(c, snapped_path):
            return ingest_sonnet(c, snapped_path, args.sonnet_audit)

        report = run_batches(
            conn, args.snapped_topics,
            batch_size=args.batch_size,
            progress_md_path=args.progress_md,
            ingest_fns={
                "ingest_haiku_apt": _haiku_ingest,
                "ingest_inapt": _inapt_ingest,
                "ingest_cascade": _cascade_ingest,
                "ingest_sonnet": _sonnet_ingest,
            },
        )
        log.info("Stage A complete: %s", report)
    finally:
        suggest_fn._proc.terminate()  # type: ignore[attr-defined]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
