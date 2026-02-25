# FastText Concreteness Regression — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Train regression models on Brysbaert concreteness scores + FastText 300d embeddings, pick the best, and fill the concreteness gap from 48.5% to 80%+ coverage.

**Architecture:** A new `predict_concreteness.py` script with three side-effect-free subcommands:

1. **`shootout`** — Pure evaluation: trains 4 models (Ridge, SVR, k-NN, Random Forest) with GridSearchCV, writes results JSON. Never modifies the DB.
2. **`fill`** — Reads shootout JSON, retrains the winner on ALL training data (not 80/20 — max accuracy for production), fills unrated synsets. Requires prior shootout.
3. **`revert`** — Deletes all `source='fasttext_regression'` rows, restoring Brysbaert-only state.

Each operation is independently runnable and idempotent. The shootout can be re-run without filling gaps. Gap-filling can be re-run (after revert) with a different shootout.

**Tech Stack:** Python 3, sqlite3, numpy, scikit-learn (new dep), pytest.

**Design doc:** `docs/plans/2026-02-25-fasttext-concreteness-regression-design.md`

---

### Task 1: Add scikit-learn dependency and extract vector loader

Add scikit-learn to requirements.txt. Extract `load_fasttext_vectors` from `enrich_pipeline.py` into `utils.py` to avoid heavy transitive imports.

**Files:**
- Modify: `data-pipeline/requirements.txt`
- Modify: `data-pipeline/scripts/utils.py`
- Modify: `data-pipeline/scripts/enrich_pipeline.py`
- Create: `data-pipeline/scripts/test_predict_concreteness.py`
- Create: `data-pipeline/scripts/predict_concreteness.py`

**Step 1: Write the failing test**

```python
"""Tests for predict_concreteness.py — FastText concreteness regression."""
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))

from predict_concreteness import build_synset_embeddings


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


def _make_vectors():
    """Fake FastText vectors — 4d for testing."""
    return {
        "apple":   (1.0, 0.0, 0.0, 0.0),
        "fruit":   (0.9, 0.1, 0.0, 0.0),
        "justice": (0.0, 0.0, 1.0, 0.0),
        "run":     (0.0, 1.0, 0.0, 0.0),
        "sprint":  (0.0, 0.8, 0.2, 0.0),
    }


def test_build_synset_embeddings_mean():
    conn = _make_test_db()
    vectors = _make_vectors()
    embeddings = build_synset_embeddings(conn, vectors)

    # synset 100 has apple + fruit → mean
    assert "100" in embeddings
    expected = np.array([(1.0 + 0.9) / 2, (0.0 + 0.1) / 2, 0.0, 0.0])
    np.testing.assert_allclose(embeddings["100"], expected, atol=1e-6)

    # synset 300 has run + sprint → mean
    assert "300" in embeddings
    expected = np.array([0.0, (1.0 + 0.8) / 2, (0.0 + 0.2) / 2, 0.0])
    np.testing.assert_allclose(embeddings["300"], expected, atol=1e-6)


def test_build_synset_embeddings_skips_oov():
    conn = _make_test_db()
    vectors = {"apple": (1.0, 0.0, 0.0, 0.0)}  # only apple, no fruit/justice/run/sprint
    embeddings = build_synset_embeddings(conn, vectors)

    assert "100" in embeddings  # apple covers synset 100
    assert "200" not in embeddings  # justice is OOV
    assert "300" not in embeddings  # run+sprint OOV
```

**Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && python -m pytest data-pipeline/scripts/test_predict_concreteness.py -v`
Expected: FAIL with `ModuleNotFoundError` (predict_concreteness doesn't exist)

**Step 3: Add scikit-learn, extract vector loader, write minimal implementation**

Add to `data-pipeline/requirements.txt`:
```
scikit-learn>=1.3.0,<2.0.0
```

Move `load_fasttext_vectors` and its cache from `enrich_pipeline.py` to `utils.py`. In `enrich_pipeline.py`, replace the function with an import: `from utils import load_fasttext_vectors`.

Add to `utils.py` (after the existing code):

```python
import numpy as np
from typing import Optional

