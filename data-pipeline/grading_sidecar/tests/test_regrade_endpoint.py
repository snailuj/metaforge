"""Tests for the blind re-grade routes.

Two safety properties under test:
  * /sample returns chains STRIPPED of the prior verdict (otherwise the re-grade
    is not blind).
  * /regrade POST lands in a SEPARATE file and never touches the gold judgements
    (the gold resolver is latest-wins, so a regrade in the gold file would
    silently overwrite the verdict it is meant to be compared against).
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import json
import pytest
from grading_sidecar import paths as paths_mod


def _v2(ts, sig, metaphor, *, topic="anxiety", tsid="72810", linkage="good"):
    return {"schema_version": "judgement.v2", "ts": ts, "judged_by": "julian",
            "round": 1, "topic": topic, "topic_synset_id": tsid, "vehicle": "swarm",
            "vehicle_synset_id": "9", "proposer": "sonnet", "chain_signature": sig,
            "linkage": linkage, "metaphor": metaphor, "tiers": [], "tags": [],
            "confidence": "high", "notes": "", "supersedes_ts": None}


def _chain(sig, *, topic="anxiety", tsid="72810", vehicle="swarm"):
    return {"schema_version": "chain.v1", "topic": topic, "topic_synset_id": tsid,
            "vehicle": vehicle, "vehicle_synset_id": "9", "proposer": "sonnet",
            "round": 1, "chain_signature": sig,
            "chain": [{"phrase": topic, "head": topic, "synset_id": tsid},
                      {"phrase": "shoal", "head": "shoal", "synset_id": "5"},
                      {"phrase": vehicle, "head": vehicle, "synset_id": "9"}],
            "generated_at": "2026-06-01T00:00:00+00:00"}


def _sig(c):
    return c * 64


def _write_jsonl(path, *records):
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")


@pytest.fixture
def regrade_client(client, tmp_path, monkeypatch):
    monkeypatch.setattr(paths_mod, "GRADING_DIR", tmp_path)
    monkeypatch.setattr(paths_mod, "JUDGEMENTS_PATH", tmp_path / "judgements_provisional.jsonl")
    monkeypatch.setattr(paths_mod, "REGRADES_PATH", tmp_path / "regrades_blind_provisional.jsonl")
    return client


def test_sample_returns_blind_chain_records(regrade_client, tmp_path):
    _write_jsonl(tmp_path / "sonnet_chains_provisional_r1.jsonl",
                 _chain(_sig("a")), _chain(_sig("b")))
    _write_jsonl(
        paths_mod.JUDGEMENTS_PATH,
        _v2("2020-01-01T10:00:00+00:00", _sig("a"), "live"),
        _v2("2020-01-01T10:01:00+00:00", _sig("b"), "dead"),
    )
    r = regrade_client.get("/api/grading/regrade/sample?n=2&min_age_days=1&seed=1")
    assert r.status_code == 200
    items = r.json()["records"]
    assert len(items) == 2
    for it in items:
        assert it["chain_signature"] in (_sig("a"), _sig("b"))
        assert it["topic"] == "anxiety"
        assert len(it["chain"]) == 3            # full path so the operator can re-grade linkage
        # No verdict rides along — otherwise the re-grade would not be blind.
        assert "metaphor" not in it
        assert "linkage" not in it
        assert "tiers" not in it
        assert "tags" not in it


def test_sample_drops_sig_with_no_chain(regrade_client, tmp_path):
    # Verdict exists but the chain file no longer carries it -> skip, don't 500.
    _write_jsonl(tmp_path / "sonnet_chains_provisional_r1.jsonl", _chain(_sig("a")))
    _write_jsonl(
        paths_mod.JUDGEMENTS_PATH,
        _v2("2020-01-01T10:00:00+00:00", _sig("a"), "live"),
        _v2("2020-01-01T10:01:00+00:00", _sig("b"), "dead"),
    )
    items = regrade_client.get(
        "/api/grading/regrade/sample?n=10&min_age_days=1&seed=1").json()["records"]
    assert [it["chain_signature"] for it in items] == [_sig("a")]


def test_post_regrade_writes_separate_file_not_gold(regrade_client):
    _write_jsonl(paths_mod.JUDGEMENTS_PATH,
                 _v2("2020-01-01T10:00:00+00:00", _sig("a"), "live"))
    gold_before = paths_mod.JUDGEMENTS_PATH.read_text()

    body = _v2("2026-06-12T10:00:00+00:00", _sig("a"), "dead")
    r = regrade_client.post("/api/grading/regrade", json=body)
    assert r.status_code == 200

    # Gold file is byte-for-byte untouched.
    assert paths_mod.JUDGEMENTS_PATH.read_text() == gold_before
    # The regrade landed in the separate blind file.
    lines = paths_mod.REGRADES_PATH.read_text().strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["metaphor"] == "dead"


def test_agreement_pairs_gold_with_regrades(regrade_client):
    _write_jsonl(
        paths_mod.JUDGEMENTS_PATH,
        _v2("2020-01-01T10:00:00+00:00", _sig("a"), "live"),
        _v2("2020-01-01T10:01:00+00:00", _sig("b"), "dead"),
    )
    _write_jsonl(
        paths_mod.REGRADES_PATH,
        _v2("2026-06-12T10:00:00+00:00", _sig("a"), "live"),   # agrees
        _v2("2026-06-12T10:01:00+00:00", _sig("b"), "live"),   # flips
    )
    body = regrade_client.get("/api/grading/regrade/agreement").json()
    assert body["n_pairs"] == 2
    assert body["metaphor"]["agreement"] == 0.5


def test_sample_requires_secret_in_prod(monkeypatch, tmp_path):
    monkeypatch.delenv("GRADING_DEV", raising=False)
    monkeypatch.setattr(paths_mod, "GRADING_DIR", tmp_path)
    monkeypatch.setattr(paths_mod, "JUDGEMENTS_PATH", tmp_path / "judgements_provisional.jsonl")
    from grading_sidecar.app import create_app
    from fastapi.testclient import TestClient
    guarded = TestClient(create_app())
    r = guarded.get("/api/grading/regrade/sample")
    assert r.status_code in (401, 403)
