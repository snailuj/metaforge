"""Predict concreteness for unrated synsets using FastText embeddings.

Trains regression models on Brysbaert-scored synsets, evaluates a 4-model
shootout, and fills the concreteness gap with the winning model.

Usage:
    python predict_concreteness.py --db PATH [--fasttext PATH] [-o results.json]
"""
import argparse
import json
import logging
import sqlite3
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from utils import LEXICON_V2, FASTTEXT_VEC

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
        prog="predict_concreteness.py",
        description="Predict concreteness for unrated synsets using FastText embeddings.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
commands:
  shootout   Train and evaluate 4 regression models (no DB writes)
  fill       Fill concreteness gaps using the shootout winner
  revert     Delete all regression predictions, restore Brysbaert-only

examples:
  %(prog)s shootout --db DB --fasttext VEC -o shootout.json
  %(prog)s fill --db DB --fasttext VEC --shootout shootout.json
  %(prog)s revert --db DB
""",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # Shared flags — added to each subparser so they work after the subcommand
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--verbose", "-v", action="store_true",
                        help="enable debug logging")
    common.add_argument("--db", default=str(LEXICON_V2),
                        help="lexicon database path (default: %(default)s)")

    # shootout
    p_shootout = sub.add_parser("shootout", parents=[common],
        help="Train and evaluate models (no DB writes)")
    p_shootout.add_argument("--fasttext", default=str(FASTTEXT_VEC),
        help="FastText .vec file (default: %(default)s)")
    p_shootout.add_argument("--output", "-o", required=True,
        help="path for results JSON")

    # fill
    p_fill = sub.add_parser("fill", parents=[common],
        help="Fill gaps using shootout winner")
    p_fill.add_argument("--fasttext", default=str(FASTTEXT_VEC),
        help="FastText .vec file (default: %(default)s)")
    p_fill.add_argument("--shootout", required=True,
        help="path to shootout results JSON")

    # revert
    sub.add_parser("revert", parents=[common],
        help="Delete regression predictions, restore Brysbaert-only")

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
