"""Shared loader for the generated metaphor chains (sonnet_chains_provisional_r*).

Extracted from walk._load_chains — the walk, the /chains route, and the blind
re-grade route all need the same "union the round files, keyed by signature"
view. Centralised here so the dedup + schema-drift guard lives in one place.
"""
from __future__ import annotations
import logging

from .persistence import read_jsonl_skip_malformed
from . import paths as paths_mod

log = logging.getLogger(__name__)

# Keys a chain record must carry to be usable. read_jsonl_skip_malformed only drops
# JSON-decode failures, so a valid-JSON line with schema drift would otherwise reach
# consumers and KeyError-500 them; we skip such lines here instead.
_REQUIRED_CHAIN_KEYS = ("chain_signature", "topic", "vehicle")


def load_chains() -> list[dict]:
    """Union all round files; drop records missing required keys and dedup by
    signature (last file wins), so one malformed or duplicated generator line can
    neither 500 a consumer nor desync a signature join."""
    by_sig: dict[str, dict] = {}
    dropped = 0
    for p in sorted(paths_mod.GRADING_DIR.glob(paths_mod.CHAINS_GLOB)):
        recs, _ = read_jsonl_skip_malformed(p)
        for r in recs:
            if not all(r.get(k) for k in _REQUIRED_CHAIN_KEYS):
                dropped += 1
                continue
            by_sig[r["chain_signature"]] = r
    if dropped:
        log.warning("load_chains: dropped %d chain record(s) missing required keys", dropped)
    return list(by_sig.values())
