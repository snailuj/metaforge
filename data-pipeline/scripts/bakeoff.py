#!/usr/bin/env python3
"""Bake-off harness: run the SAME topics through several generation backends and
score them head-to-head, so we choose a farm-out model on data, not vibes.

Each candidate is the existing generation runner (`generate_metaphor_edges.py`)
pointed at a different backend via `--provider/--base-url/--{sonnet,haiku}-model`
(OpenRouter / DeepInfra / GLM / local), with the Claude run as the baseline.

Two entrypoints:
  run   — generate per candidate over a topics subset (+ reuse an existing
          Claude baseline file, no re-spend), write a manifest, then score.
  score — (re)build the markdown scorecard from a manifest.

Pure pieces (`build_candidate_cmd`, `summarise_model`) are unit-tested; the
subprocess orchestration is thin glue. Optional, spend-gated deeper metrics:
  --liveness N    proxy live-rate (mlr conservative judge) over N sampled chains
  --gloss-judge N Claude-judged gloss sense-accuracy over N sampled nodes
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent


# --- pure helpers (unit-tested) ---------------------------------------------

def build_candidate_cmd(cand, *, topics, db, out, summary, python, runner, max_topics):
    """argv to run one candidate through the generation runner. A candidate is
    {name, model, [provider], [base_url], [api_key_env]}; default provider=openai."""
    provider = cand.get("provider", "openai")
    model = cand["model"]
    cmd = [python, runner, "--topics", topics, "--output", out, "--db", db,
           "--round", "3", "--batch-size", "10", "--no-tripwire",
           "--max-topics", str(max_topics), "--summary-out", summary,
           "--provider", provider, "--sonnet-model", model, "--haiku-model", model]
    if provider == "openai":
        cmd += ["--base-url", cand["base_url"],
                "--api-key-env", cand.get("api_key_env", "OPENROUTER_API_KEY")]
        if cand.get("reasoning") is False:   # run the reasoning model in fast mode
            cmd += ["--reasoning-off"]
    return cmd


def summarise_model(rows):
    """Structural scorecard metrics for one model's chain.v1 output."""
    chains = len(rows)
    if not chains:
        return {"chains": 0, "topics": 0, "vehicles_per_topic": 0, "distinct_vehicles": 0,
                "vehicle_diversity": 0, "gloss_coverage": 0, "mean_chain_len": 0,
                "self_metaphor": 0, "zero_gloss_chains": 0}
    topics = {r["topic_synset_id"] for r in rows}
    nodes = [s for r in rows for s in r["chain"]]
    glossed = sum(1 for s in nodes if s.get("gloss"))
    vehicles = [r["vehicle"] for r in rows]
    return {
        "chains": chains,
        "topics": len(topics),
        "vehicles_per_topic": round(chains / len(topics), 2),
        "distinct_vehicles": len(set(vehicles)),
        "vehicle_diversity": round(len(set(vehicles)) / chains, 3),
        "gloss_coverage": round(glossed / len(nodes), 3),
        "mean_chain_len": round(sum(len(r["chain"]) for r in rows) / chains, 2),
        "self_metaphor": sum(1 for r in rows if r.get("topic_synset_id") == r.get("vehicle_synset_id")),
        "zero_gloss_chains": sum(1 for r in rows if not all(s.get("gloss") for s in r["chain"])),
        "top_vehicles": Counter(vehicles).most_common(5),
    }


def load_rows(path):
    p = Path(path)
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def subset_baseline(baseline_rows, topic_ids):
    """The baseline (existing Claude run) filtered to the bake-off's topics."""
    ids = set(topic_ids)
    return [r for r in baseline_rows if str(r.get("topic_synset_id")) in ids]


# --- optional, spend-gated deep metrics -------------------------------------

