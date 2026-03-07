"""Tests for shared utility functions."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from utils import normalise, load_checkpoint, save_checkpoint, get_git_commit


def test_normalise_strips_and_lowercases():
    """Verify normalise() strips whitespace and lowercases."""
    assert normalise(" Hello World ") == "hello world"


def test_normalise_edge_cases():
    """Verify normalise() handles edge cases correctly."""
    # Empty string
    assert normalise("") == ""

    # Already normalised
    assert normalise("hello world") == "hello world"

    # Tabs and newlines
    assert normalise("\tHello\nWorld\t") == "hello\nworld"


# --- Checkpoint I/O tests ---


def test_save_checkpoint_is_atomic(tmp_path):
    """save_checkpoint writes atomically — no .tmp file left behind."""
    cp = tmp_path / "checkpoint.json"
    state = {"completed_ids": ["s1"], "synsets": [{"id": "s1"}]}
    save_checkpoint(cp, state)

    assert cp.exists()
    assert not list(tmp_path.glob("*.tmp"))
    loaded = json.loads(cp.read_text())
    assert loaded["completed_ids"] == ["s1"]


def test_save_checkpoint_overwrites_existing(tmp_path):
    """save_checkpoint replaces existing checkpoint atomically."""
    cp = tmp_path / "checkpoint.json"
    save_checkpoint(cp, {"completed_ids": [], "synsets": []})
    save_checkpoint(cp, {"completed_ids": ["s1"], "synsets": [{"id": "s1"}]})

    loaded = json.loads(cp.read_text())
    assert loaded["completed_ids"] == ["s1"]


def test_load_checkpoint_handles_corrupt_json(tmp_path):
    """load_checkpoint recovers from corrupt JSON by returning empty state."""
    cp = tmp_path / "checkpoint.json"
    cp.write_text("{truncated")

    state = load_checkpoint(cp)

    assert state == {"completed_ids": [], "synsets": []}
    assert (tmp_path / "checkpoint.json.corrupt").exists()
    assert not cp.exists()


def test_load_checkpoint_reads_unified_format(tmp_path):
    """load_checkpoint reads the unified checkpoint format."""
    cp = tmp_path / "checkpoint.json"
    cp.write_text(json.dumps({
        "completed_ids": ["s1", "s2"],
        "synsets": [{"id": "s1"}, {"id": "s2"}],
    }))
    state = load_checkpoint(cp)
    assert len(state["completed_ids"]) == 2
    assert len(state["synsets"]) == 2


def test_load_checkpoint_backward_compat_results_key(tmp_path):
    """load_checkpoint remaps legacy 'results' key to 'synsets'."""
    cp = tmp_path / "checkpoint.json"
    cp.write_text(json.dumps({
        "completed_ids": ["s1"],
        "results": [{"id": "s1"}],
    }))
    state = load_checkpoint(cp)
    assert "synsets" in state
    assert "results" not in state
    assert state["synsets"] == [{"id": "s1"}]


def test_load_checkpoint_empty_when_missing(tmp_path):
    """load_checkpoint returns empty state when file doesn't exist."""
    state = load_checkpoint(tmp_path / "nonexistent.json")
    assert state == {"completed_ids": [], "synsets": []}


# --- get_git_commit tests ---


def test_get_git_commit_returns_string():
    """get_git_commit returns a string (hash or 'unknown')."""
    result = get_git_commit()
    assert isinstance(result, str)
    assert len(result) > 0
