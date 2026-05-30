# Metaphor Grading Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. The spec at `docs/superpowers/specs/2026-05-30-metaphor-grading-tool-design.md` is the authoritative source for all code details, semantics, and rationale — this plan references spec sections by name; do NOT diverge from the spec without operator approval.

**Goal:** Ship the Metaphor Grading Tool v1 — a single-user web UI integrated into the existing Metaforge thesaurus app as a grading mode, deployed to `metaforge-next.julianit.me` via path-scoped Caddy routing, persisting JSONL judgements + cross-session design notes to the repo with auto-commit, and supporting the active-learning bootstrap loop that iterates the Sonnet chain-generation prompt.

**Architecture:** Path-scoped Caddy routing on `metaforge-next.julianit.me` adds `/api/grading/healthz` (unauth'd probe) and `/api/grading/*` (basic-auth + secret-injection); other paths still route to the existing Go API on 8081. A new Python FastAPI sidecar on 127.0.0.1:53775 serves only `/api/grading/*` (API-only, no static files), persists JSONL via `fcntl.flock + fsync` to `data-pipeline/grading/`, and runs a 15-min auto-commit asyncio task. Frontend mode toggle baked into `mf-app`; probe-on-mount graceful-degrades on prod where the sidecar isn't reachable.

**Tech Stack:**
- **Backend:** Python 3.12, FastAPI, uvicorn, Pydantic v2, pytest, pytest-asyncio.
- **Frontend:** Lit + Vite + TypeScript, 3d-force-graph (already wired), vitest + happy-dom.
- **Infra:** Caddy 2 (existing), systemd (existing), Git (auto-commit subprocess).
- **Persistence:** JSONL + markdown, fcntl advisory locks.

**Branch:** `metaphor-graph/grading-tool` (new, off `metaphor-graph/enrich-stage-a`).

---

## Spec reference

The spec is the source of truth: `docs/superpowers/specs/2026-05-30-metaphor-grading-tool-design.md`. Every task below references a spec section by name. If you find ambiguity, **stop and ask** — do not improvise.

## File structure (created/modified by this plan)

**New (sidecar):**
- `data-pipeline/grading_sidecar/__init__.py`
- `data-pipeline/grading_sidecar/app.py` — FastAPI app + middleware
- `data-pipeline/grading_sidecar/auth.py` — `verify_secret` dependency
- `data-pipeline/grading_sidecar/persistence.py` — `append_jsonl`, `read_jsonl_skip_malformed`, fcntl lock helper
- `data-pipeline/grading_sidecar/models.py` — Pydantic models (`ChainRecord`, `JudgementRecord`, etc.) with `schema_version`
- `data-pipeline/grading_sidecar/paths.py` — canonical paths to grading files
- `data-pipeline/grading_sidecar/routes/__init__.py`
- `data-pipeline/grading_sidecar/routes/healthz.py`
- `data-pipeline/grading_sidecar/routes/topics.py`
- `data-pipeline/grading_sidecar/routes/chains.py`
- `data-pipeline/grading_sidecar/routes/judgements.py`
- `data-pipeline/grading_sidecar/routes/design_notes.py`
- `data-pipeline/grading_sidecar/routes/stats.py`
- `data-pipeline/grading_sidecar/routes/calibration.py`
- `data-pipeline/grading_sidecar/autocommit.py` — asyncio task
- `data-pipeline/grading_sidecar/main.py` — uvicorn entrypoint
- `data-pipeline/grading_sidecar/requirements.txt`
- `data-pipeline/grading_sidecar/tests/__init__.py`
- `data-pipeline/grading_sidecar/tests/conftest.py`
- `data-pipeline/grading_sidecar/tests/test_*.py` (one per module)
- `data-pipeline/grading_sidecar/README.md`

**New (data files, committed):**
- `data-pipeline/grading/README.md`
- `data-pipeline/grading/sonnet_chains_provisional_r1.jsonl` — populated by Task 13
- `data-pipeline/grading/judgements_provisional.jsonl` — empty at first; sidecar appends
- `data-pipeline/grading/design_notes_provisional.md` — empty at first

**New (frontend):**
- `web/src/types/grading.ts` — TypeScript types matching Pydantic models
- `web/src/api/grading-client.ts` — fetch wrappers for `/api/grading/*`
- `web/src/api/grading-client.test.ts`
- `web/src/components/mf-topic-picker.ts` — filterable combobox
- `web/src/components/mf-topic-picker.test.ts`
- `web/src/components/mf-grade-panel.ts` — verdict controls + keyboard shortcuts
- `web/src/components/mf-grade-panel.test.ts`
- `web/src/components/mf-design-notes.ts` — append-only notes
- `web/src/components/mf-design-notes.test.ts`
- `web/src/components/mf-error-banner.ts`
- `web/src/components/mf-error-banner.test.ts`
- `web/src/components/mf-mobile-notes-overlay.ts`
- `web/src/components/mf-mobile-notes-overlay.test.ts`

**Modified (frontend):**
- `web/src/components/mf-app.ts` — mode state, probe, toggle, error wiring
- `web/src/components/mf-app.test.ts` — extend
- `web/src/components/mf-force-graph.ts` — `mode` prop, grade-data input, dedup, click-to-select
- `web/src/components/mf-force-graph.test.ts` — extend
- `web/src/components/mf-search-bar.ts` — hide in grade mode

**New (scripts):**
- `data-pipeline/scripts/run_chain_spike.py` — promoted from `/tmp/stagea_spike/run_spike.py`, prompt emits `{phrase, head}`
- `data-pipeline/scripts/test_run_chain_spike.py`
- `data-pipeline/scripts/head_extraction_backfill.py` — round-1 backfill subagent driver
- `data-pipeline/scripts/build_next_round_prompt.py` — anti-example clustering + deterministic topic shuffle
- `data-pipeline/scripts/test_build_next_round_prompt.py`
- `data-pipeline/scripts/grading_diagnostics.py` — Wilson CI test
- `data-pipeline/scripts/test_grading_diagnostics.py`
- `data-pipeline/scripts/calibration_drift_check.py`
- `data-pipeline/scripts/test_calibration_drift_check.py`
- `data-pipeline/scripts/validate_grading_jsonl.py`
- `data-pipeline/scripts/test_validate_grading_jsonl.py`

**New (deploy):**
- `deploy/grading/deploy.sh`
- `deploy/grading/metaforge-grading.service` — systemd unit template
- `deploy/grading/metaforge-grading.env.example`

**Modified (deploy):**
- `deploy/caddy/metaforge-next.caddy.template` — patch with `/api/grading/*` handle blocks (or create if not yet repo-tracked; see Task 12)

**Modified (project docs):**
- `CLAUDE.md` — add grading subsystem to Quick Links + brief section
- `.gitignore` — add `data-pipeline/grading_sidecar/__pycache__/`, etc.

**Pre-commit hook:**
- `scripts/pre_commit_secret_scan.py` — high-entropy / common-secret scan over `data-pipeline/grading/`
- `.git/hooks/pre-commit` (instructions only — not committed)

---

## Pre-flight

Before starting Task 1, the worker must:

1. **Confirm working tree clean**: `git status` shows no uncommitted changes.
2. **Create branch**: `git checkout -b metaphor-graph/grading-tool metaphor-graph/enrich-stage-a`.
3. **Confirm Python venv exists**: `data-pipeline/.venv/bin/python --version` returns Python 3.12+.
4. **Confirm Node deps**: `cd web && npm install` runs clean.
5. **Confirm DB present** (for any tests that hit it): `ls data-pipeline/output/lexicon_v2.db`.
6. **Confirm caddy and systemctl on PATH** (Tasks 11-12 only).

If any step fails, **stop and report**. Do not improvise around missing prerequisites.

---

## Tasks

### Task 1: Sidecar package skeleton + FastAPI app + healthz + middleware

**Spec sections:** *Architecture*, *Sidecar (Python FastAPI)*, *Auth → Host-header allowlist + CORS*.

**Files:**
- Create: `data-pipeline/grading_sidecar/__init__.py` (empty)
- Create: `data-pipeline/grading_sidecar/requirements.txt`
- Create: `data-pipeline/grading_sidecar/paths.py`
- Create: `data-pipeline/grading_sidecar/app.py`
- Create: `data-pipeline/grading_sidecar/routes/__init__.py` (empty)
- Create: `data-pipeline/grading_sidecar/routes/healthz.py`
- Create: `data-pipeline/grading_sidecar/main.py`
- Create: `data-pipeline/grading_sidecar/tests/__init__.py` (empty)
- Create: `data-pipeline/grading_sidecar/tests/conftest.py`
- Create: `data-pipeline/grading_sidecar/tests/test_app.py`

- [ ] **Step 1: Add deps to requirements.txt**

```text
# data-pipeline/grading_sidecar/requirements.txt
fastapi>=0.110,<0.120
uvicorn[standard]>=0.27,<0.40
pydantic>=2.5,<3.0
pytest>=7.0
pytest-asyncio>=0.23
httpx>=0.27  # used by FastAPI TestClient
```

Run: `data-pipeline/.venv/bin/pip install -r data-pipeline/grading_sidecar/requirements.txt`

- [ ] **Step 2: Define canonical paths**

```python
# data-pipeline/grading_sidecar/paths.py
"""Canonical filesystem paths for grading data.

Resolved relative to the repo root at import time so tests can monkey-patch
GRADING_DIR for isolation.
"""
from __future__ import annotations
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GRADING_DIR = REPO_ROOT / "data-pipeline" / "grading"
CHAINS_GLOB = "sonnet_chains_provisional_r*.jsonl"
JUDGEMENTS_PATH = GRADING_DIR / "judgements_provisional.jsonl"
DESIGN_NOTES_PATH = GRADING_DIR / "design_notes_provisional.md"
```

- [ ] **Step 3: Write the failing test for healthz + middleware**

```python
# data-pipeline/grading_sidecar/tests/conftest.py
from __future__ import annotations
import os
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def client(monkeypatch):
    """TestClient with GRADING_DEV=1 to bypass secret check in tests."""
    monkeypatch.setenv("GRADING_DEV", "1")
    from grading_sidecar.app import create_app
    app = create_app()
    return TestClient(app)
```

```python
# data-pipeline/grading_sidecar/tests/test_app.py
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
```

Run: `data-pipeline/.venv/bin/python -m pytest data-pipeline/grading_sidecar/tests/test_app.py -v`
Expected: FAIL (ModuleNotFoundError: grading_sidecar).

- [ ] **Step 4: Implement healthz route**

```python
# data-pipeline/grading_sidecar/routes/healthz.py
from fastapi import APIRouter
router = APIRouter()

@router.get("/api/grading/healthz")
def healthz() -> dict:
    """Public probe — used by the frontend graceful-degrade check.
    No auth, no state leak."""
    return {"ok": True}
```

- [ ] **Step 5: Implement app + Host-allowlist + CORS**

```python
# data-pipeline/grading_sidecar/app.py
"""FastAPI app factory.

Host-header allowlist defends against DNS-rebinding on 127.0.0.1:53775
(see spec → Auth → Host-header allowlist + CORS). CORS is same-origin only.
"""
from __future__ import annotations
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from .routes import healthz

ALLOWED_HOSTS = {
    "metaforge-next.julianit.me",
    "localhost:53775",
    "localhost:5173",
    "127.0.0.1:53775",
    "testserver",  # FastAPI TestClient default
}

def create_app() -> FastAPI:
    app = FastAPI(title="Metaforge Grading Sidecar", version="0.1.0")

    @app.middleware("http")
    async def host_allowlist(request: Request, call_next):
        host = request.headers.get("host", "").lower()
        if host not in ALLOWED_HOSTS:
            return JSONResponse(
                {"error": "Misdirected request"}, status_code=421
            )
        return await call_next(request)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[],  # same-origin only
        allow_methods=["GET", "POST"],
        allow_headers=["X-Grading-Secret"],
    )

    app.include_router(healthz.router)
    return app
```

- [ ] **Step 6: Implement main.py uvicorn entrypoint**

```python
# data-pipeline/grading_sidecar/main.py
"""Uvicorn entrypoint for the grading sidecar.

Asserts GRADING_DEV is unset (the systemd unit forces this in prod;
local dev sets it explicitly).
"""
from __future__ import annotations
import os
import sys
import uvicorn
from .app import create_app

def main() -> int:
    # Prod-mode assertion: if systemd unit's Environment=GRADING_DEV= is empty,
    # this passes. If a dev shell accidentally inherits GRADING_DEV=1 into prod,
    # systemd should have overridden it — but assert anyway for clarity.
    if os.environ.get("GRADING_DEV") == "1" and os.environ.get("METAFORGE_GRADING_DEV_OK") != "1":
        # In dev, the runner sets METAFORGE_GRADING_DEV_OK=1 to acknowledge.
        print("REFUSING: GRADING_DEV=1 without METAFORGE_GRADING_DEV_OK=1 — prod-mode assertion",
              file=sys.stderr)
        return 1
    app = create_app()
    uvicorn.run(app, host="127.0.0.1", port=53775, log_config=None)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 7: Run tests, expect GREEN**

Run: `data-pipeline/.venv/bin/python -m pytest data-pipeline/grading_sidecar/tests/test_app.py -v`
Expected: 4 passed.

- [ ] **Step 8: Commit**

```bash
git add data-pipeline/grading_sidecar/
git commit -m "feat(grading-sidecar): FastAPI skeleton + healthz + host allowlist"
```

---

### Task 2: Auth dependency (X-Grading-Secret, fail-closed, hmac.compare_digest)

**Spec sections:** *Auth → Layer 2 — Sidecar shared-secret header*, *Auth → Dev-mode bypass*.

**Files:**
- Create: `data-pipeline/grading_sidecar/auth.py`
- Modify: `data-pipeline/grading_sidecar/app.py` (wire auth as global dep)
- Create: `data-pipeline/grading_sidecar/tests/test_auth.py`

- [ ] **Step 1: Write failing tests**

```python
# data-pipeline/grading_sidecar/tests/test_auth.py
from __future__ import annotations
import os
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
    client = TestClient(_app_with_protected_route())
    r = client.get("/protected")
    assert r.status_code == 401

def test_wrong_header_returns_401(monkeypatch, tmp_path):
    secret_file = tmp_path / "secret"
    secret_file.write_text("the-real-secret")
    monkeypatch.setenv("GRADING_SECRET_FILE", str(secret_file))
    monkeypatch.delenv("GRADING_DEV", raising=False)
    client = TestClient(_app_with_protected_route())
    r = client.get("/protected", headers={"X-Grading-Secret": "wrong"})
    assert r.status_code == 401

def test_correct_header_returns_200(monkeypatch, tmp_path):
    secret_file = tmp_path / "secret"
    secret_file.write_text("the-real-secret")
    monkeypatch.setenv("GRADING_SECRET_FILE", str(secret_file))
    monkeypatch.delenv("GRADING_DEV", raising=False)
    client = TestClient(_app_with_protected_route())
    r = client.get("/protected", headers={"X-Grading-Secret": "the-real-secret"})
    assert r.status_code == 200

def test_dev_bypass_skips_check(monkeypatch):
    monkeypatch.setenv("GRADING_DEV", "1")
    client = TestClient(_app_with_protected_route())
    r = client.get("/protected")  # no header
    assert r.status_code == 200

def test_load_secret_fails_on_missing_file(monkeypatch, tmp_path):
    monkeypatch.setenv("GRADING_SECRET_FILE", str(tmp_path / "nonexistent"))
    with pytest.raises(SystemExit):
        load_secret()

def test_load_secret_fails_on_empty_file(monkeypatch, tmp_path):
    secret_file = tmp_path / "secret"
    secret_file.write_text("")
    monkeypatch.setenv("GRADING_SECRET_FILE", str(secret_file))
    with pytest.raises(SystemExit):
        load_secret()
```

Run: `data-pipeline/.venv/bin/python -m pytest data-pipeline/grading_sidecar/tests/test_auth.py -v`
Expected: FAIL (ImportError for `grading_sidecar.auth`).

- [ ] **Step 2: Implement auth module**

```python
# data-pipeline/grading_sidecar/auth.py
"""Sidecar auth dependency.

Reads GRADING_SECRET from the file pointed to by GRADING_SECRET_FILE env
var (default: /etc/metaforge/grading_secret) at first call, then caches.
hmac.compare_digest for constant-time comparison.

GRADING_DEV=1 bypasses the check (dev only — the production systemd unit
sets Environment=GRADING_DEV= and asserts via main.py).
"""
from __future__ import annotations
import functools
import hmac
import os
import sys
from pathlib import Path
from fastapi import Header, HTTPException

DEFAULT_SECRET_FILE = "/etc/metaforge/grading_secret"

@functools.lru_cache(maxsize=1)
def load_secret() -> str:
    path = Path(os.environ.get("GRADING_SECRET_FILE", DEFAULT_SECRET_FILE))
    if not path.exists():
        print(f"FATAL: GRADING_SECRET file missing: {path}", file=sys.stderr)
        raise SystemExit(1)
    secret = path.read_text().strip()
    if not secret:
        print(f"FATAL: GRADING_SECRET file is empty: {path}", file=sys.stderr)
        raise SystemExit(1)
    return secret

def verify_secret(x_grading_secret: str = Header(default="")) -> None:
    if os.environ.get("GRADING_DEV") == "1":
        return
    expected = load_secret()
    if not hmac.compare_digest(x_grading_secret, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")
```

- [ ] **Step 3: Wire as default dep on protected routes (done per-route in later tasks; nothing to change in app.py yet — healthz stays unauth'd)**

- [ ] **Step 4: Run tests, expect GREEN**

Run: `data-pipeline/.venv/bin/python -m pytest data-pipeline/grading_sidecar/tests/test_auth.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add data-pipeline/grading_sidecar/auth.py data-pipeline/grading_sidecar/tests/test_auth.py
git commit -m "feat(grading-sidecar): X-Grading-Secret auth dep (constant-time, fail-closed)"
```

---

### Task 3: Persistence module (fcntl-locked append, malformed-line-skip reader, UTF-8 NFC)

**Spec sections:** *Sidecar → Persistence — corrected atomicity*, *Data shapes → UTF-8 normalisation*.

**Files:**
- Create: `data-pipeline/grading_sidecar/persistence.py`
- Create: `data-pipeline/grading_sidecar/tests/test_persistence.py`

- [ ] **Step 1: Write failing tests**

```python
# data-pipeline/grading_sidecar/tests/test_persistence.py
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path
import pytest
from grading_sidecar.persistence import append_jsonl, read_jsonl_skip_malformed

def test_append_writes_single_line(tmp_path):
    f = tmp_path / "out.jsonl"
    append_jsonl(f, {"a": 1, "b": "x"})
    assert f.read_text() == '{"a": 1, "b": "x"}\n'

def test_append_is_additive(tmp_path):
    f = tmp_path / "out.jsonl"
    append_jsonl(f, {"a": 1})
    append_jsonl(f, {"a": 2})
    lines = f.read_text().splitlines()
    assert [json.loads(l) for l in lines] == [{"a": 1}, {"a": 2}]

def test_append_nfc_normalises_unicode(tmp_path):
    f = tmp_path / "out.jsonl"
    # 'café' decomposed (NFD) vs composed (NFC) — append must normalise
    decomposed = "café"  # 'e' + combining acute
    composed = "café"     # precomposed 'é'
    append_jsonl(f, {"word": decomposed})
    line = f.read_text().splitlines()[0]
    rec = json.loads(line)
    assert rec["word"] == composed

def test_read_skips_malformed_lines(tmp_path):
    f = tmp_path / "in.jsonl"
    f.write_text('{"a": 1}\nNOT JSON\n{"a": 2}\n')
    records, skipped = read_jsonl_skip_malformed(f)
    assert records == [{"a": 1}, {"a": 2}]
    assert skipped == 1

def test_read_missing_file_returns_empty(tmp_path):
    records, skipped = read_jsonl_skip_malformed(tmp_path / "missing.jsonl")
    assert records == []
    assert skipped == 0

def test_concurrent_append_no_corruption(tmp_path):
    """Spawn 4 subprocesses each appending 25 records; verify all 100 present, no truncation."""
    f = tmp_path / "out.jsonl"
    script = tmp_path / "writer.py"
    script.write_text(f'''
import sys, json
sys.path.insert(0, {str(Path(__file__).resolve().parent.parent.parent)!r})
from grading_sidecar.persistence import append_jsonl
from pathlib import Path
worker = int(sys.argv[1])
for i in range(25):
    append_jsonl(Path({str(f)!r}), {{"worker": worker, "i": i}})
''')
    procs = [subprocess.Popen([sys.executable, str(script), str(w)]) for w in range(4)]
    for p in procs:
        p.wait()
        assert p.returncode == 0
    records, skipped = read_jsonl_skip_malformed(f)
    assert len(records) == 100
    assert skipped == 0
```

Run from repo root: `data-pipeline/.venv/bin/python -m pytest data-pipeline/grading_sidecar/tests/test_persistence.py -v`
Expected: FAIL (ImportError).

- [ ] **Step 2: Implement persistence module per spec section "Persistence — corrected atomicity"**

```python
# data-pipeline/grading_sidecar/persistence.py
"""Append-only JSONL persistence with fcntl.flock + fsync.

See spec section "Sidecar → Persistence — corrected atomicity" for rationale:
the .tmp+rename pattern is for full-file replacement, NOT append. We use
O_APPEND + advisory fcntl.flock (kernel releases on crash) + fsync.

UTF-8 NFC-normalised per spec section "Data shapes → UTF-8 normalisation".
"""
from __future__ import annotations
import fcntl
import json
import logging
import os
import unicodedata
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

def _nfc(obj: Any) -> Any:
    if isinstance(obj, str):
        return unicodedata.normalize("NFC", obj)
    if isinstance(obj, dict):
        return {k: _nfc(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_nfc(x) for x in obj]
    return obj

def append_jsonl(path: Path, record: dict) -> None:
    """Atomic append of one JSONL line. Safe across concurrent writers
    via fcntl.flock; safe across crashes (advisory lock auto-released).
    fsync ensures durability before return."""
    line = json.dumps(_nfc(record), ensure_ascii=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)

def read_jsonl_skip_malformed(path: Path) -> tuple[list[dict], int]:
    """Return (records, skipped_count). Missing file → ([], 0).
    Malformed lines logged at WARNING and skipped, not raised."""
    if not path.exists():
        return [], 0
    records: list[dict] = []
    skipped = 0
    with open(path, "r", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_SH)
        try:
            for i, raw in enumerate(f, 1):
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    records.append(json.loads(raw))
                except json.JSONDecodeError as exc:
                    log.warning("malformed JSONL line %d in %s: %s", i, path, exc)
                    skipped += 1
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    return records, skipped
```

- [ ] **Step 3: Run tests, expect GREEN**

Run: `data-pipeline/.venv/bin/python -m pytest data-pipeline/grading_sidecar/tests/test_persistence.py -v`
Expected: 6 passed.

- [ ] **Step 4: Commit**

```bash
git add data-pipeline/grading_sidecar/persistence.py data-pipeline/grading_sidecar/tests/test_persistence.py
git commit -m "feat(grading-sidecar): fcntl-locked JSONL append + malformed-line skip + NFC"
```

---

### Task 4: Pydantic models with schema_version, chain_signature, label/confidence enums

**Spec sections:** *Data shapes → Chain record*, *Data shapes → Judgement record*.

**Files:**
- Create: `data-pipeline/grading_sidecar/models.py`
- Create: `data-pipeline/grading_sidecar/tests/test_models.py`

- [ ] **Step 1: Write failing tests**

```python
# data-pipeline/grading_sidecar/tests/test_models.py
from __future__ import annotations
import pytest
from grading_sidecar.models import (
    ChainRecord, ChainStep, JudgementRecord, DesignNotePost,
    compute_chain_signature, normalise_phrase,
)

def test_chain_step_required_fields():
    s = ChainStep(phrase="anger", head="anger", synset_id="12345")
    assert s.phrase == "anger"

def test_chain_step_nullable_synset():
    s = ChainStep(phrase="tail meeting mouth", head="tail", synset_id=None)
    assert s.synset_id is None

def test_chain_record_validates_schema_version():
    with pytest.raises(ValueError):
        ChainRecord(
            schema_version="chain.v999",
            topic="anger", topic_synset_id="12345",
            vehicle="venom", vehicle_synset_id="67890",
            proposer="sonnet_v1", round=1,
            chain=[ChainStep(phrase="anger", head="anger", synset_id="12345"),
                   ChainStep(phrase="venom", head="venom", synset_id="67890")],
            chain_signature="x" * 64,
            generated_at="2026-05-30T03:14:00Z",
        )

def test_chain_record_endpoint_canonicalisation():
    """chain[0]/chain[-1] MUST match top-level topic/vehicle fields."""
    with pytest.raises(ValueError, match="endpoint"):
        ChainRecord(
            schema_version="chain.v1",
            topic="anger", topic_synset_id="12345",
            vehicle="venom", vehicle_synset_id="67890",
            proposer="sonnet_v1", round=1,
            chain=[
                ChainStep(phrase="WRONG", head="WRONG", synset_id="99999"),
                ChainStep(phrase="venom", head="venom", synset_id="67890"),
            ],
            chain_signature="x" * 64,
            generated_at="2026-05-30T03:14:00Z",
        )

def test_judgement_record_label_enum():
    with pytest.raises(ValueError):
        JudgementRecord(
            schema_version="judgement.v1",
            ts="2026-05-30T07:14:00Z", judged_by="julian", round=1,
            topic="anger", topic_synset_id="12345",
            vehicle="venom", vehicle_synset_id="67890",
            proposer="sonnet_v1", chain_signature="x" * 64,
            label="bogus", confidence="high",
        )

def test_judgement_record_confidence_enum():
    with pytest.raises(ValueError):
        JudgementRecord(
            schema_version="judgement.v1",
            ts="2026-05-30T07:14:00Z", judged_by="julian", round=1,
            topic="anger", topic_synset_id="12345",
            vehicle="venom", vehicle_synset_id="67890",
            proposer="sonnet_v1", chain_signature="x" * 64,
            label="live", confidence="enthusiastic",
        )

def test_judgement_notes_max_length():
    with pytest.raises(ValueError):
        JudgementRecord(
            schema_version="judgement.v1",
            ts="2026-05-30T07:14:00Z", judged_by="julian", round=1,
            topic="anger", topic_synset_id="12345",
            vehicle="venom", vehicle_synset_id="67890",
            proposer="sonnet_v1", chain_signature="x" * 64,
            label="bad_path", confidence="high",
            notes="x" * 1001,
        )

def test_compute_chain_signature_stable_across_case_and_whitespace():
    s1 = compute_chain_signature("sonnet_v1", ["Anger", " hostility ", "venom"])
    s2 = compute_chain_signature("sonnet_v1", ["anger", "hostility", "venom"])
    assert s1 == s2
    assert len(s1) == 64

def test_compute_chain_signature_changes_on_proposer():
    s1 = compute_chain_signature("sonnet_v1", ["anger", "venom"])
    s2 = compute_chain_signature("cascade_v1", ["anger", "venom"])
    assert s1 != s2

def test_normalise_phrase_strips_and_lowers_and_nfc():
    assert normalise_phrase("  Café  ") == "café"
```

Run: `data-pipeline/.venv/bin/python -m pytest data-pipeline/grading_sidecar/tests/test_models.py -v`
Expected: FAIL (ImportError).

- [ ] **Step 2: Implement models**

```python
# data-pipeline/grading_sidecar/models.py
"""Pydantic models matching the JSONL schemas defined in
docs/superpowers/specs/2026-05-30-metaphor-grading-tool-design.md

Section: "Data shapes → Chain record" / "Judgement record" / "Design-note block".
"""
from __future__ import annotations
import hashlib
import unicodedata
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator, model_validator

ChainSchemaVersion = Literal["chain.v1"]
JudgementSchemaVersion = Literal["judgement.v1"]
Label = Literal["live", "dead", "bad_path", "irrelevant"]
Confidence = Literal["high", "med", "low"]

def normalise_phrase(s: str) -> str:
    return unicodedata.normalize("NFC", s).strip().lower()

def compute_chain_signature(proposer: str, phrases: list[str]) -> str:
    """sha256(":".join([proposer] + [normalise(phrase) for phrase in phrases]))
    Stable across snap drift / head re-extraction (phrase-based, not synset-based)."""
    payload = ":".join([proposer] + [normalise_phrase(p) for p in phrases])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

class ChainStep(BaseModel):
    phrase: str = Field(min_length=1)
    head: str = Field(min_length=1)
    synset_id: Optional[str] = None

class ChainRecord(BaseModel):
    schema_version: ChainSchemaVersion
    topic: str
    topic_synset_id: str
    vehicle: str
    vehicle_synset_id: str
    proposer: str
    round: int = Field(ge=1)
    chain: list[ChainStep] = Field(min_length=2)
    chain_signature: str = Field(pattern=r"^[0-9a-f]{64}$")
    generated_at: str  # ISO-8601 UTC

    @model_validator(mode="after")
    def _endpoint_canonicalisation(self) -> "ChainRecord":
        if (self.chain[0].phrase != self.topic
            or self.chain[0].head != self.topic
            or self.chain[0].synset_id != self.topic_synset_id):
            raise ValueError(
                "endpoint canonicalisation: chain[0] must equal topic/topic_synset_id"
            )
        if (self.chain[-1].phrase != self.vehicle
            or self.chain[-1].head != self.vehicle
            or self.chain[-1].synset_id != self.vehicle_synset_id):
            raise ValueError(
                "endpoint canonicalisation: chain[-1] must equal vehicle/vehicle_synset_id"
            )
        return self

class JudgementRecord(BaseModel):
    schema_version: JudgementSchemaVersion
    ts: str
    judged_by: str
    round: int = Field(ge=1)
    topic: str
    topic_synset_id: str
    vehicle: str
    vehicle_synset_id: str
    proposer: str
    chain_signature: str = Field(pattern=r"^[0-9a-f]{64}$")
    label: Label
    confidence: Confidence = "high"
    notes: str = Field(default="", max_length=1000)
    supersedes_ts: Optional[str] = None

class DesignNotePost(BaseModel):
    content: str = Field(min_length=1, max_length=10000)
```

- [ ] **Step 3: Run tests, expect GREEN**

Run: `data-pipeline/.venv/bin/python -m pytest data-pipeline/grading_sidecar/tests/test_models.py -v`
Expected: 9 passed (with proper attention to the canonicalisation error message in `test_chain_record_endpoint_canonicalisation`).

- [ ] **Step 4: Commit**

```bash
git add data-pipeline/grading_sidecar/models.py data-pipeline/grading_sidecar/tests/test_models.py
git commit -m "feat(grading-sidecar): Pydantic models with schema_version + chain_signature"
```

---

### Task 5: /api/grading/judgements GET + POST

**Spec sections:** *Sidecar → Endpoints*, *Data shapes → Judgement record*.

**Files:**
- Create: `data-pipeline/grading_sidecar/routes/judgements.py`
- Modify: `data-pipeline/grading_sidecar/app.py` (include router)
- Create: `data-pipeline/grading_sidecar/tests/test_judgements_endpoint.py`

- [ ] **Step 1: Write failing tests**

```python
# data-pipeline/grading_sidecar/tests/test_judgements_endpoint.py
from __future__ import annotations
import json
import pytest
from grading_sidecar import paths as paths_mod

@pytest.fixture
def judgements_client(client, tmp_path, monkeypatch):
    monkeypatch.setattr(paths_mod, "JUDGEMENTS_PATH", tmp_path / "j.jsonl")
    return client

VALID = {
    "schema_version": "judgement.v1",
    "ts": "2026-05-30T07:14:00Z",
    "judged_by": "julian", "round": 1,
    "topic": "anger", "topic_synset_id": "12345",
    "vehicle": "venom", "vehicle_synset_id": "67890",
    "proposer": "sonnet_v1",
    "chain_signature": "a" * 64,
    "label": "live", "confidence": "high",
    "notes": "",
}

def test_post_judgement_appends_and_returns(judgements_client):
    r = judgements_client.post("/api/grading/judgements", json=VALID)
    assert r.status_code == 200
    assert r.json()["chain_signature"] == "a" * 64

def test_post_judgement_persists_to_disk(judgements_client, tmp_path):
    judgements_client.post("/api/grading/judgements", json=VALID)
    lines = (paths_mod.JUDGEMENTS_PATH).read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["topic"] == "anger"

def test_post_judgement_rejects_bad_label(judgements_client):
    bad = {**VALID, "label": "bogus"}
    r = judgements_client.post("/api/grading/judgements", json=bad)
    assert r.status_code == 422

def test_post_judgement_rejects_oversized_notes(judgements_client):
    bad = {**VALID, "notes": "x" * 1001}
    r = judgements_client.post("/api/grading/judgements", json=bad)
    assert r.status_code == 422

def test_get_judgements_returns_appended(judgements_client):
    judgements_client.post("/api/grading/judgements", json=VALID)
    r = judgements_client.get("/api/grading/judgements")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert body["records"][0]["topic"] == "anger"

def test_get_judgements_topic_filter(judgements_client):
    judgements_client.post("/api/grading/judgements", json={**VALID, "topic": "anger"})
    judgements_client.post("/api/grading/judgements", json={**VALID, "topic": "joy"})
    r = judgements_client.get("/api/grading/judgements?topic=anger")
    assert r.status_code == 200
    assert r.json()["count"] == 1

def test_get_judgements_empty_when_no_file(judgements_client):
    r = judgements_client.get("/api/grading/judgements")
    assert r.status_code == 200
    assert r.json()["count"] == 0
```

Run: `data-pipeline/.venv/bin/python -m pytest data-pipeline/grading_sidecar/tests/test_judgements_endpoint.py -v`
Expected: FAIL (no router yet).

- [ ] **Step 2: Implement route**

```python
# data-pipeline/grading_sidecar/routes/judgements.py
from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, Query
from ..auth import verify_secret
from ..models import JudgementRecord
from ..persistence import append_jsonl, read_jsonl_skip_malformed
from .. import paths as paths_mod

router = APIRouter(dependencies=[Depends(verify_secret)])

@router.post("/api/grading/judgements")
def post_judgement(record: JudgementRecord) -> dict:
    append_jsonl(paths_mod.JUDGEMENTS_PATH, record.model_dump(mode="json"))
    return record.model_dump(mode="json")

@router.get("/api/grading/judgements")
def get_judgements(topic: Optional[str] = Query(default=None)) -> dict:
    records, skipped = read_jsonl_skip_malformed(paths_mod.JUDGEMENTS_PATH)
    if topic is not None:
        records = [r for r in records if r.get("topic") == topic]
    return {"count": len(records), "skipped_malformed": skipped, "records": records}
```

- [ ] **Step 3: Register router in app.py**

Modify `data-pipeline/grading_sidecar/app.py` — add to `create_app`:
```python
from .routes import judgements
app.include_router(judgements.router)
```

- [ ] **Step 4: Run tests, expect GREEN**

Run: `data-pipeline/.venv/bin/python -m pytest data-pipeline/grading_sidecar/tests/test_judgements_endpoint.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add data-pipeline/grading_sidecar/routes/judgements.py \
        data-pipeline/grading_sidecar/app.py \
        data-pipeline/grading_sidecar/tests/test_judgements_endpoint.py
git commit -m "feat(grading-sidecar): /api/grading/judgements GET + POST"
```

---

### Task 6: /api/grading/chains GET (unions round files, topic filter, skips malformed)

**Spec sections:** *Sidecar → Endpoints*, *Bootstrap loop → Round mechanics*.

**Files:**
- Create: `data-pipeline/grading_sidecar/routes/chains.py`
- Modify: `data-pipeline/grading_sidecar/app.py` (include router)
- Create: `data-pipeline/grading_sidecar/tests/test_chains_endpoint.py`

- [ ] **Step 1: Write failing tests**

```python
# data-pipeline/grading_sidecar/tests/test_chains_endpoint.py
from __future__ import annotations
import json
import pytest
from grading_sidecar import paths as paths_mod

VALID_CHAIN_BASE = {
    "schema_version": "chain.v1",
    "topic": "anger", "topic_synset_id": "12345",
    "vehicle": "venom", "vehicle_synset_id": "67890",
    "proposer": "sonnet_v1", "round": 1,
    "chain": [
        {"phrase": "anger", "head": "anger", "synset_id": "12345"},
        {"phrase": "hostility", "head": "hostility", "synset_id": "54321"},
        {"phrase": "venom", "head": "venom", "synset_id": "67890"},
    ],
    "chain_signature": "a" * 64,
    "generated_at": "2026-05-30T03:14:00Z",
}

@pytest.fixture
def chains_client(client, tmp_path, monkeypatch):
    monkeypatch.setattr(paths_mod, "GRADING_DIR", tmp_path)
    return client

def _write_round(tmp_path, round_num, *records):
    f = tmp_path / f"sonnet_chains_provisional_r{round_num}.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in records) + "\n")

def test_get_chains_unions_multiple_round_files(chains_client, tmp_path):
    _write_round(tmp_path, 1, VALID_CHAIN_BASE)
    _write_round(tmp_path, 2, {**VALID_CHAIN_BASE, "round": 2, "chain_signature": "b"*64})
    r = chains_client.get("/api/grading/chains")
    assert r.status_code == 200
    assert r.json()["count"] == 2

def test_get_chains_topic_filter(chains_client, tmp_path):
    _write_round(tmp_path, 1,
        VALID_CHAIN_BASE,
        {**VALID_CHAIN_BASE,
         "topic": "joy", "topic_synset_id": "11111",
         "chain": [
            {"phrase": "joy", "head": "joy", "synset_id": "11111"},
            {"phrase": "venom", "head": "venom", "synset_id": "67890"},
         ],
         "chain_signature": "c"*64,
        },
    )
    r = chains_client.get("/api/grading/chains?topic=anger")
    assert r.status_code == 200
    assert r.json()["count"] == 1

def test_get_chains_skips_malformed_lines(chains_client, tmp_path):
    f = tmp_path / "sonnet_chains_provisional_r1.jsonl"
    f.write_text(json.dumps(VALID_CHAIN_BASE) + "\nNOT JSON\n")
    r = chains_client.get("/api/grading/chains")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert body["skipped_malformed"] == 1

def test_get_chains_empty_when_no_files(chains_client):
    r = chains_client.get("/api/grading/chains")
    assert r.status_code == 200
    assert r.json() == {"count": 0, "skipped_malformed": 0, "records": []}
```

- [ ] **Step 2: Implement route**

```python
# data-pipeline/grading_sidecar/routes/chains.py
from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, Query
from ..auth import verify_secret
from ..persistence import read_jsonl_skip_malformed
from .. import paths as paths_mod

router = APIRouter(dependencies=[Depends(verify_secret)])

@router.get("/api/grading/chains")
def get_chains(topic: Optional[str] = Query(default=None)) -> dict:
    records: list[dict] = []
    skipped = 0
    for p in sorted(paths_mod.GRADING_DIR.glob(paths_mod.CHAINS_GLOB)):
        recs, s = read_jsonl_skip_malformed(p)
        records.extend(recs)
        skipped += s
    if topic is not None:
        records = [r for r in records if r.get("topic") == topic]
    return {"count": len(records), "skipped_malformed": skipped, "records": records}
```

- [ ] **Step 3: Register + test + commit**

Modify `app.py` to `include_router(chains.router)`.

Run: `data-pipeline/.venv/bin/python -m pytest data-pipeline/grading_sidecar/tests/test_chains_endpoint.py -v`
Expected: 4 passed.

```bash
git add data-pipeline/grading_sidecar/routes/chains.py \
        data-pipeline/grading_sidecar/app.py \
        data-pipeline/grading_sidecar/tests/test_chains_endpoint.py
git commit -m "feat(grading-sidecar): /api/grading/chains GET (unions rounds, topic filter, skip malformed)"
```

---

### Task 7: /api/grading/topics + /api/grading/stats + /api/grading/calibration-sample

**Spec sections:** *Sidecar → Endpoints*, *Bootstrap loop → Calibration-drift workflow*.

**Files:**
- Create: `data-pipeline/grading_sidecar/routes/topics.py`
- Create: `data-pipeline/grading_sidecar/routes/stats.py`
- Create: `data-pipeline/grading_sidecar/routes/calibration.py`
- Modify: `data-pipeline/grading_sidecar/app.py`
- Create: `data-pipeline/grading_sidecar/tests/test_topics_stats_calibration.py`

- [ ] **Step 1: Write failing tests**

```python
# data-pipeline/grading_sidecar/tests/test_topics_stats_calibration.py
from __future__ import annotations
import json
import pytest
from grading_sidecar import paths as paths_mod

@pytest.fixture
def patched_paths(client, tmp_path, monkeypatch):
    monkeypatch.setattr(paths_mod, "GRADING_DIR", tmp_path)
    monkeypatch.setattr(paths_mod, "JUDGEMENTS_PATH", tmp_path / "j.jsonl")
    return client, tmp_path

CHAIN = {
    "schema_version": "chain.v1",
    "topic": "anger", "topic_synset_id": "12345",
    "vehicle": "venom", "vehicle_synset_id": "67890",
    "proposer": "sonnet_v1", "round": 1,
    "chain": [
        {"phrase": "anger", "head": "anger", "synset_id": "12345"},
        {"phrase": "venom", "head": "venom", "synset_id": "67890"},
    ],
    "chain_signature": "a" * 64,
    "generated_at": "2026-05-30T03:14:00Z",
}

def test_topics_lean_response(patched_paths):
    client, tmp_path = patched_paths
    f = tmp_path / "sonnet_chains_provisional_r1.jsonl"
    f.write_text(json.dumps(CHAIN) + "\n"
                 + json.dumps({**CHAIN, "topic": "joy", "topic_synset_id": "11111",
                               "chain": [
                                  {"phrase": "joy", "head": "joy", "synset_id": "11111"},
                                  {"phrase": "venom", "head": "venom", "synset_id": "67890"},
                               ],
                               "chain_signature": "b"*64}) + "\n")
    r = client.get("/api/grading/topics")
    assert r.status_code == 200
    body = r.json()
    assert sorted(t["topic"] for t in body["topics"]) == ["anger", "joy"]
    # Lean — no per-topic counts (UI derives from /judgements)
    assert "chains_judged" not in body["topics"][0]

def test_stats_reports_counts(patched_paths):
    client, tmp_path = patched_paths
    (tmp_path / "sonnet_chains_provisional_r1.jsonl").write_text(json.dumps(CHAIN) + "\n")
    r = client.get("/api/grading/stats")
    assert r.status_code == 200
    body = r.json()
    assert body["chain_count"] == 1
    assert body["judgement_count"] == 0
    assert body["schema_version"]["chain"] == "chain.v1"

def test_calibration_sample_returns_n_chains(patched_paths):
    client, tmp_path = patched_paths
    f = tmp_path / "sonnet_chains_provisional_r1.jsonl"
    # 20 chains
    f.write_text("\n".join(
        json.dumps({**CHAIN, "chain_signature": format(i, "064x")})
        for i in range(20)
    ) + "\n")
    r = client.get("/api/grading/calibration-sample?n=5&round=1")
    assert r.status_code == 200
    assert len(r.json()["records"]) == 5

def test_calibration_sample_deterministic_with_seed(patched_paths):
    client, tmp_path = patched_paths
    f = tmp_path / "sonnet_chains_provisional_r1.jsonl"
    f.write_text("\n".join(
        json.dumps({**CHAIN, "chain_signature": format(i, "064x")})
        for i in range(20)
    ) + "\n")
    r1 = client.get("/api/grading/calibration-sample?n=5&round=1&seed=42")
    r2 = client.get("/api/grading/calibration-sample?n=5&round=1&seed=42")
    assert r1.json()["records"] == r2.json()["records"]
```

- [ ] **Step 2: Implement routes**

```python
# data-pipeline/grading_sidecar/routes/topics.py
from fastapi import APIRouter, Depends
from ..auth import verify_secret
from ..persistence import read_jsonl_skip_malformed
from .. import paths as paths_mod

router = APIRouter(dependencies=[Depends(verify_secret)])

@router.get("/api/grading/topics")
def get_topics() -> dict:
    seen: dict[str, dict] = {}
    for p in sorted(paths_mod.GRADING_DIR.glob(paths_mod.CHAINS_GLOB)):
        recs, _ = read_jsonl_skip_malformed(p)
        for r in recs:
            seen.setdefault(r["topic"], {
                "topic": r["topic"], "topic_synset_id": r["topic_synset_id"]
            })
    return {"topics": sorted(seen.values(), key=lambda x: x["topic"])}
```

```python
# data-pipeline/grading_sidecar/routes/stats.py
import datetime as dt
from fastapi import APIRouter, Depends
from ..auth import verify_secret
from ..persistence import read_jsonl_skip_malformed
from .. import paths as paths_mod

router = APIRouter(dependencies=[Depends(verify_secret)])

@router.get("/api/grading/stats")
def get_stats() -> dict:
    chain_count = 0
    for p in paths_mod.GRADING_DIR.glob(paths_mod.CHAINS_GLOB):
        recs, _ = read_jsonl_skip_malformed(p)
        chain_count += len(recs)
    judgements, _ = read_jsonl_skip_malformed(paths_mod.JUDGEMENTS_PATH)
    last_judgement_ts = max((j["ts"] for j in judgements), default=None)
    return {
        "chain_count": chain_count,
        "judgement_count": len(judgements),
        "last_judgement_ts": last_judgement_ts,
        "schema_version": {"chain": "chain.v1", "judgement": "judgement.v1"},
        "server_ts": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
```

```python
# data-pipeline/grading_sidecar/routes/calibration.py
import random
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from ..auth import verify_secret
from ..persistence import read_jsonl_skip_malformed
from .. import paths as paths_mod

router = APIRouter(dependencies=[Depends(verify_secret)])

@router.get("/api/grading/calibration-sample")
def calibration_sample(
    n: int = Query(default=10, ge=1, le=100),
    round: int = Query(default=1, ge=1),
    seed: Optional[int] = Query(default=None),
) -> dict:
    target = paths_mod.GRADING_DIR / f"sonnet_chains_provisional_r{round}.jsonl"
    recs, _ = read_jsonl_skip_malformed(target)
    if not recs:
        raise HTTPException(404, f"no chains for round {round}")
    rng = random.Random(seed if seed is not None else 0)
    rng.shuffle(recs)
    return {"records": recs[:n]}
```

- [ ] **Step 3: Register + test + commit**

Modify `app.py`: `app.include_router(topics.router); app.include_router(stats.router); app.include_router(calibration.router)`.

Run: `data-pipeline/.venv/bin/python -m pytest data-pipeline/grading_sidecar/tests/test_topics_stats_calibration.py -v`
Expected: 4 passed.

```bash
git add data-pipeline/grading_sidecar/routes/topics.py \
        data-pipeline/grading_sidecar/routes/stats.py \
        data-pipeline/grading_sidecar/routes/calibration.py \
        data-pipeline/grading_sidecar/app.py \
        data-pipeline/grading_sidecar/tests/test_topics_stats_calibration.py
git commit -m "feat(grading-sidecar): /api/grading/topics + /stats + /calibration-sample"
```

---

### Task 8: /api/grading/design-notes GET + POST (append-only timestamped blocks)

**Spec sections:** *Sidecar → Endpoints*, *Data shapes → Design-note block*.

**Files:**
- Create: `data-pipeline/grading_sidecar/routes/design_notes.py`
- Modify: `data-pipeline/grading_sidecar/app.py`
- Create: `data-pipeline/grading_sidecar/tests/test_design_notes_endpoint.py`

- [ ] **Step 1: Write failing tests**

```python
# data-pipeline/grading_sidecar/tests/test_design_notes_endpoint.py
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
```

- [ ] **Step 2: Implement route**

```python
# data-pipeline/grading_sidecar/routes/design_notes.py
import datetime as dt
import fcntl
import os
from fastapi import APIRouter, Depends
from ..auth import verify_secret
from ..models import DesignNotePost
from .. import paths as paths_mod

router = APIRouter(dependencies=[Depends(verify_secret)])

@router.get("/api/grading/design-notes")
def get_design_notes() -> dict:
    path = paths_mod.DESIGN_NOTES_PATH
    if not path.exists():
        return {"content": ""}
    return {"content": path.read_text(encoding="utf-8")}

@router.post("/api/grading/design-notes")
def post_design_note(payload: DesignNotePost) -> dict:
    ts = dt.datetime.now(dt.timezone.utc).isoformat()
    block = f"\n## {ts}\n\n{payload.content}\n"
    path = paths_mod.DESIGN_NOTES_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.write(block)
            f.flush()
            os.fsync(f.fileno())
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    return {"ts": ts, "appended_chars": len(block)}
```

- [ ] **Step 3: Register + test + commit**

Modify `app.py`: `app.include_router(design_notes.router)`.

Run: `data-pipeline/.venv/bin/python -m pytest data-pipeline/grading_sidecar/tests/test_design_notes_endpoint.py -v`
Expected: 5 passed.

```bash
git add data-pipeline/grading_sidecar/routes/design_notes.py \
        data-pipeline/grading_sidecar/app.py \
        data-pipeline/grading_sidecar/tests/test_design_notes_endpoint.py
git commit -m "feat(grading-sidecar): /api/grading/design-notes GET + POST"
```

---

### Task 9: Autocommit asyncio task (subprocess git add/commit every 15 min, mockable)

**Spec sections:** *Sidecar → Auto-commit timer*.

**Files:**
- Create: `data-pipeline/grading_sidecar/autocommit.py`
- Modify: `data-pipeline/grading_sidecar/app.py` (start the task in lifespan)
- Create: `data-pipeline/grading_sidecar/tests/test_autocommit.py`

- [ ] **Step 1: Write failing tests**

```python
# data-pipeline/grading_sidecar/tests/test_autocommit.py
import asyncio
import pytest
from unittest.mock import patch
from grading_sidecar.autocommit import autocommit_once

def test_autocommit_calls_git_add_and_commit(tmp_path):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        autocommit_once(repo_root=str(tmp_path), grading_subdir="data-pipeline/grading/")
    cmds = [call.args[0] for call in mock_run.call_args_list]
    assert any("add" in c for c in cmds)
    assert any("commit" in c for c in cmds)

def test_autocommit_tolerates_no_changes(tmp_path):
    with patch("subprocess.run") as mock_run:
        # git commit returns 1 when nothing to commit — autocommit must not crash
        mock_run.side_effect = [
            type("r", (), {"returncode": 0, "stdout": b"", "stderr": b""})(),  # add
            type("r", (), {"returncode": 1, "stdout": b"nothing to commit", "stderr": b""})(),  # commit
        ]
        # Should not raise
        autocommit_once(repo_root=str(tmp_path), grading_subdir="data-pipeline/grading/")

def test_autocommit_logs_failure(tmp_path, caplog):
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = Exception("git not found")
        autocommit_once(repo_root=str(tmp_path), grading_subdir="data-pipeline/grading/")
    assert "autocommit failed" in caplog.text.lower()
```

- [ ] **Step 2: Implement autocommit**

```python
# data-pipeline/grading_sidecar/autocommit.py
"""15-min auto-commit of data-pipeline/grading/ — see spec → Sidecar → Auto-commit timer.

Does NOT push (would require VPS credentials). Julian pushes from his dev box.
"""
from __future__ import annotations
import asyncio
import datetime as dt
import logging
import subprocess

log = logging.getLogger(__name__)

def autocommit_once(repo_root: str, grading_subdir: str) -> None:
    """One-shot: git add <subdir>; git commit -m '...' . Idempotent / tolerant
    of 'nothing to commit'. Errors logged, never raised."""
    try:
        subprocess.run(
            ["git", "-C", repo_root, "add", grading_subdir],
            check=True, capture_output=True,
        )
        ts = dt.datetime.now(dt.timezone.utc).isoformat()
        result = subprocess.run(
            ["git", "-C", repo_root, "commit", "-m", f"wip(grading): autosave {ts}"],
            capture_output=True,
        )
        if result.returncode not in (0, 1):
            log.warning("autocommit unexpected returncode=%d stderr=%s",
                        result.returncode, result.stderr.decode("utf-8", "replace"))
    except Exception as exc:
        log.error("autocommit failed: %s", exc, exc_info=True)

async def autocommit_loop(repo_root: str, grading_subdir: str,
                          interval_sec: float = 900) -> None:
    while True:
        await asyncio.sleep(interval_sec)
        autocommit_once(repo_root, grading_subdir)
```

- [ ] **Step 3: Wire into FastAPI lifespan in app.py**

```python
# in data-pipeline/grading_sidecar/app.py
from contextlib import asynccontextmanager
import asyncio
from .autocommit import autocommit_loop
from . import paths as paths_mod

@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(
        autocommit_loop(str(paths_mod.REPO_ROOT), "data-pipeline/grading/")
    )
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass

# In create_app, pass lifespan=lifespan to FastAPI(...)
```

- [ ] **Step 4: Test + commit**

Run: `data-pipeline/.venv/bin/python -m pytest data-pipeline/grading_sidecar/tests/test_autocommit.py -v`
Expected: 3 passed.

```bash
git add data-pipeline/grading_sidecar/autocommit.py \
        data-pipeline/grading_sidecar/app.py \
        data-pipeline/grading_sidecar/tests/test_autocommit.py
git commit -m "feat(grading-sidecar): 15-min auto-commit asyncio task"
```

---

### Task 10: systemd service + deploy script (sidecar)

**Spec sections:** *Sidecar → Systemd unit*, *Deployment & CI → Caddy snippet management*.

**Files:**
- Create: `deploy/grading/metaforge-grading.service`
- Create: `deploy/grading/metaforge-grading.env.example`
- Create: `deploy/grading/deploy.sh`

- [ ] **Step 1: Write systemd unit template**

```ini
# deploy/grading/metaforge-grading.service
[Unit]
Description=Metaforge Grading Sidecar
After=network.target

[Service]
Type=simple
User=metaforge-grading
WorkingDirectory=/home/agent/projects/metaforge
EnvironmentFile=/etc/default/metaforge-grading
Environment=GRADING_DEV=
ExecStart=/home/agent/projects/metaforge/data-pipeline/.venv/bin/python -m grading_sidecar.main
Restart=on-failure
RestartSec=2
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
# Do NOT use ProtectHome=read-only — known gotcha that broke metaforge-api (see deploy-servers memory)
ReadWritePaths=/home/agent/projects/metaforge/data-pipeline/grading/ /home/agent/projects/metaforge/.git/
CapabilityBoundingSet=

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: Write env-file example**

```bash
# deploy/grading/metaforge-grading.env.example
# Copy to /etc/default/metaforge-grading on the VPS, populate, chmod 0640.
GRADING_SECRET_FILE=/etc/metaforge/grading_secret
PYTHONPATH=/home/agent/projects/metaforge/data-pipeline/
```

- [ ] **Step 3: Write deploy.sh per spec → Deployment & CI → Caddy snippet management**

```bash
# deploy/grading/deploy.sh
#!/usr/bin/env bash
# Deploy the Metaforge grading sidecar + patched metaforge-next Caddy snippet.
# Idempotent. Fails closed on missing secrets.
set -euo pipefail

: "${JULIAN_BCRYPT_HASH:?must be set in /etc/default/caddy (or in shell env)}"
: "${GRADING_SECRET:?must be set in /etc/default/caddy (or in shell env)}"

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

# 1. Render Caddy snippet
envsubst < "$REPO_ROOT/deploy/caddy/metaforge-next.caddy.template" \
    | sudo tee /etc/caddy/conf.d/metaforge-next.caddy.active >/dev/null

# 2. Validate before reload
sudo caddy validate --config /etc/caddy/Caddyfile

# 3. Install systemd unit (idempotent — overwrites)
sudo install -m 0644 "$REPO_ROOT/deploy/grading/metaforge-grading.service" \
    /etc/systemd/system/metaforge-grading.service
sudo systemctl daemon-reload

# 4. Ensure secret file exists with 0600 perms
sudo install -d -m 0700 /etc/metaforge
if [ ! -f /etc/metaforge/grading_secret ]; then
    echo "ERROR: /etc/metaforge/grading_secret does not exist." >&2
    echo "Create it manually: echo -n '<secret>' | sudo tee /etc/metaforge/grading_secret; sudo chmod 600 /etc/metaforge/grading_secret" >&2
    exit 1
fi
sudo chmod 0600 /etc/metaforge/grading_secret

# 5. Apply
sudo systemctl reload caddy
sudo systemctl enable --now metaforge-grading
sudo systemctl restart metaforge-grading

# 6. Smoke
sleep 2
curl -fsS http://127.0.0.1:53775/api/grading/healthz
curl -fsS https://metaforge-next.julianit.me/api/grading/healthz

# 7. Auth smoke — wrong basic-auth must 401
if curl -fsS -u julian:WRONGPASS https://metaforge-next.julianit.me/api/grading/stats; then
    echo "FAIL: auth bypass (wrong-pass returned 200)" >&2
    exit 1
fi
echo "OK: auth smoke (401 on wrong creds)"

echo "Deploy complete."
```

- [ ] **Step 4: Make executable + commit**

```bash
chmod +x deploy/grading/deploy.sh
git add deploy/grading/
git commit -m "feat(grading-sidecar): systemd unit + deploy.sh + env example"
```

(No automated tests for deploy artefacts; they're validated by Task 12's deploy smoke against the live VPS.)

---

### Task 11: Patch deploy/caddy/metaforge-next.caddy.template with `/api/grading/*` blocks

**Spec sections:** *Auth → Layer 1 — Caddy HTTP Basic Auth (path-scoped)*, *Deployment & CI*.

**Files:**
- Modify (or create if not yet in repo): `deploy/caddy/metaforge-next.caddy.template`

- [ ] **Step 1: Locate the existing metaforge-next Caddy snippet on the VPS**

Run: `sudo cat /etc/caddy/conf.d/metaforge-next.caddy* 2>/dev/null | head -40`
Capture the current site block (already serving the thesaurus via `reverse_proxy 127.0.0.1:8081`).

- [ ] **Step 2: Write/update the repo template** per spec section "Layer 1 — Caddy HTTP Basic Auth (path-scoped)"

```caddy
# deploy/caddy/metaforge-next.caddy.template
metaforge-next.julianit.me {
    # Healthz — public, no auth (frontend probe).
    handle /api/grading/healthz {
        reverse_proxy 127.0.0.1:53775
    }

    # Grading API — auth + rate limit + body cap + secret injection.
    handle /api/grading/* {
        basicauth {
            julian {$JULIAN_BCRYPT_HASH}
        }

        request_body {
            max_size 1MB
        }

        rate_limit {
            zone grading_ip {
                key {remote_host}
                events 10
                window 10s
            }
        }

        log {
            output file /var/log/caddy/metaforge-next.julianit.me.log
            format json
        }

        reverse_proxy 127.0.0.1:53775 {
            header_up X-Grading-Secret {$GRADING_SECRET}
        }
    }

    # Default — existing thesaurus Go API serves the SPA + thesaurus/forge endpoints
    reverse_proxy 127.0.0.1:8081
}
```

**If the existing snippet has additional directives** (cache headers, error-page rules, etc.), merge them inside the default `reverse_proxy` path or as sibling directives. The two `handle` blocks must come BEFORE the default `reverse_proxy` so Caddy's path-specificity routing prefers them.

- [ ] **Step 3: Commit (no smoke yet; smoke is in Task 12 after the deploy runs)**

```bash
git add deploy/caddy/metaforge-next.caddy.template
git commit -m "feat(grading-tool): patch metaforge-next Caddy snippet with /api/grading/* routing"
```

---

### Task 12: Deploy + auth smoke on metaforge-next

**Spec sections:** *Auth → Auth smoke tests (CI)*, *Deployment & CI*.

This task is **runtime-only** (no Python tests). It exercises Task 10's `deploy/grading/deploy.sh` against the VPS.

- [ ] **Step 1: Generate password + bcrypt hash (one-shot, NOT committed)**

```bash
# On Julian's dev box (or via remote shell):
openssl rand -base64 24    # capture this — save to password manager
# Then bcrypt the password (replace <PASSWORD> with the output above):
caddy hash-password --plaintext '<PASSWORD>'  # capture the hash
```

- [ ] **Step 2: Generate the sidecar shared-secret**

```bash
openssl rand -hex 32    # capture, save securely
```

- [ ] **Step 3: Populate `/etc/default/caddy` with both**

```bash
sudo tee -a /etc/default/caddy <<'EOF'
JULIAN_BCRYPT_HASH=<bcrypt hash from Step 1>
GRADING_SECRET=<hex secret from Step 2>
EOF
sudo chmod 0640 /etc/default/caddy
```

- [ ] **Step 4: Populate `/etc/metaforge/grading_secret`**

```bash
sudo install -d -m 0700 /etc/metaforge
echo -n '<same hex secret as Step 2>' | sudo tee /etc/metaforge/grading_secret >/dev/null
sudo chmod 0600 /etc/metaforge/grading_secret
sudo useradd --system --shell /sbin/nologin --no-create-home metaforge-grading 2>/dev/null || true
sudo chown metaforge-grading:metaforge-grading /etc/metaforge/grading_secret
```

- [ ] **Step 5: Run deploy script**

```bash
JULIAN_BCRYPT_HASH=<...> GRADING_SECRET=<...> sudo --preserve-env=JULIAN_BCRYPT_HASH,GRADING_SECRET \
    /home/agent/projects/metaforge/deploy/grading/deploy.sh
```

Expected: all 7 steps complete; final line "Deploy complete."

- [ ] **Step 6: Manual auth smoke tests**

```bash
# 1. Unauth'd healthz works
curl -fsS https://metaforge-next.julianit.me/api/grading/healthz
# → {"ok": true}

# 2. Wrong basic-auth on protected endpoint → 401
curl -s -o /dev/null -w "%{http_code}" -u julian:WRONGPASS \
    https://metaforge-next.julianit.me/api/grading/stats
# → 401

# 3. Right basic-auth → 200
curl -fsS -u julian:<PASSWORD> https://metaforge-next.julianit.me/api/grading/stats
# → {...stats...}

# 4. Existing thesaurus paths still work
curl -fsS https://metaforge-next.julianit.me/thesaurus/lookup?word=anger
# → existing thesaurus response (no auth on this path)

# 5. Fail-closed test: temporarily clear /etc/metaforge/grading_secret, restart sidecar
sudo bash -c 'echo -n > /etc/metaforge/grading_secret'
sudo systemctl restart metaforge-grading
sudo systemctl status metaforge-grading  # should show: failed, exit code 1
# Restore:
echo -n '<hex secret>' | sudo tee /etc/metaforge/grading_secret >/dev/null
sudo chmod 0600 /etc/metaforge/grading_secret
sudo chown metaforge-grading:metaforge-grading /etc/metaforge/grading_secret
sudo systemctl restart metaforge-grading
```

- [ ] **Step 7: Document the password storage location for Julian**

Add a one-line note to `deploy/grading/README.md`:
> The `julian` basic-auth password lives in Julian's password manager — NOT in this repo. The bcrypt hash is in `/etc/default/caddy` and is safe to commit (Caddy snippet env-var substitution).

- [ ] **Step 8: Commit**

```bash
git add deploy/grading/README.md
git commit -m "docs(grading): deploy README"
```

---

### Task 13: Head-extraction backfill (round-1 data)

**Spec sections:** *Head extraction backfill*.

**Files:**
- Create: `data-pipeline/scripts/head_extraction_backfill.py`
- Output: `data-pipeline/grading/sonnet_chains_provisional_r1.jsonl` (committed)

- [ ] **Step 1: Implement the backfill script**

```python
# data-pipeline/scripts/head_extraction_backfill.py
"""Round-1 backfill: extract {phrase, head, synset_id} per chain step from the
existing /tmp/stagea_spike/sonnet_chains.jsonl flat-string chains.

Single-word phrase → head = phrase.lower(); multi-word → batched Haiku call.
Snap each unique head via lookup_primary_synset (nullable on miss).

See spec section "Head extraction backfill" for the subagent prompt and shape.
"""
from __future__ import annotations
import argparse
import json
import sys
import sqlite3
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))

from metaphor_graph import lookup_primary_synset, compute_path_hash  # noqa: E402
from claude_client import prompt_json  # noqa: E402

# Import the chain_signature function from the sidecar module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "grading_sidecar"))
from models import compute_chain_signature  # noqa: E402

SOURCE = "/tmp/stagea_spike/sonnet_chains.jsonl"
DEST = Path(__file__).resolve().parent.parent / "grading" / "sonnet_chains_provisional_r1.jsonl"
HAIKU_BATCH_SIZE = 50

def normalise(s: str) -> str:
    return unicodedata.normalize("NFC", s.strip())

def extract_heads_batch(phrases: list[str]) -> dict[str, str]:
    """Haiku batched call. Returns {phrase: head}."""
    prompt = (
        "For each phrase below, return the single-word concept that the phrase "
        "most centres on — typically a noun. Prefer a head likely to be re-used "
        "across other metaphor traversals over a hyper-specific one.\n\n"
        "Output strict JSON: {\"phrases\": [{\"phrase\": \"...\", \"head\": \"...\"}, ...]}\n\n"
        "Phrases:\n" + "\n".join(f"- {p}" for p in phrases)
    )
    resp = prompt_json(prompt, model="claude-haiku-4-5-20251001")
    return {item["phrase"]: item["head"].lower() for item in resp["phrases"]}

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(Path(__file__).resolve().parent.parent / "output" / "lexicon_v2.db"))
    parser.add_argument("--source", default=SOURCE)
    parser.add_argument("--dest", default=str(DEST))
    args = parser.parse_args()

    raw = [json.loads(l) for l in open(args.source) if l.strip()]
    print(f"Loaded {len(raw)} chain records from {args.source}", file=sys.stderr)

    # Collect unique phrases
    multi_word: set[str] = set()
    for rec in raw:
        for vehicle in rec["vehicles"]:
            for step in vehicle["chain"]:
                if " " in str(step).strip():
                    multi_word.add(normalise(step))

    print(f"Found {len(multi_word)} unique multi-word phrases", file=sys.stderr)

    # Batched Haiku calls
    heads: dict[str, str] = {}
    multi_word_list = sorted(multi_word)
    for i in range(0, len(multi_word_list), HAIKU_BATCH_SIZE):
        batch = multi_word_list[i:i+HAIKU_BATCH_SIZE]
        print(f"  Haiku batch {i//HAIKU_BATCH_SIZE + 1}: {len(batch)} phrases", file=sys.stderr)
        heads.update(extract_heads_batch(batch))

    # Snap heads to synsets
    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)

    def head_of(phrase: str) -> str:
        p = normalise(phrase)
        if " " not in p:
            return p.lower()
        return heads.get(p, p.split()[0].lower())

    out_records: list[dict] = []
    for rec in raw:
        topic = rec["topic"]
        topic_head = topic.lower()
        topic_synset = lookup_primary_synset(conn, topic_head)
        for vehicle in rec["vehicles"]:
            v_phrase = vehicle["vehicle"]
            v_head = v_phrase.lower()
            v_synset = lookup_primary_synset(conn, v_head)
            chain_steps = []
            for step in vehicle["chain"]:
                phrase = normalise(step)
                head = head_of(phrase)
                synset_id = lookup_primary_synset(conn, head)
                chain_steps.append({
                    "phrase": phrase,
                    "head": head,
                    "synset_id": synset_id,
                })
            # Endpoint canonicalisation — ensure chain[0] == topic, chain[-1] == vehicle
            chain_steps[0] = {"phrase": topic, "head": topic_head, "synset_id": topic_synset}
            chain_steps[-1] = {"phrase": v_phrase, "head": v_head, "synset_id": v_synset}

            phrases = [s["phrase"] for s in chain_steps]
            sig = compute_chain_signature("sonnet_v1", phrases)
            out_records.append({
                "schema_version": "chain.v1",
                "topic": topic, "topic_synset_id": topic_synset,
                "vehicle": v_phrase, "vehicle_synset_id": v_synset,
                "proposer": "sonnet_v1", "round": 1,
                "chain": chain_steps,
                "chain_signature": sig,
                "generated_at": "2026-05-30T00:00:00Z",  # placeholder; source predates
            })

    dest = Path(args.dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        for r in out_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"Wrote {len(out_records)} chains to {dest}", file=sys.stderr)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Dry-run smoke (optional, only requires Haiku spend)**

Run: `data-pipeline/.venv/bin/python data-pipeline/scripts/head_extraction_backfill.py --source /tmp/stagea_spike/sonnet_chains.jsonl --dest /tmp/r1_check.jsonl`

Expected: prints batch counts and a final "Wrote N chains to /tmp/r1_check.jsonl" with N == 200.

- [ ] **Step 3: Produce + commit the real round-1 output**

```bash
data-pipeline/.venv/bin/python data-pipeline/scripts/head_extraction_backfill.py
git add data-pipeline/scripts/head_extraction_backfill.py \
        data-pipeline/grading/sonnet_chains_provisional_r1.jsonl
git commit -m "feat(grading): round-1 chain backfill with {phrase, head, synset_id}"
```

Cost: ~10 Haiku batched calls × $0.005 ≈ $0.05.

---

### Task 14: Frontend TypeScript types + grading API client

**Spec sections:** *UI integration*, *Data shapes*.

**Files:**
- Create: `web/src/types/grading.ts`
- Create: `web/src/api/grading-client.ts`
- Create: `web/src/api/grading-client.test.ts`

- [ ] **Step 1: Write failing tests**

```typescript
// web/src/api/grading-client.test.ts
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { GradingClient } from './grading-client';

describe('GradingClient', () => {
    let fetchMock: ReturnType<typeof vi.fn>;
    beforeEach(() => {
        fetchMock = vi.fn();
        global.fetch = fetchMock as unknown as typeof fetch;
    });

    it('probe returns true on 200', async () => {
        fetchMock.mockResolvedValue({ ok: true, status: 200 });
        const client = new GradingClient();
        expect(await client.probe()).toBe(true);
    });

    it('probe returns true on 401 (auth required, still available)', async () => {
        fetchMock.mockResolvedValue({ ok: false, status: 401 });
        const client = new GradingClient();
        expect(await client.probe()).toBe(true);
    });

    it('probe returns false on 404', async () => {
        fetchMock.mockResolvedValue({ ok: false, status: 404 });
        const client = new GradingClient();
        expect(await client.probe()).toBe(false);
    });

    it('probe returns false on network error', async () => {
        fetchMock.mockRejectedValue(new Error('network'));
        const client = new GradingClient();
        expect(await client.probe()).toBe(false);
    });

    it('postJudgement retries 3x on 5xx with exponential backoff', async () => {
        vi.useFakeTimers();
        fetchMock
            .mockResolvedValueOnce({ ok: false, status: 500 })
            .mockResolvedValueOnce({ ok: false, status: 500 })
            .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ ts: 'x' }) });
        const client = new GradingClient();
        const promise = client.postJudgement({} as any);
        await vi.runAllTimersAsync();
        const result = await promise;
        expect(result.ts).toBe('x');
        expect(fetchMock).toHaveBeenCalledTimes(3);
        vi.useRealTimers();
    });
});
```

- [ ] **Step 2: Implement types**

```typescript
// web/src/types/grading.ts
export type Label = 'live' | 'dead' | 'bad_path' | 'irrelevant';
export type Confidence = 'high' | 'med' | 'low';

