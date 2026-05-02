# M002-kitkng: Pipeline Memory Optimisation

**Gathered:** 2026-05-02
**Status:** Draft — awaiting depth verification (auto-mode blocker; see below)

> **Auto-mode blocker:** The system enforces a mechanical gate that requires `ask_user_questions` with id `depth_verification_M002-kitkng_*` before promoting this draft to CONTEXT. The user's global CLAUDE.md prohibits `ask_user_questions` during auto-mode execution due to a known timeout bug that fabricates consent. Per CLAUDE.md instruction priority (user instructions > skills > defaults), the agent paused rather than bypass the gate. This draft contains the full intended CONTEXT content; promotion requires the user to either (a) confirm depth out-of-band so the agent can re-run with the gate satisfied, or (b) lift the auto-mode `ask_user_questions` prohibition for this turn.

## Project Description

Reduce data-pipeline peak memory from ~11 GB to under 2 GB so the enrichment pipeline runs comfortably on the 3.9 GB VPS without swap-thrashing. The work has two phases:

1. Replace the FastText loader's pathological Python-tuple representation with a numpy float32 matrix container (`FastTextVectors`).
2. Streamline downstream pipeline stages — stream `snap_properties` via cursor, fold `predict_concreteness` fill into `run_pipeline()` to kill a redundant FastText load, and add a canary warning to `cluster_vocab` for combinatoric explosions. Add a `pipeline_integration` pytest marker that proves end-to-end stage ordering.

## Why This Milestone

The data pipeline currently peaks at ~11 GB RSS during enrichment, primarily because `load_fasttext_vectors()` materialises 2M+ word vectors as `dict[str, tuple[float, ...]]`. Python object overhead inflates a ~600 MB float32 payload to ~11 GB. On the staging VPS (3.9 GB RAM) this forces swap-thrashing or outright OOM, blocking enrichment runs and the **20k-word enrichment** item listed in `CLAUDE.md` as MVP-required. Without this fix, the MVP cannot ship on the chosen hosting footprint.

## User-Visible Outcome

### When this milestone is complete, the operator can:

- Run `data-pipeline/enrich.sh` on the 3.9 GB staging VPS and see the full pipeline complete with peak RSS under 2 GB (measured via `/usr/bin/time -v` or `psutil`), no swap thrashing, no OOM kill.
- Observe the pipeline performs only **one** FastText load instead of two — the concreteness fill step now reuses the in-memory `FastTextVectors`.
- See a clear warning logged when `cluster_vocab` produces any chunk with more than 100k above-threshold pairs, so misconfigured thresholds are caught before they explode the run.
- Run the new `pipeline_integration` pytest marker locally to prove stage ordering end-to-end on a tiny fixture DB; the marker is excluded from default test runs so day-to-day development stays fast.

### Entry point / environment

- **Entry point:** `data-pipeline/enrich.sh` (full pipeline) and `python -m pytest -m pipeline_integration` (ordering proof).
- **Environment:** local dev (Python venv at `data-pipeline/.venv`) and staging VPS (3.9 GB RAM).
- **Live dependencies involved:** SQLite (`data-pipeline/output/lexicon_v2.db`) and the FastText `.vec` file. No network calls.

## Completion Class

- **Contract complete means:** `FastTextVectors` container exists with numpy float32 matrix + `word_to_idx` dict; all consumers in `enrich_pipeline.py` and `predict_concreteness.py` migrated; `snap_properties` two-pass cursor refactor green; `cluster_vocab` 100k-pair canary warning fires under test; `pipeline_integration` marker registered and excluded from default runs; full data-pipeline pytest suite green.
- **Integration complete means:** `enrich.sh` no longer invokes `predict_concreteness.py` as a separate process for the fill step — the in-process call from `run_pipeline()` produces identical `synset_concreteness` rows; `pipeline_integration` test passes end-to-end on a tiny fixture DB asserting row counts at all five checkpoints (`synset_properties`, `lemma_embeddings`, `vocab_clusters`, `synset_properties_curated`, `synset_concreteness`).
- **Operational complete means:** A real enrichment run on the 3.9 GB VPS completes with peak RSS measured under 2 GB. This is the load-bearing scaling proof — the integration fixture proves ordering, not scaling.

## Final Integrated Acceptance

To call this milestone complete, we must prove:

