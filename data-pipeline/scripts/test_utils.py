"""Tests for shared utility functions."""
import json
import struct
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from utils import (
    EMBEDDING_DIM,
    FastTextVectors,
    get_git_commit,
    load_checkpoint,
    load_fasttext_vectors,
    normalise,
    save_checkpoint,
)


def test_normalise_strips_and_lowercases():
    """Verify normalise() strips whitespace and lowercases."""
    assert normalise(" Hello World ") == "hello world"


def test_normalise_edge_cases():
    """Verify normalise() handles edge cases correctly."""
    # Empty string
    assert normalise("") == ""

    # Already normalised
    assert normalise("hello world") == "hello world"

    # Tabs and newlines
    assert normalise("\tHello\nWorld\t") == "hello\nworld"


# --- Checkpoint I/O tests ---


def test_save_checkpoint_is_atomic(tmp_path):
    """save_checkpoint writes atomically — no .tmp file left behind."""
    cp = tmp_path / "checkpoint.json"
    state = {"completed_ids": ["s1"], "synsets": [{"id": "s1"}]}
    save_checkpoint(cp, state)

    assert cp.exists()
    assert not list(tmp_path.glob("*.tmp"))
    loaded = json.loads(cp.read_text())
    assert loaded["completed_ids"] == ["s1"]


def test_save_checkpoint_overwrites_existing(tmp_path):
    """save_checkpoint replaces existing checkpoint atomically."""
    cp = tmp_path / "checkpoint.json"
    save_checkpoint(cp, {"completed_ids": [], "synsets": []})
    save_checkpoint(cp, {"completed_ids": ["s1"], "synsets": [{"id": "s1"}]})

    loaded = json.loads(cp.read_text())
    assert loaded["completed_ids"] == ["s1"]


def test_load_checkpoint_handles_corrupt_json(tmp_path):
    """load_checkpoint recovers from corrupt JSON by returning empty state."""
    cp = tmp_path / "checkpoint.json"
    cp.write_text("{truncated")

    state = load_checkpoint(cp)

    assert state == {"completed_ids": [], "synsets": []}
    assert (tmp_path / "checkpoint.json.corrupt").exists()
    assert not cp.exists()


def test_load_checkpoint_reads_unified_format(tmp_path):
    """load_checkpoint reads the unified checkpoint format."""
    cp = tmp_path / "checkpoint.json"
    cp.write_text(json.dumps({
        "completed_ids": ["s1", "s2"],
        "synsets": [{"id": "s1"}, {"id": "s2"}],
    }))
    state = load_checkpoint(cp)
    assert len(state["completed_ids"]) == 2
    assert len(state["synsets"]) == 2


def test_load_checkpoint_backward_compat_results_key(tmp_path):
    """load_checkpoint remaps legacy 'results' key to 'synsets'."""
    cp = tmp_path / "checkpoint.json"
    cp.write_text(json.dumps({
        "completed_ids": ["s1"],
        "results": [{"id": "s1"}],
    }))
    state = load_checkpoint(cp)
    assert "synsets" in state
    assert "results" not in state
    assert state["synsets"] == [{"id": "s1"}]


def test_load_checkpoint_empty_when_missing(tmp_path):
    """load_checkpoint returns empty state when file doesn't exist."""
    state = load_checkpoint(tmp_path / "nonexistent.json")
    assert state == {"completed_ids": [], "synsets": []}


# --- get_git_commit tests ---


def test_get_git_commit_returns_string():
    """get_git_commit returns a string (hash or 'unknown')."""
    result = get_git_commit()
    assert isinstance(result, str)
    assert len(result) > 0


# --- FastTextVectors container tests ---


def _make_container(words_to_vec):
    """Build a FastTextVectors from {word: list[float]}."""
    words = list(words_to_vec.keys())
    matrix = np.array([words_to_vec[w] for w in words], dtype=np.float32)
    word_to_idx = {w: i for i, w in enumerate(words)}
    return FastTextVectors(matrix=matrix, word_to_idx=word_to_idx)


def test_fasttext_vectors_contains_known_word():
    """__contains__ returns True for a word in word_to_idx."""
    vectors = _make_container({"cat": [0.1] * EMBEDDING_DIM})
    assert "cat" in vectors


def test_fasttext_vectors_does_not_contain_unknown_word():
    """__contains__ returns False for a word not in word_to_idx."""
    vectors = _make_container({"cat": [0.1] * EMBEDDING_DIM})
    assert "dog" not in vectors