export interface ChainStep {
    phrase: string;
    head: string;
    synset_id: string | null;
}

export interface ChainRecord {
    schema_version: 'chain.v1';
    topic: string;
    topic_synset_id: string;
    vehicle: string;
    vehicle_synset_id: string;
    proposer: string;
    round: number;
    chain: ChainStep[];
    chain_signature: string;
    generated_at: string;
}

export interface JudgementRecord {
    schema_version: 'judgement.v1';
    ts?: string;
    judged_by: string;
    round: number;
    topic: string;
    topic_synset_id: string;
    vehicle: string;
    vehicle_synset_id: string;
    proposer: string;
    chain_signature: string;
    label: Label;
    confidence: Confidence;
    notes: string;
    supersedes_ts: string | null;
}

export interface TopicSummary {
    topic: string;
    topic_synset_id: string;
}
```

- [ ] **Step 3: Implement client**

```typescript
// web/src/api/grading-client.ts
import type { ChainRecord, JudgementRecord, TopicSummary } from '../types/grading';

const BASE = '/api/grading';
const RETRY_DELAYS_MS = [1000, 3000, 9000];

export class GradingClient {
    async probe(): Promise<boolean> {
        try {
            const r = await fetch(`${BASE}/healthz`);
            // 200 OR 401 both mean "grading is available here"
            return r.ok || r.status === 401;
        } catch {
            return false;
        }
    }

