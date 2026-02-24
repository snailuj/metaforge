"""Cluster curated vocabulary entries by FastText cosine similarity.

Groups synonymous vocab entries (e.g. "heavy"/"weighty") into clusters using
Union-Find on pairwise cosine similarity above a configurable threshold.
Each cluster's ID is the smallest vocab_id in the connected component.

Usage:
    python cluster_vocab.py --db PATH [--threshold 0.8]
"""
import argparse
import sqlite3
import struct
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from utils import LEXICON_V2, EMBEDDING_DIM


# ── Union-Find with path compression + union by rank ──

class UnionFind:
    """Disjoint-set data structure with path compression and union by rank."""

    def __init__(self) -> None:
        self._parent: dict[int, int] = {}
        self._rank: dict[int, int] = {}

    def make_set(self, x: int) -> None:
        if x not in self._parent:
            self._parent[x] = x
            self._rank[x] = 0

    def find(self, x: int) -> int:
        if self._parent[x] != x:
            self._parent[x] = self.find(self._parent[x])
        return self._parent[x]

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self._rank[ra] < self._rank[rb]:
            ra, rb = rb, ra
        self._parent[rb] = ra
        if self._rank[ra] == self._rank[rb]:
            self._rank[ra] += 1

    def components(self) -> dict[int, list[int]]:
        """Return {root: [members]} for all components."""
        groups: dict[int, list[int]] = {}
        for x in self._parent:
            root = self.find(x)
            groups.setdefault(root, []).append(x)
        return groups


def cluster_vocab(
    conn: sqlite3.Connection,
    threshold: float = 0.8,
    chunk_size: int = 2048,
) -> dict[str, int]:
    """Cluster curated vocab entries by embedding cosine similarity.

    Reads property_vocab_curated + lemma_embeddings.
    Writes vocab_clusters table.

    Returns stats dict with cluster counts.
    """
    conn.executescript("""
        DROP TABLE IF EXISTS vocab_clusters;
        CREATE TABLE vocab_clusters (
            vocab_id         INTEGER PRIMARY KEY,
            cluster_id       INTEGER NOT NULL,
            is_representative INTEGER NOT NULL DEFAULT 0,
            is_singleton     INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX idx_vc_cluster ON vocab_clusters(cluster_id);
    """)

    # Load all vocab entries
    all_vocab = conn.execute(
        "SELECT vocab_id, lemma FROM property_vocab_curated ORDER BY vocab_id"
    ).fetchall()
    vocab_ids_all = [row[0] for row in all_vocab]
    lemma_by_vid = {row[0]: row[1] for row in all_vocab}

    if not all_vocab:
        conn.commit()
        return {"total_vocab": 0, "num_clusters": 0, "singletons": 0, "largest_cluster": 0}

    # Load embeddings for vocab entries via lemma_embeddings
    embedded_rows = conn.execute("""
        SELECT pvc.vocab_id, le.embedding
        FROM property_vocab_curated pvc
        JOIN lemma_embeddings le ON LOWER(le.lemma) = LOWER(pvc.lemma)
    """).fetchall()

    # Build matrix of embedded vocab
    embedded_vids: list[int] = []
    vectors: list[list[float]] = []
    for vid, blob in embedded_rows:
        vec = list(struct.unpack(f"{EMBEDDING_DIM}f", blob))
        vectors.append(vec)
        embedded_vids.append(vid)

    # Initialise Union-Find for all vocab entries
    uf = UnionFind()
    for vid in vocab_ids_all:
        uf.make_set(vid)

    n = len(embedded_vids)
    if n >= 2:
        # Build normalised matrix
        matrix = np.array(vectors, dtype=np.float32)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1
        matrix /= norms

        # Chunked pairwise cosine similarity with vectorised threshold
        for ci in range(0, n, chunk_size):
            ci_end = min(ci + chunk_size, n)
            for cj in range(ci, n, chunk_size):
                cj_end = min(cj + chunk_size, n)

                sub_sim = np.dot(matrix[ci:ci_end], matrix[cj:cj_end].T)

                if ci == cj:
                    # Diagonal chunk — upper triangle only
                    rows, cols = np.where(np.triu(sub_sim >= threshold, k=1))
                else:
                    # Off-diagonal chunk
                    rows, cols = np.where(sub_sim >= threshold)

                for li, lj in zip(rows, cols):
                    uf.union(embedded_vids[ci + li], embedded_vids[cj + lj])

    # Resolve clusters: cluster_id = smallest vocab_id in component
    components = uf.components()

    # Map UF root → smallest vocab_id in component
    root_to_cluster: dict[int, int] = {}
    for root, members in components.items():
        root_to_cluster[root] = min(members)

    inserts: list[tuple[int, int, int, int]] = []
    singletons = 0
    cluster_sizes: dict[int, int] = {}

    for vid in vocab_ids_all:
        root = uf.find(vid)
        cluster_id = root_to_cluster[root]
        members = components[root]
        is_singleton = 1 if len(members) == 1 else 0
        is_representative = 1 if vid == cluster_id else 0

        if is_singleton:
            singletons += 1

        cluster_sizes[cluster_id] = cluster_sizes.get(cluster_id, 0) + 1
        inserts.append((vid, cluster_id, is_representative, is_singleton))

    conn.executemany(
        "INSERT INTO vocab_clusters (vocab_id, cluster_id, is_representative, is_singleton) "
        "VALUES (?, ?, ?, ?)",
        inserts,
    )
    conn.commit()

    num_clusters = len(set(r[1] for r in inserts))
    largest = max(cluster_sizes.values()) if cluster_sizes else 0

    print(f"  Clustered {len(vocab_ids_all)} vocab entries into {num_clusters} clusters "
          f"({singletons} singletons, largest={largest})")

    return {
        "total_vocab": len(vocab_ids_all),
        "num_clusters": num_clusters,
        "singletons": singletons,
        "largest_cluster": largest,
    }


def main():
    parser = argparse.ArgumentParser(description="Cluster curated vocabulary by embedding similarity")
    parser.add_argument("--db", default=str(LEXICON_V2), help="Path to lexicon DB")
    parser.add_argument("--threshold", type=float, default=0.8, help="Cosine similarity threshold")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    try:
        cluster_vocab(conn, threshold=args.threshold)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
