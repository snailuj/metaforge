"""Tests for lib/claude_client."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def test_import():
    from claude_client import ClaudeError
    assert issubclass(ClaudeError, Exception)


def test_error_hierarchy():
    from claude_client import ClaudeError, RateLimitError, EmptyResponseError, ParseError
    assert issubclass(RateLimitError, ClaudeError)
    assert issubclass(EmptyResponseError, ClaudeError)
    assert issubclass(ParseError, ClaudeError)
    assert not issubclass(RateLimitError, EmptyResponseError)


# --- _strip_fences -----------------------------------------------------------

from claude_client import _strip_fences


def test_strip_fences_json():
    assert _strip_fences("```json\n[1,2]\n```") == "[1,2]"


def test_strip_fences_markdown():
    assert _strip_fences("```markdown\nsome text\n```") == "some text"


def test_strip_fences_noop():
    assert _strip_fences("[1,2,3]") == "[1,2,3]"


def test_strip_fences_whitespace():
    assert _strip_fences("```json\n  data  \n```") == "  data  "
