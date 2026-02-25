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