def test_fasttext_vectors_getitem_returns_numpy_row():
    """__getitem__ returns the matrix row as a numpy array of float32."""
    vec = [float(i) for i in range(EMBEDDING_DIM)]
    vectors = _make_container({"cat": vec})

    row = vectors["cat"]

    assert isinstance(row, np.ndarray)
    assert row.dtype == np.float32
    assert row.shape == (EMBEDDING_DIM,)
    np.testing.assert_allclose(row, np.array(vec, dtype=np.float32))


def test_fasttext_vectors_getitem_unknown_raises_keyerror():
    """__getitem__ raises KeyError for unknown words (matches dict semantics)."""
    vectors = _make_container({"cat": [0.0] * EMBEDDING_DIM})
    with pytest.raises(KeyError):
        _ = vectors["dog"]


def test_fasttext_vectors_matrix_shape():
    """.matrix is a 2D numpy array shaped (n_words, dim)."""
    vectors = _make_container({
        "cat": [0.1] * EMBEDDING_DIM,
        "dog": [0.2] * EMBEDDING_DIM,
        "bird": [0.3] * EMBEDDING_DIM,
    })
    assert vectors.matrix.shape == (3, EMBEDDING_DIM)
    assert vectors.matrix.dtype == np.float32


def test_fasttext_vectors_dim_property():
    """.dim returns the embedding dimension (matrix.shape[1])."""
    vectors = _make_container({"cat": [0.1] * EMBEDDING_DIM})
    assert vectors.dim == EMBEDDING_DIM


def test_fasttext_vectors_len():
    """len() returns the number of words."""
    vectors = _make_container({
        "a": [0.0] * EMBEDDING_DIM,
        "b": [0.0] * EMBEDDING_DIM,
    })
    assert len(vectors) == 2


# --- FastTextVectors __post_init__ validation tests ---


def test_fasttext_vectors_rejects_non_2d_matrix():
    """__post_init__ raises ValueError when matrix is not 2D."""
    flat = np.zeros(EMBEDDING_DIM, dtype=np.float32)  # 1D
    with pytest.raises(ValueError, match="2D|ndim"):
        FastTextVectors(matrix=flat, word_to_idx={"cat": 0})


def test_fasttext_vectors_rejects_wrong_embedding_dim():
    """__post_init__ raises ValueError when matrix.shape[1] != EMBEDDING_DIM."""
    bad_dim = np.zeros((1, EMBEDDING_DIM + 1), dtype=np.float32)
    with pytest.raises(ValueError, match="EMBEDDING_DIM|shape"):
        FastTextVectors(matrix=bad_dim, word_to_idx={"cat": 0})


def test_fasttext_vectors_rejects_wrong_dtype():
    """__post_init__ raises ValueError when matrix.dtype is not float32."""
    f64 = np.zeros((1, EMBEDDING_DIM), dtype=np.float64)
    with pytest.raises(ValueError, match="float32|dtype"):
        FastTextVectors(matrix=f64, word_to_idx={"cat": 0})


def test_fasttext_vectors_rejects_row_count_mismatch():
    """__post_init__ raises ValueError when shape[0] != len(word_to_idx)."""
    matrix = np.zeros((2, EMBEDDING_DIM), dtype=np.float32)
    with pytest.raises(ValueError, match="row|word_to_idx|len"):
        FastTextVectors(matrix=matrix, word_to_idx={"cat": 0})


def test_fasttext_vectors_matrix_is_read_only():
    """Matrix rows are non-writeable — caller mutation raises ValueError.

    numpy raises ValueError ("assignment destination is read-only") on writes
    to a read-only array. This converts silent caller-mutation of a shared
    embedding row into an immediate, loud failure.
    """
    vectors = _make_container({"cat": [0.1] * EMBEDDING_DIM})
    with pytest.raises(ValueError):
        vectors["cat"][0] = 99.0


# --- load_fasttext_vectors tests ---


