"""Tests for judge_corpus — gold-corpus data prep for the judge agreement harness.

Fixture-based and fully offline. The load-bearing properties:

  * verdict semantics are REUSED from grading_sidecar (supersede + latest-wins,
    v1 label → v2 axes, tag-implies-bad-linkage) — asserted by feeding mixed
    v1/v2 records through load_resolved and reading the stamped
    `linkage_effective`;
  * liveness_rows keeps bad_head rows and never gates on linkage (the two judge
    axes are orthogonal — a Stage-1 verdict must not shape the Stage-2 corpus);
  * attach_chain_context flags a missing chain (chain_missing=True + warning)
    rather than silently dropping the row.

Plus one integration guard against the live grading-live corpus (skipped when
that worktree is absent).
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import judge_corpus as jc

LIVE_VERDICTS = Path(
    "/home/agent/projects/metaforge/.worktrees/next/data-pipeline/grading/judgements_provisional.jsonl"
)


def _v2(ts, sig, metaphor, *, topic="anxiety", tsid="72810", vehicle="swarm",
        vsid="75829", linkage="good", tags=None, notes="", supersedes=None):
    return {"schema_version": "judgement.v2", "ts": ts, "judged_by": "julian",
            "round": 1, "topic": topic, "topic_synset_id": tsid,
            "vehicle": vehicle, "vehicle_synset_id": vsid, "proposer": "sonnet_v1",
            "chain_signature": sig, "linkage": linkage, "metaphor": metaphor,
            "tiers": [], "tags": tags or [], "confidence": "high",
            "notes": notes, "supersedes_ts": supersedes}


def _v1(ts, sig, label, *, topic="anger", tsid="30227", vehicle="volcano",
        vsid="79695", supersedes=None):
    return {"schema_version": "judgement.v1", "ts": ts, "judged_by": "julian",
            "round": 1, "topic": topic, "topic_synset_id": tsid,
            "vehicle": vehicle, "vehicle_synset_id": vsid, "proposer": "sonnet_v1",
            "chain_signature": sig, "label": label, "confidence": "high",
            "notes": "", "supersedes_ts": supersedes}


def _write_jsonl(path: Path, records: list, *, raw_lines: list[str] | None = None):
    lines = [json.dumps(r) for r in records] + (raw_lines or [])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _chain(sig, *, topic="anxiety", tsid="72810", vehicle="swarm", vsid="75829",
           middle=("pressure", "60988")):
    steps = [{"phrase": topic, "head": topic, "synset_id": tsid},
             {"phrase": middle[0], "head": middle[0], "synset_id": middle[1]},
             {"phrase": vehicle, "head": vehicle, "synset_id": vsid}]
    return {"schema_version": "chain.v1", "topic": topic, "topic_synset_id": tsid,
            "vehicle": vehicle, "vehicle_synset_id": vsid, "proposer": "sonnet_v1",
            "round": 1, "chain": steps, "chain_signature": sig,
            "generated_at": "2026-05-30T00:00:00Z"}


# --- load_resolved ---

def test_load_resolved_skips_malformed_and_keeps_valid(tmp_path):
    path = _write_jsonl(tmp_path / "j.jsonl",
                        [_v2("2026-06-01T10:00:00+00:00", "a", "live"),
                         _v1("2026-06-01T11:00:00+00:00", "b", "dead")],
                        raw_lines=["{not json"])
    rows = jc.load_resolved(path)
    assert {r["chain_signature"] for r in rows} == {"a", "b"}


def test_load_resolved_missing_file_escalates(tmp_path):
    with pytest.raises(FileNotFoundError):
        jc.load_resolved(tmp_path / "absent.jsonl")


def test_load_resolved_supersede_and_latest_wins(tmp_path):
    path = _write_jsonl(tmp_path / "j.jsonl", [
        _v2("2026-06-01T09:00:00+00:00", "a", "dead"),
        _v2("2026-06-01T10:00:00+00:00", "a", "live"),       # latest wins per sig
        _v2("2026-06-01T08:00:00+00:00", "b", "live"),       # named by c's marker
        _v2("2026-06-01T10:30:00+00:00", "c", "dead",
            supersedes="2026-06-01T08:00:00+00:00"),
    ])
    rows = {r["chain_signature"]: r for r in jc.load_resolved(path)}
    assert rows["a"]["metaphor"] == "live"
    assert "b" not in rows


def test_load_resolved_stamps_linkage_effective(tmp_path):
    path = _write_jsonl(tmp_path / "j.jsonl", [
        _v2("2026-06-01T10:00:00+00:00", "good", "live", linkage="good"),
        _v2("2026-06-01T10:01:00+00:00", "tapped", "dead", linkage="bad"),
        # tag-implies-bad-linkage: grader skipped the tap but tagged leap
        _v2("2026-06-01T10:02:00+00:00", "forced", "dead", linkage="good", tags=["leap"]),
        # padding is NOT a forcing tag — a padded path can still bridge cleanly
        _v2("2026-06-01T10:03:00+00:00", "padded", "live", linkage="good", tags=["padding"]),
    ])
    rows = {r["chain_signature"]: r["linkage_effective"] for r in jc.load_resolved(path)}
    assert rows == {"good": "good", "tapped": "bad", "forced": "bad", "padded": "good"}


def test_load_resolved_maps_v1_labels_to_axes(tmp_path):
    path = _write_jsonl(tmp_path / "j.jsonl", [
        _v1("2026-06-01T10:00:00+00:00", "v1live", "live"),
        _v1("2026-06-01T10:01:00+00:00", "v1bp", "bad_path"),
        _v1("2026-06-01T10:02:00+00:00", "v1irr", "irrelevant"),
    ])
    rows = {r["chain_signature"]: r for r in jc.load_resolved(path)}
    assert rows["v1live"]["metaphor"] == "live"
    assert rows["v1live"]["linkage_effective"] == "good"
    assert rows["v1bp"]["metaphor"] is None
    assert rows["v1bp"]["linkage_effective"] == "bad"
    assert rows["v1irr"]["linkage_effective"] is None     # linkage moot for irrelevant


# --- construction_rows ---

def _resolved(records, tmp_path):
    return jc.load_resolved(_write_jsonl(tmp_path / "j.jsonl", records))


def test_construction_rows_labels_and_drops_irrelevant(tmp_path):
    rows = jc.construction_rows(_resolved([
        _v2("2026-06-01T10:00:00+00:00", "g", "live", linkage="good"),
        _v2("2026-06-01T10:01:00+00:00", "b", "dead", linkage="bad"),
        _v2("2026-06-01T10:02:00+00:00", "f", "dead", linkage="good", tags=["bad_head"]),
        _v1("2026-06-01T10:03:00+00:00", "bp", "bad_path"),
        _v1("2026-06-01T10:04:00+00:00", "irr", "irrelevant"),  # no linkage signal
    ], tmp_path))
    by_sig = {r["chain_signature"]: r["y_link"] for r in rows}
    assert by_sig == {"g": 0, "b": 1, "f": 1, "bp": 1}
    assert "irr" not in by_sig


# --- liveness_rows ---

def test_liveness_rows_keeps_live_dead_only(tmp_path):
    rows = jc.liveness_rows(_resolved([
        _v2("2026-06-01T10:00:00+00:00", "L", "live"),
        _v2("2026-06-01T10:01:00+00:00", "D", "dead"),
        _v2("2026-06-01T10:02:00+00:00", "I", "irrelevant"),
        _v1("2026-06-01T10:03:00+00:00", "bp", "bad_path"),   # metaphor unknown
    ], tmp_path))
    by_sig = {r["chain_signature"]: r["y_live"] for r in rows}
    assert by_sig == {"L": 1, "D": 0}


def test_liveness_rows_keeps_bad_head_and_bad_linkage(tmp_path):
    # Orthogonality is load-bearing: bad_head endpoints are canonicalised so the
    # pairing stays valid, and a Stage-1 (linkage) verdict must not gate Stage 2.
    rows = jc.liveness_rows(_resolved([
        _v2("2026-06-01T10:00:00+00:00", "bh", "live", tags=["bad_head"]),
        _v2("2026-06-01T10:01:00+00:00", "bl", "dead", linkage="bad"),
    ], tmp_path))
    by_sig = {r["chain_signature"]: r["y_live"] for r in rows}
    assert by_sig == {"bh": 1, "bl": 0}


# --- attach_chain_context ---

def test_attach_chain_context_joins_chain_and_glosses(tmp_path):
    rows = jc.liveness_rows(_resolved(
        [_v2("2026-06-01T10:00:00+00:00", "a", "live")], tmp_path))
    glosses = {"72810": {"pos": "n", "definition": "a vague unpleasant emotion"},
               "75829": {"pos": "n", "definition": "a moving crowd"}}
    out = jc.attach_chain_context(rows, [_chain("a")], glosses)
    assert out[0]["chain_missing"] is False
    assert [s["phrase"] for s in out[0]["chain"]] == ["anxiety", "pressure", "swarm"]
    assert set(out[0]["chain"][0]) == {"phrase", "head", "synset_id"}
    assert out[0]["topic_gloss"]["definition"] == "a vague unpleasant emotion"
    assert out[0]["vehicle_gloss"]["pos"] == "n"
    assert out[0]["y_live"] == 1                      # corpus keys ride through


def test_attach_chain_context_flags_missing_chain(tmp_path, caplog):
    rows = jc.liveness_rows(_resolved(
        [_v2("2026-06-01T10:00:00+00:00", "orphan", "live")], tmp_path))
    with caplog.at_level(logging.WARNING):
        out = jc.attach_chain_context(rows, [_chain("other")], {})
    assert len(out) == 1                              # flagged, never dropped
    assert out[0]["chain_missing"] is True
    assert out[0]["chain"] == []
    assert "orphan" in caplog.text


def test_attach_chain_context_missing_gloss_is_none(tmp_path):
    rows = jc.liveness_rows(_resolved(
        [_v2("2026-06-01T10:00:00+00:00", "a", "live")], tmp_path))
    out = jc.attach_chain_context(rows, [_chain("a")], {})
    assert out[0]["topic_gloss"] is None
    assert out[0]["vehicle_gloss"] is None


def test_attach_chain_context_does_not_mutate_input(tmp_path):
    rows = jc.liveness_rows(_resolved(
        [_v2("2026-06-01T10:00:00+00:00", "a", "live")], tmp_path))
    before = dict(rows[0])
    jc.attach_chain_context(rows, [_chain("a")], {})
    assert rows[0] == before


def test_attach_chain_context_accepts_directory_and_gloss_path(tmp_path):
    # Round files: r2 re-emits signature "a" with a different middle step —
    # last file wins, mirroring chain_store's union semantics.
    _write_jsonl(tmp_path / "sonnet_chains_provisional_r1.jsonl",
                 [_chain("a"), _chain("b", vehicle="kettle", vsid="52164")])
    _write_jsonl(tmp_path / "sonnet_chains_provisional_r2.jsonl",
                 [_chain("a", middle=("steam", "61000"))])
    gloss_path = _write_jsonl(tmp_path / "chain_glosses_provisional.jsonl",
                              [{"synset_id": "72810", "pos": "n",
                                "definition": "a vague unpleasant emotion"}])
    rows = jc.liveness_rows(_resolved(
        [_v2("2026-06-01T10:00:00+00:00", "a", "live")], tmp_path))
    out = jc.attach_chain_context(rows, tmp_path, gloss_path)
    assert [s["phrase"] for s in out[0]["chain"]] == ["anxiety", "steam", "swarm"]
    assert out[0]["topic_gloss"] == {"pos": "n", "definition": "a vague unpleasant emotion"}
    assert out[0]["vehicle_gloss"] is None


def test_load_chains_drops_schema_drift_records():
    chains = jc.load_chains([_chain("ok"), {"chain_signature": "x", "topic": "t"}])
    assert [c["chain_signature"] for c in chains] == ["ok"]


def test_load_glosses_missing_file_degrades_to_empty(tmp_path, caplog):
    with caplog.at_level(logging.WARNING):
        glosses = jc.load_glosses(tmp_path / "absent.jsonl")
    assert glosses == {}
    assert "gloss" in caplog.text.lower()


# --- sense-suspect quarantine (operator finding 2026-07-03: two gold rows were
# graded under a different sense assumption than the recorded synset — the
# verdict is about another pairing entirely; quarantined pending re-grade) ----

SUSPECTS_FILE = Path(__file__).resolve().parent.parent / "grading" / "gold_sense_suspect.jsonl"


def test_drop_sense_suspect_drops_only_matching_signatures(caplog):
    rows = [{"chain_signature": "keep-me", "topic": "a", "vehicle": "b"},
            {"chain_signature": "drop-me", "topic": "c", "vehicle": "d"}]
    with caplog.at_level(logging.WARNING):
        kept = jc.drop_sense_suspect(rows, [{"chain_signature": "drop-me",
                                             "reason": "sense mismatch"}])
    assert [r["chain_signature"] for r in kept] == ["keep-me"]
    assert "drop-me" in caplog.text  # a quarantined gold row is never silent


def test_drop_sense_suspect_accepts_a_jsonl_path(tmp_path):
    suspects = tmp_path / "suspects.jsonl"
    suspects.write_text(json.dumps({"chain_signature": "drop-me", "reason": "r"}) + "\n")
    rows = [{"chain_signature": "keep-me"}, {"chain_signature": "drop-me"}]
    kept = jc.drop_sense_suspect(rows, suspects)
    assert [r["chain_signature"] for r in kept] == ["keep-me"]


def test_drop_sense_suspect_missing_file_escalates(tmp_path):
    # Like the gold file: a silently-absent quarantine list would score
    # known-corrupt rows as gold.
    with pytest.raises(FileNotFoundError):
        jc.drop_sense_suspect([], tmp_path / "absent.jsonl")


def test_committed_suspects_carry_the_fault_and_heliotrope_rows():
    recs = [json.loads(l) for l in SUSPECTS_FILE.read_text().splitlines() if l.strip()]
    sigs = {r["chain_signature"] for r in recs}
    assert "e19b265b5b22bb6a92f6e2951c5ae1cc0651113bc6fa4a2da96568c0e83f5000" in sigs  # ambush->fault (sports sense)
    assert "0ee96dd420bcebd7ae6a5379fce3d841eaf2b9719e4e2dcfcd654a9aca04ff05" in sigs  # longing->heliotrope (mineral sense)
    assert all(r.get("reason") for r in recs)  # every quarantine states its why


# --- integration guard against the live grading-live corpus ---

def test_live_corpus_counts():
    if not LIVE_VERDICTS.exists():
        pytest.skip("grading-live worktree not present")
    resolved = jc.load_resolved(LIVE_VERDICTS)
    assert len(resolved) >= 125
    assert len(jc.liveness_rows(resolved)) >= 115
    construction = jc.construction_rows(resolved)
    assert sum(r["y_link"] == 1 for r in construction) >= 45
    assert len({r["topic_synset_id"] for r in resolved}) >= 28
