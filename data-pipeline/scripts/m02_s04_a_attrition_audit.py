"""M02-S04-A — Cohort-attrition audit.

Stratify why each apt and each inapt pair drops out of scoring.

The sweep harness reports only cohort-level rollups:
  apt=232/274 (unresolved=3, no_properties=39)
  inapt=317/1447 (unresolved=469, no_properties=661)

…but no per-pair reason breakdown and no stratification by domain/tier
(apt) or genre (inapt). If the surviving cohort is not representative
of the original, every separation_score we have measured is reading off
a biased slice rather than an honest discrimination test.

This audit re-runs the resolve + properties path used by
`evaluate_aptness._score_cohort` and records, per pair:
  * status (scored | unresolved | no_properties)
  * which side failed when status != scored
  * pair metadata (domain/tier for apt; genre for inapt)

Output: `data-pipeline/sweeps/M02-S04-A-attrition-audit.md` with tables
and a verdict on whether the resolved cohort is representative.
"""
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from evaluate_aptness import lookup_primary_synset, _get_properties

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "data-pipeline" / "output" / "lexicon_v2.db"
APT_PAIRS = REPO_ROOT / "data-pipeline" / "fixtures" / "metaphor_pairs_v2.json"
INAPT = REPO_ROOT / "data-pipeline" / "fixtures" / "munch_inapt.jsonl"
OUTPUT = REPO_ROOT / "data-pipeline" / "sweeps" / "M02-S04-A-attrition-audit.md"


def classify_apt_pair(conn, pair):
    """Return (status, failure_side) for an apt pair.

    status ∈ {scored, unresolved, no_properties}.
    failure_side ∈ {source, target, both, None}.
    """
    src = pair.get("source")
    tgt = pair.get("target")
    src_sid = lookup_primary_synset(conn, src) if src else None
    tgt_sid = lookup_primary_synset(conn, tgt) if tgt else None

    src_unres = src_sid is None
    tgt_unres = tgt_sid is None
    if src_unres or tgt_unres:
        if src_unres and tgt_unres:
            return "unresolved", "both"
        return "unresolved", "source" if src_unres else "target"

    src_props = _get_properties(conn, src_sid)
    tgt_props = _get_properties(conn, tgt_sid)
    src_no = not src_props
    tgt_no = not tgt_props
    if src_no or tgt_no:
        if src_no and tgt_no:
            return "no_properties", "both"
        return "no_properties", "source" if src_no else "target"

    return "scored", None


def classify_inapt_pair(conn, row):
    """Return (status, failure_side) for an inapt MUNCH pair.

    Same statuses as apt, but failure_side ∈ {target, paraphrase, both, None}.
    """
    tgt = row.get("target")
    para = row.get("paraphrase")
    tgt_sid = lookup_primary_synset(conn, tgt) if tgt else None
    para_sid = lookup_primary_synset(conn, para) if para else None

    tgt_unres = tgt_sid is None
    para_unres = para_sid is None
    if tgt_unres or para_unres:
        if tgt_unres and para_unres:
            return "unresolved", "both"
        return "unresolved", "target" if tgt_unres else "paraphrase"

    tgt_props = _get_properties(conn, tgt_sid)
    para_props = _get_properties(conn, para_sid)
    tgt_no = not tgt_props
    para_no = not para_props
    if tgt_no or para_no:
        if tgt_no and para_no:
            return "no_properties", "both"
        return "no_properties", "target" if tgt_no else "paraphrase"

    return "scored", None


def audit_apt(conn):
    """Walk apt pairs; return list of per-pair audit dicts."""
    with open(APT_PAIRS) as f:
        pairs = json.load(f)
    audit = []
    for p in pairs:
        status, side = classify_apt_pair(conn, p)
        audit.append({
            "source": p.get("source"),
            "target": p.get("target"),
            "tier": p.get("tier"),
            "domain": p.get("domain"),
            "status": status,
            "failure_side": side,
        })
    return audit


def audit_inapt(conn):
    """Walk inapt controls; return list of per-pair audit dicts."""
    audit = []
    with open(INAPT) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            if row.get("label") != "inapt":
                continue
            status, side = classify_inapt_pair(conn, row)
            audit.append({
                "target": row.get("target"),
                "paraphrase": row.get("paraphrase"),
                "genre": row.get("genre"),
                "status": status,
                "failure_side": side,
            })
    return audit


def fmt_count_table(counter, total, header):
    lines = [f"| {header} | count | % of total |", "|---|---|---|"]
    for key, count in counter.most_common():
        pct = 100.0 * count / total if total else 0
        lines.append(f"| {key} | {count} | {pct:.1f}% |")
    return "\n".join(lines)


