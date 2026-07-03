"""Agreement harness for candidate LLM judges — topic-grouped Cohen's κ.

Measures how well a candidate judge (a callable `(few_shot, item) -> 0/1`)
tracks the operator's gold verdicts on one axis (construction linkage or
liveness). Mirrors the learning-curve harness shape (grouped folds, empirical
bands, markdown report, argparse main) but the unit under test is a JUDGE, not
a model fit, so the metric is κ + confusion against gold rather than AUC.

Headline correctness property: leave-one-topic-out folds are topic-disjoint and
the few-shot examples shown to the judge are drawn from train only — leakage is
asserted at the fold level AND at the prompt level (a sibling metaphor of the
held-out topic must never appear in the prompt).

κ discipline (plan §2): per-repeat κ values give an empirical [p5, p95] band; a
band straddling 0 reads "underpowered, not usable". Judge failures are logged
ABSTENTIONS (counted, excluded from scoring), never crashes — except
KeyboardInterrupt and claude_client's SessionLimitError, which must halt the
run cleanly (the judge-side cache makes resume free). SessionLimitError is
duck-typed by class name so this module stays importable with no LLM deps.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import math
import os
import random
import re
import sys
import time
from pathlib import Path

import numpy as np
from sklearn.metrics import cohen_kappa_score, confusion_matrix

_SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS_DIR))                            # sibling modules (judge_corpus, judge_stage*)
sys.path.insert(0, str(_SCRIPTS_DIR.parent.parent / "lib"))      # claude_client (via judge_llm, lazy)

log = logging.getLogger(__name__)

AXIS_KEYS = {"construction": "y_link", "liveness": "y_live"}

_LABELS = (0, 1)


def _topic_of(row: dict) -> str:
    return str(row.get("topic_synset_id"))


def topic_folds(rows: list[dict], n_repeats: int, seed: int):
    """Leave-one-topic-out folds, repeated n_repeats times.

    Per repeat every topic is held out exactly once; only the hold-out ORDER is
    shuffled between repeats (the partitions themselves are fixed by LOTO — the
    repeats vary results through per-fold few-shot draws downstream).
    Deterministic for a seed. Yields (train_rows, test_rows).
    """
    by_topic: dict[str, list[dict]] = {}
    for r in rows:
        by_topic.setdefault(_topic_of(r), []).append(r)
    topics = sorted(by_topic)
    rng = random.Random(seed)
    for _rep in range(n_repeats):
        order = topics[:]
        rng.shuffle(order)
        for held_out in order:
            train = [r for t in topics if t != held_out for r in by_topic[t]]
            yield train, list(by_topic[held_out])


def select_few_shot(train_rows: list[dict], k: int, seed: int, balance_key: str) -> list[dict]:
    """Deterministic class-balanced few-shot draw from TRAIN rows only.

    Aims for k//2 per class on `balance_key`; a short class is topped up from
    the other so k is honoured whenever train has enough rows. Topic-
    disjointness from the test fold follows by construction (train rows only) —
    run_axis asserts it anyway at the prompt level. Pools are signature-sorted
    before sampling so the draw depends only on (train content, seed).
    """
    if k <= 0:
        return []
    pools = {label: sorted((r for r in train_rows if int(r[balance_key]) == label),
                           key=lambda r: r["chain_signature"])
             for label in _LABELS}
    rng = random.Random(seed)

    targets = {0: k // 2, 1: k // 2}
    if k % 2:  # odd k: give the extra slot to the larger pool (tie -> positive class)
        targets[1 if len(pools[1]) >= len(pools[0]) else 0] += 1

    chosen: list[dict] = []
    shortfall = 0
    for label in _LABELS:
        take = min(targets[label], len(pools[label]))
        shortfall += targets[label] - take
        chosen.extend(rng.sample(pools[label], take))
    if shortfall:
        picked = {r["chain_signature"] for r in chosen}
        rest = sorted((r for r in train_rows if r["chain_signature"] not in picked),
                      key=lambda r: r["chain_signature"])
        chosen.extend(rng.sample(rest, min(shortfall, len(rest))))
    rng.shuffle(chosen)  # avoid a class-blocked prompt order
    return chosen


def _is_session_limit(exc: BaseException) -> bool:
    """Duck-typed claude_client.SessionLimitError detection (by class name in the
    MRO) so the harness never needs the LLM layer importable to run offline."""
    return any(c.__name__ == "SessionLimitError" for c in type(exc).__mro__)


# Injectable sleep seam so the wait-for-reset path is testable without waiting.
_sleep = time.sleep

# Successive limit-waits before giving up — guards against a reset that never
# actually frees quota (each wait is typically a multi-hour window).
_MAX_LIMIT_WAITS = 4

# Seconds past the advertised reset before resuming — don't race the boundary.
_RESET_BUFFER_S = 90

_RESET_RE = re.compile(r"resets\s+(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)", re.IGNORECASE)


def _parse_reset_utc(message: str, now: "dt.datetime"):
    """Reset datetime (UTC) parsed from a session-limit message, or None.

    The claude CLI phrases it 'resets 5:30pm (UTC)' / 'resets 10am (UTC)' — both
    observed formats are UTC wall-clock times. A time at-or-before `now` means
    the NEXT occurrence (tomorrow); 12am/12pm follow the usual convention.
    """
    m = _RESET_RE.search(message)
    if not m:
        return None
    hour, minute, half = int(m.group(1)), int(m.group(2) or 0), m.group(3).lower()
    hour = hour % 12 + (12 if half == "pm" else 0)
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += dt.timedelta(days=1)
    return candidate


def _kappa_or_none(y_true: list[int], y_pred: list[int]):
    """Cohen's κ, or None when undefined (empty pool / degenerate marginals)."""
    if not y_true:
        return None
    kappa = cohen_kappa_score(y_true, y_pred, labels=list(_LABELS))
    return None if math.isnan(kappa) else float(kappa)


