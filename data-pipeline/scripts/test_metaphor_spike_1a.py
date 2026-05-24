"""Tests for metaphor_spike_1a.py — Phase 1a runner.

Uses no DB and no LLM calls. Every test is pure-function.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from metaphor_spike_1a import (
    TOPICS,
    build_apt_prompt,
    build_inapt_prompt,
)


def test_topics_count():
    assert len(TOPICS) == 5


def test_topics_have_word_and_gloss():
    for t in TOPICS:
        assert "word" in t, f"missing 'word' key: {t}"
        assert "gloss" in t, f"missing 'gloss' key: {t}"
        assert t["word"].strip(), "word must be non-empty"
        assert t["gloss"].strip(), "gloss must be non-empty"


def test_topic_words_are_single_tokens():
    """Topic words must not contain spaces — they are lemma keys."""
    for t in TOPICS:
        assert " " not in t["word"], f"topic word must be single token: {t['word']!r}"


def test_apt_prompt_contains_topic_and_gloss():
    prompt = build_apt_prompt("fire", "rapid oxidation producing heat and light")
    assert "fire" in prompt
    assert "rapid oxidation producing heat and light" in prompt
    # Must not echo the gloss placeholder literally
    assert "<TOPIC>" not in prompt
    assert "<GLOSS>" not in prompt


def test_inapt_prompt_contains_topic_and_gloss():
    prompt = build_inapt_prompt("fire", "rapid oxidation producing heat and light")
    assert "fire" in prompt
    assert "rapid oxidation producing heat and light" in prompt
    assert "<TOPIC>" not in prompt
    assert "<GLOSS>" not in prompt


def test_apt_and_inapt_prompts_are_different():
    apt = build_apt_prompt("grief", "deep sorrow")
    inapt = build_inapt_prompt("grief", "deep sorrow")
    assert apt != inapt
