"""M02-S04-B — Union-size distribution check.

The `random_uniform` null reference scored separation_score = -0.0164
on the M02-S02 v1/v2/v3 sweeps. The docstring for `_random_uniform` in
evaluate_aptness.py explicitly flags when the null is unbiased:

    > the cohort-level expected separation_score is unbiased ONLY when
    > the apt and inapt cohorts share similar union-size distributions

If apt and inapt have systematically different |pa ∪ pb| distributions,
the null drift is mechanical — coming from cohort shape, not algorithm
quality — and every separation_score we have measured is partly reading
off cohort-shape mismatch.

This audit computes, for the resolved apt and resolved inapt cohorts:
  * |pa| and |pb| separately
  * |pa ∩ pb| (intersection size)
  * |pa ∪ pb| (union size)

…all in terms of distinct curated cluster_ids. Reports median, p25,
p75, p95, and prints summary tables.

Output: data-pipeline/sweeps/M02-S04-B-union-sizes.md.
"""
import json
import sqlite3
import sys
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).parent))
from evaluate_aptness import lookup_primary_synset, _get_properties

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "data-pipeline" / "output" / "lexicon_v2.db"
APT_PAIRS = REPO_ROOT / "data-pipeline" / "fixtures" / "metaphor_pairs_v2.json"
INAPT = REPO_ROOT / "data-pipeline" / "fixtures" / "munch_inapt.jsonl"
OUTPUT = REPO_ROOT / "data-pipeline" / "sweeps" / "M02-S04-B-union-sizes.md"


def _percentile(values, p):
    if not values:
        return 0.0
    s = sorted(values)
    rank = (p / 100.0) * (len(s) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(s) - 1)
    frac = rank - lo
    return s[lo] * (1 - frac) + s[hi] * frac


def cohort_stats(label, sizes):
    """Render a markdown row of size statistics."""
    if not sizes:
        return f"| {label} | 0 | – | – | – | – | – |"
    return (
        f"| {label} | {len(sizes)} | {min(sizes)} | "
        f"{_percentile(sizes, 25):.0f} | {median(sizes):.0f} | "
        f"{_percentile(sizes, 75):.0f} | {_percentile(sizes, 95):.0f} |"
    )


def gather_apt(conn):
    """For each apt pair that scores, return (|pa|, |pb|, |pa∩pb|, |pa∪pb|)."""
    with open(APT_PAIRS) as f:
        pairs = json.load(f)
    rows = []
    for p in pairs:
        src = p.get("source")
        tgt = p.get("target")
        if not src or not tgt:
            continue
        ssid = lookup_primary_synset(conn, src)
        tsid = lookup_primary_synset(conn, tgt)
        if ssid is None or tsid is None:
            continue
        pa = _get_properties(conn, ssid)
        pb = _get_properties(conn, tsid)
        if not pa or not pb:
            continue
        sa, sb = set(pa), set(pb)
        rows.append((len(sa), len(sb), len(sa & sb), len(sa | sb)))
    return rows


def gather_inapt(conn):
    """For each inapt pair that scores, return (|pa|, |pb|, |pa∩pb|, |pa∪pb|)."""
    rows = []
    with open(INAPT) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict) or row.get("label") != "inapt":
                continue
            tgt = row.get("target")
            para = row.get("paraphrase")
            if not tgt or not para:
                continue
            tsid = lookup_primary_synset(conn, tgt)
            psid = lookup_primary_synset(conn, para)
            if tsid is None or psid is None:
                continue
            pa = _get_properties(conn, tsid)
            pb = _get_properties(conn, psid)
            if not pa or not pb:
                continue
            sa, sb = set(pa), set(pb)
            rows.append((len(sa), len(sb), len(sa & sb), len(sa | sb)))
    return rows


def split_columns(rows):
    """Transpose [(|pa|, |pb|, |∩|, |∪|), …] into four column lists."""
    return (
        [r[0] for r in rows],
        [r[1] for r in rows],
        [r[2] for r in rows],
        [r[3] for r in rows],
    )


