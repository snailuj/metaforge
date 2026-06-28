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

def proxy_live_rate(rows, sample_n, model="claude-haiku-4-5-20251001"):
    """Conservative zero-FP proxy live-rate over a sample (reuses mlr judge)."""
    import metaphor_live_rate as mlr
    import random
    sample = rows if len(rows) <= sample_n else random.sample(rows, sample_n)
    live = 0
    for rec in sample:
        try:
            if mlr.judge_chain(rec, model=model):
                live += 1
        except Exception as exc:  # noqa: BLE001 — a judge failure must not abort scoring
            print(f"[bakeoff] live-judge failed (skipped): {exc}", file=sys.stderr)
    return round(live / len(sample), 3) if sample else 0.0


_GLOSS_JUDGE = (
    "You are auditing word-sense glosses. For the head word '{head}' as used in the "
    "phrase '{phrase}', is this gloss an ACCURATE definition of a real sense of that "
    "word that fits the phrase?\nGloss: {gloss}\n"
    "Answer STRICT JSON: {{\"accurate\": true|false}}"
)


def gloss_accuracy(rows, sample_n, judge_model="claude-haiku-4-5-20251001"):
    """Fraction of sampled nodes whose emitted gloss is a real, fitting sense."""
    import random
    from claude_client import prompt_json
    nodes = [s for r in rows for s in r["chain"] if s.get("gloss")]
    sample = nodes if len(nodes) <= sample_n else random.sample(nodes, sample_n)
    ok = 0
    for s in sample:
        try:
            v = prompt_json(_GLOSS_JUDGE.format(head=s.get("head", ""), phrase=s.get("phrase", ""),
                                                gloss=s["gloss"]), model=judge_model, max_retries=2)
            ok += 1 if isinstance(v, dict) and v.get("accurate") else 0
        except Exception as exc:  # noqa: BLE001
            print(f"[bakeoff] gloss-judge failed (skipped): {exc}", file=sys.stderr)
    return round(ok / len(sample), 3) if sample else 0.0


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


def _score_one(name, path, wall, args):
    rows = load_rows(path)
    res = {"name": name, "path": str(path), "wall_clock_s": wall, "metrics": summarise_model(rows)}
    if args.liveness:
        res["live_rate"] = proxy_live_rate(rows, args.liveness)
    if args.gloss_judge:
        res["gloss_accuracy"] = gloss_accuracy(rows, args.gloss_judge)
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
    results = [_score_one(name, path, manifest.get("wall_clock_s", {}).get(name, "-"), args)
               for name, path in manifest["outputs"].items()]
    card = render_scorecard(results)
    (Path(out_dir) / "scorecard.md").write_text(card + "\n")
    (Path(out_dir) / "scorecard.json").write_text(json.dumps(results, indent=2))
    print("\n" + card + "\n")
    print(f"[bakeoff] scorecard -> {out_dir}/scorecard.md")


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
    r.add_argument("--gloss-judge", type=int, default=0, help="Sample N nodes for gloss accuracy (costs Claude calls).")
    r.set_defaults(func=cmd_run)

    s = sub.add_parser("score", help="(re)score from a manifest")
    s.add_argument("--manifest", required=True)
    s.add_argument("--liveness", type=int, default=0)
    s.add_argument("--gloss-judge", type=int, default=0)
    s.set_defaults(func=cmd_score)

    args = ap.parse_args()
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
