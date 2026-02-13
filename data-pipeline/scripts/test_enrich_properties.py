"""Tests for enrich_properties.py — claude -p enrichment script."""
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Ensure scripts/ is importable when running from data-pipeline/
sys.path.insert(0, str(Path(__file__).parent))

from enrich_properties import (
    format_batch_items,
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


# --- 1. format_batch_items ---------------------------------------------------

def test_format_batch_items():
    text = format_batch_items(SAMPLE_SYNSETS)
    assert "ID: 100001" in text
    assert "Word: candle" in text
    assert "Definition: stick of wax with a wick" in text
    assert "ID: 100002" in text
    assert "Word: whisper" in text
    assert "Definition: speak softly" in text


# --- 2. extract_batch merges local data ---------------------------------------

@patch("enrich_properties.prompt_json")
def test_extract_batch_merges_local_data(mock_prompt_json):
    mock_prompt_json.return_value = CANNED_RESULT
    results = extract_batch(SAMPLE_SYNSETS, model="haiku")

    assert len(results) == 2
    r0 = results[0]
    assert r0["id"] == "100001"
    assert r0["lemma"] == "candle"
    assert r0["definition"] == "stick of wax with a wick"
    assert r0["pos"] == "n"
    assert "warm" in r0["properties"]


# --- 3. extract_batch warns on unknown IDs ------------------------------------

@patch("enrich_properties.prompt_json")
def test_extract_batch_warns_unknown_ids(mock_prompt_json, caplog):
    import logging
    bad_result = [{"id": "999999", "properties": ["unknown"]}]
    mock_prompt_json.return_value = bad_result
    with caplog.at_level(logging.WARNING):
        results = extract_batch(SAMPLE_SYNSETS, model="haiku")

    assert len(results) == 0
    assert any("999999" in r.message for r in caplog.records)


# --- 4. checkpoint round-trip -------------------------------------------------

def test_checkpoint_round_trip(tmp_path):
    cp_file = tmp_path / "checkpoint.json"
    state = {"completed_ids": ["100001", "100002"], "results": CANNED_RESULT}
    save_checkpoint(cp_file, state)
    loaded = load_checkpoint(cp_file)
    assert loaded["completed_ids"] == ["100001", "100002"]
    assert len(loaded["results"]) == 2


# --- 5. checkpoint resume filters completed ----------------------------------

def test_checkpoint_resume_filters_completed(tmp_path):
    cp_file = tmp_path / "checkpoint.json"
    state = {"completed_ids": ["100001"], "results": [CANNED_RESULT[0]]}
    save_checkpoint(cp_file, state)
    loaded = load_checkpoint(cp_file)
    completed = set(loaded["completed_ids"])

    remaining = [s for s in SAMPLE_SYNSETS if s["id"] not in completed]
    assert len(remaining) == 1
    assert remaining[0]["id"] == "100002"


# --- 6. UsageExhaustedError is RateLimitError alias --------------------------

def test_usage_exhausted_error_is_rate_limit_alias():
    """UsageExhaustedError is an alias for claude_client.RateLimitError."""
    from claude_client import RateLimitError
    assert UsageExhaustedError is RateLimitError


# --- 7. extract_batch surfaces RateLimitError immediately --------------------

@patch("enrich_properties.prompt_json")
def test_extract_batch_no_retry_on_usage_exhausted(mock_prompt_json):
    """RateLimitError surfaces immediately from prompt_json."""
    mock_prompt_json.side_effect = UsageExhaustedError("rate limit exceeded")
    with pytest.raises(UsageExhaustedError):
        extract_batch(SAMPLE_SYNSETS, model="haiku")
    assert mock_prompt_json.call_count == 1


# --- 8. extract_batch uses custom prompt_template ----------------------------

@patch("enrich_properties.prompt_json")
def test_extract_batch_custom_prompt_template(mock_prompt_json):
    """extract_batch uses prompt_template when provided."""
    mock_prompt_json.return_value = CANNED_RESULT
    custom = "Custom prompt: {batch_items}\nJSON only: [{{}}]"
    extract_batch(SAMPLE_SYNSETS, model="haiku", prompt_template=custom)

    # Verify the prompt passed to prompt_json contains our custom text
    sent_prompt = mock_prompt_json.call_args[0][0]
    assert "Custom prompt:" in sent_prompt
    assert "ID: 100001" in sent_prompt  # batch_items still interpolated


# --- 9. extract_batch uses BATCH_PROMPT by default --------------------------

@patch("enrich_properties.prompt_json")
def test_extract_batch_default_prompt_unchanged(mock_prompt_json):
    """extract_batch uses BATCH_PROMPT when no prompt_template given."""
    mock_prompt_json.return_value = CANNED_RESULT
    extract_batch(SAMPLE_SYNSETS, model="haiku")

    sent_prompt = mock_prompt_json.call_args[0][0]
    # BATCH_PROMPT contains "sensory and behavioural properties"
    assert "sensory and behavioural properties" in sent_prompt


# --- 10. extract_batch rejects invalid template -------------------------------

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


# --- 11. run_enrichment returns EnrichmentResult dataclass --------------------

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


# --- 12. run_enrichment tracks failed synset IDs ----------------------------

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


# --- 13. enrichment output JSON includes failed_synset_ids -------------------

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