    async getTopics(): Promise<{ topics: TopicSummary[] }> {
        const r = await fetch(`${BASE}/topics`);
        if (!r.ok) throw new Error(`getTopics: ${r.status}`);
        return r.json();
    }

    async getChains(topic?: string): Promise<{ count: number; records: ChainRecord[] }> {
        const url = topic ? `${BASE}/chains?topic=${encodeURIComponent(topic)}` : `${BASE}/chains`;
        const r = await fetch(url);
        if (!r.ok) throw new Error(`getChains: ${r.status}`);
        return r.json();
    }

    async getJudgements(topic?: string): Promise<{ count: number; records: JudgementRecord[] }> {
        const url = topic ? `${BASE}/judgements?topic=${encodeURIComponent(topic)}` : `${BASE}/judgements`;
        const r = await fetch(url);
        if (!r.ok) throw new Error(`getJudgements: ${r.status}`);
        return r.json();
    }

    async postJudgement(j: JudgementRecord): Promise<JudgementRecord> {
        let lastError: Error | null = null;
        for (let attempt = 0; attempt <= RETRY_DELAYS_MS.length; attempt++) {
            try {
                const r = await fetch(`${BASE}/judgements`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(j),
                });
                if (r.ok) return r.json();
                if (r.status >= 400 && r.status < 500) {
                    throw new Error(`postJudgement: ${r.status} (no retry)`);
                }
                lastError = new Error(`postJudgement: ${r.status}`);
            } catch (e) {
                lastError = e as Error;
            }
            if (attempt < RETRY_DELAYS_MS.length) {
                await new Promise(res => setTimeout(res, RETRY_DELAYS_MS[attempt]));
            }
        }
        throw lastError!;
    }

    async getDesignNotes(): Promise<{ content: string }> {
        const r = await fetch(`${BASE}/design-notes`);
        if (!r.ok) throw new Error(`getDesignNotes: ${r.status}`);
        return r.json();
    }

    async postDesignNote(content: string): Promise<{ ts: string }> {
        const r = await fetch(`${BASE}/design-notes`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content }),
        });
        if (!r.ok) throw new Error(`postDesignNote: ${r.status}`);
        return r.json();
    }
}
```

- [ ] **Step 4: Test + commit**

Run: `cd web && npx vitest run src/api/grading-client.test.ts`
Expected: 5 passed.

```bash
git add web/src/types/grading.ts web/src/api/grading-client.ts web/src/api/grading-client.test.ts
git commit -m "feat(grading-ui): TypeScript types + grading API client with retry+backoff"
```

---

### Task 15: mf-app mode state + probe + toggle + error wiring

**Spec sections:** *UI integration → Grading-availability probe (graceful degrade)*, *UI integration → Default landing state*.

**Files:**
- Modify: `web/src/components/mf-app.ts`
- Modify: `web/src/components/mf-app.test.ts`
- Create: `web/src/components/mf-error-banner.ts`
- Create: `web/src/components/mf-error-banner.test.ts`

- [ ] **Step 1: Write tests for mode probe + toggle in mf-app.test.ts (extend existing)**

```typescript
// in web/src/components/mf-app.test.ts — ADDITIONAL tests
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { fixture, html } from '@open-wc/testing-helpers';
import './mf-app';

