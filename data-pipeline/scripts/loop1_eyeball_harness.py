#!/usr/bin/env python3
"""Loop-1 cumulative eyeball: Go-suggest candidate-gen + Python loop-config rescore.

For each topic in ``loop1_eyeball_topics.json``:
  1. Query Go ``/forge/suggest?word=<lemma>&limit=K`` against the loop branch
     DB. Capture candidate set, Go cascade scores, and the source_synset_id
     Go resolved the lemma to.
  2. Re-score each candidate via Python ``evaluate_cascade_pair`` using
     PRODUCTION_CASCADE_CONFIG (which inherits the loop-tuned dataclass
     defaults: d_cap=0.68, rerank_exponent=0.75, concreteness_bonus_coef=0.002).
  3. Emit a Markdown report with one section per topic, showing:
     - Topic + POS + gloss + (resolved synset_id)
     - Side-by-side: Go top-K rank vs Python-loop top-K rank, scored.
     - Diff column: rank delta (Python_rank - Go_rank), so swaps stand out.

Outputs:
  - data-pipeline/output/loop1_eyeball_results.json  (raw)
  - data-pipeline/output/loop1_eyeball_report.md     (human eyeball doc)
"""

from __future__ import annotations

import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "data-pipeline" / "scripts"))

from evaluate_cascade import evaluate_cascade_pair  # noqa: E402
from evaluate_loop_harness import PRODUCTION_CASCADE_CONFIG  # noqa: E402

DB_PATH = REPO_ROOT / "data-pipeline" / "output" / "lexicon_v2.db"
BINARY = REPO_ROOT / "api" / "metaforge"
TOPICS_JSON = REPO_ROOT / "data-pipeline" / "output" / "loop1_eyeball_topics.json"
RESULTS_JSON = REPO_ROOT / "data-pipeline" / "output" / "loop1_eyeball_results.json"
REPORT_MD = REPO_ROOT / "data-pipeline" / "output" / "loop1_eyeball_report.md"

PORT = 9192
LIMIT = 20  # candidates per topic
TOP_K_DISPLAY = 10  # Markdown shows top-K only


def start_api() -> subprocess.Popen:
    env = os.environ.copy()
    env["METAFORGE_FORGE_CASCADE"] = "1"
    env["METAFORGE_FORGE_CANDIDATES"] = "union"
    args = [str(BINARY), "--db", str(DB_PATH), "--port", str(PORT), "--cascade"]
    proc = subprocess.Popen(args, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    base = f"http://127.0.0.1:{PORT}"
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            if requests.get(f"{base}/health", timeout=0.5).ok:
                return proc
        except requests.RequestException:
            time.sleep(0.1)
    proc.kill()
    out, err = proc.communicate(timeout=2)
    raise RuntimeError(f"API failed to start:\nstdout: {out[-500:]!r}\nstderr: {err[-500:]!r}")


def stop_api(proc: subprocess.Popen) -> None:
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=2)


def fetch_suggestions(base_url: str, lemma: str, limit: int) -> dict | None:
    try:
        r = requests.get(
            f"{base_url}/forge/suggest",
            params={"word": lemma, "limit": limit},
            timeout=15,
        )
    except requests.RequestException as e:
        print(f"  WARN: {lemma!r} request failed: {e}", file=sys.stderr)
        return None
    if r.status_code != 200:
        print(f"  WARN: {lemma!r} status={r.status_code} body={r.text[:200]!r}", file=sys.stderr)
        return None
    return r.json()


def score_topic(conn: sqlite3.Connection, topic: dict, base_url: str) -> dict:
    """Returns dict with raw Go output + Python rescore for each candidate."""
    body = fetch_suggestions(base_url, topic["lemma"], LIMIT)
    if body is None:
        return {"topic": topic, "error": "fetch_failed", "candidates": []}

    suggestions = body.get("suggestions", [])
    if not suggestions:
        # Diagnostic: pull topic concreteness so the report can hint at why
        # nothing came back. Most common cause is a high topic concreteness
        # leaving no headroom for vehicles above the +1.0 signed-delta gate.
        cur = conn.cursor()
        cur.execute(
            "SELECT score FROM synset_concreteness WHERE synset_id = ?",
            (topic["synset_id"],),
        )
        row = cur.fetchone()
        topic_c = row[0] if row else None
        return {
            "topic": topic,
            "error": "no_suggestions",
            "topic_concreteness": topic_c,
            "candidates": [],
        }

    # Go resolved the lemma to some source_synset_id. Use that as the cascade
    # topic — matches what the API actually scored against.
    source_synset_id = suggestions[0].get("source_synset_id") or topic["synset_id"]

    candidates = []
    for s in suggestions:
        vehicle_id = s.get("synset_id")
        if not vehicle_id:
            continue
        go_final = s.get("final_score")
        go_status = s.get("cascade_status", "")
        # Python re-score with loop config.
        py = evaluate_cascade_pair(
            conn=conn,
            synset_id_topic=source_synset_id,
            synset_id_vehicle=vehicle_id,
            config=PRODUCTION_CASCADE_CONFIG,
        )
        candidates.append({
            "vehicle_synset_id": vehicle_id,
            "vehicle_word": s.get("word"),
            "vehicle_definition": s.get("definition", ""),
            "go_final_score": go_final,
            "go_cascade_status": go_status,
            "go_cosine_distance": s.get("cosine_distance"),
            "py_final_score": py.final_score,
            "py_status": py.status,
            "py_gate_passed": py.gate_passed,
            "py_ortony_score": py.ortony_score,
            "py_cosine_distance": py.cosine_distance,
        })

    return {
        "topic": topic,
        "source_synset_id": source_synset_id,
        "candidates": candidates,
    }