def judge_slug(model):
    """Filesystem-safe slug of a judge model id, so different judges keep separate
    checkpoint files and never silently return each other's cached verdicts."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", model)


def _load_checkpoint(path):
    """Map of chain-key -> checkpoint record, for resumable judging. Tolerates a
    truncated final line (process killed mid-flush) by skipping unparseable rows."""
    done = {}
    if not path:
        return done
    p = Path(path)
    if p.exists():
        for line in p.read_text().splitlines():
            try:
                rec = json.loads(line)
                done[rec["key"]] = rec
            except (json.JSONDecodeError, KeyError, TypeError):
                pass
    return done


def proxy_live_rate(rows, sample_chains, prompt_fn=None, model="anthropic/claude-haiku-4.5",
                    label="", checkpoint_path=None):
    """Conservative zero-FP proxy live-rate over a deterministic chain sample.

    Reuses the calibrated `metaphor_live_rate` Haiku proxy judge — it UNDER-calls
    `live`, so a `live` signal is trustworthy (a healthy run sits low, ~0.08-0.14).
    `prompt_fn(prompt, model=...)` is injected so the judge runs over fast,
    off-subscription HTTP (OpenRouter) and is unit-testable; a None prompt_fn falls
    back to the claude_client CLI inside judge_chain. CHECKPOINTED + RESUMABLE per
    chain (keyed by chain_signature): a kill/crash never re-judges a done chain.
    A judge that errors returns ok=False and is SKIPPED (never counted as dead) so
    transient API failures cannot deflate the rate. Same deterministic sample as the
    gloss judge, so liveness and gloss-accuracy score the SAME chains."""
    import metaphor_live_rate as mlr
    usable = [r for r in rows if r.get("chain")]
    sample = sorted(usable, key=lambda r: _chain_key(label, r))[:sample_chains]

    done = _load_checkpoint(checkpoint_path)
    cp = Path(checkpoint_path) if checkpoint_path else None
    fh = cp.open("a") if cp else None
    live = total = 0
    try:
        for i, r in enumerate(sample, 1):
            k = _chain_key(label, r)
            if k in done:
                v = done[k]["live"]
            else:
                res = mlr.judge_chain(r, prompt_fn=prompt_fn, model=model)
                if not res.get("ok"):
                    print(f"[bakeoff] {label} live-judge skipped: {res.get('error')}", file=sys.stderr)
                    continue
                v = 1 if res.get("verdict") == "live" else 0
                if fh:
                    fh.write(json.dumps({"key": k, "live": v}) + "\n")
                    fh.flush()
                done[k] = {"live": v}
            live += v
            total += 1
            if i % 5 == 0 or i == len(sample):
                print(f"[bakeoff] {label} live {i}/{len(sample)} chains, live={live}/{total}", flush=True)
    finally:
        if fh:
            fh.close()
    return round(live / total, 3) if total else 0.0


_CHAIN_GLOSS_JUDGE = (
    "A metaphor chain moves step by step from a TOPIC to a VEHICLE. Each hop must be "
    "coherent, so every node's word is meant in ONE specific sense — the sense that makes "
    "the step from the previous node work. Each node lists a `gloss` stating its intended sense.\n\n"
    "Judge whether each node's gloss captures the sense the chain ACTUALLY INTENDS at that "
    "position, read in the context of the surrounding nodes. Mark `accurate:false` if the gloss "
    "describes a real but DIFFERENT sense of the word than the chain uses here, or is vague or "
    "incorrect. A gloss that fits some OTHER meaning of a polysemous word — but not the one this "
    "chain needs — is WRONG. Only `accurate:true` when it matches the intended, in-context sense.\n\n"
    "Chain (TOPIC → VEHICLE):\n{chain_block}\n\n"
    "Respond with STRICT JSON only, one entry per node in order:\n"
    '{{"nodes": [{{"head": "<head>", "accurate": true|false}}]}}'
)


def _chain_key(label, r):
    import hashlib
    basis = r.get("chain_signature") or "|".join(
        f"{n.get('head', '')}:{n.get('gloss', '')}" for n in r["chain"])
    return hashlib.sha1(f"{label}|{basis}".encode("utf-8")).hexdigest()[:16]


def _render_chain(r):
    head = f"TOPIC={r.get('topic', '?')}  VEHICLE={r.get('vehicle', '?')}"
    lines = [f"  {i+1}. \"{n.get('phrase', '')}\" (head: {n.get('head', '')}) — gloss: {n.get('gloss', '')}"
             for i, n in enumerate(r["chain"])]
    return head + "\n" + "\n".join(lines)


def gloss_accuracy(rows, sample_chains, prompt_json, judge_model, label="", checkpoint_path=None):
    """Fraction of nodes whose gloss matches the IN-CONTEXT intended sense.

    Judges each gloss inside its WHOLE chain, not in isolation: a polysemous
    single-lemma node passes a node-only check as long as the gloss matches any
    meaning ("not garbage"), but the chain fixes which sense is intended, so the
    gloss must match THAT one. We sample whole chains (one judge call per chain →
    per-node verdicts) and pool nodes across chains.

    `prompt_json` is injected for fast HTTP judging. CHECKPOINTED + RESUMABLE per
    chain (keyed by chain_signature): a kill/crash/fix never re-judges a done chain.
    Deterministic sampling so resume hits the same chains. Skipped (failed) chains
    don't count. Logs progress per chain."""
    usable = [r for r in rows if r.get("chain")]
    sample = sorted(usable, key=lambda r: _chain_key(label, r))[:sample_chains]

    done = _load_checkpoint(checkpoint_path)
    cp = Path(checkpoint_path) if checkpoint_path else None

    fh = cp.open("a") if cp else None
    ok = total = 0
    try:
        for i, r in enumerate(sample, 1):
            k = _chain_key(label, r)
            if k in done:
                a, t = done[k]["acc"], done[k]["tot"]
            else:
                try:
                    resp = prompt_json(_CHAIN_GLOSS_JUDGE.format(chain_block=_render_chain(r)),
                                       model=judge_model, max_retries=2)
                    verdicts = resp.get("nodes", []) if isinstance(resp, dict) else []
                    t = len(r["chain"])
                    a = sum(1 for v in verdicts[:t] if isinstance(v, dict) and v.get("accurate"))
                except Exception as exc:  # noqa: BLE001 — a skip must not abort or deflate
                    print(f"[bakeoff] {label} chain-gloss-judge failed (skipped): {exc}", file=sys.stderr)
                    continue
                if fh:
                    fh.write(json.dumps({"key": k, "acc": a, "tot": t}) + "\n")
                    fh.flush()
                done[k] = {"acc": a, "tot": t}
            ok += a
            total += t
            if i % 5 == 0 or i == len(sample):
                print(f"[bakeoff] {label} chain-gloss {i}/{len(sample)} chains, "
                      f"nodes ok={ok}/{total}", flush=True)
    finally:
        if fh:
            fh.close()
    return round(ok / total, 3) if total else 0.0


