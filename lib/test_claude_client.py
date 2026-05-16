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


def test_strip_fences_javascript_language_tag():
    """Model occasionally emits ```javascript\\n...\\n``` rather than ```json.
    The fence regex must accept any lowercase language tag, otherwise the
    function falls through to the unfenced extractor and can return a
    corrupt body."""
    assert _strip_fences("```javascript\n[1,2]\n```") == "[1,2]"


def test_strip_fences_text_language_tag():
    """Same as above for ```text\\n..."""
    assert _strip_fences("```text\nsome text\n```") == "some text"


def test_strip_fences_empty_language_tag():
    """Regression: empty language tag must still work."""
    assert _strip_fences("```\n[1,2]\n```") == "[1,2]"


def test_strip_fences_unfenced_prose_with_stray_brace_before_array():
    """Prose mentions a `{placeholder}` brace before the real JSON array.
    Old extractor took the first opener (the `{` of `{placeholder}`),
    then rfind('}') matched that same brace — returning `{placeholder}`
    which fails to parse. Bracket-balance scan must extract the real
    array `[1,2,3]` regardless of stray braces in prose."""
    payload = "Note: the next batch uses {placeholder} IDs: [1,2,3]"
    result = _strip_fences(payload)
    # The result must parse as a JSON array (not as a stray brace).
    parsed = json.loads(result)
    assert parsed == [1, 2, 3]


def test_strip_fences_unfenced_plain_array():
    """Plain unfenced array — basic case."""
    result = _strip_fences("[1,2,3]")
    assert json.loads(result) == [1, 2, 3]


def test_strip_fences_unfenced_plain_object():
    """Plain unfenced object — basic case."""
    result = _strip_fences('{"a": 1}')
    assert json.loads(result) == {"a": 1}


def test_strip_fences_nested_array_in_object():
    """Bracket balance must handle depth — nested array inside object."""
    payload = 'Result: {"items": [1, 2, [3, 4]], "ok": true}'
    result = _strip_fences(payload)
    parsed = json.loads(result)
    assert parsed == {"items": [1, 2, [3, 4]], "ok": True}


def test_strip_fences_string_with_brackets_inside():
    """A `]` or `}` inside a JSON string literal must NOT decrement depth.
    Old rfind-based scan would match the bracket inside the string and
    truncate the body. Bracket-balance scan must respect string literals."""
    payload = 'Prefix: {"note": "contains ] and } chars", "n": 1}'
    result = _strip_fences(payload)
    parsed = json.loads(result)
    assert parsed == {"note": "contains ] and } chars", "n": 1}


def test_strip_fences_string_with_escaped_quote():
    """Escaped quote inside string must not close the string early."""
    payload = 'Out: {"note": "a \\"quoted\\" word", "n": 2}'
    result = _strip_fences(payload)
    parsed = json.loads(result)
    assert parsed == {"note": 'a "quoted" word', "n": 2}


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


def test_parse_events_empty_stdout_includes_marker():
    """EmptyResponseError on empty stdout must surface an empty-stdout
    marker in the exception message so retry-loop WARNING logs and outer
    callers can distinguish empty vs malformed vs no-result-event paths
    without re-running. Mirrors the head/tail diagnostic pattern that
    prompt_json already uses for JSON-decode failures."""
    with pytest.raises(EmptyResponseError) as excinfo:
        _parse_events("", 0, "")
    assert "(empty)" in str(excinfo.value)


def test_parse_events_malformed_json_includes_head_tail():
    """Top-level json.loads failure must include stdout head/tail in the
    exception message — otherwise the retry loop logs '... after error:
    Failed to parse claude stdout as JSON: ...' with zero visibility
    into what the CLI actually returned."""
    bad = "not-json-prose " + ("x" * 700) + " trailing-tail-marker"
    with pytest.raises(EmptyResponseError) as excinfo:
        _parse_events(bad, 0, "")
    msg = str(excinfo.value)
    assert "head=" in msg
    assert "tail=" in msg
    assert "trailing-tail-marker" in msg