describe('mf-app grading mode', () => {
    beforeEach(() => {
        vi.spyOn(global, 'fetch').mockResolvedValue({ ok: true, status: 200 } as Response);
        localStorage.clear();
    });

    it('shows toggle when probe returns 200', async () => {
        const el = await fixture(html`<mf-app></mf-app>`);
        await el.updateComplete;
        // Wait for probe
        await new Promise(r => setTimeout(r, 50));
        await el.updateComplete;
        expect(el.shadowRoot!.querySelector('[data-testid="grade-toggle"]')).toBeTruthy();
    });

    it('hides toggle when probe returns 404', async () => {
        (global.fetch as any).mockResolvedValue({ ok: false, status: 404 });
        const el = await fixture(html`<mf-app></mf-app>`);
        await new Promise(r => setTimeout(r, 50));
        await el.updateComplete;
        expect(el.shadowRoot!.querySelector('[data-testid="grade-toggle"]')).toBeFalsy();
    });

    it('defaults to grade mode on metaforge-next.julianit.me when probe succeeds', async () => {
        // Mock window.location.host
        Object.defineProperty(window, 'location', {
            value: { host: 'metaforge-next.julianit.me' }, writable: true
        });
        const el = await fixture<any>(html`<mf-app></mf-app>`);
        await new Promise(r => setTimeout(r, 50));
        await el.updateComplete;
        expect(el.mode).toBe('grade');
    });

    it('forces mode to browse on 401 after a session', async () => {
        const el = await fixture<any>(html`<mf-app></mf-app>`);
        el.mode = 'grade';
        // Simulate a 401 from any subsequent endpoint
        el.handleAuthExpired();
        expect(el.mode).toBe('browse');
    });
});
```

- [ ] **Step 2: Implement mf-error-banner first (simple component)**

```typescript
// web/src/components/mf-error-banner.ts
import { LitElement, html, css } from 'lit';
import { customElement, property } from 'lit/decorators.js';

