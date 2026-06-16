"""Tests for the sense-check routes."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import json
import pytest
from grading_sidecar import paths as paths_mod


def _write(path, *records):
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")


@pytest.fixture
def sc_client(client, tmp_path, monkeypatch):
    monkeypatch.setattr(paths_mod, "GRADING_DIR", tmp_path)
    monkeypatch.setattr(paths_mod, "SENSE_LABELS_PATH",
                        tmp_path / "sense_labels_provisional.jsonl")
    monkeypatch.setattr(paths_mod, "JUDGEMENTS_PATH",
                        tmp_path / "judgements_provisional.jsonl")
    return client


def _chain(sig, topic, tsid, vehicle, vsid):
    return {"schema_version": "chain.v1", "topic": topic, "topic_synset_id": tsid,
            "vehicle": vehicle, "vehicle_synset_id": vsid, "proposer": "sonnet",
            "round": 1, "chain_signature": sig, "generated_at": "2026-06-01T00:00:00+00:00",
            "chain": [{"phrase": topic, "head": topic, "synset_id": tsid},
                      {"phrase": vehicle, "head": vehicle, "synset_id": vsid}]}


def test_sample_returns_enriched_items(sc_client, tmp_path):
    _write(tmp_path / "sonnet_chains_provisional_r1.jsonl",
           _chain("a", "longing", "72598", "drought", "104281"))
    _write(tmp_path / paths_mod.SENSE_FLAGS_NAME,
           {"role": "vehicle", "word": "drought", "synset_id": "104281",
            "verdict": "WRONG_SENSE"})
    _write(tmp_path / paths_mod.CHAIN_GLOSSES_NAME,
           {"synset_id": "104281", "pos": "n", "definition": "a dry spell"})
    _write(tmp_path / paths_mod.SENSE_CANDIDATES_NAME,
           {"lemma": "drought", "senses": [
               {"synset_id": "104281", "pos": "n", "gloss": "a dry spell", "tagcount": 3}]})
    body = sc_client.get("/api/grading/sense-check/sample?n_flagged=5&n_random=0&seed=1").json()
    assert body["count"] == 1
    it = body["items"][0]
    assert it["word"] == "drought" and it["snapped_gloss"] == "a dry spell"
    assert it["candidates"][0]["synset_id"] == "104281"
    assert it["context"]["chains"][0]["chain_signature"] == "a"


def test_sample_returns_empty_when_no_precompute_files(sc_client, tmp_path):
    """Degradation contract: all precompute files absent → 200 with count=0, items=[]."""
    # tmp_path has no files written — all loaders degrade to empty collections.
    body = sc_client.get("/api/grading/sense-check/sample?n_flagged=5&n_random=5&seed=1").json()
    assert body == {"count": 0, "items": []}


def test_post_label_lands_in_separate_file_not_judgements(sc_client, tmp_path):
    payload = {"role": "topic", "word": "apprehension", "snapped_synset_id": "1760",
               "verdict": "wrong", "intended_synset_id": "72797", "chain_signature": "a"}
    r = sc_client.post("/api/grading/sense-check", json=payload)
    assert r.status_code == 200
    assert (tmp_path / "sense_labels_provisional.jsonl").exists()
    assert not (tmp_path / "judgements_provisional.jsonl").exists()
    saved = json.loads((tmp_path / "sense_labels_provisional.jsonl").read_text().strip())
    assert saved["verdict"] == "wrong" and saved["schema_version"] == "sense_label.v1"
