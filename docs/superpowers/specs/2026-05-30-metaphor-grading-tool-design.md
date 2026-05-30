# Metaphor Grading Tool — v1 Design

**Date:** 2026-05-30
**Branch:** `metaphor-graph/grading-tool` (new, off `metaphor-graph/enrich-stage-a`)
**PIPELINE.md filing:** new Backlog entry — promoted to Next when grading-tool work starts (see *PIPELINE filing* section near the end).
**Predecessors:**
- Stage A hardening spec — `docs/superpowers/specs/2026-05-29-metaphor-graph-stage-a-hardening.md`
- Chain-spike outcome — 20-topic Sonnet ordered-chain test, `/tmp/stagea_spike/sonnet_chains.jsonl` (200 chains, mean 5.3 steps, near-zero adjacent substring-overlap padding hint, 57% multi-word steps, qualitatively rich but non-trivial `bad_path` rate visible on eyeball — see `metaforge-next.julianit.me` rendering of the spike output)
- Metaphor-graph schema base — `docs/superpowers/specs/2026-05-28-metaphor-graph-schema-design.md`

**Memory anchors:** `eval_as_preference_tracking_instrument`, `metaphor_graph_vs_property_graph`, `metaphor_graph_schema_base_landed`, `loop2_cohort_haiku_only`, `mobile_remote_brevity`, `critique_when_invited`, `snapping_reconciliation_deferred`.

**Spec status:** revised 2026-05-30 after a 6-lens adversarial review (security, UX, data model, bootstrap loop, scope/YAGNI, completeness critic). All findings triaged; Tier-1 fixes inline; deferred items called out in scope/risks.

---

## Why this exists

The chain-spike proved Sonnet **can** produce ordered, coherent metaphor traversals when given the right prompt envelope (creative license + minimal-leap, no-padding instruction). Eyeball confirmed v1 quality with two visible failure modes:

1. **Merged / backfilled paths** — Sonnet chooses a vehicle, then bridges by introducing a sideways concept that doesn't strictly follow from the previous step. Example: `anger → hostility → toxicity → secretion → venom` (`secretion` is sideways).
2. **Padding** — too many near-redundant steps. Example: `time → passage → flow → current → direction → irreversibility → river` (`time → flow → river` would carry the same meaning).

Running the full 200-cohort at this quality wastes Sonnet tokens and pollutes the metaphor graph. Instead we do an **active-learning bootstrap loop**: capture Julian's per-path verdicts on the 20 existing chains, extract `bad_path` examples, inject them as anti-examples in the next-round Sonnet prompt, iterate ~5 rounds of 20 until the bad_path rate trend flattens (or until we hit a different intervention threshold), THEN scale to the remaining cohort.

The grading tool is the **instrument** of this loop. It is also the deliberate **seed of the production Forge UI in edit mode** — every component built here is the start of the queued Forge UI milestone.

### Strategic value

- **Calibrated training signal** — `bad_path` verdicts are first-class negative examples for both the generator's prompt-iteration *and* later LLM-as-judge scale-out. Explicit negatives beat absence-of-positive.
- **Eval/generator unification** — per `eval_as_preference_tracking_instrument`, eval and generator are the same problem. Judgements ARE the training data for graph-completion (eventual scorer) and for prompt-refinement (immediate generator improvement).
- **Latent metaphor yield** — chains' intermediate steps are themselves candidate topic→step pairs. 200 chains × ~3.3 intermediates ≈ ~660 bonus metaphor candidates per round (harvested only at DB-ingest time post-bootstrap; not a v1 deliverable).

---

## Goals & non-goals

**Goals**

1. Render chains as a **unified force-graph per topic**, with intermediate and vehicle nodes deduplicated across chains by `head_concept` (or `synset_id` where snapped).
2. Capture per-path verdicts (`live` / `dead` / `bad_path` / `irrelevant`) with **3-step confidence** (`high` / `med` / `low`) and optional 2-3-row notes; **save-on-click** with explicit success/failure feedback.
3. Capture **cross-session design notes** (append-only file; UI shows file-loaded history above a live textarea; no autosave-flush-upward complexity).
4. **Keyboard-first** input on desktop (single-key verdicts, arrow navigation). Mouse + thumb-tap mirror keyboard.
5. Block nuisance script traffic via auth on the public subdomain; fail-closed if any secret is missing.
6. Persist all data to the **repo** (committed, with `_provisional` filename markers) so nothing is lost; **auto-commit timer** flushes WIP to git every 15 min.
7. Be the seed of the production Forge UI: integrate into the existing thesaurus app as a mode toggle, NOT a separate route.
8. Support the bootstrap loop: round-based chain ingestion, anti-example injection script, calibration-drift sampler.

**Non-goals**

- Multi-user / proper IAM — single user; nuisance protection only.
- DB ingest of judgements — deferred until prompt settles (see *DB ingest* section).
- 3D rendering on mobile — flat-text grading on narrow screens.
- Multi-hop graph traversal — Sonnet generates single-path chains; The Bridge feature owns multi-hop graph search.
- LLM-as-judge / synthetic re-grading — separate later phase.
- Editing chains directly — read-only; verdicts only.
- Step-level granularity verdicts — verdict is on the whole path.
- Per-judgement weight controls / what-if reranking — confidence only (see `feedback_critique_when_invited`).
- Round-to-round chain re-runs of the same topic — fresh 20 topics from the unenriched cohort per round.
- Feeding `dead` / `irrelevant` verdicts into the next round's prompt — bootstrap loop's anti-example feed is `bad_path` only (chain-quality signal). Pair-level negatives (`dead` / `irrelevant`) are captured in JSONL for later analysis but not piped into Sonnet for v1.
- Auto-clustering of `bad_path` notes by failure mode — manual selection for v1; clustering is a follow-up if patterns emerge.
- Multi-head step concepts with weights — speculative complexity ahead of evidence (see `feedback_critique_when_invited`).

---

## Architecture

```
Browser (mobile or desktop)
    ↕ HTTPS
Caddy on metaforge-next.julianit.me  (existing site block; path-scoped routing added)
    │
    ├─ /api/grading/healthz   → reverse_proxy 127.0.0.1:53775         (NO auth — probe path)
    │
    ├─ /api/grading/*         → basicauth (cost-12 bcrypt)
    │                            request_body { max_size 1MB }
    │                            rate_limit per-IP (1 r/s, burst 10)
    │                            log access (no headers, no body) → journald
    │                            reverse_proxy 127.0.0.1:53775 {
    │                                header_up X-Grading-Secret {env.GRADING_SECRET}
    │                            }
    │
    └─ (default)              → reverse_proxy 127.0.0.1:8081           (existing Metaforge Go API
                                  serving SPA + /forge/* + /thesaurus/*)
                          │
                          ▼
              Python sidecar (FastAPI, systemd service — API only, no static serving)
              ├─ Auth: X-Grading-Secret required on every non-healthz route
              │        (hmac.compare_digest; UNLESS GRADING_DEV=1, asserted unset in prod systemd)
              ├─ Host-header allowlist: metaforge-next.julianit.me, localhost:5173 (dev)
              ├─ CORS: Access-Control-Allow-Origin = same origin only
              ├─ GET  /api/grading/healthz             → 200; no auth; frontend probe
              ├─ GET  /api/grading/stats               → counts, last-write timestamp, schema_version
              ├─ GET  /api/grading/topics              → lean topic list (no per-topic counts; UI derives)
              ├─ GET  /api/grading/chains?topic=…      → unions sonnet_chains_provisional_r*.jsonl
              ├─ GET  /api/grading/judgements?topic=…  → raw stream (UI applies latest-per-signature)
              ├─ POST /api/grading/judgements          → append (fcntl-flock + plain append + fsync)
              ├─ GET  /api/grading/design-notes        → full markdown content
              ├─ POST /api/grading/design-notes        → append timestamped block
              └─ GET  /api/grading/calibration-sample?n=10&round=1 → re-grading sample
                          │
                          ▼
                  data-pipeline/grading/  (committed, _provisional)
                  ├─ sonnet_chains_provisional_r1.jsonl
                  ├─ sonnet_chains_provisional_r2.jsonl … rN
                  ├─ judgements_provisional.jsonl
                  ├─ design_notes_provisional.md
                  └─ README.md  (file-format definitions, how to start sidecar locally)
                          │
                          ▼
                  Auto-commit timer (sidecar runs `git add … && git commit -m "wip(grading): autosave"`
                  every 15 min if any file changed; logs to journald)
```