def test_parse_events_no_result_event_includes_head_tail():
    """No-result-event error path must include stdout diagnostic too."""
    stdout = json.dumps([{"type": "system", "subtype": "init"}])
    with pytest.raises(EmptyResponseError) as excinfo:
        _parse_events(stdout, 0, "")
    msg = str(excinfo.value)
    assert "head=" in msg


def test_parse_events_missing_result_field_includes_keys():
    """Missing-result-field already names the keys; verify it still does
    AND that the head/tail diagnostic is attached so the retry log shows
    the actual CLI response shape."""
    stdout = json.dumps([{"type": "result", "is_error": False}])
    with pytest.raises(EmptyResponseError) as excinfo:
        _parse_events(stdout, 0, "")
    msg = str(excinfo.value)
    assert "head=" in msg
    assert "is_error" in msg  # the keys list is still present


def test_parse_events_unexpected_shape_includes_head_tail():
    """Unexpected top-level JSON shape (e.g. a string) must include the
    stdout diagnostic so we can see what was actually returned."""
    stdout = json.dumps("just a string")
    with pytest.raises(EmptyResponseError) as excinfo:
        _parse_events(stdout, 0, "")
    msg = str(excinfo.value)
    assert "head=" in msg


def test_empty_response_error_typed_fields():
    """EmptyResponseError must expose stdout_head, stdout_tail, total_len
    as typed attributes so structured callers don't have to regex-parse
    the message. Round 1's diagnostic is interpolated into args[0] only;
    type-design-analyzer flagged that as a magic-string contract."""
    bad = "prose-prefix " + ("x" * 700) + " trailing-tail"
    with pytest.raises(EmptyResponseError) as excinfo:
        _parse_events(bad, 0, "")
    e = excinfo.value
    assert hasattr(e, "stdout_head")
    assert hasattr(e, "stdout_tail")
    assert hasattr(e, "total_len")
    assert e.total_len == len(bad)
    assert "prose-prefix" in e.stdout_head
    assert "trailing-tail" in e.stdout_tail


def test_parse_error_typed_fields():
    """ParseError raised from prompt_json's JSON-decode path must expose
    the same typed fields as EmptyResponseError."""
    with patch("claude_client._invoke_with_retries") as mock_invoke:
        # Long enough to exceed the 500+500 cap so head/tail split applies.
        mock_invoke.return_value = "not-json-prose " + ("x" * 1500) + " end-marker"
        with pytest.raises(ParseError) as excinfo:
            prompt_json("prompt", model="haiku")
        e = excinfo.value
        assert hasattr(e, "stdout_head")
        assert hasattr(e, "stdout_tail")
        assert hasattr(e, "total_len")
        assert e.total_len > 0
        assert "end-marker" in e.stdout_tail
        assert "not-json-prose" in e.stdout_head


def test_parse_events_nonzero_exit_includes_head_tail():
    """Non-zero exit error must include stdout head/tail — currently only
    stderr is surfaced; if the CLI emitted partial stdout (e.g. a Bus
    Error after a 3-event prefix), that context disappears."""
    partial = '[{"type":"system","subtype":"init"}]'
    with pytest.raises(ClaudeError) as excinfo:
        _parse_events(partial, 1, "claude: segfault")
    msg = str(excinfo.value)
    assert "head=" in msg or partial[:50] in msg


def test_parse_events_handles_single_result_object_schema():
    """The claude CLI's --output-format=json schema returns a single result
    object, not a list. Earlier versions emitted a JSON array of events
    ({type:system,...}, {type:result,...}); current versions emit the
    final result event directly as a top-level object. The parser must
    accept both — otherwise the list-iteration path treats the dict's
    keys as events and raises 'str' object has no attribute 'get'.
    """
    stdout = json.dumps({
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": "hello",
    })
    assert _parse_events(stdout, 0, "") == "hello"


