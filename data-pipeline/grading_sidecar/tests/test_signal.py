"""Tests for grading_sidecar.signal — the coverage/breadth + path-geometry report.

Pure logic (no IO). Verdict resolution mirrors grading_io (latest-wins +
supersede) so the report matches the offline analysis. Geometry concordance is
optional — the report degrades cleanly when no geometry file is present.
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from grading_sidecar import signal_report as signal


def _v2(ts, sig, metaphor, *, topic="anxiety", tsid="72810", supersedes=None, tags=None):
    return {"schema_version": "judgement.v2", "ts": ts, "topic": topic,
            "topic_synset_id": tsid, "vehicle": "swarm", "vehicle_synset_id": "9",
            "chain_signature": sig, "linkage": "good", "metaphor": metaphor,
            "tiers": [], "tags": tags or [], "confidence": "high", "supersedes_ts": supersedes}


def test_resolve_verdicts_latest_wins_and_supersede():
    rows = [
        _v2("2026-06-01T10:00:00+00:00", "sigA", "dead"),
        _v2("2026-06-01T11:00:00+00:00", "sigA", "live"),                       # regrade same sig
        _v2("2026-06-01T12:00:00+00:00", "sigB", "live",
            supersedes="2026-06-01T09:00:00+00:00"),
        _v2("2026-06-01T09:00:00+00:00", "sigC", "dead"),                        # superseded by sigB
    ]
    resolved = signal.resolve_verdicts(rows)
    by_sig = {r["chain_signature"]: r for r in resolved}
    assert by_sig["sigA"]["metaphor"] == "live"   # latest regrade wins
    assert "sigC" not in by_sig                    # superseded ts dropped
    assert "sigB" in by_sig


def test_binary_label_drops_irrelevant():
    assert signal.binary_label({"metaphor": "live"}) == "live"
    assert signal.binary_label({"metaphor": "dead"}) == "dead"
    assert signal.binary_label({"metaphor": "irrelevant"}) is None
    assert signal.binary_label({"metaphor": None}) is None


def test_coverage_counts_topics_both_class_and_powered():
    rows = [
        {"sig": "s1", "tsid": "T1", "topic": "t1", "y": 1},
        {"sig": "s2", "tsid": "T1", "topic": "t1", "y": 0},   # T1: 1 live/1 dead -> 1 pair
        {"sig": "s3", "tsid": "T2", "topic": "t2", "y": 1},
        {"sig": "s4", "tsid": "T2", "topic": "t2", "y": 1},
        {"sig": "s5", "tsid": "T2", "topic": "t2", "y": 0},
        {"sig": "s6", "tsid": "T2", "topic": "t2", "y": 0},
        {"sig": "s7", "tsid": "T2", "topic": "t2", "y": 0},   # T2: 2 live/3 dead -> 6 pairs (powered)
        {"sig": "s8", "tsid": "T3", "topic": "t3", "y": 1},   # T3: 1 live/0 dead -> not both-class
    ]
    cov = signal.coverage(rows)
    assert cov["n"] == 8 and cov["n_live"] == 4 and cov["n_dead"] == 4
    assert cov["n_topics"] == 3
    assert cov["n_both_class_topics"] == 2     # T1, T2 (not T3)
    assert cov["n_powered_topics"] == 1        # only T2 has >=5 within-topic pairs
    assert cov["per_topic"][0]["topic_synset_id"] == "T2"   # sorted by pairs desc


def test_within_topic_concordance_pools_pairs():
    rows = [
        {"sig": "a", "tsid": "T", "topic": "t", "y": 1},
        {"sig": "b", "tsid": "T", "topic": "t", "y": 0},
    ]
    geo = {"a": {"max_hop_cos": 0.9}, "b": {"max_hop_cos": 0.3}}
    auc, n_pairs = signal.within_topic_concordance(rows, geo, "max_hop_cos")
    assert auc == 1.0 and n_pairs == 1     # live > dead on the single pair


def test_within_topic_concordance_none_when_no_geometry():
    rows = [{"sig": "a", "tsid": "T", "topic": "t", "y": 1},
            {"sig": "b", "tsid": "T", "topic": "t", "y": 0}]
    auc, n_pairs = signal.within_topic_concordance(rows, {}, "max_hop_cos")
    assert auc is None and n_pairs == 0


def test_build_report_without_geometry():
    judgements = [
        _v2("2026-06-01T10:00:00+00:00", "s1", "live"),
        _v2("2026-06-01T10:01:00+00:00", "s2", "dead"),
        _v2("2026-06-01T10:02:00+00:00", "s3", "irrelevant"),   # excluded
    ]
    rep = signal.build_signal_report(judgements, {}, server_ts="2026-06-08T00:00:00Z")
    assert rep["n"] == 2 and rep["n_live"] == 1 and rep["n_dead"] == 1
    assert rep["geometry_available"] is False
    assert rep["geometry_features"] == []


def test_build_report_with_geometry():
    judgements = [
        _v2("2026-06-01T10:00:00+00:00", "s1", "live"),
        _v2("2026-06-01T10:01:00+00:00", "s2", "dead"),
    ]
    geo = {"s1": {"max_hop_cos": 0.8, "std_hop_cos": 0.2},
           "s2": {"max_hop_cos": 0.3, "std_hop_cos": 0.1}}
    rep = signal.build_signal_report(judgements, geo, server_ts="2026-06-08T00:00:00Z")
    assert rep["geometry_available"] is True
    by_name = {f["name"]: f for f in rep["geometry_features"]}
    assert by_name["max_hop_cos"]["within_topic_auc"] == 1.0
    assert by_name["max_hop_cos"]["n_pairs"] == 1


def test_signal_report_excludes_bad_head_from_liveness():
    # A mis-extracted vehicle (bad_head) makes the judged pairing a phantom, so its
    # liveness label is unreliable -> dropped from the liveness rows + counted.
    judgements = [
        _v2("2026-06-01T10:00:00+00:00", "s1", "live"),
        _v2("2026-06-01T10:01:00+00:00", "s2", "dead"),
        _v2("2026-06-01T10:02:00+00:00", "s3", "live", tags=["bad_head"]),
    ]
    rep = signal.build_signal_report(judgements, {}, server_ts="2026-06-08T00:00:00Z")
    assert rep["n"] == 2                     # bad_head row excluded from liveness
    assert rep["n_excluded_bad_head"] == 1


def test_signal_report_keeps_leap_padding_in_liveness():
    # leap/padding are bad LINKAGE but the vehicle is right -> liveness label valid.
    judgements = [
        _v2("2026-06-01T10:00:00+00:00", "s1", "live", tags=["leap"]),
        _v2("2026-06-01T10:01:00+00:00", "s2", "dead", tags=["padding"]),
    ]
    rep = signal.build_signal_report(judgements, {}, server_ts="2026-06-08T00:00:00Z")
    assert rep["n"] == 2
    assert rep["n_excluded_bad_head"] == 0


def test_signal_report_linkage_counts_use_effective_rule():
    # Linkage axis is orthogonal to liveness: a forcing tag counts as bad linkage
    # even when (bad_head) it is also dropped from the liveness rows.
    judgements = [
        _v2("2026-06-01T10:00:00+00:00", "s1", "live"),                  # good
        _v2("2026-06-01T10:01:00+00:00", "s2", "dead", tags=["leap"]),   # forced bad
        _v2("2026-06-01T10:02:00+00:00", "s3", "live", tags=["padding"]),  # stays good
        _v2("2026-06-01T10:03:00+00:00", "s4", "live", tags=["bad_head"]),  # bad linkage AND excluded from liveness
    ]
    rep = signal.build_signal_report(judgements, {}, server_ts="2026-06-08T00:00:00Z")
    assert rep["n_linkage_bad"] == 2     # s2 (leap), s4 (bad_head)
    assert rep["n_linkage_good"] == 2    # s1, s3 (padding)
    assert rep["n_excluded_bad_head"] == 1
