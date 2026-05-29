# Metaphor Graph Stage A — Dry-Run Hardening Plan

**Spec:** `docs/superpowers/specs/2026-05-29-metaphor-graph-stage-a-hardening.md`
**Branch:** `metaphor-graph/enrich-stage-a`
**Discipline:** TDD (RED → GREEN → COMMIT) per task. UK English. Atomic commits.
**Run cmds:** tests from `data-pipeline/`: `.venv/bin/python -m pytest scripts/<file> -q`. Go build: `export PATH="/usr/local/go/bin:$PATH"; (cd api && go build -o /tmp/metaforge_stagea ./cmd/metaforge)`.

## Parallelisation / file ownership

- **Wave 1 (serial, foundation):** Task A. Everything else imports from it — must land first.
- **Wave 2 (5 parallel agents, disjoint files):** Tasks B, C, D, E, F. One module+test pair each, no overlap. Agents do RED→GREEN but **do not** run git; orchestrator commits each pair after verifying.
- **Wave 3 (serial):** Task G (run module), then Task H (verification run, orchestrator-only).

Established gotchas (from the original Stage A build): test files need `sys.path.insert(0, str(Path(__file__).parent))` before local imports; in-memory fixtures that exercise **writers** must be transactional (`sqlite3.connect(":memory:")`, NOT autocommit); `property_vocab_curated` fixtures need a `vocab_id` column; idempotency is detected by COUNT(*) delta (the `IntegrityError` branch is unreachable but kept as belt-and-braces).

---

## Wave 1 — Task A: Relocate `lookup_primary_synset` into `metaphor_graph.py`

**Files:** `metaphor_graph.py` (add), `evaluate_aptness.py` (re-import), `test_metaphor_graph.py` (add test). Verify `test_evaluate_aptness.py` stays green.

**Why:** the endpoint resolver lives in `evaluate_aptness.py`; importing that heavy module into every ingest script is wrong. Move it to the snapping home; `evaluate_aptness` re-imports it so its public API (and tests) are unchanged.

- **RED** — in `test_metaphor_graph.py`, add a test that imports the resolver from its new home and resolves a word that is in the `lemmas` table but NOT in `property_vocab_curated` (the case `snap_concept_string` misses):
  ```python
  from metaphor_graph import lookup_primary_synset
  def test_lookup_primary_synset_resolves_via_lemmas_table(...):
      # fixture: synset + lemma present, NOT in property_vocab_curated
      assert lookup_primary_synset(conn, "recursion") is not None
  ```
  Fails: `cannot import name 'lookup_primary_synset' from 'metaphor_graph'`.
- **GREEN** —
  1. Read the *full* current `lookup_primary_synset` in `evaluate_aptness.py` (incl. its inner `_direct` and lemmatised-variant fallback). Move it **verbatim** into `metaphor_graph.py`. If it lemmatises, reuse `metaphor_graph`'s existing `_get_lemmatiser()` rather than duplicating; move any private helper it depends on.
  2. In `evaluate_aptness.py`, replace the `def lookup_primary_synset(...)` with `from metaphor_graph import lookup_primary_synset  # re-exported; canonical home is metaphor_graph` (keep the name importable for existing callers/tests).
- **VERIFY** — `pytest scripts/test_metaphor_graph.py scripts/test_evaluate_aptness.py -q` both green.
- **COMMIT** — `refactor(metaphor-graph): relocate lookup_primary_synset to metaphor_graph; evaluate_aptness re-imports`.

---

## Wave 2 (parallel) — Task B: Topic pre-flight → `lookup_primary_synset`

**Files:** `metaphor_graph_enrich_topics.py`, `test_metaphor_graph_enrich_topics.py`.

- **RED** — extend the test fixture with a word present in `lemmas`/`synsets` but absent from `property_vocab_curated` (e.g. `'recursion'`); assert it now lands in `snapped`, not `dropped`. Fails against current `snap_concept_string`.
- **GREEN** — in `snap_topics`, swap `snap_concept_string(conn, t["word"])` → `lookup_primary_synset(conn, t["word"])` (import from `metaphor_graph`). Rename the drop reason `"no_curated_synset"` → `"no_synset"`; update the existing assertion accordingly.
- **COMMIT** — `fix(metaphor-graph): topic pre-flight resolves via lookup_primary_synset (63.5%→100% coverage)`.

## Wave 2 — Task C: Haiku ingest vehicle → `lookup_primary_synset`

**Files:** `metaphor_graph_enrich_haiku.py`, `test_metaphor_graph_enrich_haiku.py`.

- **RED** — fixture JSONL with an exotic vehicle that misses the property vocab but resolves in `lemmas` (e.g. `"fermentation"`); assert a bridge is produced for it (currently counted as `bridges_skipped_snap_failure`).
- **GREEN** — replace `vehicle_sid = snap_concept_string(conn, vehicle_raw)` → `lookup_primary_synset(conn, vehicle_raw)`. Leave path/property snapping (inside `insert_bridge_with_raw_path`) untouched.
- **COMMIT** — `fix(metaphor-graph): haiku ingest resolves vehicles via lookup_primary_synset`.

## Wave 2 — Task D: Inapt ingest vehicle → `lookup_primary_synset`

**Files:** `metaphor_graph_enrich_inapt.py`, `test_metaphor_graph_enrich_inapt.py`.

