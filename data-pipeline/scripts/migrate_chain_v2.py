"""Per-hop noun-prior snapper and chain.v1 → chain.v2 migration.

$0 pass (no model or LLM calls) — uses existing glosses via snap_by_gloss_embed
(FastText cosine) falling back to snap_by_gloss (token overlap), then the
noun-POS inventory prior.  Originals are untouched; a new sibling file is
written per input.  chain_signature is phrase-based and is NEVER recomputed —
it is verified to be consistent with the output phrases and a RuntimeError is
raised on mismatch (guards against phrase mutation bugs).

Public surface (consumed by later tasks and the CLI):
  noun_prior_snap(conn, vectors, phrase, head, gloss) -> dict
      Per-hop snap: gloss evidence first, then noun prior, then vec: gate.
  migrate_record(rec: dict, snap_fn) -> dict
      chain.v1 dict → chain.v2 dict; chain.v2 inputs returned unchanged.
  migrate_file(in_path, out_path, snap_fn, force=False) -> dict
      File-level idempotent wrapper with per-step confidence counters.
  make_snap_fn(conn, vectors) -> callable
      Bind conn/vectors into a (phrase, head, gloss) → dict closure.
  main(argv) — CLI driver.
"""
from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "grading_sidecar"))

from metaphor_graph import snap_by_gloss, snap_by_gloss_embed
from models import compute_chain_signature, vec_ref
from sense_inventory import noun_inventory, vec_gate

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Core snapper
# ---------------------------------------------------------------------------

def noun_prior_snap(conn: sqlite3.Connection, vectors,
                    phrase: str, head: str, gloss: Optional[str]) -> dict:
    """Per-hop noun-prior snapper for chain migration.

    Priority (spec §4):
    1. Gloss evidence — snap_by_gloss_embed (FastText cosine) then snap_by_gloss
       (token overlap).  If either returns a synset, ACCEPT it unconditionally:
       decisive gloss evidence overrides the noun prior even for cross-POS senses.
    2. No snap result → check vec_gate:
       - True (no noun synset for phrase or head): admit as vec: node.
       - False: fall back to the top noun-inventory sense with confidence='low'.

    Logs vec: admissions and low-confidence snaps with phrase so operators can
    audit the flow.  Never silently drops a step — always returns a result.
    """
    synset_id: Optional[str] = None

    if gloss:
        # Try embedding snap first (FastText cosine), fall back to token overlap.
        synset_id = (snap_by_gloss_embed(conn, head, gloss, vectors)
                     or snap_by_gloss(conn, head, gloss))

    if synset_id is not None:
        return {
            "synset_id": synset_id,
            "node_ref": f"syn:{synset_id}",
            "confidence": "ok",
        }

    # No gloss evidence — consult the vec: gate then the noun prior.
    if vec_gate(conn, phrase, head):
        node_ref = f"vec:{vec_ref(phrase)}"
        log.info("noun_prior_snap: vec: admission — phrase=%r head=%r", phrase, head)
        return {"synset_id": None, "node_ref": node_ref, "confidence": "vec"}

    inv = noun_inventory(conn, phrase, head)
    top_sid = inv[0]["synset_id"]   # inv is non-empty: vec_gate returned False
    log.warning("noun_prior_snap: low-confidence snap — phrase=%r head=%r "
                "snapped=%s", phrase, head, top_sid)
    return {
        "synset_id": top_sid,
        "node_ref": f"syn:{top_sid}",
        "confidence": "low",
    }


# ---------------------------------------------------------------------------
# Record migration
# ---------------------------------------------------------------------------

def migrate_record(rec: dict, snap_fn: Callable) -> dict:
    """Return a chain.v2 dict from a chain.v1 dict.

    snap_fn(phrase, head, gloss) → {synset_id, node_ref, confidence}.
    Records already at chain.v2 are returned unchanged (idempotency).
    The chain_signature is verified against the output phrases after migration;
    a RuntimeError is raised on mismatch — phrases must be byte-stable across
    the migration so all existing verdicts stay valid.
    """
    if rec.get("schema_version") == "chain.v2":
        return rec

    chain = rec.get("chain", [])
    out_chain = []
    for step in chain:
        phrase = step["phrase"]
        head   = step["head"]
        gloss  = step.get("gloss")

        result = snap_fn(phrase, head, gloss)
        sid    = result["synset_id"]

        out_step = dict(step)
        out_step["synset_id"] = sid
        out_step["node_ref"]  = result["node_ref"]
        # apt_senses carries the intended sense when a synset resolved; vec: steps
        # yield an empty list (the node has no co-apt senses to enumerate yet).
        out_step["apt_senses"] = (
            [{"synset_id": sid, "source": "intended"}] if sid is not None else []
        )
        out_chain.append(out_step)

    # Build output record; mirror endpoint fields from the re-snapped steps.
    out = dict(rec)
    out["chain"] = out_chain
    out["schema_version"] = "chain.v2"

    topic_step   = out_chain[0]
    vehicle_step = out_chain[-1]

    out["topic_synset_id"]   = topic_step["synset_id"]
    out["topic_node_ref"]    = topic_step["node_ref"]
    out["vehicle_synset_id"] = vehicle_step["synset_id"]
    out["vehicle_node_ref"]  = vehicle_step["node_ref"]

    # Guard: phrases must be byte-stable across migration (the signature is
    # phrase-based — any mutation would silently invalidate all verdicts).
    proposer    = out["proposer"]
    out_phrases = [s["phrase"] for s in out_chain]
    recomputed  = compute_chain_signature(proposer, out_phrases)
    if recomputed != out["chain_signature"]:
        raise RuntimeError(
            f"chain_signature mismatch after migration: "
            f"recomputed {recomputed!r} != stored {out['chain_signature']!r} "
            f"— phrases were mutated or the input signature was corrupt"
        )

    return out


