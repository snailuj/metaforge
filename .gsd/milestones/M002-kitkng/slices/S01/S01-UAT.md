# S01: FastText numpy migration — UAT

**Milestone:** M002-kitkng
**Written:** 2026-05-02T07:41:56.428Z

# S01 UAT — FastText numpy migration

## Preconditions

1. Worktree `/home/agent/projects/metaforge/.gsd/worktrees/M002-kitkng` checked out at the slice's terminal commit.
2. Python venv at `.venv/` populated from `data-pipeline/requirements.txt` (numpy, pytest, sqlite3 stdlib, etc.).
3. `data-pipeline/output/lexicon_v2.db` populated (≥ ~230 MB) — restore from a sibling worktree if it's a 0-byte placeholder.

## Test cases

### TC1 — FastTextVectors container surface

**Steps:**
1. `cd data-pipeline`
2. `../.venv/bin/python -m pytest scripts/test_utils.py::test_fasttext_vectors_contains_known_word scripts/test_utils.py::test_fasttext_vectors_does_not_contain_unknown_word scripts/test_utils.py::test_fasttext_vectors_getitem_returns_numpy_row scripts/test_utils.py::test_fasttext_vectors_getitem_unknown_raises_keyerror scripts/test_utils.py::test_fasttext_vectors_matrix_shape scripts/test_utils.py::test_fasttext_vectors_dim_property scripts/test_utils.py::test_fasttext_vectors_len -v`

**Expected:** 7 tests pass. `__contains__` returns True for in-vocab words, False otherwise. `__getitem__` returns a numpy ndarray (not a tuple) of dtype float32. Unknown lookup raises KeyError. `.matrix.shape == (n, 300)`. `.dim == 300`. `len()` matches `word_to_idx`.

### TC2 — Loader returns FastTextVectors and caches by path

**Steps:**
1. `../.venv/bin/python -m pytest scripts/test_utils.py::test_load_fasttext_vectors_returns_fasttextvectors scripts/test_utils.py::test_load_fasttext_vectors_caches_by_path scripts/test_utils.py::test_load_fasttext_vectors_skips_malformed_lines scripts/test_utils.py::test_load_fasttext_vectors_rejects_wrong_dim -v`

**Expected:** All 4 pass. The loader returns a `FastTextVectors` instance, caches by absolute path on second call, silently drops malformed rows (matrix is trimmed to actual word count), and raises `ValueError` if header dim ≠ `EMBEDDING_DIM`.

### TC3 — Float32 precision parity (T04 regression test)

**Steps:**
1. `../.venv/bin/python -m pytest scripts/test_utils.py::test_float32_precision_matches_tuple_pack -v`

**Expected:** Test passes. Asserts `struct.pack(f"{EMBEDDING_DIM}f", *tuple_path)` and `struct.pack(f"{EMBEDDING_DIM}f", *numpy_float32_row.tolist())` produce **byte-identical** blobs for a deterministically-seeded float64 vector, and that round-tripping both blobs matches within `rtol=1e-7`.

### TC4 — enrich_pipeline consumers migrated

**Steps:**
1. `../.venv/bin/python -m pytest scripts/test_enrich_pipeline.py -v`
2. `grep -c 'tuple\[float' scripts/enrich_pipeline.py`
3. `grep -n FastTextVectors scripts/enrich_pipeline.py`

**Expected:** All 36 enrich_pipeline tests pass. Step 2 returns 0 (no remaining tuple-of-float annotations). Step 3 shows the `FastTextVectors` annotation on `_get_embedding`, `_get_compound_embedding`, `curate_properties`, and `store_lemma_embeddings`. The `struct` import is gone; embedding blobs are written via `numpy.tobytes()`.

### TC5 — predict_concreteness consumers migrated

**Steps:**
1. `../.venv/bin/python -m pytest scripts/test_predict_concreteness.py -v`
2. `grep -n 'tuple\[float' scripts/predict_concreteness.py`

**Expected:** 19 tests pass. `grep` returns no matches. `build_synset_embeddings`, `cmd_shootout`, and `cmd_fill` all accept `FastTextVectors`.

### TC6 — Full slice-level suite (acceptance gate)

**Steps:**
1. `cd data-pipeline && ../.venv/bin/python -m pytest scripts/ -v --tb=short`

**Expected:** **388 passed, 0 failed** in roughly 45–60 seconds. All 24 test files green.

### TC7 — Embedding blob byte-compat with prior writer (manual cross-check)

**Purpose:** Confirms that existing rows in `lemma_embeddings.embedding` and `property_vocabulary.embedding` (written by the pre-migration code) remain readable after the migration.

**Steps:**
1. `../.venv/bin/python -c "import sqlite3, struct; c = sqlite3.connect('output/lexicon_v2.db'); row = c.execute('SELECT embedding FROM lemma_embeddings LIMIT 1').fetchone(); print(len(row[0]), len(struct.unpack('300f', row[0])))"`

**Expected:** Outputs `1200 300` — blob is 1200 bytes (300 × 4 bytes), unpacks cleanly into 300 float32 values. Confirms the on-disk format unchanged.

## Edge cases

- **Malformed FastText line in middle of file:** Loader drops the row, continues parsing remaining lines, and trims the final matrix to the actual word count. `len(vectors)` and `vectors.matrix.shape[0]` stay in sync.
- **Empty/zero-byte FastText file:** `load_fasttext_vectors` raises a clean error parsing the header (existing behaviour preserved).
- **Compound word with all OOV components:** `_get_compound_embedding` returns `None` (existing behaviour preserved by the np.stack/mean rewrite).
- **Concurrent loader calls with same path:** Cache-by-path ensures only one parse — second call returns the same `FastTextVectors` instance.
- **Worktree without DB or venv:** TC6 fails fast with environment errors before any production code runs. Document remediation: provision venv + restore DB.

## Sign-off criteria

UAT passes when TC1–TC6 all green and TC7 produces the expected `1200 300` output. Edge cases are covered by existing tests in TC4–TC6.
