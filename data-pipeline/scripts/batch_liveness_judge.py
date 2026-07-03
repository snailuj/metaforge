#!/usr/bin/env python3
"""Batch liveness judge over chain.v1 JSONL, via claude_client (subscription CLI).

Preserves the STRICT, conservative per-metaphor rubric from metaphor_live_rate,
but judges N metaphors per `claude -p` call to amortise the ~13s subprocess
overhead. Each metaphor is still judged INDEPENDENTLY (the prompt forbids
cross-item anchoring) — batching is a throughput trick, not a change of
instrument. CHECKPOINTED + RESUMABLE per chain (keyed by chain_signature): a
kill / rate-limit / crash never re-judges a done chain.

Runs on the Claude subscription (claude_client), so it may hit a 429 session
limit; on RateLimitError it stops cleanly (checkpoint intact) for a later resume.

⚠️ CALIBRATION CAVEAT (measured 2026-07-02): batching drifts the liveness judge
LENIENT — batch-20 scored the Sonnet baseline at 0.40 live vs the calibrated
per-chain rate of ~0.22 (judging many metaphors in one context anchors the model
toward "all plausible"). Do NOT use this for a calibrated liveness rate — use the
per-chain judge (bakeoff.proxy_live_rate / metaphor_live_rate.judge_chain). This
tool is fine only for rough bulk triage where absolute calibration doesn't matter.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent.parent / "lib")]

_RUBRIC = (
    'Classify each metaphor below as exactly "live", "dead", or "irrelevant".\n\n'
    "Definitions:\n"
    '  - "live": an apt, vivid, cross-domain metaphor a careful writer would use — the\n'
    "    vehicle illuminates the topic in a fresh, non-obvious way.\n"
    '  - "dead": a cliché, a near-synonym, a conventional/dead metaphor, or a pairing whose\n'
    "    connection is purely literal or definitional (no cross-domain leap).\n"
    '  - "irrelevant": no genuine metaphorical connection between topic and vehicle.\n\n'
    "Be a strict, conservative judge: if you are unsure, in any doubt, or the aptness is only\n"
    'weak, do NOT call it "live". Reserve "live" for metaphors you are confident a discerning\n'
    "editor would keep. Under-calling live is correct; over-calling live is a serious error.\n"
    "Judge each metaphor INDEPENDENTLY on its own merits — do not let the others shift your bar.\n\n"
    "METAPHORS:\n{items}\n\n"
    "Output ONLY a JSON array, exactly one object per metaphor above, in the same order:\n"
    '[{{"i": 1, "verdict": "live|dead|irrelevant"}}, ...]'
)

_VALID = ("live", "dead", "irrelevant")


def render_item(idx: int, rec: dict) -> str:
    chain_str = " → ".join(s.get("phrase", "") for s in rec.get("chain", []))
    return f'{idx}. {rec.get("topic","")} → {rec.get("vehicle","")}  (chain: {chain_str})'


def build_batch_prompt(chunk: list[dict]) -> str:
    items = "\n".join(render_item(i, r) for i, r in enumerate(chunk, 1))
    return _RUBRIC.format(items=items)


def _load_done(out_path: Path) -> dict:
    done = {}
    if out_path.exists():
        for line in out_path.read_text().splitlines():
            try:
                rec = json.loads(line)
                done[rec["chain_signature"]] = rec["verdict"]
            except (json.JSONDecodeError, KeyError):
                pass
    return done


def judge_file(arm_path, out_path, prompt_json, model, batch_size, max_batches=None, label=""):
    rows = [json.loads(l) for l in Path(arm_path).read_text().splitlines() if l.strip()]
    done = _load_done(Path(out_path))
    pending = [r for r in rows if r.get("chain_signature") not in done]
    fh = open(out_path, "a")
    batches = 0
    try:
        for start in range(0, len(pending), batch_size):
            if max_batches is not None and batches >= max_batches:
                break
            chunk = pending[start:start + batch_size]
            try:
                resp = prompt_json(build_batch_prompt(chunk), model=model, max_retries=3)
            except Exception as exc:  # noqa: BLE001 — surface + stop cleanly (checkpoint intact)
                name = type(exc).__name__
                if "RateLimit" in name or "SessionLimit" in name:
                    print(f"[judge] {label} STOPPED on rate/session limit ({name}): {exc}", file=sys.stderr)
                    break
                print(f"[judge] {label} batch failed (skipped): {exc}", file=sys.stderr)
                continue
            verdicts = resp if isinstance(resp, list) else []
            by_i = {v.get("i"): v.get("verdict") for v in verdicts if isinstance(v, dict)}
            wrote = 0
            for i, rec in enumerate(chunk, 1):
                verdict = by_i.get(i)
                if verdict not in _VALID:
                    continue  # missing / malformed -> skip (don't deflate), re-judged on resume
                fh.write(json.dumps({"chain_signature": rec["chain_signature"], "verdict": verdict}) + "\n")
                wrote += 1
            fh.flush()
            batches += 1
            total_done = len(_load_done(Path(out_path)))
            print(f"[judge] {label} batch {batches} (+{wrote}/{len(chunk)}), total judged={total_done}/{len(rows)}",
                  flush=True)
    finally:
        fh.close()
    return summarise(out_path, len(rows))


def summarise(out_path, n_total):
    done = _load_done(Path(out_path))
    live = sum(1 for v in done.values() if v == "live")
    return {"judged": len(done), "total": n_total, "live": live,
            "live_rate": round(live / len(done), 4) if done else 0.0}


def main() -> int:
    ap = argparse.ArgumentParser(description="Batch liveness judge (claude_client, strict per-item).")
    ap.add_argument("--arm-file", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--batch-size", type=int, default=20)
    ap.add_argument("--max-batches", type=int, default=None, help="Cap batches this run (calibration).")
    ap.add_argument("--label", default="")
    args = ap.parse_args()
    from claude_client import prompt_json
    res = judge_file(args.arm_file, args.out, prompt_json, args.model,
                     args.batch_size, args.max_batches, label=args.label or Path(args.arm_file).stem)
    print(json.dumps(res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
