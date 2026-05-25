"""Tests for the loop harness loaders (the parts that don't touch the DB).

The end-to-end ``evaluate_loop`` is exercised via the smoke-test
baseline pass (committed alongside the harness). These tests cover
the cohort loaders that flatten the per-format file shapes into the
common row dict the metric module expects.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest

import evaluate_loop_harness as h


def _write_jsonl(path: Path, items: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for it in items:
            fh.write(json.dumps(it) + "\n")


# ---------------------------------------------------------------------------
# Phase 2 loader
# ---------------------------------------------------------------------------


def test_phase2_loader_flattens_apt_metaphors(tmp_path):
    apt = tmp_path / "apt.jsonl"
    inapt = tmp_path / "inapt.jsonl"
    _write_jsonl(apt, [
        {"topic": "anger", "metaphors": [
            {"vehicle": "fire", "shared_features": [], "confidence": 0.9},
            {"vehicle": "storm", "shared_features": [], "confidence": 0.7},
        ]},
    ])
    _write_jsonl(inapt, [
        {"topic": "anger", "inapt_metaphors": [
            {"vehicle": "fury", "inapt_reason_type": "same_domain", "explanation": "x"},
        ]},
    ])
    rows = h._load_phase2_pairs(apt, inapt)
    assert len(rows) == 3
    apt_rows = [r for r in rows if r["cohort"] == "apt"]
    inapt_rows = [r for r in rows if r["cohort"] == "inapt"]
    assert {(r["topic"], r["vehicle"]) for r in apt_rows} == {("anger", "fire"), ("anger", "storm")}
    assert inapt_rows[0]["inapt_reason_type"] == "same_domain"


def test_phase2_loader_skips_malformed(tmp_path):
    apt = tmp_path / "apt.jsonl"
    inapt = tmp_path / "inapt.jsonl"
    _write_jsonl(apt, [
        {"topic": "anger", "metaphors": [
            {"vehicle": "fire"},
            "not a dict",
            {"shared_features": []},  # no vehicle
            {"vehicle": 12345},  # non-string vehicle
            {"vehicle": ""},  # empty vehicle
        ]},
        {"metaphors": [{"vehicle": "x"}]},  # no topic
        {"topic": "anger", "metaphors": "not a list"},
    ])
    _write_jsonl(inapt, [])
    rows = h._load_phase2_pairs(apt, inapt)
    # Only one valid (anger, fire) survives the filters.
    assert len(rows) == 1
    assert rows[0]["topic"] == "anger" and rows[0]["vehicle"] == "fire"


def test_phase2_loader_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        h._load_phase2_pairs(tmp_path / "nope.jsonl", tmp_path / "nope2.jsonl")


# ---------------------------------------------------------------------------
# Lakoff loader
# ---------------------------------------------------------------------------


def test_lakoff_loader_reads_one_per_line(tmp_path):
    apt = tmp_path / "lakoff_apt.jsonl"
    inapt = tmp_path / "lakoff_inapt.jsonl"
    _write_jsonl(apt, [
        {"topic": "anger", "vehicle": "fire", "lakoff_class": "ANGER IS FIRE"},
        {"topic": "anger", "vehicle": "heat"},
    ])
    _write_jsonl(inapt, [
        {"topic": "anger", "vehicle": "umbrella", "label": "inapt"},
    ])
    rows = h._load_lakoff_pairs(apt, inapt)
    assert len(rows) == 3
    cohorts = {r["cohort"] for r in rows}
    assert cohorts == {"apt", "inapt"}


def test_lakoff_loader_tolerates_garbled_lines(tmp_path):
    apt = tmp_path / "a.jsonl"
    inapt = tmp_path / "i.jsonl"
    apt.write_text(
        '{"topic": "anger", "vehicle": "fire"}\n'
        'not valid json\n'
        '{"topic": 123, "vehicle": "x"}\n'   # non-string topic
        '"a bare string"\n'                  # not a dict
        '{"topic": "anger", "vehicle": "heat"}\n'
    )
    _write_jsonl(inapt, [])
    rows = h._load_lakoff_pairs(apt, inapt)
    assert len(rows) == 2
    assert {r["vehicle"] for r in rows} == {"fire", "heat"}
