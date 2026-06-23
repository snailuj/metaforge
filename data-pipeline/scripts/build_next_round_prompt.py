"""Build the next-round Sonnet prompt with bad_path anti-examples + topic selection.

Per spec section "Bootstrap loop → Anti-example selection algorithm":
- ≤target bad_paths → use all (after substantive-notes filter)
- >target → cluster by leading tag chip (merge/padding/leap/other), proportional, max cluster_max_per_tag/cluster
- Exclude empty/short notes (< min_chars by default)

Topic selection: deterministic shuffle of remaining-topic IDs via fixed seed (SHA256 of seed string).
Already-enriched topics (collected from prior round files) are excluded.

CLI: --judgements <path> --topics-input <path> --output <path> --target 10
"""
from __future__ import annotations
import argparse
import hashlib
import json
import random
import re
import sys
from pathlib import Path
from typing import Iterable

TAG_RE = re.compile(r"^(merge|padding|leap|other)[:\s]", re.IGNORECASE)


def filter_substantive_notes(items: list[dict], min_chars: int = 20) -> list[dict]:
    return [x for x in items if len(x.get("notes", "")) >= min_chars]


def _tag_of(notes: str) -> str:
    m = TAG_RE.match(notes)
    return m.group(1).lower() if m else "other"


def select_anti_examples(items: list[dict], target: int = 10,
                          cluster_max_per_tag: int = 4,
                          min_note_chars: int = 20) -> list[dict]:
    items = filter_substantive_notes(items, min_chars=min_note_chars)
    if len(items) <= target:
        return items
    by_tag: dict[str, list[dict]] = {}
    for it in items:
        by_tag.setdefault(_tag_of(it.get("notes", "")), []).append(it)
    out: list[dict] = []
    for _tag, group in by_tag.items():
        out.extend(group[:cluster_max_per_tag])
        if len(out) >= target:
            break
    return out[:target]


def deterministic_topic_shuffle(topics: list[str], seed_str: str,
                                 exclude: Iterable[str] = ()) -> list[str]:
    exclude_set = set(exclude)
    pool = [t for t in topics if t not in exclude_set]
    seed = int.from_bytes(hashlib.sha256(seed_str.encode()).digest()[:8], "big")
    rng = random.Random(seed)
    rng.shuffle(pool)
    return pool


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--judgements", default="data-pipeline/grading/judgements_provisional.jsonl")
    p.add_argument("--topics-input", default="data-pipeline/scripts/spike_2_topics.json")
    p.add_argument("--rounds-dir", default="data-pipeline/grading/")
    p.add_argument("--batch-size", type=int, default=20)
    p.add_argument("--seed-str", default="topics_v1")
    p.add_argument("--target-anti-examples", type=int, default=10)
    args = p.parse_args()

    # Collect bad_paths from judgements (latest-per-signature)
    judgements_path = Path(args.judgements)
    judgements = []
    if judgements_path.exists():
        judgements = [json.loads(l) for l in judgements_path.read_text().splitlines() if l.strip()]
    latest_by_sig: dict[str, dict] = {}
    for j in judgements:
        sig = j["chain_signature"]
        if sig not in latest_by_sig or j["ts"] > latest_by_sig[sig]["ts"]:
            latest_by_sig[sig] = j
    bad_paths = [j for j in latest_by_sig.values() if j["label"] == "bad_path"]
    print(f"Found {len(bad_paths)} bad_path verdicts (latest-per-signature)", file=sys.stderr)
    anti_examples = select_anti_examples(bad_paths, target=args.target_anti_examples)
    print(f"Selected {len(anti_examples)} anti-examples", file=sys.stderr)

    # Determine already-enriched topics from prior round files
    rounds_dir = Path(args.rounds_dir)
    enriched_topics: set[str] = set()
    for p_file in rounds_dir.glob("sonnet_chains_provisional_r*.jsonl"):
        for line in p_file.read_text().splitlines():
            if line.strip():
                enriched_topics.add(json.loads(line)["topic"])
    print(f"Already enriched: {len(enriched_topics)} topics", file=sys.stderr)

    # Deterministic shuffle and pick the next batch
    topics_data = json.loads(Path(args.topics_input).read_text())
    all_topic_words = [t["word"] for t in topics_data.get("topics", topics_data)]
    shuffled = deterministic_topic_shuffle(all_topic_words, seed_str=args.seed_str,
                                            exclude=enriched_topics)
    next_batch = shuffled[:args.batch_size]
    print(f"Next batch ({len(next_batch)} topics): {next_batch}", file=sys.stderr)

    print(json.dumps({
        "next_batch": next_batch,
        "anti_examples": [
            {"chain": [], "notes": ae.get("notes", "")}  # actual chain phrase list left to caller
            for ae in anti_examples
        ],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