- A full `enrich.sh` run on the 3.9 GB staging VPS completes successfully with peak RSS under 2 GB, captured via `/usr/bin/time -v` (or `psutil` equivalent). This is the only proof that cannot be simulated.
- The `pipeline_integration` test passes end-to-end on a fresh checkout, demonstrating the five-stage ordering invariant holds.
- `grep -r 'tuple\[float' data-pipeline/scripts/utils.py | wc -l` returns 0 — no tuple-of-floats representation remains.
- `enrich.sh` contains exactly one path that loads FastText vectors; the standalone `predict_concreteness.py fill` invocation has been removed.
- struct-pack precision regression test confirms numpy float32 path matches the old tuple-of-float64 path within 1e-7 — no silent similarity-threshold drift.

## Architectural Decisions

### FastTextVectors numpy container replaces dict[str, tuple[float, ...]]

**Decision:** Introduce a `FastTextVectors` dataclass in `data-pipeline/scripts/utils.py` holding a numpy float32 matrix (shape `n_words × 300`) and a `word_to_idx: dict[str, int]`. Implement `__contains__` and `__getitem__` so existing call sites read naturally (`if word in vectors`, `row = vectors[word]`). `load_fasttext_vectors()` parses directly into numpy rows — never into Python tuples.

**Rationale:** The current `dict[str, tuple[float, ...]]` representation pays ~5 KB per word in Python object overhead (PyTuple header + 300 PyFloat boxes + dict bucket) on top of a 1.2 KB float32 payload. A numpy float32 matrix collapses the per-word overhead to ~1.2 KB. For 2M words this is the difference between ~11 GB and ~1.2 GB RSS.

**Alternatives Considered:**
- Memory-mapped numpy file — discarded as premature; the in-memory float32 matrix already fits the 2 GB budget and avoids mmap-related portability issues across local/VPS environments.
- Keep the dict but switch values to `array.array('f', ...)` — discarded; still pays the per-word dict bucket overhead and complicates downstream numpy math (`predict_concreteness.build_synset_embeddings` already converts to numpy).

### Two-pass cursor in snap_properties

**Decision:** Refactor `snap_properties()` to iterate via SQLite cursor in two passes. Pass 1 (Stages 1–2: exact + morphological match) queries only `synset_id`, property text, and salience — no embedding blob. Pass 2 (Stage 3: cosine similarity) queries embedding blobs only for the unmatched synset/property pairs.

**Rationale:** The current single-pass implementation materialises all ~245k rows including 1200-byte embedding blobs into a Python list, costing ~294 MB. Roughly 60–70% of properties match in Stages 1–2 and never need their blob. Two-pass cursor iteration keeps memory bounded by chunk size, not corpus size.

**Alternatives Considered:**
- Process each row individually with single-row commits — discarded; the SQLite write-amplification cost would dominate.
- Stream via generators while keeping a single query — discarded; the embedding blob is the dominant cost and must be excluded from the first pass to realise the saving.

### Fold predict_concreteness fill into run_pipeline()

**Decision:** Move the concreteness gap-fill step from a separate `predict_concreteness.py fill` subprocess (currently invoked at `data-pipeline/enrich.sh:261`) into `run_pipeline()` in `enrich_pipeline.py`, called after `store_lemma_embeddings()`. The fold reuses the already-loaded `FastTextVectors` and the open SQLite connection. `enrich.sh` is updated to drop the standalone invocation. The shootout step remains standalone — it is an evaluation, not a pipeline stage.

**Rationale:** The standalone subprocess re-loads FastText from scratch, costing a second ~1.2 GB (post-S01) on top of the in-process load. Folding eliminates the second load entirely. The split was a packaging artefact, not a deliberate isolation boundary.

**Alternatives Considered:**
- Keep the subprocess and pass FastText via shared memory — discarded; complexity exceeds the cost of folding.
- Cache FastText to disk and reload — discarded; reload time is non-trivial and disk space is bounded on the VPS.

### 100k-pair canary in cluster_vocab

**Decision:** Add a warning log inside `cluster_vocab()`'s inner loop (around `cluster_vocab.py:137`, after the `np.where` call) that fires when any pairwise chunk yields more than 100k above-threshold pairs. Warning, not error — does not abort the run.

**Rationale:** A misconfigured similarity threshold causes combinatoric explosion that has historically been silent until OOM. A canary at 100k pairs per chunk is well above legitimate workloads and well below the OOM cliff, giving the operator a chance to abort and re-tune.

**Alternatives Considered:**
- Hard error — discarded; thresholds are workload-dependent and a hard error would block legitimate large runs.
- Global pair counter with periodic logging — discarded; per-chunk gives faster signal and is cheaper to implement.

### New pipeline_integration pytest marker

