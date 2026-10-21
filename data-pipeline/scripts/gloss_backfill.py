"""Gloss-backfill: enrich EXISTING chains with model-inferred per-node sense
glosses, then re-snap by gloss-match.

Faster than re-generation and — crucially — preserves the original edges and the
phrase-based `chain_signature`, so existing verdicts and the human sense-labels
stay valid. The model reads a coherent chain (topic → … → vehicle) and infers
the sense each node carries IN CONTEXT; we then re-snap via the same gloss-match
WSD used at generation time (metaphor_graph.snap_by_gloss). This is post-hoc
inference of intent, not the generator's recorded intent, so it is MEASURED
against the operator's human sense-labels before being trusted at scale.

Pure functions here; the CLI driver injects the model call (claude_client.
prompt_json) and the snapper so tests stay offline.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Callable, Optional


def build_gloss_prompt(topic: str, topic_gloss: str,
                       chain_phrases: list[str]) -> str:
    """Prompt the model to gloss the intended sense of each non-topic node.

    The topic's curated sense is given as context; the model returns a one-line
    dictionary-style gloss for each subsequent node (steps + vehicle), reading
    the sense each carries within this specific chain.
    """
    arrow = " → ".join(chain_phrases)
    targets = chain_phrases[1:]  # steps + vehicle; the topic sense is given
    numbered = "\n".join(f"  {i + 1}. {p}" for i, p in enumerate(targets))
    return f"""You are disambiguating word senses in an existing metaphor chain.

The chain walks from a topic to a vehicle, one concept per step:
  {arrow}

The TOPIC "{topic}" is used in this sense: {topic_gloss}

For EACH of the following nodes, give a one-line dictionary-style gloss of the
SPECIFIC SENSE the word carries AS USED IN THIS CHAIN (read the surrounding
steps to fix the sense — e.g. in an emotional chain "tension" means mental
strain, not the physics sense). Do not invent a new chain; just report the
sense each existing node intends.

Nodes to gloss (in order):
{numbered}

Respond with STRICT JSON and nothing else: a list of {len(targets)} one-line
gloss strings, in the same order as the nodes above:
{{"glosses": ["<sense of node 1>", "<sense of node 2>", ...]}}"""


def build_topic_gloss_prompt(topic: str, topic_gloss: str,
                             chains: list[list[str]]) -> str:
    """Prompt to gloss EVERY node of every chain a topic appears in, in one call.

    One model call per topic (not per chain) keeps the corpus rollout to ~one
    call per topic. Each chain shares the same topic sense (given); the model
    returns, per chain, a one-line sense gloss for each non-topic node.
    """
    blocks = []
    for i, ch in enumerate(chains):
        arrow = " → ".join(ch)
        targets = "\n".join(f"     {j + 1}. {p}" for j, p in enumerate(ch[1:]))
        blocks.append(f"  CHAIN {i + 1}: {arrow}\n   nodes to gloss:\n{targets}")
    chains_text = "\n\n".join(blocks)
    shape = ", ".join(f"[{len(ch) - 1} glosses]" for ch in chains)
    return f"""You are disambiguating word senses in existing metaphor chains.

Every chain below starts from the topic "{topic}", used in this sense:
  {topic_gloss}

Each chain walks one concept per step from that topic to a vehicle. For EACH
non-topic node, give a one-line dictionary-style gloss of the SPECIFIC SENSE the
word carries AS USED IN THAT CHAIN (read the surrounding steps to fix the sense —
e.g. in an emotional chain "tension" is mental strain, not the physics sense).
Report the sense each existing node intends; do not invent new chains.

{chains_text}

