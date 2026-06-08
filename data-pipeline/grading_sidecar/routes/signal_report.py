"""GET /api/grading/signal — on-demand coverage/breadth + path-geometry report.

Thin IO wiring over grading_sidecar.signal_report: read the live verdicts, join
an optional precomputed geometry file, and return the dashboard. No DB / numpy:
the path geometry is precomputed offline (against the typed lexicon) into
chain_geometry_provisional.jsonl; this route only serves it.
"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends

from ..auth import verify_secret
from ..persistence import read_jsonl_skip_malformed
from ..signal_report import build_signal_report
from .. import paths as paths_mod

router = APIRouter(dependencies=[Depends(verify_secret)])


def _load_geometry() -> dict:
    """chain_signature -> geometry-feature dict. Missing file → {} (report degrades)."""
    path = paths_mod.GRADING_DIR / paths_mod.CHAIN_GEOMETRY_NAME
    records, _ = read_jsonl_skip_malformed(path)
    return {r["chain_signature"]: r for r in records if r.get("chain_signature")}


@router.get("/api/grading/signal")
def get_signal() -> dict:
    judgements, _ = read_jsonl_skip_malformed(paths_mod.JUDGEMENTS_PATH)
    server_ts = dt.datetime.now(dt.timezone.utc).isoformat()
    return build_signal_report(judgements, _load_geometry(), server_ts=server_ts)