def main():
    conn = sqlite3.connect(str(DB_PATH))
    try:
        apt_rows = gather_apt(conn)
        inapt_rows = gather_inapt(conn)
    finally:
        conn.close()

    apt_a, apt_b, apt_int, apt_un = split_columns(apt_rows)
    inapt_a, inapt_b, inapt_int, inapt_un = split_columns(inapt_rows)

    table_header = (
        "| metric | n | min | p25 | median | p75 | p95 |\n"
        "|---|---|---|---|---|---|---|"
    )

    # Compare cohort-level distributions of the four metrics.
    apt_section = "\n".join([
        table_header,
        cohort_stats("|pa| (topic side)", apt_a),
        cohort_stats("|pb| (vehicle side)", apt_b),
        cohort_stats("|pa ∩ pb|", apt_int),
        cohort_stats("|pa ∪ pb|", apt_un),
    ])
    inapt_section = "\n".join([
        table_header,
        cohort_stats("|pa| (target side)", inapt_a),
        cohort_stats("|pb| (paraphrase side)", inapt_b),
        cohort_stats("|pa ∩ pb|", inapt_int),
        cohort_stats("|pa ∪ pb|", inapt_un),
    ])

    # Cross-cohort comparison on union size — the null's bias-driver.
    def fmt_cmp(name, av, iv):
        if not av or not iv:
            return ""
        a_med = median(av)
        i_med = median(iv)
        a_p95 = _percentile(av, 95)
        i_p95 = _percentile(iv, 95)
        med_delta_pct = 100.0 * (a_med - i_med) / max(i_med, 1)
        p95_delta_pct = 100.0 * (a_p95 - i_p95) / max(i_p95, 1)
        flag = "⚠️" if abs(med_delta_pct) > 30 or abs(p95_delta_pct) > 30 else "✓"
        return (
            f"| {name} | {a_med:.0f} | {i_med:.0f} | "
            f"{med_delta_pct:+.1f}% | {a_p95:.0f} | {i_p95:.0f} | "
            f"{p95_delta_pct:+.1f}% | {flag} |"
        )

    cross_section = "\n".join([
        "| metric | apt median | inapt median | median Δ% | apt p95 | inapt p95 | p95 Δ% | flag |",
        "|---|---|---|---|---|---|---|---|",
        fmt_cmp("|pa|", apt_a, inapt_a),
        fmt_cmp("|pb|", apt_b, inapt_b),
        fmt_cmp("|pa ∩ pb|", apt_int, inapt_int),
        fmt_cmp("|pa ∪ pb|", apt_un, inapt_un),
    ])

    # Verdict — is the random_uniform drift explained by cohort shape?
    a_un_med = median(apt_un) if apt_un else 0
    i_un_med = median(inapt_un) if inapt_un else 0
    union_med_delta = 100.0 * (a_un_med - i_un_med) / max(i_un_med, 1)
    if abs(union_med_delta) > 30:
        verdict = (
            "⚠️ **Cohort-shape mismatch confirmed.** Median |pa ∪ pb| differs "
            f"by {union_med_delta:+.1f}% between apt and inapt cohorts. The "
            "documented null-noise drift (random_uniform separation = -0.0164) "
            "is at least partly mechanical — every separation_score on this "
            "harness is partly measuring cohort-shape skew, not just scoring "
            "formula quality."
        )
    elif abs(union_med_delta) > 15:
        verdict = (
            "🟡 **Borderline.** Median |pa ∪ pb| differs by "
            f"{union_med_delta:+.1f}% between cohorts — meaningful but not "
            "overwhelming. The null-drift is partially explained by cohort "
            "shape; some residual algorithm signal may survive."
        )
    else:
        verdict = (
            "✓ **Union sizes broadly comparable.** Median |pa ∪ pb| differs "
            f"by {union_med_delta:+.1f}% between cohorts. The null-drift must "
            "have other sources — investigate threshold-percentile sensitivity "
            "or check for systematic cluster_id frequency differences."
        )

    out = [
        "# M02-S04-B — Union-size distribution check",
        "",
        f"**DB:** `{DB_PATH.relative_to(REPO_ROOT)}`  ",
        f"**Apt resolved:** {len(apt_rows)} pairs  ",
        f"**Inapt resolved:** {len(inapt_rows)} pairs  ",
        "",
        "Sizes are in **distinct curated cluster_ids**.",
        "",
        "## Apt cohort (source = topic, target = vehicle)",
        "",
        apt_section,
        "",
        "## Inapt cohort (target side, paraphrase side)",
        "",
        inapt_section,
        "",
        "## Cross-cohort delta",
        "",
        "Flag triggers at |Δ%| > 30 on either median or p95 — that's the "
        "rough threshold where cohort-shape mismatch starts driving the "
        "random_uniform null off zero noticeably given the ~270-pair cohort "
        "size noise floor.",
        "",
        cross_section,
        "",
        "## Verdict",
        "",
        verdict,
        "",
        "## Why this matters",
        "",
        "From `evaluate_aptness._random_uniform` docstring: *\"the cohort-level "
        "expected separation_score is unbiased ONLY when the apt and inapt "
        "cohorts share similar union-size distributions; if apt unions are "
        "systematically larger or smaller than inapt unions the null reference "
        "becomes biased.\"*",
        "",
        "The v1/v2/v3 sweeps showed random_uniform separation = −0.0164. "
        "Combined with this audit, that drift is now mechanically explained "
        "(or refuted) by the union-size distribution comparison above.",
    ]

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(out))
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