**Subdomain decision (2026-05-30):** grading deploys on `metaforge-next.julianit.me` (the existing staging tier) via **path-scoped routing** within its existing Caddy block — NOT a new subdomain. `dev.julianit.me` is freed up as scratch. The frontend (with grading mode baked into `mf-app`) ships unchanged to both `production` and `next` worktrees via the existing deploy convention. On `metaforge.julianit.me` (prod), the grading toggle is hidden because the frontend probes `/api/grading/healthz` at mount and that path is not routed there (returns 404 from the Go API). On `metaforge-next.julianit.me` the probe returns 200 (sidecar) and the toggle shows. Same SPA artifact, different deploy targets, graceful degradation. Promotion of grading to prod is a future Caddy snippet edit on `metaforge.julianit.me`, not a re-architecture.

**Why** every layer:

- **Caddy basic-auth** is the cheapest blanket nuisance-block; runs before any app code; native browser handles the prompt; mobile remembers per-host.
- **Caddy rate-limit** caps the bcrypt-verification CPU surface (a known DoS amplifier at cost 14; we drop to cost 12 + per-IP cap).
- **Caddy request-body cap** prevents accidental 1GB pastes from a runaway frontend bug.
- **Defense-in-depth `X-Grading-Secret`** means a future Caddy misconfig doesn't open the sidecar; sidecar refuses traffic without the header. Both ends fail closed on missing/empty secret.
- **Sidecar in Python (FastAPI)** — same venv as the existing pipeline; Pydantic validation + OpenAPI for free; lighter than wiring this into the Go API while the data model is still in flux. Acceptably heavy for a single-user tool because the venv already has the deps.
- **127.0.0.1 bind** — sidecar never directly internet-reachable; Caddy is the only path in. Host-header allowlist defends against DNS-rebinding.
- **JSONL persistence** — matches the existing pipeline's append-only / replay-friendly pattern; trivially diff-able in git; no schema migration risk; ingest into the DB is a one-shot later transform.
- **Repo persistence** — Julian explicitly requested this so judgements + notes are versioned and durable; auto-commit timer closes the data-loss-between-commits window.

---

## Auth (defense-in-depth, fail-closed)

**Threat model:** opportunistic crawlers / scripts discovering the subdomain via DNS, CT logs, or scan. Not protecting against targeted attacker.

### Layer 1 — Caddy HTTP Basic Auth (path-scoped)

We patch the **existing** `metaforge-next.julianit.me` Caddy snippet (which currently reverse-proxies everything to the thesaurus Go API on 127.0.0.1:8081) to add two new path-scoped blocks for grading. Default-path behaviour (thesaurus + SPA) is preserved.

`deploy/caddy/metaforge-next.caddy.template` (committed; rendered to `/etc/caddy/conf.d/metaforge-next.caddy.active` at deploy time):

```caddy
metaforge-next.julianit.me {
    # 1) Healthz: NO auth — used by the frontend to probe whether grading is available.
    handle /api/grading/healthz {
        reverse_proxy 127.0.0.1:53775
    }

    # 2) Grading API: auth + rate-limit + body cap + secret-injection.
    handle /api/grading/* {
        basicauth {
            julian {$JULIAN_BCRYPT_HASH}
        }

        request_body {
            max_size 1MB
        }

        # rate_limit per-IP, 1 r/s sustained, burst 10 (caddy-ratelimit plugin)
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
            # do NOT log headers or body — both contain credentials
        }

        reverse_proxy 127.0.0.1:53775 {
            header_up X-Grading-Secret {$GRADING_SECRET}
        }
    }

    # 3) Default: existing thesaurus + SPA via the Go API.
    reverse_proxy 127.0.0.1:8081
    # ... (existing cache headers, error-page directives, etc. — preserved from current snippet)
}
```

The `production` worktree's `metaforge.julianit.me` snippet is NOT modified — its `/api/grading/*` paths simply 404 (no handle block), the frontend probe sees that, and the grading toggle stays hidden on prod.

- `JULIAN_BCRYPT_HASH` and `GRADING_SECRET` come from `/etc/default/caddy` (Caddy systemd EnvironmentFile, mode `0640 caddy:caddy`).
- **Password requirement:** Julian generates a 24-char password via `openssl rand -base64 24`, stores it ONLY in his password manager. Bcrypt hash via `caddy hash-password` at cost 12. The hash is safe in the repo because the password is high-entropy.
- **Cost 12, not 14** — cost-14 bcrypt verification (~1+ CPU-sec on the VPS) plus no rate limit was a DoS amplifier. Cost 12 + rate limit balances brute-force cost vs DoS surface.
- **`{$GRADING_SECRET}` fail-closed:** Caddy substitutes `$VAR` from the environment. If `GRADING_SECRET` is unset, the substituted header is empty. The deploy script (see *Deployment* section) asserts both env vars are non-empty before reload; Caddy reload fails if not.

### Layer 2 — Sidecar shared-secret header

Sidecar reads the same `GRADING_SECRET` from `/etc/metaforge/grading_secret` (mode `0600`, owned by sidecar user, NOT readable by `caddy` user — deliberately isolated). On startup:

```python
SECRET = Path("/etc/metaforge/grading_secret").read_text().strip()
if not SECRET:
    raise SystemExit("FATAL: GRADING_SECRET file is empty; refusing to start.")
```

Every request must carry `X-Grading-Secret: <secret>`. Sidecar compares via `hmac.compare_digest` (constant-time). Mismatch → 401.

**`/api/grading/healthz`** is exempted from the secret check inside the sidecar (the route handler bypasses the auth dependency). Caddy proxies it publicly without basic-auth so the frontend can probe `grading-availability` cheaply on every mount. Probe response is intentionally minimal (`{"ok": true}`) — leaks no state. systemd/monitoring on the VPS can also hit `http://127.0.0.1:53775/api/grading/healthz` directly.

### Dev-mode bypass (explicit and asserted)

Local development sets `GRADING_DEV=1` in shell env. Sidecar's auth dependency:

```python
def verify_secret(req: Request, x_grading_secret: str = Header(default="")):
    if os.environ.get("GRADING_DEV") == "1":
        return
    if not hmac.compare_digest(x_grading_secret, SECRET):
        raise HTTPException(401)
```

**The production `metaforge-grading.service` systemd unit MUST set `Environment=GRADING_DEV=` (empty)** AND assert on startup that `os.environ.get("GRADING_DEV") != "1"`, refusing to start otherwise. This makes the dev bypass impossible to accidentally enable in prod. Smoke-tested in CI / deploy script.

### Host-header allowlist + CORS

FastAPI middleware:

- `Host:` must be `metaforge-next.julianit.me` (prod), `localhost:53775`, or `localhost:5173` (dev). Otherwise 421 Misdirected.
- `Access-Control-Allow-Origin` = same-origin only. No cross-origin XHR/fetch.

Defends against DNS-rebinding attacks targeting `127.0.0.1:53775` from a hostile origin in Julian's browser.

### Frontend invariant

The frontend bundle MUST NOT contain `X-Grading-Secret` — Caddy injects it; the browser never sees it. A `grep` check on `web/dist/` post-build (CI step) refuses commits that leak the header name from frontend code paths.

