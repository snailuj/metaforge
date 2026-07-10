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


def _gloss_resolver(mapping):
    """resolve_by_gloss double, keyed on (lemma, emitted_gloss) so a test proves
    the emitted gloss is threaded through — not just the lemma."""
    return lambda lemma, g: mapping.get((lemma, g))


def _sonnet_resp_with_glosses(vehicle="volcano", mid="pressure"):
    return {"topic": "ignored", "vehicles": [
        {"vehicle": vehicle, "chain": [
            {"phrase": "anger", "head": "anger", "gloss": "GT"},
            {"phrase": mid, "head": mid, "gloss": "GP"},
            {"phrase": vehicle, "head": vehicle, "gloss": "GV"},
        ]},
    ]}


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
    # endpoints now carry a uniform gloss key: topic from the curated gloss param,
    # vehicle from its emitted gloss (None here — _sonnet_resp emits no glosses).
    assert r["chain"][0] == {"phrase": "anger", "head": "anger", "synset_id": "1", "gloss": "g"}
    assert r["chain"][-1] == {"phrase": "volcano", "head": "volcano", "synset_id": "2", "gloss": None}


def test_transform_uses_emitted_gloss_to_snap():
    # emit-the-sense: the gloss-aware resolver wins over the legacy resolver, and
    # the emitted gloss is recorded on each step.
    recs = mge.chain_records_from_sonnet(
        topic="anger", topic_synset_id="1", gloss="a strong feeling of displeasure",
        sonnet_resp=_sonnet_resp_with_glosses(), proposer="sonnet_v1", round_num=2,
        generated_at="2026-06-04T00:00:00+00:00",
        resolve_synset=_resolver({"anger": "1", "volcano": "2", "pressure": "3"}),
        resolve_by_gloss=_gloss_resolver({("volcano", "GV"): "2g", ("pressure", "GP"): "3g"}),
    )
    r = recs[0]
    assert r["vehicle_synset_id"] == "2g"                 # gloss-match beat resolver "2"
    assert r["chain"][-1]["gloss"] == "GV"
    assert r["chain"][1]["synset_id"] == "3g" and r["chain"][1]["gloss"] == "GP"
    assert r["chain"][0]["gloss"] == "a strong feeling of displeasure"
    ChainRecord(**r)


def test_transform_falls_back_to_resolver_when_gloss_unmatched():
    # resolve_by_gloss returns None (no gloss match) -> legacy resolver is used,
    # but the emitted gloss is still recorded.
    recs = mge.chain_records_from_sonnet(
        topic="anger", topic_synset_id="1", gloss="g",
        sonnet_resp=_sonnet_resp_with_glosses(), proposer="sonnet_v1", round_num=2,
        generated_at="2026-06-04T00:00:00+00:00",
        resolve_synset=_resolver({"anger": "1", "volcano": "2", "pressure": "3"}),
        resolve_by_gloss=_gloss_resolver({}),  # never matches
    )
    r = recs[0]
    assert r["vehicle_synset_id"] == "2"                  # fell back to resolver
    assert r["chain"][-1]["gloss"] == "GV"                # gloss still recorded
    assert r["chain"][1]["synset_id"] == "3"


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


def test_load_avoid_vehicles(tmp_path):
    p = tmp_path / "avoid.json"
    p.write_text('["fermentation", "undertow", "tide"]')
    assert mge.load_avoid_vehicles(str(p)) == ["fermentation", "undertow", "tide"]


def test_load_avoid_vehicles_none_path_returns_empty():
    assert mge.load_avoid_vehicles(None) == []


def test_load_avoid_vehicles_rejects_non_list(tmp_path):
    p = tmp_path / "avoid.json"
    p.write_text('{"avoid_vehicles": ["fermentation"]}')
    with pytest.raises(ValueError):
        mge.load_avoid_vehicles(str(p))


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