def _write_vec_file(path: Path, rows: list[tuple[str, list[float]]], dim: int = EMBEDDING_DIM):
    """Write a FastText-format .vec file."""
    lines = [f"{len(rows)} {dim}"]
    for word, vec in rows:
        lines.append(word + " " + " ".join(f"{x:.6f}" for x in vec))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_load_fasttext_vectors_returns_fasttextvectors(tmp_path, monkeypatch):
    """load_fasttext_vectors returns a FastTextVectors instance."""
    # Reset module cache so test is hermetic
    import utils as utils_mod
    monkeypatch.setattr(utils_mod, "_fasttext_cache", {})

    vec_file = tmp_path / "tiny.vec"
    _write_vec_file(vec_file, [
        ("cat", [0.1] * EMBEDDING_DIM),
        ("dog", [0.2] * EMBEDDING_DIM),
    ])

    vectors = load_fasttext_vectors(str(vec_file))

    assert isinstance(vectors, FastTextVectors)
    assert "cat" in vectors
    assert "dog" in vectors
    assert vectors.matrix.shape == (2, EMBEDDING_DIM)
    assert vectors.matrix.dtype == np.float32
    np.testing.assert_allclose(
        vectors["cat"],
        np.array([0.1] * EMBEDDING_DIM, dtype=np.float32),
        rtol=1e-5,
    )


def test_load_fasttext_vectors_caches_by_path(tmp_path, monkeypatch):
    """Second call with same path returns the same object (cached)."""
    import utils as utils_mod
    monkeypatch.setattr(utils_mod, "_fasttext_cache", {})

    vec_file = tmp_path / "tiny.vec"
    _write_vec_file(vec_file, [("cat", [0.5] * EMBEDDING_DIM)])

    first = load_fasttext_vectors(str(vec_file))
    second = load_fasttext_vectors(str(vec_file))

    assert first is second


def test_load_fasttext_vectors_skips_malformed_lines(tmp_path, monkeypatch):
    """Lines with wrong dimensionality or non-numeric values are skipped."""
    import utils as utils_mod
    monkeypatch.setattr(utils_mod, "_fasttext_cache", {})

    vec_file = tmp_path / "tiny.vec"
    # Header claims 3 words but second row is malformed (too few cols)
    lines = [f"3 {EMBEDDING_DIM}"]
    lines.append("good " + " ".join(["0.1"] * EMBEDDING_DIM))
    lines.append("bad 0.1 0.2 0.3")  # only 3 values
    lines.append("alsogood " + " ".join(["0.2"] * EMBEDDING_DIM))
    vec_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    vectors = load_fasttext_vectors(str(vec_file))

    assert "good" in vectors
    assert "alsogood" in vectors
    assert "bad" not in vectors
    assert vectors.matrix.shape == (2, EMBEDDING_DIM)


def test_load_fasttext_vectors_dedupes_duplicate_words(tmp_path, monkeypatch):
    """Duplicate words in the .vec file must not leak orphan rows.

    If the same word appears twice, the loader should keep only the first
    occurrence and skip the rest. The matrix row count must equal the
    word→idx map size — a mismatch indicates an orphaned row leaked through.
    """
    import utils as utils_mod
    monkeypatch.setattr(utils_mod, "_fasttext_cache", {})

    vec_file = tmp_path / "dupes.vec"
    # Header claims 3 rows; "cat" appears twice with different vectors.
    lines = [f"3 {EMBEDDING_DIM}"]
    lines.append("cat " + " ".join(["0.1"] * EMBEDDING_DIM))
    lines.append("dog " + " ".join(["0.2"] * EMBEDDING_DIM))
    lines.append("cat " + " ".join(["0.9"] * EMBEDDING_DIM))  # duplicate
    vec_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    vectors = load_fasttext_vectors(str(vec_file))

    # Invariant: no orphan rows.
    assert vectors.matrix.shape[0] == len(vectors.word_to_idx)
    assert len(vectors) == 2
    # First occurrence wins — "cat" should still hold the 0.1 vector.
    np.testing.assert_allclose(
        vectors["cat"],
        np.array([0.1] * EMBEDDING_DIM, dtype=np.float32),
        rtol=1e-5,
    )


