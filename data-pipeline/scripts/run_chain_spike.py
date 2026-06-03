"""Stage A chain-spike: Sonnet ordered-chain rewrite on snapped topics.

Promoted from /tmp/stagea_spike/run_spike.py (T21).  Key changes from the
original spike:
  - Each chain step is emitted as {"phrase": "...", "head": "..."} rather
    than a bare string, so the grading tool can record per-step heads.
  - build_prompt() accepts an optional anti_examples list so the editor can
    feed back judged-bad paths and steer Sonnet away from them in subsequent
    loops.
  - Output records conform to chain.v1 schema (compute_chain_signature +
    lookup_primary_synset for head resolution).
  - Argparse entrypoint replaces hard-coded file paths.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Path adjustments so this script can be invoked directly or via pytest.
sys.path.insert(0, str(Path(__file__).resolve().parent))               # metaphor_graph
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))  # claude_client
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "grading_sidecar"))  # models

from metaphor_graph import lookup_primary_synset  # noqa: E402
from claude_client import prompt_json, ClaudeError  # noqa: E402
from models import compute_chain_signature  # noqa: E402

# ---------------------------------------------------------------------------
# Defaults (can be overridden via argparse)
# ---------------------------------------------------------------------------
_DEFAULT_SNAPPED_TOPICS = (
    "/tmp/stagea_dryrun2/topics_snapped_batch1.json"
)
_DEFAULT_HAIKU_JSONL = (
    "/home/agent/projects/metaforge/data-pipeline/output/"
    "metaphor_spike_apt_phase2_20260525T004154.jsonl"
)
_DEFAULT_OUTPUT = "/tmp/stagea_spike/sonnet_chains.jsonl"
_DEFAULT_MODEL = "claude-sonnet-4-6"
_PROPOSER = "run_chain_spike"


# ---------------------------------------------------------------------------
# Prompt builder (pure function — tested without I/O)
# ---------------------------------------------------------------------------

def build_prompt(
    topic: str,
    gloss: str,
    haiku_metaphors: list[dict],
    anti_examples: list[dict] | None = None,
) -> str:
    """Return the Sonnet prompt string for ordered-chain generation.

    Each chain step must be emitted as {"phrase": "...", "head": "..."} so the
    grading tool can record per-step lexical heads.

    anti_examples: list of {"chain": [str, ...], "notes": str} dicts that the
    editor has judged as bad paths; included in the prompt as an AVOID block
    when the list is non-empty.
    """
    # Build candidate-vehicle rows from Haiku output.
    rows = []
    for m in haiku_metaphors:
        if not isinstance(m, dict):
            continue
        v = m.get("vehicle", "")
        feats = [
            sf["concept"]
            for sf in m.get("shared_features", [])
            if isinstance(sf, dict) and isinstance(sf.get("concept"), str)
        ]
        rows.append(f"- {v}: {', '.join(feats)}" if feats else f"- {v}")
    vehicles_text = "\n".join(rows) if rows else "(none)"

    # Build the anti-examples block (only when the caller passes non-empty list).
    anti_block = ""
    if anti_examples:
        lines = [
            "Avoid chains that look like these (judged bad path by the editor):\n"
        ]
        for i, ex in enumerate(anti_examples, 1):
            chain_str = " → ".join(ex.get("chain", []))
            notes = ex.get("notes", "")
            lines.append(f"  EXAMPLE {i}: {chain_str}")
            if notes:
                lines.append(f"    Why it failed: {notes}")
        anti_block = "\n" + "\n".join(lines) + "\n"

    return f"""You are doing a polished editorial rewrite of a metaphor-enrichment dataset.

For the topic below, Haiku produced a list of 10 candidate vehicles with shared features as flat sets. Your job:

1) You have full creative license to substitute weak/conventional vehicles with more vivid, literary, cross-domain ones — exactly the kind of substitutions an editor would make (e.g. "anger → fermentation" rather than "anger → fire" if it is apter).
2) For EACH vehicle, return an ORDERED CHAIN of concept steps from topic to vehicle — a recognisable conceptual walk, NOT a flat set.
3) Use as many steps as the traversal naturally needs. Prefer SMALLER LEAPS over fewer steps. Every step must add new conceptual ground — no near-synonyms, no padding. CRUCIALLY, each adjacent pair must stand on its own: a reader shown ONLY those two concepts, blind to every other step in the chain, must still find the leap apt. Do not let a step lean on context accumulated earlier in the chain to justify it — each hop must read as apt in isolation, so the same hop stays valid when a different path reuses it. (Every step is still load-bearing — removing it should skip necessary ground — but no step may DEPEND on the specific steps before it for its own aptness.)
4) Return exactly 10 vehicles.
5) Each step in the chain must be a JSON object with two keys:
   - "phrase": the full step label (a single word or very short noun phrase)
   - "head": the single-word lexical head of the phrase (e.g. phrase "burning rage" → head "rage"; phrase "fire" → head "fire")
{anti_block}
Topic: {topic}
Gloss: {gloss}

Haiku candidates (vehicle: shared-feature set):
{vehicles_text}

Respond with STRICT JSON of this shape, and nothing else:
{{
  "topic": "{topic}",
  "vehicles": [
    {{
      "vehicle": "<single-word lemma>",
      "chain": [
        {{"phrase": "{topic}", "head": "{topic}"}},
        {{"phrase": "<step>", "head": "<head>"}},
        {{"phrase": "<vehicle>", "head": "<vehicle>"}}
      ]
    }},
    ...
  ]
}}

