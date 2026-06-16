"""Test the candidate-senses precompute generator against a tiny in-memory lexicon."""
import json
import sqlite3
from pathlib import Path

import build_sense_candidates as bsc


def _db():
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, pos TEXT, definition TEXT);
        CREATE TABLE lemmas (lemma TEXT, synset_id TEXT);
        CREATE TABLE sense_attributes (sensekey TEXT, lemma TEXT, synset_id TEXT, tagcount INTEGER);
        INSERT INTO synsets VALUES ('1','n','the felt emotion of dread'),
                                   ('2','n','the act of arresting a criminal');
        INSERT INTO lemmas VALUES ('apprehension','1'), ('apprehension','2');
        INSERT INTO sense_attributes VALUES ('k1','apprehension','2', 7);
        """
    )
    conn.commit()
    return conn


def test_emits_all_senses_with_tagcount_ordered(tmp_path):
    out = tmp_path / "sense_candidates_provisional.jsonl"
    chains = tmp_path / "chains.jsonl"
    chains.write_text(json.dumps({
        "topic": "apprehension", "topic_synset_id": "1",
        "vehicle": "apprehension", "vehicle_synset_id": "2",
        "chain": [{"synset_id": "1"}, {"synset_id": "2"}]}) + "\n")
    n = bsc.export(_db(), [str(chains)], str(out))
    assert n == 1  # one lemma
    row = json.loads(out.read_text().strip())
    assert row["lemma"] == "apprehension"
    sids = [s["synset_id"] for s in row["senses"]]
    assert set(sids) == {"1", "2"}
    # Tagged sense (tagcount 7) sorts before the untagged (NULL) one.
    assert sids[0] == "2"
    tagged = next(s for s in row["senses"] if s["synset_id"] == "2")
    assert tagged["tagcount"] == 7 and tagged["pos"] == "n"