def test_run_threads_resolve_by_gloss(tmp_path):
    # emit-the-sense end-to-end: run() passes resolve_by_gloss through, so a
    # gloss-emitting Sonnet response snaps the vehicle by gloss-match.
    out = tmp_path / "chains.jsonl"

    def sonnet(prompt):
        return _sonnet_resp_with_glosses()

    res = mge.run(
        topics=[{"word": "anger", "topic_synset_id": "1", "gloss": "g1"}],
        output_jsonl=str(out), haiku_fn=_haiku, sonnet_fn=sonnet,
        resolve_synset=_resolve_all,                       # would snap volcano -> "9"
        resolve_by_gloss=_gloss_resolver({("volcano", "GV"): "9g", ("pressure", "GP"): "7g"}),
        proposer="sonnet_v1", round_num=2, batch_size=20,
        now_fn=lambda: "2026-06-04T00:00:00+00:00",
    )
    assert res["chains_written"] == 1
    rec = json.loads(out.read_text().splitlines()[0])
    assert rec["vehicle_synset_id"] == "9g"               # gloss-match, not "9"
    assert rec["chain"][-1]["gloss"] == "GV"


def test_run_threads_avoid_vehicles_into_sonnet_prompt(tmp_path):
    """The avoid-list reaches the Sonnet substitution prompt, so the soft
    diversity nudge applies where the final vehicle is actually chosen."""
    out = tmp_path / "chains.jsonl"
    seen_prompts = []

    def sonnet(prompt):
        seen_prompts.append(prompt)
        return _sonnet_resp()

    mge.run(
        topics=_two_topics(), output_jsonl=str(out), haiku_fn=_haiku, sonnet_fn=sonnet,
        resolve_synset=_resolve_all, batch_size=20,
        avoid_vehicles=["fermentation", "undertow"],
        now_fn=lambda: "2026-06-04T00:00:00+00:00",
    )
    assert any("fermentation" in p and "over-used" in p.lower() for p in seen_prompts)


def test_run_omits_avoid_block_without_avoid_vehicles(tmp_path):
    out = tmp_path / "chains.jsonl"
    seen_prompts = []
    mge.run(
        topics=_two_topics(), output_jsonl=str(out), haiku_fn=_haiku,
        sonnet_fn=lambda p: (seen_prompts.append(p) or _sonnet_resp()),
        resolve_synset=_resolve_all, batch_size=20,
        now_fn=lambda: "2026-06-04T00:00:00+00:00",
    )
    assert all("over-used" not in p.lower() for p in seen_prompts)


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


# --- review hardening: distinct-synset topics + a volcano/storm resolver -----
def _topics(n):
    return [{"word": f"w{i}", "topic_synset_id": str(100 + i), "gloss": "g"} for i in range(n)]


def _resolve_vehicles(w):
    return {"volcano": "9", "storm": "8", "pressure": "7"}.get(w)


# --- money-safety: cost charged at point of spend, not only on success -------
def test_run_charges_cost_on_attempt_even_when_every_topic_errors(tmp_path):
    """Cost guard must NOT fail open: a topic that spent Haiku+Sonnet then errored
    still accrues its spend, so --max-cost-usd can engage on an all-error tail."""
    out = tmp_path / "c.jsonl"

    def boom(prompt):
        raise RuntimeError("sonnet down")

    res = mge.run(
        topics=_two_topics(), output_jsonl=str(out), haiku_fn=_haiku, sonnet_fn=boom,
        resolve_synset=_resolve_all, now_fn=lambda: "2026-06-04T00:00:00+00:00",
    )
    assert res["est_cost_usd"] == pytest.approx(
        2 * (mge.HAIKU_COST_PER_TOPIC + mge.SONNET_COST_PER_TOPIC)
    )


