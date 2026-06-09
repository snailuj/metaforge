"""Tests for GET /api/grading/glosses — synset gloss/POS lookup."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import json
import pytest
from grading_sidecar import paths as paths_mod


def _write_jsonl(path, *records):
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")


@pytest.fixture
def gloss_client(client, tmp_path, monkeypatch):
    monkeypatch.setattr(paths_mod, "GRADING_DIR", tmp_path)
    return client


def test_glosses_empty_when_no_file(gloss_client):
    r = gloss_client.get("/api/grading/glosses")
    assert r.status_code == 200
    assert r.json() == {"glosses": {}}


def test_glosses_returns_pos_and_definition(gloss_client, tmp_path):
    _write_jsonl(
        tmp_path / paths_mod.CHAIN_GLOSSES_NAME,
        {"synset_id": "72810", "pos": "n", "definition": "a vague unpleasant emotion"},
        {"synset_id": "5", "pos": "s", "definition": "out of fashion"},
    )
    body = gloss_client.get("/api/grading/glosses").json()["glosses"]
    assert body["72810"] == {"pos": "n", "definition": "a vague unpleasant emotion"}
    assert body["5"]["pos"] == "s"
