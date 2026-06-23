from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest
from grading_sidecar import paths as paths_mod

@pytest.fixture
def notes_client(client, tmp_path, monkeypatch):
    monkeypatch.setattr(paths_mod, "DESIGN_NOTES_PATH", tmp_path / "notes.md")
    return client

def test_get_design_notes_empty(notes_client):
    r = notes_client.get("/api/grading/design-notes")
    assert r.status_code == 200
    assert r.json() == {"content": ""}

def test_post_appends_timestamped_block(notes_client, tmp_path):
    r = notes_client.post("/api/grading/design-notes", json={"content": "first thought"})
    assert r.status_code == 200
    body = (tmp_path / "notes.md").read_text()
    assert "first thought" in body
    assert body.startswith("\n## ")  # timestamp header

def test_post_multiple_appends_preserves_history(notes_client, tmp_path):
    notes_client.post("/api/grading/design-notes", json={"content": "first"})
    notes_client.post("/api/grading/design-notes", json={"content": "second"})
    body = (tmp_path / "notes.md").read_text()
    assert "first" in body
    assert "second" in body
    assert body.count("## ") == 2

def test_post_rejects_empty_content(notes_client):
    r = notes_client.post("/api/grading/design-notes", json={"content": ""})
    assert r.status_code == 422

def test_post_rejects_oversized_content(notes_client):
    r = notes_client.post("/api/grading/design-notes", json={"content": "x" * 10001})
    assert r.status_code == 422

def test_get_after_post_returns_full_content(notes_client):
    notes_client.post("/api/grading/design-notes", json={"content": "alpha"})
    notes_client.post("/api/grading/design-notes", json={"content": "beta"})
    r = notes_client.get("/api/grading/design-notes")
    assert r.status_code == 200
    body = r.json()["content"]
    assert "alpha" in body and "beta" in body