def test_run_cost_cap_stops_within_batch(tmp_path):
    """Overshoot must be bounded to ~one topic, not a whole batch."""
    out = tmp_path / "c.jsonl"
    res = mge.run(
        topics=_topics(5), output_jsonl=str(out), haiku_fn=_haiku,
        sonnet_fn=lambda p: _sonnet_resp(), resolve_synset=_resolve_vehicles,
        batch_size=20, max_cost_usd=0.6, now_fn=lambda: "2026-06-04T00:00:00+00:00",
    )
    # per_topic ~0.252: stops once est_cost >= 0.6, i.e. after the 3rd topic
    assert res["paused"] is True and res["pause_reason"] == "cost_cap"
    assert res["topics_processed"] == 3


# --- safety brake: zero-record batches must feed the tripwire ----------------
def test_run_tripwire_pauses_on_all_empty_batches(tmp_path):
    """A cratering tail can produce ZERO valid records per batch (all vehicles
    unresolvable). That total collapse must trip the brake, not slip past it."""
    out = tmp_path / "c.jsonl"
    tw = mlr.new_tripwire(window=4, min_judged=2, abs_floor=0.5, rel_drop=0.9, baseline_n=2)
    res = mge.run(
        topics=_topics(6), output_jsonl=str(out), haiku_fn=_haiku,
        sonnet_fn=lambda p: _sonnet_resp(), resolve_synset=lambda w: None,  # nothing resolves
        batch_size=1, tripwire=tw, judge_fn=lambda rec: {"verdict": "dead", "ok": True},
        judge_sample=2, now_fn=lambda: "2026-06-04T00:00:00+00:00",
    )
    assert res["paused"] is True and res["pause_reason"] == "tripwire"
    assert res["chains_written"] == 0


def test_run_tripwire_ignores_transient_errors(tmp_path):
    """A 429/transient-error storm ALSO produces zero-record batches — but those
    carry NO liveness signal (the topic never got a verdict; it's retried on
    resume). They must NOT feed synthetic-dead, or a session-limit outage
    false-trips the brake on healthy generation. Mirror of the all-empty test:
    same zero records, opposite cause, opposite verdict."""
    out = tmp_path / "c.jsonl"

    def boom(prompt):
        raise RuntimeError("429 session limit · resets 3pm (UTC)")

    tw = mlr.new_tripwire(window=4, min_judged=2, abs_floor=0.5, rel_drop=0.9, baseline_n=2)
    res = mge.run(
        topics=_topics(6), output_jsonl=str(out), haiku_fn=_haiku,
        sonnet_fn=boom, resolve_synset=_resolve_vehicles,
        batch_size=1, tripwire=tw, judge_fn=lambda rec: {"verdict": "dead", "ok": True},
        judge_sample=2, now_fn=lambda: "2026-06-04T00:00:00+00:00",
    )
    assert res["paused"] is False and res["pause_reason"] is None
    assert res["topics_processed"] == 6  # all attempted; none cut off by a false pause


def test_run_judge_samples_spread_across_distinct_topics(tmp_path):
    """The brake must see >=1 record per topic, not judge_sample records from a
    single prolific topic — else clustered degradation is invisible."""
    out = tmp_path / "c.jsonl"
    seen = []

    def judge(rec):
        seen.append(rec["topic_synset_id"])
        return {"verdict": "live", "ok": True}

    def sonnet_two_vehicles(prompt):
        return {"vehicles": [
            {"vehicle": "volcano", "chain": [{"phrase": "x", "head": "x"}, {"phrase": "volcano", "head": "volcano"}]},
            {"vehicle": "storm", "chain": [{"phrase": "y", "head": "y"}, {"phrase": "storm", "head": "storm"}]},
        ]}

    tw = mlr.new_tripwire(window=10, min_judged=100, abs_floor=0.0, rel_drop=1.0, baseline_n=10)
    mge.run(
        topics=_topics(2), output_jsonl=str(out), haiku_fn=_haiku, sonnet_fn=sonnet_two_vehicles,
        resolve_synset=_resolve_vehicles, batch_size=20, tripwire=tw, judge_fn=judge,
        judge_sample=2, now_fn=lambda: "2026-06-04T00:00:00+00:00",
    )
    assert len(seen) == 2 and len(set(seen)) == 2  # two DISTINCT topics, not 2 vehicles of one


