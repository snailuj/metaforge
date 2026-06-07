"""Tests for GET /api/grading/walk — the signal-prioritised grading walk route.

The route is pure IO wiring over grading_sidecar.walk: it globs the chain rounds,
joins triage liveness (triage_scores*.jsonl) + structural flags
(triage_structural.jsonl), reads existing verdicts (to skip graded paths and to
steer topic order toward under-collected panel axes), and returns the walk
entries each carrying the full chain record for rendering.
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import json
import pytest
from grading_sidecar import paths as paths_mod


def _chain(topic, vehicle, sig):
    """A minimal raw chain record (the route reads raw JSON, no pydantic)."""
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
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")


@pytest.fixture
def walk_client(client, tmp_path, monkeypatch):
    monkeypatch.setattr(paths_mod, "GRADING_DIR", tmp_path)
    monkeypatch.setattr(paths_mod, "JUDGEMENTS_PATH", tmp_path / "judgements_provisional.jsonl")
    return client


def test_walk_empty_when_no_files(walk_client):
    r = walk_client.get("/api/grading/walk")
    assert r.status_code == 200
    assert r.json() == {"count": 0, "entries": []}


def test_walk_returns_entries_with_full_record(walk_client, tmp_path):
    _write_jsonl(tmp_path / "sonnet_chains_provisional_r2.jsonl",
                 _chain("anger", "venom", "a" * 64),
                 _chain("anger", "frost", "b" * 64))
    _write_jsonl(tmp_path / "triage_scores_r2.jsonl",
                 {"chain_signature": "a" * 64, "topic": "anger", "vehicle": "venom", "score": 8},
                 {"chain_signature": "b" * 64, "topic": "anger", "vehicle": "frost", "score": 2})
    _write_jsonl(tmp_path / "triage_structural.jsonl",
                 {"chain_signature": "a" * 64, "bad_head": False, "leap": False, "weak_linkage": False},
                 {"chain_signature": "b" * 64, "bad_head": False, "leap": False, "weak_linkage": False})
    r = walk_client.get("/api/grading/walk")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 2
    e = body["entries"][0]
    # walk fields + dwell position + the full chain record for rendering
    assert {"chain_signature", "topic", "vehicle", "liveness", "dwell_index", "dwell_n", "record"} <= set(e)
    assert e["record"]["chain_signature"] == e["chain_signature"]
    assert e["record"]["chain"][0]["head"] == "anger"


def test_walk_joins_liveness_and_structural(walk_client, tmp_path):
    _write_jsonl(tmp_path / "sonnet_chains_provisional_r2.jsonl", _chain("anger", "venom", "a" * 64))
    _write_jsonl(tmp_path / "triage_scores_r2.jsonl",
                 {"chain_signature": "a" * 64, "score": 9})
    _write_jsonl(tmp_path / "triage_structural.jsonl",
                 {"chain_signature": "a" * 64, "bad_head": True, "leap": False, "weak_linkage": True})
    body = walk_client.get("/api/grading/walk").json()
    e = body["entries"][0]
    assert e["liveness"] == 9
    assert e["bad_head"] is True and e["weak_linkage"] is True and e["leap"] is False


def test_walk_untriaged_chain_appears_midranked(walk_client, tmp_path):
    # a chain with no triage liveness still appears (defaults to the midpoint)
    _write_jsonl(tmp_path / "sonnet_chains_provisional_r2.jsonl", _chain("anger", "venom", "a" * 64))
    body = walk_client.get("/api/grading/walk").json()
    assert body["count"] == 1
    assert body["entries"][0]["liveness"] == 5


def test_walk_skips_graded_by_default(walk_client, tmp_path):
    _write_jsonl(tmp_path / "sonnet_chains_provisional_r2.jsonl",
                 _chain("anger", "venom", "a" * 64),
                 _chain("anger", "frost", "b" * 64))
    _write_jsonl(tmp_path / "triage_scores_r2.jsonl",
                 {"chain_signature": "a" * 64, "score": 8},
                 {"chain_signature": "b" * 64, "score": 2})
    _write_jsonl(paths_mod.JUDGEMENTS_PATH,
                 {"chain_signature": "a" * 64, "topic": "anger", "linkage": "good", "metaphor": "live"})
    sigs = {e["chain_signature"] for e in walk_client.get("/api/grading/walk").json()["entries"]}
    assert "a" * 64 not in sigs and "b" * 64 in sigs


def test_walk_ungraded_zero_includes_graded(walk_client, tmp_path):
    _write_jsonl(tmp_path / "sonnet_chains_provisional_r2.jsonl",
                 _chain("anger", "venom", "a" * 64),
                 _chain("anger", "frost", "b" * 64))
    _write_jsonl(paths_mod.JUDGEMENTS_PATH,
                 {"chain_signature": "a" * 64, "topic": "anger", "linkage": "good", "metaphor": "live"})
    sigs = {e["chain_signature"] for e in walk_client.get("/api/grading/walk?ungraded=0").json()["entries"]}
    assert "a" * 64 in sigs and "b" * 64 in sigs


def test_walk_steers_topic_order_by_label_coverage(walk_client, tmp_path):
    # Two flagged topics, equal spread. Existing verdicts saturate live/dead/leap but
    # never tag:bad_head -> the bad_head topic must surface first on the coverage gap.
    _write_jsonl(tmp_path / "sonnet_chains_provisional_r2.jsonl",
                 _chain("BADHEAD", "v1", "h1".ljust(64, "0")),
                 _chain("BADHEAD", "v2", "h2".ljust(64, "0")),
                 _chain("BADHEAD", "v3", "h3".ljust(64, "0")),
                 _chain("LEAP", "v4", "l1".ljust(64, "0")),
                 _chain("LEAP", "v5", "l2".ljust(64, "0")),
                 _chain("LEAP", "v6", "l3".ljust(64, "0")))
    _write_jsonl(tmp_path / "triage_scores_r2.jsonl",
                 {"chain_signature": "h1".ljust(64, "0"), "score": 8},
                 {"chain_signature": "h2".ljust(64, "0"), "score": 2},
                 {"chain_signature": "h3".ljust(64, "0"), "score": 5},
                 {"chain_signature": "l1".ljust(64, "0"), "score": 8},
                 {"chain_signature": "l2".ljust(64, "0"), "score": 2},
                 {"chain_signature": "l3".ljust(64, "0"), "score": 5})
    _write_jsonl(tmp_path / "triage_structural.jsonl",
                 {"chain_signature": "h3".ljust(64, "0"), "bad_head": True, "leap": False, "weak_linkage": False},
                 {"chain_signature": "l3".ljust(64, "0"), "bad_head": False, "leap": True, "weak_linkage": False})
    saturating = (
        [{"chain_signature": f"g{i}".ljust(64, "0"), "topic": "other",
          "linkage": "good", "metaphor": "live", "tags": ["leap"]} for i in range(20)]
        + [{"chain_signature": f"d{i}".ljust(64, "0"), "topic": "other",
            "linkage": "good", "metaphor": "dead", "tags": []} for i in range(20)]
    )
    _write_jsonl(paths_mod.JUDGEMENTS_PATH, *saturating)
    body = walk_client.get("/api/grading/walk").json()
    assert body["entries"][0]["topic"] == "BADHEAD"