def test_load_fasttext_vectors_handles_mixed_skip_reasons(tmp_path, monkeypatch):
    """A .vec file containing BOTH a duplicate word and a malformed line must
    still produce a self-consistent FastTextVectors instance.

    Regression guard for the split-counter refactor: previously a single
    `skipped` counter conflated the two kinds of skip in the warning message.
    The size invariant (matrix rows == word_to_idx entries) must hold
    regardless of which mix of skip reasons fired.
    """
    import utils as utils_mod
    monkeypatch.setattr(utils_mod, "_fasttext_cache", {})

    vec_file = tmp_path / "mixed.vec"
    lines = [f"4 {EMBEDDING_DIM}"]
    lines.append("cat " + " ".join(["0.1"] * EMBEDDING_DIM))
    lines.append("dog " + " ".join(["0.2"] * EMBEDDING_DIM))
    lines.append("cat " + " ".join(["0.9"] * EMBEDDING_DIM))  # duplicate
    lines.append("bad 0.1 0.2 0.3")  # malformed (too few cols)
    vec_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    vectors = load_fasttext_vectors(str(vec_file))

    # Two unique well-formed words survive.
    assert len(vectors) == 2
    # No orphan rows from either skip path.
    assert vectors.matrix.shape[0] == len(vectors.word_to_idx)
    assert "cat" in vectors and "dog" in vectors
    assert "bad" not in vectors


def test_load_fasttext_vectors_handles_zero_word_header(tmp_path, monkeypatch):
    """A `0 300` header (degenerate but legal) must not crash with ZeroDivisionError.

    The skipped-percentage calculation `skipped / num_words * 100` divided by
    zero when the header announced no words. The loader should still return a
    valid (empty) FastTextVectors instance.
    """
    import utils as utils_mod
    monkeypatch.setattr(utils_mod, "_fasttext_cache", {})

    vec_file = tmp_path / "empty.vec"
    # Header announces 0 words; one stray malformed line forces skipped > 0
    # so we exercise the warning branch where the divide would happen.
    vec_file.write_text(f"0 {EMBEDDING_DIM}\nbad 0.1 0.2\n", encoding="utf-8")

    vectors = load_fasttext_vectors(str(vec_file))

    assert isinstance(vectors, FastTextVectors)
    assert len(vectors) == 0
    assert vectors.matrix.shape[0] == 0


def test_load_fasttext_vectors_rejects_wrong_dim(tmp_path, monkeypatch):
    """Header dim != EMBEDDING_DIM raises ValueError."""
    import utils as utils_mod
    monkeypatch.setattr(utils_mod, "_fasttext_cache", {})

    vec_file = tmp_path / "wrong.vec"
    _write_vec_file(vec_file, [("cat", [0.1] * 100)], dim=100)

    with pytest.raises(ValueError, match="dimension mismatch"):
        load_fasttext_vectors(str(vec_file))


# --- Float32 precision regression ---


def test_float32_precision_matches_tuple_pack():
    """struct.pack of float32 numpy row matches the old tuple-of-float pack within float32 tolerance.

    The pre-refactor code held vectors as tuple[float, ...] (Python float = float64)
    and packed them with struct.pack(f'{EMBEDDING_DIM}f', *tup). The new code packs
    a numpy float32 row directly. Both paths emit single-precision bytes via the 'f'
    format, so the resulting blobs must be bit-identical when the source values are
    representable in float32 — and within float32 epsilon when they aren't.
    """
    rng = np.random.default_rng(42)
    # Use float64 source values that exercise both representable and non-representable
    # float32 magnitudes (small, large, fractions that need rounding).
    source_f64 = rng.uniform(-1.0, 1.0, EMBEDDING_DIM).astype(np.float64)

    # Old path: tuple of Python floats (float64) → struct.pack as 'f' (float32)
    old_tuple = tuple(float(x) for x in source_f64)
    old_blob = struct.pack(f"{EMBEDDING_DIM}f", *old_tuple)

    # New path: numpy float32 row from FastTextVectors → struct.pack as 'f'
    new_row = source_f64.astype(np.float32)
    container = FastTextVectors(
        matrix=new_row.reshape(1, EMBEDDING_DIM),
        word_to_idx={"w": 0},
    )
    new_blob = struct.pack(f"{EMBEDDING_DIM}f", *container["w"])

    # struct.pack with 'f' downcasts float64→float32 the same way numpy does, so the
    # two blobs should be byte-identical.
    assert old_blob == new_blob

    # Cross-check: unpacked floats agree to float32 precision.
    old_unpacked = np.array(struct.unpack(f"{EMBEDDING_DIM}f", old_blob), dtype=np.float32)
    new_unpacked = np.array(struct.unpack(f"{EMBEDDING_DIM}f", new_blob), dtype=np.float32)
    np.testing.assert_allclose(old_unpacked, new_unpacked, rtol=1e-7, atol=0.0)