### Considered and rejected

- **OAuth / SSO** — overkill for nuisance protection.
- **IP allowlist** — Julian's IPs change.
- **Secret-URL-path** — leaks via referrers, screenshots.
- **Cookie/JWT session** — basic auth is stateless and free.
- **mTLS / client certs** — cert distribution friction on mobile.
- **Sidecar-level password auth** — adds frontend login UI; Caddy basic is browser-native.

### Auth smoke tests (CI)

- `curl -s -o /dev/null -w "%{http_code}" https://metaforge-next.julianit.me` → 401 (no basic auth)
- `curl -u julian:wrongpass https://metaforge-next.julianit.me/api/grading/healthz` → 401 (path is unproxied; Caddy basic-auth still blocks)
- Production startup: `GRADING_DEV=1 systemctl start metaforge-grading` → service fails to start (assertion).
- Empty-secret tests: clear `/etc/default/caddy`, reload → reload fails. Clear `/etc/metaforge/grading_secret`, restart sidecar → sidecar refuses to start.
- Constant-time test: hmac.compare_digest in place (unit test).

---

## Data shapes

All persisted as JSONL or markdown in `data-pipeline/grading/`. Committed to git. **UTF-8 encoded, NFC-normalised, no BOM.** Every JSONL record carries a `schema_version` field; readers fail-fast on unknown versions.

### Chain record (`sonnet_chains_provisional_rN.jsonl`)

One JSONL line per (topic, vehicle, proposer) chain:

```json
{
  "schema_version": "chain.v1",
  "topic": "anger",
  "topic_synset_id": "12345",
  "vehicle": "venom",
  "vehicle_synset_id": "67890",
  "proposer": "sonnet_v1",
  "round": 1,
  "chain": [
    {"phrase": "anger",     "head": "anger",     "synset_id": "12345"},
    {"phrase": "hostility", "head": "hostility", "synset_id": "54321"},
    {"phrase": "toxicity",  "head": "toxicity",  "synset_id": "44441"},
    {"phrase": "secretion", "head": "secretion", "synset_id": "33312"},
    {"phrase": "venom",     "head": "venom",     "synset_id": "67890"}
  ],
  "chain_signature": "<sha256 hex, 64 chars>",
  "generated_at": "2026-05-30T03:14:00Z"
}
```

Field notes:

- `synset_id` values are **bare integer-as-text** (matching the existing `synsets` PK shape: `'1'`, `'12345'`, …). The earlier draft used illustrative `lemma-pos-sense` strings; that was wrong — examples now match the real DB.
- **Steps are objects** `{phrase, head, synset_id}`. `phrase` is the verbatim Sonnet emission; `head` is the single-word indexing concept; `synset_id` is the result of `lookup_primary_synset(head)` (nullable).
- **Endpoint canonicalisation invariant** (enforced by ingest validator): `chain[0].phrase == topic`, `chain[0].head == topic`, `chain[0].synset_id == topic_synset_id` (and the symmetric for `chain[-1]`/vehicle). If they disagree at write time, write fails. This eliminates the "which is canonical when they disagree" ambiguity by making them required-equal.
- **`synset_id` nullable** for non-endpoint steps when `lookup_primary_synset(head)` returns null. Chain still ingests; logged for monitoring.
- **`proposer` is `sonnet_v1`** (renamed from `haiku_sonnet_v1`). Sonnet generates the chains; Haiku is only used for head-extraction backfill, which is annotation metadata, not generation. Documented mapping for clarity.
- **`chain_signature`** = `sha256(":".join([proposer] + [normalise(step.phrase) for step in chain]))` where `normalise(s) = unicodedata.normalize("NFC", s).strip().lower()`. **Phrase-based, snap-independent, proposer-included.** Stable under head re-extraction, snap drift, or future snapping reconciliation. The earlier `(synset_id or head or phrase)` formula was unstable — discarded.
- **Sonnet head validation** at ingest time (round 2+ chains): `head ∈ phrase.split()` OR `head` cosine-close (≥0.5) to phrase's word-embedding centroid. Chains failing validation are still written but flagged `head_validation: "failed"` in a separate field for monitoring. Round-1 backfill chains skip this check (head came from Haiku post-hoc).

### Judgement record (`judgements_provisional.jsonl`)

One JSONL line per verdict, append-only:

```json
{
  "schema_version": "judgement.v1",
  "ts": "2026-05-30T07:14:00Z",
  "judged_by": "julian",
  "round": 1,
  "topic": "anger",
  "topic_synset_id": "12345",
  "vehicle": "venom",
  "vehicle_synset_id": "67890",
  "proposer": "sonnet_v1",
  "chain_signature": "<sha256 hex>",
  "label": "bad_path",
  "confidence": "high",
  "notes": "merged path — secretion sideways to reach venom",
  "supersedes_ts": null
}
```

- `label` ∈ `{live, dead, bad_path, irrelevant}` — v1 UI collapse. JSONL stores the literal user click. **DB-ingest mapping** (see *DB ingest* section below) maps `dead` → `dead_lakoff` and requires the schema migration that adds `bad_path` to the CHECK constraint before any ingest runs.
- `confidence` ∈ `{high, med, low}` (3-step, default `high`). Cleaner UX than continuous slider; nothing downstream uses fine-grained values.
- `notes` ≤ 1000 chars (Pydantic `max_length`); free-text; optional.
- `supersedes_ts` is the timestamp of the prior verdict for this `chain_signature` (only set on re-grade). Lets calibration-drift analysis distinguish "Julian changed his mind" from "fat-fingered mobile UI" by inspecting time delta.

**JSONL is append-only.** The UI applies latest-per-`chain_signature` on read (sidecar serves raw stream; UI does the merge — keeps the sidecar simple and the merge logic in one place). Re-grade history is preserved in the JSONL forever; DB-ingest later picks the latest per signature, losing the history at that point — acknowledged in *DB ingest* section.

### Design-note block (`design_notes_provisional.md`)

Append-only markdown. The UI shows the file's existing content as **read-only history above** a fresh live textarea; on save, the live textarea's content becomes a new timestamped block appended to the file, and the textarea clears. No autosave-flush-upward; no debounced rapid-save:

```markdown
## 2026-05-30T07:14:00Z

Sonnet keeps backfilling steps when it picks a slightly-exotic vehicle.
The bad_path rate seems higher for vehicles two or more semantic hops
from the topic — worth tightening the prompt to require minimal-leap
from step 1.
```

Save trigger: explicit "Save" button OR Cmd/Ctrl+S OR 30-second idle-timeout (whichever comes first).

### Pre-commit / pre-write guard

A pre-commit hook scans `data-pipeline/grading/` for high-entropy strings and common secret patterns (API key prefixes, password-like patterns). Refuses commit if any flagged. Belt-and-braces against accidental secret leakage in notes fields.

Plus a one-line UI hint near both note inputs: *"Public repo — no secrets, names, or personal context."*

---

## UI integration

### Grading-availability probe (graceful degrade)

On mount, `mf-app` fires a single GET to `/api/grading/healthz`:

- **200** → grading is available here; render the mode toggle; respect last-used `localStorage` mode (default `grade` on `metaforge-next.julianit.me`).
- **401** → grading is available but the user hasn't authed yet; render the toggle (browser shows the basic-auth prompt when the user clicks any auth'd grading endpoint).
- **404 / network error / 5xx** → grading is NOT available here (prod URL, sidecar down, local dev without `GRADING_DEV=1`); the toggle is hidden entirely and `mode` is forced to `browse`. The SPA collapses cleanly to the read-only thesaurus.

This means the SAME `web/dist/` artifact ships to both the `production` and `next` worktrees: it's the path-routing on the Caddy host that determines whether grading mode is reachable. No URL-aware build-time flags.