# --- output integrity: self-metaphor + within-topic dedup -------------------
def test_transform_skips_self_metaphor():
    sonnet = {"vehicles": [{"vehicle": "fire", "chain": [
        {"phrase": "fire", "head": "fire"}, {"phrase": "heat", "head": "heat"},
        {"phrase": "fire", "head": "fire"}]}]}
    recs = mge.chain_records_from_sonnet(
        topic="fire", topic_synset_id="1", gloss="g", sonnet_resp=sonnet,
        proposer="sonnet_v1", round_num=2, generated_at="2026-06-04T00:00:00+00:00",
        resolve_synset=_resolver({"fire": "1", "heat": "3"}),  # vehicle 'fire' -> topic synset
    )
    assert recs == []


def test_transform_dedups_repeated_walk():
    v = {"vehicle": "volcano", "chain": [
        {"phrase": "anger", "head": "anger"}, {"phrase": "pressure", "head": "pressure"},
        {"phrase": "volcano", "head": "volcano"}]}
    recs = mge.chain_records_from_sonnet(
        topic="anger", topic_synset_id="1", gloss="g", sonnet_resp={"vehicles": [v, v]},
        proposer="sonnet_v1", round_num=2, generated_at="2026-06-04T00:00:00+00:00",
        resolve_synset=_resolver({"anger": "1", "volcano": "2", "pressure": "3"}),
    )
    assert len(recs) == 1  # identical walk emitted twice -> one record (signature dedup)


# --- idempotency: zero-record topics must not be re-spent on resume ----------
def test_run_does_not_respend_zero_record_topics(tmp_path):
    out = tmp_path / "c.jsonl"
    calls = []

    def haiku(word, gloss):
        calls.append(word)
        return {"topic": word, "metaphors": [{"vehicle": "volcano", "shared_features": []}]}

    kw = dict(output_jsonl=str(out), haiku_fn=haiku, sonnet_fn=lambda p: _sonnet_resp(),
              resolve_synset=lambda w: None, now_fn=lambda: "2026-06-04T00:00:00+00:00")
    r1 = mge.run(topics=_topics(2), **kw)
    assert r1["chains_written"] == 0
    r2 = mge.run(topics=_topics(2), **kw)  # permanently-empty topics must be skipped
    assert r2["topics_processed"] == 0
    assert len(calls) == 2  # Haiku spent only once per topic, never re-billed


# --- session-limit fast-pause + pause notification ---------------------------
# generate_metaphor_edges imports claude_client onto sys.path, so this resolves.
from claude_client import SessionLimitError, SessionLimitFormatError  # noqa: E402


def test_run_pauses_fast_on_session_limit(tmp_path):
    """A 429 session limit must STOP the whole run immediately (not skip the
    topic and grind on), recording the parsed reset time for a clean resume."""
    out = tmp_path / "c.jsonl"

    def limit(prompt):
        raise SessionLimitError("limit", reset_text="resets 7:50am (UTC)",
                                reset_hour=7, reset_minute=50)

    res = mge.run(
        topics=_topics(6), output_jsonl=str(out), haiku_fn=_haiku, sonnet_fn=limit,
        resolve_synset=_resolve_vehicles, batch_size=2,
        now_fn=lambda: "2026-06-04T00:00:00+00:00",
    )
    assert res["paused"] is True and res["pause_reason"] == "session_limit"
    assert res["reset_hour"] == 7 and res["reset_minute"] == 50
    assert "7:50" in res["reset_text"]
    assert res["topics_processed"] == 1          # stopped at the first, didn't grind 6
    assert mge.completed_topic_synset_ids(str(out)) == set()  # nothing banked; retries on resume