# Progress heartbeat cadence (items). Batch practice: a multi-hundred-call LLM
# run must be observable from its log alone — not inferred from cache file sizes.
_HEARTBEAT_EVERY = 25


def run_axis(rows: list[dict], judge_fn, axis_key: str, *,
             k_shot: int = 6, n_repeats: int = 5, seed: int = 0,
             checkpoint_fn=None) -> dict:
    """Score one judge on one axis over repeated leave-one-topic-out folds.

    Pools (y_true, y_pred) per repeat for the band and across all repeats for
    the headline κ. Any judge exception other than KeyboardInterrupt and a
    SessionLimitError pass-through is an abstention: logged, counted, excluded
    from scoring. Single-class test folds are skipped with a log line (their
    items are never presented to the judge).

    checkpoint_fn (optional) receives a partial result dict (complete=False)
    after every finished repeat, and once more on a session-limit halt
    (halted="session_limit", in-flight repeat included marked partial=True)
    BEFORE the error re-raises — a 99%-complete run must leave its artefact.
    The final return carries complete=True.
    """
    n_topics = len({_topic_of(r) for r in rows})
    folds = topic_folds(rows, n_repeats, seed)
    all_true: list[int] = []
    all_pred: list[int] = []
    per_repeat: list[dict] = []
    n_items = n_abstain = n_folds_skipped = 0
    started = time.monotonic()
    # ETA denominator is an upper bound (skipped folds discovered lazily).
    approx_total = n_repeats * len(rows)

    def _assemble(pool_true: list[int], pool_pred: list[int], reps: list[dict],
                  *, complete: bool, halted: str | None = None) -> dict:
        rep_kappas = [r["kappa"] for r in reps if r["kappa"] is not None]
        band = ([float(np.percentile(rep_kappas, 5)), float(np.percentile(rep_kappas, 95))]
                if rep_kappas else [None, None])
        n_scored = len(pool_true)
        accuracy = (sum(t == p for t, p in zip(pool_true, pool_pred)) / n_scored
                    if n_scored else None)
        majority = (max(pool_true.count(label) for label in _LABELS) / n_scored
                    if n_scored else None)
        confusion = (confusion_matrix(pool_true, pool_pred, labels=list(_LABELS)).tolist()
                     if n_scored else [[0, 0], [0, 0]])
        elapsed = time.monotonic() - started
        return {
            "axis_key": axis_key,
            "kappa": _kappa_or_none(pool_true, pool_pred),
            "kappa_band": band,
            "accuracy": accuracy,
            "majority_baseline": majority,
            "confusion": confusion,
            "n_items": n_items,
            "n_scored": n_scored,
            "n_abstain": n_abstain,
            "n_folds_skipped": n_folds_skipped,
            "n_topics": n_topics,
            "per_repeat": reps,
            "complete": complete,
            "halted": halted,
            "elapsed_s": round(elapsed, 1),
            "items_per_s": round(n_scored / elapsed, 3) if elapsed > 0 and n_scored else None,
            "config": {"k_shot": k_shot, "n_repeats": n_repeats, "seed": seed},
        }

    for rep in range(n_repeats):
        rep_true: list[int] = []
        rep_pred: list[int] = []
        rep_abstain = 0
        for fold_idx in range(n_topics):
            train, test = next(folds)
            held_topic = _topic_of(test[0])
            if len({int(r[axis_key]) for r in test}) < 2:
                log.info("skipping single-class fold: topic=%s repeat=%d", held_topic, rep)
                n_folds_skipped += 1
                continue
            few_shot = select_few_shot(train, k_shot,
                                       seed + rep * 1009 + fold_idx, axis_key)
            # Prompt-level leakage guard — the most-tested property of the plan.
            # Explicit raise, not assert: this must survive `python -O`.
            if any(_topic_of(ex) == held_topic for ex in few_shot):
                raise RuntimeError(f"few-shot leaked held-out topic {held_topic}")
            for item in test:
                n_items += 1
                try:
                    pred = int(judge_fn(few_shot, item))
                except KeyboardInterrupt:
                    raise
                except BaseException as exc:  # noqa: BLE001 — abstention boundary by design
                    if _is_session_limit(exc):
                        # Flush the partial artefact BEFORE halting — everything
                        # scored so far stays on disk; resume replays from cache.
                        if checkpoint_fn is not None:
                            n_abstain += rep_abstain
                            partial_rep = {"repeat": rep,
                                           "kappa": _kappa_or_none(rep_true, rep_pred),
                                           "n_scored": len(rep_true),
                                           "n_abstain": rep_abstain, "partial": True}
                            checkpoint_fn(_assemble(all_true + rep_true, all_pred + rep_pred,
                                                    per_repeat + [partial_rep],
                                                    complete=False, halted="session_limit"))
                        raise  # halt cleanly; the judge-side cache makes resume free
                    log.warning("judge abstained on %s (topic=%s, repeat=%d): %s",
                                item.get("chain_signature"), held_topic, rep, exc)
                    rep_abstain += 1
                    continue
                rep_true.append(int(item[axis_key]))
                rep_pred.append(pred)
                if n_items % _HEARTBEAT_EVERY == 0:
                    elapsed = time.monotonic() - started
                    rate = n_items / elapsed if elapsed > 0 else 0.0
                    eta = (approx_total - n_items) / rate if rate > 0 else float("inf")
                    log.info("progress: repeat %d/%d topic=%s processed %d/~%d "
                             "scored %d abstained %d elapsed %.0fs rate %.2f/s eta ~%.0fs",
                             rep + 1, n_repeats, held_topic, n_items, approx_total,
                             len(all_true) + len(rep_true), n_abstain + rep_abstain,
                             elapsed, rate, eta)
        rep_kappa = _kappa_or_none(rep_true, rep_pred)
        per_repeat.append({"repeat": rep, "kappa": rep_kappa,
                           "n_scored": len(rep_true), "n_abstain": rep_abstain})
        log.info("repeat %d: kappa=%s scored=%d abstained=%d",
                 rep, rep_kappa, len(rep_true), rep_abstain)
        all_true.extend(rep_true)
        all_pred.extend(rep_pred)
        n_abstain += rep_abstain
        if checkpoint_fn is not None:
            checkpoint_fn(_assemble(all_true, all_pred, list(per_repeat), complete=False))

    return _assemble(all_true, all_pred, per_repeat, complete=True)