_fasttext_cache: dict[str, dict[str, tuple[float, ...]]] = {}


def load_fasttext_vectors(vec_path: str) -> dict[str, tuple[float, ...]]:
    """Load FastText vectors from .vec file into memory.

    Results are cached by path — subsequent calls return the same dict.
    """
    if vec_path in _fasttext_cache:
        print(f"  Using cached vectors for {vec_path}")
        return _fasttext_cache[vec_path]

    vectors = {}
    print(f"  Loading {vec_path}...")

    with open(vec_path, "r", encoding="utf-8") as f:
        header = f.readline().strip().split()
        num_words, dim = int(header[0]), int(header[1])
        print(f"  Header: {num_words} words, {dim}d")

        if dim != EMBEDDING_DIM:
            raise ValueError(
                f"FastText dimension mismatch: file has {dim}d, expected {EMBEDDING_DIM}d"
            )

        for i, line in enumerate(f):
            parts = line.rstrip().split(" ")
            word = parts[0]
            try:
                vec = tuple(float(x) for x in parts[1:])
                if len(vec) == dim:
                    vectors[word] = vec
            except ValueError:
                continue

            if (i + 1) % 200000 == 0:
                print(f"    Loaded {i + 1} words...")

    print(f"  Loaded {len(vectors)} vectors")
    _fasttext_cache[vec_path] = vectors
    return vectors
```

In `enrich_pipeline.py`, replace the `_fasttext_cache` variable and `load_fasttext_vectors` function body with:

```python
from utils import load_fasttext_vectors
```

And remove the old `_fasttext_cache` and `load_fasttext_vectors` definitions.

Create `data-pipeline/scripts/predict_concreteness.py`:

```python
"""Predict concreteness for unrated synsets using FastText embeddings.

Trains regression models on Brysbaert-scored synsets, evaluates a 4-model
shootout, and fills the concreteness gap with the winning model.

Usage:
    python predict_concreteness.py --db PATH [--fasttext PATH] [-o results.json]
"""
import logging
import sqlite3

import numpy as np

log = logging.getLogger(__name__)


def build_synset_embeddings(
    conn: sqlite3.Connection,
    vectors: dict[str, tuple[float, ...]],
) -> dict[str, np.ndarray]:
    """Compute mean embedding per synset from lemma vectors.

    For each synset, averages the FastText vectors of all its lemmas
    that have embeddings. Synsets with no in-vocabulary lemmas are skipped.
    """
    rows = conn.execute("SELECT synset_id, lemma FROM lemmas").fetchall()

    synset_lemmas: dict[str, list[str]] = {}
    for synset_id, lemma in rows:
        synset_lemmas.setdefault(synset_id, []).append(lemma)

    embeddings = {}
    for synset_id, lemmas in synset_lemmas.items():
        vecs = [np.array(vectors[l]) for l in lemmas if l in vectors]
        if vecs:
            embeddings[synset_id] = np.mean(vecs, axis=0)

    return embeddings
```

**Step 4: Install new dep and run test to verify it passes**

Run: `source .venv/bin/activate && pip install scikit-learn>=1.3.0 && python -m pytest data-pipeline/scripts/test_predict_concreteness.py -v`
Expected: 2 PASS

Also run existing tests to verify the vector loader refactor didn't break anything:
Run: `python -m pytest data-pipeline/scripts/ -v --timeout=60`

**Step 5: Commit**

```bash
git add data-pipeline/requirements.txt data-pipeline/scripts/utils.py \
  data-pipeline/scripts/enrich_pipeline.py \
  data-pipeline/scripts/predict_concreteness.py \
  data-pipeline/scripts/test_predict_concreteness.py
