from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

def test_healthz_returns_ok(client):
    r = client.get("/api/grading/healthz")
    assert r.status_code == 200
    assert r.json() == {"ok": True}

def test_host_header_allowlist_rejects_other_hosts(client):
    r = client.get("/api/grading/healthz", headers={"Host": "evil.example.com"})
    assert r.status_code == 421

def test_host_header_allowlist_accepts_metaforge_next(client):
    r = client.get("/api/grading/healthz", headers={"Host": "metaforge-next.julianit.me"})
    assert r.status_code == 200

def test_host_header_allowlist_accepts_localhost(client):
    r = client.get("/api/grading/healthz", headers={"Host": "localhost:53775"})
    assert r.status_code == 200

def test_host_allowlist_runs_before_cors(client):
    """Cross-origin request to an unknown Host returns 421 (host-allowlist
    outermost), NOT a CORS-mediated 400/403. Regression guard for middleware
    ordering."""
    r = client.get(
        "/api/grading/healthz",
        headers={"Host": "evil.example.com", "Origin": "http://evil.example.com"},
    )
    assert r.status_code == 421