def test_run_session_limit_unparseable_pauses_loudly(tmp_path):
    """A confirmed 429 whose reset format we can't parse must halt with a
    DISTINCT loud reason, not the graceful session_limit path."""
    out = tmp_path / "c.jsonl"

    def boom(prompt):
        raise SessionLimitFormatError("unparseable", raw="hit your limit (try later)")

    res = mge.run(
        topics=_topics(6), output_jsonl=str(out), haiku_fn=_haiku, sonnet_fn=boom,
        resolve_synset=_resolve_vehicles, batch_size=2,
        now_fn=lambda: "2026-06-04T00:00:00+00:00",
    )
    assert res["paused"] is True
    assert res["pause_reason"] == "session_limit_unparseable"
    assert res["topics_processed"] == 1


def test_run_notifies_on_session_limit_pause(tmp_path):
    """notify_fn must fire on a pause, carrying the summary (reason + reset)."""
    out = tmp_path / "c.jsonl"
    seen = []

    def limit(prompt):
        raise SessionLimitError("limit", reset_text="resets 3pm (UTC)",
                                reset_hour=15, reset_minute=0)

    mge.run(
        topics=_topics(3), output_jsonl=str(out), haiku_fn=_haiku, sonnet_fn=limit,
        resolve_synset=_resolve_vehicles, batch_size=1, notify_fn=seen.append,
        now_fn=lambda: "2026-06-04T00:00:00+00:00",
    )
    assert len(seen) == 1
    assert seen[0]["pause_reason"] == "session_limit"
    assert seen[0]["reset_text"] == "resets 3pm (UTC)"


def test_run_notifies_on_tripwire_pause(tmp_path):
    """ANY pause notifies — not just session limits. Tripwire collapse too."""
    out = tmp_path / "c.jsonl"
    seen = []
    tw = mlr.new_tripwire(window=1, min_judged=1, abs_floor=0.5, rel_drop=0.9, baseline_n=1)
    mge.run(
        topics=_two_topics(), output_jsonl=str(out), haiku_fn=_haiku,
        sonnet_fn=lambda p: _sonnet_resp(), resolve_synset=_resolve_all,
        batch_size=1, tripwire=tw, judge_fn=lambda rec: {"verdict": "dead", "ok": True},
        judge_sample=1, notify_fn=seen.append, now_fn=lambda: "2026-06-04T00:00:00+00:00",
    )
    assert len(seen) == 1 and seen[0]["pause_reason"] == "tripwire"


def test_run_no_notify_on_clean_completion(tmp_path):
    """A run that finishes without pausing must NOT notify."""
    out = tmp_path / "c.jsonl"
    seen = []
    mge.run(
        topics=_two_topics(), output_jsonl=str(out), haiku_fn=_haiku,
        sonnet_fn=lambda p: _sonnet_resp(), resolve_synset=_resolve_all,
        notify_fn=seen.append, now_fn=lambda: "2026-06-04T00:00:00+00:00",
    )
    assert seen == []


# --- NTFY pause notification (poster + message formatter) ---------------------
def test_format_pause_message_session_limit():
    msg = mge.format_pause_message({
        "pause_reason": "session_limit", "topics_processed": 12,
        "chains_written": 118, "est_cost_usd": 3.1,
        "reset_text": "resets 7:50am (UTC)", "reset_hour": 7, "reset_minute": 50,
    })
    assert "session_limit" in msg
    assert "resets 7:50am (UTC)" in msg
    assert "118" in msg  # progress is visible


def test_format_pause_message_unparseable_is_loud():
    msg = mge.format_pause_message({
        "pause_reason": "session_limit_unparseable", "topics_processed": 5,
        "chains_written": 40, "est_cost_usd": 1.0, "reset_text": "weird new text",
    })
    low = msg.lower()
    assert "unparseable" in low or "unrecognised" in low or "server" in low