def build_judge_pj(args):
    """The prompt_json the judge uses. openai → fast HTTP (OpenRouter), off the
    Claude subscription; claude → the heavyweight CLI (slow, only if no key)."""
    if getattr(args, "judge_provider", "openai") == "openai":
        import functools
        from openai_client import prompt_json as oai
        key = os.environ.get(args.judge_api_key_env)
        if not key:
            raise SystemExit(f"judge: env {args.judge_api_key_env} unset (needed for openai judge)")
        # Cap output: a gloss/liveness verdict is tiny, but OpenRouter reserves credit
        # for the full max_tokens, so an uncapped call 402s once the balance runs low.
        return functools.partial(oai, base_url=args.judge_base_url, api_key=key,
                                 reasoning={"enabled": False}, max_tokens=512)
    from claude_client import prompt_json as cc
    return cc


def build_liveness_pj(args):
    """A `(prompt, model)` judge callable for the liveness proxy — same fast
    OpenRouter transport as the gloss judge (reasoning off, conservative retries),
    off the Claude subscription. judge_chain calls it as prompt_fn(prompt, model=…)."""
    import functools
    from openai_client import prompt_json as oai
    key = os.environ.get(args.judge_api_key_env)
    if not key:
        raise SystemExit(f"liveness: env {args.judge_api_key_env} unset (needed for the live judge)")
    call = functools.partial(oai, base_url=args.judge_base_url, api_key=key,
                             reasoning={"enabled": False}, max_retries=2, max_tokens=256)
    return lambda prompt, model: call(prompt, model=model)


