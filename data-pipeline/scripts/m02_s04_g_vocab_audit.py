"""M02-S04-G — Curated-vocab gap audit from snap_dropped.jsonl.

Reads `data-pipeline/output/snap_dropped.jsonl` (the streaming diagnostic
that snap_properties.py writes for every property that fails to snap)
and surfaces what's dropping. The output is the input to a targeted
curated-vocab augmentation.

Three views the audit produces:

  1. Top-N dropped property texts, with mean salience and best cosine
     score. High-frequency drops with high salience and high-but-still-
     subthreshold best_score are the cleanest vocab-gap candidates.

  2. Per-reason breakdown (below_threshold / no_embedding / zero_norm)
     — the three drop modes have different fixes:
       * below_threshold: vocab gap (add an entry, or lower threshold)
       * no_embedding: FastText OOV (rare word, multi-word, typo)
       * zero_norm: FastText returns zero vector (corrupt embedding row)

  3. Apt-cohort focus — of the apt-cohort synsets that STILL drop to
     no_properties even at the current snap threshold (e.g. post-0.48),
     which LLM properties on those synsets are getting dropped? This is
     the surgically-targeted view of what vocab additions would
     directly recover apt-cohort coverage.

Output: data-pipeline/sweeps/M02-S04-G-vocab-audit.md
"""
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

sys.path.insert(0, str(Path(__file__).parent))
from evaluate_aptness import lookup_primary_synset, _get_properties

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "data-pipeline" / "output" / "lexicon_v2.db"
APT_PAIRS = REPO_ROOT / "data-pipeline" / "fixtures" / "metaphor_pairs_v2.json"
DROPPED = REPO_ROOT / "data-pipeline" / "output" / "snap_dropped.jsonl"
OUTPUT = REPO_ROOT / "data-pipeline" / "sweeps" / "M02-S04-G-vocab-audit.md"


def load_drops():
    """Read snap_dropped.jsonl into a list of dicts.

    Records:
      {"text": str, "synset_id": str, "salience": float, "reason": str,
       "best_score": float | absent}
    """
    rows = []
    if not DROPPED.is_file():
        return rows
    with open(DROPPED) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def lost_apt_synset_ids(conn):
    """Return set of synset_ids that drop to no_properties for at least
    one apt-pair side at the current DB state.

    Re-runs the same classification logic as S04-A — but only retains
    'no_properties' (i.e. resolved-but-no-curated). These are the
    synsets where vocab gap is the active failure mode."""
    lost = set()
    with open(APT_PAIRS) as f:
        pairs = json.load(f)
    for p in pairs:
        for lemma in (p.get("source"), p.get("target")):
            if not lemma:
                continue
            sid = lookup_primary_synset(conn, lemma)
            if sid is None:
                continue
            if not _get_properties(conn, sid):
                lost.add(sid)
    return lost


