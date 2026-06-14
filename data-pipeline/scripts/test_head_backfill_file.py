"""Tests for the file-level head-backfill pass over chain.v1 JSONL round files.

`resnap_chain_file` streams a chain.v1 JSONL file, re-derives intermediate heads
from phrases (no LLM), re-snaps synsets via an injected callable, writes the
result, and reports stats. Idempotent and malformed-line tolerant.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from head_extraction_backfill import resnap_chain_file


def _snap(head: str):
    return None if head == "nowhere" else f"syn:{head}"


def _write_jsonl(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def _rec(chain_steps):
    return {
        "schema_version": "chain.v1",
        "topic": "ambush",
        "topic_synset_id": "100",
        "vehicle": "avalanche",
        "vehicle_synset_id": "200",
        "proposer": "sonnet_v1",
        "round": 2,
        "chain_signature": "a" * 64,
        "generated_at": "2026-06-04T00:00:00Z",
        "chain": chain_steps,
    }


def test_resnaps_file_and_reports_changes(tmp_path):
    rec = _rec([
        {"phrase": "ambush", "head": "ambush", "synset_id": "100"},
        {"phrase": "lightning strike", "head": "lightning", "synset_id": "syn:lightning"},
        {"phrase": "hidden accumulation", "head": "accumulation", "synset_id": "syn:accumulation"},
        {"phrase": "avalanche", "head": "avalanche", "synset_id": "200"},
    ])
    src = tmp_path / "in.jsonl"
    dst = tmp_path / "out.jsonl"
    _write_jsonl(src, [rec])

    stats = resnap_chain_file(str(src), str(dst), _snap)

    out = [json.loads(l) for l in dst.open() if l.strip()]
    assert len(out) == 1
    assert out[0]["chain"][1]["head"] == "strike"
    assert out[0]["chain"][1]["synset_id"] == "syn:strike"
    assert stats["n_records"] == 1
    assert stats["n_heads_changed"] == 1  # only the lightning->strike step moved


def test_idempotent_second_pass_changes_nothing(tmp_path):
    rec = _rec([
        {"phrase": "ambush", "head": "ambush", "synset_id": "100"},
        {"phrase": "lightning strike", "head": "lightning", "synset_id": "syn:lightning"},
        {"phrase": "avalanche", "head": "avalanche", "synset_id": "200"},
    ])
    src = tmp_path / "in.jsonl"
    mid = tmp_path / "mid.jsonl"
    dst = tmp_path / "out.jsonl"
    _write_jsonl(src, [rec])

    resnap_chain_file(str(src), str(mid), _snap)
    stats2 = resnap_chain_file(str(mid), str(dst), _snap)

    assert stats2["n_heads_changed"] == 0
    assert mid.read_text() == dst.read_text()


def test_tolerates_blank_and_malformed_lines(tmp_path):
    src = tmp_path / "in.jsonl"
    dst = tmp_path / "out.jsonl"
    good = _rec([
        {"phrase": "ambush", "head": "ambush", "synset_id": "100"},
        {"phrase": "lightning strike", "head": "lightning", "synset_id": "syn:lightning"},
        {"phrase": "avalanche", "head": "avalanche", "synset_id": "200"},
    ])
    with src.open("w", encoding="utf-8") as f:
        f.write("\n")
        f.write("{not json\n")
        f.write(json.dumps(good) + "\n")

    stats = resnap_chain_file(str(src), str(dst), _snap)

    out = [json.loads(l) for l in dst.open() if l.strip()]
    assert len(out) == 1
    assert stats["n_records"] == 1
    assert stats["n_malformed"] == 1