# --- orchestration (glue) ----------------------------------------------------

def render_scorecard(results):
    """results: list of {name, wall_clock_s, metrics, [live_rate], [gloss_accuracy]}."""
    cols = [("model", "name"), ("chains", None), ("topics", None),
            ("veh/topic", "vehicles_per_topic"), ("distinct_veh", "distinct_vehicles"),
            ("diversity", "vehicle_diversity"), ("gloss_cov", "gloss_coverage"),
            ("zero_gloss", "zero_gloss_chains"), ("chain_len", "mean_chain_len"),
            ("self_met", "self_metaphor")]
    head = ["model", "chains", "topics", "veh/topic", "distinct_veh", "diversity",
            "gloss_cov", "zero_gloss", "chain_len", "self_met", "wall_s", "live_rate", "gloss_acc"]
    lines = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    for r in results:
        m = r["metrics"]
        row = [r["name"], m["chains"], m["topics"], m["vehicles_per_topic"],
               m["distinct_vehicles"], m["vehicle_diversity"], m["gloss_coverage"],
               m["zero_gloss_chains"], m["mean_chain_len"], m["self_metaphor"],
               r.get("wall_clock_s", "-"), r.get("live_rate", "-"), r.get("gloss_accuracy", "-")]
        lines.append("| " + " | ".join(str(x) for x in row) + " |")
    return "\n".join(lines)


def _score_one(name, path, wall, args, judge_pj=None, live_pj=None, out_dir=None):
    rows = load_rows(path)
    res = {"name": name, "path": str(path), "wall_clock_s": wall, "metrics": summarise_model(rows)}
    if args.liveness:
        # checkpoint keyed by the LIVENESS model (separate from the gloss judge) so the
        # two judges never share a cache and a model swap re-judges instead of resuming.
        cp = str(Path(out_dir) / f"{name}.{judge_slug(args.liveness_model)}.liverate.jsonl") if out_dir else None
        res["live_rate"] = proxy_live_rate(rows, args.liveness, prompt_fn=live_pj,
                                           model=args.liveness_model, label=name, checkpoint_path=cp)
    if args.gloss_judge:
        cp = str(Path(out_dir) / f"{name}.{judge_slug(args.judge_model)}.glossjudge.jsonl") if out_dir else None
        res["gloss_accuracy"] = gloss_accuracy(rows, args.gloss_judge, judge_pj,
                                               args.judge_model, label=name, checkpoint_path=cp)
    return res


