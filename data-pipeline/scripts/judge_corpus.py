"""Gold-corpus data prep for the LLM-judge agreement harness (plan section 1).

Reuses the sidecar's verdict semantics rather than re-deriving them:
resolve_verdicts (supersede + latest-wins per chain_signature),
normalise_judgement (v1 label -> v2 axes) and effective_linkage (the
tag-implies-bad-linkage convention) come from grading_sidecar, and the
effective value is stamped on each row as `linkage_effective` so downstream
judges read one settled field instead of re-applying the rule.

Two judge axes, deliberately orthogonal:

  * construction_rows — Stage-1 (linkage) set. v1-irrelevant rows carry no
    linkage signal (linkage_effective is None: the pairing is unconnected, so
    linkage was moot) and are dropped. y_link=1 = bad linkage.
  * liveness_rows — Stage-2 (pairing) set. bad_head rows are KEPT — the
    endpoints are canonicalised so the topic->vehicle pairing stays valid —
    and linkage NEVER gates membership: a Stage-1 verdict shaping the Stage-2
    corpus would couple the axes the harness exists to measure separately.

Loaders take explicit paths (no import-time path constants of our own): the
gold lives on the grading-live worktree, not this checkout, so the caller must
say where. grading_sidecar.chain_store.load_chains is import-time-bound to the
repo grading dir, hence load_chains here mirrors its union/dedup semantics
over an explicit directory instead.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # -> grading_sidecar package

from grading_sidecar.models import effective_linkage, normalise_judgement  # noqa: E402
from grading_sidecar.persistence import read_jsonl_skip_malformed  # noqa: E402
from grading_sidecar.signal_report import resolve_verdicts  # noqa: E402

log = logging.getLogger(__name__)

# Mirrors grading_sidecar.chain_store: round-file glob + the keys a chain
# record must carry to be joinable (schema-drift lines are skipped, not 500ed).
CHAINS_GLOB = "sonnet_chains_provisional_r*.jsonl"
_REQUIRED_CHAIN_KEYS = ("chain_signature", "topic", "vehicle")


def load_resolved(path: Path | str) -> list[dict]:
    """Read a judgements JSONL -> resolved, normalised rows with
    `linkage_effective` stamped.

    Malformed lines are skipped+logged (per-line by the reader, aggregate
    here). A missing file escalates — the gold corpus is the whole point of a
    harness run, so an empty-list fallback would silently score nothing.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"gold verdicts file not found: {path}")
    raw, skipped = read_jsonl_skip_malformed(path)
    if skipped:
        log.warning("load_resolved: skipped %d malformed line(s) in %s", skipped, path)
    rows = []
    for rec in resolve_verdicts(raw):
        norm = normalise_judgement(rec)
        rows.append({**norm, "linkage_effective": effective_linkage(norm)})
    log.info("load_resolved: %d raw line(s) -> %d resolved verdict(s) from %s",
             len(raw), len(rows), path)
    return rows


def construction_rows(records: list[dict]) -> list[dict]:
    """Stage-1 (linkage) corpus: y_link=1 = bad linkage.

    Drops rows whose linkage_effective is None (v1 'irrelevant' — linkage was
    moot, no Stage-1 signal). Indexes the stamp directly so a caller passing
    un-stamped rows fails loudly rather than yielding an empty corpus.
    """
    rows = [{**r, "y_link": 1 if r["linkage_effective"] == "bad" else 0}
            for r in records if r["linkage_effective"] is not None]
    log.info("construction_rows: %d/%d row(s) kept (y_link=1: %d)",
             len(rows), len(records), sum(r["y_link"] for r in rows))
    return rows


def liveness_rows(records: list[dict]) -> list[dict]:
    """Stage-2 (pairing) corpus: metaphor in live/dead only; y_live=1 = live.

    bad_head rows stay in (pairing valid — see module docstring) and linkage
    never gates. v1 'bad_path' rows (metaphor None) drop out naturally.
    """
    rows = [{**r, "y_live": 1 if r.get("metaphor") == "live" else 0}
            for r in records if r.get("metaphor") in ("live", "dead")]
    log.info("liveness_rows: %d/%d row(s) kept (y_live=1: %d)",
             len(rows), len(records), sum(r["y_live"] for r in rows))
    return rows


