"""Tests for the deterministic chain.v1 head-backfill pass.

`backfill_chain_record` re-derives every INTERMEDIATE step's head from its phrase
via the no-LLM extractor and re-snaps the synset via an injected lookup. The
topic/vehicle endpoints are canonical and must be left untouched. No model spend.
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from head_extraction_backfill import backfill_chain_record


def _fake_snap(head: str):
    # Deterministic stub: synset = "syn:<head>", or None for a known miss.
    return None if head == "nowhere" else f"syn:{head}"


_BASE = {
    "schema_version": "chain.v1",
    "topic": "ambush",
    "topic_synset_id": "100",
    "vehicle": "avalanche",
    "vehicle_synset_id": "200",
    "proposer": "sonnet_v1",
    "round": 2,
    "chain_signature": "a" * 64,
    "generated_at": "2026-06-04T00:00:00Z",
    "chain": [
        {"phrase": "ambush", "head": "ambush", "synset_id": "100"},
        # bad emitted head: premodifier chosen over the noun
        {"phrase": "lightning strike", "head": "lightning", "synset_id": "syn:lightning"},
        # already-correct premodifier head
        {"phrase": "hidden accumulation", "head": "accumulation", "synset_id": "syn:accumulation"},
        {"phrase": "avalanche", "head": "avalanche", "synset_id": "200"},
    ],
}


def test_corrects_bad_intermediate_head_and_resnaps():
    out = backfill_chain_record(_BASE, _fake_snap)
    # the premodifier defect is repaired and the synset re-snapped to the new head
    assert out["chain"][1]["head"] == "strike"
    assert out["chain"][1]["synset_id"] == "syn:strike"


def test_leaves_correct_intermediate_head_untouched():
    out = backfill_chain_record(_BASE, _fake_snap)
    assert out["chain"][2]["head"] == "accumulation"
    assert out["chain"][2]["synset_id"] == "syn:accumulation"


def test_endpoints_are_never_modified():
    out = backfill_chain_record(_BASE, _fake_snap)
    assert out["chain"][0] == {"phrase": "ambush", "head": "ambush", "synset_id": "100"}
    assert out["chain"][-1] == {"phrase": "avalanche", "head": "avalanche", "synset_id": "200"}


def test_does_not_mutate_input():
    import copy
    original = copy.deepcopy(_BASE)
    backfill_chain_record(_BASE, _fake_snap)
    assert _BASE == original


def test_idempotent():
    once = backfill_chain_record(_BASE, _fake_snap)
    twice = backfill_chain_record(once, _fake_snap)
    assert once == twice


def test_signature_and_metadata_preserved():
    out = backfill_chain_record(_BASE, _fake_snap)
    assert out["chain_signature"] == _BASE["chain_signature"]
    assert out["topic_synset_id"] == "100"
    assert out["vehicle_synset_id"] == "200"
    assert out["generated_at"] == _BASE["generated_at"]


def test_unresolved_synset_becomes_none():
    rec = {
        **_BASE,
        "chain": [
            {"phrase": "ambush", "head": "ambush", "synset_id": "100"},
            {"phrase": "nowhere", "head": "nowhere", "synset_id": "old"},
            {"phrase": "avalanche", "head": "avalanche", "synset_id": "200"},
        ],
    }
    out = backfill_chain_record(rec, _fake_snap)
    assert out["chain"][1]["head"] == "nowhere"
    assert out["chain"][1]["synset_id"] is None
