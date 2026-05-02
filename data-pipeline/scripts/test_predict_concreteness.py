"""Tests for predict_concreteness.py — FastText concreteness regression."""
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))

from predict_concreteness import (
    build_synset_embeddings, build_training_data, run_model_shootout,
    retrain_winner, fill_concreteness_gaps, revert_concreteness_predictions,
    cmd_shootout, cmd_fill, cmd_revert,
)
from utils import EMBEDDING_DIM, FastTextVectors


def _pad(vec) -> np.ndarray:
    """Right-pad a short vector with zeros to EMBEDDING_DIM.

    Tests historically used compact 4-dim fixtures for readability. The
    FastTextVectors invariant requires shape[1] == EMBEDDING_DIM, so we pad
    here rather than rewriting every fixture's expected values.
    """
    arr = np.asarray(vec, dtype=np.float32)
    if arr.shape[0] >= EMBEDDING_DIM:
        return arr[:EMBEDDING_DIM]
    out = np.zeros(EMBEDDING_DIM, dtype=np.float32)
    out[: arr.shape[0]] = arr
    return out


def _ft(mapping: dict[str, tuple]) -> FastTextVectors:
    """Build a FastTextVectors container from a {word: tuple-or-array} mapping."""
    if not mapping:
        return FastTextVectors(
            matrix=np.empty((0, EMBEDDING_DIM), dtype=np.float32),
            word_to_idx={},
        )
    words = list(mapping.keys())
    matrix = np.array([_pad(mapping[w]) for w in words], dtype=np.float32)
    word_to_idx = {w: i for i, w in enumerate(words)}
    return FastTextVectors(matrix=matrix, word_to_idx=word_to_idx)