def load_chains(source) -> list[dict]:
    """Chain records deduped by signature (last wins).

    Accepts an in-memory list of chain records, or a directory containing
    sonnet_chains_provisional_r*.jsonl round files — globbed in sorted order so
    a later round's re-emission of a signature wins, mirroring chain_store.
    Records missing required keys are dropped+logged (schema-drift guard).
    """
    if isinstance(source, (str, Path)):
        directory = Path(source)
        if not directory.is_dir():
            raise FileNotFoundError(f"chains directory not found: {directory}")
        records: list[dict] = []
        for p in sorted(directory.glob(CHAINS_GLOB)):
            recs, skipped = read_jsonl_skip_malformed(p)
            if skipped:
                log.warning("load_chains: skipped %d malformed line(s) in %s", skipped, p)
            records.extend(recs)
    else:
        records = list(source)

    by_sig: dict[str, dict] = {}
    dropped = 0
    for r in records:
        if not all(r.get(k) for k in _REQUIRED_CHAIN_KEYS):
            dropped += 1
            continue
        by_sig[r["chain_signature"]] = r
    if dropped:
        log.warning("load_chains: dropped %d chain record(s) missing required keys", dropped)
    return list(by_sig.values())


def load_glosses(source) -> dict:
    """synset_id -> {pos, definition}, from a prebuilt map or the
    chain_glosses_provisional.jsonl path (same projection as the sidecar's
    /glosses route). A missing FILE degrades to {} with a warning — glosses
    are enrichment, the contract allows topic_gloss/vehicle_gloss = None —
    unlike the gold file, whose absence escalates in load_resolved.
    """
    if not isinstance(source, (str, Path)):
        return dict(source)
    path = Path(source)
    if not path.exists():
        log.warning("load_glosses: %s missing — context will attach gloss-free", path)
        return {}
    records, skipped = read_jsonl_skip_malformed(path)
    if skipped:
        log.warning("load_glosses: skipped %d malformed line(s) in %s", skipped, path)
    return {r["synset_id"]: {"pos": r.get("pos"), "definition": r.get("definition")}
            for r in records if r.get("synset_id")}


def attach_chain_context(rows: list[dict], chains, glosses) -> list[dict]:
    """Join chain steps + endpoint glosses onto corpus rows (non-mutating).

    chains: list of chain records or a round-file directory (see load_chains);
    glosses: synset_id map or the gloss JSONL path (see load_glosses).

    Adds `chain` ([{phrase, head, synset_id}]), `topic_gloss`/`vehicle_gloss`
    ({pos, definition} or None) and `chain_missing`. A row with no matching
    chain is flagged+logged, never dropped — silently shrinking the gold
    corpus would skew every kappa downstream.
    """
    chain_by_sig = {c["chain_signature"]: c for c in load_chains(chains)}
    gloss_map = load_glosses(glosses)
    out: list[dict] = []
    n_missing = 0
    for r in rows:
        chain_rec = chain_by_sig.get(r.get("chain_signature"))
        if chain_rec is None:
            n_missing += 1
            log.warning("attach_chain_context: no chain for signature %s (%s -> %s)",
                        r.get("chain_signature"), r.get("topic"), r.get("vehicle"))
        # Project steps to the contract keys so generator-side extras don't leak.
        steps = [{"phrase": s.get("phrase"), "head": s.get("head"),
                  "synset_id": s.get("synset_id")}
                 for s in (chain_rec or {}).get("chain", [])]
        out.append({**r,
                    "chain": steps,
                    "topic_gloss": gloss_map.get(r.get("topic_synset_id")),
                    "vehicle_gloss": gloss_map.get(r.get("vehicle_synset_id")),
                    "chain_missing": chain_rec is None})
    if n_missing:
        log.warning("attach_chain_context: %d/%d row(s) missing a chain record",
                    n_missing, len(rows))
    log.info("attach_chain_context: %d row(s), %d gloss entr(y/ies) available",
             len(out), len(gloss_map))
    return out
