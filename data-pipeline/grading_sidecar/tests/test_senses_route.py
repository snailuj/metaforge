"""Tests for GET /api/grading/senses?key=<canonical_phrase>.

Serves pre-computed noun sense inventories from a JSONL file so the grading
panel can display a sense fan without the sidecar touching the lexicon DB.
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import json
import pytest
from grading_sidecar import paths as paths_mod


def _write_jsonl(path: Path, *records):
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")


@pytest.fixture
def senses_client(client, tmp_path, monkeypatch):
    monkeypatch.setattr(paths_mod, "GRADING_DIR", tmp_path)
    return client, tmp_path


def _inventory_rows():
    return [
        {
            "key": "glance",
            "senses": [
                {"synset_id": "100", "sensenum": 1, "tagcount": 9,
                 "definition": "a brief look", "pos": "n"},
                {"synset_id": "102", "sensenum": 3, "tagcount": 0,
                 "definition": "a deflection", "pos": "n"},
            ],
        },
        {
            "key": "wound",
            "senses": [
                {"synset_id": "200", "sensenum": 1, "tagcount": 2,
                 "definition": "an open sore", "pos": "n"},
            ],
        },
    ]


def test_senses_returns_fan_for_known_key(senses_client):
    client, tmp_path = senses_client
    _write_jsonl(tmp_path / paths_mod.SENSE_INVENTORIES_NAME, *_inventory_rows())
    resp = client.get("/api/grading/senses?key=glance")
    assert resp.status_code == 200
    body = resp.json()
    assert body["key"] == "glance"
    assert len(body["senses"]) == 2
    assert body["senses"][0]["synset_id"] == "100"
    assert body["senses"][0]["definition"] == "a brief look"


def test_senses_returns_empty_for_unknown_key(senses_client):
    client, tmp_path = senses_client
    _write_jsonl(tmp_path / paths_mod.SENSE_INVENTORIES_NAME, *_inventory_rows())
    resp = client.get("/api/grading/senses?key=pressed_flower")
    assert resp.status_code == 200
    body = resp.json()
    assert body["key"] == "pressed_flower"
    assert body["senses"] == []


def test_senses_degrades_to_empty_when_file_missing(senses_client):
    """No 500 when the inventory file has not yet been built."""
    client, _ = senses_client
    # GRADING_DIR is tmp_path; no file written
    resp = client.get("/api/grading/senses?key=glance")
    assert resp.status_code == 200
    body = resp.json()
    assert body["senses"] == []