def representativeness_verdict(strat_pre, strat_post, label):
    """Compare pre-resolution and post-resolution stratifications.

    For each stratum, report (pre_count, post_count, retention_pct). A
    biased filter shows up as retention varying meaningfully across
    strata. Calculate a max-min spread on retention; > 25 percentage
    points is flagged as biased.
    """
    rows = []
    keys = set(strat_pre) | set(strat_post)
    for k in sorted(keys, key=str):
        pre = strat_pre.get(k, 0)
        post = strat_post.get(k, 0)
        ret = 100.0 * post / pre if pre else 0
        rows.append((k, pre, post, ret))
    lines = [
        f"| {label} | pre-resolve | resolved (scored) | retention % |",
        "|---|---|---|---|",
    ]
    for k, pre, post, ret in rows:
        lines.append(f"| {k} | {pre} | {post} | {ret:.1f}% |")
    retentions = [r for _, pre, _, r in rows if pre >= 5]
    if retentions:
        spread = max(retentions) - min(retentions)
        verdict = (
            f"**Spread:** retention varies by {spread:.1f} percentage points "
            f"across strata with n≥5. "
            + ("⚠️ likely biased filter (>25pp)." if spread > 25 else "✓ retention reasonably uniform.")
        )
    else:
        verdict = "_(insufficient stratum sizes for spread analysis)_"
    return "\n".join(lines) + "\n\n" + verdict


def main():
    if not DB_PATH.is_file():
        raise FileNotFoundError(f"DB not at {DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH))
    try:
        apt = audit_apt(conn)
        inapt = audit_inapt(conn)
    finally:
        conn.close()

    apt_total = len(apt)
    inapt_total = len(inapt)

    apt_status = Counter(p["status"] for p in apt)
    inapt_status = Counter(p["status"] for p in inapt)

    apt_failure_side = Counter(
        (p["status"], p["failure_side"]) for p in apt if p["status"] != "scored"
    )
    inapt_failure_side = Counter(
        (p["status"], p["failure_side"]) for p in inapt if p["status"] != "scored"
    )

    # Stratifications
    apt_domain_pre = Counter(p["domain"] for p in apt)
    apt_domain_scored = Counter(p["domain"] for p in apt if p["status"] == "scored")
    apt_tier_pre = Counter(p["tier"] for p in apt)
    apt_tier_scored = Counter(p["tier"] for p in apt if p["status"] == "scored")

    inapt_genre_pre = Counter(p["genre"] for p in inapt)
    inapt_genre_scored = Counter(p["genre"] for p in inapt if p["status"] == "scored")

    out = [
        "# M02-S04-A — Cohort-attrition audit",
        "",
        f"**DB:** `{DB_PATH.relative_to(REPO_ROOT)}`  ",
        f"**Apt source:** `{APT_PAIRS.relative_to(REPO_ROOT)}` ({apt_total} pairs)  ",
        f"**Inapt source:** `{INAPT.relative_to(REPO_ROOT)}` ({inapt_total} label=inapt rows)  ",
        "",
        "Generated by `data-pipeline/scripts/m02_s04_a_attrition_audit.py`.",
        "",
        "## Headline",
        "",
        f"- Apt: **{apt_status['scored']}/{apt_total}** scored "
        f"(unresolved={apt_status['unresolved']}, no_properties={apt_status['no_properties']})  ",
        f"- Inapt: **{inapt_status['scored']}/{inapt_total}** scored "
        f"(unresolved={inapt_status['unresolved']}, no_properties={inapt_status['no_properties']})",
        "",
        "## Apt cohort — failure breakdown",
        "",
        fmt_count_table(
            Counter({f"{s} ({side})": c for (s, side), c in apt_failure_side.items()}),
            apt_total,
            "failure mode",
        ),
        "",
        "## Apt cohort — retention by domain",
        "",
        representativeness_verdict(apt_domain_pre, apt_domain_scored, "domain"),
        "",
        "## Apt cohort — retention by tier",
        "",
        representativeness_verdict(apt_tier_pre, apt_tier_scored, "tier"),
        "",
        "## Inapt cohort — failure breakdown",
        "",
        fmt_count_table(
            Counter({f"{s} ({side})": c for (s, side), c in inapt_failure_side.items()}),
            inapt_total,
            "failure mode",
        ),
        "",
        "## Inapt cohort — retention by genre",
        "",
        representativeness_verdict(inapt_genre_pre, inapt_genre_scored, "genre"),
        "",
        "## Lost-words tail (apt, unresolved + no_properties)",
        "",
        "First 30 by source/target so we can eyeball what kind of vocab is missing:",
        "",
        "```",
    ]
    lost_apt = [p for p in apt if p["status"] != "scored"]
    for p in lost_apt[:30]:
        out.append(
            f"  {p['source']!s:>12} → {p['target']!s:<12}  "
            f"[{p['status']}/{p['failure_side']}]  domain={p['domain']} tier={p['tier']}"
        )
    out.append("```")
    out.append("")
    out.append("## Lost-words tail (inapt, sample of 30)")
    out.append("")
    out.append("```")
    lost_inapt = [p for p in inapt if p["status"] != "scored"]
    for p in lost_inapt[:30]:
        out.append(
            f"  {p['target']!s:>15} ↔ {p['paraphrase']!s:<15}  "
            f"[{p['status']}/{p['failure_side']}]  genre={p['genre']}"
        )
    out.append("```")
    out.append("")
    out.append("## Verdict — is the resolved cohort representative?")
    out.append("")
    out.append("See the per-stratum retention tables above. Two failure modes "
               "to watch for: (1) retention skew across strata > 25 percentage "
               "points implies the filter is removing one category preferentially; "
               "(2) absolute retention < 50% for the inapt cohort means we're "
               "scoring on a slice rather than a representative sample regardless "
               "of even retention.")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(out))
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