**Decision:** Create `test_pipeline_integration.py` with `@pytest.mark.pipeline_integration`. Build a small fixture DB (~10 synsets, 3–4 properties each) and a tiny mock FastText file (5 words, 300d). Run the full pipeline end-to-end and assert row counts at five checkpoints: `synset_properties`, `lemma_embeddings`, `vocab_clusters`, `synset_properties_curated`, `synset_concreteness`. Register the marker in `conftest.py`; configure `pytest.ini` to exclude it from default runs (CI path filter to be documented in a comment).

**Rationale:** Stage ordering bugs in the pipeline are silent — the wrong order produces empty downstream tables instead of crashes. A small ordering-proof test that runs the actual `run_pipeline()` catches these before they hit a real run. Excluding from default runs keeps unit-test latency low.

**Alternatives Considered:**
- Run as part of the default test suite — discarded; even the small fixture is too slow to run on every commit.
- Skip the integration test and rely on the VPS run — discarded; integration test is the contract for ordering, the VPS run is the contract for scaling.

---

> See `.gsd/DECISIONS.md` for the full append-only register of all project decisions.

## Error Handling Strategy

- **FastText loader:** raise `FileNotFoundError` early if the `.vec` file is missing; raise `ValueError` on malformed lines (logged with line number) and abort load — corrupt vectors must not silently propagate.
- **Two-pass cursor in `snap_properties`:** wrap each pass in try/finally to ensure cursor cleanup on exception; row-order changes between passes treated as a programming error and assertion-checked in the equivalence test.
- **Folded `predict_concreteness` fill:** if no shootout JSON is provided, log an info message and skip — matches current `enrich.sh` behaviour. Connection errors propagate to `run_pipeline()` which already commits per-stage.
- **`cluster_vocab` canary:** warning only — never aborts the run. Includes the chunk index and pair count so the operator can correlate to the threshold setting.
- **`pipeline_integration` test:** failures must surface row-count assertion details so a stage misorder is immediately diagnosable.

## Risks and Unknowns

- **Float32 vs float64 precision drift in similarity thresholds** — mitigated by a 1e-7 regression test in `test_utils.py`.
- **Two-pass cursor refactor could change row order or commit semantics** — mitigated by an equivalence test.
- **Folded `predict_concreteness` might share previously-isolated module state** — verified by the `pipeline_integration` test exercising the full sequence.
- **VPS measurement methodology** — final acceptance pins to `/usr/bin/time -v` `Maximum resident set size`.
- **Pipeline integration fixture is small** — proves ordering, not scaling. The VPS run is the load-bearing scaling proof.

## Existing Codebase / Prior Art

- `data-pipeline/scripts/utils.py` — currently houses `load_fasttext_vectors()` returning `dict[str, tuple[float, ...]]`. New `FastTextVectors` container lives here.
- `data-pipeline/scripts/enrich_pipeline.py` — `_get_embedding`, `_get_compound_embedding`, `curate_properties`, `store_lemma_embeddings`, and `run_pipeline` consume the vectors; all migrate to `FastTextVectors`.
- `data-pipeline/scripts/predict_concreteness.py` — `build_synset_embeddings`, `cmd_shootout`, `cmd_fill` consume the vectors; `cmd_fill` is folded into `run_pipeline()`.
- `data-pipeline/scripts/snap_properties.py` — two-pass cursor refactor target.
- `data-pipeline/scripts/cluster_vocab.py` (around line 137) — canary warning insertion point.
- `data-pipeline/enrich.sh` (around line 261) — standalone `predict_concreteness.py fill` invocation removed in S02.
- `data-pipeline/scripts/test_*.py` — 24 existing test files; precision regression and integration tests added.
- `CLAUDE.md` — pins MVP requirements including 20k-word enrichment, which depends on this milestone landing.

## Relevant Requirements

- *MVP — 20k word enrichment* (CLAUDE.md "Required for MVP-complete") — this milestone unblocks running enrichment at the target word count on the chosen VPS footprint.
- *Algorithms standard* (CLAUDE.md) — "Recognise OOM risk and proactively filter, stream and paginate to avoid OOM errors."
- *Observability standard* (CLAUDE.md) — `cluster_vocab` canary, structured warnings, and integration-test row-count assertions all serve agent-first observability.

## Scope

### In Scope

- `FastTextVectors` numpy container in `utils.py` and refactored `load_fasttext_vectors()`.
- Migration of all consumers in `enrich_pipeline.py` and `predict_concreteness.py`.
- Float32 precision regression test (1e-7 tolerance).
- Two-pass cursor refactor of `snap_properties()`.
- Folding `predict_concreteness.fill` into `run_pipeline()` and updating `enrich.sh`.
- 100k-pair canary warning in `cluster_vocab()`.
- `pipeline_integration` pytest marker, `conftest.py` registration, `pytest.ini` exclusion.
- Five-checkpoint integration ordering test on a small fixture.
- VPS run with measured peak RSS < 2 GB.

