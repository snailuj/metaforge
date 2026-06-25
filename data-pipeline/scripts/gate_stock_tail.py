#!/usr/bin/env python3
"""Suitability gate over the un-tagged 'stock tail' topics.

The tail (curated nouns with no SemCor-tagged sense) is a MIX of evocative
rare words (the verdigris/moraine register) and junk (proper nouns, bare
`-ness` nominalisations, technical jargon, abbreviations, British-spelling
near-duplicates of common words). A cheap batched Haiku pass keeps the
metaphor-usable concepts and drops the rest — the scalable analogue of the
hand-curation that built the 324.

Reuses the pipeline's claude_client (CLI subscription, no API $). Resumable:
each verdict is checkpointed to a JSONL keyed by word; a re-run skips done
words. Session-limit windows are slept-through (parse reset -> sleep -> resume)
so the gate survives unattended alongside the generation run.

Output: a vetted-topics JSON ({n, topics:[{word,topic_synset_id,gloss}]}) of
the KEPT tail, ready to append to the generation run's topic list.
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from claude_client import (  # noqa: E402
    SessionLimitError,
    SessionLimitFormatError,
    parse_reset_time,
    prompt_json,
)

RUBRIC = """You are curating TOPIC WORDS for a metaphor-generation engine used by genre-fiction writers.
For each word below, decide whether it is a GOOD topic to build vivid, live metaphors from.

KEEP (true) a word that names an evocative, imageable concept: a concrete object, a natural or
weather/geological phenomenon, a sensory experience, an emotion or mood, an abstract human state,
a social or relational dynamic, a bodily experience, a process or transformation.

DROP (false) a word that is: a proper noun or place/brand/person name; an abbreviation or acronym;
an informal/slang term of address (mum, mrs, mate); a bare grammatical nominalisation with no image
of its own (activeness, adhesiveness, wrongfulness); narrow technical/scientific/medical/legal jargon
(zymolysis, adiposis, chlamydia); a mere British-spelling variant or inflection of a common everyday
word (centre, colour, behaviour); or anything too generic/administrative to evoke an image.

Respond with STRICT JSON only, an array of objects, one per input word, in order:
[{"word": "<word>", "keep": true|false}]
Nothing else."""


def build_prompt(words: list[str]) -> str:
    listing = "\n".join(f"- {w}" for w in words)
    return f"{RUBRIC}\n\nWords:\n{listing}\n"


def load_done(checkpoint: Path) -> dict[str, bool]:
    done: dict[str, bool] = {}
    if checkpoint.exists():
        for line in checkpoint.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                done[rec["word"]] = bool(rec["keep"])
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
    return done


def classify_batch(words: list[str], model: str) -> dict[str, bool]:
    """Return {word: keep}. Robust to the model omitting/extra words."""
    resp = prompt_json(build_prompt(words), model=model, max_retries=3)
    verdicts: dict[str, bool] = {}
    rows = resp if isinstance(resp, list) else resp.get("words", []) if isinstance(resp, dict) else []
    for row in rows:
        if isinstance(row, dict) and "word" in row:
            verdicts[str(row["word"]).strip().lower()] = bool(row.get("keep"))
    return verdicts


def sleep_until_reset(reset_text: str, buffer_s: int = 90) -> None:
    h, m = parse_reset_time(reset_text)
    now = datetime.datetime.now(datetime.timezone.utc)
    t = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if t <= now:
        t += datetime.timedelta(days=1)
    secs = int((t - now).total_seconds()) + buffer_s
    print(f"[gate] session limit (resets {reset_text}). Sleeping {secs}s.", flush=True)
    time.sleep(max(secs, buffer_s))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tail", required=True, help="Tail topics JSON ({topics:[{word,topic_synset_id,gloss}]}).")
    ap.add_argument("--checkpoint", required=True, help="Resumable per-word verdict JSONL.")
    ap.add_argument("-o", "--output", required=True, help="Vetted KEEP topics JSON.")
    ap.add_argument("--batch-size", type=int, default=30)
    ap.add_argument("--model", default="claude-haiku-4-5-20251001")
    args = ap.parse_args()

    tail = json.loads(Path(args.tail).read_text())["topics"]
    by_word = {t["word"]: t for t in tail}
    checkpoint = Path(args.checkpoint)
    done = load_done(checkpoint)
    pending = [t["word"] for t in tail if t["word"] not in done]
    print(f"[gate] tail={len(tail)} done={len(done)} pending={len(pending)}", flush=True)

    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    with checkpoint.open("a") as ck:
        i = 0
        while i < len(pending):
            batch = pending[i:i + args.batch_size]
            try:
                verdicts = classify_batch(batch, args.model)
            except SessionLimitFormatError as exc:
                print(f"[gate] LOUD: unparseable session-limit reset: {exc}", file=sys.stderr, flush=True)
                return 2
            except SessionLimitError as exc:
                sleep_until_reset(str(exc).split("resets", 1)[-1].strip() or "")
                continue  # retry same batch
            except Exception as exc:  # noqa: BLE001 — log, default-keep, press on
                print(f"[gate] batch error ({exc}); defaulting batch to KEEP", file=sys.stderr, flush=True)
                verdicts = {}
            for w in batch:
                keep = verdicts.get(w.lower(), True)  # default-keep on omission (safe: judge triages later)
                ck.write(json.dumps({"word": w, "keep": keep}) + "\n")
                done[w] = keep
            ck.flush()
            i += len(batch)
            if (i // args.batch_size) % 10 == 0:
                print(f"[gate] {i}/{len(pending)} classified", flush=True)

    kept = [by_word[w] for w, keep in done.items() if keep and w in by_word]
    for t in kept:
        t.pop("semcor_tagged", None)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    json.dump({"n": len(kept), "topics": kept}, open(args.output, "w"), indent=2)
    n_keep = sum(1 for v in done.values() if v)
    print(f"[gate] DONE: kept {n_keep}/{len(done)} -> {args.output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
