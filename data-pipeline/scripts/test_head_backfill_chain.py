"""Tests for the deterministic chain.v1 head-backfill pass.

`backfill_chain_record` re-derives every INTERMEDIATE step's head from its phrase
via the no-LLM extractor and re-snaps the synset via an injected lookup. The
topic/vehicle endpoints are canonical and must be left untouched. No model spend.
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from head_extraction_backfill import backfill_chain_record, is_confident_improvement


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
    # confident=False = unconditional rewrite: every intermediate head re-derived.
    out = backfill_chain_record(_BASE, _fake_snap, confident=False)
    # the premodifier defect is repaired and the synset re-snapped to the new head
    assert out["chain"][1]["head"] == "strike"
    assert out["chain"][1]["synset_id"] == "syn:strike"


def test_leaves_correct_intermediate_head_untouched():
    out = backfill_chain_record(_BASE, _fake_snap, confident=False)
    assert out["chain"][2]["head"] == "accumulation"
    assert out["chain"][2]["synset_id"] == "syn:accumulation"


def test_endpoints_are_never_modified():
    out = backfill_chain_record(_BASE, _fake_snap, confident=False)
    assert out["chain"][0] == {"phrase": "ambush", "head": "ambush", "synset_id": "100"}
    assert out["chain"][-1] == {"phrase": "avalanche", "head": "avalanche", "synset_id": "200"}


def test_does_not_mutate_input():
    import copy
    original = copy.deepcopy(_BASE)
    backfill_chain_record(_BASE, _fake_snap, confident=False)
    assert _BASE == original


def test_idempotent():
    once = backfill_chain_record(_BASE, _fake_snap, confident=False)
    twice = backfill_chain_record(once, _fake_snap, confident=False)
    assert once == twice


def test_signature_and_metadata_preserved():
    out = backfill_chain_record(_BASE, _fake_snap, confident=False)
    assert out["chain_signature"] == _BASE["chain_signature"]
    assert out["topic_synset_id"] == "100"
    assert out["vehicle_synset_id"] == "200"
    assert out["generated_at"] == _BASE["generated_at"]


# --- confident-only replacement policy -----------------------------------

def test_confident_improvement_fires_on_premodifier_over_noun():
    # adjective premodifier emitted instead of the trailing noun head
    assert is_confident_improvement("boundary line", "boundary", "line") is True
    assert is_confident_improvement("filigree work", "filigree", "work") is True


def test_confident_improvement_fires_on_compound_restore():
    # model stripped a hyphen prefix; restore the full compound
    assert is_confident_improvement("self-reflection", "reflection", "self-reflection") is True
    assert is_confident_improvement("heat-fusion", "fusion", "heat-fusion") is True


def test_confident_improvement_suppresses_ambiguous_subject_gerund():
    # "death spreading" — subject + predicate gerund; keep the emitted noun.
    assert is_confident_improvement("death spreading", "death", "spreading") is False
    # "X of Y" head-shift is not high-confidence either.
    assert is_confident_improvement("loss of bearings", "orientation", "loss") is False
    # particle/adverb grabs must never be confident.
    assert is_confident_improvement("traces beneath", "traces", "beneath") is False


def test_confident_mode_only_changes_high_confidence_steps():
    rec = {
        **_BASE,
        "chain": [
            {"phrase": "ambush", "head": "ambush", "synset_id": "100"},
            {"phrase": "boundary line", "head": "boundary", "synset_id": "syn:boundary"},
            {"phrase": "death spreading", "head": "death", "synset_id": "syn:death"},
            {"phrase": "avalanche", "head": "avalanche", "synset_id": "200"},
        ],
    }
    out = backfill_chain_record(rec, _fake_snap, confident=True)
    # premodifier defect fixed
    assert out["chain"][1]["head"] == "line"
    assert out["chain"][1]["synset_id"] == "syn:line"
    # ambiguous subject+gerund left untouched (emitted head + its synset preserved)
    assert out["chain"][2]["head"] == "death"
    assert out["chain"][2]["synset_id"] == "syn:death"


def test_unresolved_synset_becomes_none():
    rec = {
        **_BASE,
        "chain": [
            {"phrase": "ambush", "head": "ambush", "synset_id": "100"},
            {"phrase": "nowhere", "head": "nowhere", "synset_id": "old"},
            {"phrase": "avalanche", "head": "avalanche", "synset_id": "200"},
        ],
    }
    out = backfill_chain_record(rec, _fake_snap, confident=False)
    assert out["chain"][1]["head"] == "nowhere"
    assert out["chain"][1]["synset_id"] is None
