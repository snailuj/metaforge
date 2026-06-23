from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import json
import pytest
from grading_sidecar import paths as paths_mod

VALID_CHAIN_BASE = {
    "schema_version": "chain.v1",
    "topic": "anger", "topic_synset_id": "12345",
    "vehicle": "venom", "vehicle_synset_id": "67890",
    "proposer": "sonnet_v1", "round": 1,
    "chain": [
        {"phrase": "anger", "head": "anger", "synset_id": "12345"},
        {"phrase": "hostility", "head": "hostility", "synset_id": "54321"},
        {"phrase": "venom", "head": "venom", "synset_id": "67890"},
    ],
    "chain_signature": "a" * 64,
    "generated_at": "2026-05-30T03:14:00Z",
}

@pytest.fixture
def chains_client(client, tmp_path, monkeypatch):
    monkeypatch.setattr(paths_mod, "GRADING_DIR", tmp_path)
    return client

def _write_round(tmp_path, round_num, *records):
    f = tmp_path / f"sonnet_chains_provisional_r{round_num}.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in records) + "\n")

def test_get_chains_unions_multiple_round_files(chains_client, tmp_path):
    _write_round(tmp_path, 1, VALID_CHAIN_BASE)
    _write_round(tmp_path, 2, {**VALID_CHAIN_BASE, "round": 2, "chain_signature": "b"*64})
    r = chains_client.get("/api/grading/chains")
    assert r.status_code == 200
    assert r.json()["count"] == 2

def test_get_chains_topic_filter(chains_client, tmp_path):
    _write_round(tmp_path, 1,
        VALID_CHAIN_BASE,
        {**VALID_CHAIN_BASE,
         "topic": "joy", "topic_synset_id": "11111",
         "chain": [
            {"phrase": "joy", "head": "joy", "synset_id": "11111"},
            {"phrase": "venom", "head": "venom", "synset_id": "67890"},
         ],
         "chain_signature": "c"*64,
        },
    )
    r = chains_client.get("/api/grading/chains?topic=anger")
    assert r.status_code == 200
    assert r.json()["count"] == 1

def test_get_chains_skips_malformed_lines(chains_client, tmp_path):
    f = tmp_path / "sonnet_chains_provisional_r1.jsonl"
    f.write_text(json.dumps(VALID_CHAIN_BASE) + "\nNOT JSON\n")
    r = chains_client.get("/api/grading/chains")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert body["skipped_malformed"] == 1

def test_get_chains_empty_when_no_files(chains_client):
    r = chains_client.get("/api/grading/chains")
    assert r.status_code == 200
    assert r.json() == {"count": 0, "skipped_malformed": 0, "records": []}


def test_chains_endpoint_excludes_stock(client, tmp_path, monkeypatch):
    import json
    from grading_sidecar import paths as paths_mod
    monkeypatch.setattr(paths_mod, "GRADING_DIR", tmp_path)
    (tmp_path / "stock").mkdir()
    rec = {"schema_version": "chain.v1", "topic": "t", "topic_synset_id": "1",
           "vehicle": "v", "vehicle_synset_id": "2", "proposer": "p", "round": 1,
           "chain_signature": "a" * 64, "generated_at": "2026-06-01T00:00:00+00:00",
           "chain": [{"phrase": "t", "head": "t", "synset_id": "1"},
                     {"phrase": "v", "head": "v", "synset_id": "2"}]}
    (tmp_path / "chain-topics_curated.jsonl").write_text(json.dumps(rec) + "\n")
    stock = {**rec, "chain_signature": "b" * 64}
    (tmp_path / "stock" / "chain-topics_stock.jsonl").write_text(json.dumps(stock) + "\n")
    body = client.get("/api/grading/chains").json()
    sigs = {r["chain_signature"] for r in body["records"]}
    assert "a" * 64 in sigs and "b" * 64 not in sigs   # stock not in the grading view
