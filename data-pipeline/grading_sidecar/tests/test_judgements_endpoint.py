from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import json
import pytest
from grading_sidecar import paths as paths_mod

# New records are v2 — POST is a write path, so it carries the two axes + multi-select tiers.
VALID = {
    "schema_version": "judgement.v2",
    "ts": "2026-05-30T07:14:00Z",
    "judged_by": "julian", "round": 1,
    "topic": "anger", "topic_synset_id": "12345",
    "vehicle": "venom", "vehicle_synset_id": "67890",
    "proposer": "sonnet_v1",
    "chain_signature": "a" * 64,
    "linkage": "good", "metaphor": "live", "confidence": "high",
    "notes": "",
}

# A legacy v1 line (flat `label`) — read-only; the GET path must normalise it to axes.
V1_LINE = {
    "schema_version": "judgement.v1",
    "ts": "2026-05-29T07:14:00Z",
    "judged_by": "julian", "round": 1,
    "topic": "fear", "topic_synset_id": "11111",
    "vehicle": "shadow", "vehicle_synset_id": "22222",
    "proposer": "sonnet_v1",
    "chain_signature": "c" * 64,
    "label": "dead", "confidence": "high",
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
    stored = json.loads(lines[0])
    assert stored["topic"] == "anger"
    assert stored["linkage"] == "good"
    assert stored["metaphor"] == "live"

def test_post_judgement_persists_tiers(judgements_client):
    judgements_client.post("/api/grading/judgements", json={**VALID, "tiers": ["strong", "surprising"]})
    stored = json.loads((paths_mod.JUDGEMENTS_PATH).read_text().splitlines()[0])
    assert stored["tiers"] == ["strong", "surprising"]

def test_post_judgement_rejects_bad_metaphor(judgements_client):
    bad = {**VALID, "metaphor": "bogus"}
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
    rec = body["records"][0]
    assert rec["topic"] == "anger"
    # v2 records carry the axes verbatim.
    assert rec["linkage"] == "good"
    assert rec["metaphor"] == "live"
    assert rec["tiers"] == []

def test_get_judgements_normalises_v1_and_v2_uniformly(judgements_client):
    """GET maps every stored line through normalise_judgement so a legacy v1
    `label` line and a v2 axis line both expose linkage/metaphor/tiers."""
    # Seed a v1 line straight to disk (bypasses the v2-only POST validator).
    paths_mod.JUDGEMENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    paths_mod.JUDGEMENTS_PATH.write_text(json.dumps(V1_LINE) + "\n")
    # Add a v2 line via the normal POST path.
    judgements_client.post("/api/grading/judgements", json=VALID)

    body = judgements_client.get("/api/grading/judgements").json()
    by_sig = {r["chain_signature"]: r for r in body["records"]}

    v1 = by_sig["c" * 64]
    assert (v1["linkage"], v1["metaphor"], v1["tiers"]) == ("good", "dead", [])
    # Non-destructive: the original v1 label is preserved alongside the axes.
    assert v1["label"] == "dead"

    v2 = by_sig["a" * 64]
    assert (v2["linkage"], v2["metaphor"], v2["tiers"]) == ("good", "live", [])

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

def test_post_judgement_injects_ts_when_missing(judgements_client):
    """Server must inject ts when the client omits it — fixes 422 on every frontend POST."""
    payload = {k: v for k, v in VALID.items() if k != "ts"}
    r = judgements_client.post("/api/grading/judgements", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert "ts" in body
    # Should be an ISO-8601 UTC timestamp
    ts = body["ts"]
    assert "T" in ts
    assert ts.endswith("+00:00") or ts.endswith("Z")