def main():
    drops = load_drops()
    if not drops:
        print(f"No drops found in {DROPPED} — has snap run yet?")
        return
    print(f"Loaded {len(drops)} drop records from {DROPPED}")

    # --- Per-reason breakdown -------------------------------------------------
    reason_counts = Counter(d.get("reason", "unknown") for d in drops)

    # --- Top-N dropped texts --------------------------------------------------
    text_to_drops = defaultdict(list)
    for d in drops:
        text_to_drops[d["text"]].append(d)

    text_rows = []
    for text, entries in text_to_drops.items():
        saliences = [e.get("salience", 0.0) for e in entries]
        best_scores = [e["best_score"] for e in entries if "best_score" in e]
        text_rows.append({
            "text": text,
            "count": len(entries),
            "mean_salience": mean(saliences) if saliences else 0.0,
            "mean_best_score": mean(best_scores) if best_scores else None,
            "reason_breakdown": Counter(e.get("reason", "?") for e in entries),
        })
    text_rows.sort(key=lambda r: (-r["count"], -r["mean_salience"]))

    # --- Apt-cohort focus -----------------------------------------------------
    conn = sqlite3.connect(str(DB_PATH))
    try:
        apt_lost = lost_apt_synset_ids(conn)
    finally:
        conn.close()
    apt_drops = [d for d in drops if d["synset_id"] in apt_lost]
    apt_text_counts = Counter(d["text"] for d in apt_drops)
    apt_synset_drops = defaultdict(list)
    for d in apt_drops:
        apt_synset_drops[d["synset_id"]].append(d)

    # --- Render report --------------------------------------------------------
    out = [
        "# M02-S04-G — Curated-vocab gap audit",
        "",
        f"**DB:** `{DB_PATH.relative_to(REPO_ROOT)}`  ",
        f"**Drops source:** `{DROPPED.relative_to(REPO_ROOT)}` "
        f"({len(drops)} records)  ",
        "",
        "Generated by `data-pipeline/scripts/m02_s04_g_vocab_audit.py`.",
        "",
        "## Drop reasons",
        "",
        "| reason | count | % | what fixes it |",
        "|---|---|---|---|",
    ]
    fixes = {
        "below_threshold": "vocab gap — add entry, or lower threshold",
        "no_embedding": "FastText OOV (rare/multi-word/typo)",
        "zero_norm": "corrupt FastText embedding row",
    }
    for reason, count in reason_counts.most_common():
        pct = 100.0 * count / len(drops)
        fix = fixes.get(reason, "?")
        out.append(f"| {reason} | {count} | {pct:.1f}% | {fix} |")
    out.append("")

    out.extend([
        "## Top-30 dropped property texts (across all synsets)",
        "",
        "Sorted by frequency, then by mean salience. The cleanest vocab-",
        "gap candidates are rows with **high count + high mean_salience +",
        "high mean_best_score** — the LLM keeps emitting them, considers",
        "them salient, and they're already cosine-close to *something* in",
        "the curated vocab, just not above threshold.",
        "",
        "| text | count | mean salience | mean best_score | top reason |",
        "|---|---|---|---|---|",
    ])
    for r in text_rows[:30]:
        mbs = f"{r['mean_best_score']:.3f}" if r["mean_best_score"] is not None else "—"
        top_reason = r["reason_breakdown"].most_common(1)[0][0]
        out.append(
            f"| `{r['text']}` | {r['count']} | "
            f"{r['mean_salience']:.2f} | {mbs} | {top_reason} |"
        )

    # --- Apt-cohort drilldown -------------------------------------------------
    out.extend([
        "",
        "## Apt-cohort focus",
        "",
        f"**{len(apt_lost)} apt-cohort synsets still have `no_properties`** "
        f"at the current DB state (i.e. every LLM property on them was "
        f"dropped). {len(apt_drops)} drop records belong to these synsets "
        f"({100.0 * len(apt_drops) / max(len(drops), 1):.1f}% of total drops).",
        "",
        "### Top dropped texts on apt-cohort synsets",
        "",
        "These are the targeted vocab-gap candidates — adding these texts "
        "to the curated vocab (or finding existing close-but-too-distant "
        "vocab entries to lower the cosine threshold against) would "
        "directly recover apt-cohort retention.",
        "",
        "| text | count on apt-lost synsets |",
        "|---|---|",
    ])
    for text, count in apt_text_counts.most_common(30):
        out.append(f"| `{text}` | {count} |")

    # --- Per-synset drilldown (top 10 apt synsets by dropped-property count) --
    out.extend([
        "",
        "### Per-synset drilldown (top 10 apt-lost synsets by dropped-prop count)",
        "",
        "Surfaces what the LLM tried to attach to each emotion/cognition "
        "synset that the snap couldn't accept. Often a synset with 10–15 "
        "LLM properties drops *all* of them — the synset has no foothold "
        "in the curated vocab. Adding even one matching vocab entry "
        "recovers the synset from `no_properties` to `has-properties`.",
        "",
    ])
    by_count = sorted(
        apt_synset_drops.items(), key=lambda kv: -len(kv[1])
    )[:10]
    conn = sqlite3.connect(str(DB_PATH))
    try:
        for sid, ds in by_count:
            row = conn.execute(
                "SELECT lemma FROM lemmas WHERE synset_id = ? LIMIT 1",
                (sid,),
            ).fetchone()
            lemma = row[0] if row else "?"
            texts = sorted({d["text"] for d in ds})
            out.append(f"**`{sid}` ({lemma}) — {len(ds)} drops:**")
            out.append("")
            out.append("```")
            for t in texts:
                # Show salience + best_score where available
                samples = [d for d in ds if d["text"] == t]
                bs = [s.get("best_score") for s in samples
                      if "best_score" in s]
                bs_str = f", best_score={mean(bs):.3f}" if bs else ""
                sal_str = f"salience={mean([s.get('salience', 0) for s in samples]):.2f}"
                out.append(f"  {t:<22} {sal_str}{bs_str}")
            out.append("```")
            out.append("")
    finally:
        conn.close()

    # --- Verdict / next-step prompt -------------------------------------------
    out.extend([
        "## Verdict / next steps",
        "",
        "1. Triage the **top-30 dropped texts** table above. For each text:",
        "   * Is it a sensorimotor primitive missing from curated vocab? "
        "    (e.g. `resonant`, `earthy`, `angular`)  → **add to "
        "      `property_vocab_curated`**.",
        "   * Is it a multi-word phrase the snap can't handle? "
        "    (e.g. `cold metal`) → either expand vocab to MWEs (design-",
        "      doc open question line 295) or have the prompt enforce "
        "      single-word.",
        "   * Is it a typo / non-English? → diagnose prompt regression.",
        "2. After curated-vocab additions, re-run snap and re-run the "
        "S04-A audit + ortony sweep. Expect apt-cohort retention to "
        "climb past the cognition baseline (95.1%) if the gap closes.",
        "3. If most top-30 drops are MWEs or rare words with no good "
        "vocab home, that's a stronger signal to pivot to S04-E "
        "(synthetic matched inapt cohort) — the asymmetry the apt cohort "
        "has is too deep for vocab patching to bridge.",
    ])

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(out))
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
