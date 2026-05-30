from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import json
import pytest
from grading_sidecar import paths as paths_mod

CHAIN = {
    "schema_version": "chain.v1",
    "topic": "anger", "topic_synset_id": "12345",
    "vehicle": "venom", "vehicle_synset_id": "67890",
    "proposer": "sonnet_v1", "round": 1,
    "chain": [
        {"phrase": "anger", "head": "anger", "synset_id": "12345"},
        {"phrase": "venom", "head": "venom", "synset_id": "67890"},
    ],
    "chain_signature": "a" * 64,
    "generated_at": "2026-05-30T03:14:00Z",
}

@pytest.fixture
def patched_paths(client, tmp_path, monkeypatch):
    monkeypatch.setattr(paths_mod, "GRADING_DIR", tmp_path)
    monkeypatch.setattr(paths_mod, "JUDGEMENTS_PATH", tmp_path / "j.jsonl")
    return client, tmp_path

def test_topics_lean_response(patched_paths):
    client, tmp_path = patched_paths
    f = tmp_path / "sonnet_chains_provisional_r1.jsonl"
    f.write_text(
        json.dumps(CHAIN) + "\n"
        + json.dumps({**CHAIN, "topic": "joy", "topic_synset_id": "11111",
                      "chain": [
                          {"phrase": "joy", "head": "joy", "synset_id": "11111"},
                          {"phrase": "venom", "head": "venom", "synset_id": "67890"},
                      ],
                      "chain_signature": "b"*64}) + "\n")
    r = client.get("/api/grading/topics")
    assert r.status_code == 200
    body = r.json()
    assert sorted(t["topic"] for t in body["topics"]) == ["anger", "joy"]
    # Lean — no per-topic counts (UI derives from /judgements)
    assert "chains_judged" not in body["topics"][0]

def test_stats_reports_counts(patched_paths):
    client, tmp_path = patched_paths
    (tmp_path / "sonnet_chains_provisional_r1.jsonl").write_text(json.dumps(CHAIN) + "\n")
    r = client.get("/api/grading/stats")
    assert r.status_code == 200
    body = r.json()
    assert body["chain_count"] == 1
    assert body["judgement_count"] == 0
    assert body["schema_version"]["chain"] == "chain.v1"

def test_calibration_sample_returns_n_chains(patched_paths):
    client, tmp_path = patched_paths
    f = tmp_path / "sonnet_chains_provisional_r1.jsonl"
    f.write_text("\n".join(
        json.dumps({**CHAIN, "chain_signature": format(i, "064x")})
        for i in range(20)
    ) + "\n")
    r = client.get("/api/grading/calibration-sample?n=5&round=1")
    assert r.status_code == 200
    assert len(r.json()["records"]) == 5

def test_calibration_sample_deterministic_with_seed(patched_paths):
    client, tmp_path = patched_paths
    f = tmp_path / "sonnet_chains_provisional_r1.jsonl"
    f.write_text("\n".join(
        json.dumps({**CHAIN, "chain_signature": format(i, "064x")})
        for i in range(20)
    ) + "\n")
    r1 = client.get("/api/grading/calibration-sample?n=5&round=1&seed=42")
    r2 = client.get("/api/grading/calibration-sample?n=5&round=1&seed=42")
    assert r1.json()["records"] == r2.json()["records"]

def test_calibration_sample_404_when_round_missing(patched_paths):
    client, _ = patched_paths
    r = client.get("/api/grading/calibration-sample?n=5&round=99")
    assert r.status_code == 404
