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
from grading_sidecar.routes import walk as walk_route

# The triage priors that drive ordering must NEVER leave the server (anchoring guard).
_PRIOR_KEYS = {"liveness", "bad_head", "leap", "weak_linkage"}


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
    # public contract: navigational fields + the full chain record for rendering
    assert {"chain_signature", "topic", "vehicle", "dwell_index", "dwell_n", "record"} <= set(e)
    assert e["record"]["chain_signature"] == e["chain_signature"]
    assert e["record"]["chain"][0]["head"] == "anger"


def test_walk_does_not_leak_triage_priors(walk_client, tmp_path):
    # The liveness score + structural flags drove the ORDERING but must not reach
    # the grader's browser — surfacing them would anchor a fresh judgement.
    _write_jsonl(tmp_path / "sonnet_chains_provisional_r2.jsonl", _chain("anger", "venom", "a" * 64))
    _write_jsonl(tmp_path / "triage_scores_r2.jsonl",
                 {"chain_signature": "a" * 64, "score": 9})
    _write_jsonl(tmp_path / "triage_structural.jsonl",
                 {"chain_signature": "a" * 64, "bad_head": True, "leap": False, "weak_linkage": True})
    e = walk_client.get("/api/grading/walk").json()["entries"][0]
    assert _PRIOR_KEYS.isdisjoint(e), f"triage priors leaked: {_PRIOR_KEYS & set(e)}"
    # ...and not smuggled inside the chain record either
    assert _PRIOR_KEYS.isdisjoint(e["record"])


def test_walk_skips_schema_incomplete_chain_records(walk_client, tmp_path):
    # valid JSON but missing chain_signature (generator schema drift / partial line)
    # must not 500 the whole walk — it is skipped, the good chain still served.
    f = tmp_path / "sonnet_chains_provisional_r2.jsonl"
    f.write_text(json.dumps(_chain("anger", "venom", "a" * 64)) + "\n"
                 + json.dumps({"topic": "fear", "vehicle": "shadow"}) + "\n")
    r = walk_client.get("/api/grading/walk")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert body["entries"][0]["chain_signature"] == "a" * 64


def test_load_liveness_later_snapshot_supersedes(walk_client, tmp_path):
    # the same signature triaged twice — the later (sorted-last) snapshot wins
    _write_jsonl(tmp_path / "triage_scores.jsonl", {"chain_signature": "a" * 64, "score": 2})
    _write_jsonl(tmp_path / "triage_scores_r2.jsonl", {"chain_signature": "a" * 64, "score": 9})
    assert walk_route._load_liveness()["a" * 64] == 9


def test_walk_steering_override_with_v1_and_v2_verdicts(walk_client, tmp_path):
    # NARROW flagged topic (small spread, exercises starved tag:bad_head) must beat
    # WIDE plain topic (wide spread) once live/dead are saturated — joined through
    # collected_labels_from_verdicts over a MIX of v1 (label) and v2 (axes) records.
    _write_jsonl(tmp_path / "sonnet_chains_provisional_r2.jsonl",
                 _chain("NARROW", "v1", "n1".ljust(64, "0")),
                 _chain("NARROW", "v2", "n2".ljust(64, "0")),
                 _chain("WIDE", "v3", "w1".ljust(64, "0")),
                 _chain("WIDE", "v4", "w2".ljust(64, "0")))
    _write_jsonl(tmp_path / "triage_scores_r2.jsonl",
                 {"chain_signature": "n1".ljust(64, "0"), "score": 6},
                 {"chain_signature": "n2".ljust(64, "0"), "score": 4},
                 {"chain_signature": "w1".ljust(64, "0"), "score": 9},
                 {"chain_signature": "w2".ljust(64, "0"), "score": 1})
    _write_jsonl(tmp_path / "triage_structural.jsonl",
                 {"chain_signature": "n2".ljust(64, "0"), "bad_head": True, "leap": False, "weak_linkage": False})
    v1 = [{"chain_signature": f"g{i}".ljust(64, "0"), "topic": "other", "label": "live"} for i in range(20)]
    v2 = [{"chain_signature": f"d{i}".ljust(64, "0"), "topic": "other",
           "linkage": "good", "metaphor": "dead", "tags": []} for i in range(20)]
    _write_jsonl(paths_mod.JUDGEMENTS_PATH, *(v1 + v2))
    body = walk_client.get("/api/grading/walk").json()
    assert body["entries"][0]["topic"] == "NARROW"


def test_walk_untriaged_chain_appears(walk_client, tmp_path):
    # a chain with no triage liveness still appears in the walk (mid-ranked — the
    # midpoint default is unit-tested in test_walk.assemble_paths; not on the wire).
    _write_jsonl(tmp_path / "sonnet_chains_provisional_r2.jsonl", _chain("anger", "venom", "a" * 64))
    body = walk_client.get("/api/grading/walk").json()
    assert body["count"] == 1
    assert body["entries"][0]["chain_signature"] == "a" * 64


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
