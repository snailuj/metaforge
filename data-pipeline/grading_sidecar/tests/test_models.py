from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest
from grading_sidecar.models import (
    ChainRecord, ChainStep, JudgementRecord, DesignNotePost,
    compute_chain_signature, normalise_phrase,
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

def test_judgement_record_rejects_bad_label():
    with pytest.raises(ValueError):
        JudgementRecord(
            schema_version="judgement.v1",
            ts="2026-05-30T07:14:00Z", judged_by="julian", round=1,
            topic="anger", topic_synset_id="12345",
            vehicle="venom", vehicle_synset_id="67890",
            proposer="sonnet_v1", chain_signature="a" * 64,
            label="bogus", confidence="high",
        )

def test_judgement_record_rejects_bad_confidence():
    with pytest.raises(ValueError):
        JudgementRecord(
            schema_version="judgement.v1",
            ts="2026-05-30T07:14:00Z", judged_by="julian", round=1,
            topic="anger", topic_synset_id="12345",
            vehicle="venom", vehicle_synset_id="67890",
            proposer="sonnet_v1", chain_signature="a" * 64,
            label="live", confidence="enthusiastic",
        )

def test_judgement_notes_max_length():
    with pytest.raises(ValueError):
        JudgementRecord(
            schema_version="judgement.v1",
            ts="2026-05-30T07:14:00Z", judged_by="julian", round=1,
            topic="anger", topic_synset_id="12345",
            vehicle="venom", vehicle_synset_id="67890",
            proposer="sonnet_v1", chain_signature="a" * 64,
            label="bad_path", confidence="high",
            notes="x" * 1001,
        )

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