def rank_by(candidates: list[dict], key: str) -> list[tuple[int, dict]]:
    """Return (rank, candidate) tuples ranked desc by `key`. Nones go last."""
    def sort_key(c):
        v = c.get(key)
        return (-(v if v is not None else -1e9), c["vehicle_synset_id"])
    sorted_ = sorted(candidates, key=sort_key)
    return [(i + 1, c) for i, c in enumerate(sorted_)]


def fmt_score(v) -> str:
    if v is None:
        return "—"
    return f"{v:.3f}"


def render_report(results: list[dict]) -> str:
    out = []
    out.append("# Loop-1 Cumulative Eyeball — Out-of-Cohort Smoke Test")
    out.append("")
    out.append(
        "Candidate set + ranking generated by Go `/forge/suggest` (pre-loop "
        "cascade config) vs Python `evaluate_cascade_pair` with `PRODUCTION_"
        "CASCADE_CONFIG` (inherits loop-tuned defaults: d_cap=0.68, "
        "rerank_exponent=0.75, concreteness_bonus_coef=0.002 + iter-1 lemma "
        "fallback + iter-2 noun-POS preference)."
    )
    out.append("")
    out.append(
        f"Topics: {len(results)}, candidates per topic: {LIMIT}, displayed: top-{TOP_K_DISPLAY}."
    )
    out.append("")
    out.append("**How to read:** Δ column is `python_rank - go_rank`. Negative = Python pushed up. Positive = Python pushed down. `—` = absent from that ranking's top-K display.")
    out.append("")

    for r in results:
        t = r["topic"]
        out.append(f"## {t['lemma']!r}  (pos={t['pos']}, synset {t['synset_id']})")
        out.append(f"_{t['gloss']}_")
        if r.get("error"):
            out.append("")
            tc = r.get("topic_concreteness")
            hint = ""
            if tc is not None:
                hint = f" — topic concreteness `{tc:.2f}` (concreteness gate needs vehicle_c − topic_c ≥ 1.0; high topic c starves the gate)"
            out.append(f"**ERROR:** {r['error']}{hint}")
            out.append("")
            continue

        out.append(f"Go resolved to source synset: `{r['source_synset_id']}`")
        out.append("")

        cands = r["candidates"]
        # Drop candidates with no Go score (shouldn't happen but safety).
        go_ranked = rank_by(cands, "go_final_score")
        py_ranked = rank_by(cands, "py_final_score")
        go_rank_by_id = {c["vehicle_synset_id"]: rk for rk, c in go_ranked}
        py_rank_by_id = {c["vehicle_synset_id"]: rk for rk, c in py_ranked}

        out.append("| # | Go top-K | Go score | Δ rank | Py top-K (loop) | Py score | Py status |")
        out.append("|---|---|---|---|---|---|---|")
        for i in range(min(TOP_K_DISPLAY, max(len(go_ranked), len(py_ranked)))):
            go_row = go_ranked[i] if i < len(go_ranked) else None
            py_row = py_ranked[i] if i < len(py_ranked) else None
            go_w = go_row[1]["vehicle_word"] if go_row else "—"
            go_s = fmt_score(go_row[1]["go_final_score"]) if go_row else "—"
            py_w = py_row[1]["vehicle_word"] if py_row else "—"
            py_s = fmt_score(py_row[1]["py_final_score"]) if py_row else "—"
            py_status = py_row[1]["py_status"] if py_row else "—"
            if py_row:
                go_r = go_rank_by_id.get(py_row[1]["vehicle_synset_id"])
                delta = py_row[0] - go_r if go_r is not None else None
                delta_s = f"{delta:+d}" if delta is not None else "—"
            else:
                delta_s = "—"
            out.append(f"| {i+1} | {go_w} | {go_s} | {delta_s} | {py_w} | {py_s} | {py_status} |")
        out.append("")

        # Brief stats per topic.
        go_scored = [c for c in cands if c["go_final_score"] is not None]
        py_scored = [c for c in cands if c["py_final_score"] is not None]
        out.append(
            f"_Candidates: {len(cands)}, "
            f"Go scored {len(go_scored)}, "
            f"Py scored {len(py_scored)} (gate-dropped or missing-prop excluded)._"
        )
        out.append("")

    return "\n".join(out)


def main() -> int:
    if not BINARY.exists():
        print(f"ERROR: Go binary not found at {BINARY}. Run: cd api && go build -o metaforge ./cmd/metaforge", file=sys.stderr)
        return 1

    data = json.loads(TOPICS_JSON.read_text())
    topics = data["topics"]
    print(f"Loaded {len(topics)} topics", file=sys.stderr)

    base_url = f"http://127.0.0.1:{PORT}"
    proc = start_api()
    print(f"API started, pid={proc.pid}", file=sys.stderr)
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        results = []
        for i, topic in enumerate(topics, 1):
            print(f"[{i}/{len(topics)}] {topic['lemma']} (pos={topic['pos']})", file=sys.stderr)
            try:
                r = score_topic(conn, topic, base_url)
            except Exception as e:
                print(f"  ERROR: {type(e).__name__}: {e}", file=sys.stderr)
                r = {"topic": topic, "error": f"exception: {type(e).__name__}: {e}", "candidates": []}
            results.append(r)
        conn.close()
    finally:
        stop_api(proc)

    RESULTS_JSON.write_text(json.dumps(results, indent=2))
    print(f"Wrote raw: {RESULTS_JSON}", file=sys.stderr)

    REPORT_MD.write_text(render_report(results))
    print(f"Wrote report: {REPORT_MD}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
