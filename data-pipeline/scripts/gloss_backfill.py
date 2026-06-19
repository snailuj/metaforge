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

import json
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
