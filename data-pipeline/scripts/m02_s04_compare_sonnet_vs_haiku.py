"""M02-S04 — Compare Sonnet vs Haiku enrichment on the 51 emotion synsets.

Reads both enrichment JSONs (under the renamed sensorimotor prompt)
and produces a side-by-side comparison of:
  * wall-time and per-synset rate
  * sensorimotor-tag count per synset (the M02 axis we care about)
  * total properties per synset
  * unique-property overlap between the two models
  * per-synset diffs — for each synset, what does each model emit?

Output: data-pipeline/sweeps/M02-S04-sonnet-vs-haiku.md
"""
import json
from collections import Counter
from pathlib import Path
from statistics import mean, median

REPO_ROOT = Path(__file__).resolve().parents[2]
SONNET = REPO_ROOT / "data-pipeline" / "output" / "enrichment_emotion-sm_sonnet_v2_20260515.json"
HAIKU = REPO_ROOT / "data-pipeline" / "output" / "enrichment_emotion-sm_haiku-v2_v2_20260515.json"
OUTPUT = REPO_ROOT / "data-pipeline" / "sweeps" / "M02-S04-sonnet-vs-haiku.md"


def load(path):
    with open(path) as f:
        return json.load(f)


def stats_for(payload):
    synsets = payload["synsets"]
    total = sum(len(s["properties"]) for s in synsets)
    sm = sum(1 for s in synsets for p in s["properties"]
             if isinstance(p, dict) and p.get("type") == "sensorimotor")
    return {
        "n_synsets": len(synsets),
        "total_props": total,
        "avg_props": total / len(synsets) if synsets else 0,
        "sm_count": sm,
        "sm_per_synset": sm / len(synsets) if synsets else 0,
        "sm_pct": 100.0 * sm / total if total else 0,
        "wall_s": payload["stats"].get("wall_seconds"),
        "unique_texts": payload["stats"].get("unique_properties"),
    }


