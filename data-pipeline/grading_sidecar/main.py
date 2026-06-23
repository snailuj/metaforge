"""Uvicorn entrypoint for the grading sidecar.

Asserts GRADING_DEV is unset in prod (systemd unit forces this; dev runner
must also set METAFORGE_GRADING_DEV_OK=1 to acknowledge bypass).
"""
from __future__ import annotations
import os
import sys
import uvicorn
from .app import create_app

def main() -> int:
    if os.environ.get("GRADING_DEV") == "1" and os.environ.get("METAFORGE_GRADING_DEV_OK") != "1":
        print("REFUSING: GRADING_DEV=1 without METAFORGE_GRADING_DEV_OK=1 — prod-mode assertion",
              file=sys.stderr)
        return 1
    app = create_app()
    uvicorn.run(app, host="127.0.0.1", port=53775, log_config=None)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