Respond with STRICT JSON and nothing else, preserving chain order and giving one
gloss per non-topic node ({shape}):
{{"chains": [["<sense>", "<sense>", ...], ...]}}"""


def parse_topic_gloss_response(resp, chains: list[list[str]]) -> list[list[str]]:
    """Extract per-chain gloss lists, validating outer + inner shapes.

    Raises ValueError on any shape mismatch so the driver skips that topic
    rather than mis-aligning glosses to nodes.
    """
    if isinstance(resp, dict):
        outer = resp.get("chains")
    else:
        outer = resp
    if not isinstance(outer, list):
        raise ValueError(f"expected a list of chains, got {type(resp).__name__}")
    if len(outer) != len(chains):
        raise ValueError(f"expected {len(chains)} chains, got {len(outer)}")
    out = []
    for i, (glosses, ch) in enumerate(zip(outer, chains)):
        if not isinstance(glosses, list):
            raise ValueError(f"chain {i}: expected a list of glosses")
        glosses = [str(g) for g in glosses]
        if len(glosses) != len(ch) - 1:
            raise ValueError(
                f"chain {i}: expected {len(ch) - 1} glosses, got {len(glosses)}")
        out.append(glosses)
    return out


def parse_gloss_response(resp, n_expected: int) -> list[str]:
    """Extract exactly `n_expected` gloss strings from a model response.

    Accepts {"glosses": [...]} or a bare list. Raises ValueError on a count
    mismatch so the driver skips/logs that record rather than mis-aligning
    glosses to nodes.
    """
    if isinstance(resp, dict):
        glosses = resp.get("glosses")
    else:
        glosses = resp
    if not isinstance(glosses, list):
        raise ValueError(f"expected a list of glosses, got {type(resp).__name__}")
    glosses = [str(g) for g in glosses]
    if len(glosses) != n_expected:
        raise ValueError(f"expected {n_expected} glosses, got {len(glosses)}")
    return glosses


def backfill_chain_record(record: dict, glosses: list[str],
                          snap_fn: Callable[[str, str], Optional[str]],
                          topic_gloss: Optional[str] = None) -> dict:
    """Return a copy of `record` with glosses attached and non-topic nodes
    re-snapped by gloss-match.

    `glosses` corresponds to chain[1:] (steps + vehicle). The topic node stays
    canonical (its curated synset_id is authoritative); it gains `topic_gloss`
    when supplied. Each non-topic node is re-snapped via snap_fn(head, gloss),
    falling back to its existing synset_id on no match. The record's
    vehicle_synset_id follows the vehicle node, EXCEPT a re-snap that would
    collapse the vehicle onto the topic synset is reverted (not a metaphor).
    `chain_signature` is phrase-based and therefore unchanged.
    """
    chain = record["chain"]
    non_topic = chain[1:]
    if len(glosses) != len(non_topic):
        raise ValueError(f"expected {len(non_topic)} glosses, got {len(glosses)}")

    nodes = [dict(s) for s in chain]  # deep-enough copy (steps are flat dicts)
    if topic_gloss is not None:
        nodes[0]["gloss"] = topic_gloss

    topic_sid = nodes[0].get("synset_id")
    for node, gloss in zip(nodes[1:], glosses):
        node["gloss"] = gloss
        new_sid = snap_fn(node["head"], gloss) or node.get("synset_id")
        node["synset_id"] = new_sid

    # a vehicle re-snap that collapses onto the topic synset is not a metaphor
    if nodes[-1].get("synset_id") == topic_sid:
        nodes[-1]["synset_id"] = chain[-1].get("synset_id")

    out = dict(record)
    out["chain"] = nodes
    out["vehicle_synset_id"] = nodes[-1].get("synset_id")
    return out


def resnap_chain_record(record: dict,
                        snap_fn: Callable[[str, str], Optional[str]]) -> dict:
    """Re-snap an already-glossed record's non-topic nodes via snap_fn(head,
    gloss), keeping the captured glosses. $0 pass (no model call): used to swap
    the token-overlap snap for an embedding snap once glosses exist. Topic node
    stays canonical; a vehicle re-snap that collapses onto the topic synset is
    reverted; chain_signature (phrase-based) is unchanged.
    """
    chain = record["chain"]
    nodes = [dict(s) for s in chain]
    topic_sid = nodes[0].get("synset_id")
    for node in nodes[1:]:
        gloss = node.get("gloss")
        if not gloss:
            continue  # nothing to snap on
        node["synset_id"] = snap_fn(node["head"], gloss) or node.get("synset_id")
    if nodes[-1].get("synset_id") == topic_sid:
        nodes[-1]["synset_id"] = chain[-1].get("synset_id")
    out = dict(record)
    out["chain"] = nodes
    out["vehicle_synset_id"] = nodes[-1].get("synset_id")
    return out


# --- driver -----------------------------------------------------------------

def done_topic_synset_ids(output_path: str) -> set[str]:
    """Topic synset_ids already written to the output (resume key)."""
    p = Path(output_path)
    if not p.exists():
        return set()
    done: set[str] = set()
    for line in p.open():
        line = line.strip()
        if not line:
            continue
        try:
            t = json.loads(line).get("topic_synset_id")
        except json.JSONDecodeError:
            continue
        if t:
            done.add(str(t))
    return done


def _group_by_topic(records: list[dict]) -> list[tuple[str, list[dict]]]:
    """Group chain records by topic_synset_id, preserving first-seen order."""
    order: list[str] = []
    groups: dict[str, list[dict]] = {}
    for r in records:
        t = str(r.get("topic_synset_id"))
        if t not in groups:
            groups[t] = []
            order.append(t)
        groups[t].append(r)
    return [(t, groups[t]) for t in order]


def main(argv=None) -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))
    from metaphor_graph import snap_by_gloss
    from claude_client import prompt_json

    ap = argparse.ArgumentParser(description="Gloss-backfill a corpus chain file.")
    ap.add_argument("--in", dest="inp", required=True, help="input chain.v1 JSONL")
    ap.add_argument("--out", required=True, help="output JSONL (resumable, append)")
    ap.add_argument("--db", required=True, help="lexicon_v2.db for gloss-match snap")
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--limit", type=int, default=None, help="max topics this run")
    args = ap.parse_args(argv)

    conn = sqlite3.connect(args.db)
    snap = lambda head, gloss: snap_by_gloss(conn, head, gloss)  # noqa: E731

    def topic_gloss_of(tsid: str) -> str:
        row = conn.execute("SELECT definition FROM synsets WHERE synset_id = ?",
                           (tsid,)).fetchone()
        return row[0] if row else ""

    records = [json.loads(l) for l in open(args.inp) if l.strip()]
    records = [r for r in records if r.get("schema_version") == "chain.v1"
               and isinstance(r.get("chain"), list)]
    groups = _group_by_topic(records)
    done = done_topic_synset_ids(args.out)
    pending = [(t, recs) for t, recs in groups if t not in done]
    if args.limit:
        pending = pending[:args.limit]
    print(f"{len(groups)} topics total, {len(done)} done, processing {len(pending)} now")

    t0 = time.monotonic()
    written = ok = failed = 0
    with open(args.out, "a") as out:
        for n, (tsid, recs) in enumerate(pending, 1):
            topic = recs[0].get("topic", "")
            tgloss = topic_gloss_of(tsid)
            chains = [[s["phrase"] for s in r["chain"]] for r in recs]
            try:
                resp = prompt_json(build_topic_gloss_prompt(topic, tgloss, chains),
                                   model=args.model)
                per_chain = parse_topic_gloss_response(resp, chains)
                for r, glosses in zip(recs, per_chain):
                    bf = backfill_chain_record(r, glosses, snap, topic_gloss=tgloss)
                    out.write(json.dumps(bf) + "\n")
                    written += 1
                out.flush()
                ok += 1
                print(f"[{n}/{len(pending)}] OK {topic!r} ({len(recs)} chains)")
            except Exception as exc:  # noqa: BLE001 — skip topic, retry on resume
                failed += 1
                print(f"[{n}/{len(pending)}] FAIL {topic!r}: {exc}")
    conn.close()
    print(f"done in {time.monotonic() - t0:.0f}s: {ok} topics ok, {failed} failed, "
          f"{written} chains written -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
