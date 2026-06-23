"""Tests for grading_sidecar.chain_store.load_chains — the shared chain loader.

Extracted from walk._load_chains (now its third use site: chains route, walk,
regrade). Same contract: union round files, dedup by signature (last file wins),
drop valid-JSON-but-schema-drifted lines so one bad generator line can't 500 a
consumer.
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import json
import pytest
from grading_sidecar import paths as paths_mod
from grading_sidecar.chain_store import load_chains


def _chain(sig, *, topic="anxiety", vehicle="swarm"):
    return {"schema_version": "chain.v1", "topic": topic, "topic_synset_id": "72810",
            "vehicle": vehicle, "vehicle_synset_id": "9", "proposer": "sonnet",
            "round": 1, "chain_signature": sig,
            "chain": [{"phrase": topic, "head": topic, "synset_id": "72810"},
                      {"phrase": vehicle, "head": vehicle, "synset_id": "9"}],
            "generated_at": "2026-06-01T00:00:00+00:00"}


def _write(path, *records):
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")


@pytest.fixture
def grading_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(paths_mod, "GRADING_DIR", tmp_path)
    return tmp_path


def test_load_chains_unions_rounds(grading_dir):
    _write(grading_dir / "sonnet_chains_provisional_r1.jsonl", _chain("a" * 64))
    _write(grading_dir / "sonnet_chains_provisional_r2.jsonl", _chain("b" * 64))
    sigs = {c["chain_signature"] for c in load_chains()}
    assert sigs == {"a" * 64, "b" * 64}


def test_load_chains_dedups_last_file_wins(grading_dir):
    _write(grading_dir / "sonnet_chains_provisional_r1.jsonl", _chain("a" * 64, vehicle="swarm"))
    _write(grading_dir / "sonnet_chains_provisional_r2.jsonl", _chain("a" * 64, vehicle="storm"))
    chains = load_chains()
    assert len(chains) == 1
    assert chains[0]["vehicle"] == "storm"      # later round supersedes


def test_load_chains_drops_schema_drift(grading_dir):
    good = _chain("a" * 64)
    drift = {"schema_version": "chain.v1", "topic": "x"}   # no chain_signature/vehicle
    _write(grading_dir / "sonnet_chains_provisional_r1.jsonl", good, drift)
    chains = load_chains()
    assert [c["chain_signature"] for c in chains] == ["a" * 64]


def test_load_chains_empty_when_no_files(grading_dir):
    assert load_chains() == []


def test_load_chains_cohort_selection_excludes_stock_for_grading(tmp_path, monkeypatch):
    import json
    from grading_sidecar import paths as paths_mod
    from grading_sidecar import chain_store
    monkeypatch.setattr(paths_mod, "GRADING_DIR", tmp_path)
    (tmp_path / "stock").mkdir()
    (tmp_path / "chain-topics_curated.jsonl").write_text(json.dumps(_chain("c1")) + "\n")
    (tmp_path / "sonnet_chains_provisional_r1.jsonl").write_text(json.dumps(_chain("s1")) + "\n")  # legacy spike
    (tmp_path / "stock" / "chain-topics_stock.jsonl").write_text(json.dumps(_chain("k1")) + "\n")

    grading = {c["chain_signature"] for c in chain_store.load_chains(paths_mod.GRADING_COHORTS)}
    assert grading == {"c1", "s1"}                       # stock excluded from grading views
    full = {c["chain_signature"] for c in chain_store.load_chains(paths_mod.SENSECHECK_COHORTS)}
    assert full == {"c1", "s1", "k1"}                    # sense-check sees stock
    # default (no args) == grading cohorts
    assert {c["chain_signature"] for c in chain_store.load_chains()} == {"c1", "s1"}
