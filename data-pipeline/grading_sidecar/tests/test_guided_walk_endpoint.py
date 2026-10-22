"""Tests for GET /api/grading/guided-walk — the operator-prefilled guided walk.

Unlike the signal-prioritised walk (which orders chains by triage priors), the
guided walk serves an EXACT ordered candidate list written offline into
guided_walk_provisional.jsonl (chain_signature, order, cohort, judge_verdict,
batch). The route joins each candidate with its full chain record for rendering
and serves the latest batch by default. Crucially, the stored judge_verdict and
the eval/train cohort NEVER leave the server — surfacing them would anchor the
operator's blind grade, the whole point of a held-out eval.
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import json
import pytest
from grading_sidecar import paths as paths_mod

# Fields that pin the answer / the held-out split — must never reach the browser.
_SERVER_ONLY = {"judge_verdict", "cohort"}


def _chain(topic, vehicle, sig, cohort_file):
    return {
        "schema_version": "chain.v1",
        "topic": topic, "topic_synset_id": "1",
        "vehicle": vehicle, "vehicle_synset_id": "2",
        "proposer": "sonnet_v1", "round": 2,
        "chain": [
            {"phrase": topic, "head": topic, "synset_id": "1"},
            {"phrase": vehicle, "head": vehicle, "synset_id": "2"},
        ],
        "chain_signature": sig, "generated_at": "2026-06-06T03:14:00Z",
    }


def _write_jsonl(path, *records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")


def _cand(sig, order, batch, cohort="train", judge_verdict="live"):
    return {"chain_signature": sig, "order": order, "batch": batch,
            "cohort": cohort, "judge_verdict": judge_verdict}


@pytest.fixture
def guided_client(client, tmp_path, monkeypatch):
    monkeypatch.setattr(paths_mod, "GRADING_DIR", tmp_path)
    return client


def test_guided_empty_when_no_file(guided_client):
    r = guided_client.get("/api/grading/guided-walk")
    assert r.status_code == 200
    assert r.json() == {"count": 0, "batch": None, "entries": []}


def test_guided_returns_entries_in_prefilled_order_with_record(guided_client, tmp_path):
    # curated cohort chains
    _write_jsonl(tmp_path / "chain-topics_curated.jsonl",
                 _chain("anger", "venom", "a" * 64, "curated"),
                 _chain("grief", "anchor", "b" * 64, "curated"))
    # deliberately list b BEFORE a to prove `order` (not file order) drives it
    _write_jsonl(tmp_path / "guided_walk_provisional.jsonl",
                 _cand("a" * 64, 1, "r1"),
                 _cand("b" * 64, 0, "r1"))
    body = guided_client.get("/api/grading/guided-walk").json()
    assert body["count"] == 2
    assert body["batch"] == "r1"
    assert [e["chain_signature"] for e in body["entries"]] == ["b" * 64, "a" * 64]
    e = body["entries"][0]
    assert {"chain_signature", "topic", "vehicle", "record", "order"} <= set(e)
    assert e["record"]["chain"][0]["head"] == "grief"


def test_guided_never_leaks_judge_verdict_or_cohort(guided_client, tmp_path):
    _write_jsonl(tmp_path / "chain-topics_curated.jsonl",
                 _chain("anger", "venom", "a" * 64, "curated"))
    _write_jsonl(tmp_path / "guided_walk_provisional.jsonl",
                 _cand("a" * 64, 0, "r1", cohort="eval", judge_verdict="dead"))
    e = guided_client.get("/api/grading/guided-walk").json()["entries"][0]
    assert _SERVER_ONLY.isdisjoint(e), f"leaked: {_SERVER_ONLY & set(e)}"
    assert _SERVER_ONLY.isdisjoint(e["record"])


def test_guided_serves_latest_batch_by_default(guided_client, tmp_path):
    _write_jsonl(tmp_path / "chain-topics_curated.jsonl",
                 _chain("anger", "venom", "a" * 64, "curated"),
                 _chain("grief", "anchor", "b" * 64, "curated"))
    _write_jsonl(tmp_path / "guided_walk_provisional.jsonl",
                 _cand("a" * 64, 0, "2026-07-05-r1"),
                 _cand("b" * 64, 0, "2026-07-06-r2"))
    body = guided_client.get("/api/grading/guided-walk").json()
    assert body["batch"] == "2026-07-06-r2"
    assert [e["chain_signature"] for e in body["entries"]] == ["b" * 64]


def test_guided_batch_override(guided_client, tmp_path):
    _write_jsonl(tmp_path / "chain-topics_curated.jsonl",
                 _chain("anger", "venom", "a" * 64, "curated"),
                 _chain("grief", "anchor", "b" * 64, "curated"))
    _write_jsonl(tmp_path / "guided_walk_provisional.jsonl",
                 _cand("a" * 64, 0, "r1"),
                 _cand("b" * 64, 0, "r2"))
    body = guided_client.get("/api/grading/guided-walk?batch=r1").json()
    assert body["batch"] == "r1"
    assert [e["chain_signature"] for e in body["entries"]] == ["a" * 64]


def test_guided_resolves_stock_cohort_candidates(guided_client, tmp_path):
    # Fresh bootstrap candidates come from the broad `stock` corpus, which the
    # grading-view cohorts DON'T glob — the guided route must still resolve them.
    _write_jsonl(tmp_path / "stock" / "chain-topics_stock.jsonl",
                 _chain("dusk", "bruise", "c" * 64, "stock"))
    _write_jsonl(tmp_path / "guided_walk_provisional.jsonl", _cand("c" * 64, 0, "r1"))
    body = guided_client.get("/api/grading/guided-walk").json()
    assert body["count"] == 1
    assert body["entries"][0]["topic"] == "dusk"


def test_guided_drops_candidate_with_no_matching_chain(guided_client, tmp_path):
    _write_jsonl(tmp_path / "chain-topics_curated.jsonl",
                 _chain("anger", "venom", "a" * 64, "curated"))
    _write_jsonl(tmp_path / "guided_walk_provisional.jsonl",
                 _cand("a" * 64, 0, "r1"),
                 _cand("missing" + "0" * 57, 1, "r1"))
    body = guided_client.get("/api/grading/guided-walk").json()
    assert body["count"] == 1
    assert body["entries"][0]["chain_signature"] == "a" * 64
