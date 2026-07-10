"""GET /api/grading/senses — per-phrase noun sense inventory for the sense fan UI.

Serves pre-computed noun-POS sense rankings (tagcount-sorted) from a JSONL file
built offline by build_sense_inventories.py (Task 2 / W1). The sidecar has no
DB; the route degrades to an empty list with a WARNING when the file is absent.

Query param:
    key — canonical phrase (output of normalise_phrase + space→underscore);
          if the caller passes the raw phrase, the lookup simply misses and
          the caller receives an empty fan (a graceful degradation, not an error).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from ..auth import verify_secret
from ..persistence import read_jsonl_skip_malformed
from .. import paths as paths_mod

log = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_secret)])


def _load_inventories() -> dict[str, list[dict]]:
    """Load the sense inventory JSONL into a {key: [sense, …]} mapping.

    Missing file degrades to {} with a warning so the grading panel keeps
    working even before the offline inventory build has run.
    """
    path = paths_mod.sense_inventories_path()
    if not path.exists():
        log.warning("sense_inventories_path missing (%s) — sense fan will be empty", path)
        return {}
    records, skipped = read_jsonl_skip_malformed(path)
    if skipped:
        log.warning("%d malformed rows skipped in %s", skipped, path)
    return {r["key"]: r.get("senses", []) for r in records if r.get("key")}


@router.get("/api/grading/senses")
def get_senses(key: str) -> dict:
    """Return the pre-ranked noun sense fan for one canonical phrase key."""
    inventories = _load_inventories()
    senses = inventories.get(key, [])
    return {"key": key, "senses": senses}
