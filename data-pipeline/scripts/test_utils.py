"""Tests for shared utility functions."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from utils import normalise


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