def test_parse_events_strips_fences_with_leading_prose():
    """Sonnet sometimes prefixes its fenced JSON with explanatory prose
    even when the system prompt says 'output only the JSON' — e.g.
    `Here are the properties:\\n```json\\n[...]\\n```\\n`. The strict
    anchored fence-strip regex left the prose intact, which broke the
    downstream json.loads with 'Expecting value: line 1 column 1 (char 0)'
    — exactly the failure mode the 8k enrichment run hit on batch 1.

    The robust stripper must extract the fenced body regardless of
    surrounding prose, in both directions.
    """
    payload = "Here are the properties:\n```json\n[1, 2, 3]\n```\nLet me know if you need adjustments."
    stdout = json.dumps({
        "type": "result",
        "is_error": False,
        "result": payload,
    })
    # After parsing + stripping we should get the bare JSON body, ready
    # for the caller's json.loads.
    assert _parse_events(stdout, 0, "") == "[1, 2, 3]"


def test_parse_events_strips_fences_with_trailing_prose():
    """Symmetric to the leading-prose case — model may close with a
    note after the fence."""
    payload = "```json\n{\"key\": \"value\"}\n```\n(end of response)"
    stdout = json.dumps({
        "type": "result",
        "is_error": False,
        "result": payload,
    })
    assert _parse_events(stdout, 0, "") == '{"key": "value"}'


def test_parse_events_extracts_unfenced_json_array_with_prose_prefix():
    """The model occasionally emits unfenced JSON prefixed with prose
    like 'Continuing with the remaining entries:\\n\\n[...]' — caught
    live on the 8k enrichment run after the fence-strip fix landed.
    The extractor must find the bare JSON array even without fences.
    """
    payload = (
        "Continuing with the remaining entries:\n\n"
        "[{\"id\": \"17211\", \"text\": \"written\"}, "
        "{\"id\": \"17212\", \"text\": \"weighty\"}]"
    )
    stdout = json.dumps({
        "type": "result",
        "is_error": False,
        "result": payload,
    })
    extracted = _parse_events(stdout, 0, "")
    parsed = json.loads(extracted)
    assert isinstance(parsed, list)
    assert parsed[0]["id"] == "17211"


def test_parse_events_extracts_unfenced_json_object_with_prose_prefix():
    """Same heuristic for JSON objects (single-dict responses, e.g. a
    one-synset call). The extractor should pick the largest sensible
    {...} block from the prose."""
    payload = "Here's the result:\n{\"answer\": 42}\nLet me know if you want more."
    stdout = json.dumps({
        "type": "result",
        "is_error": False,
        "result": payload,
    })
    extracted = _parse_events(stdout, 0, "")
    parsed = json.loads(extracted)
    assert parsed == {"answer": 42}


def test_parse_events_handles_single_result_object_rate_limit():
    """The dict-schema path must also detect rate-limit errors so the
    enrichment script doesn't retry on quota exhaustion."""
    stdout = json.dumps({
        "type": "result",
        "is_error": True,
        "result": "rate limit exceeded",
    })
    with pytest.raises(RateLimitError):
        _parse_events(stdout, 0, "")


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
    from claude_client import _EMPTY_MCP
    mock_run.return_value = _make_proc()
    _invoke("test prompt", model="haiku")
    cmd = mock_run.call_args[0][0]
    # Assert the stable prefix — model/max-turns/session flags — and then
    # check the MCP-config flags as a feature group so a single-arg tweak
    # doesn't drift the whole list. Both --strict-mcp-config and an
    # explicit empty MCP config are required so the CLI never inherits a
    # user's local MCP servers during automated enrichment runs.
    assert cmd[:9] == [
        "claude", "-p", "--output-format", "json",
        "--model", "haiku", "--max-turns", "1",
        "--no-session-persistence",
    ]
    assert "--strict-mcp-config" in cmd
    assert cmd[cmd.index("--mcp-config") + 1] == _EMPTY_MCP
    assert mock_run.call_args[1]["input"] == "test prompt"
    assert mock_run.call_args[1]["capture_output"] is True
    assert mock_run.call_args[1]["text"] is True
    # Timeout bumped 300→900 in 3eb1d101 to accommodate v2 enrichment
    # batches (240–360s typical, 900s gives headroom without masking hangs).
    assert mock_run.call_args[1]["timeout"] == 900


