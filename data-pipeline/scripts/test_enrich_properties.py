"""Tests for enrich_properties.py — claude -p enrichment script."""
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Ensure scripts/ is importable when running from data-pipeline/
sys.path.insert(0, str(Path(__file__).parent))

from enrich_properties import (
    format_batch_items,
    parse_response,
    invoke_claude,
    extract_batch,
    load_checkpoint,
    save_checkpoint,
    run_enrichment,
    EnrichmentResult,
    UsageExhaustedError,
)


# --- Test data ---------------------------------------------------------------

SAMPLE_SYNSETS = [
    {"id": "100001", "lemma": "candle", "definition": "stick of wax with a wick", "pos": "n"},
    {"id": "100002", "lemma": "whisper", "definition": "speak softly", "pos": "v"},
]

CANNED_RESULT = [
    {"id": "100001", "properties": ["warm", "flickering", "luminous"]},
    {"id": "100002", "properties": ["quiet", "intimate", "breathy"]},
]


def _make_completed_process(result_payload, returncode=0, stderr=""):
    """Build a fake CompletedProcess with claude -p JSON event array."""
    events = [
        {"type": "system", "subtype": "init", "session_id": "test"},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": json.dumps(result_payload)}]}},
        {"type": "result", "subtype": "success", "is_error": False, "result": json.dumps(result_payload)},
    ]
    return subprocess.CompletedProcess(
        args=["claude"], returncode=returncode, stdout=json.dumps(events), stderr=stderr,
    )


def _make_fenced_process(result_payload):
    """Build a fake CompletedProcess where result has markdown fences."""
    inner = "```json\n" + json.dumps(result_payload) + "\n```"
    events = [
        {"type": "system", "subtype": "init", "session_id": "test"},
        {"type": "result", "subtype": "success", "is_error": False, "result": inner},
    ]
    return subprocess.CompletedProcess(
        args=["claude"], returncode=0, stdout=json.dumps(events), stderr="",
    )


# --- 1. format_batch_items ---------------------------------------------------

def test_format_batch_items():
    text = format_batch_items(SAMPLE_SYNSETS)
    assert "ID: 100001" in text
    assert "Word: candle" in text
    assert "Definition: stick of wax with a wick" in text
    assert "ID: 100002" in text
    assert "Word: whisper" in text
    assert "Definition: speak softly" in text


# --- 2. parse_response success -----------------------------------------------

def test_parse_response_success():
    proc = _make_completed_process(CANNED_RESULT)
    results = parse_response(proc)
    assert len(results) == 2
    assert results[0]["id"] == "100001"
    assert "warm" in results[0]["properties"]


# --- 3. parse_response markdown fences ----------------------------------------

def test_parse_response_markdown_fences():
    proc = _make_fenced_process(CANNED_RESULT)
    results = parse_response(proc)
    assert len(results) == 2
    assert results[1]["id"] == "100002"


# --- 4. parse_response CLI error ----------------------------------------------

def test_parse_response_cli_error():
    proc = subprocess.CompletedProcess(
        args=["claude"], returncode=1, stdout="", stderr="model not found",
    )
    with pytest.raises(RuntimeError, match="claude CLI failed"):
        parse_response(proc)


# --- 5. invoke_claude command shape -------------------------------------------

@patch("enrich_properties.subprocess.run")
def test_invoke_claude_command_shape(mock_run):
    mock_run.return_value = _make_completed_process(CANNED_RESULT)
    invoke_claude("test prompt", model="haiku")

    args, kwargs = mock_run.call_args
    cmd = args[0]
    assert cmd[0] == "claude"
    assert "-p" in cmd
    assert "--output-format" in cmd
    idx = cmd.index("--output-format")
    assert cmd[idx + 1] == "json"
    assert "--max-turns" in cmd
    idx = cmd.index("--max-turns")
    assert cmd[idx + 1] == "1"
    assert "--no-session-persistence" in cmd
    assert "--model" in cmd
    idx = cmd.index("--model")
    assert cmd[idx + 1] == "haiku"


# --- 6. invoke_claude stdin ---------------------------------------------------

@patch("enrich_properties.subprocess.run")
def test_invoke_claude_stdin(mock_run):
    mock_run.return_value = _make_completed_process(CANNED_RESULT)
    invoke_claude("my prompt text", model="sonnet")

    _, kwargs = mock_run.call_args
    assert kwargs["input"] == "my prompt text"
    assert kwargs["text"] is True
    assert kwargs["capture_output"] is True


# --- 7. extract_batch merges local data ---------------------------------------

