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


# --- _invoke_with_retries ----------------------------------------------------

from claude_client import _invoke_with_retries, ParseError


@patch("claude_client.time.sleep")
@patch("claude_client._invoke")
def test_retries_on_transient_failure(mock_invoke, mock_sleep):
    mock_invoke.side_effect = [EmptyResponseError("empty"), "success"]
    result = _invoke_with_retries("prompt", model="haiku", max_retries=3)
    assert result == "success"
    assert mock_invoke.call_count == 2


@patch("claude_client.time.sleep")
@patch("claude_client._invoke")
def test_retries_on_parse_error(mock_invoke, mock_sleep):
    mock_invoke.side_effect = [ParseError("bad json"), "ok"]
    result = _invoke_with_retries("prompt", model="haiku", max_retries=3)
    assert result == "ok"


@patch("claude_client._invoke")
def test_no_retry_on_rate_limit(mock_invoke):
    mock_invoke.side_effect = RateLimitError("limit")
    with pytest.raises(RateLimitError):
        _invoke_with_retries("prompt", model="haiku", max_retries=5)
    assert mock_invoke.call_count == 1


@patch("claude_client.time.sleep")
@patch("claude_client._invoke")
def test_exhausts_retries(mock_invoke, mock_sleep):
    mock_invoke.side_effect = EmptyResponseError("always empty")
    with pytest.raises(EmptyResponseError):
        _invoke_with_retries("prompt", model="haiku", max_retries=3)
    assert mock_invoke.call_count == 3


@patch("claude_client.time.sleep")
@patch("claude_client._invoke")
def test_exponential_backoff(mock_invoke, mock_sleep):
    mock_invoke.side_effect = [EmptyResponseError("e1"), EmptyResponseError("e2"), "ok"]
    _invoke_with_retries("prompt", model="haiku", max_retries=5)
    sleeps = [call[0][0] for call in mock_sleep.call_args_list]
    assert sleeps[0] == 4   # min(4 * 2^0, 120)
    assert sleeps[1] == 8   # min(4 * 2^1, 120)


# --- prompt_text -------------------------------------------------------------

from claude_client import prompt_text


@patch("claude_client._invoke_with_retries")
def test_prompt_text_returns_text(mock_invoke):
    mock_invoke.return_value = "Analysis text here"
    result = prompt_text("Write analysis", model="haiku")
    assert result == "Analysis text here"


@patch("claude_client._invoke_with_retries")
def test_prompt_text_passes_params(mock_invoke):
    mock_invoke.return_value = "ok"
    prompt_text("p", model="sonnet", max_retries=3, verbose=True)
    mock_invoke.assert_called_once_with("p", model="sonnet", max_retries=3, verbose=True)


# --- prompt_json -------------------------------------------------------------

from claude_client import prompt_json


@patch("claude_client._invoke_with_retries")
def test_prompt_json_list(mock_invoke):
    mock_invoke.return_value = '[{"id": "1"}]'
    result = prompt_json("prompt", model="haiku", expect=list)
    assert result == [{"id": "1"}]


@patch("claude_client._invoke_with_retries")
def test_prompt_json_dict(mock_invoke):
    mock_invoke.return_value = '{"key": "val"}'
    result = prompt_json("prompt", model="haiku", expect=dict)
    assert result == {"key": "val"}


@patch("claude_client._invoke_with_retries")
def test_prompt_json_wrong_type(mock_invoke):
    mock_invoke.return_value = '{"key": "val"}'
    with pytest.raises(ParseError, match="Expected list"):
        prompt_json("prompt", model="haiku", expect=list)


@patch("claude_client._invoke_with_retries")
def test_prompt_json_invalid_json(mock_invoke):
    mock_invoke.return_value = "not json at all"
    with pytest.raises(ParseError, match="Failed to parse JSON"):
        prompt_json("prompt", model="haiku")


@patch("claude_client._invoke_with_retries")
def test_prompt_json_no_type_check(mock_invoke):
    mock_invoke.return_value = '{"key": "val"}'
    result = prompt_json("prompt", model="haiku")  # no expect
    assert result == {"key": "val"}


# --- prompt_batch ------------------------------------------------------------

from claude_client import prompt_batch


@patch("claude_client._invoke_with_retries")
def test_prompt_batch_chunking(mock_invoke):
    mock_invoke.side_effect = [
        '[{"id":"a"},{"id":"b"}]',
        '[{"id":"c"}]',
    ]
    results = prompt_batch(
        items=["a", "b", "c"],
        template="Process: {batch_items}",
        batch_size=2,
        model="haiku",
    )
    assert len(results) == 3
    assert mock_invoke.call_count == 2


@patch("claude_client._invoke_with_retries")
def test_prompt_batch_render_fn(mock_invoke):
    mock_invoke.return_value = '[{"id": "1"}]'
    render = lambda items: "\n".join(f"Item: {i}" for i in items)
    prompt_batch(items=["x"], template="{batch_items}", batch_size=10,
                 model="haiku", render_fn=render)
    sent_prompt = mock_invoke.call_args[0][0]
    assert "Item: x" in sent_prompt


@patch("claude_client._invoke_with_retries")
def test_prompt_batch_on_batch_callback(mock_invoke):
    mock_invoke.return_value = '[{"id":"a"}]'
    calls = []
    prompt_batch(
        items=["a"],
        template="{batch_items}",
        batch_size=10,
        model="haiku",
        on_batch=lambda idx, total, results: calls.append((idx, total, results)),
    )
    assert calls == [(1, 1, [{"id": "a"}])]


def test_prompt_batch_rejects_bad_template():
    with pytest.raises(ValueError, match="batch_items"):
        prompt_batch(items=["a"], template="no placeholder", batch_size=10, model="haiku")


@patch("claude_client._invoke_with_retries")
def test_prompt_batch_non_list_raises(mock_invoke):
    mock_invoke.return_value = '{"not": "a list"}'
    with pytest.raises(ParseError, match="Expected list"):
        prompt_batch(items=["a"], template="{batch_items}", batch_size=10, model="haiku")
