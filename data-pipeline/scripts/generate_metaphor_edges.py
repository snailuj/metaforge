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
from models import ChainRecord, compute_chain_signature  # noqa: E402

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
) -> list[dict]:
    """Explode a Sonnet response into validated chain.v1 records.

    Endpoints are FORCED canonical — chain[0] := (topic, topic, topic_synset_id)
    and chain[-1] := (vehicle, vehicle, vehicle_synset_id) — so the records
    satisfy ChainRecord's endpoint-canonicalisation invariant regardless of how
    the model phrased its first/last step. The signature is computed over the
    FINAL phrases (what a grader sees), so it matches across runs that produce
    the same walk. A vehicle whose lemma does not resolve to a synset is
    skipped (a chain.v1 record requires a vehicle_synset_id).
    """
    out: list[dict] = []
    seen_sigs: set[str] = set()
    for v in sonnet_resp.get("vehicles", []) if isinstance(sonnet_resp, dict) else []:
        if not isinstance(v, dict):
            continue
        vehicle = v.get("vehicle")
        if not isinstance(vehicle, str) or not vehicle.strip():
            continue
        vehicle = vehicle.strip()
        vehicle_synset_id = resolve_synset(vehicle)
        if not vehicle_synset_id:
            log.info("skip vehicle %r for topic %r: no synset", vehicle, topic)
            continue
        if vehicle_synset_id == topic_synset_id:
            # self-metaphor (topic echoed as vehicle, or a lemma resolving back to
            # the topic synset) is not a metaphor — drop it, don't grade it.
            log.info("skip self-metaphor %r for topic %r", vehicle, topic)
            continue

        raw_chain = v.get("chain", []) if isinstance(v.get("chain"), list) else []
        steps = [{"phrase": topic, "head": topic, "synset_id": topic_synset_id}]
        for s in raw_chain[1:-1]:  # intermediates only; endpoints are forced
            if not isinstance(s, dict):
                continue
            phrase = s.get("phrase")
            if not isinstance(phrase, str) or not phrase.strip():
                continue
            phrase = phrase.strip()
            head = s.get("head")
            head = head.strip() if isinstance(head, str) and head.strip() else phrase
            sid = resolve_synset(head) or resolve_synset(phrase)
            steps.append({"phrase": phrase, "head": head, "synset_id": sid})
        steps.append({"phrase": vehicle, "head": vehicle, "synset_id": vehicle_synset_id})

        phrases = [s["phrase"] for s in steps]
        signature = compute_chain_signature(proposer, phrases)
        if signature in seen_sigs:
            # identical walk emitted twice in one response -> one card, not two
            # (chain_signature is the grading dedup/verdict key).
            continue
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
    proposer: str = "sonnet_v1",
    round_num: int = 2,
    batch_size: int = 20,
    max_topics: int | None = None,
    max_cost_usd: float | None = None,
    tripwire=None,
    judge_fn=None,
    judge_sample: int = 2,
    anti_examples: list[dict] | None = None,
    now_fn=None,
    autocommit_every: int | None = None,
    commit_fn=None,
    log_fn=None,
    haiku_cost_per_topic: float = HAIKU_COST_PER_TOPIC,
    sonnet_cost_per_topic: float = SONNET_COST_PER_TOPIC,
) -> dict:
    """Generate chains for `topics`, appending chain.v1 JSONL to output_jsonl.

    Returns a summary dict. Pauses (without raising) when the tripwire trips or
    the estimated cost guard is hit, leaving a resumable output file behind.
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

    for bstart in range(0, len(pending), batch_size):
        batch = pending[bstart:bstart + batch_size]
        batch_recs: list[dict] = []
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
                    prompt = build_prompt(word, gloss, metaphors, anti_examples or None)
                    try:
                        sresp = sonnet_fn(prompt)
                    finally:
                        est_cost += sonnet_cost_per_topic
                    recs = chain_records_from_sonnet(
                        topic=word, topic_synset_id=tsid, gloss=gloss, sonnet_resp=sresp,
                        proposer=proposer, round_num=round_num, generated_at=now_fn(),
                        resolve_synset=resolve_synset,
                    )
                else:
                    log.info("skip %s: no Haiku metaphors", word)
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
                # permanently-empty topic is never re-billed on resume.
                _append_attempted(output_jsonl, tsid)

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
            elif batch:
                # attempted topics but ZERO usable records IS a liveness collapse
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

    return {
        "topics_processed": topics_processed,
        "chains_written": chains_written,
        "batches": batches,
        "est_cost_usd": round(est_cost, 4),
        "paused": paused,
        "pause_reason": pause_reason,
        "tripwire": tripwire,
    }


# ---------------------------------------------------------------------------
# Production wiring (thin; exercised by the small validation run, not unit tests)
# ---------------------------------------------------------------------------

def make_live_sonnet_fn(model: str):
    from claude_client import prompt_json
    return lambda prompt: prompt_json(prompt, model=model)


def make_live_haiku_fn(model: str):
    from claude_client import prompt_json
    from metaphor_spike_1a import build_apt_prompt
    return lambda word, gloss: prompt_json(build_apt_prompt(word, gloss), model=model)


def make_stored_haiku_fn(haiku_jsonl: str):
    """Reuse a stored Haiku apt JSONL (no Haiku re-spend) — keyed by topic."""
    from run_chain_spike import _load_jsonl
    by_topic = {d["topic"]: d for d in _load_jsonl(haiku_jsonl) if isinstance(d, dict) and d.get("topic")}
    return lambda word, gloss: by_topic.get(word, {"topic": word, "metaphors": []})


def make_resolver(conn):
    from metaphor_graph import lookup_primary_synset
    return lambda w: lookup_primary_synset(conn, w)


def make_judge_fn(model: str):
    return lambda rec: mlr.judge_chain(rec, model=model)


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
    ap.add_argument("--proposer", default="sonnet_v1")
    ap.add_argument("--round", type=int, default=2, dest="round_num")
    ap.add_argument("--batch-size", type=int, default=20)
    ap.add_argument("--max-topics", type=int, default=None, help="Hard cap on topics this run (deterministic budget).")
    ap.add_argument("--max-cost-usd", type=float, default=None, help="Soft guard on estimated spend.")
    ap.add_argument("--sonnet-model", default="claude-sonnet-4-6")
    ap.add_argument("--haiku-model", default="claude-haiku-4-5-20251001")
    ap.add_argument("--judge-model", default="claude-haiku-4-5-20251001")
    ap.add_argument("--judge-sample", type=int, default=3, help="topics sample-judged per batch (brake density).")
    ap.add_argument("--no-tripwire", action="store_true", help="Disable the live-rate tripwire.")
    ap.add_argument("--tw-window", type=int, default=30)
    ap.add_argument("--tw-min-judged", type=int, default=15)
    ap.add_argument("--tw-abs-floor", type=float, default=0.08,
                    help="collapse floor — set BELOW the measured healthy live-rate, not as a quality bar.")
    ap.add_argument("--tw-rel-drop", type=float, default=0.4)
    ap.add_argument("--tw-baseline-n", type=int, default=15)
    ap.add_argument("--autocommit-every", type=int, default=None, help="git-commit the output every N batches.")
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
        if args.haiku_jsonl:
            haiku_fn = make_stored_haiku_fn(args.haiku_jsonl)
            haiku_cost = 0.0
        else:
            haiku_fn = make_live_haiku_fn(args.haiku_model)
            haiku_cost = HAIKU_COST_PER_TOPIC
        sonnet_fn = make_live_sonnet_fn(args.sonnet_model)

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
            resolve_synset=resolve_synset, proposer=args.proposer, round_num=args.round_num,
            batch_size=args.batch_size, max_topics=args.max_topics, max_cost_usd=args.max_cost_usd,
            tripwire=tripwire, judge_fn=judge_fn, judge_sample=args.judge_sample, anti_examples=anti,
            autocommit_every=args.autocommit_every, commit_fn=commit_fn,
            haiku_cost_per_topic=haiku_cost,
        )
    finally:
        conn.close()

    summary.pop("tripwire", None)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