@patch("enrich_properties.invoke_claude")
def test_extract_batch_merges_local_data(mock_invoke):
    mock_invoke.return_value = _make_completed_process(CANNED_RESULT)
    results = extract_batch(SAMPLE_SYNSETS, model="haiku")

    assert len(results) == 2
    r0 = results[0]
    assert r0["id"] == "100001"
    assert r0["lemma"] == "candle"
    assert r0["definition"] == "stick of wax with a wick"
    assert r0["pos"] == "n"
    assert "warm" in r0["properties"]


# --- 8. extract_batch warns on unknown IDs ------------------------------------

@patch("enrich_properties.invoke_claude")
def test_extract_batch_warns_unknown_ids(mock_invoke, capsys):
    bad_result = [{"id": "999999", "properties": ["unknown"]}]
    mock_invoke.return_value = _make_completed_process(bad_result)
    results = extract_batch(SAMPLE_SYNSETS, model="haiku")

    assert len(results) == 0
    captured = capsys.readouterr()
    assert "999999" in captured.out


# --- 9. checkpoint round-trip -------------------------------------------------

def test_checkpoint_round_trip(tmp_path):
    cp_file = tmp_path / "checkpoint.json"
    state = {"completed_ids": ["100001", "100002"], "results": CANNED_RESULT}
    save_checkpoint(cp_file, state)
    loaded = load_checkpoint(cp_file)
    assert loaded["completed_ids"] == ["100001", "100002"]
    assert len(loaded["results"]) == 2


# --- 10. checkpoint resume filters completed ----------------------------------

def test_checkpoint_resume_filters_completed(tmp_path):
    cp_file = tmp_path / "checkpoint.json"
    state = {"completed_ids": ["100001"], "results": [CANNED_RESULT[0]]}
    save_checkpoint(cp_file, state)
    loaded = load_checkpoint(cp_file)
    completed = set(loaded["completed_ids"])

    remaining = [s for s in SAMPLE_SYNSETS if s["id"] not in completed]
    assert len(remaining) == 1
    assert remaining[0]["id"] == "100002"


# --- 11. extract_batch retries on failure -------------------------------------

@patch("enrich_properties.invoke_claude")
def test_extract_batch_retries_on_failure(mock_invoke):
    fail_proc = subprocess.CompletedProcess(
        args=["claude"], returncode=1, stdout="", stderr="timeout",
    )
    ok_proc = _make_completed_process(CANNED_RESULT)
    mock_invoke.side_effect = [fail_proc, fail_proc, ok_proc]

    results = extract_batch(SAMPLE_SYNSETS, model="haiku")
    assert len(results) == 2
    assert mock_invoke.call_count == 3


# --- 12. UsageExhaustedError on rate limit ------------------------------------

def test_parse_response_rate_limit_raises_usage_exhausted():
    """parse_response raises UsageExhaustedError on rate-limit error text."""
    events = [
        {"type": "system", "subtype": "init", "session_id": "test"},
        {"type": "result", "subtype": "error", "is_error": True,
         "result": "rate limit exceeded, please wait"},
    ]
    proc = subprocess.CompletedProcess(
        args=["claude"], returncode=0, stdout=json.dumps(events), stderr="",
    )
    with pytest.raises(UsageExhaustedError, match="rate limit"):
        parse_response(proc)


def test_parse_response_quota_raises_usage_exhausted():
    """parse_response raises UsageExhaustedError on quota/429 error text."""
    for error_text in ["quota exceeded", "429 Too Many Requests", "usage limit reached", "overloaded"]:
        events = [
            {"type": "system", "subtype": "init", "session_id": "test"},
            {"type": "result", "subtype": "error", "is_error": True,
             "result": error_text},
        ]
        proc = subprocess.CompletedProcess(
            args=["claude"], returncode=0, stdout=json.dumps(events), stderr="",
        )
        with pytest.raises(UsageExhaustedError):
            parse_response(proc)


def test_parse_response_non_rate_limit_error_raises_runtime_error():
    """parse_response raises RuntimeError (not UsageExhaustedError) for other errors."""
    events = [
        {"type": "system", "subtype": "init", "session_id": "test"},
        {"type": "result", "subtype": "error", "is_error": True,
         "result": "model not available"},
    ]
    proc = subprocess.CompletedProcess(
        args=["claude"], returncode=0, stdout=json.dumps(events), stderr="",
    )
    with pytest.raises(RuntimeError, match="model not available"):
        parse_response(proc)
    # Ensure it's NOT a UsageExhaustedError
    try:
        parse_response(proc)
    except UsageExhaustedError:
        pytest.fail("Should not raise UsageExhaustedError for non-rate-limit errors")
    except RuntimeError:
        pass  # expected


