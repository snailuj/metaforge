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


# --- _parse_events -----------------------------------------------------------

import json
import pytest
from claude_client import (
    _parse_events, ClaudeError, RateLimitError, EmptyResponseError,
)


def _make_stdout(result_text, is_error=False):
    return json.dumps([
        {"type": "system", "subtype": "init"},
        {"type": "result", "is_error": is_error, "result": result_text},
    ])


def test_parse_events_success():
    assert _parse_events(_make_stdout("hello"), 0, "") == "hello"


def test_parse_events_empty_stdout():
    with pytest.raises(EmptyResponseError):
        _parse_events("", 0, "")


def test_parse_events_nonzero_exit():
    with pytest.raises(ClaudeError, match="exit 1"):
        _parse_events("", 1, "some error")


def test_parse_events_no_result_event():
    stdout = json.dumps([{"type": "system"}])
    with pytest.raises(EmptyResponseError):
        _parse_events(stdout, 0, "")


def test_parse_events_missing_result_field():
    stdout = json.dumps([{"type": "result", "is_error": False}])
    with pytest.raises(EmptyResponseError):
        _parse_events(stdout, 0, "")


def test_parse_events_rate_limit():
    with pytest.raises(RateLimitError):
        _parse_events(_make_stdout("rate limit exceeded", is_error=True), 0, "")


def test_parse_events_quota():
    with pytest.raises(RateLimitError):
        _parse_events(_make_stdout("quota exceeded", is_error=True), 0, "")


def test_parse_events_non_rate_limit_error():
    with pytest.raises(ClaudeError, match="some other error"):
        _parse_events(_make_stdout("some other error", is_error=True), 0, "")


def test_parse_events_strips_fences():
    stdout = _make_stdout("```json\n[1,2]\n```")
    assert _parse_events(stdout, 0, "") == "[1,2]"


# --- _invoke -----------------------------------------------------------------

from unittest.mock import patch, MagicMock
from claude_client import _invoke


def _make_proc(result_text="ok", returncode=0, stderr=""):
    proc = MagicMock()
    proc.stdout = json.dumps([
        {"type": "result", "is_error": False, "result": result_text},
    ])
    proc.returncode = returncode
    proc.stderr = stderr
    return proc


@patch("claude_client.subprocess.run")
def test_invoke_command_shape(mock_run):
    mock_run.return_value = _make_proc()
    _invoke("test prompt", model="haiku")
    cmd = mock_run.call_args[0][0]
    assert cmd == [
        "claude", "-p", "--output-format", "json",
        "--model", "haiku", "--max-turns", "1",
        "--no-session-persistence",
    ]
    assert mock_run.call_args[1]["input"] == "test prompt"
    assert mock_run.call_args[1]["capture_output"] is True
    assert mock_run.call_args[1]["text"] is True
    assert mock_run.call_args[1]["timeout"] == 120


@patch("claude_client.subprocess.run")
def test_invoke_returns_parsed_text(mock_run):
    mock_run.return_value = _make_proc(result_text="the answer")
    assert _invoke("prompt", model="sonnet") == "the answer"


@patch("claude_client.subprocess.run")
def test_invoke_verbose_logging(mock_run, caplog):
    mock_run.return_value = _make_proc(result_text="ok")
    import logging
    with caplog.at_level(logging.DEBUG, logger="claude_client"):
        _invoke("test prompt", model="haiku", verbose=True)
    assert any("test prompt" in r.message for r in caplog.records)