def test_notify_ntfy_noop_when_unconfigured(monkeypatch):
    monkeypatch.delenv("NTFY_URL", raising=False)
    monkeypatch.delenv("NTFY_TOKEN", raising=False)
    calls = []
    sent = mge.notify_ntfy("hello", post_fn=lambda u, m, h: calls.append((u, m, h)))
    assert sent is False and calls == []  # never posts without a configured URL


def test_notify_ntfy_posts_with_auth_when_configured(monkeypatch):
    monkeypatch.setenv("NTFY_URL", "https://ntfy.example/topic")
    monkeypatch.setenv("NTFY_TOKEN", "tok123")
    calls = []
    sent = mge.notify_ntfy("hello", post_fn=lambda u, m, h: calls.append((u, m, h)))
    assert sent is True
    url, message, headers = calls[0]
    assert url == "https://ntfy.example/topic" and message == "hello"
    assert headers.get("Authorization") == "Bearer tok123"


def test_notify_ntfy_swallows_post_errors(monkeypatch):
    monkeypatch.setenv("NTFY_URL", "https://ntfy.example/topic")
    monkeypatch.delenv("NTFY_TOKEN", raising=False)

    def boom(u, m, h):
        raise RuntimeError("network down")

    # best-effort: a failed POST must not raise (would otherwise crash the run)
    assert mge.notify_ntfy("hello", post_fn=boom) is False


# --- summary-out (machine-readable handoff for the autonomous wrapper) --------
def test_write_summary_roundtrips_without_tripwire(tmp_path):
    p = tmp_path / "summary.json"
    mge._write_summary({"pause_reason": "session_limit", "reset_text": "resets 3pm (UTC)",
                         "tripwire": object()}, str(p))  # tripwire is non-serialisable
    got = json.loads(p.read_text())
    assert got["pause_reason"] == "session_limit"
    assert got["reset_text"] == "resets 3pm (UTC)"
    assert "tripwire" not in got  # stripped — not JSON-serialisable, not needed downstream


# ---------------------------------------------------------------------------
# Task 4: chain.v2 emission — vec: vehicle gate, per-step node_ref + apt_senses
# ---------------------------------------------------------------------------

def _oov_vec_gate(phrase, head):
    """Stub: admits only 'pressed flower' as a vec: node (OOV multi-word)."""
    return phrase == "pressed flower"


def _sonnet_resp_oov_vehicle():
    """Sonnet response whose vehicle is an OOV multi-word phrase."""
    return {"topic": "ignored", "vehicles": [
        {"vehicle": "pressed flower", "chain": [
            {"phrase": "NOT_TOPIC", "head": "emotion"},
            {"phrase": "memory", "head": "memory"},
            {"phrase": "pressed flower", "head": "flower"},
        ]},
    ]}


def test_transform_v2_oov_vehicle_admitted_as_vec_not_skipped():
    """An OOV multi-word vehicle that resolver cannot snap is admitted as a
    vec: node when vec_gate_fn approves — no skip, valid chain.v2 record."""
    recs = mge.chain_records_from_sonnet(
        topic="anger", topic_synset_id="1", gloss="g",
        sonnet_resp=_sonnet_resp_oov_vehicle(),
        proposer="sonnet_v1", round_num=2,
        generated_at="2026-06-04T00:00:00+00:00",
        resolve_synset=_resolver({"anger": "1", "memory": "5"}),
        vec_gate_fn=_oov_vec_gate,
    )
    assert len(recs) == 1
    r = recs[0]
    assert r["schema_version"] == "chain.v2"
    assert r["vehicle"] == "pressed flower"
    assert r["vehicle_synset_id"] is None
    assert r["vehicle_node_ref"] == "vec:pressed_flower"
    ChainRecord(**r)  # must validate as a proper chain.v2 record


