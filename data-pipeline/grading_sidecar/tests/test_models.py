from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest
from grading_sidecar.models import (
    ChainRecord, ChainStep, JudgementRecord, DesignNotePost,
    compute_chain_signature, normalise_phrase, normalise_judgement,
    effective_linkage, has_bad_head,
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

def test_chain_step_retains_emitted_gloss():
    # emit-the-sense: the model's intended one-line sense per node, recorded at
    # generation time (a lemma can be re-snapped later; an intended sense cannot).
    s = ChainStep(phrase="ferment", head="ferment", synset_id="42",
                  gloss="the slow chemical breakdown of a substance by microbes")
    assert s.gloss == "the slow chemical breakdown of a substance by microbes"

def test_chain_step_gloss_defaults_none_for_backward_compat():
    s = ChainStep(phrase="anger", head="anger", synset_id="12345")
    assert s.gloss is None

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
    return (d["linkage"], d["metaphor"], d["tiers"])

# --- W2.1: tiers list (strong/ironic/surprising), multi-select ---

def test_judgement_accepts_multiple_tiers():
    r = JudgementRecord(schema_version="judgement.v2", judged_by="op", round=1,
        topic="anger", topic_synset_id="1", vehicle="volcano", vehicle_synset_id="2",
        proposer="sonnet_v1", chain_signature="a"*64, linkage="good", metaphor="live",
        tiers=["strong", "surprising"])
    assert r.tiers == ["strong", "surprising"]

def test_judgement_tiers_default_empty():
    r = JudgementRecord(schema_version="judgement.v2", judged_by="op", round=1,
        topic="t", topic_synset_id="1", vehicle="v", vehicle_synset_id="2",
        proposer="p", chain_signature="a"*64, linkage="good", metaphor="dead")
    assert r.tiers == []

def test_judgement_rejects_unknown_tier():
    with pytest.raises(Exception):
        JudgementRecord(schema_version="judgement.v2", judged_by="op", round=1,
            topic="t", topic_synset_id="1", vehicle="v", vehicle_synset_id="2",
            proposer="p", chain_signature="a"*64, linkage="good", metaphor="live",
            tiers=["legendary"])

def test_normalise_judgement_v2_returns_tiers_list():
    assert normalise_judgement({"linkage": "good", "metaphor": "live", "tiers": ["ironic"]})["tiers"] == ["ironic"]
    assert normalise_judgement({"linkage": "good", "metaphor": "dead"})["tiers"] == []

def test_normalise_judgement_v1_returns_empty_tiers():
    assert normalise_judgement({"label": "live"})["tiers"] == []

def test_v2_record_roundtrips_two_axes_and_tiers():
    rec = JudgementRecord(
        schema_version="judgement.v2", judged_by="julian", round=1,
        topic="anchor", topic_synset_id="syn-anchor", vehicle="stone",
        vehicle_synset_id="syn-stone", proposer="sonnet_v1",
        chain_signature="a" * 64, linkage="good", metaphor="live", tiers=["strong"],
    )
    assert rec.linkage == "good" and rec.metaphor == "live" and rec.tiers == ["strong"]

def test_v2_tiers_default_empty():
    rec = JudgementRecord(
        schema_version="judgement.v2", judged_by="j", round=1,
        topic="t", topic_synset_id="s", vehicle="v", vehicle_synset_id="s2",
        proposer="p", chain_signature="b" * 64, linkage="good", metaphor="live",
    )
    assert rec.tiers == []

def test_v2_record_rejects_bad_tier():
    with pytest.raises(ValueError):
        JudgementRecord(
            schema_version="judgement.v2", judged_by="j", round=1,
            topic="t", topic_synset_id="s", vehicle="v", vehicle_synset_id="s2",
            proposer="p", chain_signature="b" * 64,
            linkage="good", metaphor="live", tiers=["bogus"],
        )

def test_normalise_v1_label_maps_to_axes():
    assert _axes({**_ID, "label": "live"}) == ("good", "live", [])
    assert _axes({**_ID, "label": "bad_path"}) == ("bad", None, [])
    assert _axes({**_ID, "label": "irrelevant"}) == (None, "irrelevant", [])
    assert _axes({**_ID, "label": "dead"}) == ("good", "dead", [])

def test_normalise_v2_record_passes_axes_through():
    raw = {
        "schema_version": "judgement.v2", **{k: v for k, v in _ID.items() if k != "schema_version"},
        "linkage": "good", "metaphor": "live", "tiers": ["strong", "ironic"],
    }
    assert _axes(raw) == ("good", "live", ["strong", "ironic"])

def test_normalise_v2_record_without_tiers_defaults_empty():
    raw = {
        "schema_version": "judgement.v2", **{k: v for k, v in _ID.items() if k != "schema_version"},
        "linkage": "bad", "metaphor": "live",
    }
    assert _axes(raw) == ("bad", "live", [])

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


def test_sense_label_requires_intended_for_wrong_and_rare():
    import pytest
    from pydantic import ValidationError
    from grading_sidecar.models import SenseLabel
    for v in ("wrong", "rare_ok"):
        with pytest.raises(ValidationError):
            SenseLabel(role="topic", word="x", snapped_synset_id="1", verdict=v)
    # right / unsure with no intended is fine.
    for v in ("right", "unsure"):
        SenseLabel(role="topic", word="x", snapped_synset_id="1", verdict=v)


def test_sense_label_defaults_and_optional_intended():
    from grading_sidecar.models import SenseLabel
    # Minimal valid label: schema_version + ts default; intended/chain_signature optional.
    lbl = SenseLabel(role="topic", word="apprehension",
                     snapped_synset_id="1760", verdict="wrong",
                     intended_synset_id="72797")
    assert lbl.schema_version == "sense_label.v1"
    assert lbl.ts  # server-injected default
    assert lbl.intended_synset_id == "72797"

    ok = SenseLabel(role="vehicle", word="river",
                    snapped_synset_id="9", verdict="right")
    assert ok.intended_synset_id is None
    assert ok.chain_signature is None

def test_design_note_post_rejects_empty():
    with pytest.raises(ValueError):
        DesignNotePost(content="")

def test_design_note_post_rejects_oversized():
    with pytest.raises(ValueError):
        DesignNotePost(content="x" * 10001)

# --- W3: structured tags[] (merge/padding/leap/bad_head/other), multi-select ---

def test_judgement_accepts_multiple_tags():
    r = JudgementRecord(schema_version="judgement.v2", judged_by="op", round=1,
        topic="anger", topic_synset_id="1", vehicle="volcano", vehicle_synset_id="2",
        proposer="sonnet_v1", chain_signature="a"*64, linkage="good", metaphor="live",
        tags=["padding", "bad_head"])
    assert r.tags == ["padding", "bad_head"]

def test_judgement_tags_default_empty():
    r = JudgementRecord(schema_version="judgement.v2", judged_by="op", round=1,
        topic="t", topic_synset_id="1", vehicle="v", vehicle_synset_id="2",
        proposer="p", chain_signature="a"*64, linkage="good", metaphor="dead")
    assert r.tags == []

def test_judgement_rejects_unknown_tag():
    with pytest.raises(Exception):
        JudgementRecord(schema_version="judgement.v2", judged_by="op", round=1,
            topic="t", topic_synset_id="1", vehicle="v", vehicle_synset_id="2",
            proposer="p", chain_signature="a"*64, linkage="good", metaphor="live",
            tags=["bogus"])

def test_normalise_judgement_v2_returns_tags_list():
    assert normalise_judgement({"linkage": "good", "metaphor": "live", "tags": ["bad_head"]})["tags"] == ["bad_head"]
    assert normalise_judgement({"linkage": "good", "metaphor": "dead"})["tags"] == []

def test_normalise_judgement_v1_returns_empty_tags():
    assert normalise_judgement({"label": "live"})["tags"] == []

# --- linkage re-derivation: structural tags imply bad linkage (Julian skips the
# redundant linkage tap; padding alone is NOT bad — a padded path can still bridge
# a good pairing). bad_head additionally poisons the LIVENESS label (wrong vehicle). ---

def test_effective_linkage_explicit_bad_stays_bad():
    assert effective_linkage({"linkage": "bad", "tags": []}) == "bad"

def test_effective_linkage_forcing_tag_overrides_good():
    for tag in ("bad_head", "leap", "merge"):
        assert effective_linkage({"linkage": "good", "tags": [tag]}) == "bad", tag

def test_effective_linkage_padding_alone_stays_good():
    assert effective_linkage({"linkage": "good", "tags": ["padding"]}) == "good"

def test_effective_linkage_other_alone_stays_good():
    assert effective_linkage({"linkage": "good", "tags": ["other"]}) == "good"

def test_effective_linkage_padding_with_forcing_tag_is_bad():
    assert effective_linkage({"linkage": "good", "tags": ["padding", "leap"]}) == "bad"

def test_effective_linkage_preserves_none_for_v1_irrelevant():
    # v1 'irrelevant' normalises to linkage None; with no forcing tag it stays None.
    assert effective_linkage({"linkage": None, "tags": []}) is None

def test_effective_linkage_missing_tags_key_is_safe():
    assert effective_linkage({"linkage": "good"}) == "good"

def test_has_bad_head():
    assert has_bad_head({"tags": ["bad_head"]}) is True
    assert has_bad_head({"tags": ["leap", "padding"]}) is False
    assert has_bad_head({"tags": []}) is False
    assert has_bad_head({}) is False


# --- Task 1: 'split' sense verdict ---

def test_sense_label_split_is_valid_with_no_intended():
    """split carries no intended sense — should be accepted with intended_synset_id=None."""
    from pydantic import ValidationError
    from grading_sidecar.models import SenseLabel
    # Must not raise — split is not in the corrective set (wrong/rare_ok).
    lbl = SenseLabel(role="topic", word="bank", snapped_synset_id="999", verdict="split")
    assert lbl.verdict == "split"
    assert lbl.intended_synset_id is None

def test_sense_label_split_with_intended_is_also_valid():
    """split MAY carry an intended_synset_id even though it is not required."""
    from grading_sidecar.models import SenseLabel
    lbl = SenseLabel(role="vehicle", word="bank", snapped_synset_id="999",
                     verdict="split", intended_synset_id="123")
    assert lbl.verdict == "split"
    assert lbl.intended_synset_id == "123"


# --- Task 1 (ux4): apt_synset_ids field for 'split' multi-select ---

def test_sense_label_split_with_apt_synset_ids():
    """split can record multiple apt senses in apt_synset_ids."""
    from grading_sidecar.models import SenseLabel
    lbl = SenseLabel(role="topic", word="glance", snapped_synset_id="100",
                     verdict="split", apt_synset_ids=["1", "2"])
    assert lbl.apt_synset_ids == ["1", "2"]
    assert lbl.intended_synset_id is None

def test_sense_label_split_apt_synset_ids_defaults_to_empty():
    """Omitting apt_synset_ids defaults to [] — backward-compatible."""
    from grading_sidecar.models import SenseLabel
    lbl = SenseLabel(role="topic", word="glance", snapped_synset_id="100",
                     verdict="split")
    assert lbl.apt_synset_ids == []

def test_sense_label_split_empty_apt_synset_ids_is_valid():
    """split with apt_synset_ids=[] is valid (flag-only, enumerate later)."""
    from grading_sidecar.models import SenseLabel
    lbl = SenseLabel(role="vehicle", word="whisper", snapped_synset_id="200",
                     verdict="split", apt_synset_ids=[])
    assert lbl.verdict == "split"
    assert lbl.apt_synset_ids == []

def test_sense_label_non_split_verdicts_have_empty_apt_synset_ids_default():
    """Non-split verdicts are unaffected — apt_synset_ids defaults to []."""
    from grading_sidecar.models import SenseLabel
    for v in ("right", "unsure"):
        lbl = SenseLabel(role="topic", word="river", snapped_synset_id="1", verdict=v)
        assert lbl.apt_synset_ids == [], f"expected [] for verdict={v}"