### Default landing state

`metaforge-next.julianit.me` defaults to **Grading Mode** on first load when the probe returns 200/401 (no need to discover a toggle). `localStorage` remembers the last-used mode within a host. A header button **[Grading Mode] ↔ [Browse Mode]** flips. On `localhost:5173` (dev), default is `browse` to preserve normal thesaurus dev flow; `grade` becomes accessible once `GRADING_DEV=1` is set and the local sidecar is running.

### Components

**New** (under `web/src/components/`):

- `mf-topic-picker.ts` — filterable combobox (not bare dropdown) of topics with chain data. Each entry shows topic phrase only. Emits `topic-selected` with `{topic, topic_synset_id}`. UI derives judgement counts from cached `/api/grading/judgements` (no server-side topic-count endpoint).
- `mf-grade-panel.ts` — verdict controls + per-chain notes textarea. Visible when a chain is selected.
  - **Four verdict buttons** (Live / Dead / Bad Path / Irrelevant), with **keyboard shortcuts L / D / B / I** as primary input. Keyboard binding shown next to each button label.
  - **Confidence picker:** three buttons (High / Med / Low), default High; keyboard 1/2/3.
  - **Notes textarea:** 2-3 rows, optional, `max_length: 1000`. Failure-mode tag chips (`merge`, `padding`, `leap`, `other`) above the textarea — clicking a chip prepends the tag to the notes; supports clustering at round-prompt-build time.
  - **Next chain:** Enter or Right arrow; **Previous:** Left arrow; **Skip without grading:** Esc.
  - **Save feedback:** explicit toast — "Saved" green, or "Failed — retrying" red with retry-then-final-error flow.
  - **Re-grade banner:** when opening an already-judged chain, banner shows previous verdict + confidence + ts; banner reads "Re-grading — your previous verdict was X; new submit will supersede"; explicit "Cancel" closes without changing. Re-grades carry `supersedes_ts`.
- `mf-design-notes.ts` — file-content history at top (read-only, scrollable, latest first) + fresh live textarea below. Save button or Cmd/Ctrl+S or 30s idle → POST → textarea clears + new block appears in history.
- `mf-error-banner.ts` — system-level error states (sidecar down, last save failed, dual-device-sync conflict, etc.).
- `mf-mobile-notes-overlay.ts` — bottom-sheet quick-append for design notes on mobile, accessible from the grading card without leaving the grading view.

**Modified:**

- `mf-app.ts` — adds `mode: 'browse' | 'grade'` state (plain private field, NOT `@state()` per Lit memory), localStorage persist, mode toggle button, conditional rendering of subcomponents. On 401, forces `mode = 'browse'`.
- `mf-force-graph.ts` — adds `mode: 'browse' | 'grade'` prop. In `grade` mode: accepts chain data + judgements, dedups nodes by `head` / `synset_id`, emits `chain-selected` event. Lazy-loads 3D library only on desktop (≥900px viewport).
- `mf-search-bar.ts` — hides in grade mode.

### Click-to-select-path UX

In grade mode the force-graph contains:
- 1 topic node (centre).
- N vehicle leaf nodes.
- M intermediate concept nodes deduplicated across chains by `(synset_id, head)` composite key (synset_id-first when present; head-string when not).

**Vehicles are the click targets** in 3D mode. On mobile, the flat-text card is the click target.

1. Click a vehicle node (or tap a card).
2. Force-graph highlights the specific chain's edges (looked up from chain data; not graph traversal). Other chains' edges dim. **If multiple chains terminate at the same vehicle (multi-proposer or path variation), a small "1 of N chains for this vehicle" selector appears at the top of the grade panel — left/right arrows or up/down keys cycle.**
3. `mf-grade-panel` opens (right column desktop / bottom modal mobile).
4. Verdict shortcut key or click → POST `/api/grading/judgements`. On success: edge re-colour to verdict colour; toast "Saved"; panel advances to next un-judged chain (Enter / Right arrow).
5. On POST failure: client retries 3× with exponential backoff (1s, 3s, 9s). If all fail, toast "Failed — your verdict will retry on next save attempt"; verdict held in localStorage `pending_judgements` queue, flushed on next successful POST or page reload.
6. Already-judged chains stay coloured (un-judged = bright; verdict-coloured = dimmed). Click re-opens with the re-grade banner.
7. **Shared-edge verdict conflict rule:** edges belong to *chains*, not abstract graph edges. Two chains sharing a step but with different verdicts render as two coloured edges between the same node pair (offset slightly visually). The selected-path glow overrides verdict colour for the active chain only.

### Visual progress affordances

- Topic picker shows `(7/10)` count next to each topic when there's any judgement data; un-judged topics show no count.
- Inside a topic, the grade panel shows "X of Y chains judged" + a "Next un-judged" shortcut button.
- Verdict colours pinned against the existing thesaurus `web/src/styles.css` palette (specific tokens decided at implementation; pinned in the implementation plan).
- **Non-colour signal** alongside verdict colours: edge-stroke pattern (solid = live, dashed = dead, dotted = bad_path, hairline = irrelevant) so colour isn't the only differentiator.

### Mobile flat-text fallback (`@media (max-width: 899px)`)

- Force-graph lazy import skipped; 3D library never loads on mobile.
- Each chain renders as a vertical card: `topic phrase → step phrase → … → vehicle phrase` (text arrows).
- Tap a card to expand: verdict buttons row + confidence buttons + notes input below.
- **Design-notes overlay** is reachable from the grading card via a "Notes" floating action button → bottom-sheet drawer (slides up over the bottom 60% of the viewport; can scroll history while keeping grading state).
- Keyboard shortcuts not assumed on mobile; tap-only mirrors keyboard semantics.

### Dual-device sync

- Sidecar is authoritative; localStorage caches only UI state (mode, last-topic, pending_judgements queue), never canonical data.
- On topic load: re-fetches `/api/grading/judgements?topic=…` even if a cached version exists.
- If two POSTs for the same `chain_signature` arrive (e.g. phone + desktop both grading), both append; UI's latest-per-signature picks the latest `ts`. Acceptable.

### Error states

| State | Render |
|-------|--------|
| `/api/grading/topics` returns empty | Banner: "No grading data yet — run a round" + link to docs |
| `/api/grading/chains?topic=…` returns empty | "This topic has no chains" + back button |
| `/api/grading/judgements` 5xx | Banner: "Couldn't load history — retry"; verdict actions disabled until recovered |
| POST verdict 5xx | Inline toast retry (3×); on final failure → pending_judgements queue + persistent banner "N verdicts pending" |
| 401 from any endpoint | Force `mode = 'browse'` + banner: "Auth expired — refresh to re-authenticate" |
| Sidecar unreachable (network error) | Banner: "Grading service unavailable — verdicts will queue locally" |
| Auto-commit failed (logged from sidecar `/api/grading/stats`) | Subtle indicator: "Last autosave 32 min ago" (instead of green "Up to date") |

---

## Sidecar (Python FastAPI)

**Stack:** Python 3.12 + FastAPI + uvicorn (already in the data-pipeline venv via transitive deps; same venv reused). Lives in `data-pipeline/grading_sidecar/`. Runs under systemd (`metaforge-grading.service`).

### Endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/api/grading/healthz` | none (public; Caddy proxies without auth) | Probe; minimal response (`{"ok": true}`); used by frontend graceful-degrade |
| GET | `/api/grading/stats` | secret | Counts, last-write ts, schema_version, autocommit_last_run |
| GET | `/api/grading/topics` | secret | Lean topic list (no per-topic counts) |
| GET | `/api/grading/chains?topic=<lemma>` | secret | Unions all `sonnet_chains_provisional_r*.jsonl`, filters by topic if given. Skips malformed lines (logged). |
| GET | `/api/grading/judgements?topic=<lemma>` | secret | Raw stream of judgement lines (UI applies latest-per-signature). |
| POST | `/api/grading/judgements` | secret | Append a verdict (Pydantic-validated). |
| GET | `/api/grading/design-notes` | secret | Full markdown content of design_notes_provisional.md. |
| POST | `/api/grading/design-notes` | secret | Append a timestamped block. |
| GET | `/api/grading/calibration-sample?n=10&round=1` | secret | Returns N random round-K chains for re-grading (calibration drift workflow). |