### Out of Scope / Non-Goals

- Memory-mapped FastText file (deferred — float32 matrix already meets the budget).
- Replacing SQLite or changing on-disk schema.
- Refactoring the `shootout` evaluation path (remains standalone).
- CI wiring of the `pipeline_integration` marker beyond a path-filter comment.
- 20k-word enrichment itself (separate milestone — this unblocks it).
- Frontend changes; API changes.

## Technical Constraints

- Must run on a 3.9 GB RAM VPS without swap.
- Python venv at `data-pipeline/.venv`; FastText `.vec` file path-configurable.
- SQLite is the only persistent store; no schema migrations as part of this milestone.
- All commits TDD-disciplined: failing test first, minimal pass, refactor.
- UK English in code/comments where applicable (project standard).
- No new runtime dependencies beyond what numpy already provides.

## Integration Points

- **SQLite (`lexicon_v2.db`)** — `snap_properties` cursor passes; `predict_concreteness.fill` writes to `synset_concreteness`. Connection sharing across folded steps must respect existing per-stage commit behaviour.
- **FastText `.vec` file** — single load via `load_fasttext_vectors()` in `run_pipeline()`; reused by all stages including the folded concreteness fill.
- **`enrich.sh`** — orchestration script; updated to drop the standalone `predict_concreteness.py fill` invocation.
- **pytest** — `conftest.py` and `pytest.ini` updated; default runs exclude `pipeline_integration`.

## Testing Requirements

- **Unit tests:** TDD red-green-refactor for every change. New tests for `FastTextVectors` (`__contains__`, `__getitem__`, `.matrix` shape, `.dim`); float32 precision regression (1e-7 tolerance); two-pass cursor equivalence in `snap_properties`; `cluster_vocab` warning fires at 100k-pair threshold.
- **Integration tests:** `test_pipeline_integration.py` with `@pytest.mark.pipeline_integration`; small fixture DB and tiny mock FastText file; row-count assertions at five checkpoints (`synset_properties`, `lemma_embeddings`, `vocab_clusters`, `synset_properties_curated`, `synset_concreteness`).
- **Test gating:** marker excluded from default runs via `pytest.ini`; opt-in via `-m pipeline_integration`.
- **Full suite green:** `cd data-pipeline && ../.venv/bin/python -m pytest scripts/ -v --tb=short` passes across all 24 existing test files.
- **VPS validation:** `/usr/bin/time -v ./enrich.sh` on the 3.9 GB staging VPS; Maximum resident set size under 2 GB.

## Acceptance Criteria

### S01 — FastText numpy migration

- `load_fasttext_vectors()` returns a `FastTextVectors` instance (numpy float32 matrix, `word_to_idx` dict, `__contains__`, `__getitem__`, `.matrix`, `.dim`).
- All consumers in `enrich_pipeline.py` and `predict_concreteness.py` use the new type.
- struct-pack output from numpy path matches tuple path within 1e-7 (precision regression test).
- `grep -r 'tuple\[float' data-pipeline/scripts/utils.py | wc -l` returns 0.
- Full data-pipeline pytest suite green.

### S02 — Pipeline memory streamlining

- `snap_properties()` uses two-pass cursor iteration; equivalence test green.
- `predict_concreteness.fill` runs inside `run_pipeline()`, sharing the loaded `FastTextVectors`.
- `enrich.sh` no longer invokes `predict_concreteness.py` standalone for the fill step.
- `cluster_vocab` logs a warning when any chunk exceeds 100k above-threshold pairs.
- `test_pipeline_integration.py` exists with `@pytest.mark.pipeline_integration`; `conftest.py` registers it; `pytest.ini` excludes it from default runs.
- Five-checkpoint row-count assertions all pass.

### Milestone

- Measured peak RSS < 2 GB on the 3.9 GB host (`/usr/bin/time -v`).
- Full data-pipeline test suite green.
- `pipeline_integration` test green.

## Open Questions

- *VPS measurement command finalised?* — current thinking: `/usr/bin/time -v ./enrich.sh` capturing `Maximum resident set size`. Resolved at execution time if simpler instrumentation suffices.
- *CI path filter syntax for the new marker?* — documented in a comment in `pytest.ini`; actual CI wiring is out of scope and tracked separately.