@customElement('mf-error-banner')
export class MfErrorBanner extends LitElement {
    static styles = css`
        :host { display: block; }
        .banner {
            background: #c47a7a;
            color: white;
            padding: 0.5rem 1rem;
            font-size: 0.9rem;
        }
        .banner.warn { background: #d6a560; }
    `;

    @property() message = '';
    @property() level: 'error' | 'warn' = 'error';

    render() {
        if (!this.message) return html``;
        return html`<div class="banner ${this.level}">${this.message}</div>`;
    }
}
```

- [ ] **Step 3: Modify mf-app per spec**

Modify `web/src/components/mf-app.ts` to add: `mode` private field (NOT @state — per `lit_vite_patterns` memory, @state on non-rendered properties causes unnecessary re-renders; mode IS rendered so @state is correct here), `connectedCallback` runs the probe, header button toggles, `localStorage` persists, `handleAuthExpired` forces browse mode. Reference spec sections "Grading-availability probe" and "Default landing state" for behaviour.

Sketch (subagent fills in remaining glue against existing mf-app structure):

```typescript
// In mf-app.ts class
import './mf-error-banner';
import { GradingClient } from '../api/grading-client';

@state() private mode: 'browse' | 'grade' = 'browse';
@state() private gradingAvailable = false;
@state() private errorMessage = '';

private client = new GradingClient();

