"""GET /api/grading/stats — aggregate counts for chain files and judgements."""
from __future__ import annotations
import datetime as dt
from collections import Counter
from fastapi import APIRouter, Depends
from ..auth import verify_secret
from ..models import normalise_judgement
from ..persistence import read_jsonl_skip_malformed
from .. import paths as paths_mod

router = APIRouter(dependencies=[Depends(verify_secret)])


@router.get("/api/grading/stats")
def get_stats() -> dict:
    chain_count = 0
    for p in paths_mod.GRADING_DIR.glob(paths_mod.CHAINS_GLOB):
        recs, _ = read_jsonl_skip_malformed(p)
        chain_count += len(recs)
    judgements, _ = read_jsonl_skip_malformed(paths_mod.JUDGEMENTS_PATH)
    last_judgement_ts = max((j.get("ts", "") for j in judgements), default="") or None

    # Bucket by the normalised axes so v1 (`label`) and v2 lines aggregate
    # together. None values (v1 bad_path → metaphor; irrelevant → linkage)
    # carry no signal on that axis and are excluded from the counts.
    normalised = [normalise_judgement(j) for j in judgements]
    metaphor_counts = Counter(
        n["metaphor"] for n in normalised if n.get("metaphor") is not None
    )
    linkage_counts = Counter(
        n["linkage"] for n in normalised if n.get("linkage") is not None
    )

    return {
        "chain_count": chain_count,
        "judgement_count": len(judgements),
        "last_judgement_ts": last_judgement_ts,
        "metaphor_counts": dict(metaphor_counts),
        "linkage_counts": dict(linkage_counts),
        "schema_version": {"chain": "chain.v1", "judgement": "judgement.v2"},
        "server_ts": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