- **RED/GREEN** — same vehicle-resolution swap as Task C, in the inapt ingest path. Test asserts an exotic inapt vehicle now produces a bridge. Synthesised weak-dim *path* concept stays on `snap_concept_string` (it's a property).
- **COMMIT** — `fix(metaphor-graph): inapt ingest resolves vehicles via lookup_primary_synset`.

## Wave 2 — Task E: Sonnet ingest vehicle fix + reuse-skip

**Files:** `metaphor_graph_enrich_sonnet.py`, `test_metaphor_graph_enrich_sonnet.py`.

- **RED (1)** — vehicle swap as Task C; assert an exotic Sonnet vehicle (e.g. `"palimpsest"`) produces a bridge.
- **RED (2)** — reuse-skip: with a mock Sonnet client, call `run_sonnet_edits` twice against the same audit-JSONL path; assert the client is invoked only for topics not already in the audit log (mirror `synthesise_paths`'s log-skip). Second run makes 0 new client calls for already-logged topics.
- **GREEN** — (a) vehicle resolver swap; (b) in `run_sonnet_edits`, read the audit JSONL first, build a `seen` set of topics, skip the LLM call for topics already present.
- **COMMIT** — `fix(metaphor-graph): sonnet ingest resolves vehicles via lookup_primary_synset + skips already-audited topics`.

## Wave 2 — Task F: Cascade in cascade mode + Go word alignment + resilience

**Files:** `metaphor_graph_enrich_cascade.py`, `test_metaphor_graph_enrich_cascade.py`.

- **RED (1)** — assert `make_go_suggest_fn` builds a subprocess command that includes `--cascade`. (Patch `subprocess.Popen` to capture argv; assert `"--cascade" in argv`.)
- **RED (2)** — Go word alignment: with a fake `suggest_fn` capturing its `topic=` kwarg, assert `ingest_cascade` passes the **curated lemma** of `topic_synset_id` when one exists (fixture: synset with curated lemma "idea"), and falls back to the raw word when the synset has no curated lemma.
- **RED (3)** — vehicle resolver swap (exotic vehicle resolves).
- **RED (4)** — per-topic resilience: a `suggest_fn` that raises for one topic must not abort the loop; remaining topics still process; the failure is recorded (e.g. `topics_errored` count + entry).
- **GREEN** —
  1. `make_go_suggest_fn`: add `"--cascade"` to the `Popen` argv. (Rely on S05 parity-tested defaults for the M03 winner config; do NOT re-pass knob flags.)
  2. `ingest_cascade`: before the Go call, resolve the lemma — `lemma = curated_lemma_for(conn, t["topic_synset_id"]) or t["word"]` where `curated_lemma_for` does `SELECT lemma FROM property_vocab_curated WHERE synset_id=?` (small local helper). Pass `topic=lemma` to `suggest_fn`. Bridge label keeps `topic_synset_id=t["topic_synset_id"]` (unchanged).
  3. Vehicle: `lookup_primary_synset(conn, vehicle_raw)`.
  4. Wrap the `suggest_fn(...)` call in try/except; on error increment `topics_errored`, append to a failures list, `continue`.
- **VERIFY note (orchestrator, Wave 3/H):** after building the Go binary, confirm cascade scoring still matches the M03 crib pairs (anger→fire, idea→light, time→money, truth→hammer) — i.e. `--cascade` defaults still encode the winner config. If drifted, escalate (do not silently re-pass knobs).
- **COMMIT** — `fix(metaphor-graph): cascade runs --cascade scorer, aligns Go topic resolution to pre-flight synset, per-topic resilience`.

---

## Wave 3 — Task G: Batch failure-isolation

**Files:** `metaphor_graph_enrich_run.py`, `test_metaphor_graph_enrich_run.py`.

- **RED** — configure `ingest_fns` where one proposer's fn raises; assert `run_batches` (a) does not propagate the exception, (b) still calls the other three, (c) records the failure for that proposer in the report and the progress markdown, (d) continues to the next batch.
- **GREEN** — in `run_batches`, replace the inline `batch_reports = {...}` dict literal with a loop that calls each ingest fn inside try/except; on exception store `{"proposer": name, "error": str(exc), "bridges_inserted": 0}` and log. Progress-row writer already tolerates missing keys (`.get`). Keep the temp-file `finally` unlink.
- **COMMIT** — `fix(metaphor-graph): batch driver isolates per-proposer failures, never aborts the run`.

## Wave 3 — Task H: Verification run (orchestrator-only, not a subagent)

Not a code task — the orchestrator runs the bounded single-batch dry-run end-to-end against a fresh scratch DB copy and asserts the fixes hold:

1. `cp lexicon_v2.db` → scratch; apply metaphor schema; build Go binary (`/tmp/metaforge_stagea`).
2. Re-run topic pre-flight (expect ~100% snap, ~0 dropped) → slice first 20 → run the CLI batch (scratch DB, `/tmp` artefacts).
3. **Assert:** all four proposers (`cascade_v1`, `haiku_v1`, `haiku_v1_inapt_synthesised`, `haiku_sonnet_v1`) have > 0 bridges; the run exits 0 (no crash); cascade produced bridges (no 404 abort); Sonnet creative vehicles survive (spot-check `fermentation`/`palimpsest` present as vehicle synsets).
4. Record outcome; if green, the hardening pass is complete and a full-200 run becomes an operator spend decision (Sonnet fresh per the Haiku-only finding).

---

## Out of scope (tracked CAP-snap-recon)

Full Go↔Python snap unification, gloss-based sense accuracy, loop-result re-eval, and the full-200 Sonnet spend. See spec "Out of scope" and PIPELINE.md Backlog.

## Self-review notes

- Fix 1 changes *endpoint* resolution only; path/property snapping deliberately unchanged.
- Single source of truth: all proposers label topics with the pre-flight synset; vehicles via `lookup_primary_synset`. Cascade *score* rides Go's lemma re-resolution (best-effort; residual divergence deferred).
- Wave 2 file ownership is disjoint → safe parallel subagents; orchestrator commits.
- Every task is RED-first; the integration verification (H) is what the mocked unit tests structurally cannot cover.
