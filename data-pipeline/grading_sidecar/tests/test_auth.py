from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from grading_sidecar.auth import verify_secret, load_secret

def _app_with_protected_route():
    app = FastAPI()
    @app.get("/protected", dependencies=[Depends(verify_secret)])
    def protected():
        return {"ok": True}
    return app

def test_missing_header_returns_401(monkeypatch, tmp_path):
    secret_file = tmp_path / "secret"
    secret_file.write_text("the-real-secret")
    monkeypatch.setenv("GRADING_SECRET_FILE", str(secret_file))
    monkeypatch.delenv("GRADING_DEV", raising=False)
    load_secret.cache_clear()  # functools.lru_cache reset between tests
    client = TestClient(_app_with_protected_route())
    r = client.get("/protected")
    assert r.status_code == 401

def test_wrong_header_returns_401(monkeypatch, tmp_path):
    secret_file = tmp_path / "secret"
    secret_file.write_text("the-real-secret")
    monkeypatch.setenv("GRADING_SECRET_FILE", str(secret_file))
    monkeypatch.delenv("GRADING_DEV", raising=False)
    load_secret.cache_clear()
    client = TestClient(_app_with_protected_route())
    r = client.get("/protected", headers={"X-Grading-Secret": "wrong"})
    assert r.status_code == 401

def test_correct_header_returns_200(monkeypatch, tmp_path):
    secret_file = tmp_path / "secret"
    secret_file.write_text("the-real-secret")
    monkeypatch.setenv("GRADING_SECRET_FILE", str(secret_file))
    monkeypatch.delenv("GRADING_DEV", raising=False)
    load_secret.cache_clear()
    client = TestClient(_app_with_protected_route())
    r = client.get("/protected", headers={"X-Grading-Secret": "the-real-secret"})
    assert r.status_code == 200

def test_dev_bypass_skips_check(monkeypatch):
    monkeypatch.setenv("GRADING_DEV", "1")
    load_secret.cache_clear()
    client = TestClient(_app_with_protected_route())
    r = client.get("/protected")  # no header
    assert r.status_code == 200

def test_load_secret_fails_on_missing_file(monkeypatch, tmp_path):
    monkeypatch.setenv("GRADING_SECRET_FILE", str(tmp_path / "nonexistent"))
    load_secret.cache_clear()
    with pytest.raises(SystemExit):
        load_secret()

def test_load_secret_fails_on_empty_file(monkeypatch, tmp_path):
    secret_file = tmp_path / "secret"
    secret_file.write_text("")
    monkeypatch.setenv("GRADING_SECRET_FILE", str(secret_file))
    load_secret.cache_clear()
    with pytest.raises(SystemExit):
        load_secret()
