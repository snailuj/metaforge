"""Tests for gap_fill_physical.py."""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from gap_fill_physical import build_gap_fill_prompt, format_gap_fill_items, merge_gap_fill


def test_format_gap_fill_items_includes_existing_props():
    """Batch item text includes existing properties for dedup."""
    items = [{
        "synset_id": "syn-justice",
        "lemma": "justice",
        "definition": "the quality of being just or fair",
        "pos": "n",
        "existing_properties": ["fair", "balanced", "impartial"],
    }]
    text = format_gap_fill_items(items)
    assert "justice" in text
    assert "fair, balanced, impartial" in text


def test_format_gap_fill_items_multiple():
    """Multiple items are separated."""
    items = [
        {"synset_id": "s1", "lemma": "a", "definition": "d1", "pos": "n",
         "existing_properties": ["x"]},
        {"synset_id": "s2", "lemma": "b", "definition": "d2", "pos": "n",
         "existing_properties": ["y"]},
    ]
    text = format_gap_fill_items(items)
    assert "s1" in text
    assert "s2" in text


def test_merge_gap_fill_appends_properties():
    """Gap-fill properties are appended to existing enrichment data."""
    existing = {
        "synsets": [
            {"id": "syn-justice", "properties": [
                {"text": "fair", "salience": 0.8, "type": "social", "relation": "justice is fair"},
            ]},
        ],
    }
    gap_fill = [
        {"id": "syn-justice", "properties": [
            {"text": "cold", "salience": 0.6, "type": "physical", "relation": "justice feels cold"},
        ]},
    ]
    merged = merge_gap_fill(existing, gap_fill)
    props = merged["synsets"][0]["properties"]
    assert len(props) == 2
    assert props[1]["text"] == "cold"


def test_merge_gap_fill_skips_duplicates():
    """Gap-fill properties that duplicate existing text are skipped."""
    existing = {
        "synsets": [
            {"id": "syn-rock", "properties": [
                {"text": "hard", "salience": 0.9, "type": "physical", "relation": "rock is hard"},
            ]},
        ],
    }
    gap_fill = [
        {"id": "syn-rock", "properties": [
            {"text": "hard", "salience": 0.8, "type": "physical", "relation": "dup"},
            {"text": "heavy", "salience": 0.7, "type": "physical", "relation": "rock is heavy"},
        ]},
    ]
    merged = merge_gap_fill(existing, gap_fill)
    props = merged["synsets"][0]["properties"]
    texts = [p["text"] for p in props]
    assert texts.count("hard") == 1
    assert "heavy" in texts


def test_merge_gap_fill_ignores_unknown_synset():
    """Gap-fill for synsets not in existing data is ignored."""
    existing = {"synsets": [{"id": "syn-rock", "properties": []}]}
    gap_fill = [{"id": "syn-unknown", "properties": [{"text": "x", "salience": 0.5, "type": "physical", "relation": ""}]}]
    merged = merge_gap_fill(existing, gap_fill)
    assert len(merged["synsets"]) == 1


def test_merge_gap_fill_does_not_mutate_input():
    """merge_gap_fill must not modify the existing_data argument."""
    existing = {
        "synsets": [{"id": "s1", "properties": [
            {"text": "hard", "salience": 0.9, "type": "physical", "relation": "x"},
        ]}],
    }
    gap_fill = [{"id": "s1", "properties": [
        {"text": "heavy", "salience": 0.7, "type": "physical", "relation": "y"},
    ]}]
    original_len = len(existing["synsets"][0]["properties"])
    merge_gap_fill(existing, gap_fill)
    assert len(existing["synsets"][0]["properties"]) == original_len


def test_build_gap_fill_prompt_inserts_items():
    """build_gap_fill_prompt inserts batch items text into the template."""
    text = build_gap_fill_prompt("ITEMS_HERE")
    assert "ITEMS_HERE" in text
    assert "physical" in text.lower()
