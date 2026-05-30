"""Append-only JSONL persistence with fcntl.flock + fsync.

See spec section "Sidecar → Persistence — corrected atomicity" for rationale:
the .tmp+rename pattern is for full-file replacement, NOT append. We use
O_APPEND + advisory fcntl.flock (kernel releases on crash) + fsync.

UTF-8 NFC-normalised per spec section "Data shapes → UTF-8 normalisation".
"""
from __future__ import annotations
import fcntl
import json
import logging
import os
import unicodedata
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

def _nfc(obj: Any) -> Any:
    if isinstance(obj, str):
        return unicodedata.normalize("NFC", obj)
    if isinstance(obj, dict):
        return {k: _nfc(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_nfc(x) for x in obj]
    return obj

def append_jsonl(path: Path, record: dict) -> None:
    """Atomic append of one JSONL line. Safe across concurrent writers via
    fcntl.flock; safe across crashes (advisory lock auto-released). fsync
    ensures durability before return."""
    line = json.dumps(_nfc(record), ensure_ascii=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)

def read_jsonl_skip_malformed(path: Path) -> tuple[list[dict], int]:
    """Return (records, skipped_count). Missing file → ([], 0). Malformed
    lines logged at WARNING and skipped, not raised."""
    if not path.exists():
        return [], 0
    records: list[dict] = []
    skipped = 0
    with open(path, "r", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_SH)
        try:
            for i, raw in enumerate(f, 1):
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    records.append(json.loads(raw))
                except json.JSONDecodeError as exc:
                    log.warning("malformed JSONL line %d in %s: %s", i, path, exc)
                    skipped += 1
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    return records, skipped
