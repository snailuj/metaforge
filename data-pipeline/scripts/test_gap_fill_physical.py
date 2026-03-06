"""Tests for gap_fill_physical.py."""

import json
import sqlite3
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from gap_fill_physical import (
    format_gap_fill_batch,
    load_synsets_from_db,
    build_output,
    GAP_FILL_PROMPT,
)


# --- Prompt tests ---

class TestGapFillPrompt:
    def test_prompt_mentions_physical(self):
        assert "physical" in GAP_FILL_PROMPT.lower()

    def test_prompt_requires_single_word(self):
        assert "single" in GAP_FILL_PROMPT.lower() or "one word" in GAP_FILL_PROMPT.lower()

    def test_prompt_has_batch_items_placeholder(self):
        assert "{batch_items}" in GAP_FILL_PROMPT


class TestFormatGapFillBatch:
    def test_includes_id_and_definition(self):
        synsets = [{"id": "s1", "lemma": "rock", "definition": "a hard mineral", "pos": "n"}]
        result = format_gap_fill_batch(synsets)
        assert "s1" in result
        assert "rock" in result
        assert "a hard mineral" in result


# --- DB lookup tests ---

class TestLoadSynsetsFromDb:
    def test_loads_synset_by_id(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, definition TEXT, pos TEXT);
            CREATE TABLE lemmas (lemma TEXT, synset_id TEXT);
            CREATE TABLE frequencies (lemma TEXT, familiarity REAL);
            INSERT INTO synsets VALUES ('s1', 'a large rock', 'n');
            INSERT INTO lemmas VALUES ('boulder', 's1');
            INSERT INTO frequencies VALUES ('boulder', 5.5);
        """)
        conn.close()

        result = load_synsets_from_db(str(db_path), ["s1"])
        assert len(result) == 1
        assert result[0]["id"] == "s1"
        assert result[0]["lemma"] == "boulder"
        assert result[0]["definition"] == "a large rock"

    def test_missing_synset_skipped(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, definition TEXT, pos TEXT);
            CREATE TABLE lemmas (lemma TEXT, synset_id TEXT);
            CREATE TABLE frequencies (lemma TEXT, familiarity REAL);
        """)
        conn.close()

        result = load_synsets_from_db(str(db_path), ["nonexistent"])
        assert len(result) == 0


# --- Output format tests ---

class TestBuildOutput:
    def test_output_has_synsets_key(self):
        results = [{"id": "s1", "properties": [{"text": "hard", "type": "physical"}]}]
        output = build_output(results, model="sonnet", batch_size=20)
        assert "synsets" in output

    def test_output_has_stats(self):
        results = [{"id": "s1", "properties": [{"text": "hard", "type": "physical"}]}]
        output = build_output(results, model="sonnet", batch_size=20)
        assert output["stats"]["total_synsets"] == 1

    def test_output_has_config(self):
        output = build_output([], model="sonnet", batch_size=20)
        assert output["config"]["model"] == "sonnet"
