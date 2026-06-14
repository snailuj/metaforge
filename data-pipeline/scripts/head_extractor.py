"""Deterministic (no-LLM) syntactic head extractor for chain-step phrases.

A metaphor chain step is ``{"phrase": ..., "head": ..., "synset_id": ...}``. The
``head`` is a DERIVED single-word concept; the ``phrase`` is authoritative. The
generating model (Sonnet) sometimes emits the wrong head — picking a premodifier
("lightning strike" -> "lightning" instead of "strike"). This module re-derives
the head from the phrase alone, so the backfill path can repair existing and
future chain files without any model spend.

Approach (rule + POS, no model):

  1. Single token -> that token, lower-cased.
  2. Multi-word -> nltk POS-tag (packaged averaged-perceptron tagger, no download)
     and locate the head NP's right edge. A preposition / relative pronoun, or a
     participle that GOVERNS further material (a reduced relative like
     "gap admitting light"), starts a postmodifier and closes the head region.
     A TRAILING participle with no object ("organic patterning") is a gerund-
     headed compound — its participle is the nominal head, not a boundary.
  3. Head = rightmost head-eligible token in that region. Head-eligibility =
     a noun POS tag OR WordNet noun membership, but NEVER a closed-class /
     particle / adverb token (so "drawing out" keeps "drawing", not "out").
  4. Leading-participle phrases ("turning toward light", no noun before the PP)
     fall through to the rightmost head-eligible token anywhere.
  5. A phrase with no noun at all (pure verb+particle) keeps its first token.

What this CANNOT fix: a head that is a syntactically-valid noun but the wrong
ONE for the metaphor (semantic, not syntactic, error). Those are irreducible
without a model and are left untouched.

Design ground truth: the operator's bad_head-tagged grading cohort + a
corpus-wide scan of the Sonnet chain files. See test_head_extractor.py.
"""
from __future__ import annotations

from functools import lru_cache

from nltk import pos_tag
from nltk.corpus import wordnet as wn

# Penn Treebank tags that name a noun directly.
_NOUN_TAGS = frozenset({"NN", "NNS", "NNP", "NNPS"})
# Prepositions / infinitival 'to' — start a postmodifier PP after a noun head.
_PREP_TAGS = frozenset({"IN", "TO"})
# Relative pronouns / adverbs — start a relative-clause postmodifier.
_REL_TAGS = frozenset({"WDT", "WP", "WP$", "WRB"})
# Finite/non-finite verb tags — a participle in postmodifier position.
_VERB_TAGS = frozenset({"VBG", "VBN", "VBD", "VBZ", "VBP", "VB"})
# Tags whose tokens can NEVER be a lexical head, even when WordNet happens to
# list the surface form as a noun (e.g. the particle "out"/"back", determiner
# "the", adverb "still"). Keeps verb-particle phrases on their verb.
_NON_HEAD_TAGS = frozenset({
    "RP", "DT", "CC", "IN", "TO", "RB", "RBR", "RBS", "CD",
    "WDT", "WP", "WP$", "WRB", "PRP", "PRP$", "EX", "MD", "POS", "UH",
})


@lru_cache(maxsize=8192)
def _is_wn_noun(word: str) -> bool:
    """True if the surface form has at least one WordNet noun sense."""
    try:
        return bool(wn.synsets(word, pos=wn.NOUN))
    except LookupError:
        # WordNet corpus unavailable — degrade to POS-only judgement.
        return False


def _is_head_candidate(idx: int, low: list[str], tags: list[tuple[str, str]]) -> bool:
    """A token is head-eligible if it reads as a noun and is not closed-class."""
    tag = tags[idx][1]
    if tag in _NON_HEAD_TAGS:
        return False
    return tag in _NOUN_TAGS or _is_wn_noun(low[idx])


def _governs_postmodifier(idx: int, tags: list[tuple[str, str]]) -> bool:
    """True if the verb at idx governs further material (reduced relative clause).

    "gap admitting light" — admitting has an object -> postmodifier verb.
    "organic patterning" — trailing gerund, no object -> nominal head, not a verb.
    """
    rest = tags[idx + 1:]
    return any(t in _NOUN_TAGS or t in _PREP_TAGS or t == "DT" for _, t in rest)


def extract_head(phrase: str) -> str:
    """Re-derive the single-word lexical head of a chain-step phrase.

    Pure and deterministic. Returns lower-cased; "" for an empty/blank phrase.
    """
    stripped = phrase.strip()
    if not stripped:
        return ""
    raw = stripped.split()
    low = [t.lower() for t in raw]
    if len(raw) == 1:
        return low[0]

    tags = pos_tag(raw)
    n = len(raw)

    # 1. Find the right edge of the head NP (exclusive) — the first postmodifier.
    seen_noun = False
    boundary = n
    for i in range(n):
        tag = tags[i][1]
        if seen_noun:
            if tag in _PREP_TAGS or tag in _REL_TAGS:
                boundary = i
                break
            if tag in _VERB_TAGS and _governs_postmodifier(i, tags):
                boundary = i
                break
        if _is_head_candidate(i, low, tags):
            seen_noun = True

    # 2. Rightmost head-eligible token within the head region.
    for i in reversed(range(boundary)):
        if _is_head_candidate(i, low, tags):
            return low[i]

    # 3. Leading-participle phrase (no noun before the PP) — search the whole span.
    for i in reversed(range(n)):
        if _is_head_candidate(i, low, tags):
            return low[i]

    # 4. No noun anywhere (pure verb + particle) — keep the leading verb.
    return low[0]