The chain MUST start with the topic and end with the vehicle. Intermediate steps are single words or very short noun phrases (no full sentences)."""


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def _load_jsonl(path: str) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    out = []
    for line in p.open():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as exc:
                print(f"[warn] skipping malformed JSONL line in {path}: {exc}", file=sys.stderr)
    return out


def _load_anti_examples(path: str | None) -> list[dict]:
    """Load anti-examples from a JSON file (list of {"chain", "notes"} objects)."""
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        print(f"[warn] anti-examples file not found: {path}", file=sys.stderr)
        return []
    try:
        data = json.loads(p.read_text())
        if isinstance(data, list):
            return data
        print(f"[warn] anti-examples file is not a JSON list: {path}", file=sys.stderr)
        return []
    except json.JSONDecodeError as exc:
        print(f"[warn] cannot parse anti-examples file {path}: {exc}", file=sys.stderr)
        return []


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stage A chain-spike: Sonnet ordered-chain generation."
    )
    parser.add_argument(
        "--snapped-topics",
        default=_DEFAULT_SNAPPED_TOPICS,
        help="Path to the snapped-topics JSON produced by the batch-prep step.",
    )
    parser.add_argument(
        "--haiku-apt-jsonl",
        default=_DEFAULT_HAIKU_JSONL,
        help="Path to the Haiku apt-metaphors JSONL (one record per topic).",
    )
    parser.add_argument(
        "--anti-examples-json",
        default=None,
        help=(
            "Optional path to a JSON file (list of {chain, notes} objects) "
            "containing editor-judged bad paths to steer Sonnet away from."
        ),
    )
    parser.add_argument(
        "--output",
        default=_DEFAULT_OUTPUT,
        help="Output JSONL path for Sonnet chain records.",
    )
    parser.add_argument(
        "--db",
        default=None,
        help=(
            "Path to lexicon_v2.db — used to resolve phrase heads via "
            "lookup_primary_synset. When omitted, head fields echo the phrase."
        ),
    )
    parser.add_argument(
        "--model",
        default=_DEFAULT_MODEL,
        help=f"Claude model to use (default: {_DEFAULT_MODEL}).",
    )
    args = parser.parse_args()

    # Load input data.
    snapped = json.loads(Path(args.snapped_topics).read_text())
    batch_topics: list[str] = [t["word"] for t in snapped["snapped"]]

    haiku_by_topic: dict[str, dict] = {
        d["topic"]: d
        for d in _load_jsonl(args.haiku_apt_jsonl)
        if d.get("topic") in batch_topics
    }
    anti_examples = _load_anti_examples(args.anti_examples_json)

    # Resolve DB connection for head snapping (optional).
    conn = None
    if args.db:
        import sqlite3
        conn = sqlite3.connect(args.db)

    # Open DB connection for head resolution if available.
    try:
        _run(
            batch_topics=batch_topics,
            haiku_by_topic=haiku_by_topic,
            anti_examples=anti_examples,
            output_path=args.output,
            model=args.model,
            conn=conn,
        )
    finally:
        if conn:
            conn.close()

    return 0


def _run(
    *,
    batch_topics: list[str],
    haiku_by_topic: dict[str, dict],
    anti_examples: list[dict],
    output_path: str,
    model: str,
    conn,
) -> None:
    """Core loop: iterate topics, call Sonnet, write JSONL.

    Each output record conforms to the chain.v1 schema envelope.  The full
    ChainRecord Pydantic validation is intentionally not applied here — the
    grading-tool ingester owns that step — so partial runs are still useful.
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()

    with open(output_path, "w") as out:
        for i, topic in enumerate(batch_topics, 1):
            entry = haiku_by_topic.get(topic)
            if not entry or not entry.get("metaphors"):
                print(f"[{i}/{len(batch_topics)}] SKIP {topic} (no haiku data)")
                continue

            prompt = build_prompt(
                topic=topic,
                gloss=entry.get("_gloss", ""),
                haiku_metaphors=entry.get("metaphors", []),
                anti_examples=anti_examples if anti_examples else None,
            )

            try:
                resp = prompt_json(prompt, model=model)
                resp.setdefault("topic", topic)
                vehicles = resp.get("vehicles", [])
                # Snap heads via DB when available.
                if conn:
                    for v in vehicles:
                        for step in v.get("chain", []):
                            if isinstance(step, dict) and "phrase" in step:
                                phrase = step["phrase"]
                                resolved = lookup_primary_synset(conn, phrase)
                                # head defaults to phrase when no synset found.
                                step["head"] = resolved or phrase
                # Attach chain.v1 metadata per vehicle.
                for v in vehicles:
                    phrases = [
                        s["phrase"] for s in v.get("chain", [])
                        if isinstance(s, dict) and "phrase" in s
                    ]
                    v["chain_signature"] = compute_chain_signature(_PROPOSER, phrases)
                    v["proposer"] = _PROPOSER
                print(f"[{i}/{len(batch_topics)}] OK {topic}: {len(vehicles)} vehicles")
            except ClaudeError as exc:
                print(f"[{i}/{len(batch_topics)}] FAIL {topic}: {exc}")
                resp = {"topic": topic, "error": str(exc), "vehicles": []}

            out.write(json.dumps(resp) + "\n")
            out.flush()

    print(f"done in {time.monotonic() - t0:.1f}s -> {output_path}")


if __name__ == "__main__":
    raise SystemExit(main())