def _atomic_write_json(path: str, obj: dict) -> None:
    """Crash-safe full-file replace (tmp + fsync + rename) — a reader never sees
    a torn JSON, and a checkpoint overwrite cannot corrupt the previous one."""
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _fmt(value, spec: str = ".3f") -> str:
    return "n/a" if value is None else format(value, spec)


def render_markdown_report(result: dict, title: str) -> str:
    cfg = result["config"]
    lo, hi = result["kappa_band"]
    (tn, fp), (fn, tp) = result["confusion"]
    lines = [
        f"# {title}",
        "",
        f"- axis `{result['axis_key']}`, {result['n_topics']} topics, "
        f"{cfg['n_repeats']} repeats of leave-one-topic-out, k_shot={cfg['k_shot']}, "
        f"seed={cfg['seed']}",
        f"- items {result['n_items']}, scored {result['n_scored']}, "
        f"abstentions {result['n_abstain']}, "
        f"single-class folds skipped {result['n_folds_skipped']}",
        "",
        "## Agreement (pooled across repeats)",
        "",
        "| metric | value |",
        "|---|---|",
        f"| Cohen's kappa | {_fmt(result['kappa'])} |",
        f"| kappa band [p5, p95] | [{_fmt(lo)}, {_fmt(hi)}] |",
        f"| accuracy | {_fmt(result['accuracy'])} |",
        f"| majority baseline | {_fmt(result['majority_baseline'])} |",
        "",
        "## Confusion (rows = gold, cols = judge)",
        "",
        "| | judge 0 | judge 1 |",
        "|---|---|---|",
        f"| gold 0 | {tn} | {fp} |",
        f"| gold 1 | {fn} | {tp} |",
        "",
        "## Per repeat",
        "",
        "| repeat | kappa | scored | abstained |",
        "|---|---|---|---|",
    ]
    lines += [f"| {r['repeat']} | {_fmt(r['kappa'])} | {r['n_scored']} | {r['n_abstain']} |"
              for r in result["per_repeat"]]
    return "\n".join(lines) + "\n"


