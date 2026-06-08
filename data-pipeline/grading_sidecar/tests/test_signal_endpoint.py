"""Tests for GET /api/grading/signal — the on-demand coverage/geometry report."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import json
import pytest
from grading_sidecar import paths as paths_mod


def _v2(ts, sig, metaphor, *, topic="anxiety", tsid="72810"):
    return {"schema_version": "judgement.v2", "ts": ts, "topic": topic,
            "topic_synset_id": tsid, "vehicle": "swarm", "vehicle_synset_id": "9",
            "chain_signature": sig, "linkage": "good", "metaphor": metaphor,
            "tiers": [], "tags": [], "confidence": "high", "supersedes_ts": None}


def _write_jsonl(path, *records):
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")


@pytest.fixture
def signal_client(client, tmp_path, monkeypatch):
    monkeypatch.setattr(paths_mod, "GRADING_DIR", tmp_path)
    monkeypatch.setattr(paths_mod, "JUDGEMENTS_PATH", tmp_path / "judgements_provisional.jsonl")
    return client


def test_signal_empty_when_no_verdicts(signal_client):
    r = signal_client.get("/api/grading/signal")
    assert r.status_code == 200
    body = r.json()
    assert body["n"] == 0 and body["n_topics"] == 0
    assert body["geometry_available"] is False


def test_signal_reports_coverage(signal_client, tmp_path):
    _write_jsonl(
        paths_mod.JUDGEMENTS_PATH,
        _v2("2026-06-01T10:00:00+00:00", "a" * 64, "live", topic="anxiety", tsid="72810"),
        _v2("2026-06-01T10:01:00+00:00", "b" * 64, "dead", topic="anxiety", tsid="72810"),
        _v2("2026-06-01T10:02:00+00:00", "c" * 64, "live", topic="anchor", tsid="60100"),
    )
    body = signal_client.get("/api/grading/signal").json()
    assert body["n"] == 3 and body["n_live"] == 2 and body["n_dead"] == 1
    assert body["n_topics"] == 2
    assert body["n_both_class_topics"] == 1     # only anxiety has both
    assert body["geometry_available"] is False


def test_signal_joins_geometry_when_present(signal_client, tmp_path):
    _write_jsonl(
        paths_mod.JUDGEMENTS_PATH,
        _v2("2026-06-01T10:00:00+00:00", "a" * 64, "live"),
        _v2("2026-06-01T10:01:00+00:00", "b" * 64, "dead"),
    )
    _write_jsonl(
        tmp_path / paths_mod.CHAIN_GEOMETRY_NAME,
        {"chain_signature": "a" * 64, "max_hop_cos": 0.8, "std_hop_cos": 0.2, "path_total_cos": 1.0},
        {"chain_signature": "b" * 64, "max_hop_cos": 0.3, "std_hop_cos": 0.1, "path_total_cos": 0.5},
    )
    body = signal_client.get("/api/grading/signal").json()
    assert body["geometry_available"] is True
    by_name = {f["name"]: f for f in body["geometry_features"]}
    assert by_name["max_hop_cos"]["within_topic_auc"] == 1.0
    assert by_name["max_hop_cos"]["n_pairs"] == 1


def test_signal_requires_secret_in_prod(client, monkeypatch, tmp_path):
    # Without GRADING_DEV the router's verify_secret dependency must gate it.
    monkeypatch.delenv("GRADING_DEV", raising=False)
    monkeypatch.setattr(paths_mod, "GRADING_DIR", tmp_path)
    monkeypatch.setattr(paths_mod, "JUDGEMENTS_PATH", tmp_path / "judgements_provisional.jsonl")
    from grading_sidecar.app import create_app
    from fastapi.testclient import TestClient
    guarded = TestClient(create_app())
    r = guarded.get("/api/grading/signal")
    assert r.status_code in (401, 403)
