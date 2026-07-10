"""Continuous metaphor-edge generation runner (chain.v1, grading-native).

Turns a file of vetted topics into one `chain.v1` ChainRecord per
(topic → vehicle), the exact format the grading tool consumes. Per the
2026-06-04 decision the output is JSONL-native (DB ingestion deferred); the
grading bootstrap loop reads these round files directly.

Pipeline per topic:
  Haiku apt vehicles (`build_apt_prompt`)  →  Sonnet ordered chains
  (`run_chain_spike.build_prompt`, context-free-hop clause)  →  explode +
  canonicalise endpoints + snap heads → append chain.v1 JSONL.

Operational properties (the genuinely-missing parts the Stage A driver lacked):
  * resume-by-topic_synset_id  (idempotent: re-running never duplicates)
  * `--max-topics` hard cap + `--max-cost-usd` soft guard (estimated)
  * proxy-judge live-rate TRIPWIRE that auto-pauses a cratering run
  * per-batch timing/cost log + periodic git auto-commit

All LLM access is injected (haiku_fn / sonnet_fn / judge_fn / resolve_synset)
so the logic is unit-tested without spending. Production wiring is in the
make_* factories + main().
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))                         # local scripts
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))   # claude_client
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "grading_sidecar"))  # models

import metaphor_live_rate as mlr  # noqa: E402
from run_chain_spike import build_prompt  # noqa: E402  (Sonnet chain prompt + clauses)
from models import ChainRecord, compute_chain_signature, vec_ref  # noqa: E402
from claude_client import SessionLimitError, SessionLimitFormatError  # noqa: E402

log = logging.getLogger(__name__)

# Measured per-topic spend (docs/inbox/2026-06-03-context-free-edges). Used for
# the cost LOG and the soft cap; --max-topics is the deterministic hard cap.
HAIKU_COST_PER_TOPIC = 0.062
SONNET_COST_PER_TOPIC = 0.19


# ---------------------------------------------------------------------------
# Pure transform: Sonnet response -> canonical chain.v1 records
# ---------------------------------------------------------------------------

def chain_records_from_sonnet(
    *,
    topic: str,
    topic_synset_id: str,
    gloss: str,
    sonnet_resp: dict,
    proposer: str,
    round_num: int,
    generated_at: str,
    resolve_synset,
    resolve_by_gloss=None,
    vec_gate_fn=None,
) -> list[dict]:
    """Explode a Sonnet response into validated chain records.

    Without `vec_gate_fn` (default): chain.v1 behaviour — endpoints are FORCED
    canonical (chain[0] := (topic, topic, topic_synset_id) and chain[-1] :=
    (vehicle, vehicle, vehicle_synset_id)); a vehicle whose lemma does not
    resolve to a synset is skipped.

    With `vec_gate_fn` (callable `(phrase, head) -> bool`): emits chain.v2
    records.  Per-step `node_ref` and `apt_senses` are set; vehicles that fail
    synset resolution are admitted as vec: nodes when `vec_gate_fn` approves
    (OOV multi-word phrases with no noun senses in the lexicon), and the
    record carries `topic_node_ref` / `vehicle_node_ref`.  A vehicle that fails
    both the resolver and the vec: gate is still skipped.

    The signature is computed over the FINAL phrases (what a grader sees), so
    it matches across runs that produce the same walk.

    emit-the-sense: when `resolve_by_gloss(lemma, gloss) -> synset_id | None` is
    supplied and the model emitted a per-step `gloss`, each node is snapped by
    gloss-to-gloss match first, falling back to `resolve_synset` on no match.
    Every step records its emitted gloss (topic from the curated `gloss` param,
    vehicle/intermediates from the model) so the sense intent survives re-snaps.
    With `resolve_by_gloss=None` (default) the snap is identical to before.
    """
    def _snap(emitted_gloss, *fallback_lemmas):
        """Gloss-match first (emit-the-sense), else the legacy resolver(s)."""
        lemma = fallback_lemmas[0]
        if resolve_by_gloss is not None and emitted_gloss:
            sid = resolve_by_gloss(lemma, emitted_gloss)
            if sid:
                return sid
        for fl in fallback_lemmas:
            sid = resolve_synset(fl)
            if sid:
                return sid
        return None

    out: list[dict] = []
    seen_sigs: set[str] = set()
    for v in sonnet_resp.get("vehicles", []) if isinstance(sonnet_resp, dict) else []:
        if not isinstance(v, dict):
            continue
        vehicle = v.get("vehicle")
        if not isinstance(vehicle, str) or not vehicle.strip():
            continue
        vehicle = vehicle.strip()
        raw_chain = v.get("chain", []) if isinstance(v.get("chain"), list) else []
        # the vehicle's emitted sense is the model's final step gloss
        vehicle_gloss = (raw_chain[-1].get("gloss")
                         if raw_chain and isinstance(raw_chain[-1], dict) else None)
        vehicle_gloss = vehicle_gloss if isinstance(vehicle_gloss, str) else None
        vehicle_synset_id = _snap(vehicle_gloss, vehicle)

        # vec: vehicle admission (chain.v2 mode only): when the resolver returns
        # None, consult vec_gate_fn instead of unconditionally skipping.  A
        # vehicle that fails both resolver and gate is still dropped.
        vehicle_node_ref: str | None = None
        if not vehicle_synset_id:
            if vec_gate_fn is not None and vec_gate_fn(vehicle, vehicle):
                # OOV multi-word or otherwise lexicon-absent vehicle — admit as a
                # vector node.  Logged via the gate itself (sense_inventory.vec_gate).
                log.info("admit vec: vehicle %r for topic %r", vehicle, topic)
                vehicle_node_ref = f"vec:{vec_ref(vehicle)}"
                # vehicle_synset_id stays None — the ChainRecord validator
                # requires vehicle_node_ref to match in this case.
            else:
                log.info("skip vehicle %r for topic %r: no synset", vehicle, topic)
                continue
        else:
            vehicle_node_ref = f"syn:{vehicle_synset_id}" if vec_gate_fn is not None else None

        if vehicle_synset_id == topic_synset_id and topic_synset_id is not None:
            # self-metaphor (topic echoed as vehicle, or a lemma resolving back to
            # the topic synset) is not a metaphor — drop it, don't grade it.
            log.info("skip self-metaphor %r for topic %r", vehicle, topic)
            continue

        # Build steps.  In chain.v2 mode each step carries node_ref + apt_senses.
        topic_step: dict = {"phrase": topic, "head": topic,
                            "synset_id": topic_synset_id, "gloss": gloss or None}
        if vec_gate_fn is not None:
            topic_step["node_ref"]   = f"syn:{topic_synset_id}"
            topic_step["apt_senses"] = [{"synset_id": topic_synset_id, "source": "intended"}]

        steps = [topic_step]
        for s in raw_chain[1:-1]:  # intermediates only; endpoints are forced
            if not isinstance(s, dict):
                continue
            phrase = s.get("phrase")
            if not isinstance(phrase, str) or not phrase.strip():
                continue
            phrase = phrase.strip()
            head = s.get("head")
            head = head.strip() if isinstance(head, str) and head.strip() else phrase
            s_gloss = s.get("gloss") if isinstance(s.get("gloss"), str) else None
            sid = _snap(s_gloss, head, phrase)
            step_d: dict = {"phrase": phrase, "head": head,
                            "synset_id": sid, "gloss": s_gloss}
            if vec_gate_fn is not None:
                if sid is not None:
                    step_d["node_ref"]   = f"syn:{sid}"
                    step_d["apt_senses"] = [{"synset_id": sid, "source": "intended"}]
                else:
                    step_d["node_ref"]   = f"vec:{vec_ref(phrase)}"
                    step_d["apt_senses"] = []
            steps.append(step_d)

        vehicle_step: dict = {"phrase": vehicle, "head": vehicle,
                              "synset_id": vehicle_synset_id, "gloss": vehicle_gloss}
        if vec_gate_fn is not None:
            vehicle_step["node_ref"]   = vehicle_node_ref
            vehicle_step["apt_senses"] = (
                [{"synset_id": vehicle_synset_id, "source": "intended"}]
                if vehicle_synset_id is not None else []
            )
        steps.append(vehicle_step)

        phrases = [s["phrase"] for s in steps]
        signature = compute_chain_signature(proposer, phrases)
        if signature in seen_sigs:
            # identical walk emitted twice in one response -> one card, not two
            # (chain_signature is the grading dedup/verdict key).
            continue

        if vec_gate_fn is not None:
            # chain.v2: include node-ref endpoint fields; vehicle_synset_id may be None
            rec = {
                "schema_version": "chain.v2",
                "topic": topic,
                "topic_synset_id": topic_synset_id,
                "topic_node_ref": f"syn:{topic_synset_id}",
                "vehicle": vehicle,
                "vehicle_synset_id": vehicle_synset_id,
                "vehicle_node_ref": vehicle_node_ref,
                "proposer": proposer,
                "round": round_num,
                "chain": steps,
                "chain_signature": signature,
                "generated_at": generated_at,
            }
        else:
            rec = {
                "schema_version": "chain.v1",
                "topic": topic,
                "topic_synset_id": topic_synset_id,
                "vehicle": vehicle,
                "vehicle_synset_id": vehicle_synset_id,
                "proposer": proposer,
                "round": round_num,
                "chain": steps,
                "chain_signature": signature,
                "generated_at": generated_at,
            }
        try:
            ChainRecord(**rec)  # guarantee grading-ingestible; skip otherwise
        except Exception as exc:  # noqa: BLE001 — invalid record is a skip, not a crash
            log.warning("skip invalid chain %s->%s: %s", topic, vehicle, exc)
            continue
        seen_sigs.add(signature)
        out.append(rec)
    return out


# ---------------------------------------------------------------------------
# Resume / input / cost helpers
# ---------------------------------------------------------------------------

def completed_topic_synset_ids(output_jsonl: str) -> set[str]:
    """Set of topic_synset_ids already present in the output (resume key)."""
    p = Path(output_jsonl)
    if not p.exists():
        return set()
    done: set[str] = set()
    with p.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                log.warning("resume: skipping malformed line in %s", output_jsonl)
                continue
            tsid = d.get("topic_synset_id")
            if tsid is not None:
                done.add(tsid)
    return done


def _attempted_path(output_jsonl: str) -> str:
    return output_jsonl + ".attempted"


def read_attempted(output_jsonl: str) -> set[str]:
    """topic_synset_ids that completed the pipeline but produced ZERO usable
    records (e.g. every vehicle unresolvable). These are spent-and-empty, so a
    resume must NOT re-bill them — distinct from transient errors, which are not
    recorded here and so DO retry."""
    p = Path(_attempted_path(output_jsonl))
    if not p.exists():
        return set()
    return {line.strip() for line in p.open() if line.strip()}


def _append_attempted(output_jsonl: str, topic_synset_id: str) -> None:
    with open(_attempted_path(output_jsonl), "a") as f:
        f.write(topic_synset_id + "\n")
        f.flush()
        os.fsync(f.fileno())


def _spread_sample(records: list[dict], k: int) -> list[dict]:
    """At most one record per distinct topic_synset_id, up to k — so the brake's
    window sees k different TOPICS, not k vehicles of one prolific topic."""
    seen: set[str] = set()
    out: list[dict] = []
    for r in records:
        t = r.get("topic_synset_id")
        if t in seen:
            continue
        seen.add(t)
        out.append(r)
        if len(out) >= k:
            break
    return out


def load_vetted_topics(path: str) -> list[dict]:
    """Load a vetted topics file: {"topics":[{word, topic_synset_id, gloss}]}.

    Raises ValueError on a malformed file or a topic missing a required field —
    a sense-unvetted topic must never silently reach generation.
    """
    data = json.loads(Path(path).read_text())
    topics = data.get("topics") if isinstance(data, dict) else data
    if not isinstance(topics, list):
        raise ValueError("topics file must contain a 'topics' list")
    for t in topics:
        if not isinstance(t, dict):
            raise ValueError(f"topic entry is not an object: {t!r}")
        for k in ("word", "topic_synset_id", "gloss"):
            if not t.get(k):
                raise ValueError(f"topic missing required field {k!r}: {t!r}")
    return topics


def estimate_cost(
    n_topics: int,
    *,
    haiku_per_topic: float = HAIKU_COST_PER_TOPIC,
    sonnet_per_topic: float = SONNET_COST_PER_TOPIC,
) -> float:
    """Estimated USD for n_topics. Pass haiku_per_topic=0 when reusing stored
    Haiku output (no Haiku re-spend)."""
    return n_topics * (haiku_per_topic + sonnet_per_topic)


def load_avoid_vehicles(path: str | None) -> list[str]:
    """Load the over-used-vehicle AVOID list — a JSON array of lemma strings.

    None/absent path → [] (no AVOID block; current behaviour). A non-list or
    malformed file raises ValueError: a mis-shaped diversity payload must fail
    loudly, not silently steer nothing on a multi-day run.
    """
    if not path:
        return []
    data = json.loads(Path(path).read_text())
    if not isinstance(data, list) or not all(isinstance(v, str) for v in data):
        raise ValueError(f"avoid-vehicles file must be a JSON list of strings: {path!r}")
    return data


# ---------------------------------------------------------------------------
# The batch driver
# ---------------------------------------------------------------------------

def run(
    *,
    topics: list[dict],
    output_jsonl: str,
    haiku_fn,
    sonnet_fn,
    resolve_synset,
    resolve_by_gloss=None,
    vec_gate_fn=None,
    proposer: str = "sonnet_v1",
    round_num: int = 2,
    batch_size: int = 20,
    max_topics: int | None = None,
    max_cost_usd: float | None = None,
    tripwire=None,
    judge_fn=None,
    judge_sample: int = 2,
    anti_examples: list[dict] | None = None,
    avoid_vehicles: list[str] | None = None,
    now_fn=None,
    autocommit_every: int | None = None,
    commit_fn=None,
    log_fn=None,
    notify_fn=None,
    haiku_cost_per_topic: float = HAIKU_COST_PER_TOPIC,
    sonnet_cost_per_topic: float = SONNET_COST_PER_TOPIC,
) -> dict:
    """Generate chains for `topics`, appending chain.v1 JSONL to output_jsonl.

    Returns a summary dict. Pauses (without raising) when the tripwire trips,
    the estimated cost guard is hit, or a 429 session limit lands, leaving a
    resumable output file behind. `notify_fn`, if given, is called once with
    the summary dict on ANY pause (best-effort; its failure never aborts the run).
    """
    now_fn = now_fn or (lambda: datetime.now(timezone.utc).isoformat())
    out_path = Path(output_jsonl)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Resume key = topics already in the output OR recorded spent-and-empty.
    completed = completed_topic_synset_ids(output_jsonl) | read_attempted(output_jsonl)
    pending = [t for t in topics if t["topic_synset_id"] not in completed]
    if max_topics is not None:
        pending = pending[:max_topics]

    topics_processed = chains_written = batches = 0
    est_cost = 0.0
    paused = False
    pause_reason = None
    session_reset_text = None
    session_reset_hour = None
    session_reset_minute = None

    for bstart in range(0, len(pending), batch_size):
        batch = pending[bstart:bstart + batch_size]
        batch_recs: list[dict] = []
        batch_clean_empty = 0  # topics that returned cleanly but yielded no records
        t0 = time.monotonic()

        for t in batch:
            word, tsid, gloss = t["word"], t["topic_synset_id"], t.get("gloss", "")
            topics_processed += 1
            recs: list[dict] = []
            errored = False
            try:
                # Charge each LLM call on ATTEMPT (try/finally) so a call that
                # raised — possibly after paid retries — still counts. Over-counting
                # is the safe direction for a spend brake; under-counting is not.
                try:
                    apt = haiku_fn(word, gloss)
                finally:
                    est_cost += haiku_cost_per_topic
                metaphors = apt.get("metaphors", []) if isinstance(apt, dict) else []
                if metaphors:
                    prompt = build_prompt(
                        word, gloss, metaphors,
                        anti_examples or None, avoid_vehicles or None,
                    )
                    try:
                        sresp = sonnet_fn(prompt)
                    finally:
                        est_cost += sonnet_cost_per_topic
                    recs = chain_records_from_sonnet(
                        topic=word, topic_synset_id=tsid, gloss=gloss, sonnet_resp=sresp,
                        proposer=proposer, round_num=round_num, generated_at=now_fn(),
                        resolve_synset=resolve_synset, resolve_by_gloss=resolve_by_gloss,
                        vec_gate_fn=vec_gate_fn,
                    )
                else:
                    log.info("skip %s: no Haiku metaphors", word)
            except SessionLimitFormatError as exc:
                # A confirmed 429 whose reset format we can't parse: a possible
                # server-side change. Halt the WHOLE run loudly rather than
                # guess — surfaces the drift instead of silently grinding.
                log.critical(
                    "SESSION-LIMIT 429 with UNRECOGNISED reset format — possible "
                    "server change. Halting run loudly (at topic %r): %s", word, exc)
                paused, pause_reason = True, "session_limit_unparseable"
                session_reset_text = exc.raw
                break
            except SessionLimitError as exc:
                # Usage/session limit: resets in hours, not seconds. Stop the
                # whole run cleanly (this topic and every later one will fail)
                # and record the reset so the caller can schedule one resume.
                log.warning(
                    "session limit hit at topic %r — pausing for clean resume (resets %s)",
                    word, exc.reset_text)
                paused, pause_reason = True, "session_limit"
                session_reset_text = exc.reset_text
                session_reset_hour, session_reset_minute = exc.reset_hour, exc.reset_minute
                break
            except Exception as exc:  # noqa: BLE001 — one topic's failure must not abort the run
                errored = True
                log.warning("topic %r generation failed (will retry on resume): %s", word, exc)

            if recs:
                with out_path.open("a") as f:
                    for r in recs:
                        f.write(json.dumps(r, ensure_ascii=False) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
                chains_written += len(recs)
                batch_recs.extend(recs)
            elif not errored:
                # processed cleanly but produced nothing usable -> record so a
                # permanently-empty topic is never re-billed on resume. This is a
                # genuine liveness signal (the model answered; the answer was barren),
                # unlike a transient error, so it feeds the tripwire below.
                _append_attempted(output_jsonl, tsid)
                batch_clean_empty += 1

            # In-loop cost guard: bound overshoot to ~one topic, not a whole batch.
            if max_cost_usd is not None and est_cost >= max_cost_usd:
                paused, pause_reason = True, "cost_cap"
                break

        batches += 1
        elapsed = time.monotonic() - t0

        # --- tripwire: feed the brake even when a batch produced nothing ---
        window_rate = None
        if tripwire is not None and judge_fn is not None:
            if batch_recs:
                for rec in _spread_sample(batch_recs, judge_sample):
                    try:
                        verdict = judge_fn(rec)
                    except Exception as exc:  # noqa: BLE001 — a judge failure must not crash the run
                        log.warning("judge failed (not counted): %s", exc)
                        continue
                    if verdict.get("ok"):
                        tripwire = mlr.record_verdict(tripwire, verdict["verdict"])
            elif batch_clean_empty:
                # topics that answered cleanly but produced ZERO usable records ARE
                # a liveness collapse -> feed synthetic-dead. A batch that is empty
                # ONLY because every topic transiently errored (e.g. 429 session
                # limit) carries no verdict and must NOT feed the brake, or an
                # outage false-trips it; those topics simply retry on resume.
                for _ in range(judge_sample):
                    tripwire = mlr.record_verdict(tripwire, "dead")
            window_rate = mlr.live_rate(list(tripwire.recent))
            if not paused and mlr.should_pause(tripwire):
                paused, pause_reason = True, "tripwire"

        row = {
            "batch": batches, "topics_in_batch": len(batch),
            "chains_written_total": chains_written, "est_cost_usd": round(est_cost, 4),
            "elapsed_s": round(elapsed, 2), "live_rate_window": window_rate,
        }
        log.info("batch %s: %s", batches, row)
        if log_fn:
            log_fn(row)

        if autocommit_every and commit_fn and (batches % autocommit_every == 0):
            try:
                commit_fn()
            except Exception as exc:  # noqa: BLE001 — a commit hiccup must not lose generated work
                log.warning("autocommit failed (continuing): %s", exc)

        if paused:
            log.warning("run paused: %s (after batch %s)", pause_reason, batches)
            break

    summary = {
        "topics_processed": topics_processed,
        "chains_written": chains_written,
        "batches": batches,
        "est_cost_usd": round(est_cost, 4),
        "paused": paused,
        "pause_reason": pause_reason,
        "reset_text": session_reset_text,
        "reset_hour": session_reset_hour,
        "reset_minute": session_reset_minute,
        "tripwire": tripwire,
    }

    # Notify on ANY pause (tripwire / cost_cap / session_limit[_unparseable]).
    # Best-effort: a notification failure must never abort or mask the run.
    if paused and notify_fn is not None:
        try:
            notify_fn(summary)
        except Exception as exc:  # noqa: BLE001 — notification is advisory, not load-bearing
            log.warning("pause notification failed (continuing): %s", exc)

    return summary


# ---------------------------------------------------------------------------
# Production wiring (thin; exercised by the small validation run, not unit tests)
# ---------------------------------------------------------------------------

def make_live_sonnet_fn(model: str, prompt_json=None):
    if prompt_json is None:
        from claude_client import prompt_json
    return lambda prompt: prompt_json(prompt, model=model)


def make_live_haiku_fn(model: str, avoid_vehicles: list[str] | None = None, prompt_json=None):
    if prompt_json is None:
        from claude_client import prompt_json
    from metaphor_spike_1a import build_apt_prompt
    return lambda word, gloss: prompt_json(
        build_apt_prompt(word, gloss, avoid_vehicles or None), model=model)


def make_stored_haiku_fn(haiku_jsonl: str):
    """Reuse a stored Haiku apt JSONL (no Haiku re-spend) — keyed by topic."""
    from run_chain_spike import _load_jsonl
    by_topic = {d["topic"]: d for d in _load_jsonl(haiku_jsonl) if isinstance(d, dict) and d.get("topic")}
    return lambda word, gloss: by_topic.get(word, {"topic": word, "metaphors": []})


def make_resolver(conn):
    from metaphor_graph import lookup_primary_synset
    return lambda w: lookup_primary_synset(conn, w)


def make_vec_gate_fn(conn):
    """Return a (phrase, head) -> bool closure that admits OOV nodes as vec:
    nodes.  True when neither the phrase nor the head has any noun sense in the
    lexicon — the condition that makes a vec: node the only valid representation."""
    from sense_inventory import vec_gate
    return lambda phrase, head: vec_gate(conn, phrase, head)


def make_gloss_resolver(conn):
    """emit-the-sense resolver: snap a lemma to the synset whose definition best
    matches the model's emitted one-line gloss; None on no match (caller falls
    back to make_resolver)."""
    from metaphor_graph import snap_by_gloss
    return lambda lemma, gloss: snap_by_gloss(conn, lemma, gloss)


def make_judge_fn(model: str):
    return lambda rec: mlr.judge_chain(rec, model=model)


def format_pause_message(summary: dict) -> str:
    """Render a one-shot NTFY message from a paused run summary.

    Leads with the reason, shows this-run progress, and (for a session limit)
    the reset clause so the recipient knows when a resume is due. The
    unparseable variant is worded loudly — it signals a possible server-side
    format change that needs a human look."""
    reason = summary.get("pause_reason") or "unknown"
    progress = (
        f"{summary.get('topics_processed', 0)} topics this run, "
        f"{summary.get('chains_written', 0)} chains, "
        f"est ${summary.get('est_cost_usd', 0)}"
    )
    if reason == "session_limit":
        tail = f"resets {summary.get('reset_text') or '?'} — will resume after that."
    elif reason == "session_limit_unparseable":
        tail = (
            "⚠️ 429 with an UNRECOGNISED reset format (possible server change) — "
            f"raw={summary.get('reset_text')!r}. Manual check needed; auto-resume halted."
        )
    else:
        tail = "check the run log."
    return f"Metaforge generation paused: {reason}. {progress}. {tail}"


def _write_summary(summary: dict, path: str) -> None:
    """Write the run summary as JSON for an orchestrating wrapper to read
    (e.g. the autonomous resume loop, which needs pause_reason + reset_text).
    Drops the non-serialisable `tripwire` object."""
    serialisable = {k: v for k, v in summary.items() if k != "tripwire"}
    with open(path, "w") as f:
        json.dump(serialisable, f, indent=2)


def _default_ntfy_post(url: str, message: str, headers: dict) -> None:
    """Best-effort HTTP POST of `message` to an ntfy topic via stdlib urllib
    (no extra deps). Raises on transport failure; notify_ntfy swallows it."""
    import urllib.request
    req = urllib.request.Request(url, data=message.encode("utf-8"), headers=headers)
    with urllib.request.urlopen(req, timeout=10) as resp:  # nosec - operator-configured URL
        resp.read()


def notify_ntfy(message: str, *, post_fn=None) -> bool:
    """Post `message` to the ntfy channel from env (NTFY_URL + optional
    NTFY_TOKEN). Returns True on send, False when unconfigured or on any
    transport error. NEVER raises — a notification is advisory, and the token
    is kept out of the repo (loaded from the environment / a gitignored file)."""
    url = os.environ.get("NTFY_URL")
    if not url:
        log.warning("NTFY not configured (NTFY_URL unset); pause notification skipped")
        return False
    token = os.environ.get("NTFY_TOKEN")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    post = post_fn or _default_ntfy_post
    try:
        post(url, message, headers)
        return True
    except Exception as exc:  # noqa: BLE001 — advisory; a failed notify must not abort the run
        log.warning("NTFY pause notification failed (continuing): %s", exc)
        return False


def make_git_commit_fn(paths: list[str], message: str, cwd: str | None = None):
    def _commit():
        subprocess.run(["git", "add", *paths], check=True, cwd=cwd)
        # A batch that produced no new lines is a benign no-op, not an error —
        # avoid manufacturing empty commits that clutter the auto-commit trail.
        res = subprocess.run(["git", "commit", "-q", "-m", message], cwd=cwd,
                             capture_output=True, text=True)
        if res.returncode != 0 and "nothing to commit" not in (res.stdout + res.stderr):
            raise RuntimeError(f"git commit failed: {res.stderr.strip() or res.stdout.strip()}")
    return _commit


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Continuous chain.v1 metaphor-edge generation runner.")
    ap.add_argument("--topics", required=True, help="Vetted topics JSON ({topics:[{word,topic_synset_id,gloss}]}).")
    ap.add_argument("--output", required=True, help="chain.v1 JSONL output (appended; resumable).")
    ap.add_argument("--db", required=True, help="lexicon_v2.db for vehicle/head synset resolution.")
    ap.add_argument("--haiku-jsonl", default=None, help="Stored Haiku apt JSONL to reuse (no Haiku re-spend).")
    ap.add_argument("--anti-examples-json", default=None, help="Editor-judged bad paths (round>1 feedback).")
    ap.add_argument("--avoid-vehicles", default=None,
                    help="JSON list of over-used vehicles to soft-discourage (mode-collapse "
                         "diversity nudge). Absent → no AVOID block (current behaviour).")
    ap.add_argument("--proposer", default="sonnet_v1")
    ap.add_argument("--round", type=int, default=2, dest="round_num")
    ap.add_argument("--batch-size", type=int, default=20)
    ap.add_argument("--max-topics", type=int, default=None, help="Hard cap on topics this run (deterministic budget).")
    ap.add_argument("--max-cost-usd", type=float, default=None, help="Soft guard on estimated spend.")
    ap.add_argument("--sonnet-model", default="claude-sonnet-4-6")
    ap.add_argument("--haiku-model", default="claude-haiku-4-5-20251001")
    ap.add_argument("--provider", choices=["claude", "openai"], default="claude",
                    help="LLM backend. 'claude' = the claude CLI (default, unchanged); "
                         "'openai' = any OpenAI-compatible endpoint (OpenRouter/DeepInfra/GLM/local) "
                         "for the bulk haiku+sonnet calls — keeps generation off the Claude quota.")
    ap.add_argument("--base-url", default=None,
                    help="OpenAI-compatible base URL (with --provider openai), e.g. "
                         "https://openrouter.ai/api/v1 or https://api.deepinfra.com/v1/openai.")
    ap.add_argument("--api-key-env", default="OPENROUTER_API_KEY",
                    help="Env var holding the provider API key (with --provider openai).")
    ap.add_argument("--reasoning-off", action="store_true",
                    help="(openai) run reasoning models in fast mode (reasoning:{enabled:false}) — "
                         "halves latency + output cost. A bake-off variable, not a default.")
    ap.add_argument("--judge-model", default="claude-haiku-4-5-20251001")
    ap.add_argument("--judge-sample", type=int, default=3, help="topics sample-judged per batch (brake density).")
    ap.add_argument("--no-tripwire", action="store_true", help="Disable the live-rate tripwire.")
    ap.add_argument("--tw-window", type=int, default=40)
    ap.add_argument("--tw-min-judged", type=int, default=20)
    ap.add_argument("--tw-abs-floor", type=float, default=0.03,
                    help="COLLAPSE floor — well below the measured ~0.10 healthy live-rate, NOT a quality bar.")
    ap.add_argument("--tw-rel-drop", type=float, default=0.6)
    ap.add_argument("--tw-baseline-n", type=int, default=20)
    ap.add_argument("--autocommit-every", type=int, default=None, help="git-commit the output every N batches.")
    ap.add_argument("--summary-out", default=None,
                    help="Write the run summary JSON here (for the autonomous resume wrapper).")
    args = ap.parse_args()

    import sqlite3
    # Make a mis-targeted autocommit visible on day 1 of a multi-day run.
    if args.autocommit_every:
        try:
            branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                                    capture_output=True, text=True).stdout.strip()
            log.info("autocommit ON: branch=%s cwd=%s output=%s", branch, os.getcwd(), args.output)
        except Exception as exc:  # noqa: BLE001 — diagnostics must not block the run
            log.warning("could not resolve git branch for autocommit log: %s", exc)
    topics = load_vetted_topics(args.topics)
    conn = sqlite3.connect(args.db)
    try:
        resolve_synset = make_resolver(conn)
        resolve_by_gloss = make_gloss_resolver(conn)  # emit-the-sense gloss-match snap
        vec_gate_fn = make_vec_gate_fn(conn)           # chain.v2: admit OOV vec: vehicles
        avoid_vehicles = load_avoid_vehicles(args.avoid_vehicles)
        if avoid_vehicles:
            log.info("vehicle AVOID nudge ON: %d over-used vehicles", len(avoid_vehicles))
        # Provider selection: 'claude' (default) leaves the factories on the claude
        # CLI; 'openai' binds an OpenAI-compatible prompt_json (base_url+key) that
        # drives the bulk haiku+sonnet calls off the Claude quota.
        provider_pj = None
        if args.provider == "openai":
            import functools
            from openai_client import prompt_json as _oai_prompt_json
            api_key = os.environ.get(args.api_key_env)
            if not api_key:
                raise SystemExit(f"--provider openai: env {args.api_key_env} is empty/unset")
            if not args.base_url:
                raise SystemExit("--provider openai: --base-url is required")
            reasoning = {"enabled": False} if args.reasoning_off else None
            provider_pj = functools.partial(_oai_prompt_json, base_url=args.base_url,
                                             api_key=api_key, reasoning=reasoning)
            log.info("provider=openai base_url=%s reasoning_off=%s haiku=%s sonnet=%s",
                     args.base_url, args.reasoning_off, args.haiku_model, args.sonnet_model)
        if args.haiku_jsonl:
            # Stored Haiku reuse: the Haiku proposal prompt is never built, so the
            # AVOID nudge can only reach the Sonnet substitution prompt. WARN so the
            # operator knows proposer-side steering is inert under --haiku-jsonl.
            if avoid_vehicles:
                log.warning("--avoid-vehicles set WITH --haiku-jsonl: the Haiku proposer is "
                            "bypassed, so steering applies only to Sonnet substitution.")
            haiku_fn = make_stored_haiku_fn(args.haiku_jsonl)
            haiku_cost = 0.0
        else:
            haiku_fn = make_live_haiku_fn(args.haiku_model, avoid_vehicles, prompt_json=provider_pj)
            haiku_cost = HAIKU_COST_PER_TOPIC
        sonnet_fn = make_live_sonnet_fn(args.sonnet_model, prompt_json=provider_pj)

        tripwire = None if args.no_tripwire else mlr.new_tripwire(
            window=args.tw_window, min_judged=args.tw_min_judged, abs_floor=args.tw_abs_floor,
            rel_drop=args.tw_rel_drop, baseline_n=args.tw_baseline_n,
        )
        judge_fn = None if args.no_tripwire else make_judge_fn(args.judge_model)

        anti = None
        if args.anti_examples_json:
            from run_chain_spike import _load_anti_examples
            anti = _load_anti_examples(args.anti_examples_json)

        commit_fn = None
        if args.autocommit_every:
            commit_fn = make_git_commit_fn(
                [args.output], f"data(generation): autocommit chain.v1 round {args.round_num}"
            )

        summary = run(
            topics=topics, output_jsonl=args.output, haiku_fn=haiku_fn, sonnet_fn=sonnet_fn,
            resolve_synset=resolve_synset, resolve_by_gloss=resolve_by_gloss,
            vec_gate_fn=vec_gate_fn,
            proposer=args.proposer, round_num=args.round_num,
            batch_size=args.batch_size, max_topics=args.max_topics, max_cost_usd=args.max_cost_usd,
            tripwire=tripwire, judge_fn=judge_fn, judge_sample=args.judge_sample, anti_examples=anti,
            avoid_vehicles=avoid_vehicles,
            autocommit_every=args.autocommit_every, commit_fn=commit_fn,
            notify_fn=lambda s: notify_ntfy(format_pause_message(s)),
            haiku_cost_per_topic=haiku_cost,
        )
    finally:
        conn.close()

    if args.summary_out:
        _write_summary(summary, args.summary_out)
    summary.pop("tripwire", None)
    print(json.dumps(summary, indent=2))
    # Exit non-zero on the LOUD pause (unrecognised 429 reset format) so a
    # server-side change surfaces to the shell/cron, not just the log.
    return 2 if summary.get("pause_reason") == "session_limit_unparseable" else 0


if __name__ == "__main__":
    raise SystemExit(main())