# --- CLI -----------------------------------------------------------------------

def _make_judge(name: str, axis_key: str, args: argparse.Namespace):
    """Stub judges are pure-Python; stage judges import lazily so offline runs
    (stubs, unit tests) never touch judge_llm or the claude CLI."""
    if name == "stub-perfect":
        return lambda few_shot, item: int(item[axis_key])
    if name == "stub-random":
        rng = random.Random(args.seed)
        return lambda few_shot, item: rng.randint(0, 1)

    import importlib
    module = importlib.import_module(f"judge_{name}")
    optional = {k: v for k, v in
                (("model", args.model), ("cache_path", args.cache)) if v is not None}
    return module.make_judge(**optional)


def _load_rows(axis: str, gold: str, grading_dir: str | None,
               sense_suspects: str | None = None,
               gold_since: str | None = None) -> list[dict]:
    import judge_corpus  # lazy: the harness itself has no corpus dependency
    records = judge_corpus.load_resolved(gold)
    if gold_since:
        # Vintage floor before everything else: pre-final-form verdicts are
        # not gold for ANY purpose (scoring or few-shot) until re-graded.
        records = judge_corpus.drop_before(records, gold_since)
    if sense_suspects:
        # Before the axis split: a sense-mismatched grade corrupts BOTH the
        # liveness label and the structural read, and the few-shot pools draw
        # from these same rows.
        records = judge_corpus.drop_sense_suspect(records, sense_suspects)
    rows = (judge_corpus.construction_rows(records) if axis == "construction"
            else judge_corpus.liveness_rows(records))
    log.info("loaded %d %s rows from %s", len(rows), axis, gold)
    if grading_dir:
        # load_chains globs the round files in the directory; load_glosses wants
        # the glosses FILE within it (degrades to {} when absent).
        glosses_path = Path(grading_dir) / "chain_glosses_provisional.jsonl"
        rows = judge_corpus.attach_chain_context(
            rows, judge_corpus.load_chains(grading_dir),
            judge_corpus.load_glosses(glosses_path))
    return rows


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Topic-grouped agreement harness (Cohen's kappa) for candidate judges.")
    p.add_argument("--axis", required=True, choices=sorted(AXIS_KEYS))
    p.add_argument("--gold", required=True,
                   help="gold verdicts JSONL (no default — point at the grading-live copy)")
    p.add_argument("--grading-dir", default=None, help="grading dir for chain/gloss context")
    p.add_argument("--sense-suspects",
                   default=str(Path(__file__).resolve().parent.parent
                               / "grading" / "gold_sense_suspect.jsonl"),
                   help="quarantine JSONL of gold rows graded under a mismatched "
                        "sense assumption (committed beside the harness); point at "
                        "an empty file to disable")
    p.add_argument("--gold-since", default="2026-06-11",
                   help="gold vintage floor (ISO date/ts): verdicts whose surviving "
                        "ts predates this are invalid — operator decision 2026-07-03, "
                        "final-form era only; re-grading restores a row; pass '' to disable")
    p.add_argument("--judge", required=True,
                   choices=["stub-perfect", "stub-random", "stage1", "stage2"])
    p.add_argument("--model", default=None, help="LLM model for stage judges (their default if unset)")
    p.add_argument("--k-shot", type=int, default=6)
    p.add_argument("--n-repeats", type=int, default=5)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--cache", default=None, help="judge LLM cache JSONL path")
    p.add_argument("-o", "--output", default=None, help="write result JSON here")
    p.add_argument("--no-wait-on-limit", action="store_true",
                   help="halt with exit 75 on a session limit instead of sleeping "
                        "until the advertised reset and resuming from cache")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s: %(message)s")
    axis_key = AXIS_KEYS[args.axis]
    rows = _load_rows(args.axis, args.gold, args.grading_dir, args.sense_suspects,
                      args.gold_since)
    judge_fn = _make_judge(args.judge, axis_key, args)

    from utils import get_git_commit  # sibling import; evidence for committed reports
    run_meta = {"axis": args.axis, "judge": args.judge, "model": args.model,
                "git_commit": get_git_commit()}
    # Every flush — checkpoint, halt, or final — carries the run metadata, so a
    # partial artefact is self-describing without the invoking command line.
    checkpoint = ((lambda partial: _atomic_write_json(args.output, {**partial, **run_meta}))
                  if args.output else None)

    waits = 0
    while True:
        try:
            result = run_axis(rows, judge_fn, axis_key, k_shot=args.k_shot,
                              n_repeats=args.n_repeats, seed=args.seed,
                              checkpoint_fn=checkpoint)
            break
        except BaseException as exc:  # noqa: BLE001 — only the resumable halt is handled
            if not _is_session_limit(exc):
                raise
            waits += 1
            reset_at = _parse_reset_utc(str(exc), dt.datetime.now(dt.timezone.utc))
            if args.no_wait_on_limit or waits > _MAX_LIMIT_WAITS or reset_at is None:
                log.error("halted on session limit (%s); partial result at %s; "
                          "re-run the SAME command to resume — banked calls replay "
                          "from cache at no cost%s", exc,
                          args.output or "(no -o given, nothing flushed)",
                          "" if args.no_wait_on_limit or reset_at is not None
                          else " [no reset time parseable from the message]")
                return 75  # EX_TEMPFAIL: temporary failure, retry the identical command
            wait_s = (reset_at - dt.datetime.now(dt.timezone.utc)).total_seconds() \
                + _RESET_BUFFER_S
            log.warning("session limit (wait %d/%d); partial flushed to %s; sleeping "
                        "%.0fs until %s UTC then resuming — banked calls replay from "
                        "cache", waits, _MAX_LIMIT_WAITS,
                        args.output or "(no -o)", wait_s,
                        reset_at.strftime("%H:%M"))
            _sleep(wait_s)

    result = {**result, **run_meta}
    title = f"Judge agreement — {args.axis} / {args.judge}"
    print(render_markdown_report(result, title))
    if args.output:
        _atomic_write_json(args.output, result)
        log.info("wrote result -> %s", args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