# --- 13. extract_batch does NOT retry on UsageExhaustedError ------------------

@patch("enrich_properties.invoke_claude")
def test_extract_batch_no_retry_on_usage_exhausted(mock_invoke):
    """UsageExhaustedError surfaces immediately, no retries."""
    events = [
        {"type": "system", "subtype": "init", "session_id": "test"},
        {"type": "result", "subtype": "error", "is_error": True,
         "result": "rate limit exceeded"},
    ]
    mock_invoke.return_value = subprocess.CompletedProcess(
        args=["claude"], returncode=0, stdout=json.dumps(events), stderr="",
    )
    with pytest.raises(UsageExhaustedError):
        extract_batch(SAMPLE_SYNSETS, model="haiku")
    # Should be called exactly once — no retries
    assert mock_invoke.call_count == 1


# --- 14. extract_batch uses custom prompt_template ----------------------------

@patch("enrich_properties.invoke_claude")
def test_extract_batch_custom_prompt_template(mock_invoke):
    """extract_batch uses prompt_template when provided."""
    mock_invoke.return_value = _make_completed_process(CANNED_RESULT)
    custom = "Custom prompt: {batch_items}\nJSON only: [{{}}]"
    extract_batch(SAMPLE_SYNSETS, model="haiku", prompt_template=custom)

    # Verify the prompt passed to invoke_claude contains our custom text
    call_args = mock_invoke.call_args
    prompt_text = call_args[0][0]
    assert "Custom prompt:" in prompt_text
    assert "ID: 100001" in prompt_text  # batch_items still interpolated


# --- 15. extract_batch uses BATCH_PROMPT by default --------------------------

@patch("enrich_properties.invoke_claude")
def test_extract_batch_default_prompt_unchanged(mock_invoke):
    """extract_batch uses BATCH_PROMPT when no prompt_template given."""
    mock_invoke.return_value = _make_completed_process(CANNED_RESULT)
    extract_batch(SAMPLE_SYNSETS, model="haiku")

    call_args = mock_invoke.call_args
    prompt_text = call_args[0][0]
    # BATCH_PROMPT contains "sensory and behavioural properties"
    assert "sensory and behavioural properties" in prompt_text


# --- 16. extract_batch rejects invalid template -------------------------------

def test_extract_batch_invalid_template():
    """extract_batch raises ValueError if template lacks {batch_items}."""
    with pytest.raises(ValueError, match="batch_items"):
        extract_batch(SAMPLE_SYNSETS, model="haiku", prompt_template="No placeholder here")


# --- Helpers for run_enrichment tests ----------------------------------------

def _mock_sqlunet_db():
    """Create a MagicMock that acts like a Path for SQLUNET_DB."""
    mock_path = MagicMock()
    mock_path.exists.return_value = True
    mock_path.__str__ = lambda s: ":memory:"
    return mock_path


# --- 17. run_enrichment returns EnrichmentResult dataclass --------------------

@patch("enrich_properties.extract_batch")
@patch("enrich_properties.get_pilot_synsets")
@patch("enrich_properties.sqlite3")
def test_run_enrichment_returns_enrichment_result(
    mock_sqlite, mock_get_synsets, mock_extract, tmp_path,
):
    """run_enrichment returns an EnrichmentResult dataclass with expected fields."""
    mock_conn = MagicMock()
    mock_sqlite.connect.return_value = mock_conn

    mock_get_synsets.return_value = SAMPLE_SYNSETS
    mock_extract.return_value = [
        {"id": "100001", "lemma": "candle", "definition": "stick of wax", "pos": "n",
         "properties": ["warm", "flickering"]},
        {"id": "100002", "lemma": "whisper", "definition": "speak softly", "pos": "v",
         "properties": ["quiet", "intimate"]},
    ]

    with patch("enrich_properties.SQLUNET_DB", _mock_sqlunet_db()), \
         patch("enrich_properties.OUTPUT_DIR", tmp_path):
        result = run_enrichment(
            size=2,
            batch_size=20,
            delay=0,
            output_file=tmp_path / "out.json",
        )

    assert isinstance(result, EnrichmentResult)
    assert result.requested == 2
    assert result.succeeded == 2
    assert result.failed == 0
    assert result.failed_ids == []
    assert result.coverage == 1.0
    assert (tmp_path / "out.json").exists()
    assert result.output_file == str(tmp_path / "out.json")


# --- 18. run_enrichment tracks failed synset IDs ----------------------------

