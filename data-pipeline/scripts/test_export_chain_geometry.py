"""Characterisation test for export_chain_geometry (grading signal precompute)."""
import json
import sqlite3
import struct

import pytest

import export_chain_geometry as ex


def _pack(vec):
    return struct.pack(f"{len(vec)}f", *vec)


def _db():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE synset_centroids (synset_id TEXT PRIMARY KEY, centroid BLOB, property_count INTEGER)")
    for sid, vec in [("T", [1, 0, 0, 0]), ("A", [1, 1, 0, 0]), ("V", [0, 1, 1, 0])]:
        conn.execute("INSERT INTO synset_centroids VALUES (?,?,?)", (sid, _pack(vec), 2))
    conn.commit()
    return conn


def test_geometry_matches_primitives():
    conn = _db()
    from evaluate_cascade import _centroid, _cosine_distance
    ns = ["T", "A", "V"]
    hops = [_cosine_distance(_centroid(conn, a), _centroid(conn, b)) for a, b in zip(ns, ns[1:])]
    g = ex.chain_geometry(conn, ns)
    assert g["n_hops"] == 2
    assert g["max_hop_cos"] == pytest.approx(max(hops))
    assert g["path_total_cos"] == pytest.approx(sum(hops))
    assert g["endpoint_cos_dist"] == pytest.approx(_cosine_distance(_centroid(conn, "T"), _centroid(conn, "V")))


def test_missing_centroid_yields_none():
    conn = _db()
    g = ex.chain_geometry(conn, ["T", "MISSING", "V"])
    assert g["max_hop_cos"] is None and g["path_total_cos"] is None
    assert g["n_hops"] == 2


def test_export_dedups_and_skips_empty(tmp_path):
    conn = _db()
    chains = tmp_path / "chains.jsonl"
    chains.write_text("\n".join(json.dumps(r) for r in [
        {"chain_signature": "s1", "chain": [{"synset_id": "T"}, {"synset_id": "V"}]},
        {"chain_signature": "s1", "chain": [{"synset_id": "T"}, {"synset_id": "A"}]},  # dup sig
        {"chain_signature": "s2", "chain": []},  # empty
    ]) + "\n", encoding="utf-8")
    out = tmp_path / "geom.jsonl"
    n = ex.export(conn, [str(chains)], str(out))
    rows = [json.loads(l) for l in open(out)]
    assert n == 1 and len(rows) == 1
    assert rows[0]["chain_signature"] == "s1"
    assert "max_hop_cos" in rows[0]
