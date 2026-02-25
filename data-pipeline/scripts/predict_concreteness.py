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
