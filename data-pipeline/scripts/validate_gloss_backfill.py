"""Validate the gloss-backfill against the operator's human sense-labels.

For each labelled VEHICLE endpoint (where the backfill does its work — topics
keep their curated gloss), find a representative chain, ask the model to infer
the vehicle's in-context sense gloss, snap it via gloss-match, and check whether
the snap lands on the sense the operator marked apt. Reports backfill accuracy
against the same gold the deterministic re-snap was measured on (current 51%,
tagcount baseline 61%) so we know whether to trust the backfill at scale.

Real model calls (subscription). Pure pieces are imported from already-tested
modules; this is glue + measurement.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))

from gloss_backfill import build_gloss_prompt, parse_gloss_response
from gloss_reconciliation_analysis import dedupe_latest, apt_target_set, snap_outcome, UNKNOWN
from metaphor_graph import snap_by_gloss
from claude_client import prompt_json

_HERE = Path(__file__).resolve()
_GRADING = _HERE.parents[1] / "grading"


def index_chains_by_signature(paths: list[str]) -> dict[str, dict]:
    """Map chain_signature -> one chain.v1 record (first seen)."""
    idx: dict[str, dict] = {}
    for p in paths:
        if not os.path.exists(p):
            continue
        for line in open(p):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            sig = r.get("chain_signature")
            if sig and sig not in idx and isinstance(r.get("chain"), list):
                idx[sig] = r
    return idx


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--labels", type=Path,
                    default=Path(".worktrees/grading-data/data-pipeline/grading/sense_labels_provisional.jsonl"))
    ap.add_argument("--db", type=Path, default=_HERE.parents[1] / "output" / "lexicon_v2.db")
    ap.add_argument("--sample", type=int, default=25, help="max vehicle endpoints to test")
    ap.add_argument("--model", default="sonnet")
    args = ap.parse_args(argv)

    labels = dedupe_latest([json.loads(l) for l in open(args.labels) if l.strip()])
    chain_paths = (glob.glob(str(_GRADING / "**" / "chain-topics_*.jsonl"), recursive=True)
                   + glob.glob(str(_GRADING / "*chains*.jsonl")))
    chains = index_chains_by_signature(chain_paths)
    conn = sqlite3.connect(str(args.db))

    # vehicle-role labels with a determinate apt target and a findable chain
    cand = [l for l in labels
            if l["role"] == "vehicle"
            and snap_outcome(l) != UNKNOWN
            and apt_target_set(l)
            and l.get("chain_signature") in chains]
    cand = cand[:args.sample]
    print(f"testing {len(cand)} vehicle endpoints (of {len(labels)} labels)\n")

    backfill_hit = current_hit = scored = 0
    for l in cand:
        rec = chains[l["chain_signature"]]
        phrases = [s["phrase"] for s in rec["chain"]]
        topic_gloss = rec["chain"][0].get("gloss") or ""
        target = apt_target_set(l)
        try:
            resp = prompt_json(build_gloss_prompt(rec["topic"], topic_gloss, phrases),
                               model=args.model)
            glosses = parse_gloss_response(resp, len(phrases) - 1)
        except Exception as exc:  # noqa: BLE001 — skip a bad call, keep measuring
            print(f"  SKIP {l['word']!r}: {exc}")
            continue
        veh_gloss = glosses[-1]
        pred = snap_by_gloss(conn, rec["chain"][-1]["head"], veh_gloss)
        scored += 1
        bh = pred in target
        ch = l["snapped_synset_id"] in target
        backfill_hit += int(bh)
        current_hit += int(ch)
        print(f"  {l['word']:16} verdict={l['verdict']:6} "
              f"current={'HIT' if ch else 'miss'} backfill={'HIT' if bh else 'miss'} "
              f"pred={pred} target={sorted(target)} gloss={veh_gloss[:45]!r}")

    conn.close()
    if scored:
        print(f"\nscored {scored}: "
              f"current-snap {current_hit}/{scored} = {100*current_hit//scored}%  |  "
              f"backfill {backfill_hit}/{scored} = {100*backfill_hit//scored}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
