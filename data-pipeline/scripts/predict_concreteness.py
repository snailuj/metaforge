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