def cmd_run(args):
    candidates = json.loads(Path(args.candidates).read_text())
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    topic_ids = [str(t["topic_synset_id"]) for t in json.loads(Path(args.topics).read_text())["topics"]]
    manifest = {"topics": args.topics, "outputs": {}, "wall_clock_s": {}}

    # Run candidates concurrently but CAPPED — each process is ~164MB and this can
    # share an underpowered, live-serving box, so a bounded queue protects the host
    # (and the OOM killer protects the live site) while still collapsing wall-clock.
    queue = list(candidates)
    running = {}  # name -> (out, t0, proc, logf)

    def launch(cand):
        name = cand["name"]
        out = str(out_dir / f"{name}.jsonl")
        summ = str(out_dir / f"{name}.summary.json")
        cmd = build_candidate_cmd(cand, topics=args.topics, db=args.db, out=out, summary=summ,
                                  python=sys.executable, runner=str(HERE / "generate_metaphor_edges.py"),
                                  max_topics=args.max_topics)
        print(f"[bakeoff] launching {name}: {cand['model']} ({len(running) + 1} running)", flush=True)
        logf = open(out_dir / f"{name}.run.log", "w")
        running[name] = (out, time.monotonic(), subprocess.Popen(cmd, stdout=logf, stderr=subprocess.STDOUT), logf)

    while queue or running:
        while queue and len(running) < args.max_parallel:
            launch(queue.pop(0))
        for name in list(running):
            out, t0, proc, logf = running[name]
            if proc.poll() is None:
                continue
            logf.close()
            manifest["wall_clock_s"][name] = round(time.monotonic() - t0, 1)
            manifest["outputs"][name] = out
            print(f"[bakeoff] {name} done rc={proc.returncode} chains={len(load_rows(out))} "
                  f"({manifest['wall_clock_s'][name]}s)", file=sys.stderr, flush=True)
            del running[name]
        if queue or running:
            time.sleep(3)

    if args.baseline_chains:
        base_rows = subset_baseline(load_rows(args.baseline_chains), topic_ids)
        bpath = str(out_dir / f"{args.baseline_name}.jsonl")
        Path(bpath).write_text("\n".join(json.dumps(r) for r in base_rows) + ("\n" if base_rows else ""))
        manifest["outputs"][args.baseline_name] = bpath
        print(f"[bakeoff] baseline {args.baseline_name}: {len(base_rows)} chains for the {len(topic_ids)} bake-off topics")

    Path(out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    _emit_scorecard(manifest, out_dir, args)


def cmd_score(args):
    manifest = json.loads(Path(args.manifest).read_text())
    _emit_scorecard(manifest, Path(args.manifest).parent, args)


def _emit_scorecard(manifest, out_dir, args):
    judge_pj = build_judge_pj(args) if args.gloss_judge else None
    live_pj = build_liveness_pj(args) if args.liveness else None
    results = [_score_one(name, path, manifest.get("wall_clock_s", {}).get(name, "-"),
                          args, judge_pj, live_pj, out_dir=out_dir)
               for name, path in manifest["outputs"].items()]
    card = render_scorecard(results)
    (Path(out_dir) / "scorecard.md").write_text(card + "\n")
    (Path(out_dir) / "scorecard.json").write_text(json.dumps(results, indent=2))
    print("\n" + card + "\n")
    print(f"[bakeoff] scorecard -> {out_dir}/scorecard.md")


def _add_judge_args(p):
    """Judge transport — defaults to fast HTTP Haiku via OpenRouter (off the Claude
    subscription, ~1-2s/call) rather than the heavyweight `claude -p` CLI."""
    p.add_argument("--judge-provider", choices=["openai", "claude"], default="openai")
    p.add_argument("--judge-base-url", default="https://openrouter.ai/api/v1")
    p.add_argument("--judge-model", default="anthropic/claude-haiku-4.5")
    p.add_argument("--judge-api-key-env", default="OPENROUTER_API_KEY")
    # The liveness proxy is a SEPARATE judge from --judge-model: it's the calibrated
    # conservative Haiku live/dead monitor, so keep it on Haiku unless re-calibrated.
    p.add_argument("--liveness-model", default="anthropic/claude-haiku-4.5")


def main() -> int:
    ap = argparse.ArgumentParser(description="Generation-model bake-off.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run candidates over a topics subset + score")
    r.add_argument("--candidates", required=True, help="JSON list of {name,model,base_url,...}.")
    r.add_argument("--topics", required=True)
    r.add_argument("--db", required=True)
    r.add_argument("--out-dir", required=True)
    r.add_argument("--max-topics", type=int, default=50)
    r.add_argument("--max-parallel", type=int, default=3,
                   help="Max concurrent candidate processes (~164MB each) — keep low on a "
                        "small/live-serving host to avoid OOM.")
    r.add_argument("--baseline-chains", default=None, help="Existing Claude chains to reuse as baseline.")
    r.add_argument("--baseline-name", default="claude")
    r.add_argument("--liveness", type=int, default=0, help="Sample N chains for proxy live-rate (costs Claude calls).")
    r.add_argument("--gloss-judge", type=int, default=0, help="Sample N nodes for gloss accuracy.")
    _add_judge_args(r)
    r.set_defaults(func=cmd_run)

    s = sub.add_parser("score", help="(re)score from a manifest")
    s.add_argument("--manifest", required=True)
    s.add_argument("--liveness", type=int, default=0)
    s.add_argument("--gloss-judge", type=int, default=0)
    _add_judge_args(s)
    s.set_defaults(func=cmd_score)

    args = ap.parse_args()
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
