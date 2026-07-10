"""Tests for migrate_chain_v2 — per-hop noun-prior snapper + chain.v2 migration.

Follows the style of test_resnap_glossed_corpus.py: pure functions injected with
stub snap_fns so no model or FastText vector calls are needed.
"""
import json
import sqlite3
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "grading_sidecar"))

from models import compute_chain_signature, vec_ref
import migrate_chain_v2 as mcv2


# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------

def _sig(proposer, phrases):
    return compute_chain_signature(proposer, phrases)


def _v1_record():
    """3-step chain.v1 record: grief -> pain -> scar."""
    phrases = ["grief", "pain", "scar"]
    return {
        "schema_version": "chain.v1", "topic": "grief", "topic_synset_id": "1",
        "vehicle": "scar", "vehicle_synset_id": "3", "proposer": "sonnet_v1",
        "round": 1, "generated_at": "2026-07-10T00:00:00+00:00",
        "chain_signature": _sig("sonnet_v1", phrases),
        "chain": [
            {"phrase": "grief", "head": "grief", "synset_id": "1"},
            {"phrase": "pain", "head": "pain", "synset_id": "2"},
            {"phrase": "scar", "head": "scar", "synset_id": "3"},
        ],
    }


def _db() -> sqlite3.Connection:
    """In-memory fixture DB matching the test_sense_inventory shape."""
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, pos TEXT, definition TEXT);
        CREATE TABLE lemmas (lemma TEXT, synset_id TEXT);
        CREATE TABLE sense_attributes (lemma TEXT, synset_id TEXT,
                                       sensenum INTEGER, tagcount INTEGER);
    """)
    rows = [
        ("100", "n", "a brief look"), ("101", "v", "look quickly"),
        ("102", "n", "a deflection"), ("200", "n", "an open sore"),
    ]
    conn.executemany("INSERT INTO synsets VALUES (?,?,?)", rows)
    conn.executemany("INSERT INTO lemmas VALUES (?,?)",
                     [("glance", "100"), ("glance", "101"), ("glance", "102"),
                      ("wound", "200")])
    conn.executemany("INSERT INTO sense_attributes VALUES (?,?,?,?)",
                     [("glance", "100", 1, 9), ("glance", "101", 2, 4),
                      ("glance", "102", 3, 0), ("wound", "200", 1, 2)])
    return conn


def _dump_fixture_to(path: Path) -> None:
    """Persist the fixture to a file-backed SQLite DB (for file-level tests)."""
    conn = sqlite3.connect(str(path))
    conn.executescript("""
        CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, pos TEXT, definition TEXT);
        CREATE TABLE lemmas (lemma TEXT, synset_id TEXT);
        CREATE TABLE sense_attributes (lemma TEXT, synset_id TEXT,
                                       sensenum INTEGER, tagcount INTEGER);
    """)
    rows = [
        ("100", "n", "a brief look"), ("101", "v", "look quickly"),
        ("102", "n", "a deflection"), ("200", "n", "an open sore"),
    ]
    conn.executemany("INSERT INTO synsets VALUES (?,?,?)", rows)
    conn.executemany("INSERT INTO lemmas VALUES (?,?)",
                     [("glance", "100"), ("glance", "101"), ("glance", "102"),
                      ("wound", "200")])
    conn.executemany("INSERT INTO sense_attributes VALUES (?,?,?,?)",
                     [("glance", "100", 1, 9), ("glance", "101", 2, 4),
                      ("glance", "102", 3, 0), ("wound", "200", 1, 2)])
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# (a) migrate_record — v1 fixture, stub snap_fn, interior sense updated
# ---------------------------------------------------------------------------

def _identity_snap(phrase, head, gloss):
    """Stub: returns the pre-existing synset for topic/vehicle; changed for interior."""
    mapping = {
        "grief": ("1", "syn:1", "ok"),
        "pain":  ("2new", "syn:2new", "ok"),  # interior sense changed
        "scar":  ("3", "syn:3", "ok"),
    }
    sid, node_ref, conf = mapping[phrase]
    return {"synset_id": sid, "node_ref": node_ref, "confidence": conf}


def test_migrate_record_v1_to_v2_updates_interior_and_sets_apt_senses():
    rec = _v1_record()
    out = mcv2.migrate_record(rec, _identity_snap)

    assert out["schema_version"] == "chain.v2"
    # Interior step updated
    assert out["chain"][1]["synset_id"] == "2new"
    assert out["chain"][1]["node_ref"] == "syn:2new"
    assert out["chain"][1]["apt_senses"] == [{"synset_id": "2new", "source": "intended"}]
    # Endpoints unchanged (same synset)
    assert out["chain"][0]["synset_id"] == "1"
    assert out["chain"][-1]["synset_id"] == "3"
    # Endpoint fields mirror step values
    assert out["topic_synset_id"] == "1"
    assert out["topic_node_ref"] == "syn:1"
    assert out["vehicle_synset_id"] == "3"
    assert out["vehicle_node_ref"] == "syn:3"
    # chain_signature preserved (phrase-based, never changes)
    assert out["chain_signature"] == rec["chain_signature"]
    # All other fields byte-identical (unchanged)
    assert out["topic"] == rec["topic"]
    assert out["vehicle"] == rec["vehicle"]
    assert out["proposer"] == rec["proposer"]
    assert out["round"] == rec["round"]
    assert out["generated_at"] == rec["generated_at"]


def test_migrate_record_does_not_mutate_input():
    rec = _v1_record()
    mcv2.migrate_record(rec, _identity_snap)
    assert rec["schema_version"] == "chain.v1"
    assert "apt_senses" not in rec["chain"][1]


# ---------------------------------------------------------------------------
# (b) already-v2 record returned unchanged (idempotency)
# ---------------------------------------------------------------------------

def test_migrate_record_v2_is_idempotent():
    rec = _v1_record()
    v2 = mcv2.migrate_record(rec, _identity_snap)
    # Second call: v2 record returned byte-identical
    v2_again = mcv2.migrate_record(v2, _identity_snap)
    assert v2_again == v2


# ---------------------------------------------------------------------------
# (c) noun_prior_snap — fixture DB, empty vectors (embed yields None)
# ---------------------------------------------------------------------------

def test_noun_prior_snap_verb_gloss_wins_over_noun_prior():
    """Gloss "look quickly" matches the verb sense (101); decisive gloss evidence wins.
    When snap_by_gloss_embed yields None (empty vectors), snap_by_gloss picks up 101.
    """
    conn = _db()
    result = mcv2.noun_prior_snap(conn, {}, "glance", "glance", "look quickly")
    # snap_by_gloss("glance", "look quickly") → "101" (verb, score 2 vs noun score 1)
    # gloss evidence is decisive — the noun prior does NOT override it
    assert result["synset_id"] == "101"
    assert result["node_ref"] == "syn:101"
    assert result["confidence"] == "ok"


def test_noun_prior_snap_no_gloss_known_noun_gives_low_confidence():
    """No gloss → skip snap → noun prior → top-noun with confidence='low'."""
    conn = _db()
    result = mcv2.noun_prior_snap(conn, {}, "glance", "glance", None)
    # noun_inventory returns ["100","102"]; top is "100" (tagcount=9)
    assert result["synset_id"] == "100"
    assert result["node_ref"] == "syn:100"
    assert result["confidence"] == "low"


def test_noun_prior_snap_unknown_phrase_and_head_gives_vec():
    """Neither phrase nor head has any noun sense → vec: admission."""
    conn = _db()
    result = mcv2.noun_prior_snap(conn, {}, "pressed flower", "flower", None)
    assert result["synset_id"] is None
    assert result["node_ref"] == "vec:pressed_flower"
    assert result["confidence"] == "vec"


def test_noun_prior_snap_unknown_with_non_matching_gloss_also_gives_vec():
    """Gloss exists but no snap match + no noun senses → vec:."""
    conn = _db()
    # "pressed flower" / "flower" → not in DB → snap_by_gloss returns None
    # → vec_gate True → vec:
    result = mcv2.noun_prior_snap(conn, {}, "pressed flower", "flower",
                                  "a dried plant keepsake")
    assert result["confidence"] == "vec"
    assert result["node_ref"] == "vec:pressed_flower"


# ---------------------------------------------------------------------------
# (d) signature-mismatch guard raises RuntimeError
# ---------------------------------------------------------------------------

def test_migrate_record_raises_on_chain_signature_mismatch():
    """If chain_signature doesn't match the record's phrases, raise RuntimeError."""
    rec = _v1_record()
    # Tamper the signature so it no longer matches the actual phrases
    rec["chain_signature"] = "b" * 64
    with pytest.raises(RuntimeError, match="chain_signature mismatch"):
        mcv2.migrate_record(rec, _identity_snap)


# ---------------------------------------------------------------------------
# (e) migrate_file — writes _v2 file, second run skips without --force
# ---------------------------------------------------------------------------

def _stub_snap_returning_same(phrase, head, gloss):
    """Minimal stub: always returns the first known noun sense or a vec node."""
    # For the v1 fixture: grief=1, pain=2, scar=3
    mapping = {"grief": "1", "pain": "2", "scar": "3"}
    if phrase in mapping:
        sid = mapping[phrase]
        return {"synset_id": sid, "node_ref": f"syn:{sid}", "confidence": "ok"}
    return {"synset_id": None, "node_ref": f"vec:{vec_ref(phrase)}", "confidence": "vec"}


def test_migrate_file_writes_output_and_skips_on_second_run(tmp_path):
    inp = tmp_path / "chains.jsonl"
    out = tmp_path / "chains_v2.jsonl"
    inp.write_text(json.dumps(_v1_record()) + "\n")

    # First run: creates the output
    summary1 = mcv2.migrate_file(str(inp), str(out), _stub_snap_returning_same)
    assert out.exists()
    assert summary1["records"] == 1
    assert not summary1.get("skipped")

    mtime_after_first = out.stat().st_mtime

    # Small sleep to ensure mtime would differ if file were rewritten
    time.sleep(0.05)

    # Second run without force: skips
    summary2 = mcv2.migrate_file(str(inp), str(out), _stub_snap_returning_same)
    assert summary2.get("skipped") is True
    assert summary2["records"] == 0
    assert out.stat().st_mtime == mtime_after_first  # file not touched


def test_migrate_file_force_rewrites_output(tmp_path):
    inp = tmp_path / "chains.jsonl"
    out = tmp_path / "chains_v2.jsonl"
    inp.write_text(json.dumps(_v1_record()) + "\n")

    mcv2.migrate_file(str(inp), str(out), _stub_snap_returning_same)
    mtime1 = out.stat().st_mtime
    time.sleep(0.05)

    summary = mcv2.migrate_file(str(inp), str(out), _stub_snap_returning_same,
                                 force=True)
    assert not summary.get("skipped")
    assert summary["records"] == 1
    assert out.stat().st_mtime > mtime1  # file was rewritten


def test_migrate_file_output_is_valid_v2_records(tmp_path):
    """Every output record must validate as chain.v2 via ChainRecord."""
    from models import ChainRecord
    inp = tmp_path / "chains.jsonl"
    out = tmp_path / "chains_v2.jsonl"
    inp.write_text(json.dumps(_v1_record()) + "\n")
    mcv2.migrate_file(str(inp), str(out), _stub_snap_returning_same)
    for line in out.read_text().splitlines():
        rec = json.loads(line)
        assert rec["schema_version"] == "chain.v2"
        ChainRecord(**rec)  # must not raise


def test_migrate_file_summary_counts_steps(tmp_path):
    """Summary counts resnapped_steps and confidence categories."""
    # Use a snap that always returns low-confidence for interior steps
    def low_snap(phrase, head, gloss):
        mapping = {"grief": ("1", "ok"), "pain": ("2", "low"), "scar": ("3", "ok")}
        sid, conf = mapping[phrase]
        return {"synset_id": sid, "node_ref": f"syn:{sid}", "confidence": conf}

    inp = tmp_path / "c.jsonl"
    out = tmp_path / "c_v2.jsonl"
    inp.write_text(json.dumps(_v1_record()) + "\n")
    summary = mcv2.migrate_file(str(inp), str(out), low_snap)
    assert summary["records"] == 1
    assert summary["low_confidence"] == 1
    assert summary["vec_admissions"] == 0
