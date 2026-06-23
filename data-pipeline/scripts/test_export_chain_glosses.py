"""Test for export_chain_glosses (grading gloss/POS precompute)."""
import json
import sqlite3

import export_chain_glosses as ex


def _db():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, pos TEXT, definition TEXT, domainid INTEGER)")
    conn.executemany("INSERT INTO synsets (synset_id, pos, definition) VALUES (?,?,?)", [
        ("1", "n", "an antique object of value"),
        ("2", "s", "out of fashion"),
        ("3", "n", "a swarm of insects"),
    ])
    conn.commit()
    return conn


def _chain(sig, ids):
    return {"chain_signature": sig, "topic_synset_id": ids[0], "vehicle_synset_id": ids[-1],
            "chain": [{"synset_id": i} for i in ids]}


def test_collect_synset_ids_includes_endpoints_and_steps(tmp_path):
    p = tmp_path / "chains.jsonl"
    p.write_text(json.dumps(_chain("s1", ["1", "2", "3"])) + "\n", encoding="utf-8")
    ids = ex.collect_synset_ids([str(p)])
    assert ids == {"1", "2", "3"}


def test_export_emits_pos_and_definition(tmp_path):
    conn = _db()
    chains = tmp_path / "chains.jsonl"
    chains.write_text(json.dumps(_chain("s1", ["1", "3"])) + "\n", encoding="utf-8")
    out = tmp_path / "glosses.jsonl"
    n = ex.export(conn, [str(chains)], str(out))
    rows = {json.loads(l)["synset_id"]: json.loads(l) for l in open(out)}
    assert n == 2
    assert rows["1"]["pos"] == "n" and "antique" in rows["1"]["definition"]
    assert rows["3"]["pos"] == "n"


def test_export_skips_ids_missing_from_synsets(tmp_path):
    conn = _db()
    chains = tmp_path / "chains.jsonl"
    chains.write_text(json.dumps(_chain("s1", ["1", "999"])) + "\n", encoding="utf-8")  # 999 absent
    out = tmp_path / "glosses.jsonl"
    n = ex.export(conn, [str(chains)], str(out))
    ids = {json.loads(l)["synset_id"] for l in open(out)}
    assert n == 1 and ids == {"1"}