def _make_test_db():
    """In-memory DB with synsets, lemmas, and synset_concreteness."""
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE synsets (
            synset_id TEXT PRIMARY KEY, pos TEXT, definition TEXT
        );
        CREATE TABLE lemmas (
            lemma TEXT, synset_id TEXT, PRIMARY KEY (lemma, synset_id)
        );
        CREATE TABLE synset_concreteness (
            synset_id TEXT PRIMARY KEY,
            score REAL NOT NULL,
            source TEXT NOT NULL
        );

        INSERT INTO synsets VALUES ('100', 'n', 'a fruit');
        INSERT INTO synsets VALUES ('200', 'n', 'fairness');
        INSERT INTO synsets VALUES ('300', 'v', 'to move');

        INSERT INTO lemmas VALUES ('apple', '100');
        INSERT INTO lemmas VALUES ('fruit', '100');
        INSERT INTO lemmas VALUES ('justice', '200');
        INSERT INTO lemmas VALUES ('run', '300');
        INSERT INTO lemmas VALUES ('sprint', '300');
    """)
    conn.commit()
    return conn


def _make_vectors() -> FastTextVectors:
    """Fake FastText vectors — 4d for testing."""
    return _ft({
        "apple":   (1.0, 0.0, 0.0, 0.0),
        "fruit":   (0.9, 0.1, 0.0, 0.0),
        "justice": (0.0, 0.0, 1.0, 0.0),
        "run":     (0.0, 1.0, 0.0, 0.0),
        "sprint":  (0.0, 0.8, 0.2, 0.0),
    })


def test_build_synset_embeddings_mean():
    conn = _make_test_db()
    vectors = _make_vectors()
    embeddings = build_synset_embeddings(conn, vectors)

    # synset 100 has apple + fruit → mean
    assert "100" in embeddings
    expected = _pad([(1.0 + 0.9) / 2, (0.0 + 0.1) / 2, 0.0, 0.0])
    np.testing.assert_allclose(embeddings["100"], expected, atol=1e-6)

    # synset 300 has run + sprint → mean
    assert "300" in embeddings
    expected = _pad([0.0, (1.0 + 0.8) / 2, (0.0 + 0.2) / 2, 0.0])
    np.testing.assert_allclose(embeddings["300"], expected, atol=1e-6)


def test_build_synset_embeddings_skips_oov():
    conn = _make_test_db()
    vectors = _ft({"apple": (1.0, 0.0, 0.0, 0.0)})  # only apple, no fruit/justice/run/sprint
    embeddings = build_synset_embeddings(conn, vectors)

    assert "100" in embeddings  # apple covers synset 100
    assert "200" not in embeddings  # justice is OOV
    assert "300" not in embeddings  # run+sprint OOV


def test_build_training_data():
    conn = _make_test_db()
    # Add Brysbaert scores
    conn.executemany(
        "INSERT INTO synset_concreteness VALUES (?, ?, ?)",
        [("100", 4.82, "brysbaert"), ("200", 1.78, "brysbaert")],
    )
    conn.commit()

    vectors = _make_vectors()
    embeddings = build_synset_embeddings(conn, vectors)
    X, y, synset_ids = build_training_data(conn, embeddings)

    assert X.shape[0] == 2  # 2 scored synsets with embeddings
    assert X.shape[1] == EMBEDDING_DIM  # padded to full embedding width
    assert len(y) == 2
    assert len(synset_ids) == 2
    # Verify scores match
    idx_100 = synset_ids.index("100")
    assert y[idx_100] == pytest.approx(4.82)
    idx_200 = synset_ids.index("200")
    assert y[idx_200] == pytest.approx(1.78)


def test_build_training_data_skips_unembedded():
    conn = _make_test_db()
    conn.executemany(
        "INSERT INTO synset_concreteness VALUES (?, ?, ?)",
        [("100", 4.82, "brysbaert"), ("200", 1.78, "brysbaert")],
    )
    conn.commit()

    # Only apple in vectors — synset 200 (justice) has no embedding
    vectors = _ft({"apple": (1.0, 0.0, 0.0, 0.0)})
    embeddings = build_synset_embeddings(conn, vectors)
    X, y, synset_ids = build_training_data(conn, embeddings)

    assert X.shape[0] == 1  # only synset 100
    assert "100" in synset_ids
    assert "200" not in synset_ids


def test_build_training_data_ignores_regression_source():
    """Only use Brysbaert ground truth, not previously predicted values."""
    conn = _make_test_db()
    conn.executemany(
        "INSERT INTO synset_concreteness VALUES (?, ?, ?)",
        [
            ("100", 4.82, "brysbaert"),
            ("200", 2.50, "fasttext_regression"),  # predicted — skip
        ],
    )
    conn.commit()

    vectors = _make_vectors()
    embeddings = build_synset_embeddings(conn, vectors)
    X, y, synset_ids = build_training_data(conn, embeddings)

    assert X.shape[0] == 1  # only brysbaert source
    assert "100" in synset_ids
    assert "200" not in synset_ids


def _make_synthetic_data(n=200, dim=4, seed=42):
    """Synthetic data where concreteness ~ first dimension (linear relationship)."""
    rng = np.random.RandomState(seed)
    X = rng.randn(n, dim)
    y = 3.0 + X[:, 0] * 0.8 + rng.randn(n) * 0.2  # mostly linear
    y = np.clip(y, 1.0, 5.0)
    return X, y


def test_run_model_shootout_returns_results():
    X, y = _make_synthetic_data()
    results = run_model_shootout(X, y)

    assert "models" in results
    assert len(results["models"]) == 4  # Ridge, SVR, k-NN, RF
    assert "best_model_name" in results
    assert "best_model" in results

    # Each model has metrics
    for m in results["models"]:
        assert "name" in m
        assert "pearson_r" in m
        assert "r2" in m
        assert "rmse" in m
        # Metrics should be reasonable on synthetic linear data
        assert m["pearson_r"] > 0.5
        assert m["rmse"] < 2.0


def test_run_model_shootout_best_is_highest_pearson():
    X, y = _make_synthetic_data()
    results = run_model_shootout(X, y)

    pearson_values = [m["pearson_r"] for m in results["models"]]
    best_idx = np.argmax(pearson_values)
    assert results["best_model_name"] == results["models"][best_idx]["name"]


def test_run_model_shootout_deterministic():
    X, y = _make_synthetic_data()
    r1 = run_model_shootout(X, y, random_state=42)
    r2 = run_model_shootout(X, y, random_state=42)

    for m1, m2 in zip(r1["models"], r2["models"]):
        assert m1["pearson_r"] == pytest.approx(m2["pearson_r"], abs=1e-6)


def test_run_model_shootout_svr_subsamples_large_data():
    """SVR grid search subsamples when training data exceeds svr_max_samples."""
    X, y = _make_synthetic_data(n=500, dim=4)
    # Cap at 100 — SVR trains on subsample, evaluates on same test set
    results = run_model_shootout(X, y, svr_max_samples=100)

    assert len(results["models"]) == 4
    svr = next(m for m in results["models"] if m["name"] == "SVR (RBF)")
    assert svr["pearson_r"] > 0.0  # still produces valid results
    assert svr["train_samples"] == 100

    # Other models trained on full training set
    ridge = next(m for m in results["models"] if m["name"] == "Ridge")
    assert ridge["train_samples"] == 400  # 500 * 0.8


def test_retrain_winner_from_shootout():
    X, y = _make_synthetic_data()
    shootout = run_model_shootout(X, y)

    # Serialise and reconstruct — simulates reading from JSON
    shootout_json = {
        "best_model_name": shootout["best_model_name"],
        "models": shootout["models"],
    }
    model = retrain_winner(X, y, shootout_json)

    # Model should predict reasonable values
    preds = model.predict(X[:5])
    assert len(preds) == 5
    for p in preds:
        assert 0.0 <= p <= 6.0  # loose check — synthetic data


def test_retrain_winner_unknown_model():
    X, y = _make_synthetic_data()
    bad_json = {
        "best_model_name": "Nonexistent Model",
        "models": [{"name": "Nonexistent Model", "best_params": {}}],
    }
    with pytest.raises(ValueError, match="Unknown model"):
        retrain_winner(X, y, bad_json)


def test_fill_concreteness_gaps():
    conn = _make_test_db()
    # synset 100 has Brysbaert score, 200 and 300 do not
    conn.execute(
        "INSERT INTO synset_concreteness VALUES ('100', 4.82, 'brysbaert')"
    )
    conn.commit()

    vectors = _make_vectors()
    embeddings = build_synset_embeddings(conn, vectors)

    # Simple mock model that always predicts 3.0
    class MockModel:
        def predict(self, X):
            return np.full(X.shape[0], 3.0)

    stats = fill_concreteness_gaps(conn, embeddings, MockModel())

    assert stats["predicted"] == 2  # synsets 200 and 300
    assert stats["already_scored"] == 1  # synset 100

    # Check DB — synsets 200 and 300 should now have predictions
    rows = conn.execute(
        "SELECT synset_id, score, source FROM synset_concreteness ORDER BY synset_id"
    ).fetchall()
    scored_ids = {r[0] for r in rows}
    assert "200" in scored_ids
    assert "300" in scored_ids

    # Verify source is fasttext_regression
    for sid, score, source in rows:
        if sid != "100":
            assert source == "fasttext_regression"
            assert score == pytest.approx(3.0)


def test_fill_concreteness_gaps_clamps_scores():
    conn = _make_test_db()
    conn.commit()

    vectors = _make_vectors()
    embeddings = build_synset_embeddings(conn, vectors)

    # Model that predicts out-of-range values
    class WildModel:
        def predict(self, X):
            return np.array([0.5, 6.0, 3.0])  # below 1, above 5, normal

    stats = fill_concreteness_gaps(conn, embeddings, WildModel())

    rows = conn.execute(
        "SELECT score FROM synset_concreteness WHERE source = 'fasttext_regression' ORDER BY score"
    ).fetchall()
    scores = [r[0] for r in rows]
    assert min(scores) >= 1.0
    assert max(scores) <= 5.0


def test_revert_concreteness_predictions():
    conn = _make_test_db()
    conn.executemany(
        "INSERT INTO synset_concreteness VALUES (?, ?, ?)",
        [
            ("100", 4.82, "brysbaert"),
            ("200", 3.50, "fasttext_regression"),
            ("300", 2.10, "fasttext_regression"),
        ],
    )
    conn.commit()

    stats = revert_concreteness_predictions(conn)

    assert stats["deleted"] == 2
    assert stats["brysbaert_retained"] == 1

    # Only Brysbaert rows remain
    rows = conn.execute("SELECT synset_id, source FROM synset_concreteness").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "100"
    assert rows[0][1] == "brysbaert"


def test_revert_idempotent():
    conn = _make_test_db()
    conn.execute("INSERT INTO synset_concreteness VALUES ('100', 4.82, 'brysbaert')")
    conn.commit()

    stats = revert_concreteness_predictions(conn)
    assert stats["deleted"] == 0
    assert stats["brysbaert_retained"] == 1


def _make_cmd_test_db_and_vectors(n=80):
    """Create DB + vectors with enough data for cmd_shootout (needs >=50 samples).

    Generates n synsets, each with one lemma and a Brysbaert score, plus
    10 extra unscored synsets for gap-fill testing.
    """
    rng = np.random.RandomState(99)
    dim = 4
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, pos TEXT, definition TEXT);
        CREATE TABLE lemmas (lemma TEXT, synset_id TEXT, PRIMARY KEY (lemma, synset_id));
        CREATE TABLE synset_concreteness (synset_id TEXT PRIMARY KEY, score REAL NOT NULL, source TEXT NOT NULL);
    """)
    vectors = {}
    scored_rows = []
    for i in range(n):
        sid = str(1000 + i)
        lemma = f"word{i}"
        conn.execute("INSERT INTO synsets VALUES (?, 'n', ?)", (sid, f"def {i}"))
        conn.execute("INSERT INTO lemmas VALUES (?, ?)", (lemma, sid))
        vectors[lemma] = tuple(rng.randn(dim).tolist())
        scored_rows.append((sid, round(1.0 + rng.rand() * 4.0, 2), "brysbaert"))

    # Extra unscored synsets for gap-fill
    for i in range(n, n + 10):
        sid = str(1000 + i)
        lemma = f"word{i}"
        conn.execute("INSERT INTO synsets VALUES (?, 'n', ?)", (sid, f"def {i}"))
        conn.execute("INSERT INTO lemmas VALUES (?, ?)", (lemma, sid))
        vectors[lemma] = tuple(rng.randn(dim).tolist())

    conn.executemany("INSERT INTO synset_concreteness VALUES (?, ?, ?)", scored_rows)
    conn.commit()
    return conn, _ft(vectors), n