async connectedCallback() {
    super.connectedCallback();
    this.gradingAvailable = await this.client.probe();
    if (this.gradingAvailable) {
        const stored = localStorage.getItem('mf-mode');
        if (stored === 'grade' || stored === 'browse') {
            this.mode = stored;
        } else if (location.host === 'metaforge-next.julianit.me') {
            this.mode = 'grade';
        }
    } else {
        this.mode = 'browse';
    }
}

private toggleMode() {
    this.mode = this.mode === 'grade' ? 'browse' : 'grade';
    localStorage.setItem('mf-mode', this.mode);
}

handleAuthExpired() {
    this.mode = 'browse';
    this.errorMessage = 'Auth expired — refresh to re-authenticate';
}
```

In `render()`:
```typescript
${this.gradingAvailable ? html`
    <button data-testid="grade-toggle" @click=${this.toggleMode}>
        ${this.mode === 'grade' ? '[Browse Mode]' : '[Grading Mode]'}
    </button>
` : ''}
<mf-error-banner .message=${this.errorMessage}></mf-error-banner>
${this.mode === 'grade' ? html`<!-- grade-mode subtree (filled in by later tasks) -->` : html`<!-- existing browse-mode tree -->`}
```

- [ ] **Step 4: Run tests, commit**

```bash
cd web && npx vitest run src/components/mf-app.test.ts src/components/mf-error-banner.test.ts
git add web/src/components/mf-app.ts web/src/components/mf-app.test.ts \
        web/src/components/mf-error-banner.ts web/src/components/mf-error-banner.test.ts
git commit -m "feat(grading-ui): mf-app mode probe + toggle + error banner"
```

---

### Task 16: mf-topic-picker (filterable combobox)

**Spec sections:** *UI integration → Components*.

**Files:**
- Create: `web/src/components/mf-topic-picker.ts`
- Create: `web/src/components/mf-topic-picker.test.ts`

- [ ] **Step 1: Write failing tests**

```typescript
// web/src/components/mf-topic-picker.test.ts
import { describe, it, expect } from 'vitest';
import { fixture, html } from '@open-wc/testing-helpers';
import './mf-topic-picker';

describe('mf-topic-picker', () => {
    const topics = [
        { topic: 'anger', topic_synset_id: '1' },
        { topic: 'joy', topic_synset_id: '2' },
        { topic: 'time', topic_synset_id: '3' },
    ];

    it('renders all topics', async () => {
        const el = await fixture(html`<mf-topic-picker .topics=${topics}></mf-topic-picker>`);
        const options = el.shadowRoot!.querySelectorAll('[data-testid="option"]');
        expect(options.length).toBe(3);
    });

    it('filters topics by typed prefix', async () => {
        const el = await fixture<any>(html`<mf-topic-picker .topics=${topics}></mf-topic-picker>`);
        const input = el.shadowRoot!.querySelector('input')!;
        input.value = 'an';
        input.dispatchEvent(new Event('input'));
        await el.updateComplete;
        const visible = el.shadowRoot!.querySelectorAll('[data-testid="option"]:not([hidden])');
        expect(visible.length).toBe(1);
        expect(visible[0].textContent).toContain('anger');
    });

    it('emits topic-selected on click', async () => {
        const el = await fixture<any>(html`<mf-topic-picker .topics=${topics}></mf-topic-picker>`);
        let captured: any = null;
        el.addEventListener('topic-selected', (e: any) => { captured = e.detail; });
        const first = el.shadowRoot!.querySelector('[data-testid="option"]') as HTMLElement;
        first.click();
        expect(captured).toEqual({ topic: 'anger', topic_synset_id: '1' });
    });
});
```

- [ ] **Step 2: Implement**

```typescript
// web/src/components/mf-topic-picker.ts
import { LitElement, html, css } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import type { TopicSummary } from '../types/grading';

@customElement('mf-topic-picker')
export class MfTopicPicker extends LitElement {
    static styles = css`
        :host { display: block; }
        input { width: 100%; padding: 0.4rem; font-size: 1rem; }
        ul { list-style: none; padding: 0; margin: 0; max-height: 50vh; overflow-y: auto; }
        li { padding: 0.5rem; cursor: pointer; }
        li:hover, li:focus { background: #2a3140; }
        li[hidden] { display: none; }
    `;

    @property({ type: Array }) topics: TopicSummary[] = [];
    @state() private filter = '';

    private onInput(e: Event) {
        this.filter = (e.target as HTMLInputElement).value.toLowerCase();
    }

    private select(t: TopicSummary) {
        this.dispatchEvent(new CustomEvent('topic-selected', { detail: t, bubbles: true, composed: true }));
    }

    render() {
        return html`
            <input type="text" placeholder="filter topics…" @input=${this.onInput} />
            <ul>
                ${this.topics.map(t => html`
                    <li data-testid="option"
                        ?hidden=${this.filter && !t.topic.toLowerCase().includes(this.filter)}
                        tabindex="0"
                        @click=${() => this.select(t)}
                        @keydown=${(e: KeyboardEvent) => { if (e.key === 'Enter') this.select(t); }}>
                        ${t.topic}
                    </li>
                `)}
            </ul>
        `;
    }
}
```

- [ ] **Step 3: Test + commit**

Run: `cd web && npx vitest run src/components/mf-topic-picker.test.ts`
Expected: 3 passed.

```bash
git add web/src/components/mf-topic-picker.ts web/src/components/mf-topic-picker.test.ts
git commit -m "feat(grading-ui): mf-topic-picker filterable combobox"
```

---

### Task 17: mf-grade-panel (verdict + confidence + notes + keyboard)

**Spec sections:** *UI integration → Components → mf-grade-panel*, *UI integration → Click-to-select-path UX*.

**Files:**
- Create: `web/src/components/mf-grade-panel.ts`
- Create: `web/src/components/mf-grade-panel.test.ts`

- [ ] **Step 1: Write failing tests**

```typescript
// web/src/components/mf-grade-panel.test.ts
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { fixture, html } from '@open-wc/testing-helpers';
import './mf-grade-panel';

const CHAIN = {
    topic: 'anger', vehicle: 'venom', chain_signature: 'a'.repeat(64),
    chain: [
        { phrase: 'anger', head: 'anger', synset_id: '1' },
        { phrase: 'hostility', head: 'hostility', synset_id: '2' },
        { phrase: 'venom', head: 'venom', synset_id: '3' },
    ],
    proposer: 'sonnet_v1', round: 1,
    topic_synset_id: '1', vehicle_synset_id: '3',
    schema_version: 'chain.v1', generated_at: 'x',
};

describe('mf-grade-panel', () => {
    it('renders chain phrases inline with arrows', async () => {
        const el = await fixture(html`<mf-grade-panel .chain=${CHAIN}></mf-grade-panel>`);
        const text = el.shadowRoot!.textContent || '';
        expect(text).toContain('anger');
        expect(text).toContain('hostility');
        expect(text).toContain('venom');
        expect(text).toContain('→');
    });

    it('emits verdict-submit on L keypress (live)', async () => {
        const el = await fixture<any>(html`<mf-grade-panel .chain=${CHAIN}></mf-grade-panel>`);
        let captured: any = null;
        el.addEventListener('verdict-submit', (e: any) => { captured = e.detail; });
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'l' }));
        await new Promise(r => setTimeout(r, 0));
        expect(captured?.label).toBe('live');
    });

    it('emits verdict-submit on D keypress (dead)', async () => {
        const el = await fixture<any>(html`<mf-grade-panel .chain=${CHAIN}></mf-grade-panel>`);
        let captured: any = null;
        el.addEventListener('verdict-submit', (e: any) => { captured = e.detail; });
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'd' }));
        await new Promise(r => setTimeout(r, 0));
        expect(captured?.label).toBe('dead');
    });

    it('emits verdict-submit on B keypress (bad_path)', async () => {
        const el = await fixture<any>(html`<mf-grade-panel .chain=${CHAIN}></mf-grade-panel>`);
        let captured: any = null;
        el.addEventListener('verdict-submit', (e: any) => { captured = e.detail; });
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'b' }));
        await new Promise(r => setTimeout(r, 0));
        expect(captured?.label).toBe('bad_path');
    });

    it('emits verdict-submit on I keypress (irrelevant)', async () => {
        const el = await fixture<any>(html`<mf-grade-panel .chain=${CHAIN}></mf-grade-panel>`);
        let captured: any = null;
        el.addEventListener('verdict-submit', (e: any) => { captured = e.detail; });
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'i' }));
        await new Promise(r => setTimeout(r, 0));
        expect(captured?.label).toBe('irrelevant');
    });

    it('confidence defaults to high; 2 sets med', async () => {
        const el = await fixture<any>(html`<mf-grade-panel .chain=${CHAIN}></mf-grade-panel>`);
        let captured: any = null;
        el.addEventListener('verdict-submit', (e: any) => { captured = e.detail; });
        document.dispatchEvent(new KeyboardEvent('keydown', { key: '2' }));
        await new Promise(r => setTimeout(r, 0));
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'l' }));
        await new Promise(r => setTimeout(r, 0));
        expect(captured?.confidence).toBe('med');
    });

    it('shows previous verdict banner when priorVerdict prop is set', async () => {
        const el = await fixture(html`
            <mf-grade-panel .chain=${CHAIN} .priorVerdict=${{ label: 'bad_path', ts: '2026-05-30T00:00:00Z' }}></mf-grade-panel>
        `);
        const banner = el.shadowRoot!.querySelector('[data-testid="re-grade-banner"]');
        expect(banner).toBeTruthy();
        expect(banner!.textContent).toContain('bad_path');
    });

    it('supports failure-mode tag chips that prepend to notes', async () => {
        const el = await fixture<any>(html`<mf-grade-panel .chain=${CHAIN}></mf-grade-panel>`);
        const chip = el.shadowRoot!.querySelector('[data-testid="chip-merge"]') as HTMLElement;
        chip.click();
        await el.updateComplete;
        const textarea = el.shadowRoot!.querySelector('textarea') as HTMLTextAreaElement;
        expect(textarea.value.startsWith('merge:')).toBe(true);
    });
});
```

- [ ] **Step 2: Implement (see spec for full visual + interaction spec)**

The implementation has full keyboard handling, four verdict buttons (`Live` / `Dead` / `Bad Path` / `Irrelevant`), confidence picker (3 buttons), tag chips (`merge` / `padding` / `leap` / `other`), notes textarea (2-3 rows, max_length 1000), re-grade banner. Wire `keydown` listener on `document` while panel is connected; clean up in `disconnectedCallback`. On verdict trigger, emit `verdict-submit` event with `{label, confidence, notes}`. See spec section "mf-grade-panel" for the visual layout and "Click-to-select-path UX" for the flow.

Full implementation: see spec section. Implementor: follow spec verbatim; pass all 8 tests.

- [ ] **Step 3: Test + commit**

Run: `cd web && npx vitest run src/components/mf-grade-panel.test.ts`
Expected: 8 passed.

```bash
git add web/src/components/mf-grade-panel.ts web/src/components/mf-grade-panel.test.ts
git commit -m "feat(grading-ui): mf-grade-panel — verdict + confidence + tags + keyboard"
```

---

### Task 18: mf-design-notes (read-only history + live textarea + save)

**Spec sections:** *UI integration → Components → mf-design-notes*, *Data shapes → Design-note block*.

**Files:**
- Create: `web/src/components/mf-design-notes.ts`
- Create: `web/src/components/mf-design-notes.test.ts`

- [ ] **Step 1: Write failing tests**

```typescript
// web/src/components/mf-design-notes.test.ts
import { describe, it, expect } from 'vitest';
import { fixture, html } from '@open-wc/testing-helpers';
import './mf-design-notes';

describe('mf-design-notes', () => {
    it('renders existing notes content as read-only history', async () => {
        const el = await fixture(html`<mf-design-notes .history=${'## 2026-05-30\n\nfirst note'}></mf-design-notes>`);
        const history = el.shadowRoot!.querySelector('[data-testid="history"]')!;
        expect(history.textContent).toContain('first note');
    });

    it('emits save-note on save button click', async () => {
        const el = await fixture<any>(html`<mf-design-notes></mf-design-notes>`);
        let captured: any = null;
        el.addEventListener('save-note', (e: any) => { captured = e.detail; });
        const ta = el.shadowRoot!.querySelector('textarea') as HTMLTextAreaElement;
        ta.value = 'new thought';
        ta.dispatchEvent(new Event('input'));
        const btn = el.shadowRoot!.querySelector('[data-testid="save-btn"]') as HTMLButtonElement;
        btn.click();
        expect(captured?.content).toBe('new thought');
    });

    it('clears textarea after save', async () => {
        const el = await fixture<any>(html`<mf-design-notes></mf-design-notes>`);
        const ta = el.shadowRoot!.querySelector('textarea') as HTMLTextAreaElement;
        ta.value = 'transient';
        ta.dispatchEvent(new Event('input'));
        const btn = el.shadowRoot!.querySelector('[data-testid="save-btn"]') as HTMLButtonElement;
        btn.click();
        await el.updateComplete;
        expect(ta.value).toBe('');
    });

    it('Cmd+S triggers save', async () => {
        const el = await fixture<any>(html`<mf-design-notes></mf-design-notes>`);
        let captured: any = null;
        el.addEventListener('save-note', (e: any) => { captured = e.detail; });
        const ta = el.shadowRoot!.querySelector('textarea') as HTMLTextAreaElement;
        ta.value = 'cmd-s test';
        ta.dispatchEvent(new Event('input'));
        ta.dispatchEvent(new KeyboardEvent('keydown', { key: 's', metaKey: true }));
        expect(captured?.content).toBe('cmd-s test');
    });

    it('30s idle triggers save when textarea has content', async () => {
        // Use fake timers for deterministic test
        const { vi } = await import('vitest');
        vi.useFakeTimers();
        const el = await fixture<any>(html`<mf-design-notes></mf-design-notes>`);
        let captured: any = null;
        el.addEventListener('save-note', (e: any) => { captured = e.detail; });
        const ta = el.shadowRoot!.querySelector('textarea') as HTMLTextAreaElement;
        ta.value = 'idle test';
        ta.dispatchEvent(new Event('input'));
        await vi.advanceTimersByTimeAsync(30_000);
        expect(captured?.content).toBe('idle test');
        vi.useRealTimers();
    });
});
```

- [ ] **Step 2: Implement** per spec section "mf-design-notes" (live textarea below; read-only history above; save = button OR Cmd/Ctrl+S OR 30s idle; clears textarea after save; no autosave-flush-upward complexity).

- [ ] **Step 3: Test + commit**

Run: `cd web && npx vitest run src/components/mf-design-notes.test.ts`
Expected: 5 passed.

```bash
git add web/src/components/mf-design-notes.ts web/src/components/mf-design-notes.test.ts
git commit -m "feat(grading-ui): mf-design-notes — history + live textarea + save"
```

---

### Task 19: mf-force-graph grade mode (dedup, click-to-select, edge colouring)

**Spec sections:** *UI integration → Click-to-select-path UX*, *UI integration → Force-graph node visuals*.

**Files:**
- Modify: `web/src/components/mf-force-graph.ts`
- Modify: `web/src/components/mf-force-graph.test.ts`

- [ ] **Step 1: Write failing tests (extend existing)**

```typescript
// in mf-force-graph.test.ts — additional describe block
import './mf-force-graph';
import { fixture, html } from '@open-wc/testing-helpers';
import { describe, it, expect, beforeEach } from 'vitest';