@patch("claude_client.subprocess.run")
def test_invoke_returns_parsed_text(mock_run):
    mock_run.return_value = _make_proc(result_text="the answer")
    assert _invoke("prompt", model="sonnet") == "the answer"


@patch("claude_client.subprocess.run")
def test_invoke_wraps_subprocess_timeout(mock_run):
    """subprocess.TimeoutExpired must be wrapped as ClaudeTimeoutError
    (a ClaudeError subclass), otherwise the narrow `except ClaudeError`
    in enrich_properties.run_enrichment (commit c5563cf6) lets the
    timeout escape and abandons every remaining batch in the run."""
    import subprocess as _sp
    from claude_client import ClaudeTimeoutError, ClaudeError
    mock_run.side_effect = _sp.TimeoutExpired(["claude"], 900)
    with pytest.raises(ClaudeTimeoutError) as excinfo:
        _invoke("prompt", model="haiku")
    # Must be a ClaudeError subclass so retry/checkpoint logic still wraps it.
    assert isinstance(excinfo.value, ClaudeError)
    # Message should surface the timeout duration for operator visibility.
    assert "900" in str(excinfo.value)


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


def test_invoke_with_retries_rejects_zero():
    """max_retries=0 must raise ValueError, not the TypeError footgun
    that comes from `raise last_error` when last_error is still None
    (the loop body never executed)."""
    with pytest.raises(ValueError, match="max_retries"):
        _invoke_with_retries("prompt", model="haiku", max_retries=0)


def test_invoke_with_retries_rejects_negative():
    """max_retries=-1 same as zero — must be a clean ValueError, not
    a silent fall-through."""
    with pytest.raises(ValueError, match="max_retries"):
        _invoke_with_retries("prompt", model="haiku", max_retries=-1)


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


@patch("claude_client._invoke_with_retries")
def test_prompt_json_wrong_type_includes_head_tail(mock_invoke):
    """prompt_json's expect-type-mismatch ParseError must include head/tail
    diagnostic context so operators can see what was returned without
    re-running the prompt. Round 1 added the diagnostic only on the
    json.loads failure path."""
    mock_invoke.return_value = '{"key": "val"}'
    with pytest.raises(ParseError) as excinfo:
        prompt_json("prompt", model="haiku", expect=list)
    msg = str(excinfo.value)
    assert "head=" in msg
    assert "tail=" in msg
    # Typed fields populated too.
    assert excinfo.value.total_len > 0


@patch("claude_client._invoke_with_retries")
def test_prompt_batch_malformed_json_includes_head_tail(mock_invoke):
    """prompt_batch JSON-decode failure must surface head/tail diagnostic
    so operators don't get a terse 'Failed to parse batch JSON: …' with
    zero visibility into the raw response."""
    mock_invoke.return_value = "prose only, no JSON here at all — operator must see this"
    with pytest.raises(ParseError) as excinfo:
        prompt_batch(items=["a"], template="{batch_items}", batch_size=10, model="haiku")
    msg = str(excinfo.value)
    assert "head=" in msg
    assert "tail=" in msg


@patch("claude_client._invoke_with_retries")
def test_prompt_batch_non_list_includes_head_tail(mock_invoke):
    """Same for the non-list-batch case."""
    mock_invoke.return_value = '{"not": "a list"}'
    with pytest.raises(ParseError) as excinfo:
        prompt_batch(items=["a"], template="{batch_items}", batch_size=10, model="haiku")
    msg = str(excinfo.value)
    assert "head=" in msg
    assert "tail=" in msg
