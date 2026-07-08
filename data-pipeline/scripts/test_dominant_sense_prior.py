"""Tests for dominant_sense_prior — the SemCor-tagcount correction for the
snapper's 'too specific' bias (gloss-match picks a narrow/rare synset when a
general dominant sense was intended). Pure functions, no DB."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import dominant_sense_prior as dsp


def _s(sid, sensenum, tagcount):
    return {"synset_id": sid, "sensenum": sensenum, "tagcount": tagcount}


# deficit: snapped to the rare accounting sense (tc0); the dominant "general lack"
# (tc1) is what the operator intended. A frequency signal exists -> correct.
def test_corrects_rare_snap_toward_clear_dominant():
    senses = [_s("60588", 1, 1), _s("99911", 2, 0), _s("95108", 3, 0), _s("94100", 4, 0)]
    out = dsp.choose_sense(senses, "94100")
    assert out["synset_id"] == "60588"
    assert out["changed"] is True
    assert out["from"] == "94100"


# arabesque: dance vs ornament, BOTH tagcount 0 — no frequency signal. The prior
# must ABSTAIN (keep the snap) and leave it to the sense-set layer, never guess.
def test_abstains_on_all_zero_tagcount_tie():
    senses = [_s("60419", 1, 0), _s("43921", 2, 0)]
    out = dsp.choose_sense(senses, "43921")
    assert out["synset_id"] == "43921"
    assert out["changed"] is False


# snap already on the dominant sense -> unchanged.
def test_keeps_snap_already_dominant():
    senses = [_s("99518", 1, 9), _s("100403", 2, 4), _s("87541", 4, 3)]
    out = dsp.choose_sense(senses, "99518")
    assert out["synset_id"] == "99518"
    assert out["changed"] is False


# a genuine tie at the max tagcount (snapped IS one of the joint-max) -> keep it,
# never flip between equally-frequent senses.
def test_keeps_snap_when_tied_for_max():
    senses = [_s("a", 1, 3), _s("b", 2, 3), _s("c", 3, 0)]
    out = dsp.choose_sense(senses, "b")
    assert out["synset_id"] == "b"
    assert out["changed"] is False


# an unknown snapped synset (not among the lemma's senses) -> keep it untouched
# (defensive: never fabricate a correction for a synset we can't reason about).
def test_keeps_unknown_snapped_synset():
    senses = [_s("x", 1, 5)]
    out = dsp.choose_sense(senses, "not-in-list")
    assert out["synset_id"] == "not-in-list"
    assert out["changed"] is False