@patch("enrich_properties.extract_batch")
@patch("enrich_properties.get_pilot_synsets")
@patch("enrich_properties.sqlite3")
def test_run_enrichment_tracks_failed_synset_ids(
    mock_sqlite, mock_get_synsets, mock_extract, tmp_path,
):
    """When a batch fails, run_enrichment captures the failed synset IDs."""
    mock_conn = MagicMock()
    mock_sqlite.connect.return_value = mock_conn

    synsets = [
        {"id": "100001", "lemma": "candle", "definition": "stick of wax", "pos": "n"},
        {"id": "100002", "lemma": "whisper", "definition": "speak softly", "pos": "v"},
        {"id": "100003", "lemma": "thunder", "definition": "loud noise", "pos": "n"},
    ]
    mock_get_synsets.return_value = synsets

    # First batch succeeds (first 2), second batch fails (third synset)
    mock_extract.side_effect = [
        [
            {"id": "100001", "lemma": "candle", "definition": "stick of wax", "pos": "n",
             "properties": ["warm"]},
            {"id": "100002", "lemma": "whisper", "definition": "speak softly", "pos": "v",
             "properties": ["quiet"]},
        ],
        RuntimeError("API failure"),
    ]

    with patch("enrich_properties.SQLUNET_DB", _mock_sqlunet_db()), \
         patch("enrich_properties.OUTPUT_DIR", tmp_path):
        result = run_enrichment(
            size=3,
            batch_size=2,
            delay=0,
            output_file=tmp_path / "out.json",
        )

    assert isinstance(result, EnrichmentResult)
    assert result.succeeded == 2
    assert result.failed == 1
    assert result.failed_ids == ["100003"]
    assert result.coverage == pytest.approx(2 / 3)


# --- 19. enrichment output JSON includes failed_synset_ids -------------------

@patch("enrich_properties.extract_batch")
@patch("enrich_properties.get_pilot_synsets")
@patch("enrich_properties.sqlite3")
def test_enrichment_output_json_includes_failed_ids(
    mock_sqlite, mock_get_synsets, mock_extract, tmp_path,
):
    """Output JSON file includes failed_synset_ids in stats."""
    mock_conn = MagicMock()
    mock_sqlite.connect.return_value = mock_conn

    synsets = [
        {"id": "100001", "lemma": "candle", "definition": "stick of wax", "pos": "n"},
        {"id": "100002", "lemma": "whisper", "definition": "speak softly", "pos": "v"},
    ]
    mock_get_synsets.return_value = synsets

    # First synset succeeds, second batch fails
    mock_extract.side_effect = [
        [{"id": "100001", "lemma": "candle", "definition": "stick of wax", "pos": "n",
          "properties": ["warm"]}],
        RuntimeError("Timeout"),
    ]

    with patch("enrich_properties.SQLUNET_DB", _mock_sqlunet_db()), \
         patch("enrich_properties.OUTPUT_DIR", tmp_path):
        result = run_enrichment(
            size=2,
            batch_size=1,
            delay=0,
            output_file=tmp_path / "out.json",
        )

    output = json.loads((tmp_path / "out.json").read_text())
    assert "failed_synset_ids" in output["stats"]
    assert output["stats"]["failed_synset_ids"] == ["100002"]


# --- 20. invoke_claude verbose logs raw output --------------------------------

@patch("enrich_properties.subprocess.run")
def test_invoke_claude_verbose_logs_raw_output(mock_run, caplog):
    """With verbose=True, invoke_claude logs the raw stdout at DEBUG level."""
    import logging

    mock_run.return_value = _make_completed_process(CANNED_RESULT)
    with caplog.at_level(logging.DEBUG, logger="enrich_properties"):
        invoke_claude("test prompt", model="haiku", verbose=True)

    assert any("stdout" in r.message.lower() or "raw" in r.message.lower()
               for r in caplog.records)


# --- 21. invoke_claude verbose logs stderr on failure -------------------------

@patch("enrich_properties.subprocess.run")
def test_invoke_claude_verbose_logs_stderr_on_failure(mock_run, caplog):
    """With verbose=True, invoke_claude logs stderr when present."""
    import logging

    fail_proc = subprocess.CompletedProcess(
        args=["claude"], returncode=1, stdout="", stderr="error detail",
    )
    mock_run.return_value = fail_proc

    with caplog.at_level(logging.DEBUG, logger="enrich_properties"):
        invoke_claude("test prompt", model="haiku", verbose=True)

    assert any("stderr" in r.message.lower() or "error detail" in r.message
               for r in caplog.records)