def test_transform_v2_resolvable_vehicle_produces_syn_node_ref():
    """With vec_gate_fn provided, a normally-resolvable vehicle still gets
    schema_version=chain.v2 and syn: node_ref — the resolver path is unchanged."""
    recs = mge.chain_records_from_sonnet(
        topic="anger", topic_synset_id="1", gloss="g",
        sonnet_resp=_sonnet_resp(),
        proposer="sonnet_v1", round_num=2,
        generated_at="2026-06-04T00:00:00+00:00",
        resolve_synset=_resolver({"anger": "1", "volcano": "2", "pressure": "3"}),
        vec_gate_fn=lambda phrase, head: False,  # gate closed for all
    )
    assert len(recs) == 1
    r = recs[0]
    assert r["schema_version"] == "chain.v2"
    assert r["vehicle_synset_id"] == "2"
    assert r["vehicle_node_ref"] == "syn:2"
    assert r["topic_node_ref"] == "syn:1"
    ChainRecord(**r)


def test_transform_v2_steps_carry_intended_apt_senses():
    """chain.v2 steps carry apt_senses with the intended synset; vec: steps
    carry an empty list (no synset to record)."""
    recs = mge.chain_records_from_sonnet(
        topic="anger", topic_synset_id="1", gloss="g",
        sonnet_resp=_sonnet_resp_oov_vehicle(),
        proposer="sonnet_v1", round_num=2,
        generated_at="2026-06-04T00:00:00+00:00",
        resolve_synset=_resolver({"anger": "1", "memory": "5"}),
        vec_gate_fn=_oov_vec_gate,
    )
    r = recs[0]
    # Topic step: resolved → apt_senses with intended sense
    topic_step = r["chain"][0]
    assert topic_step["apt_senses"] == [{"synset_id": "1", "source": "intended"}]
    assert topic_step["node_ref"] == "syn:1"
    # Intermediate step: resolved → apt_senses with intended sense
    mid_step = r["chain"][1]
    assert mid_step["apt_senses"] == [{"synset_id": "5", "source": "intended"}]
    assert mid_step["node_ref"] == "syn:5"
    # Vec: vehicle step: no synset → empty apt_senses
    vec_step = r["chain"][-1]
    assert vec_step["apt_senses"] == []
    assert vec_step["node_ref"] == "vec:pressed_flower"


def test_transform_v2_unresolvable_vehicle_not_vec_eligible_skipped():
    """An unresolvable vehicle that also fails the vec: gate is still skipped —
    the gate is the sole admission criterion when a synset is absent."""
    recs = mge.chain_records_from_sonnet(
        topic="anger", topic_synset_id="1", gloss="g",
        sonnet_resp=_sonnet_resp(vehicle="xyzzy"),
        proposer="sonnet_v1", round_num=2,
        generated_at="2026-06-04T00:00:00+00:00",
        resolve_synset=_resolver({"anger": "1", "pressure": "3"}),
        vec_gate_fn=lambda phrase, head: False,  # gate closed for all
    )
    assert recs == []


def test_run_v2_vec_vehicle_written_to_jsonl(tmp_path):
    """run() threads vec_gate_fn so OOV vehicles reach the output file rather
    than being silently dropped."""
    out = tmp_path / "chains.jsonl"

    def sonnet(_prompt):
        return _sonnet_resp_oov_vehicle()

    res = mge.run(
        topics=[{"word": "anger", "topic_synset_id": "1", "gloss": "g"}],
        output_jsonl=str(out),
        haiku_fn=_haiku,
        sonnet_fn=sonnet,
        resolve_synset=_resolver({"anger": "1", "memory": "5"}),
        vec_gate_fn=_oov_vec_gate,
        now_fn=lambda: "2026-06-04T00:00:00+00:00",
    )
    assert res["chains_written"] == 1
    rec = json.loads(out.read_text().splitlines()[0])
    assert rec["schema_version"] == "chain.v2"
    assert rec["vehicle_synset_id"] is None
    assert rec["vehicle_node_ref"] == "vec:pressed_flower"
    ChainRecord(**rec)
