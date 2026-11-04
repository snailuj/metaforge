"""Cross-site write defence (audit finding L2).

Caddy injects X-Grading-Secret on every request that passed basic auth and the
browser attaches the basic-auth credentials by itself, so the secret cannot tell
the site's own page from another site's. The guard therefore keys on Origin,
Sec-Fetch-Site and Content-Type of state-changing requests.
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import json
import pytest
from fastapi.testclient import TestClient
from grading_sidecar import paths as paths_mod
from grading_sidecar.app import ALLOWED_ORIGINS
from .test_judgements_endpoint import VALID as JUDGEMENT
from .test_regrade_endpoint import _v2 as _regrade_v2

SITE = "https://metaforge-next.julianit.me"
STATE_CHANGING = ["POST", "PUT", "PATCH", "DELETE"]


@pytest.fixture
def probe(client):
    """The shared client plus a counting handler on every state-changing method,
    so 'never reaches a handler' is observed rather than inferred from a status."""
    hits: list[str] = []

    @client.app.api_route("/__probe", methods=STATE_CHANGING)
    async def _probe():
        hits.append("hit")
        return {"ok": True}

    client.hits = hits
    return client


@pytest.fixture
def write_client(client, tmp_path, monkeypatch):
    monkeypatch.setattr(paths_mod, "GRADING_DIR", tmp_path)
    monkeypatch.setattr(paths_mod, "JUDGEMENTS_PATH", tmp_path / "judgements.jsonl")
    monkeypatch.setattr(paths_mod, "REGRADES_PATH", tmp_path / "regrades.jsonl")
    monkeypatch.setattr(paths_mod, "SENSE_LABELS_PATH", tmp_path / "sense_labels.jsonl")
    monkeypatch.setattr(paths_mod, "DESIGN_NOTES_PATH", tmp_path / "notes.md")
    return client


# Every existing POST route with a body that its handler accepts.
POST_ROUTES = [
    ("/api/grading/judgements", JUDGEMENT),
    ("/api/grading/regrade", _regrade_v2("2026-06-12T10:00:00+00:00", "a" * 64, "dead")),
    ("/api/grading/sense-check",
     {"role": "topic", "word": "apprehension", "snapped_synset_id": "1760",
      "verdict": "wrong", "intended_synset_id": "72797", "chain_signature": "a"}),
    ("/api/grading/design-notes", {"content": "a thought"}),
]


def test_allowlist_names_the_site_and_local_dev_only():
    assert ALLOWED_ORIGINS == {
        SITE, "http://localhost:5173", "http://127.0.0.1:5173"}


# Rule: no state-changing request from another origin reaches a handler,
# whatever its content type.
@pytest.mark.parametrize("method", STATE_CHANGING)
@pytest.mark.parametrize("content_type", [
    "application/json", "text/plain", "application/x-www-form-urlencoded",
    "multipart/form-data; boundary=x", None])
@pytest.mark.parametrize("origin", [
    "https://evil.example", "null", "http://metaforge-next.julianit.me",
    "https://metaforge-next.julianit.me.evil.example", SITE + ":8443"])
def test_foreign_origin_never_reaches_handler(probe, method, content_type, origin):
    headers = {"Origin": origin}
    if content_type:
        headers["Content-Type"] = content_type
    r = probe.request(method, "/__probe", content=b'{"a":1}', headers=headers)
    assert r.status_code == 403
    assert probe.hits == []


@pytest.mark.parametrize("method", STATE_CHANGING)
@pytest.mark.parametrize("site", ["cross-site", "same-site", "bogus", ""])
def test_non_same_origin_fetch_site_never_reaches_handler(probe, method, site):
    r = probe.request(method, "/__probe", content=b"{}",
                      headers={"Sec-Fetch-Site": site, "Content-Type": "application/json"})
    assert r.status_code == 403
    assert probe.hits == []


def test_fetch_site_wins_over_allowed_origin(probe):
    """A forged-looking pair: allowed Origin but the browser says cross-site."""
    r = probe.post("/__probe", json={}, headers={
        "Origin": SITE, "Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403 and probe.hits == []


# Rule: a state-changing request without a JSON content type never reaches a handler.
@pytest.mark.parametrize("method", STATE_CHANGING)
@pytest.mark.parametrize("content_type", [
    "text/plain", "application/x-www-form-urlencoded", "multipart/form-data; boundary=x",
    "application/jsonx", "text/json", "application/json-patch+json", "", None])
def test_non_json_content_type_never_reaches_handler(probe, method, content_type):
    headers = {"Content-Type": content_type} if content_type is not None else {}
    r = probe.request(method, "/__probe", content=b'{"a":1}', headers=headers)
    assert r.status_code == 415
    assert probe.hits == []


@pytest.mark.parametrize("content_type", [
    "application/json", "application/json; charset=utf-8", "Application/JSON",
    "application/json ;charset=UTF-8"])
def test_json_content_type_with_parameters_is_accepted(probe, content_type):
    r = probe.post("/__probe", content=b"{}", headers={"Content-Type": content_type})
    assert r.status_code == 200 and probe.hits == ["hit"]


@pytest.mark.parametrize("origin", sorted(ALLOWED_ORIGINS))
@pytest.mark.parametrize("fetch_site", ["same-origin", "none", None])
def test_allowed_origins_and_fetch_sites_pass(probe, origin, fetch_site):
    headers = {"Origin": origin}
    if fetch_site:
        headers["Sec-Fetch-Site"] = fetch_site
    r = probe.post("/__probe", json={}, headers=headers)
    assert r.status_code == 200 and probe.hits == ["hit"]


def test_no_origin_no_fetch_site_json_is_allowed(probe):
    """curl, tests and server-side tools send neither header."""
    r = probe.post("/__probe", json={})
    assert r.status_code == 200 and probe.hits == ["hit"]


# Rule: the site's own same-origin JSON POSTs still succeed, on every POST route.
@pytest.mark.parametrize("path,body", POST_ROUTES, ids=[p for p, _ in POST_ROUTES])
def test_same_origin_json_post_succeeds_on_every_route(write_client, path, body):
    r = write_client.post(path, json=body, headers={
        "Origin": SITE, "Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("path,body", POST_ROUTES, ids=[p for p, _ in POST_ROUTES])
def test_cross_site_post_to_every_route_writes_nothing(write_client, tmp_path, path, body):
    r = write_client.post(path, content=json.dumps(body), headers={
        "Origin": "https://evil.example", "Content-Type": "text/plain",
        "Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    assert list(tmp_path.iterdir()) == []


# Rule: reads are unaffected.
@pytest.mark.parametrize("headers", [
    {"Origin": "https://evil.example"}, {"Sec-Fetch-Site": "cross-site"}, {}])
def test_gets_are_unaffected(client, headers):
    assert client.get("/api/grading/healthz", headers=headers).status_code == 200


def test_refusal_is_logged_without_secrets(probe, caplog):
    caplog.set_level("WARNING")
    probe.post("/__probe", content=b"{}", headers={
        "Origin": "https://evil.example", "Content-Type": "text/plain",
        "X-Grading-Secret": "hunter2", "Authorization": "Basic c2VjcmV0"})
    text = caplog.text
    assert "POST" in text and "/__probe" in text and "https://evil.example" in text
    assert "hunter2" not in text and "c2VjcmV0" not in text
