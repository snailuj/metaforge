"""Sidecar auth dependency.

Reads GRADING_SECRET from the file pointed to by GRADING_SECRET_FILE env var
(default: /etc/metaforge/grading_secret) at first call, then caches.
hmac.compare_digest for constant-time comparison.

GRADING_DEV=1 bypasses the check (dev only — the production systemd unit
sets Environment=GRADING_DEV= and main.py asserts this).
"""
from __future__ import annotations
import functools
import hmac
import os
import sys
from pathlib import Path
from fastapi import Header, HTTPException

DEFAULT_SECRET_FILE = "/etc/metaforge/grading_secret"

@functools.lru_cache(maxsize=1)
def load_secret() -> str:
    path = Path(os.environ.get("GRADING_SECRET_FILE", DEFAULT_SECRET_FILE))
    if not path.exists():
        print(f"FATAL: GRADING_SECRET file missing: {path}", file=sys.stderr)
        raise SystemExit(1)
    secret = path.read_text().strip()
    if not secret:
        print(f"FATAL: GRADING_SECRET file is empty: {path}", file=sys.stderr)
        raise SystemExit(1)
    return secret

def verify_secret(x_grading_secret: str = Header(default="")) -> None:
    if os.environ.get("GRADING_DEV") == "1":
        return
    expected = load_secret()
    if not hmac.compare_digest(x_grading_secret, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")
