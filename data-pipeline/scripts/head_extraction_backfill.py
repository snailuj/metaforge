"""Round-1 backfill: extract {phrase, head, synset_id} per chain step from the
existing /tmp/stagea_spike/sonnet_chains.jsonl flat-string chains.

Single-word phrase → head = phrase.lower(); multi-word → batched Haiku call.
Snap each unique head via lookup_primary_synset (nullable on miss).
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import unicodedata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "data-pipeline" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "lib"))
sys.path.insert(0, str(REPO_ROOT / "data-pipeline" / "grading_sidecar"))

from metaphor_graph import lookup_primary_synset  # noqa: E402
from claude_client import prompt_json  # noqa: E402
from models import compute_chain_signature  # noqa: E402

SOURCE = "/tmp/stagea_spike/sonnet_chains.jsonl"
DEST = REPO_ROOT / "data-pipeline" / "grading" / "sonnet_chains_provisional_r1.jsonl"
HAIKU_BATCH_SIZE = 50
HAIKU_MODEL = "claude-haiku-4-5-20251001"


def normalise(s: str) -> str:
    return unicodedata.normalize("NFC", s.strip())


HEAD_PROMPT_INSTRUCTIONS = (
    "For each phrase below, return the single-word concept that the phrase "
    "most centres on — typically a noun. Prefer a head likely to be re-used "
    "across other metaphor traversals over a hyper-specific one. "
    "Preserve modifiers that flip or invert meaning: a negation, opposition, or "
    "relational modifier changes the head — 'resists change' -> 'resistance' or "
    "'stability', not 'change'; 'avoids risk' -> 'caution', not 'risk'. Prefer a "
    "single word that still names a common concept so it resolves to a synset.\n\n"
)


def extract_heads_batch(phrases: list[str]) -> dict[str, str]:
    """Haiku batched call. Returns {phrase: head}."""
    prompt = (
        HEAD_PROMPT_INSTRUCTIONS
        + "Output strict JSON: {\"phrases\": [{\"phrase\": \"...\", \"head\": \"...\"}, ...]}\n\n"
        + "Phrases:\n" + "\n".join(f"- {p}" for p in phrases)
    )
    resp = prompt_json(prompt, model=HAIKU_MODEL, expect=dict)
    return {item["phrase"]: item["head"].lower() for item in resp["phrases"]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db",
        default=str(REPO_ROOT / "data-pipeline" / "output" / "lexicon_v2.db"),
    )
    parser.add_argument("--source", default=SOURCE)
    parser.add_argument("--dest", default=str(DEST))
    args = parser.parse_args()

    raw = [json.loads(l) for l in open(args.source) if l.strip()]
    print(f"Loaded {len(raw)} topic-records from {args.source}", file=sys.stderr)

    # Collect all multi-word intermediate steps (not endpoints — those get
    # their head from the phrase itself per the endpoint-canonicalisation rule).
    multi_word: set[str] = set()
    for rec in raw:
        for vehicle in rec["vehicles"]:
            chain = vehicle["chain"]
            # Skip first (topic) and last (vehicle) — endpoints are canonical.
            for step in chain[1:-1]:
                p = normalise(step)
                if " " in p:
                    multi_word.add(p)

    print(f"Found {len(multi_word)} unique multi-word phrases", file=sys.stderr)

    heads: dict[str, str] = {}
    multi_word_list = sorted(multi_word)
    for i in range(0, len(multi_word_list), HAIKU_BATCH_SIZE):
        batch = multi_word_list[i : i + HAIKU_BATCH_SIZE]
        batch_num = i // HAIKU_BATCH_SIZE + 1
        print(f"  Haiku batch {batch_num}: {len(batch)} phrases", file=sys.stderr)
        heads.update(extract_heads_batch(batch))

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)

    def head_of(phrase: str) -> str:
        """Single-word → lower; multi-word → Haiku result or first token."""
        p = normalise(phrase)
        if " " not in p:
            return p.lower()
        return heads.get(p, p.split()[0].lower())

    out_records: list[dict] = []
    for rec in raw:
        topic = rec["topic"]
        topic_head = topic.lower()
        topic_synset = lookup_primary_synset(conn, topic_head)

        for vehicle in rec["vehicles"]:
            v_phrase = vehicle["vehicle"]
            v_head = v_phrase.lower()
            v_synset = lookup_primary_synset(conn, v_head)

            chain_steps = []
            for step in vehicle["chain"]:
                phrase = normalise(step)
                head = head_of(phrase)
                synset_id = lookup_primary_synset(conn, head)
                chain_steps.append(
                    {
                        "phrase": phrase,
                        "head": head,
                        "synset_id": synset_id,
                    }
                )

            # Endpoint canonicalisation per chain.v1 spec: first step = topic,
            # last step = vehicle, both with canonical heads and snapped synsets.
            # ChainRecord.topic_synset_id / vehicle_synset_id are non-Optional str
            # fields — use "" for unresolved synsets so Pydantic accepts it, and
            # mirror that same "" into chain[0/−1].synset_id so the endpoint
            # equality validator passes. ChainStep.synset_id is Optional[str];
            # "" satisfies that constraint just as well as None.
            topic_synset_str = topic_synset or ""
            v_synset_str = v_synset or ""

            chain_steps[0] = {
                "phrase": topic,
                "head": topic_head,
                "synset_id": topic_synset_str,
            }
            chain_steps[-1] = {
                "phrase": v_phrase,
                "head": v_head,
                "synset_id": v_synset_str,
            }

            phrases = [s["phrase"] for s in chain_steps]
            sig = compute_chain_signature("sonnet_v1", phrases)

            out_records.append(
                {
                    "schema_version": "chain.v1",
                    "topic": topic,
                    "topic_synset_id": topic_synset_str,
                    "vehicle": v_phrase,
                    "vehicle_synset_id": v_synset_str,
                    "proposer": "sonnet_v1",
                    "round": 1,
                    "chain": chain_steps,
                    "chain_signature": sig,
                    # Source predates this backfill run — use a fixed placeholder.
                    "generated_at": "2026-05-30T00:00:00Z",
                }
            )

    conn.close()

    dest = Path(args.dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        for r in out_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"Wrote {len(out_records)} chains to {dest}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