describe('mf-force-graph grade mode', () => {
    const chains = [
        {
            topic: 'anger', vehicle: 'venom', chain_signature: 'a'.repeat(64),
            topic_synset_id: '1', vehicle_synset_id: '3', proposer: 'sonnet_v1', round: 1,
            schema_version: 'chain.v1' as const, generated_at: 'x',
            chain: [
                { phrase: 'anger', head: 'anger', synset_id: '1' },
                { phrase: 'heat', head: 'heat', synset_id: '2' },
                { phrase: 'venom', head: 'venom', synset_id: '3' },
            ],
        },
        {
            topic: 'anger', vehicle: 'fire', chain_signature: 'b'.repeat(64),
            topic_synset_id: '1', vehicle_synset_id: '5', proposer: 'sonnet_v1', round: 1,
            schema_version: 'chain.v1' as const, generated_at: 'x',
            chain: [
                { phrase: 'anger', head: 'anger', synset_id: '1' },
                { phrase: 'heat', head: 'heat', synset_id: '2' },  // shared with above
                { phrase: 'fire', head: 'fire', synset_id: '5' },
            ],
        },
    ];

    it('dedups intermediate nodes by synset_id', async () => {
        const el = await fixture<any>(html`<mf-force-graph mode="grade" .gradeChains=${chains}></mf-force-graph>`);
        await el.updateComplete;
        // Both chains pass through heat (synset_id=2) — node count should be 4, not 5
        // (topic anger + heat shared + venom + fire = 4 nodes)
        expect(el.gradeNodes.length).toBe(4);
        expect(el.gradeNodes.filter((n: any) => n.id === 'syn:2').length).toBe(1);
    });

    it('emits chain-selected on vehicle node click', async () => {
        const el = await fixture<any>(html`<mf-force-graph mode="grade" .gradeChains=${chains}></mf-force-graph>`);
        await el.updateComplete;
        let captured: any = null;
        el.addEventListener('chain-selected', (e: any) => { captured = e.detail; });
        el.handleNodeClick({ id: 'syn:3', isVehicle: true });
        // venom vehicle should match chain[0] (anger->heat->venom)
        expect(captured?.chain_signature).toBe('a'.repeat(64));
    });

    it('hides toggle below 900px viewport (mobile fallback)', async () => {
        // happy-dom doesn't naturally simulate matchMedia; use the component's own
        // viewport check.
        const el = await fixture<any>(html`<mf-force-graph mode="grade" .viewportWidth=${800} .gradeChains=${chains}></mf-force-graph>`);
        await el.updateComplete;
        // 3D library should NOT be loaded
        expect(el.threeDLoaded).toBe(false);
    });
});
```

- [ ] **Step 2: Implement grade-mode logic in mf-force-graph.ts**

The implementation:
- Adds `mode: 'browse' | 'grade'` prop, `gradeChains: ChainRecord[]` prop, `judgements: JudgementRecord[]` prop, `viewportWidth: number` prop (defaults to `window.innerWidth`).
- In grade mode, builds nodes from chain steps:
  - Node id format: `syn:<synset_id>` if synset_id is non-null; `head:<head>` otherwise; `phrase:<phrase>` as final fallback. This is the dedup key.
  - Topic, vehicles, intermediates differentiated by role.
  - Edges built per chain — DO NOT collapse edges across chains (a chain's edge belongs to that chain so verdict colouring stays disambiguable, per spec "Shared-edge verdict conflict rule").
- Click-to-select: vehicle-role node click → look up the chain(s) ending at this vehicle's synset/head → if multiple, emit `chain-selected` with the first; later iteration adds cycle/disambiguation UI. Emit event detail = full chain record.
- Edge colouring: looks up the latest judgement per chain_signature, applies colour per spec table. Selected-path edges glow override.
- Lazy 3D library load: only when `mode === 'grade' && viewportWidth >= 900` — falls back to a flat-text list view rendered inline otherwise (Task 20 handles the mobile case fully).
- **Memory gotcha**: mock `3d-force-graph` in tests per existing pattern (see `web/src/components/mf-force-graph.test.ts` for the Proxy-chainable mock; reuse).

Full implementation: see spec sections "Click-to-select-path UX" + "Force-graph node visuals".

- [ ] **Step 3: Test + commit**

Run: `cd web && npx vitest run src/components/mf-force-graph.test.ts`
Expected: existing tests + 3 new pass.

```bash
git add web/src/components/mf-force-graph.ts web/src/components/mf-force-graph.test.ts
git commit -m "feat(grading-ui): mf-force-graph grade mode — dedup, click-to-select, edge colouring"
```

---

### Task 20: Mobile flat-text fallback + mf-mobile-notes-overlay

**Spec sections:** *UI integration → Mobile flat-text fallback*.

**Files:**
- Create: `web/src/components/mf-mobile-notes-overlay.ts`
- Create: `web/src/components/mf-mobile-notes-overlay.test.ts`
- Modify: `web/src/components/mf-force-graph.ts` (flat-text path when viewport < 900)
- Modify: `web/src/components/mf-app.ts` (mount mobile notes overlay)

- [ ] **Step 1: Write tests**

```typescript
// web/src/components/mf-mobile-notes-overlay.test.ts
import { describe, it, expect } from 'vitest';
import { fixture, html } from '@open-wc/testing-helpers';
import './mf-mobile-notes-overlay';

describe('mf-mobile-notes-overlay', () => {
    it('hidden by default', async () => {
        const el = await fixture(html`<mf-mobile-notes-overlay></mf-mobile-notes-overlay>`);
        expect(el.shadowRoot!.querySelector('[data-testid="overlay"]')).toBeFalsy();
    });

    it('opens when open prop true', async () => {
        const el = await fixture(html`<mf-mobile-notes-overlay open></mf-mobile-notes-overlay>`);
        expect(el.shadowRoot!.querySelector('[data-testid="overlay"]')).toBeTruthy();
    });

    it('emits close on close-button click', async () => {
        const el = await fixture<any>(html`<mf-mobile-notes-overlay open></mf-mobile-notes-overlay>`);
        let captured = false;
        el.addEventListener('close', () => { captured = true; });
        (el.shadowRoot!.querySelector('[data-testid="close-btn"]') as HTMLElement).click();
        expect(captured).toBe(true);
    });

    it('forwards save-note from inner mf-design-notes', async () => {
        const el = await fixture<any>(html`<mf-mobile-notes-overlay open></mf-mobile-notes-overlay>`);
        let captured: any = null;
        el.addEventListener('save-note', (e: any) => { captured = e.detail; });
        const inner = el.shadowRoot!.querySelector('mf-design-notes') as any;
        inner.dispatchEvent(new CustomEvent('save-note', { detail: { content: 'mobile note' }, bubbles: true, composed: true }));
        expect(captured?.content).toBe('mobile note');
    });
});
```

- [ ] **Step 2: Implement mf-mobile-notes-overlay**

Bottom-sheet drawer (slides up over bottom 60% of viewport), embeds `mf-design-notes`, has close button. Backdrop click closes. Forwards `save-note` events.

- [ ] **Step 3: Wire flat-text path in mf-force-graph for viewportWidth < 900**

Per spec section "Mobile flat-text fallback": each chain renders as a vertical card with text arrows; tap expands verdict controls. Lazy-load of 3D library is skipped on this breakpoint.

- [ ] **Step 4: Wire mobile-notes-overlay into mf-app**

A floating action button in grade mode opens the overlay on viewports < 900px; desktop continues to show `mf-design-notes` inline.

- [ ] **Step 5: Test + commit**

```bash
cd web && npx vitest run src/components/mf-mobile-notes-overlay.test.ts
git add web/src/components/mf-mobile-notes-overlay.ts \
        web/src/components/mf-mobile-notes-overlay.test.ts \
        web/src/components/mf-force-graph.ts \
        web/src/components/mf-app.ts
git commit -m "feat(grading-ui): mobile flat-text fallback + bottom-sheet notes overlay"
```

---

### Task 21: Promote run_chain_spike.py + update Sonnet prompt for {phrase, head} output

**Spec sections:** *Head extraction backfill → Spike runner prompt update*.

**Files:**
- Create: `data-pipeline/scripts/run_chain_spike.py` (promoted from `/tmp/stagea_spike/run_spike.py`)
- Create: `data-pipeline/scripts/test_run_chain_spike.py`

- [ ] **Step 1: Promote the script + write failing test**

Test asserts: the prompt-builder function emits a prompt that requests `{phrase, head}` output structure, includes the `bad_path` anti-example block when provided, and outputs a valid JSON shape.

```python
# data-pipeline/scripts/test_run_chain_spike.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_chain_spike import build_prompt

def test_prompt_requests_phrase_and_head():
    p = build_prompt("anger", "gloss", [{"vehicle": "fire", "shared_features": [{"concept": "heat"}]}])
    assert '"phrase"' in p and '"head"' in p

def test_prompt_includes_anti_examples_when_provided():
    p = build_prompt("anger", "gloss", [{"vehicle": "fire", "shared_features": []}],
                     anti_examples=[{"chain": ["anger", "x", "fire"], "notes": "padding"}])
    assert "AVOID" in p.upper() or "Avoid" in p
    assert "padding" in p

def test_prompt_omits_anti_examples_block_when_empty():
    p1 = build_prompt("anger", "g", [{"vehicle": "fire", "shared_features": []}])
    p2 = build_prompt("anger", "g", [{"vehicle": "fire", "shared_features": []}], anti_examples=[])
    assert "AVOID" not in p1.upper() and "AVOID" not in p2.upper()
```

- [ ] **Step 2: Implement (promote `/tmp/stagea_spike/run_spike.py`)**

Copy and adapt:
- Move from `/tmp/stagea_spike/run_spike.py` → `data-pipeline/scripts/run_chain_spike.py`.
- Change prompt to require `{phrase, head}` per step (see spec → Head extraction backfill → Spike runner prompt update).
- Accept optional `anti_examples` parameter (list of `{chain, notes}`).
- Output JSONL conforming to `chain.v1` schema (compute chain_signature, snap heads via lookup_primary_synset post-Sonnet).

- [ ] **Step 3: Test + commit**

Run: `data-pipeline/.venv/bin/python -m pytest data-pipeline/scripts/test_run_chain_spike.py -v`
Expected: 3 passed.

```bash
git add data-pipeline/scripts/run_chain_spike.py data-pipeline/scripts/test_run_chain_spike.py
git commit -m "feat(grading): promote run_chain_spike.py with {phrase, head} prompt + anti-examples"
```

---

### Task 22: build_next_round_prompt.py (anti-example clustering, deterministic shuffle)

**Spec sections:** *Bootstrap loop → Anti-example selection algorithm*, *Bootstrap loop → Same-topic re-attempt policy*.

**Files:**
- Create: `data-pipeline/scripts/build_next_round_prompt.py`
- Create: `data-pipeline/scripts/test_build_next_round_prompt.py`

- [ ] **Step 1: Write failing tests**

```python
# data-pipeline/scripts/test_build_next_round_prompt.py
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_next_round_prompt import (
    select_anti_examples, deterministic_topic_shuffle, filter_substantive_notes
)

def test_filter_excludes_short_notes():
    items = [
        {"notes": "merge sideways step", "chain_signature": "a"},
        {"notes": "x", "chain_signature": "b"},
        {"notes": "", "chain_signature": "c"},
    ]
    out = filter_substantive_notes(items, min_chars=20)
    assert [x["chain_signature"] for x in out] == ["a"]

def test_select_uses_all_when_few():
    items = [{"notes": "merge: something quite long here", "chain_signature": str(i)} for i in range(3)]
    result = select_anti_examples(items, target=10)
    assert len(result) == 3

def test_select_clusters_by_tag_prefix_proportionally():
    items = (
        [{"notes": "merge: " + "x"*30, "chain_signature": f"m{i}"} for i in range(8)]
        + [{"notes": "padding: " + "x"*30, "chain_signature": f"p{i}"} for i in range(8)]
    )
    result = select_anti_examples(items, target=10, cluster_max_per_tag=4)
    merge = sum(1 for r in result if r["notes"].startswith("merge:"))
    padding = sum(1 for r in result if r["notes"].startswith("padding:"))
    assert merge <= 4 and padding <= 4
    assert len(result) <= 10

def test_deterministic_topic_shuffle_reproducible():
    topics = ["a", "b", "c", "d", "e"]
    s1 = deterministic_topic_shuffle(topics, seed_str="topics_v1")
    s2 = deterministic_topic_shuffle(topics, seed_str="topics_v1")
    assert s1 == s2

def test_deterministic_topic_shuffle_excludes_already_used(tmp_path):
    topics = ["a", "b", "c", "d", "e"]
    shuffled = deterministic_topic_shuffle(topics, seed_str="topics_v1",
                                           exclude={"b", "d"})
    assert "b" not in shuffled and "d" not in shuffled
    assert len(shuffled) == 3
```

- [ ] **Step 2: Implement**

```python
# data-pipeline/scripts/build_next_round_prompt.py
"""Build the next-round Sonnet prompt with bad_path anti-examples + topic selection.

Per spec section "Bootstrap loop → Anti-example selection algorithm":
- ≤10 bad_paths → use all
- >10 → cluster by leading tag chip (merge/padding/leap/other), proportional, max 4/cluster
- Exclude empty/short notes (< 20 chars by default)

Topic selection: deterministic shuffle of remaining-topic IDs via fixed seed (SHA256 of seed string).
Already-enriched topics (collected from prior round files) are excluded.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import random
import re
import sys
from pathlib import Path
from typing import Iterable

TAG_RE = re.compile(r"^(merge|padding|leap|other)[:\s]", re.IGNORECASE)

def filter_substantive_notes(items: list[dict], min_chars: int = 20) -> list[dict]:
    return [x for x in items if len(x.get("notes", "")) >= min_chars]

def _tag_of(notes: str) -> str:
    m = TAG_RE.match(notes)
    return m.group(1).lower() if m else "other"

def select_anti_examples(items: list[dict], target: int = 10,
                          cluster_max_per_tag: int = 4) -> list[dict]:
    items = filter_substantive_notes(items)
    if len(items) <= target:
        return items
    by_tag: dict[str, list[dict]] = {}
    for it in items:
        by_tag.setdefault(_tag_of(it.get("notes", "")), []).append(it)
    out: list[dict] = []
    for tag, group in by_tag.items():
        out.extend(group[:cluster_max_per_tag])
        if len(out) >= target:
            break
    return out[:target]

def deterministic_topic_shuffle(topics: list[str], seed_str: str,
                                 exclude: Iterable[str] = ()) -> list[str]:
    exclude_set = set(exclude)
    pool = [t for t in topics if t not in exclude_set]
    seed = int.from_bytes(hashlib.sha256(seed_str.encode()).digest()[:8], "big")
    rng = random.Random(seed)
    rng.shuffle(pool)
    return pool

# CLI entrypoint omitted here — straightforward wiring of the above + reading
# judgements_provisional.jsonl + running run_chain_spike with the augmented prompt.
# See spec for the full prompt-template block.
```

(Full CLI wiring: collect bad_paths from judgements, run select_anti_examples, deterministic_topic_shuffle the unjudged remaining topics from `spike_2_topics.json`, build prompt, invoke `run_chain_spike.main()`, write `sonnet_chains_provisional_r{N+1}.jsonl`.)

- [ ] **Step 3: Test + commit**

```bash
data-pipeline/.venv/bin/python -m pytest data-pipeline/scripts/test_build_next_round_prompt.py -v
git add data-pipeline/scripts/build_next_round_prompt.py \
        data-pipeline/scripts/test_build_next_round_prompt.py
git commit -m "feat(grading): build_next_round_prompt — clustering selector + deterministic shuffle"
```

---

### Task 23: grading_diagnostics.py (Wilson CI bad_path-rate trend test)

**Spec sections:** *Bootstrap loop → Convergence diagnostic (statistically honest)*.

**Files:**
- Create: `data-pipeline/scripts/grading_diagnostics.py`
- Create: `data-pipeline/scripts/test_grading_diagnostics.py`

- [ ] **Step 1: Write failing tests**

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from grading_diagnostics import wilson_ci, ci_overlap, convergence_verdict

def test_wilson_ci_known_values():
    # 6/20 → ~[0.146, 0.519]
    lo, hi = wilson_ci(6, 20, alpha=0.05)
    assert 0.13 < lo < 0.16
    assert 0.50 < hi < 0.53

def test_wilson_ci_edge_zero():
    lo, hi = wilson_ci(0, 20)
    assert lo == 0.0
    assert 0.0 < hi < 0.2

def test_wilson_ci_edge_n_equals_k():
    lo, hi = wilson_ci(20, 20)
    assert hi == 1.0
    assert lo > 0.8

def test_ci_overlap_overlapping():
    # CIs (0.15, 0.52) and (0.08, 0.42) overlap
    assert ci_overlap((0.15, 0.52), (0.08, 0.42)) is True

def test_ci_overlap_separate():
    # (0.30, 0.52) and (0.01, 0.24) — barely overlap (0.24 > 0.30? no) — separate
    assert ci_overlap((0.30, 0.52), (0.01, 0.24)) is False

def test_convergence_verdict_proceed_when_ci_separates():
    rounds = [
        {"round": 1, "bad_path": 6, "total": 20},
        {"round": 2, "bad_path": 4, "total": 20},
        {"round": 3, "bad_path": 1, "total": 20},
    ]
    v = convergence_verdict(rounds)
    assert v["status"] == "DOWN"

def test_convergence_verdict_flat_when_cis_overlap():
    rounds = [{"round": i+1, "bad_path": 5, "total": 20} for i in range(3)]
    v = convergence_verdict(rounds)
    assert v["status"] == "FLAT"

def test_convergence_verdict_ceiling_at_8_rounds():
    rounds = [{"round": i+1, "bad_path": 5, "total": 20} for i in range(8)]
    v = convergence_verdict(rounds)
    assert v["status"] == "CEILING"
```

- [ ] **Step 2: Implement**

```python
# data-pipeline/scripts/grading_diagnostics.py
"""Bad_path-rate convergence diagnostic with Wilson 95% CI.