def main():
    if not SONNET.is_file():
        print(f"Missing {SONNET}")
        return
    if not HAIKU.is_file():
        print(f"Missing {HAIKU} — has the haiku run finished?")
        return

    s_payload = load(SONNET)
    h_payload = load(HAIKU)
    s_stats = stats_for(s_payload)
    h_stats = stats_for(h_payload)

    # Per-synset deltas — match on id, compare sm-counts and total counts.
    s_by_id = {s["id"]: s for s in s_payload["synsets"]}
    h_by_id = {s["id"]: s for s in h_payload["synsets"]}
    common_ids = sorted(set(s_by_id) & set(h_by_id))

    rows = []
    sm_sonnet_total = 0
    sm_haiku_total = 0
    for sid in common_ids:
        s = s_by_id[sid]
        h = h_by_id[sid]
        s_sm = sum(1 for p in s["properties"]
                   if isinstance(p, dict) and p.get("type") == "sensorimotor")
        h_sm = sum(1 for p in h["properties"]
                   if isinstance(p, dict) and p.get("type") == "sensorimotor")
        sm_sonnet_total += s_sm
        sm_haiku_total += h_sm
        rows.append({
            "id": sid,
            "lemma": s.get("lemma", h.get("lemma", "?")),
            "s_n": len(s["properties"]),
            "h_n": len(h["properties"]),
            "s_sm": s_sm,
            "h_sm": h_sm,
            "s_texts": [p.get("text") if isinstance(p, dict) else p
                        for p in s["properties"]],
            "h_texts": [p.get("text") if isinstance(p, dict) else p
                        for p in h["properties"]],
        })

    # Vocabulary overlap — for each synset, what fraction of its texts are
    # shared between the two models? Gives a quick "do they agree?" view.
    overlap_pct = []
    for r in rows:
        s_set = set(r["s_texts"])
        h_set = set(r["h_texts"])
        if not s_set or not h_set:
            continue
        overlap = len(s_set & h_set) / len(s_set | h_set)
        overlap_pct.append(overlap)

    out = [
        "# M02-S04 — Sonnet vs Haiku enrichment comparison",
        "",
        "Same 51 emotion-domain apt-cohort synsets, same `physical → "
        "sensorimotor` renamed prompt, same `--batch-size 5`. Only the "
        "model differs.",
        "",
        "## Aggregate",
        "",
        "| metric | sonnet | haiku | Δ |",
        "|---|---|---|---|",
        f"| n_synsets | {s_stats['n_synsets']} | {h_stats['n_synsets']} | "
        f"{h_stats['n_synsets'] - s_stats['n_synsets']:+d} |",
        f"| total properties | {s_stats['total_props']} | "
        f"{h_stats['total_props']} | "
        f"{h_stats['total_props'] - s_stats['total_props']:+d} |",
        f"| avg props/synset | {s_stats['avg_props']:.1f} | "
        f"{h_stats['avg_props']:.1f} | "
        f"{h_stats['avg_props'] - s_stats['avg_props']:+.1f} |",
        f"| sensorimotor tags total | {s_stats['sm_count']} | "
        f"{h_stats['sm_count']} | "
        f"{h_stats['sm_count'] - s_stats['sm_count']:+d} |",
        f"| sensorimotor per synset | {s_stats['sm_per_synset']:.1f} | "
        f"{h_stats['sm_per_synset']:.1f} | "
        f"{h_stats['sm_per_synset'] - s_stats['sm_per_synset']:+.1f} |",
        f"| sensorimotor % of total | {s_stats['sm_pct']:.1f}% | "
        f"{h_stats['sm_pct']:.1f}% | "
        f"{h_stats['sm_pct'] - s_stats['sm_pct']:+.1f}pp |",
        f"| unique-text vocab | {s_stats['unique_texts']} | "
        f"{h_stats['unique_texts']} | "
        f"{h_stats['unique_texts'] - s_stats['unique_texts']:+d} |",
        # Sonnet payload predates the wall_seconds field — fall back to the
        # known 1123s wall time measured by file-mtime delta on that run.
        f"| wall time (s) | "
        f"{s_stats['wall_s'] if s_stats['wall_s'] else 1123} | "
        f"{h_stats['wall_s'] if h_stats['wall_s'] else 'n/a'} | "
        f"{(h_stats['wall_s'] or 0) - (s_stats['wall_s'] or 1123):+.1f} |",
        f"| wall time (m:ss) | "
        f"{int((s_stats['wall_s'] or 1123)//60)}m {int((s_stats['wall_s'] or 1123)%60)}s | "
        f"{int((h_stats['wall_s'] or 0)//60)}m {int((h_stats['wall_s'] or 0)%60)}s | "
        f"{((h_stats['wall_s'] or 0) / (s_stats['wall_s'] or 1123)):.2f}× |",
        "",
        f"**Per-synset text-set overlap (Jaccard) between Sonnet and Haiku:** "
        f"median {median(overlap_pct):.2f}, mean {mean(overlap_pct):.2f}. "
        f"(1.0 = identical vocabulary on a synset; 0 = no shared texts.)",
        "",
        "## Per-synset sensorimotor + total counts",
        "",
        "| synset | lemma | s_n | h_n | s_sm | h_sm | sm Δ |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        delta = r["h_sm"] - r["s_sm"]
        delta_str = f"+{delta}" if delta > 0 else str(delta)
        out.append(
            f"| {r['id']} | {r['lemma']} | {r['s_n']} | {r['h_n']} | "
            f"{r['s_sm']} | {r['h_sm']} | {delta_str} |"
        )

    # Pick a handful of representative synsets to dump side-by-side.
    out.extend(["", "## Side-by-side property dump (first 5 synsets)", ""])
    for r in rows[:5]:
        out.append(f"### `{r['lemma']}` (synset `{r['id']}`)")
        out.append("")
        out.append("**Sonnet properties:**")
        out.append("")
        out.append("```")
        for p in s_by_id[r["id"]]["properties"]:
            if isinstance(p, dict):
                out.append(
                    f"  {p.get('text', ''):<18} "
                    f"sal={p.get('salience', 0):.2f} "
                    f"type={p.get('type', '?')}"
                )
            else:
                out.append(f"  {p}")
        out.append("```")
        out.append("")
        out.append("**Haiku properties:**")
        out.append("")
        out.append("```")
        for p in h_by_id[r["id"]]["properties"]:
            if isinstance(p, dict):
                out.append(
                    f"  {p.get('text', ''):<18} "
                    f"sal={p.get('salience', 0):.2f} "
                    f"type={p.get('type', '?')}"
                )
            else:
                out.append(f"  {p}")
        out.append("```")
        out.append("")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(out))
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