### Persistence — corrected atomicity

**The earlier `.tmp + rename` pattern was wrong for append-only JSONL** (would either lose history or race-clobber). Correct pattern:

```python
import fcntl, os, json

def append_jsonl(path, record):
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with open(path, "a", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
```

- Advisory `fcntl.flock` — safe on crash (kernel releases lock automatically).
- `O_APPEND` semantics — single-write atomicity for lines ≤ PIPE_BUF (~4KB).
- `fsync` ensures durability before responding 200.
- **Concurrent processes (sidecar + offline scripts):** the same flock is taken by `build_next_round_prompt.py` etc. before reading or writing. All grading-tool scripts use a shared helper module that wraps file ops with this lock.

### Auto-commit timer

Sidecar runs a background asyncio task every 15 minutes:

```python
async def autocommit_loop():
    while True:
        await asyncio.sleep(15 * 60)
        try:
            subprocess.run(
                ["git", "-C", REPO_ROOT, "add", "data-pipeline/grading/"],
                check=True, capture_output=True,
            )
            result = subprocess.run(
                ["git", "-C", REPO_ROOT, "commit", "-m",
                 f"wip(grading): autosave {datetime.utcnow().isoformat()}"],
                capture_output=True,
            )
            # result.returncode == 1 means "nothing to commit" — fine
            log.info("autocommit done", extra={"returncode": result.returncode})
        except Exception as exc:
            log.error("autocommit failed", exc_info=exc)
```

Does NOT push automatically (would require credentials on the VPS). Julian pushes from his dev machine.

### Observability

- Structured JSON logs per request: `method, path, status, latency_ms, user_agent`.
- Structured log per POST verdict: `topic, vehicle, chain_signature, label, confidence`.
- `/api/grading/stats` returns counters (POST count, error count) and last-write timestamps.
- Frontend shows "Last sync 4s ago" indicator next to mode toggle.

### Systemd unit

`/etc/systemd/system/metaforge-grading.service` — derived from the hardened `metaforge-api.service` template per memory `deploy_servers` notes:

```ini
[Service]
Type=simple
User=metaforge-grading
EnvironmentFile=/etc/default/metaforge-grading
Environment=GRADING_DEV=
ExecStart=/path/to/venv/bin/uvicorn …
Restart=on-failure
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
# DO NOT use ProtectHome=read-only — known gotcha that broke metaforge-api (per memory)
ReadWritePaths=/path/to/data-pipeline/grading/
CapabilityBoundingSet=
```

`User=metaforge-grading` is a new dedicated user; owns `/etc/metaforge/grading_secret`; not in `caddy` group.

### Failure modes & recovery

| Failure | Detection | Recovery |
|---------|----------|----------|
| Sidecar crash | systemd Restart=on-failure | restart; pending_judgements in browser localStorage retries |
| JSONL line malformed | GET endpoint skips + logs at WARN | `scripts/validate_grading_jsonl.py` reports count; manual fix from git history |
| Auto-commit fails | sidecar log + `/api/grading/stats` returns degraded; banner in UI | manual `git add && git commit` from VPS; investigate (probably hook failure) |
| Disk full | sidecar 5xx on POST | UI queues verdicts; banner; ops alert via journald |
| Concurrent write race | (defended by flock; should not happen) | logged; no data loss expected |
| Stale localStorage from a prior session | server is authoritative; sidecar's `chain_signature` is canonical | UI always re-fetches on topic load |

### Testing

- pytest with tmp JSONL fixtures: append, GET, validation, malformed-line skip, lock under concurrent processes (subprocess test).
- Constant-time secret-comparison unit test.
- Schema-version unknown → reject test.
- Auto-commit subprocess mock test.
- Auth fail-closed tests (empty secret, missing file).

---

## Bootstrap loop

### Round mechanics

1. **Round 1 setup** (one-shot, pre-grading):
   - Head-extraction subagent runs (below) → `sonnet_chains_provisional_r1.jsonl`.
   - Commit.

2. **Julian grades round 1** via the UI:
   - Verdicts append to `judgements_provisional.jsonl`.
   - Cross-session notes accumulate in `design_notes_provisional.md`.
   - Auto-commit timer flushes every 15 min.

