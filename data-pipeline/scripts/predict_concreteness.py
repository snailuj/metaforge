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
