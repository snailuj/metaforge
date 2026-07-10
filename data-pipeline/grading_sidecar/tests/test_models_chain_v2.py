"""chain.v2 additive schema tests (Task 6 / W2).

Reuses Task 1's chain contract tests verbatim (adapted to the grading_sidecar
import path) PLUS W2-specific verdict extensions: StepAptSense field on
JudgementRecord and vec: vehicle endpoints.
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest
from grading_sidecar.models import (
    AptSense, ChainRecord, ChainStep, ChainSchemaVersion,
    JudgementRecord, StepAptSense,
    compute_chain_signature, vec_ref,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _sig(proposer, phrases):
    return compute_chain_signature(proposer, phrases)


def _v1_record():
    phrases = ["grief", "pain", "scar"]
    return {
        "schema_version": "chain.v1", "topic": "grief", "topic_synset_id": "1",
        "vehicle": "scar", "vehicle_synset_id": "3", "proposer": "sonnet_v1",
        "round": 1, "generated_at": "2026-07-10T00:00:00+00:00",
        "chain_signature": _sig("sonnet_v1", phrases),
        "chain": [
            {"phrase": "grief", "head": "grief", "synset_id": "1"},
            {"phrase": "pain", "head": "pain", "synset_id": "2"},
            {"phrase": "scar", "head": "scar", "synset_id": "3"},
        ],
    }


# ---------------------------------------------------------------------------
# Task 1 chain.v2 tests (ported verbatim to grading_sidecar import path)
# ---------------------------------------------------------------------------

def test_v1_record_still_validates():
    rec = ChainRecord(**_v1_record())
    assert rec.schema_version == "chain.v1"
    assert rec.chain[0].node_ref is None
    assert rec.chain[0].apt_senses == []


def test_vec_ref_canonicalises_via_normalise_phrase():
    # NFC+strip+lower; spaces->underscores (double space preserved as double underscore)
    assert vec_ref("Pressed  Flower ") == "pressed__flower"
    assert vec_ref("glance") == "glance"


def test_resolved_node_ref_derivation():
    syn = ChainStep(phrase="wound", head="wound", synset_id="82241")
    assert syn.resolved_node_ref() == "syn:82241"
    explicit = ChainStep(phrase="wound", head="wound", synset_id="82241",
                         node_ref="syn:82241")
    assert explicit.resolved_node_ref() == "syn:82241"
    vec = ChainStep(phrase="pressed flower", head="flower", synset_id=None)
    assert vec.resolved_node_ref() == "vec:pressed_flower"


def test_v2_vec_vehicle_endpoint_validates():
    phrases = ["nostalgia", "keepsake", "pressed flower"]
    rec = ChainRecord(
        schema_version="chain.v2", topic="nostalgia", topic_synset_id="10",
        vehicle="pressed flower", vehicle_synset_id=None,
        vehicle_node_ref="vec:pressed_flower", proposer="sonnet_v1", round=1,
        generated_at="2026-07-10T00:00:00+00:00",
        chain_signature=_sig("sonnet_v1", phrases),
        chain=[
            {"phrase": "nostalgia", "head": "nostalgia", "synset_id": "10"},
            {"phrase": "keepsake", "head": "keepsake", "synset_id": "11"},
            {"phrase": "pressed flower", "head": "flower", "synset_id": None,
             "node_ref": "vec:pressed_flower"},
        ],
    )
    assert rec.chain[-1].resolved_node_ref() == "vec:pressed_flower"


def test_v2_vec_vehicle_requires_matching_node_ref():
    bad = _v1_record()
    bad["schema_version"] = "chain.v2"
    bad["vehicle_synset_id"] = None
    bad["chain"][-1]["synset_id"] = None
    # no vehicle_node_ref supplied -> must fail
    with pytest.raises(ValueError):
        ChainRecord(**bad)


def test_apt_senses_roundtrip():
    step = ChainStep(phrase="glance", head="glance", synset_id="70001",
                     apt_senses=[{"synset_id": "70001", "source": "intended"},
                                 {"synset_id": "70002", "source": "operator"}])
    assert [a.synset_id for a in step.apt_senses] == ["70001", "70002"]
    with pytest.raises(ValueError):
        AptSense(synset_id="x", source="snapper")  # not a valid source


# ---------------------------------------------------------------------------
# Task 6: verdict extensions — StepAptSense + vec: vehicle fields
# ---------------------------------------------------------------------------

def _v2_judgement_base():
    """A well-formed v2 judgement record with topic/vehicle synset IDs present."""
    return {
        "schema_version": "judgement.v2",
        "ts": "2026-07-10T00:00:00+00:00",
        "judged_by": "julian",
        "round": 1,
        "topic": "nostalgia",
        "topic_synset_id": "10",
        "vehicle": "pressed flower",
        "vehicle_synset_id": "99",
        "proposer": "sonnet_v1",
        "chain_signature": "a" * 64,
        "linkage": "good",
        "metaphor": "live",
        "confidence": "high",
    }


def test_judgement_v2_without_step_apt_senses_still_validates():
    """Stored v2 judgement lines without step_apt_senses must still validate (read-compat)."""
    rec = JudgementRecord(**_v2_judgement_base())
    assert rec.step_apt_senses == []


def test_judgement_v2_with_step_apt_senses_roundtrips():
    """A verdict carrying step_apt_senses round-trips with the correct types."""
    data = {**_v2_judgement_base(),
            "step_apt_senses": [{"step_idx": 2, "synset_id": "70002"}]}
    rec = JudgementRecord(**data)
    assert len(rec.step_apt_senses) == 1
    assert rec.step_apt_senses[0].step_idx == 2
    assert rec.step_apt_senses[0].synset_id == "70002"


def test_judgement_v2_vec_vehicle_validates():
    """Verdict for a vec: vehicle (vehicle_synset_id=None, vehicle_node_ref set) validates."""
    data = {
        **_v2_judgement_base(),
        "vehicle_synset_id": None,
        "vehicle_node_ref": "vec:pressed_flower",
    }
    rec = JudgementRecord(**data)
    assert rec.vehicle_synset_id is None
    assert rec.vehicle_node_ref == "vec:pressed_flower"


def test_judgement_v2_topic_node_ref_optional():
    """topic_node_ref is optional; existing records without it validate."""
    rec = JudgementRecord(**_v2_judgement_base())
    assert rec.topic_node_ref is None


def test_step_apt_sense_rejects_negative_step_idx():
    """step_idx must be >= 0."""
    with pytest.raises(ValueError):
        StepAptSense(step_idx=-1, synset_id="70001")


def test_step_apt_sense_rejects_empty_synset_id():
    with pytest.raises(ValueError):
        StepAptSense(step_idx=0, synset_id="")
