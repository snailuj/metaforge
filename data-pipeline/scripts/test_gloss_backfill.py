"""Tests for gloss_backfill.py — enrich EXISTING chains with model-inferred
per-node sense glosses, then re-snap by gloss-match.

Faster than re-generation and preserves the original edges + chain_signature
(so existing verdicts / the 121 human sense-labels stay valid). The model call
is injected so these tests make no API calls.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from gloss_backfill import (
    build_gloss_prompt,
    parse_gloss_response,
    backfill_chain_record,
    build_topic_gloss_prompt,
    parse_topic_gloss_response,
)


def _record(**over):
    base = {
        "schema_version": "chain.v1",
        "topic": "tension", "topic_synset_id": "1",
        "vehicle": "tempest", "vehicle_synset_id": "100",
        "proposer": "sonnet_v1", "round": 3,
        "chain": [
            {"phrase": "tension", "head": "tension", "synset_id": "1"},
            {"phrase": "pressure", "head": "pressure", "synset_id": "5"},
            {"phrase": "tempest", "head": "tempest", "synset_id": "100"},
        ],
        "chain_signature": "a" * 64,
        "generated_at": "2026-06-19T00:00:00Z",
    }
    base.update(over)
    return base


# --- build_gloss_prompt -----------------------------------------------------

def test_prompt_shows_chain_and_asks_for_per_node_sense():
    p = build_gloss_prompt("tension", "mental or emotional strain",
                           ["tension", "pressure", "tempest"])
    assert "tension" in p and "pressure" in p and "tempest" in p
    assert "mental or emotional strain" in p   # topic gloss given as context
    assert "sense" in p.lower()
    assert "gloss" in p.lower()


def test_prompt_requests_strict_json_list():
    p = build_gloss_prompt("tension", "strain", ["tension", "pressure", "tempest"])
    assert "JSON" in p


# --- parse_gloss_response ---------------------------------------------------

def test_parse_accepts_glosses_key():
    out = parse_gloss_response({"glosses": ["a sense", "b sense"]}, n_expected=2)
    assert out == ["a sense", "b sense"]


def test_parse_accepts_bare_list():
    out = parse_gloss_response(["a sense", "b sense"], n_expected=2)
    assert out == ["a sense", "b sense"]


def test_parse_rejects_wrong_count():
    with pytest.raises(ValueError):
        parse_gloss_response(["only one"], n_expected=2)


# --- backfill_chain_record --------------------------------------------------

def _snap(mapping):
    """snap_fn double: (head, gloss) -> sid (gloss-match), else None."""
    return lambda head, gloss: mapping.get((head, gloss))


def test_backfill_attaches_glosses_and_resnaps_nontopic_nodes():
    rec = _record()
    glosses = ["the build-up of force", "a violent emotional upheaval"]  # step, vehicle
    snap = _snap({("pressure", "the build-up of force"): "5g",
                  ("tempest", "a violent emotional upheaval"): "200"})
    out = backfill_chain_record(rec, glosses, snap, topic_gloss="emotional strain")

    # topic node untouched except it gains the curated gloss; synset stays canonical
    assert out["chain"][0]["synset_id"] == "1"
    assert out["chain"][0]["gloss"] == "emotional strain"
    # step + vehicle re-snapped by gloss-match and carry their gloss
    assert out["chain"][1]["synset_id"] == "5g"
    assert out["chain"][1]["gloss"] == "the build-up of force"
    assert out["chain"][-1]["synset_id"] == "200"
    assert out["chain"][-1]["gloss"] == "a violent emotional upheaval"
    # the record's vehicle_synset_id follows the vehicle node
    assert out["vehicle_synset_id"] == "200"
    # signature is phrase-based -> unchanged (existing verdicts stay valid)
    assert out["chain_signature"] == rec["chain_signature"]


def test_backfill_falls_back_to_existing_synset_when_no_gloss_match():
    rec = _record()
    glosses = ["x", "y"]
    snap = _snap({})  # never matches
    out = backfill_chain_record(rec, glosses, snap)
    assert out["chain"][1]["synset_id"] == "5"      # unchanged
    assert out["chain"][-1]["synset_id"] == "100"   # unchanged
    assert out["chain"][1]["gloss"] == "x"          # gloss still recorded
    assert out["vehicle_synset_id"] == "100"


def test_backfill_does_not_mutate_input():
    rec = _record()
    backfill_chain_record(rec, ["x", "y"], _snap({("pressure", "x"): "9"}))
    assert rec["chain"][1]["synset_id"] == "5"      # original untouched
    assert "gloss" not in rec["chain"][1]


def test_backfill_guards_against_self_metaphor_collapse():
    # if re-snapping the vehicle would collapse it onto the topic synset, keep original
    rec = _record()
    snap = _snap({("tempest", "g2"): "1"})  # would make vehicle == topic synset "1"
    out = backfill_chain_record(rec, ["g1", "g2"], snap)
    assert out["chain"][-1]["synset_id"] == "100"   # reverted to original
    assert out["vehicle_synset_id"] == "100"


def test_backfill_rejects_gloss_count_mismatch():
    with pytest.raises(ValueError):
        backfill_chain_record(_record(), ["only-one"], _snap({}))


# --- index_chains_by_signature (validation loader) --------------------------

# --- per-topic batched prompt / parse (corpus rollout) ----------------------

_CHAINS = [
    ["tension", "pressure", "tempest"],
    ["tension", "strain", "quake", "rupture"],
]


def test_topic_prompt_shows_every_chain_and_node():
    p = build_topic_gloss_prompt("tension", "emotional strain", _CHAINS)
    for node in ["pressure", "tempest", "strain", "quake", "rupture"]:
        assert node in p
    assert "emotional strain" in p
    assert "JSON" in p and "chains" in p.lower()


def test_parse_topic_response_shapes_match_chains():
    resp = {"chains": [["g-pressure", "g-tempest"],
                       ["g-strain", "g-quake", "g-rupture"]]}
    out = parse_topic_gloss_response(resp, _CHAINS)
    assert out == [["g-pressure", "g-tempest"], ["g-strain", "g-quake", "g-rupture"]]


def test_parse_topic_response_rejects_wrong_chain_count():
    with pytest.raises(ValueError):
        parse_topic_gloss_response({"chains": [["only-one-chain", "x"]]}, _CHAINS)


def test_parse_topic_response_rejects_wrong_node_count():
    bad = {"chains": [["g-pressure"], ["g-strain", "g-quake", "g-rupture"]]}  # chain 0 short
    with pytest.raises(ValueError):
        parse_topic_gloss_response(bad, _CHAINS)


def test_index_chains_by_signature_first_seen_wins(tmp_path):
    from validate_gloss_backfill import index_chains_by_signature
    p = tmp_path / "c.jsonl"
    p.write_text(
        '{"chain_signature":"sig1","chain":[{"phrase":"a"}]}\n'
        '\n'
        '{"chain_signature":"sig1","chain":[{"phrase":"DUP"}]}\n'
        '{"chain_signature":"sig2","chain":[{"phrase":"b"}]}\n'
    )
    idx = index_chains_by_signature([str(p), str(tmp_path / "missing.jsonl")])
    assert set(idx) == {"sig1", "sig2"}
    assert idx["sig1"]["chain"][0]["phrase"] == "a"  # first seen, not DUP


def test_done_topic_synset_ids_reads_output(tmp_path):
    from gloss_backfill import done_topic_synset_ids
    p = tmp_path / "out.jsonl"
    p.write_text('{"topic_synset_id":"1"}\n{"topic_synset_id":"2"}\n{"topic_synset_id":"1"}\n')
    assert done_topic_synset_ids(str(p)) == {"1", "2"}
    assert done_topic_synset_ids(str(tmp_path / "nope.jsonl")) == set()
