"""M02-S04 — Build the apt-cohort gap synset_ids file for surgical enrichment.

Reads metaphor_pairs_v2.json, identifies lemmas that drop with status
'no_properties' or 'unresolved' (per the S04-A audit), and classifies
each into:

  * unenriched — synset resolves but has no rows in `synset_properties`
    AT ALL. Surgical enrichment can fix this.
  * snap-dropped — synset has LLM-enriched properties in `synset_properties`
    but none survived snap into `synset_properties_curated`. Enrichment
    can't help — needs snap retuning (S04-D in the retro plan).
  * unresolved — the lemma doesn't resolve to any synset. Neither
    enrichment nor snap helps — lexicon scope issue.

Outputs:
  * data-pipeline/output/apt_gap_synset_ids.json — flat list of the
    `unenriched` synset_ids, ready to feed to
    `enrich_properties.py --synset-ids`.
  * data-pipeline/sweeps/M02-S04-apt-gap-classification.md — full
    breakdown for the retro audit trail.
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
SYNSET_IDS_OUT = REPO_ROOT / "data-pipeline" / "output" / "apt_gap_synset_ids.json"
REPORT_OUT = REPO_ROOT / "data-pipeline" / "sweeps" / "M02-S04-apt-gap-classification.md"


def has_llm_properties(conn, synset_id):
    """True iff synset_properties has at least one row for this synset."""
    row = conn.execute(
        "SELECT 1 FROM synset_properties WHERE synset_id = ? LIMIT 1",
        (synset_id,),
    ).fetchone()
    return row is not None


def classify(conn, lemma):
    """Return ('status', synset_id_or_None, reason)."""
    if not lemma:
        return ("missing-lemma", None, "no lemma in pair")
    sid = lookup_primary_synset(conn, lemma)
    if sid is None:
        return ("unresolved", None, "no synset for this lemma in lexicon")
    if _get_properties(conn, sid):
        return ("has-properties", sid, "already has curated properties")
    if has_llm_properties(conn, sid):
        return ("snap-dropped", sid, "LLM-enriched but snap dropped all")
    return ("unenriched", sid, "no LLM enrichment yet — surgical fix")


def main():
    with open(APT_PAIRS) as f:
        pairs = json.load(f)

    conn = sqlite3.connect(str(DB_PATH))
    try:
        # Walk every apt pair; we only care about pairs that are currently
        # dropping (i.e. either side fails to score) since well-scoring
        # pairs are already in the cohort.
        rows = []
        for p in pairs:
            src = p.get("source")
            tgt = p.get("target")
            domain = p.get("domain")
            tier = p.get("tier")
            for role, lemma in (("source", src), ("target", tgt)):
                status, sid, reason = classify(conn, lemma)
                rows.append({
                    "role": role,
                    "lemma": lemma,
                    "synset_id": sid,
                    "domain": domain,
                    "tier": tier,
                    "status": status,
                    "reason": reason,
                })
    finally:
        conn.close()

    # Dedupe synset_ids — multiple pairs may share a lemma.
    unenriched_ids = sorted({r["synset_id"] for r in rows
                             if r["status"] == "unenriched" and r["synset_id"]})
    snap_dropped_ids = sorted({r["synset_id"] for r in rows
                               if r["status"] == "snap-dropped" and r["synset_id"]})

    SYNSET_IDS_OUT.parent.mkdir(parents=True, exist_ok=True)
    SYNSET_IDS_OUT.write_text(json.dumps(unenriched_ids, indent=2))
    print(f"Wrote {len(unenriched_ids)} synset_ids to {SYNSET_IDS_OUT}")

    # Stats by role × status (one synset per side)
    status_by_role = Counter((r["role"], r["status"]) for r in rows)
    status_total = Counter(r["status"] for r in rows)

    # Domain breakdown of the unenriched (surgical-target) cohort
    unenriched_domain = Counter(
        r["domain"] for r in rows
        if r["status"] == "unenriched"
    )

    # Sample lists for the report — focus on what surgical will and
    # won't fix.
    unenriched_samples = [
        (r["role"], r["lemma"], r["domain"], r["tier"])
        for r in rows if r["status"] == "unenriched"
    ]
    snap_dropped_samples = [
        (r["role"], r["lemma"], r["domain"], r["tier"])
        for r in rows if r["status"] == "snap-dropped"
    ]
    unresolved_samples = [
        (r["role"], r["lemma"], r["domain"], r["tier"])
        for r in rows if r["status"] == "unresolved"
    ]

    REPORT_OUT.parent.mkdir(parents=True, exist_ok=True)
    out = [
        "# M02-S04 — Apt-cohort gap synset classification",
        "",
        f"Generated from `metaphor_pairs_v2.json` ({len(pairs)} pairs, "
        f"{len(rows)} synset-sides analysed) against the live DB.",
        "",
        "## Status totals (synset-sides)",
        "",
        "| status | count | what fixes it |",
        "|---|---|---|",
        f"| unenriched | {status_total.get('unenriched', 0)} | surgical enrichment (this run) |",
        f"| snap-dropped | {status_total.get('snap-dropped', 0)} | snap retuning (S04-D) |",
        f"| unresolved | {status_total.get('unresolved', 0)} | lexicon scope expansion (not in M02) |",
        f"| has-properties | {status_total.get('has-properties', 0)} | already scoring — no action needed |",
        f"| missing-lemma | {status_total.get('missing-lemma', 0)} | data quality on apt pairs |",
        "",
        "## Breakdown by role × status",
        "",
        "| role | status | count |",
        "|---|---|---|",
    ]
    for (role, status), count in sorted(status_by_role.items()):
        out.append(f"| {role} | {status} | {count} |")
    out.extend([
        "",
        "## Unenriched targets (this surgical run will fix)",
        "",
        f"Distinct synset_ids: **{len(unenriched_ids)}** "
        f"(deduped across role and pair).",
        "",
        "Domain breakdown:",
        "",
        "| domain | count of side-instances |",
        "|---|---|",
    ])
    for dom, count in unenriched_domain.most_common():
        out.append(f"| {dom} | {count} |")
    out.extend([
        "",
        "Sample (first 30 side-instances):",
        "",
        "```",
    ])
    for role, lemma, domain, tier in unenriched_samples[:30]:
        out.append(f"  {role:>6} {lemma!s:<14} domain={domain} tier={tier}")
    out.extend([
        "```",
        "",
        f"## Snap-dropped — enrichment can't fix these "
        f"({len(snap_dropped_ids)} distinct synsets)",
        "",
        "These synsets have LLM enrichment data in `synset_properties` but "
        "every property dropped at snap (most likely `below_threshold` "
        "embedding match against curated vocab). Surgical enrichment "
        "would just re-enrich the same data; the real fix is snap "
        "threshold retuning or curated vocab expansion (S04-D in the "
        "retro plan).",
        "",
        "```",
    ])
    for role, lemma, domain, tier in snap_dropped_samples[:30]:
        out.append(f"  {role:>6} {lemma!s:<14} domain={domain} tier={tier}")
    out.extend([
        "```",
        "",
        "## Unresolved — lexicon scope issue",
        "",
        "Lemma doesn't resolve to any synset (not in `lemmas` or "
        "`property_vocab_curated` for any sense). Neither enrichment "
        "nor snap helps — the word is outside the current lexicon.",
        "",
        "```",
    ])
    for role, lemma, domain, tier in unresolved_samples[:30]:
        out.append(f"  {role:>6} {lemma!s:<14} domain={domain} tier={tier}")
    out.extend([
        "```",
        "",
        "## Next steps",
        "",
        "1. (caller) `--from-json` import the in-flight 8k partial so the "
        "surgical run's `--skip-enriched-required` flag can see what's "
        "already covered.",
        "2. (caller) Run `enrich_properties.py --synset-ids "
        "apt_gap_synset_ids.json --strategy frequency --size <N> "
        "--skip-enriched-required` where N matches `len(unenriched_ids)`. "
        "The frequency padding phase will fetch zero extras since "
        "required_ids already fills the slate.",
        "3. (downstream) Re-run M02-S04-A attrition audit to confirm "
        "the surgical lifted apt retention back toward the cognition "
        "stratum (currently 69.2% → 95.1% gap).",
    ])
    REPORT_OUT.write_text("\n".join(out))
    print(f"Wrote classification report to {REPORT_OUT}")


if __name__ == "__main__":
    main()