git commit -m "feat(concreteness): add scikit-learn dep, extract vector loader, synset embedding builder"
```

---

### Task 2: Build training data from Brysbaert scores

Extract (X, y) training data: embeddings for scored synsets paired with their Brysbaert scores.

**Files:**
- Modify: `data-pipeline/scripts/predict_concreteness.py`
- Modify: `data-pipeline/scripts/test_predict_concreteness.py`

**Step 1: Write the failing test**

```python
from predict_concreteness import build_training_data


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
    assert X.shape[1] == 4  # 4d test vectors
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
    vectors = {"apple": (1.0, 0.0, 0.0, 0.0)}
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
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest data-pipeline/scripts/test_predict_concreteness.py::test_build_training_data -v`
Expected: FAIL with `ImportError`

**Step 3: Write minimal implementation**

Add to `predict_concreteness.py`:

```python
def build_training_data(
    conn: sqlite3.Connection,
    synset_embeddings: dict[str, np.ndarray],
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Build (X, y) training data from Brysbaert-scored synsets.

    Only uses source='brysbaert' rows (ground truth), not previously
    predicted values. Skips synsets without embeddings.

    Returns (X, y, synset_ids) where X is (n, dim) embeddings and
    y is (n,) concreteness scores.
    """
    rows = conn.execute(
        "SELECT synset_id, score FROM synset_concreteness WHERE source = 'brysbaert'"
    ).fetchall()

    X_list = []
    y_list = []
    ids = []

    for synset_id, score in rows:
        if synset_id in synset_embeddings:
            X_list.append(synset_embeddings[synset_id])
            y_list.append(score)
            ids.append(synset_id)

    if not X_list:
        dim = next(iter(synset_embeddings.values())).shape[0] if synset_embeddings else 0
        return np.empty((0, dim)), np.array([]), []

    return np.array(X_list), np.array(y_list), ids
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest data-pipeline/scripts/test_predict_concreteness.py -v`
Expected: 5 PASS

**Step 5: Commit**

```bash
git add data-pipeline/scripts/predict_concreteness.py \
  data-pipeline/scripts/test_predict_concreteness.py
git commit -m "feat(concreteness): build training data from Brysbaert scores"
```

---

### Task 3: Model shootout — train, evaluate, compare

Train 4 models with GridSearchCV, evaluate on held-out test set, return ranked results.

**Files:**
- Modify: `data-pipeline/scripts/predict_concreteness.py`
- Modify: `data-pipeline/scripts/test_predict_concreteness.py`

**Step 1: Write the failing test**

```python
from predict_concreteness import run_model_shootout


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
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest data-pipeline/scripts/test_predict_concreteness.py::test_run_model_shootout_returns_results -v`
Expected: FAIL with `ImportError`

**Step 3: Write minimal implementation**

Add to `predict_concreteness.py`:

```python
from scipy.stats import pearsonr
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import GridSearchCV, train_test_split
from sklearn.neighbors import KNeighborsRegressor
from sklearn.linear_model import Ridge
from sklearn.svm import SVR


def run_model_shootout(
    X: np.ndarray,
    y: np.ndarray,
    test_size: float = 0.2,
    random_state: int = 42,
) -> dict:
    """Train 4 models, evaluate on held-out test set, return ranked results.

    Models: Ridge, SVR (RBF), k-NN, Random Forest.
    Hyperparameters tuned via 5-fold cross-validation on training set.

    Returns dict with:
        models: list of {name, pearson_r, r2, rmse, params}
        best_model_name: name of model with highest pearson_r
        best_model: fitted sklearn estimator
    """
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=random_state,
    )

    configs = [
        {
            "name": "Ridge",
            "estimator": Ridge(),
            "params": {"alpha": [0.01, 0.1, 1.0, 10.0, 100.0]},
        },
        {
            "name": "SVR (RBF)",
            "estimator": SVR(kernel="rbf"),
            "params": {
                "C": [0.1, 1.0, 10.0],
                "gamma": ["scale", "auto"],
                "epsilon": [0.05, 0.1, 0.2],
            },
        },
        {
            "name": "k-NN",
            "estimator": KNeighborsRegressor(),
            "params": {
                "n_neighbors": [3, 5, 10, 20],
                "weights": ["uniform", "distance"],
            },
        },
        {
            "name": "Random Forest",
            "estimator": RandomForestRegressor(random_state=random_state),
            "params": {
                "n_estimators": [50, 100],
                "max_depth": [10, 20, None],
            },
        },
    ]

    results = []
    best_score = -1.0
    best_model = None
    best_name = None

    for cfg in configs:
        log.info("Training %s...", cfg["name"])
        grid = GridSearchCV(
            cfg["estimator"], cfg["params"],
            cv=5, scoring="r2", n_jobs=-1,
        )
        grid.fit(X_train, y_train)
        y_pred = grid.predict(X_test)

        r, _ = pearsonr(y_test, y_pred)
        r2 = grid.score(X_test, y_test)
        rmse = float(np.sqrt(np.mean((y_test - y_pred) ** 2)))

        results.append({
            "name": cfg["name"],
            "pearson_r": round(float(r), 4),
            "r2": round(float(r2), 4),
            "rmse": round(rmse, 4),
            "best_params": grid.best_params_,
        })

        log.info("  %s: r=%.4f  R²=%.4f  RMSE=%.4f  params=%s",
                 cfg["name"], r, r2, rmse, grid.best_params_)

        if r > best_score:
            best_score = r
            best_model = grid.best_estimator_
            best_name = cfg["name"]

    # Sort by pearson_r descending
    results.sort(key=lambda m: m["pearson_r"], reverse=True)

    return {
        "models": results,
        "best_model_name": best_name,
        "best_model": best_model,
        "train_size": len(X_train),
        "test_size": len(X_test),
    }
```

**Step 4: Install scipy and run test to verify it passes**

Run: `source .venv/bin/activate && pip install scipy && python -m pytest data-pipeline/scripts/test_predict_concreteness.py -v`
Expected: 8 PASS

Note: `scipy` is a transitive dependency of scikit-learn but import it explicitly. Add to requirements.txt if not already pulled in.

**Step 5: Commit**

```bash
git add data-pipeline/scripts/predict_concreteness.py \
  data-pipeline/scripts/test_predict_concreteness.py
git commit -m "feat(concreteness): 4-model shootout with GridSearchCV"
```

---

### Task 4: Retrain winner from shootout JSON + gap-fill + revert

Three composable operations: `retrain_winner` reconstructs the winning model from shootout JSON and fits on ALL training data; `fill_concreteness_gaps` writes predictions to DB; `revert_concreteness_predictions` restores Brysbaert-only state.

**Files:**
- Modify: `data-pipeline/scripts/predict_concreteness.py`
- Modify: `data-pipeline/scripts/test_predict_concreteness.py`

**Step 1: Write the failing tests**

```python
from predict_concreteness import (
    retrain_winner, fill_concreteness_gaps, revert_concreteness_predictions,
)


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
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest data-pipeline/scripts/test_predict_concreteness.py::test_retrain_winner_from_shootout -v`
Expected: FAIL with `ImportError`

**Step 3: Write minimal implementation**

Add to `predict_concreteness.py`:

```python
_MODEL_CLASSES = {
    "Ridge": lambda params: Ridge(**params),
    "SVR (RBF)": lambda params: SVR(kernel="rbf", **params),
    "k-NN": lambda params: KNeighborsRegressor(**params),
    "Random Forest": lambda params: RandomForestRegressor(**params),
}


def retrain_winner(
    X: np.ndarray,
    y: np.ndarray,
    shootout_results: dict,
) -> object:
    """Reconstruct and refit the winning model from shootout results.

    Uses ALL training data (no holdout) for maximum production accuracy.
    The shootout JSON provides the model name and best hyperparameters.
    """
    name = shootout_results["best_model_name"]

    if name not in _MODEL_CLASSES:
        raise ValueError(f"Unknown model: {name!r}")

    # Find the best_params for the winner
    winner_entry = next(
        (m for m in shootout_results["models"] if m["name"] == name), None
    )
    if winner_entry is None:
        raise ValueError(f"Model {name!r} not found in shootout results")

    params = winner_entry.get("best_params", {})
    model = _MODEL_CLASSES[name](params)
    model.fit(X, y)

    log.info("Retrained %s on %d samples with params %s", name, len(y), params)
    return model


def fill_concreteness_gaps(
    conn: sqlite3.Connection,
    synset_embeddings: dict[str, np.ndarray],
    model,
) -> dict[str, int]:
    """Predict concreteness for unrated synsets and write to DB.

    Only fills synsets that:
    - Have no existing score in synset_concreteness
    - Have a synset embedding (at least one lemma in FastText)

    Predictions are clamped to [1.0, 5.0] and stored with
    source='fasttext_regression'.
    """
    scored = set(
        r[0] for r in conn.execute(
            "SELECT synset_id FROM synset_concreteness"
        ).fetchall()
    )

    unscored_ids = []
    unscored_vecs = []
    for sid, vec in synset_embeddings.items():
        if sid not in scored:
            unscored_ids.append(sid)
            unscored_vecs.append(vec)

    if not unscored_vecs:
        return {"predicted": 0, "already_scored": len(scored), "no_embedding": 0}

    X = np.array(unscored_vecs)
    predictions = model.predict(X)

    # Clamp to valid Brysbaert range
    predictions = np.clip(predictions, 1.0, 5.0)

    rows = [
        (sid, round(float(score), 4), "fasttext_regression")
        for sid, score in zip(unscored_ids, predictions)
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO synset_concreteness (synset_id, score, source) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()

    all_synsets = set(synset_embeddings.keys())
    no_embedding = len(all_synsets - scored - set(unscored_ids))

    return {
        "predicted": len(rows),
        "already_scored": len(scored),
        "no_embedding": no_embedding,
    }


def revert_concreteness_predictions(conn: sqlite3.Connection) -> dict[str, int]:
    """Delete all fasttext_regression predictions, restoring Brysbaert-only state.

    Idempotent — safe to call even if no regression predictions exist.
    """
    before = conn.execute("SELECT COUNT(*) FROM synset_concreteness").fetchone()[0]
    conn.execute("DELETE FROM synset_concreteness WHERE source = 'fasttext_regression'")
    conn.commit()
    after = conn.execute("SELECT COUNT(*) FROM synset_concreteness").fetchone()[0]

    deleted = before - after
    log.info("Reverted: deleted %d regression predictions, %d Brysbaert retained", deleted, after)

    return {"deleted": deleted, "brysbaert_retained": after}
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest data-pipeline/scripts/test_predict_concreteness.py -v`
Expected: 15 PASS (8 old + 7 new)

**Step 5: Commit**

```bash
git add data-pipeline/scripts/predict_concreteness.py \
  data-pipeline/scripts/test_predict_concreteness.py
git commit -m "feat(concreteness): retrain winner, gap-fill, and revert operations"
```

---

### Task 5: CLI with subcommands (shootout / fill / revert)

Three independent subcommands. `shootout` never touches DB. `fill` requires prior shootout JSON. `revert` restores Brysbaert-only state.

**Files:**
- Modify: `data-pipeline/scripts/predict_concreteness.py`
- Modify: `data-pipeline/scripts/test_predict_concreteness.py`

**Step 1: Write the failing tests**

```python
import json
from predict_concreteness import cmd_shootout, cmd_fill, cmd_revert


def test_cmd_shootout_writes_json_not_db(tmp_path):
    conn = _make_test_db()
    conn.executemany(
        "INSERT INTO synset_concreteness VALUES (?, ?, ?)",
        [("100", 4.82, "brysbaert"), ("200", 1.78, "brysbaert")],
    )
    conn.commit()

    vectors = _make_vectors()
    output = tmp_path / "shootout.json"

    cmd_shootout(conn, vectors, str(output))

    # JSON was written
    assert output.exists()
    data = json.loads(output.read_text())
    assert "models" in data
    assert "best_model_name" in data
    assert len(data["models"]) == 4

    # DB was NOT modified — still only 2 Brysbaert rows
    count = conn.execute("SELECT COUNT(*) FROM synset_concreteness").fetchone()[0]
    assert count == 2


def test_cmd_fill_requires_shootout(tmp_path):
    conn = _make_test_db()
    conn.execute("INSERT INTO synset_concreteness VALUES ('100', 4.82, 'brysbaert')")
    conn.commit()

    vectors = _make_vectors()
    missing_path = str(tmp_path / "nonexistent.json")

    with pytest.raises(FileNotFoundError, match="run shootout"):
        cmd_fill(conn, vectors, missing_path)


def test_cmd_fill_uses_shootout_winner(tmp_path):
    conn = _make_test_db()
    conn.executemany(
        "INSERT INTO synset_concreteness VALUES (?, ?, ?)",
        [("100", 4.82, "brysbaert"), ("200", 1.78, "brysbaert")],
    )
    conn.commit()

    vectors = _make_vectors()
    output = tmp_path / "shootout.json"

    # Run shootout first
    cmd_shootout(conn, vectors, str(output))

    # Then fill — synset 300 has no Brysbaert score but has embeddings
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
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest data-pipeline/scripts/test_predict_concreteness.py::test_cmd_shootout_writes_json_not_db -v`
Expected: FAIL with `ImportError`

**Step 3: Write minimal implementation**

Add to `predict_concreteness.py`:

```python
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from utils import LEXICON_V2, FASTTEXT_VEC


def _get_git_commit() -> str:
    """Return short git commit hash, or 'unknown' if not in a repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def cmd_shootout(
    conn: sqlite3.Connection,
    vectors: dict[str, tuple[float, ...]],
    output_path: str,
    random_state: int = 42,
) -> dict:
    """Run model shootout and write results JSON. Never modifies DB."""
    embeddings = build_synset_embeddings(conn, vectors)
    log.info("Built %d synset embeddings", len(embeddings))

    X, y, synset_ids = build_training_data(conn, embeddings)
    log.info("Training data: %d samples", len(y))

    if len(y) < 50:
        raise ValueError(f"Too few training samples ({len(y)}) — need at least 50")

    shootout = run_model_shootout(X, y, random_state=random_state)

    results = {
        "models": shootout["models"],
        "best_model_name": shootout["best_model_name"],
        "train_size": shootout["train_size"],
        "test_size": shootout["test_size"],
        "git_commit": _get_git_commit(),
    }

    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    log.info("Shootout results written to %s", output_path)

    return results


def cmd_fill(
    conn: sqlite3.Connection,
    vectors: dict[str, tuple[float, ...]],
    shootout_path: str,
) -> dict:
    """Fill concreteness gaps using the winner from a prior shootout.

    Reads shootout JSON, retrains the winner on ALL training data,
    then predicts for unrated synsets.
    """
    if not Path(shootout_path).exists():
        raise FileNotFoundError(
            f"Shootout results not found: {shootout_path} — run shootout before gap-filling"
        )

    with open(shootout_path) as f:
        shootout_results = json.load(f)

    embeddings = build_synset_embeddings(conn, vectors)
    X, y, _ = build_training_data(conn, embeddings)

    log.info("Retraining %s on %d samples (full training set)...",
             shootout_results["best_model_name"], len(y))
    model = retrain_winner(X, y, shootout_results)

    gap_stats = fill_concreteness_gaps(conn, embeddings, model)

    total = conn.execute("SELECT COUNT(*) FROM synsets").fetchone()[0]
    scored = conn.execute("SELECT COUNT(*) FROM synset_concreteness").fetchone()[0]
    pct = round(scored / total * 100, 1) if total > 0 else 0

    return {
        "gap_fill": gap_stats,
        "model_used": shootout_results["best_model_name"],
        "coverage": {"total_synsets": total, "scored": scored, "pct": pct},
        "git_commit": _get_git_commit(),
    }


def cmd_revert(conn: sqlite3.Connection) -> dict:
    """Revert to Brysbaert-only concreteness state."""
    return revert_concreteness_predictions(conn)


def main():
    parser = argparse.ArgumentParser(
        description="Concreteness regression: shootout / fill / revert"
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    # shootout
    p_shootout = sub.add_parser("shootout", help="Train and evaluate models (no DB writes)")
    p_shootout.add_argument("--db", default=str(LEXICON_V2))
    p_shootout.add_argument("--fasttext", default=str(FASTTEXT_VEC))
    p_shootout.add_argument("--output", "-o", required=True, help="Path for results JSON")

    # fill
    p_fill = sub.add_parser("fill", help="Fill gaps using shootout winner")
    p_fill.add_argument("--db", default=str(LEXICON_V2))
    p_fill.add_argument("--fasttext", default=str(FASTTEXT_VEC))
    p_fill.add_argument("--shootout", required=True, help="Path to shootout results JSON")

    # revert
    p_revert = sub.add_parser("revert", help="Delete regression predictions, restore Brysbaert-only")
    p_revert.add_argument("--db", default=str(LEXICON_V2))

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    conn = sqlite3.connect(args.db)
    try:
        if args.command == "shootout":
            from utils import load_fasttext_vectors
            vectors = load_fasttext_vectors(args.fasttext)
            results = cmd_shootout(conn, vectors, args.output)
            print(f"\n=== Shootout ({results.get('git_commit', '?')}) ===")
            for m in results["models"]:
                print(f"  {m['name']:20s}  r={m['pearson_r']:.4f}  R²={m['r2']:.4f}  RMSE={m['rmse']:.4f}")
            print(f"\n  Winner: {results['best_model_name']}")
            print(f"  Results: {args.output}")

        elif args.command == "fill":
            from utils import load_fasttext_vectors
            vectors = load_fasttext_vectors(args.fasttext)
            results = cmd_fill(conn, vectors, args.shootout)
            cov = results["coverage"]
            gap = results["gap_fill"]
            print(f"\n=== Fill ({results.get('git_commit', '?')}) ===")
            print(f"  Model: {results['model_used']}")
            print(f"  Predicted: {gap['predicted']} synsets")
            print(f"  Coverage: {cov['scored']}/{cov['total_synsets']} ({cov['pct']}%)")

        elif args.command == "revert":
            stats = cmd_revert(conn)
            print(f"\n=== Revert ===")
            print(f"  Deleted: {stats['deleted']} regression predictions")
            print(f"  Retained: {stats['brysbaert_retained']} Brysbaert scores")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest data-pipeline/scripts/test_predict_concreteness.py -v`
Expected: 19 PASS (15 old + 4 new)

**Step 5: Commit**

```bash
git add data-pipeline/scripts/predict_concreteness.py \
  data-pipeline/scripts/test_predict_concreteness.py
git commit -m "feat(concreteness): CLI subcommands — shootout / fill / revert"
```

---

### Task 6: Live run against real DB

Run shootout, fill, and verify coverage reaches 80%+.

**Files:** None (manual verification)

**Step 1: Run shootout (no DB changes)**

```bash
source .venv/bin/activate
python data-pipeline/scripts/predict_concreteness.py shootout \
  --db data-pipeline/output/lexicon_v2.db \
  --fasttext data-pipeline/raw/wiki-news-300d-1M.vec \
  -o data-pipeline/output/concreteness_shootout.json -v
```

**Step 2: Verify shootout output**

Check that:
- All 4 models trained and evaluated
- Best model pearson_r > 0.7 (literature: ~0.8-0.9 for FastText)
- JSON is well-formed, contains model rankings and best_params

**Step 3: Fill gaps**

```bash
python data-pipeline/scripts/predict_concreteness.py fill \
  --db data-pipeline/output/lexicon_v2.db \
  --fasttext data-pipeline/raw/wiki-news-300d-1M.vec \
  --shootout data-pipeline/output/concreteness_shootout.json -v
```

**Step 4: Verify fill output**

Check that:
- Coverage >= 80% (target)
- Predictions in valid range [1.0, 5.0]
- Log shows sensible prediction counts

**Step 5: Verify revert works**

```bash
python data-pipeline/scripts/predict_concreteness.py revert \
  --db data-pipeline/output/lexicon_v2.db
```

Should show deletion count and Brysbaert retention. Then re-fill:

```bash
python data-pipeline/scripts/predict_concreteness.py fill \
  --db data-pipeline/output/lexicon_v2.db \
  --fasttext data-pipeline/raw/wiki-news-300d-1M.vec \
  --shootout data-pipeline/output/concreteness_shootout.json -v
```

**Step 6: Run full test suite**

```bash
python -m pytest data-pipeline/scripts/ -v
cd api && go test ./...
```

**Step 7: Re-run evals with improved coverage**

```bash
python data-pipeline/scripts/evaluate_mrr.py --db data-pipeline/output/lexicon_v2.db --port 8080 -v -o data-pipeline/output/eval_mrr.json
python data-pipeline/scripts/evaluate_discrimination.py --db data-pipeline/output/lexicon_v2.db --port 8080 --max-words 50 --limit 100 -o data-pipeline/output/eval_discrimination.json -v
```

**Step 8: Commit results**

```bash
git add data-pipeline/output/concreteness_shootout.json
git commit -m "data: concreteness regression shootout — [MODEL] r=[R] coverage [PCT]%"
```

---

## CLI Usage Summary

```bash
# 1. Evaluate models (pure, no DB writes)
python predict_concreteness.py shootout --db DB --fasttext VEC -o shootout.json

# 2. Fill gaps with winner (writes to DB)
python predict_concreteness.py fill --db DB --fasttext VEC --shootout shootout.json

# 3. Revert to Brysbaert-only (undo fill)
python predict_concreteness.py revert --db DB

# Re-run shootout after pipeline changes, then re-fill:
python predict_concreteness.py revert --db DB
python predict_concreteness.py shootout --db DB --fasttext VEC -o shootout.json
python predict_concreteness.py fill --db DB --fasttext VEC --shootout shootout.json
```

---

## Summary

| Task | What | Tests | New functions |
|------|------|-------|---------------|
| 1 | scikit-learn dep + vector loader refactor + synset embeddings | 2 | `build_synset_embeddings` |
| 2 | Training data extraction | 3 | `build_training_data` |
| 3 | 4-model shootout with GridSearchCV | 3 | `run_model_shootout` |
| 4 | Retrain winner + gap-fill + revert | 7 | `retrain_winner`, `fill_concreteness_gaps`, `revert_concreteness_predictions` |
| 5 | CLI subcommands (shootout / fill / revert) | 4 | `cmd_shootout`, `cmd_fill`, `cmd_revert`, `main` |
| 6 | Live run + verification | 0 (manual) | — |

**Total: 6 tasks, 19 tests, ~6 commits**

**Dependencies added:** scikit-learn (requirements.txt)
**Refactor:** `load_fasttext_vectors` moved from enrich_pipeline.py → utils.py
