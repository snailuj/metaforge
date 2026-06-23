# data-pipeline/grading_sidecar/

FastAPI sidecar for the Metaphor Grading Tool.
Runs on port 53775; deployed at `metaforge-next.julianit.me` under path-scoped Caddy routing (`/api/grading/*`).

---

## Stack

| Component | Version |
|-----------|---------|
| Python | 3.12 |
| FastAPI | >=0.110,<0.120 |
| uvicorn | >=0.27 (with standard extras) |
| Pydantic | v2 (>=2.5,<3.0) |
| pytest + pytest-asyncio | test harness |
| httpx | FastAPI TestClient transport |

See `requirements.txt` for pinned ranges.

---

## Module layout

```
grading_sidecar/
├── main.py           — ASGI app factory; middleware registration order matters (see Auth below)
├── app.py            — FastAPI instance + lifespan; mounts route modules
├── auth.py           — X-Grading-Secret validation (hmac.compare_digest) + HostAllowlistMiddleware
├── autocommit.py     — background thread: git commit data-pipeline/grading/ every 15 min
├── models.py         — Pydantic models: ChainRecord, JudgementRecord, DesignNotePost, ChainStep
├── paths.py          — module-level path constants (monkey-patched by tests; keep as plain constants)
├── persistence.py    — fcntl-flock + append + fsync JSONL writers; chain union reader
├── routes/
│   ├── healthz.py    — GET /api/grading/healthz (no auth; Caddy probe path)
│   ├── chains.py     — GET /api/grading/chains?topic=…
│   ├── judgements.py — GET + POST /api/grading/judgements
│   ├── design_notes.py — GET + POST /api/grading/design-notes
│   ├── stats.py      — GET /api/grading/stats
│   ├── topics.py     — GET /api/grading/topics
│   └── calibration.py — GET /api/grading/calibration-sample?n=10&round=1
└── tests/
    ├── conftest.py
    ├── test_app.py
    ├── test_auth.py
    ├── test_autocommit.py
    ├── test_chains_endpoint.py
    ├── test_design_notes_endpoint.py
    ├── test_judgements_endpoint.py
    ├── test_models.py
    ├── test_persistence.py
    └── test_topics_stats_calibration.py
```

---

## Auth

Two layers, both enforced in production:

1. **Caddy basic-auth** — cost-12 bcrypt password. Caddy blocks unauthenticated requests at the edge before they reach the sidecar. The `/api/grading/healthz` path is exempt (probe path; no auth).

2. **`X-Grading-Secret` header** — validated inside the sidecar on every non-healthz route via `hmac.compare_digest`. Caddy injects the secret automatically via `header_up X-Grading-Secret {env.GRADING_SECRET}`; the browser never sees the raw value.

**Middleware ordering note:** `add_middleware()` prepends, so the last-registered middleware is the outermost layer. `HostAllowlistMiddleware` is registered after `CORSMiddleware` so host-allowlist runs first on inbound requests.

**Dev bypass:** `GRADING_DEV=1` disables both the `X-Grading-Secret` check and the host-allowlist. Must not be set in the production systemd unit (asserted at startup; the service fails-closed if it is).

Allowed hosts: `metaforge-next.julianit.me` (prod) + `localhost:5173` (Vite dev server).

---

## Running locally

```bash
cd /home/agent/projects/metaforge
GRADING_DEV=1 METAFORGE_GRADING_DEV_OK=1 \
    data-pipeline/.venv/bin/python -m grading_sidecar.main
```

Healthz check:

```
http://localhost:53775/api/grading/healthz
```

---

## Running tests

```bash
cd /home/agent/projects/metaforge
data-pipeline/.venv/bin/python -m pytest data-pipeline/grading_sidecar/tests/ -v
```

Expect ~62 tests. All tests use in-memory / temp-directory fixtures — no real JSONL files are read or written.

---

## Deploy

Artefacts live under `deploy/grading/`:

| File | Purpose |
|------|---------|
| `deploy.sh` | Installs the systemd service and Caddy snippet on the VPS |
| `metaforge-grading.service` | systemd unit template |
| `metaforge-grading.env.example` | Environment variable template (do not commit real values) |

Quick reference — provision secrets on the operator's box first (never in the repo):

```bash
PWD=$(openssl rand -base64 24)
SECRET=$(openssl rand -hex 32)
caddy hash-password --plaintext "$PWD"   # → bcrypt hash for Caddy config

# Then on VPS:
sudo tee -a /etc/default/caddy <<EOF
JULIAN_BCRYPT_HASH=<hash>
GRADING_SECRET=<secret>
EOF
echo -n "$SECRET" | sudo tee /etc/metaforge/grading_secret >/dev/null
sudo chmod 600 /etc/metaforge/grading_secret

sudo /home/agent/projects/metaforge/deploy/grading/deploy.sh
```

---

## Reference

- **Authoritative design spec:** `docs/superpowers/specs/2026-05-30-metaphor-grading-tool-design.md`
- **Implementation plan:** `docs/superpowers/plans/2026-05-30-metaphor-grading-tool.md`
- **Data directory (JSONL files):** `data-pipeline/grading/README.md`
