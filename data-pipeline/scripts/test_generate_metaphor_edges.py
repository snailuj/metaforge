"""Tests for generate_metaphor_edges — the continuous chain.v1 generation runner.

The runner turns vetted topics into grading-native chain.v1 JSONL (one
ChainRecord per topic→vehicle), with resume-by-topic, a topic/cost cap, a
proxy-judge live-rate tripwire, per-batch logging and periodic auto-commit.

All LLM access is injected (haiku_fn / sonnet_fn / judge_fn / resolve_synset)
so these tests make no API calls.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "grading_sidecar"))

import generate_metaphor_edges as mge
import metaphor_live_rate as mlr
from models import ChainRecord, compute_chain_signature


# --- fixtures ---------------------------------------------------------------
def _sonnet_resp(vehicle="volcano", mid="pressure"):
    """A Sonnet response whose chain[0] is deliberately NOT canonical, to prove
    the transform forces topic/vehicle endpoints."""
    return {"topic": "ignored", "vehicles": [
        {"vehicle": vehicle, "chain": [
            {"phrase": "NOT_TOPIC", "head": "emotion"},
            {"phrase": mid, "head": mid},
            {"phrase": vehicle, "head": "mountain"},
        ]},
    ]}


def _resolver(mapping):
    return lambda w: mapping.get(w)


# --- chain_records_from_sonnet (the canonicalising transform) --------------
def test_transform_produces_valid_chainrecord():
    recs = mge.chain_records_from_sonnet(
        topic="anger", topic_synset_id="1", gloss="strong emotion",
        sonnet_resp=_sonnet_resp(), proposer="sonnet_v1", round_num=2,
        generated_at="2026-06-04T00:00:00+00:00",
        resolve_synset=_resolver({"anger": "1", "volcano": "2", "pressure": "3"}),
    )
    assert len(recs) == 1
    r = recs[0]
    assert r["schema_version"] == "chain.v1"
    assert r["topic"] == "anger" and r["topic_synset_id"] == "1"
    assert r["vehicle"] == "volcano" and r["vehicle_synset_id"] == "2"
    assert r["round"] == 2 and r["proposer"] == "sonnet_v1"
    ChainRecord(**r)  # must validate (endpoint canonicalisation included)


def test_transform_forces_canonical_endpoints():
    recs = mge.chain_records_from_sonnet(
        topic="anger", topic_synset_id="1", gloss="g", sonnet_resp=_sonnet_resp(),
        proposer="sonnet_v1", round_num=2, generated_at="2026-06-04T00:00:00+00:00",
        resolve_synset=_resolver({"anger": "1", "volcano": "2", "pressure": "3"}),
    )
    r = recs[0]
    assert r["chain"][0] == {"phrase": "anger", "head": "anger", "synset_id": "1"}
    assert r["chain"][-1] == {"phrase": "volcano", "head": "volcano", "synset_id": "2"}


def test_transform_signature_matches_final_phrases():
    recs = mge.chain_records_from_sonnet(
        topic="anger", topic_synset_id="1", gloss="g", sonnet_resp=_sonnet_resp(mid="pressure"),
        proposer="sonnet_v1", round_num=2, generated_at="2026-06-04T00:00:00+00:00",
        resolve_synset=_resolver({"anger": "1", "volcano": "2", "pressure": "3"}),
    )
    assert recs[0]["chain_signature"] == compute_chain_signature(
        "sonnet_v1", ["anger", "pressure", "volcano"]
    )


def test_transform_skips_vehicle_without_resolvable_synset():
    recs = mge.chain_records_from_sonnet(
        topic="anger", topic_synset_id="1", gloss="g",
        sonnet_resp=_sonnet_resp(vehicle="xyzzy"), proposer="sonnet_v1", round_num=2,
        generated_at="2026-06-04T00:00:00+00:00",
        resolve_synset=_resolver({"anger": "1", "pressure": "3"}),  # xyzzy unresolved
    )
    assert recs == []


# --- resume / topic file / cost helpers ------------------------------------
def test_completed_topic_synset_ids(tmp_path):
    p = tmp_path / "out.jsonl"
    p.write_text('{"topic_synset_id":"1"}\n{"topic_synset_id":"2"}\n{"topic_synset_id":"1"}\n')
    assert mge.completed_topic_synset_ids(str(p)) == {"1", "2"}


def test_completed_topic_synset_ids_missing_file(tmp_path):
    assert mge.completed_topic_synset_ids(str(tmp_path / "nope.jsonl")) == set()


def test_load_vetted_topics(tmp_path):
    p = tmp_path / "t.json"
    p.write_text('{"topics":[{"word":"anger","topic_synset_id":"1","gloss":"g"}]}')
    ts = mge.load_vetted_topics(str(p))
    assert ts[0]["word"] == "anger" and ts[0]["topic_synset_id"] == "1"


def test_load_vetted_topics_rejects_missing_fields(tmp_path):
    p = tmp_path / "t.json"
    p.write_text('{"topics":[{"word":"anger"}]}')
    with pytest.raises(ValueError):
        mge.load_vetted_topics(str(p))


def test_estimate_cost_scales_linearly():
    one = mge.estimate_cost(1)
    assert mge.estimate_cost(100) == pytest.approx(one * 100)
    assert one == pytest.approx(mge.HAIKU_COST_PER_TOPIC + mge.SONNET_COST_PER_TOPIC)


# --- the run driver ---------------------------------------------------------
def _two_topics():
    return [
        {"word": "anger", "topic_synset_id": "1", "gloss": "g1"},
        {"word": "time", "topic_synset_id": "2", "gloss": "g2"},
    ]


def _haiku(word, gloss):
    return {"topic": word, "metaphors": [
        {"vehicle": "volcano", "shared_features": [{"concept": "pressure"}]}]}


def _resolve_all(w):
    return {"anger": "1", "time": "2", "volcano": "9", "pressure": "7"}.get(w)


def test_run_writes_valid_chainrecords(tmp_path):
    out = tmp_path / "chains.jsonl"
    seen_prompts = []

    def sonnet(prompt):
        seen_prompts.append(prompt)
        return _sonnet_resp()

    res = mge.run(
        topics=_two_topics(), output_jsonl=str(out), haiku_fn=_haiku, sonnet_fn=sonnet,
        resolve_synset=_resolve_all, proposer="sonnet_v1", round_num=2, batch_size=20,
        now_fn=lambda: "2026-06-04T00:00:00+00:00",
    )
    assert res["chains_written"] == 2
    assert res["topics_processed"] == 2
    # the real context-free-hop prompt was used
    assert any("in isolation" in p.lower() for p in seen_prompts)
    lines = [json.loads(l) for l in out.read_text().splitlines()]
    for l in lines:
        ChainRecord(**l)  # all grading-ingestible
    assert {l["topic_synset_id"] for l in lines} == {"1", "2"}


def test_run_resumes_and_skips_completed(tmp_path):
    out = tmp_path / "chains.jsonl"
    kw = dict(output_jsonl=str(out), haiku_fn=_haiku, sonnet_fn=lambda p: _sonnet_resp(),
              resolve_synset=_resolve_all, now_fn=lambda: "2026-06-04T00:00:00+00:00")
    mge.run(topics=_two_topics(), **kw)
    res2 = mge.run(topics=_two_topics(), **kw)  # same output -> nothing new
    assert res2["topics_processed"] == 0
    assert res2["chains_written"] == 0


def test_run_respects_max_topics(tmp_path):
    out = tmp_path / "chains.jsonl"
    res = mge.run(
        topics=_two_topics(), output_jsonl=str(out), haiku_fn=_haiku,
        sonnet_fn=lambda p: _sonnet_resp(), resolve_synset=_resolve_all,
        max_topics=1, now_fn=lambda: "2026-06-04T00:00:00+00:00",
    )
    assert res["topics_processed"] == 1


def test_run_pauses_when_tripwire_trips(tmp_path):
    out = tmp_path / "chains.jsonl"
    tw = mlr.new_tripwire(window=1, min_judged=1, abs_floor=0.5, rel_drop=0.9, baseline_n=1)
    res = mge.run(
        topics=_two_topics(), output_jsonl=str(out), haiku_fn=_haiku,
        sonnet_fn=lambda p: _sonnet_resp(), resolve_synset=_resolve_all,
        batch_size=1, tripwire=tw, judge_fn=lambda rec: {"verdict": "dead", "ok": True},
        judge_sample=1, now_fn=lambda: "2026-06-04T00:00:00+00:00",
    )
    assert res["paused"] is True
    # second topic was not processed after the pause
    assert res["topics_processed"] == 1


def test_run_skips_topic_on_generation_error_without_crashing(tmp_path):
    out = tmp_path / "chains.jsonl"

    def boom(prompt):
        raise RuntimeError("sonnet down")

    res = mge.run(
        topics=_two_topics(), output_jsonl=str(out), haiku_fn=_haiku, sonnet_fn=boom,
        resolve_synset=_resolve_all, now_fn=lambda: "2026-06-04T00:00:00+00:00",
    )
    assert res["chains_written"] == 0  # nothing written, but run completed
    # no completed topics recorded -> a later run retries them (idempotent)
    assert mge.completed_topic_synset_ids(str(out)) == set()


def test_run_autocommits_every_n_batches(tmp_path):
    out = tmp_path / "chains.jsonl"
    commits = []
    mge.run(
        topics=_two_topics(), output_jsonl=str(out), haiku_fn=_haiku,
        sonnet_fn=lambda p: _sonnet_resp(), resolve_synset=_resolve_all,
        batch_size=1, autocommit_every=1, commit_fn=lambda: commits.append(1),
        now_fn=lambda: "2026-06-04T00:00:00+00:00",
    )
    assert len(commits) == 2  # one per batch (2 topics, batch_size 1)