def test_cmd_shootout_writes_json_not_db(tmp_path):
    conn, vectors, n_scored = _make_cmd_test_db_and_vectors()
    output = tmp_path / "shootout.json"

    cmd_shootout(conn, vectors, str(output))

    # JSON was written
    assert output.exists()
    data = json.loads(output.read_text())
    assert "models" in data
    assert "best_model_name" in data
    assert len(data["models"]) == 4

    # DB was NOT modified — still only n_scored Brysbaert rows
    count = conn.execute("SELECT COUNT(*) FROM synset_concreteness").fetchone()[0]
    assert count == n_scored


def test_cmd_fill_requires_shootout(tmp_path):
    conn = _make_test_db()
    conn.execute("INSERT INTO synset_concreteness VALUES ('100', 4.82, 'brysbaert')")
    conn.commit()

    vectors = _make_vectors()
    missing_path = str(tmp_path / "nonexistent.json")

    with pytest.raises(FileNotFoundError, match="run shootout"):
        cmd_fill(conn, vectors, missing_path)


def test_cmd_fill_uses_shootout_winner(tmp_path):
    conn, vectors, _ = _make_cmd_test_db_and_vectors()
    output = tmp_path / "shootout.json"

    # Run shootout first
    cmd_shootout(conn, vectors, str(output))

    # Then fill — 10 extra synsets have no Brysbaert score but have embeddings
    stats = cmd_fill(conn, vectors, str(output))
    assert stats["gap_fill"]["predicted"] >= 1

    # DB now has regression predictions
    reg_count = conn.execute(
        "SELECT COUNT(*) FROM synset_concreteness WHERE source = 'fasttext_regression'"
    ).fetchone()[0]
    assert reg_count >= 1


def test_cmd_revert():
    conn = _make_test_db()
    conn.executemany(
        "INSERT INTO synset_concreteness VALUES (?, ?, ?)",
        [
            ("100", 4.82, "brysbaert"),
            ("200", 3.50, "fasttext_regression"),
        ],
    )
    conn.commit()

    stats = cmd_revert(conn)
    assert stats["deleted"] == 1

    count = conn.execute("SELECT COUNT(*) FROM synset_concreteness").fetchone()[0]
    assert count == 1
