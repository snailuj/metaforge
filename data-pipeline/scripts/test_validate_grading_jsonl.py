"""Tests for validate_grading_jsonl.py — written first (TDD/RED)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Ensure the script under test is importable from this test file's location.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

# Also ensure grading_sidecar is importable.
_GRADING_SIDECAR = _HERE.parent / "grading_sidecar"
if str(_GRADING_SIDECAR) not in sys.path:
    sys.path.insert(0, str(_GRADING_SIDECAR))

from validate_grading_jsonl import validate_lines  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures — minimal valid records
# ---------------------------------------------------------------------------

VALID_CHAIN = {
    "schema_version": "chain.v1",
    "topic": "anger",
    "topic_synset_id": "30227",
    "vehicle": "volcano",
    "vehicle_synset_id": "79695",
    "proposer": "sonnet_v1",
    "round": 1,
    "chain": [
        {"phrase": "anger", "head": "anger", "synset_id": "30227"},
        {"phrase": "volcano", "head": "volcano", "synset_id": "79695"},
    ],
    "chain_signature": "a" * 64,
    "generated_at": "2026-05-30T00:00:00Z",
}

VALID_JUDGEMENT = {
    "schema_version": "judgement.v1",
    "ts": "2026-05-30T12:00:00Z",
    "judged_by": "julian",
    "round": 1,
    "topic": "anger",
    "topic_synset_id": "30227",
    "vehicle": "volcano",
    "vehicle_synset_id": "79695",
    "proposer": "sonnet_v1",
    "chain_signature": "a" * 64,
    "label": "live",
    "confidence": "high",
    "notes": "",
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestValidChainRecord:
    def test_single_valid_chain_record_reports_zero_errors(self):
        lines = [json.dumps(VALID_CHAIN)]
        result = validate_lines(lines)
        assert result["parsed_ok"] == 1
        assert result["bad_json"] == 0
        assert result["bad_version"] == 0
        assert result["bad_validation"] == 0
        assert result["errors"] == []


class TestValidJudgementRecord:
    def test_single_valid_judgement_record_reports_zero_errors(self):
        lines = [json.dumps(VALID_JUDGEMENT)]
        result = validate_lines(lines)
        assert result["parsed_ok"] == 1
        assert result["bad_json"] == 0
        assert result["bad_version"] == 0
        assert result["bad_validation"] == 0
        assert result["errors"] == []


class TestMalformedJson:
    def test_malformed_json_counted_as_bad_json_does_not_crash(self):
        lines = ["{not valid json}"]
        result = validate_lines(lines)
        assert result["bad_json"] == 1
        assert result["parsed_ok"] == 0
        assert len(result["errors"]) == 1
        assert "JSON parse" in result["errors"][0]

    def test_remaining_valid_lines_still_parsed_after_malformed_line(self):
        lines = ["{bad}", json.dumps(VALID_CHAIN)]
        result = validate_lines(lines)
        assert result["bad_json"] == 1
        assert result["parsed_ok"] == 1


class TestUnknownSchemaVersion:
    def test_unknown_schema_version_flagged_with_message(self):
        record = dict(VALID_CHAIN, schema_version="unknown.v99")
        lines = [json.dumps(record)]
        result = validate_lines(lines)
        assert result["bad_version"] == 1
        assert result["parsed_ok"] == 0
        assert len(result["errors"]) == 1
        assert "unknown schema_version" in result["errors"][0]
        assert "unknown.v99" in result["errors"][0]

    def test_missing_schema_version_key_flagged(self):
        record = {k: v for k, v in VALID_CHAIN.items() if k != "schema_version"}
        lines = [json.dumps(record)]
        result = validate_lines(lines)
        assert result["bad_version"] == 1

    def test_null_schema_version_flagged(self):
        record = dict(VALID_CHAIN, schema_version=None)
        lines = [json.dumps(record)]
        result = validate_lines(lines)
        assert result["bad_version"] == 1


class TestEmptyFile:
    def test_empty_file_reports_zero_errors_and_zero_records(self):
        result = validate_lines([])
        assert result["parsed_ok"] == 0
        assert result["bad_json"] == 0
        assert result["bad_version"] == 0
        assert result["bad_validation"] == 0
        assert result["errors"] == []

    def test_blank_lines_only_reports_zero_errors_and_zero_records(self):
        result = validate_lines(["", "  ", "\t"])
        assert result["parsed_ok"] == 0
        assert result["errors"] == []


class TestNonGradingSchema:
    def test_non_grading_schema_version_flagged(self):
        """A file matching the glob but with a non-grading schema_version is flagged."""
        record = {"schema_version": "something_else.v1", "data": "whatever"}
        lines = [json.dumps(record)]
        result = validate_lines(lines)
        assert result["bad_version"] == 1
        assert "unknown schema_version" in result["errors"][0]


class TestMixedLines:
    def test_mix_of_valid_invalid_and_unknown(self):
        bad_json_line = "{oops}"
        unknown_ver_line = json.dumps({"schema_version": "nope.v0", "x": 1})
        # Missing required fields — validation error
        bad_record = {"schema_version": "chain.v1", "topic": "anger"}
        bad_valid_line = json.dumps(bad_record)
        good_line = json.dumps(VALID_CHAIN)

        lines = [bad_json_line, unknown_ver_line, bad_valid_line, good_line]
        result = validate_lines(lines)
        assert result["parsed_ok"] == 1
        assert result["bad_json"] == 1
        assert result["bad_version"] == 1
        assert result["bad_validation"] == 1
        assert len(result["errors"]) == 3
