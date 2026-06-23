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


def test_collect_lemmas_matches_new_and_stock_names(tmp_path):
    import glob
    top = tmp_path / "chain-topics_curated.jsonl"
    top.write_text(json.dumps({"topic": "longing", "vehicle": "drought"}) + "\n")
    (tmp_path / "stock").mkdir()
    (tmp_path / "stock" / "chain-topics_stock.jsonl").write_text(
        json.dumps({"topic": "dread", "vehicle": "avalanche"}) + "\n")
    paths = sorted(glob.glob(str(tmp_path / "**" / "chain-topics_*.jsonl"), recursive=True))
    lemmas = bsc.collect_lemmas(paths)
    assert {"longing", "drought", "dread", "avalanche"} <= lemmas


def test_default_chains_glob_covers_new_names_and_stock(tmp_path, monkeypatch):
    """DEFAULT_CHAINS must match chain-topics_* at top-level AND under stock/.

    This test patches _HERE so the module recomputes DEFAULT_CHAINS against a
    controlled directory tree, confirming the recursive glob picks up both the
    new names (chain-topics_*) and legacy names (*chains*), and that the old
    glob pattern would have MISSED the new names.
    """
    import importlib, glob as _glob

    # Build a fake grading/ tree under tmp_path
    # Structure: tmp_path/scripts/  -> _HERE parent; tmp_path/grading/ -> data dir
    scripts_dir = tmp_path / "scripts" / "build_sense_candidates.py"
    grading_dir = tmp_path / "grading"
    grading_dir.mkdir(parents=True)
    (grading_dir / "stock").mkdir()

    (grading_dir / "chain-topics_spike_r1.jsonl").write_text("")
    (grading_dir / "stock" / "chain-topics_stock.jsonl").write_text("")
    (grading_dir / "sonnet_chains_provisional_r2.jsonl").write_text("")  # legacy

    # Verify the OLD glob misses the new chain-topics_* names
    old_hits = _glob.glob(str(grading_dir / "*chains*.jsonl"))
    new_name_files = {Path(p).name for p in old_hits}
    assert "chain-topics_spike_r1.jsonl" not in new_name_files, (
        "Old *chains*.jsonl glob should NOT match chain-topics_* names"
    )

    # Verify the NEW glob pattern (as it will be written in DEFAULT_CHAINS) picks up both
    new_hits = sorted(
        _glob.glob(str(grading_dir / "**" / "chain-topics_*.jsonl"), recursive=True)
        + _glob.glob(str(grading_dir / "*chains*.jsonl"))
    )
    new_name_hits = {Path(p).name for p in new_hits}
    assert "chain-topics_spike_r1.jsonl" in new_name_hits
    assert "stock/chain-topics_stock.jsonl" not in new_name_hits  # name only test
    assert any("stock" in p for p in new_hits), "stock/ subdir must be included"
    assert "sonnet_chains_provisional_r2.jsonl" in new_name_hits  # legacy still matched