3. **Round 2 trigger** (Julian's call):
   - Run `scripts/build_next_round_prompt.py`:
     - Reads `judgements_provisional.jsonl`, applies latest-per-signature merge.
     - Extracts chains with `label == "bad_path"`.
     - **Anti-example selection algorithm (no longer "random or most-recent"):**
       - If ≤ 10 bad_paths exist → use all.
       - If > 10 → cluster by leading `notes` tag chip (`merge` / `padding` / `leap` / `other`), pick proportionally (up to 4 per cluster). If chip distribution is empty, fall back to random sample with note-length-> 20-char filter (skip chains without substantive notes).
       - Always exclude chains with empty notes (the prompt's `Why it failed:` line is meaningless without a reason; bad signal for Sonnet).
     - Selects next 20 unenriched topics: **deterministic shuffle of remaining-topic IDs via a fixed seed (the SHA256 of `topics_v1`) — documented; means topic ordering across rounds is reproducible and order-bias is randomised once at project start**.
     - Composes prompt with anti-examples + new topics.
     - Calls Sonnet with updated `{phrase, head}` output requirement → `sonnet_chains_provisional_r2.jsonl`.
   - **Partial-round recovery:** if Sonnet rate-limits or errors mid-round, the script writes whatever completed to `sonnet_chains_provisional_r2_partial.jsonl`; a `--resume` flag picks up from where it stopped and atomically promotes `_partial` → final on completion. Idempotent re-runs are safe.

4. **Commit round 2**, Julian grades, iterate.

### Carry-forward policy (settled)

**Early-round chains stay in the pool.** All graded chains, regardless of round, contribute to the eventual metaphor graph at DB-ingest time. Bad_paths are excluded by virtue of their label (graph_edges view filters to `label='live'`); the rest are graph-quality. Early-round live chains are kept because they ARE good chains — the prompt evolves, not the cohort's intrinsic quality.

### Convergence diagnostic (statistically honest)

`scripts/grading_diagnostics.py` (runs manually):
- Reads judgements grouped by round.
- Computes per-round `bad_path_rate` AND a Wilson 95% CI (n=20 per round has ±~0.13 noise on a 0.10 rate — point comparisons are statistically meaningless).
- Reports trend with CI overlap:
  - "Trending DOWN (CIs separate)" — proceed
  - "FLAT or overlapping CIs across last 3 rounds" — intervention candidate (model swap / structural prompt rewrite)
  - "Hard ceiling: 8 rounds reached — escalate" — regardless of rate

The 0.05 absolute floor is now framed as *aspirational*, not a stop signal — the CI-overlap test is the real diagnostic.

### Calibration-drift workflow

At round 3 (and every round thereafter), the script `scripts/calibration_drift_check.py`:
- Fetches `/api/grading/calibration-sample?n=10&round=1` (sidecar returns 10 random round-1 chains).
- Marks them in a separate `calibration_targets.json` file.
- UI surfaces a "Calibration drift check" button next to the topic picker — opens a focused view of those 10 chains with their prior verdict shown alongside.
- Julian re-grades them (re-grade banner shows prior verdict).
- Script computes label-flip rate (re-grade label ≠ original label).
- **Threshold:** if flip rate ≥ 0.30 (3+ of 10 flipped), the diagnostic flags drift; recommended action is to grade a wider re-sample (50 chains) before trusting any new round's trend signal.

### Same-topic re-attempt policy

Fresh 20 topics per round (Non-goal). But within a round, the same `(topic, vehicle)` pair can recur in future rounds because Sonnet may pick the same vehicle for a different topic (e.g. `wolf` for `aggression` after `wolf` for `predator`). **Vehicle is not banned across rounds.** Pair-level rejections (`dead`, `irrelevant`) are NOT used to ban Sonnet from re-proposing the vehicle on future topics — see Non-goals (out of scope for v1 bootstrap-loop).

### Strategic-value harvest

The "~660 latent metaphor candidates from intermediates" mentioned in Strategic Value is **not harvested by the grading tool itself**. It's a property of the data the tool collects, realised at DB-ingest time when chain steps become `metaphor_bridges` nodes. Implementation order does not include a separate harvest step; the harvest IS the DB-ingest migration.

---

## Head extraction backfill

The existing 20-topic chain spike output has flat-string steps. Before round 1 grading can start, backfill `{phrase, head, synset_id}` per step.

### Subagent flow

Spawn one subagent via `Agent` tool:

1. **Read** `/tmp/stagea_spike/sonnet_chains.jsonl` (20 lines, 200 chains, ~660 intermediate steps + 220 endpoint steps).
2. **Collect unique phrases** (~880 max, fewer with dedup).
3. **Head extraction:**
   - Single-word phrase → `head = phrase.lower()`.
   - Multi-word phrase (~57%) → batched Haiku 4.5 calls (~50 phrases/call, ~10 calls) with prompt:
     > "For each phrase below, return the single-word concept that the phrase most centres on — typically a noun. Prefer a head likely to be re-used across other metaphor traversals over a hyper-specific one. Output strict JSON: `{\"phrases\": [{\"phrase\": \"...\", \"head\": \"...\"}, …]}`."
4. **Snap** each unique head via `lookup_primary_synset` (Python, fast, free). `synset_id` is null on miss.
5. **Validate:** for each step, `head ∈ phrase.split()` OR `head` cosine-close (≥0.5) to phrase's FastText centroid. Flag failures (don't reject).
6. **Build augmented chains** with new step-object shape + compute `chain_signature`.
7. **Write** `data-pipeline/grading/sonnet_chains_provisional_r1.jsonl`, commit.

Cost: ~10 Haiku batched calls × $0.005 ≈ $0.05 (±$0.05 with retries). Negligible.

### Spike runner prompt update (round 2+)

`scripts/run_chain_spike.py` (promoted from `/tmp/stagea_spike/run_spike.py` into the repo) updates its prompt:

```
For EACH step in the chain, return BOTH the displayable phrase AND a single-word head concept.

- "phrase": the human-readable phrase (single or multi-word).
- "head": the single-word concept the phrase centres on — typically a noun, ideally one likely to be re-used across other metaphor traversals. The "head" is what we use to index the step into the metaphor graph.

Output:
{
  "topic": "...",
  "vehicles": [
    {"vehicle": "...", "chain": [{"phrase": "...", "head": "..."}, …]}
  ]
}
```

---

## Deployment & CI

### Caddy snippet management (patch existing metaforge-next snippet)

The existing `next` worktree already manages a `metaforge-next.caddy.template` for the staging host. The grading-tool work **adds the two path-scoped `handle` blocks above** (`/api/grading/healthz` and `/api/grading/*`) to that template, alongside the existing default `reverse_proxy 127.0.0.1:8081`. No new subdomain, no new Caddy site block.

`deploy/grading/deploy.sh` extends the existing `next` worktree's deploy convention:

```bash
set -euo pipefail
test -n "${JULIAN_BCRYPT_HASH:?}"   # fail-closed on missing
test -n "${GRADING_SECRET:?}"

# Render the patched metaforge-next snippet (template lives in deploy/caddy/)
envsubst < deploy/caddy/metaforge-next.caddy.template \
    > /etc/caddy/conf.d/metaforge-next.caddy.active

# Validate before reload so a broken snippet doesn't take the staging site down.
caddy validate --config /etc/caddy/Caddyfile

# Apply
systemctl reload caddy
systemctl restart metaforge-grading

# Post-deploy smoke
curl -fsS http://127.0.0.1:53775/api/grading/healthz
curl -fsS https://metaforge-next.julianit.me/api/grading/healthz
curl -fsS -u julian:wrongpass https://metaforge-next.julianit.me/api/grading/stats \
    && { echo "FAIL: auth bypass" >&2; exit 1; } || true   # expected 401
```

`.active` rendered file is gitignored (matches existing two-site deploy convention). `dev.julianit.me` snippet is unchanged — it stays scratch as Julian wants.

### Frontend build → VPS

The frontend is **served by the existing Metaforge Go API** on `127.0.0.1:8081` (per the existing `production`/`next` worktree convention), NOT by the sidecar. The grading mode toggle is baked into `mf-app`, so the same `web/dist/` artifact ships to both worktrees via the existing deploy scripts. On the `next` worktree the grading toggle activates (because the sidecar is reachable); on `production` it stays hidden via the healthz probe.

This means: no new frontend deploy plumbing. Re-run the existing `next` worktree's deploy after building `web/` and the updated SPA lands. The sidecar is API-only — it does not serve static files.

### CI checks (project pre-commit / future GitHub Actions)

- `grep -r "X-Grading-Secret" web/dist/ && exit 1` — frontend must not leak the header name.
- `scripts/validate_grading_jsonl.py` — schema_version + line-level parse over `data-pipeline/grading/*.jsonl`.
- Pytest sidecar suite.
- Vitest frontend suite.

### Rollback

Sidecar: `systemctl rollback metaforge-grading` (or `git checkout <prev> && systemctl restart`). Caddy snippet: revert in repo, run `deploy/grading/deploy.sh`.

---

## DB ingest (deferred, with concrete migration plan)

When the bootstrap loop converges (per convergence diagnostic) AND Julian decides:

1. **Schema migration:**
   - Add `bad_path` to `metaphor_judgments.label` CHECK constraint. Requires SQLite table rebuild — explicit migration script (`scripts/migrate_add_bad_path.sql`) using the standard `CREATE new → INSERT old → DROP old → RENAME` pattern.
   - The schema migration lands on `metaphor-graph/schema-base` BEFORE the branch is merged to main (it's currently unmerged), so the CHECK constraint is right from the start. No post-merge migration needed.
2. **Chain ingest** — `sonnet_chains_provisional_r*.jsonl` → `metaphor_bridges` (multi-step bridges with phrase + head + synset_id per step). Stage A re-model (per Stage A hardening spec section "Bridge model") becomes mandatory at this point.
3. **Judgement ingest** — `judgements_provisional.jsonl` → `metaphor_judgments`. Map `dead` → `dead_lakoff`. Apply latest-per-signature merge before insert (the `UNIQUE(bridge_id, judged_by)` constraint enforces one verdict per chain per judge; re-grade history is lost in the DB but preserved in the JSONL forever as the audit trail).
4. **Promotion:** `*_provisional.jsonl` files move to `data-pipeline/grading/legacy/`, retained for historical audit. Canonical names without `_provisional` are reserved for post-ingest streams (when grading continues against DB-backed data).
5. **`prompt_version` annotation:** each ingested `metaphor_bridge` row carries a `proposer_version` indicating the round it came from, so future analyses can distinguish bootstrap-era data from post-settle data.

Trigger: manual (Julian runs the migration script). No automatic trigger.

---

## Documentation & onboarding

- **CLAUDE.md (project root):** add the grading subsystem to the "Quick Links" table and a brief "Grading tool — when active" section explaining the bootstrap-loop premise.
- **`data-pipeline/grading/README.md`** (committed): file format definitions, how to start sidecar locally (`uvicorn …` + `GRADING_DEV=1` env), how to read judgements, how to run the next-round prompt builder.
- **`data-pipeline/grading_sidecar/README.md`**: developer notes for the sidecar (FastAPI app structure, test commands, common dev tasks).
- **Memory anchor**: post-implementation, save a `grading_tool_landed.md` memory recording what shipped + any gotchas surfaced during integration.

---

## PIPELINE.md filing

Add to `docs/roadmap/PIPELINE.md` Backlog:

> **Metaphor Grading Tool — bootstrap-loop instrument** *(spec'd 2026-05-30, plan-pending)* — single-user web UI integrated into the thesaurus app as a grading mode. Captures live/dead/bad_path/irrelevant verdicts on Sonnet-generated chains; persists to JSONL in `data-pipeline/grading/`; auto-commits every 15 min. Auth via Caddy basic + sidecar secret. The seed of the production Forge UI. Spec: `docs/superpowers/specs/2026-05-30-metaphor-grading-tool-design.md`.

Promote to Next when implementation work starts.

---

## Settled decisions

| Decision | Outcome |
|----------|---------|
| Form factor | Grading toggle in the existing thesaurus app; NOT a separate route. |
| Deployment subdomain | `metaforge-next.julianit.me` (existing staging tier). Path-scoped routing within the existing Caddy site block — NOT a new subdomain. `dev.julianit.me` stays untouched as scratch. Promotion to prod (`metaforge.julianit.me`) is a future Caddy snippet edit, not a re-architecture. |
| Frontend distribution | Same `web/dist/` artifact ships to both `production` and `next` worktrees via existing deploy. Grading toggle activates only where the sidecar is reachable (graceful-degrade via `/api/grading/healthz` probe). |
| API path namespace | All grading endpoints live under `/api/grading/*`. Default `/` and `/forge/*` / `/thesaurus/*` paths still hit the existing Go API on 8081 unchanged. |
| Sidecar serves static files? | NO — sidecar is API-only. The existing Go API on 8081 serves `web/dist/` (per existing thesaurus convention). |
| Default mode on metaforge-next.julianit.me | `grade` (no toggle discovery needed). |
| Persistence layer | Repo-committed JSONL + markdown, `_provisional` filename markers, under `data-pipeline/grading/`. UTF-8 NFC, no BOM. Schema-versioned. |
| Auto-commit | Sidecar runs `git add … && git commit -m 'wip(grading): autosave'` every 15 min if any change. No push. |
| Auth | Caddy HTTP Basic (cost-12 bcrypt + high-entropy 24-char password) + defense-in-depth `X-Grading-Secret` (fail-closed both ends) + rate limit + host allowlist + request-body cap + no header logging. |
| Caddy snippet location | `deploy/caddy/metaforge-next.caddy.template` (patched copy of the existing next-worktree template) in repo; rendered to `/etc/caddy/conf.d/metaforge-next.caddy.active` at deploy time. `.active` file gitignored per existing convention. `dev.caddy` snippet unchanged. |
| Local-dev auth bypass | `GRADING_DEV=1` env-gated; production systemd unit asserts unset and fails to start if set. |
| Backend | Python FastAPI sidecar, bound to 127.0.0.1:53775, served by systemd. API only — no static-file serving. |
| Port number rationale | 53775 inherited from the chain-spike's HTTP server (no specific tie to that infra anymore now that the dev subdomain is freed; the port is just an available high-port. Adjusting to e.g. 8082 is fine if a more memorable choice is preferred during implementation). |
| 3D rendering | Reuses existing `mf-force-graph` (3d-force-graph). Desktop ≥900px only. Lazy-loaded. |
| Mobile | Flat-text grading cards + bottom-sheet design-notes overlay. No 3D library load. |
| Chain step shape | `{phrase, head, synset_id}` — backfilled for existing data via subagent + Haiku; new rounds emit directly via updated Sonnet prompt. `synset_id` is bare integer-as-text (matching `synsets` PK). |
| Head validation | `head ∈ phrase.split()` OR cosine-close to phrase centroid (≥0.5). Failures flagged not rejected. |
| `chain_signature` | `sha256(":".join([proposer] + [normalise(step.phrase) for step in chain]))` — phrase-based, snap-independent, proposer-included. Stable. |
| Endpoint canonicalisation | `chain[0]` and `chain[-1]` MUST equal top-level topic/vehicle fields per all three subfields. Enforced at write. |
| Proposer naming | `sonnet_v1` (NOT `haiku_sonnet_v1`). Haiku's role is annotation-only. |
| Shared-node rendering | Force-graph dedups intermediate + vehicle nodes by `(synset_id, head)`. Click-to-select highlights one path. Shared-edge verdict-conflict: per-chain edges render separately (offset). |
| Verdict labels (JSONL) | `live` / `dead` / `bad_path` / `irrelevant`. UI shows literal labels. DB-ingest maps `dead` → `dead_lakoff` + adds `bad_path` to CHECK (schema migration). |
| Confidence | 3-step `high`/`med`/`low` (NOT continuous slider). Default `high`. |
| Keyboard shortcuts | L/D/B/I (verdicts), 1/2/3 (confidence), Enter/Right (next), Left (prev), Esc (skip). |
| Save feedback | Explicit toast (saved / failed-retrying / queued-locally). 3× retry with backoff. |
| Re-grade flow | Banner shows prior verdict; explicit "Re-grading — your previous verdict was X" message; new write carries `supersedes_ts`. |
| Notes capture | Per-judgement (2-3 rows textarea + tag chips `merge/padding/leap/other`, optional) AND cross-session (large textarea, append-on-save, no autosave-flush-upward). |
| Bootstrap loop carry-forward | All graded chains retained for eventual graph (early-round live chains kept; bad_paths excluded by label, not by round). |
| Anti-example selector | Cluster by tag chip → proportional sample (up to 4/cluster); empty-notes excluded; deterministic shuffle for topic ordering with documented seed. |
| Partial-round recovery | `_partial` file + `--resume` flag in `build_next_round_prompt.py`. |
| Convergence diagnostic | Wilson 95% CI overlap test across 3 rounds; 8-round hard ceiling. 0.05 floor is aspirational. |
| Calibration drift | `scripts/calibration_drift_check.py` + UI surfacing; flip-rate ≥ 0.30 → flag drift. |
| Filterable combobox | `mf-topic-picker` uses combobox (filter + scroll), not bare dropdown. |
| Non-colour signalling | Edge-stroke pattern alongside verdict colour. |
| Verdict colour palette | Reference existing `web/src/styles.css` palette tokens. |
| Pre-commit secret scan | Pre-commit hook scans `data-pipeline/grading/` for high-entropy / common-secret patterns. UI hint near note inputs. |
| DB ingest trigger | Manual; post-convergence. Schema migration lands on `metaphor-graph/schema-base` BEFORE that branch is merged. |
| `dead_synonym` vs `dead_lakoff` split | Out of scope for v1 UI; ingest maps `dead` → `dead_lakoff`. Restore the split if patterns demand it. |
| Multi-head step concepts with weights | Deferred (footgun — see `feedback_critique_when_invited`). |

---

## Risks & mitigations (revised)

| Risk | Severity | Mitigation |
|------|---------|-----------|
| bcrypt offline-crack against repo-committed hash | low | high-entropy 24-char password; cost-12 bcrypt; Caddy rate-limit caps online attempts. |
| Caddy/sidecar secret desync during rotation | medium | Deploy script asserts both env vars before reload; outage window is the reload itself (~1s); rotation is a 5-min op. |
| DoS via crawler hitting bcrypt | medium | Caddy `rate_limit` plugin per-IP; cost-12 (not 14). |
| DNS-rebinding attack on 127.0.0.1:53775 | low | sidecar Host-header allowlist + CORS same-origin only. |
| Public repo leak via judgement notes | medium | pre-commit hook scans for entropy/secret patterns; UI hint near inputs. |
| Verdict POST failure → lost click | medium | 3× retry + localStorage `pending_judgements` queue + persistent banner. |
| JSONL line corruption | low | line-level skip + log + `validate_grading_jsonl.py` pre-commit check. |
| Dual-device verdict race | low | server authoritative; latest-`ts` wins on read. Acceptable. |
| Auto-commit failure (e.g. permissions) | low | sidecar log + `/api/grading/stats` exposes last successful commit; UI surfaces "stale" indicator. |
| WIP loss between commits | low | 15-min auto-commit window; banner shows time-since-last-commit. |
| Calibration drift | medium | `calibration_drift_check.py` at round 3+; flip-rate ≥0.30 triggers wider re-sample. |
| Bad_path-rate convergence noise at n=20 | medium | Wilson CI test, not point comparison; 8-round hard ceiling. |
| Snap drift invalidating `chain_signature` | mitigated | Signature is phrase-based, snap-independent. (Was a critical issue in v1 draft; fixed.) |
| Atomic-append data loss | mitigated | fcntl.flock + plain append + fsync. (Was a critical issue in v1 draft; fixed.) |
| Local-dev bypass leaking to prod | mitigated | systemd unit asserts `GRADING_DEV` unset; deploy script enforces. |
| Sonnet emits unsnappable head | low | `synset_id = null`; chain still ingests; logged for monitoring. |
| Mobile force-graph performance | n/a | Disabled below 900px; flat-text fallback. |
| Dense graph (>40 nodes per topic) | low | per-topic chain ceiling explicit (40 chains per topic) — assert and error if exceeded. |
| UTF-8/Unicode in phrases | low | NFC normalisation pinned; non-ASCII heads may snap null (acceptable). |
| Caddy directive ordering — `handle` blocks must be evaluated BEFORE the default `reverse_proxy 127.0.0.1:8081`, or grading paths silently get the Go API's 404 | medium | Caddy evaluates `handle` blocks by specificity (longest path prefix wins) — `/api/grading/*` outranks `/`. Pinned in deploy.sh smoke-test (curl `/api/grading/healthz` must hit sidecar, not Go API). |
| Caddy reload to rotate grading secrets briefly affects thesaurus paths too (single Caddy reload reloads the whole config) | low | Reload is <1s; thesaurus serves stale connections through the reload. Acceptable for staging-tier work. |
| Production Caddy snippet drifts behind staging's grading additions, then a future "promote grading to prod" edit forgets a path | medium | Document the staging↔prod snippet relationship in `deploy/caddy/README.md` so the eventual promotion is a documented diff, not a re-derivation. |
| Frontend graceful-degrade probe leaks "grading is here" to anyone hitting prod/staging | low | `/api/grading/healthz` returns a static `{"ok": true}` — no state leak. Acknowledged as expected behaviour for the probe pattern. |

---

## Implementation order (sketch for `writing-plans`)

1. **Auth foundation** — patch `deploy/caddy/metaforge-next.caddy.template` with the two `handle /api/grading/*` blocks (healthz + auth'd); add `deploy/grading/deploy.sh`; generate 24-char password (Julian's password manager) + bcrypt hash; populate `/etc/default/caddy` env-vars (`JULIAN_BCRYPT_HASH`, `GRADING_SECRET`); create `/etc/metaforge/grading_secret` (mode 0600); validate Caddy config; smoke-test that existing thesaurus paths still 200, grading paths 401 without auth and 200 with; assert empty-secret fail-closed.
2. **Sidecar skeleton** — FastAPI app in `data-pipeline/grading_sidecar/`, all endpoints stubbed; pytest scaffolding green; auth dependency (`hmac.compare_digest`, dev-bypass via `GRADING_DEV=1`); host-allowlist middleware; `/api/grading/healthz` 127.0.0.1-only.
3. **Sidecar persistence + locking** — `append_jsonl` helper (flock + fsync), `read_jsonl_skip_malformed`, schema-version validation; full pytest coverage.
4. **Auto-commit task** — asyncio loop, subprocess `git add && git commit`, log + `/api/grading/stats` integration.
5. **Head-extraction backfill subagent** — produces `data-pipeline/grading/sonnet_chains_provisional_r1.jsonl`, committed.
6. **Systemd service install** — `metaforge-grading.service`, dedicated user, hardening pinned (no ProtectHome), verify autocommit runs.
7. **Frontend mode toggle + topic picker (combobox)** — `mf-app` mode state, `mf-topic-picker` combobox, localStorage persist.
8. **Force-graph grade mode** — chain data input, dedup logic, click-to-select, edge colouring + stroke-pattern, lazy-load 3D library on desktop.
9. **Grade panel + keyboard shortcuts** — verdict + confidence buttons with keys, tag chips, save toast, retry queue, re-grade banner.
10. **Design-notes component** — file-content history + fresh textarea + save flow (button/Cmd-S/idle).
11. **Mobile flat-text fallback + bottom-sheet notes overlay** — responsive split, mobile-specific notes affordance.
12. **Error states + banners** — sidecar-down, queue-pending, 401 force-mode-browse, last-sync indicator.
13. **`scripts/build_next_round_prompt.py`** — anti-example clustering selector, deterministic topic shuffle, partial-round resume.
14. **`scripts/grading_diagnostics.py`** + **`scripts/calibration_drift_check.py`** — Wilson CI test, drift flow.
15. **`scripts/validate_grading_jsonl.py`** + pre-commit hook + secret-scan hook.
16. **Documentation** — `data-pipeline/grading/README.md`, `data-pipeline/grading_sidecar/README.md`, CLAUDE.md update, PIPELINE.md filing, memory anchor.
17. **Integration smoke + Julian's first grading session on round 1** — verify the loop end-to-end before committing to round 2. Quantitative gate: if first 20 chains take > 30 min, halt and tune ergonomics.
18. **Round 2 ship** — run `build_next_round_prompt.py`, generate `sonnet_chains_provisional_r2.jsonl` with the updated Sonnet prompt, commit.

---

## Spec self-review

Pass 2 (post-adversarial-review revision):

- **Placeholder scan:** no TBDs, no TODOs, no vague requirements that lack acceptance criteria. All 5 prior open questions are now resolved in *Settled decisions*.
- **Internal consistency:** auth (Caddy + sidecar + dev bypass), data shapes (snap-independent signature, endpoint canonicalisation), sidecar (fcntl-flock atomicity), UI (keyboard shortcuts + retry queue), bootstrap loop (cluster-based anti-example selection, Wilson CI), DB-ingest (schema migration on schema-base branch) all reference the same fields, files, and invariants. Re-read pass found no contradictions.
- **Scope check:** ~18-step implementation order is sized for a single plan; complexity is calibrated (FastAPI + 3D + auth) for the stated value (the bootstrap-loop instrument + Forge-UI-seed).
- **Ambiguity check:** previously-ambiguous points (label collapse, signature formula, endpoint dup canonical, port choice, Caddy-snippet location) now have explicit settled decisions. Multi-chain-same-vehicle, shared-edge verdict conflict, partial-round recovery, calibration-drift operationalisation all spec'd concretely.
- **Adversarial-review coverage:** of 30+ findings across 6 lenses, Tier-1 critical-multi-lens issues (atomic-append, chain_signature instability, bcrypt+memorable password, dev-bypass contradiction, label/CHECK mismatch, missing keyboard shortcuts) are all fixed. Tier-2 issues (anti-example clustering, convergence statistics, calibration-drift operationalisation, dual-device sync, observability, deployment, documentation) addressed. Tier-3 (UI polish, naming pedantry) noted as plan-time decisions.
