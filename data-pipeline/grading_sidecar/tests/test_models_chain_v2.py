"""chain.v2 — additive over chain.v1; every v1 record must still validate."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pytest
from models import (AptSense, ChainRecord, ChainStep, ChainSchemaVersion,
                    compute_chain_signature, vec_ref)


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


def test_v1_record_still_validates():
    rec = ChainRecord(**_v1_record())
    assert rec.schema_version == "chain.v1"
    assert rec.chain[0].node_ref is None
    assert rec.chain[0].apt_senses == []


def test_vec_ref_canonicalises_via_normalise_phrase():
    assert vec_ref("Pressed  Flower ") == "pressed__flower"  # NFC+strip+lower; spaces->underscores
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