# ---------------------------------------------------------------------------
# File-level migration (with per-step confidence counters)
# ---------------------------------------------------------------------------

def migrate_file(in_path: str, out_path: str,
                 snap_fn: Callable, force: bool = False) -> dict:
    """Migrate a JSONL chain file from v1 to v2, collecting confidence stats.

    Writes `out_path` atomically (tmp + rename).  Skips (returns skipped=True)
    when `out_path` exists and `force` is False — mtime is not touched.
    The snap_fn is wrapped internally to count confidence outcomes per step.

    Returns summary: {records, resnapped_steps, vec_admissions, low_confidence}
    (plus skipped=True when skipped).
    """
    blank = {
        "records": 0, "resnapped_steps": 0,
        "vec_admissions": 0, "low_confidence": 0,
    }

    if Path(out_path).exists() and not force:
        log.info("migrate_file: skipping %s (output exists; pass force=True to overwrite)",
                 out_path)
        return {**blank, "skipped": True}

    # Wrap snap_fn in a counter so we track confidence outcomes per step.
    counts = {"resnapped_steps": 0, "vec_admissions": 0, "low_confidence": 0}

    def _counting_snap(phrase: str, head: str, gloss):
        result = snap_fn(phrase, head, gloss)
        # Every step routed through the snapper is a re-snap — this is the
        # throughput counter the migration audit reports on.
        counts["resnapped_steps"] += 1
        conf = result.get("confidence")
        if conf == "vec":
            counts["vec_admissions"] += 1
        elif conf == "low":
            counts["low_confidence"] += 1
        return result

    tmp_path = out_path + ".tmp"
    records = 0
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(in_path) as fin, open(tmp_path, "w") as fout:
            for line in fin:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError as exc:
                    log.warning("migrate_file: skipping malformed line: %s", exc)
                    continue
                if not isinstance(rec.get("chain"), list):
                    log.warning("migrate_file: skipping record without chain: %s",
                                rec.get("chain_signature", "<no sig>"))
                    continue
                out_rec = migrate_record(rec, _counting_snap)
                fout.write(json.dumps(out_rec) + "\n")
                records += 1
        # Atomic rename — readers never see a partial file.
        os.replace(tmp_path, out_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        raise

    return {
        "records": records,
        "resnapped_steps": counts["resnapped_steps"],
        "vec_admissions":  counts["vec_admissions"],
        "low_confidence":  counts["low_confidence"],
    }


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------

def make_snap_fn(conn: sqlite3.Connection, vectors) -> Callable:
    """Return a snap_fn(phrase, head, gloss) → dict closure bound to conn+vectors."""
    def _snap(phrase: str, head: str, gloss: Optional[str]) -> dict:
        return noun_prior_snap(conn, vectors, phrase, head, gloss)
    return _snap


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))
    from utils import load_fasttext_vectors, FASTTEXT_VEC

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", required=True, help="lexicon_v2.db (read-only)")
    ap.add_argument("--vectors", default=str(FASTTEXT_VEC),
                    help="FastText .vec file (default: %(default)s)")
    ap.add_argument("--in", dest="inputs", nargs="+", required=True,
                    help="input chain JSONL files or globs")
    ap.add_argument("--out-suffix", default="_v2",
                    help="suffix appended to the stem for output files (default: _v2)")
    ap.add_argument("--force", action="store_true",
                    help="overwrite existing output files")
    args = ap.parse_args(argv)

    t0 = time.monotonic()
    print(f"loading FastText vectors from {args.vectors} ...")
    vectors = load_fasttext_vectors(args.vectors)
    print(f"loaded in {time.monotonic() - t0:.0f}s")

    conn = sqlite3.connect(args.db)
    snap_fn = make_snap_fn(conn, vectors)

    # Expand globs in the input list.
    input_paths = []
    for pat in args.inputs:
        expanded = glob.glob(pat)
        if expanded:
            input_paths.extend(sorted(expanded))
        else:
            input_paths.append(pat)

    for inp in input_paths:
        p = Path(inp)
        out = str(p.parent / (p.stem + args.out_suffix + ".jsonl"))
        summary = migrate_file(inp, out, snap_fn, force=args.force)
        print(f"  {p.name} -> {Path(out).name}: {json.dumps(summary)}")

    conn.close()
    print(f"done in {time.monotonic() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
