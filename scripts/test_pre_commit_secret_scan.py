"""Tests for pre_commit_secret_scan.py — written first (TDD/RED).

All tests use tmp directories so they never touch the real grading data.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure the script under test is importable.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from pre_commit_secret_scan import scan_text, scan_dir  # noqa: E402


# ---------------------------------------------------------------------------
# scan_text tests
# ---------------------------------------------------------------------------


class TestKnownSecretPrefixes:
    def test_openai_key_flagged(self):
        text = "api_key = sk-abc1234567890abcdefghijklmnopqrst"
        findings = scan_text(text)
        assert any("known secret prefix" in f for f in findings), findings

    def test_github_pat_flagged(self):
        text = "token = ghp_abc1234567890abcdefghij"
        findings = scan_text(text)
        assert any("known secret prefix" in f for f in findings), findings

    def test_github_oauth_flagged(self):
        text = "token = gho_abc1234567890abcdefghij"
        findings = scan_text(text)
        assert any("known secret prefix" in f for f in findings), findings

    def test_slack_bot_token_flagged(self):
        text = "slack_token = xoxb-11111111111-22222222222-abc1234567890"
        findings = scan_text(text)
        assert any("known secret prefix" in f for f in findings), findings

    def test_aws_access_key_flagged(self):
        text = "aws_key = AKIAIOSFODNN7EXAMPLE1234"
        findings = scan_text(text)
        assert any("known secret prefix" in f for f in findings), findings

    def test_pem_private_key_flagged(self):
        text = "-----BEGIN RSA PRIVATE KEY-----\nabc123"
        findings = scan_text(text)
        assert any("known secret prefix" in f for f in findings), findings


class TestHighEntropyStrings:
    def test_high_entropy_40char_hex_flagged(self):
        # Random-looking 40-hex SHA1 — uniform distribution, high entropy
        text = "hash = a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
        findings = scan_text(text)
        assert any("high-entropy hex" in f for f in findings), findings

    def test_normal_english_prose_not_flagged(self):
        text = (
            "The quick brown fox jumps over the lazy dog. "
            "This is a perfectly normal sentence with no secrets."
        )
        findings = scan_text(text)
        assert findings == [], findings

    def test_short_hex_not_flagged(self):
        # 8-char hex is too short to trigger
        text = "colour = #1a2b3c4d"
        findings = scan_text(text)
        # Should not flag as high-entropy hex (below min length)
        hex_findings = [f for f in findings if "high-entropy hex" in f]
        assert hex_findings == []


class TestNormalContent:
    def test_empty_string_not_flagged(self):
        assert scan_text("") == []

    def test_normal_jsonl_record_not_flagged(self):
        import json
        record = {
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
        # Note: chain_signature is 64 repeated 'a' — uniform hex chars, may have
        # moderate entropy. Test that normal grading data doesn't false-positive.
        text = json.dumps(record)
        findings = scan_text(text)
        # chain_signature of all-same char has entropy 0 — must NOT be flagged
        assert findings == [], f"Unexpected findings in normal record: {findings}"

    def test_chain_signature_hex_in_jsonl_not_flagged(self):
        """chain_signature is a SHA-256 hex digest — benign identifier, not a secret."""
        import json
        # Use a realistic high-entropy chain_signature (like the real grading data).
        record = {
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
            # High-entropy SHA-256: would trigger hex check if not suppressed.
            "chain_signature": "9ea3c79fdf724c66b1808f9beaa13be92cd3996a2baed39be70f4bade3e6eba0",
            "generated_at": "2026-05-30T00:00:00Z",
        }
        text = json.dumps(record)
        findings = scan_text(text)
        assert findings == [], f"chain_signature falsely flagged: {findings}"


# ---------------------------------------------------------------------------
# scan_dir tests
# ---------------------------------------------------------------------------


class TestScanDir:
    def test_file_with_openai_key_flagged(self, tmp_path):
        f = tmp_path / "secrets.jsonl"
        f.write_text('{"key": "sk-abc1234567890abcdefghijklmnopqrst"}')
        results = scan_dir(tmp_path)
        assert str(f) in results
        assert any("known secret prefix" in item for item in results[str(f)])

    def test_file_with_github_pat_flagged(self, tmp_path):
        f = tmp_path / "data.jsonl"
        f.write_text('{"token": "ghp_abc1234567890abcdefghij"}')
        results = scan_dir(tmp_path)
        assert str(f) in results

    def test_file_with_high_entropy_hex_flagged(self, tmp_path):
        f = tmp_path / "hashes.txt"
        # 40-char hex string with high entropy (many distinct chars)
        f.write_text("digest = a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2")
        results = scan_dir(tmp_path)
        assert str(f) in results

    def test_file_with_normal_prose_not_flagged(self, tmp_path):
        f = tmp_path / "notes.txt"
        f.write_text("This is completely normal text with no secrets.")
        results = scan_dir(tmp_path)
        assert results == {}

    def test_missing_directory_returns_empty_dict(self, tmp_path):
        missing = tmp_path / "does_not_exist"
        results = scan_dir(missing)
        assert results == {}

    def test_empty_directory_returns_empty_dict(self, tmp_path):
        results = scan_dir(tmp_path)
        assert results == {}

    def test_subdirectory_files_scanned_recursively(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        f = sub / "nested.jsonl"
        f.write_text('{"api_key": "sk-abc1234567890abcdefghijklmnopqrst"}')
        results = scan_dir(tmp_path)
        assert str(f) in results

    def test_clean_file_not_in_results(self, tmp_path):
        clean = tmp_path / "clean.jsonl"
        clean.write_text('{"label": "live", "notes": "looks good"}')
        dirty = tmp_path / "dirty.jsonl"
        dirty.write_text('{"key": "sk-abc1234567890abcdefghijklmnopqrst"}')
        results = scan_dir(tmp_path)
        assert str(clean) not in results
        assert str(dirty) in results
