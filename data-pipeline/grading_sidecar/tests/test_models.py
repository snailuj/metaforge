from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest
from grading_sidecar.models import (
    ChainRecord, ChainStep, JudgementRecord, DesignNotePost,
    compute_chain_signature, normalise_phrase, normalise_judgement,
)

def _step(phrase, head, synset_id):
    return ChainStep(phrase=phrase, head=head, synset_id=synset_id)

def _valid_chain(**overrides):
    base = dict(
        schema_version="chain.v1",
        topic="anger", topic_synset_id="12345",
        vehicle="venom", vehicle_synset_id="67890",
        proposer="sonnet_v1", round=1,
        chain=[
            _step("anger", "anger", "12345"),
            _step("hostility", "hostility", "54321"),
            _step("venom", "venom", "67890"),
        ],
        chain_signature="a" * 64,
        generated_at="2026-05-30T03:14:00Z",
    )
    base.update(overrides)
    return base

def test_chain_step_required_fields():
    s = ChainStep(phrase="anger", head="anger", synset_id="12345")
    assert s.phrase == "anger"

def test_chain_step_nullable_synset():
    s = ChainStep(phrase="tail meeting mouth", head="tail", synset_id=None)
    assert s.synset_id is None

def test_chain_record_rejects_unknown_schema_version():
    with pytest.raises(ValueError):
        ChainRecord(**_valid_chain(schema_version="chain.v999"))

def test_chain_record_endpoint_canonicalisation():
    """chain[0]/chain[-1] MUST match top-level topic/vehicle fields."""
    bad = _valid_chain(chain=[
        _step("WRONG", "WRONG", "99999"),
        _step("venom", "venom", "67890"),
    ])
    with pytest.raises(ValueError, match="endpoint"):
        ChainRecord(**bad)

def test_chain_record_accepts_valid():
    r = ChainRecord(**_valid_chain())
    assert r.topic == "anger"

def test_judgement_record_rejects_bad_metaphor_verdict():
    with pytest.raises(ValueError):
        JudgementRecord(
            schema_version="judgement.v2",
            ts="2026-05-30T07:14:00Z", judged_by="julian", round=1,
            topic="anger", topic_synset_id="12345",
            vehicle="venom", vehicle_synset_id="67890",
            proposer="sonnet_v1", chain_signature="a" * 64,
            linkage="good", metaphor="bogus", confidence="high",
        )

def test_judgement_record_rejects_bad_linkage():
    with pytest.raises(ValueError):
        JudgementRecord(
            schema_version="judgement.v2",
            ts="2026-05-30T07:14:00Z", judged_by="julian", round=1,
            topic="anger", topic_synset_id="12345",
            vehicle="venom", vehicle_synset_id="67890",
            proposer="sonnet_v1", chain_signature="a" * 64,
            linkage="maybe", metaphor="live", confidence="high",
        )

def test_judgement_record_rejects_bad_confidence():
    with pytest.raises(ValueError):
        JudgementRecord(
            schema_version="judgement.v2",
            ts="2026-05-30T07:14:00Z", judged_by="julian", round=1,
            topic="anger", topic_synset_id="12345",
            vehicle="venom", vehicle_synset_id="67890",
            proposer="sonnet_v1", chain_signature="a" * 64,
            linkage="good", metaphor="live", confidence="enthusiastic",
        )

def test_judgement_notes_max_length():
    with pytest.raises(ValueError):
        JudgementRecord(
            schema_version="judgement.v2",
            ts="2026-05-30T07:14:00Z", judged_by="julian", round=1,
            topic="anger", topic_synset_id="12345",
            vehicle="venom", vehicle_synset_id="67890",
            proposer="sonnet_v1", chain_signature="a" * 64,
            linkage="bad", metaphor="dead", confidence="high",
            notes="x" * 1001,
        )

# --- v2 two-axis model + v1 read-compat normaliser ---

