"""Tests for the deterministic (no-LLM) syntactic head extractor.

Ground-truth cases are drawn from the operator's bad_head-tagged grading cohort
and a corpus-wide scan of the Sonnet chain files (see the diagnosis in
docs/inbox / the head-extractor design). The extractor re-derives the lexical
head of a chain-step phrase from the phrase text alone — the backfill path uses
it to repair mis-emitted intermediate heads without any model spend.
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from head_extractor import extract_head


# --- single word: identity (lower-cased) ---------------------------------

def test_single_word_returns_itself_lowercased():
    assert extract_head("Magma") == "magma"
    assert extract_head("pressure") == "pressure"


# --- premodifier + noun: head is the noun (the dominant correct pattern) ---

def test_adjective_premodifier_picks_noun():
    # "decorative layer" -> layer, not the adjective
    assert extract_head("decorative layer") == "layer"
    assert extract_head("hidden accumulation") == "accumulation"
    assert extract_head("buried wound") == "wound"


def test_participle_premodifier_picks_noun():
    # past-participle premodifier ("triggered snap") -> the noun
    assert extract_head("triggered snap") == "snap"
    assert extract_head("compressed energy") == "energy"


# --- the genuine defect class: premodifier wrongly emitted as head --------

def test_corrects_premodifier_over_noun_defect():
    # These are the cases the operator's bad_head tag is really flagging:
    # the generator emitted the modifier; the real head is the trailing noun.
    assert extract_head("lightning strike") == "strike"
    assert extract_head("boundary line") == "line"
    assert extract_head("current flow") == "flow"
    assert extract_head("filigree work") == "work"
    assert extract_head("breaking ranks") == "ranks"
    assert extract_head("holding ground") == "ground"
    assert extract_head("harvesting death") == "death"


# --- head + postmodifier PP: head is the noun BEFORE the preposition -------

def test_postmodifier_pp_keeps_governing_noun():
    # "X of Y" / "X between Y" — head is X, the noun governing the phrase.
    assert extract_head("ritual of engagement") == "ritual"
    assert extract_head("point of return") == "point"
    assert extract_head("beast of burden") == "beast"
    assert extract_head("division of labour") == "division"
    assert extract_head("puppet on strings") == "puppet"


def test_postmodifier_participial_keeps_subject_noun():
    # reduced-relative participle postmodifier — head is the subject noun.
    assert extract_head("gap admitting light") == "gap"
    assert extract_head("message outlasting the sender") == "message"
    assert extract_head("ground giving way") == "ground"


# --- gerund-headed NP: the trailing deverbal noun IS the head -------------

def test_gerund_headed_noun_phrase_keeps_gerund():
    # "organic patterning" centres on the patterning; don't fall back to the adj.
    assert extract_head("organic patterning") == "patterning"
    assert extract_head("light scattering") == "scattering"
    assert extract_head("surface covering") == "covering"


# --- verb-particle / no-noun phrases: keep the verb, never invent a noun ---

def test_verb_particle_phrase_has_no_noun_head():
    # "drawing out", "holding back" — intransitive verb + particle. There is no
    # better noun head; keep the verb/gerund rather than grabbing the particle.
    assert extract_head("drawing out") == "drawing"
    assert extract_head("holding back") == "holding"
    assert extract_head("turning back") == "turning"


# --- robustness ----------------------------------------------------------

def test_empty_and_whitespace():
    assert extract_head("") == ""
    assert extract_head("   ") == ""


def test_strips_and_lowercases():
    assert extract_head("  Grey Palette  ") == "palette"