Per spec: point comparisons at n=20 are statistically meaningless; use CI overlap.
Status: DOWN (proceed) / FLAT (intervention needed) / CEILING (8-round hard stop).
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path

def wilson_ci(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    z = 1.959963984540054  # ~scipy.stats.norm.ppf(1 - 0.025)
    z2 = z * z
    p = k / n
    centre = (p + z2 / (2 * n)) / (1 + z2 / n)
    margin = (z * math.sqrt((p * (1 - p) + z2 / (4 * n)) / n)) / (1 + z2 / n)
    lo = max(0.0, centre - margin)
    hi = min(1.0, centre + margin)
    return (lo, hi)

def ci_overlap(ci1: tuple[float, float], ci2: tuple[float, float]) -> bool:
    return not (ci1[1] < ci2[0] or ci2[1] < ci1[0])

def convergence_verdict(rounds: list[dict], ceiling: int = 8) -> dict:
    """rounds: [{round, bad_path, total}, ...] sorted by round ascending."""
    if len(rounds) >= ceiling:
        return {"status": "CEILING", "rounds": len(rounds),
                "message": f"hit {ceiling}-round ceiling; escalate intervention"}
    if len(rounds) < 2:
        return {"status": "INSUFFICIENT", "rounds": len(rounds)}
    # Look at last 2: do their CIs separate?
    last = rounds[-1]; prev = rounds[-2]
    ci_last = wilson_ci(last["bad_path"], last["total"])
    ci_prev = wilson_ci(prev["bad_path"], prev["total"])
    if not ci_overlap(ci_last, ci_prev) and ci_last[1] < ci_prev[0]:
        return {"status": "DOWN", "rounds": len(rounds),
                "ci_last": ci_last, "ci_prev": ci_prev}
    # Look across last 3 for flatness
    if len(rounds) >= 3:
        last3 = rounds[-3:]
        cis = [wilson_ci(r["bad_path"], r["total"]) for r in last3]
        all_overlap = all(ci_overlap(cis[i], cis[j])
                          for i in range(3) for j in range(3) if i != j)
        if all_overlap:
            return {"status": "FLAT", "rounds": len(rounds), "cis": cis}
    return {"status": "MIXED", "rounds": len(rounds)}

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--judgements", default="data-pipeline/grading/judgements_provisional.jsonl")
    args = p.parse_args()
    lines = Path(args.judgements).read_text().splitlines() if Path(args.judgements).exists() else []
    judgements = [json.loads(l) for l in lines if l.strip()]
    # Aggregate: latest-per-signature, then count bad_path per round
    latest_by_sig: dict[str, dict] = {}
    for j in judgements:
        sig = j["chain_signature"]
        if sig not in latest_by_sig or j["ts"] > latest_by_sig[sig]["ts"]:
            latest_by_sig[sig] = j
    per_round: dict[int, dict] = {}
    for j in latest_by_sig.values():
        r = j["round"]
        per_round.setdefault(r, {"round": r, "bad_path": 0, "total": 0})
        per_round[r]["total"] += 1
        if j["label"] == "bad_path":
            per_round[r]["bad_path"] += 1
    rounds = sorted(per_round.values(), key=lambda x: x["round"])
    for r in rounds:
        lo, hi = wilson_ci(r["bad_path"], r["total"])
        print(f"Round {r['round']}: bad_path {r['bad_path']}/{r['total']} = "
              f"{r['bad_path']/max(1,r['total']):.0%}  CI95: ({lo:.2f}, {hi:.2f})")
    v = convergence_verdict(rounds)
    print(f"\nVerdict: {v['status']}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Test + commit**

```bash
data-pipeline/.venv/bin/python -m pytest data-pipeline/scripts/test_grading_diagnostics.py -v
git add data-pipeline/scripts/grading_diagnostics.py \
        data-pipeline/scripts/test_grading_diagnostics.py
git commit -m "feat(grading): grading_diagnostics — Wilson-CI convergence test"
```

---

### Task 24: calibration_drift_check.py

**Spec sections:** *Bootstrap loop → Calibration-drift workflow*.

**Files:**
- Create: `data-pipeline/scripts/calibration_drift_check.py`
- Create: `data-pipeline/scripts/test_calibration_drift_check.py`

- [ ] **Step 1: Write failing tests + implement**

The script fetches a sample from `/api/grading/calibration-sample`, presents prior verdicts, and (post-re-grade) computes flip-rate. v1 is operationally simple: write a `calibration_targets.json` to disk that the UI surfaces; compare original vs latest verdict after Julian re-grades; print flip-rate.

```python
def compute_flip_rate(originals: list[dict], regrades: list[dict]) -> dict:
    """{chain_signature → label} maps. Return {n, flips, rate}."""
    by_sig = {o["chain_signature"]: o for o in originals}
    flips = 0
    counted = 0
    for r in regrades:
        sig = r["chain_signature"]
        if sig in by_sig:
            counted += 1
            if r["label"] != by_sig[sig]["label"]:
                flips += 1
    return {"n": counted, "flips": flips, "rate": flips / counted if counted else 0.0}
```

Tests assert: flip-rate calculation; threshold (≥ 0.30 → flag drift).

```bash
git add data-pipeline/scripts/calibration_drift_check.py \
        data-pipeline/scripts/test_calibration_drift_check.py
git commit -m "feat(grading): calibration_drift_check — re-grade flip-rate"
```

---

### Task 25: validate_grading_jsonl.py + pre-commit secret scan

**Spec sections:** *Pre-commit / pre-write guard*, *Sidecar → Failure modes & recovery → JSONL corruption*.

**Files:**
- Create: `data-pipeline/scripts/validate_grading_jsonl.py`
- Create: `data-pipeline/scripts/test_validate_grading_jsonl.py`
- Create: `scripts/pre_commit_secret_scan.py`

- [ ] **Step 1: Write validate_grading_jsonl + tests**

Validator reads each `data-pipeline/grading/*.jsonl` file, parses each line, checks `schema_version` is known, validates against the appropriate Pydantic model, reports per-file results. Exits non-zero on any error.

- [ ] **Step 2: Write pre_commit_secret_scan + tests**

Scans `data-pipeline/grading/` for high-entropy strings (Shannon entropy > 4.5 over runs of ≥20 chars) and common secret prefixes (`sk-`, `ghp_`, `xoxb-`, etc.). Exits non-zero if found.

- [ ] **Step 3: Document hook installation in deploy/grading/README.md**

The hook is opt-in for Julian's dev box. Not auto-installed. Document the installation command:
```bash
ln -sf $(pwd)/scripts/pre_commit_secret_scan.py .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

- [ ] **Step 4: Commit**

```bash
data-pipeline/.venv/bin/python -m pytest data-pipeline/scripts/test_validate_grading_jsonl.py -v
git add data-pipeline/scripts/validate_grading_jsonl.py \
        data-pipeline/scripts/test_validate_grading_jsonl.py \
        scripts/pre_commit_secret_scan.py \
        deploy/grading/README.md
git commit -m "feat(grading): JSONL schema validator + pre-commit secret-scan hook"
```

---

### Task 26: Documentation (READMEs + CLAUDE.md + memory)

**Spec sections:** *Documentation & onboarding*.

**Files:**
- Create: `data-pipeline/grading/README.md`
- Create: `data-pipeline/grading_sidecar/README.md`
- Modify: `CLAUDE.md`
- Memory: `~/.claude/projects/-home-agent-projects-metaforge/memory/grading_tool_landed.md`

- [ ] **Step 1: `data-pipeline/grading/README.md`** — file format definitions (chain.v1, judgement.v1, design-note block), how to start the sidecar locally (`GRADING_DEV=1 METAFORGE_GRADING_DEV_OK=1 python -m grading_sidecar.main`), how to inspect / hand-edit (don't).

- [ ] **Step 2: `data-pipeline/grading_sidecar/README.md`** — developer notes, FastAPI structure, test commands, common dev tasks.

- [ ] **Step 3: `CLAUDE.md`** — add Quick-Links row for the grading subsystem; add a brief section "Grading tool — when active" explaining the bootstrap-loop premise + deploy target.

- [ ] **Step 4: Save memory anchor**

Create memory file `grading_tool_landed.md` summarising: shipped scope, gotchas surfaced during integration (any), deploy commands, the bootstrap-loop status.

- [ ] **Step 5: Commit**

```bash
git add data-pipeline/grading/README.md data-pipeline/grading_sidecar/README.md CLAUDE.md
git commit -m "docs(grading): READMEs + CLAUDE.md grading section + memory anchor"
```

---

### Task 27: Integration smoke + first grading session

**Spec sections:** *Implementation order → 17*, *Testing → Integration smoke (manual, in spec)*.

This task is **manual** — Julian-in-the-loop.

- [ ] **Step 1: Build frontend on the `next` worktree**

```bash
cd /home/agent/projects/metaforge/.worktrees/next/web
git pull origin metaphor-graph/grading-tool   # or merge as appropriate
npm install
npm run build
```

- [ ] **Step 2: Restart the Go API on the next worktree** so it picks up the new `web/dist/`.

```bash
sudo systemctl restart metaforge-api-next
```

- [ ] **Step 3: Open `https://metaforge-next.julianit.me` on Julian's browser**

- Complete basic-auth prompt.
- Verify "[Grading Mode]" button appears in header.
- Toggle on; verify topic picker appears.
- Pick "anger" — verify force-graph constellation renders with topic node + 10 vehicle leaves + shared intermediate nodes.

- [ ] **Step 4: Grade one chain end-to-end**

- Click "fermentation" vehicle node.
- Verify grade panel opens with chain phrases inline.
- Press `L` → "Saved" toast appears.
- Verify edge re-colours.
- Reload page — verdict persists.
- Inspect `data-pipeline/grading/judgements_provisional.jsonl` — verify the row landed.

- [ ] **Step 5: Test the design-notes textarea**

- Type a paragraph; press Cmd/Ctrl+S.
- Verify save indicator + textarea clears + history block appears above.
- Verify `data-pipeline/grading/design_notes_provisional.md` has the new block.

- [ ] **Step 6: Quantitative gate check**

If grading the first 20 chains takes > 30 min (per spec "Implementation order → 17"), HALT and tune ergonomics before scaling. Otherwise proceed.

- [ ] **Step 7: Commit any docs updates from the integration session**

If the smoke surfaced issues, fix them, re-test, then:

```bash
git add -A
git commit -m "fix(grading): integration smoke fixes"
```

- [ ] **Step 8: Tag the milestone**

```bash
git tag -a grading-tool-v1 -m "Grading Tool v1 — first grading session passed"
```

---

### Task 28: (Post-v1) Round 2 prep

This task is OUT OF SCOPE FOR v1 and runs only when Julian has graded enough of round 1 to trigger round 2. The script and infrastructure exist (Task 22); the operator decides when to fire.

- [ ] Run `data-pipeline/scripts/build_next_round_prompt.py` after grading round 1.
- [ ] Inspect the generated `sonnet_chains_provisional_r2.jsonl`.
- [ ] Commit; the UI picks up round 2 chains automatically via `/api/grading/chains`.
- [ ] Run `data-pipeline/scripts/grading_diagnostics.py` after grading round 2 to check the bad_path trend.

---

## Self-review

**Spec coverage check** (per writing-plans skill):

| Spec section | Implemented in |
|---|---|
| Architecture | Tasks 1-12 (sidecar + Caddy + deploy) |
| Auth (Layer 1 basicauth) | Tasks 11-12 |
| Auth (Layer 2 secret + dev-bypass + hmac.compare_digest) | Task 2, 12 |
| Auth (fail-closed on empty secret) | Task 2 |
| Auth (Host-header allowlist + CORS) | Task 1 |
| Auth (smoke tests) | Task 12 |
| Data shapes (chain.v1, judgement.v1, schema_version) | Task 4 |
| Data shapes (chain_signature phrase-based + proposer) | Task 4 (compute_chain_signature) |
| Data shapes (endpoint canonicalisation) | Task 4 model_validator |
| Data shapes (UTF-8 NFC) | Task 3 (`_nfc` helper) |
| Persistence (fcntl.flock + fsync) | Task 3 |
| Sidecar endpoints | Tasks 5-8, 10 (autocommit) |
| Auto-commit timer | Task 9 |
| Head extraction backfill | Task 13 |
| Spike runner prompt update | Task 21 |
| UI mode toggle + probe + error | Task 15 |
| mf-topic-picker (combobox) | Task 16 |
| mf-grade-panel (keyboard shortcuts) | Task 17 |
| mf-design-notes | Task 18 |
| mf-force-graph grade mode (dedup, click-to-select) | Task 19 |
| Mobile flat-text + bottom-sheet notes overlay | Task 20 |
| Bootstrap-loop scripts | Tasks 22-24 |
| JSONL validator + pre-commit secret scan | Task 25 |
| Documentation | Task 26 |
| Integration smoke | Task 27 |
| DB ingest | OUT OF SCOPE — deferred per spec |
| Multi-head step concepts | OUT OF SCOPE — deferred per spec |

**Placeholder scan:** No "TBD"/"TODO" remain. Where implementation references "see spec" (e.g. Task 17 mf-grade-panel full visual layout), the spec contains the verbatim detail — implementer must read the spec, not improvise.

**Type consistency:** `compute_chain_signature(proposer, phrases)` defined in Task 4; called in Tasks 13, 21 with same signature. `Label` / `Confidence` literals match across `models.py` (Task 4), `grading.ts` (Task 14), and `mf-grade-panel.test.ts` (Task 17). `chain.v1` / `judgement.v1` consistent throughout. `chain_signature` is 64-char lowercase hex everywhere.

**Open risks for implementor:**
- The `rate_limit` directive in the Caddy snippet requires the `caddy-ratelimit` plugin. If not installed on the VPS, deploy.sh will fail at the `caddy validate` step. **Install before running Task 12**: `sudo caddy add-package github.com/mholt/caddy-ratelimit` then `sudo systemctl restart caddy`.
- `httpx` is needed for FastAPI TestClient; it's in Task 1's requirements.txt. If the data-pipeline venv has an older FastAPI without httpx as transitive, `pip install httpx` explicitly.

---

## Execution handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-30-metaphor-grading-tool.md`. Two execution options:**

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration. **REQUIRED SUB-SKILL:** `superpowers:subagent-driven-development`.

2. **Inline Execution** — execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints for review.

**Which approach?**