_ID = dict(
    schema_version="judgement.v1", judged_by="julian", round=1,
    topic="anger", topic_synset_id="12345",
    vehicle="venom", vehicle_synset_id="67890",
    proposer="sonnet_v1", chain_signature="a" * 64,
)

def _axes(raw: dict) -> tuple:
    d = normalise_judgement(raw)
    return (d["linkage"], d["metaphor"], d["tier"])

def test_v2_record_roundtrips_two_axes_and_optional_tier():
    rec = JudgementRecord(
        schema_version="judgement.v2", judged_by="julian", round=1,
        topic="anchor", topic_synset_id="syn-anchor", vehicle="stone",
        vehicle_synset_id="syn-stone", proposer="sonnet_v1",
        chain_signature="a" * 64, linkage="good", metaphor="dead", tier="obvious",
    )
    assert rec.linkage == "good" and rec.metaphor == "dead" and rec.tier == "obvious"

def test_v2_tier_optional_defaults_none():
    rec = JudgementRecord(
        schema_version="judgement.v2", judged_by="j", round=1,
        topic="t", topic_synset_id="s", vehicle="v", vehicle_synset_id="s2",
        proposer="p", chain_signature="b" * 64, linkage="good", metaphor="live",
    )
    assert rec.tier is None

def test_v2_record_rejects_bad_tier():
    with pytest.raises(ValueError):
        JudgementRecord(
            schema_version="judgement.v2", judged_by="j", round=1,
            topic="t", topic_synset_id="s", vehicle="v", vehicle_synset_id="s2",
            proposer="p", chain_signature="b" * 64,
            linkage="good", metaphor="live", tier="bogus",
        )

def test_normalise_v1_label_maps_to_axes():
    assert _axes({**_ID, "label": "live"}) == ("good", "live", None)
    assert _axes({**_ID, "label": "bad_path"}) == ("bad", None, None)
    assert _axes({**_ID, "label": "irrelevant"}) == (None, "irrelevant", None)
    assert _axes({**_ID, "label": "dead"}) == ("good", "dead", None)

def test_normalise_v2_record_passes_axes_through():
    raw = {
        "schema_version": "judgement.v2", **{k: v for k, v in _ID.items() if k != "schema_version"},
        "linkage": "good", "metaphor": "dead", "tier": "obvious",
    }
    assert _axes(raw) == ("good", "dead", "obvious")

def test_normalise_v2_record_without_tier_defaults_none():
    raw = {
        "schema_version": "judgement.v2", **{k: v for k, v in _ID.items() if k != "schema_version"},
        "linkage": "bad", "metaphor": "live",
    }
    assert _axes(raw) == ("bad", "live", None)

def test_normalise_is_non_destructive():
    raw = {**_ID, "label": "live", "notes": "keep me"}
    out = normalise_judgement(raw)
    assert out["label"] == "live" and out["notes"] == "keep me"

def test_compute_chain_signature_stable_across_case_and_whitespace():
    s1 = compute_chain_signature("sonnet_v1", ["Anger", " hostility ", "venom"])
    s2 = compute_chain_signature("sonnet_v1", ["anger", "hostility", "venom"])
    assert s1 == s2
    assert len(s1) == 64

def test_compute_chain_signature_changes_on_proposer():
    s1 = compute_chain_signature("sonnet_v1", ["anger", "venom"])
    s2 = compute_chain_signature("cascade_v1", ["anger", "venom"])
    assert s1 != s2

def test_normalise_phrase_strips_and_lowers_and_nfc():
    decomposed = "Café"  # may include combining acute depending on source encoding
    assert normalise_phrase(f"  {decomposed}  ") == "café"

def test_design_note_post_rejects_empty():
    with pytest.raises(ValueError):
        DesignNotePost(content="")

def test_design_note_post_rejects_oversized():
    with pytest.raises(ValueError):
        DesignNotePost(content="x" * 10001)
