from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import json
import pytest
from grading_sidecar import paths as paths_mod

VALID = {
    "schema_version": "judgement.v1",
    "ts": "2026-05-30T07:14:00Z",
    "judged_by": "julian", "round": 1,
    "topic": "anger", "topic_synset_id": "12345",
    "vehicle": "venom", "vehicle_synset_id": "67890",
    "proposer": "sonnet_v1",
    "chain_signature": "a" * 64,
    "label": "live", "confidence": "high",
    "notes": "",
}

@pytest.fixture
def judgements_client(client, tmp_path, monkeypatch):
    monkeypatch.setattr(paths_mod, "JUDGEMENTS_PATH", tmp_path / "j.jsonl")
    return client

def test_post_judgement_appends_and_returns(judgements_client):
    r = judgements_client.post("/api/grading/judgements", json=VALID)
    assert r.status_code == 200
    assert r.json()["chain_signature"] == "a" * 64

def test_post_judgement_persists_to_disk(judgements_client, tmp_path):
    judgements_client.post("/api/grading/judgements", json=VALID)
    lines = (paths_mod.JUDGEMENTS_PATH).read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["topic"] == "anger"

def test_post_judgement_rejects_bad_label(judgements_client):
    bad = {**VALID, "label": "bogus"}
    r = judgements_client.post("/api/grading/judgements", json=bad)
    assert r.status_code == 422

def test_post_judgement_rejects_oversized_notes(judgements_client):
    bad = {**VALID, "notes": "x" * 1001}
    r = judgements_client.post("/api/grading/judgements", json=bad)
    assert r.status_code == 422

def test_get_judgements_returns_appended(judgements_client):
    judgements_client.post("/api/grading/judgements", json=VALID)
    r = judgements_client.get("/api/grading/judgements")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert body["records"][0]["topic"] == "anger"

def test_get_judgements_topic_filter(judgements_client):
    judgements_client.post("/api/grading/judgements", json={**VALID, "topic": "anger"})
    judgements_client.post("/api/grading/judgements", json={**VALID, "topic": "joy"})
    r = judgements_client.get("/api/grading/judgements?topic=anger")
    assert r.status_code == 200
    assert r.json()["count"] == 1

def test_get_judgements_empty_when_no_file(judgements_client):
    r = judgements_client.get("/api/grading/judgements")
    assert r.status_code == 200
    assert r.json()["count"] == 0
