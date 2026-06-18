"""Shared loader for the generated metaphor chains.

Extracted from walk._load_chains — the walk, the /chains route, and the blind
re-grade route all need the same "union the round files, keyed by signature"
view. Centralised here so the dedup + schema-drift guard lives in one place.

Chain files are grouped into cohorts (`spike`, `curated`, `stock`) defined in
paths.CHAIN_COHORTS. Each reader passes the cohort list it needs:
  - Grading views (walk/chains/topics/stats/regrade): GRADING_COHORTS
  - Sense-check: SENSECHECK_COHORTS (adds `stock` for context)
"""
from __future__ import annotations
import logging
from collections.abc import Iterator
from pathlib import Path

from .persistence import read_jsonl_skip_malformed
from . import paths as paths_mod

log = logging.getLogger(__name__)

# Keys a chain record must carry to be usable. read_jsonl_skip_malformed only drops
# JSON-decode failures, so a valid-JSON line with schema drift would otherwise reach
# consumers and KeyError-500 them; we skip such lines here instead.
_REQUIRED_CHAIN_KEYS = ("chain_signature", "topic", "vehicle")


def cohort_files(cohorts: list[str]) -> Iterator[Path]:
    """Yield the chain files for `cohorts`, in cohort-then-filename order.

    The fall-through composition: each reader picks which cohorts it sees by passing
    a cohort list. Patterns are resolved relative to paths.GRADING_DIR."""
    for cohort in cohorts:
        for pattern in paths_mod.CHAIN_COHORTS.get(cohort, []):
            yield from sorted(paths_mod.GRADING_DIR.glob(pattern))


def load_chains(cohorts: list[str] | None = None, *, tag_cohort: bool = False) -> list[dict]:
    """Union the cohort files; drop records missing required keys; dedup by signature
    (last file wins). Defaults to the grading-view cohorts (no stock).

    When `tag_cohort=True`, each returned record carries a `_cohort` key (the name
    of the cohort the file belonged to, e.g. "spike"/"curated"/"stock"). This is the
    sense-check sampler's mechanism for cohort-aware random-pool filtering."""
    if cohorts is None:
        cohorts = paths_mod.GRADING_COHORTS
    by_sig: dict[str, dict] = {}
    dropped = 0
    for cohort in cohorts:
        for pattern in paths_mod.CHAIN_COHORTS.get(cohort, []):
            for p in sorted(paths_mod.GRADING_DIR.glob(pattern)):
                recs, _ = read_jsonl_skip_malformed(p)
                for r in recs:
                    if not all(r.get(k) for k in _REQUIRED_CHAIN_KEYS):
                        dropped += 1
                        continue
                    record = {**r, "_cohort": cohort} if tag_cohort else r
                    by_sig[r["chain_signature"]] = record
    if dropped:
        log.warning("load_chains: dropped %d chain record(s) missing required keys", dropped)
    return list(by_sig.values())
