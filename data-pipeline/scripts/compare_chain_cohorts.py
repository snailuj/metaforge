"""Side-by-side comparison of two chain cohorts for the same topics.

Use when a generation-prompt change (e.g. the context-free-hop clause) has
regenerated chains for a fixed topic set, and you want to eyeball whether the
path structure actually shifted — matched on (topic, vehicle), old path beside
new path. Deliberately does NOT auto-judge "context-bound"-ness: that is the
human signal the pilot exists to capture. This just lays the paths side by side.

Handles both on-disk shapes:
  - grouped   (run_chain_spike output): {topic, vehicles:[{vehicle, chain:[...]}]}
  - flattened (committed round-1 cohort): {topic, vehicle, chain:[...]}
chain steps may be {"phrase","head"} dicts or bare strings.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def extract_phrases(chain: list) -> list[str]:
    """Pull the ordered phrase labels from a chain of dict-or-string steps."""
    out: list[str] = []
    for step in chain:
        if isinstance(step, dict):
            out.append(step.get("phrase", ""))
        else:
            out.append(step)
    return out


def index_chains(records: list[dict]) -> dict[tuple[str, str], list[str]]:
    """Map (topic, vehicle) -> ordered phrase list, accepting either shape."""
    idx: dict[tuple[str, str], list[str]] = {}
    for rec in records:
        topic = rec.get("topic", "")
        if "vehicles" in rec:  # grouped
            for v in rec["vehicles"]:
                idx[(topic, v.get("vehicle", ""))] = extract_phrases(v.get("chain", []))
        elif "vehicle" in rec:  # flattened
            idx[(topic, rec["vehicle"])] = extract_phrases(rec.get("chain", []))
    return idx


def _load_jsonl(path: str) -> list[dict]:
    out: list[dict] = []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as exc:
            print(f"[warn] skipping malformed line in {path}: {exc}", file=sys.stderr)
    return out


def compare(
    old_idx: dict[tuple[str, str], list[str]],
    new_idx: dict[tuple[str, str], list[str]],
) -> dict:
    """Partition the two indexes into common / old-only / new-only rows."""
    old_keys, new_keys = set(old_idx), set(new_idx)

    def _row(key, **paths):
        topic, vehicle = key
        return {"topic": topic, "vehicle": vehicle, **paths}

    common = [
        _row(k, old_path=old_idx[k], new_path=new_idx[k])
        for k in sorted(old_keys & new_keys)
    ]
    old_only = [_row(k, old_path=old_idx[k]) for k in sorted(old_keys - new_keys)]
    new_only = [_row(k, new_path=new_idx[k]) for k in sorted(new_keys - old_keys)]
    return {"common": common, "old_only": old_only, "new_only": new_only}


def _arrow(path: list[str]) -> str:
    return " → ".join(path)


def render_markdown(comparison: dict, *, old_label: str, new_label: str) -> str:
    """Render a per-topic side-by-side artifact for human eyeballing."""
    common = comparison["common"]
    old_only = comparison["old_only"]
    new_only = comparison["new_only"]

    topics = sorted({r["topic"] for r in common + old_only + new_only})
    lines = [
        f"# Chain cohort comparison — {old_label} vs {new_label}",
        "",
        f"- Matched (same topic+vehicle): **{len(common)}**",
        f"- {old_label}-only vehicles (substituted away): **{len(old_only)}**",
        f"- {new_label}-only vehicles (newly introduced): **{len(new_only)}**",
        "",
        "For each matched vehicle the two paths sit one above the other so a "
        "context-bound hop in one but not the other is easy to spot.",
        "",
    ]
    for topic in topics:
        lines.append(f"## {topic}")
        lines.append("")
        for r in (x for x in common if x["topic"] == topic):
            lines.append(f"**{topic} → {r['vehicle']}**")
            lines.append(f"- {old_label}: {_arrow(r['old_path'])}")
            lines.append(f"- {new_label}: {_arrow(r['new_path'])}")
            lines.append("")
        sub = [r["vehicle"] for r in old_only if r["topic"] == topic]
        add = [r["vehicle"] for r in new_only if r["topic"] == topic]
        if sub:
            lines.append(f"_dropped in {new_label}: {', '.join(sub)}_")
        if add:
            lines.append(f"_new in {new_label}: {', '.join(add)}_")
        if sub or add:
            lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old", required=True, help="OLD cohort JSONL.")
    parser.add_argument("--new", required=True, help="NEW cohort JSONL.")
    parser.add_argument("--old-label", default="OLD")
    parser.add_argument("--new-label", default="NEW")
    parser.add_argument("--output", default=None, help="Markdown output path (stdout if omitted).")
    args = parser.parse_args()

    old_idx = index_chains(_load_jsonl(args.old))
    new_idx = index_chains(_load_jsonl(args.new))
    md = render_markdown(
        compare(old_idx, new_idx),
        old_label=args.old_label,
        new_label=args.new_label,
    )
    if args.output:
        Path(args.output).write_text(md, encoding="utf-8")
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
