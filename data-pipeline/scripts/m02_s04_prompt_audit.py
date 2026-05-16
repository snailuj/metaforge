"""M02-S04 — Prompt-quality audit on emotion-domain apt-cohort enrichments.

Three hypotheses to test for why the LLM emits abstract properties
(`cardinal`, `liminal`, `summative`) rather than sensorimotor ones
(`warm`, `dense`, `flickering`):

  H1. Model limitation — the model just isn't good at this task.
  H2. Synset-side limitation — common abstract words genuinely lack
      sensorimotor properties to extract.
  H3. Prompt limitation — the system prompt is overconstraining,
      panicking the model, or asking for too many properties.

The audit pulls the LLM's *actual* enrichment output (from
`synset_properties`) for the apt-cohort emotion-domain source words.
For each synset:
  * Lists every LLM property emitted (text, salience, type if v2)
  * Classifies each as 'physical-sensorimotor', 'emotional-abstract',
    'social-cultural', or 'other' using a simple heuristic based on
    the v2 `type` field plus a sensorimotor wordlist
  * Reports: did snap accept it? If so, against which curated entry?

Output: `data-pipeline/sweeps/M02-S04-prompt-audit-emotion.md` — the
audit material is then read by a human to triage H1/H2/H3.
"""
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from evaluate_aptness import lookup_primary_synset

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "data-pipeline" / "output" / "lexicon_v2.db"
APT_PAIRS = REPO_ROOT / "data-pipeline" / "fixtures" / "metaphor_pairs_v2.json"
OUTPUT = REPO_ROOT / "data-pipeline" / "sweeps" / "M02-S04-prompt-audit-emotion.md"

# A rough sensorimotor heuristic — properties whose text matches one of
# these regex stems is plausibly sensorimotor. Far from perfect but
# enough to surface obvious abstract / sensorimotor ratios.
SENSORIMOTOR_HINTS = {
    # texture / temperature / weight / luminosity
    "warm", "cold", "hot", "cool", "heavy", "light", "dense", "thick", "thin",
    "rough", "smooth", "soft", "hard", "sharp", "dull", "bright", "dark",
    "luminous", "shiny", "glossy", "matt", "translucent", "opaque",
    # sound / movement / pace
    "loud", "quiet", "silent", "rhythmic", "pulsing", "flickering", "rapid",
    "slow", "swift", "still", "steady", "jittery", "vibrating", "ringing",
    # taste / smell
    "bitter", "sweet", "salty", "sour", "savoury", "acrid", "fragrant",
    "pungent", "musky", "aromatic", "earthy",
    # body / posture
    "stiff", "limp", "rigid", "flexible", "supple", "yielding", "tense",
    "taut", "loose", "slack",
    # spatial / shape
    "round", "angular", "curved", "linear", "tall", "short", "wide", "narrow",
    "long", "compact", "vast", "spacious", "cramped",
    # interoception / sensation
    "tingling", "aching", "throbbing", "burning", "stinging", "itchy",
    "numb", "fluttering",
    # vivid colour
    "red", "blue", "green", "yellow", "black", "white", "grey",
}


def classify_property(prop_text, prop_type):
    """Classify a property as sensorimotor / abstract-emotional / other.

    Returns one of {'sensorimotor', 'physical-other', 'emotional',
    'social', 'effect-functional', 'behaviour', 'unknown'}.
    """
    text = (prop_text or "").lower().strip()
    if text in SENSORIMOTOR_HINTS:
        return "sensorimotor"
    if prop_type == "physical":
        return "physical-other"
    if prop_type == "emotional":
        return "emotional"
    if prop_type == "social":
        return "social"
    if prop_type in ("effect", "functional"):
        return "effect-functional"
    if prop_type == "behaviour":
        return "behaviour"
    return "unknown"


def fetch_apt_source_words(domain_filter=None):
    """Apt-pair source words. If domain_filter is given, restrict to
    that domain; otherwise return all apt source words with their
    domain so the caller can stratify."""
    with open(APT_PAIRS) as f:
        pairs = json.load(f)
    words = []
    seen = set()
    for p in pairs:
        if domain_filter is not None and p.get("domain") != domain_filter:
            continue
        src = p.get("source")
        if src and src not in seen:
            words.append((src, p.get("domain")))
            seen.add(src)
    return words


def main():
    # Decide between emotion-only (the original investigation) and
    # cross-domain (the M02-S04 sidestep — does emotion underperform
    # specifically, or is the prompt-violation pattern pervasive?).
    cross_domain = "--cross-domain" in sys.argv
    domain_filter = None if cross_domain else "emotion"
    words_with_domain = fetch_apt_source_words(domain_filter)
    label = "cross-domain" if cross_domain else "emotion-domain"
    print(f"Auditing {len(words_with_domain)} {label} apt-cohort source words")
    words = [w for w, _ in words_with_domain]
    word_domain = {w: d for w, d in words_with_domain}

    conn = sqlite3.connect(str(DB_PATH))

    # Detect property_vocabulary column shape — older builds may use
    # `text` rather than `property_text`. Probe and adapt.
    cols = [r[1] for r in conn.execute(
        "PRAGMA table_info(property_vocabulary)"
    ).fetchall()]
    text_col = "property_text" if "property_text" in cols else "text"

    try:
        sections = []
        total_props = 0
        type_counter = Counter()
        sensorimotor_counter = 0
        unenriched_words = []
        # Per-domain accumulators for the cross-domain sidestep.
        per_domain_props = Counter()
        per_domain_sensorimotor = Counter()
        per_domain_physical_typed = Counter()  # type=='physical' by LLM
        per_domain_enriched = Counter()
        per_domain_unenriched = Counter()
        per_domain_avg_per_synset_sum = Counter()

        for word in words:
            sid = lookup_primary_synset(conn, word)
            if sid is None:
                sections.append(
                    f"### `{word}` — UNRESOLVED in lexicon\n"
                )
                continue
            # Pull each LLM property exactly once. The earlier draft
            # LEFT JOIN'd synset_properties_curated on synset_id alone,
            # which produces a cartesian per LLM property × curated row
            # (e.g. 11 LLM × 10 curated = 110 inflated rows). The snap
            # status per LLM property is not a simple FK; we'd have to
            # re-run snap to recover it, which is overkill for this
            # audit. Show LLM emission shape instead.
            rows = conn.execute(
                f"""
                SELECT
                    sp.property_id,
                    pv.{text_col}    AS text,
                    sp.salience,
                    sp.property_type AS type
                FROM synset_properties sp
                JOIN property_vocabulary pv ON pv.property_id = sp.property_id
                WHERE sp.synset_id = ?
                ORDER BY sp.salience DESC, pv.{text_col}
                """,
                (sid,),
            ).fetchall()

            domain = word_domain.get(word, "?")
            if not rows:
                unenriched_words.append((word, sid))
                per_domain_unenriched[domain] += 1
                continue
            per_domain_enriched[domain] += 1
            per_domain_avg_per_synset_sum[domain] += len(rows)

            classified = []
            for pid, text, salience, ptype in rows:
                klass = classify_property(text, ptype)
                type_counter[klass] += 1
                total_props += 1
                per_domain_props[domain] += 1
                if klass == "sensorimotor":
                    sensorimotor_counter += 1
                    per_domain_sensorimotor[domain] += 1
                if ptype == "physical":
                    per_domain_physical_typed[domain] += 1
                classified.append((text, salience, ptype, klass))

            sm_count = sum(1 for c in classified if c[3] == "sensorimotor")
            section = [
                f"### `{word}` (synset `{sid}`) — {len(rows)} properties, "
                f"{sm_count} sensorimotor",
                "",
                "| text | salience | LLM type | classification |",
                "|---|---|---|---|",
            ]
            for text, salience, ptype, klass in classified:
                section.append(
                    f"| `{text}` | {salience:.2f} | "
                    f"{ptype or '—'} | {klass} |"
                )
            sections.append("\n".join(section) + "\n")

        sensorimotor_pct = (
            100.0 * sensorimotor_counter / total_props if total_props else 0
        )

        # Top abstract/emotional/effect properties across the cohort —
        # these are what's diluting the sensorimotor signal.
        # Pull and re-summarise.
        all_texts_by_class = {
            "sensorimotor": Counter(),
            "physical-other": Counter(),
            "emotional": Counter(),
            "social": Counter(),
            "effect-functional": Counter(),
            "behaviour": Counter(),
            "unknown": Counter(),
        }
        # Re-walk the data to populate top-text-by-class (cheap; cached
        # synset list).
        for word in words:
            sid = lookup_primary_synset(conn, word)
            if sid is None:
                continue
            rows = conn.execute(
                f"""
                SELECT pv.{text_col}, sp.property_type
                FROM synset_properties sp
                JOIN property_vocabulary pv ON pv.property_id = sp.property_id
                WHERE sp.synset_id = ?
                """, (sid,),
            ).fetchall()
            for text, ptype in rows:
                klass = classify_property(text, ptype)
                all_texts_by_class[klass][text] += 1

        title = f"M02-S04 — Prompt-quality audit ({label} apt cohort)"
        out = [
            f"# {title}",
            "",
            f"**DB:** `{DB_PATH.relative_to(REPO_ROOT)}`  ",
            f"**Cohort:** {len(words)} {label} apt-pair source "
            f"words.  ",
            f"**Generator:** `data-pipeline/scripts/m02_s04_prompt_audit.py"
            f"{' --cross-domain' if cross_domain else ''}`",
            "",
            "Three hypotheses under test:",
            "",
            "- **H1 — Model limitation:** the model just isn't good at "
            "  extracting sensorimotor properties.",
            "- **H2 — Synset-side limitation:** common abstract words "
            "  genuinely lack sensorimotor properties to extract.",
            "- **H3 — Prompt limitation:** the system prompt is "
            "  overconstraining, or asking for too many properties, "
            "  pushing the model into abstract-vocab panic.",
            "",
            "## Headline",
            "",
            f"- Words audited: **{len(words)}** "
            f"({len(unenriched_words)} unenriched, "
            f"{len(words) - len(unenriched_words)} have LLM properties).",
            f"- Total LLM properties across the cohort: **{total_props}**",
            f"- Properties matching the sensorimotor wordlist: "
            f"**{sensorimotor_counter}** ({sensorimotor_pct:.1f}%)",
            "",
            "### Classification mix",
            "",
            "| class | count | % |",
            "|---|---|---|",
        ]
        for klass, count in type_counter.most_common():
            pct = 100.0 * count / total_props if total_props else 0
            out.append(f"| {klass} | {count} | {pct:.1f}% |")

        # Per-domain stratification — only meaningful in cross-domain mode
        if cross_domain:
            out.extend([
                "",
                "### Per-domain stratification",
                "",
                "The prompt says ≥4 physical-typed properties per synset "
                "(10–15 properties total). The columns below test whether "
                "abstract domains (emotion/cognition/society) under-emit "
                "physical-typed properties relative to concrete domains "
                "(body/nature) — i.e. does the under-emission pattern "
                "track abstractness or is it pervasive?",
                "",
                "| domain | enriched | unenriched | avg props/synset | "
                "physical-typed/synset | sensorimotor (heuristic) % |",
                "|---|---|---|---|---|---|",
            ])
            all_domains = sorted(set(word_domain.values()))
            for d in all_domains:
                e = per_domain_enriched.get(d, 0)
                u = per_domain_unenriched.get(d, 0)
                props = per_domain_props.get(d, 0)
                avg_per = (per_domain_avg_per_synset_sum.get(d, 0) / e
                           if e else 0)
                phys_per = (per_domain_physical_typed.get(d, 0) / e
                            if e else 0)
                sm_pct = (100.0 * per_domain_sensorimotor.get(d, 0) / props
                          if props else 0)
                out.append(
                    f"| {d} | {e} | {u} | {avg_per:.1f} | "
                    f"{phys_per:.1f} | {sm_pct:.1f}% |"
                )

        out.extend([
            "",
            "### Most-frequent properties per class (top 10 each)",
            "",
        ])
        for klass in ("sensorimotor", "physical-other", "emotional",
                      "behaviour", "effect-functional", "social", "unknown"):
            top = all_texts_by_class[klass].most_common(10)
            if not top:
                continue
            out.append(f"**{klass}**")
            out.append("")
            out.append("```")
            for text, count in top:
                out.append(f"  {count:>3}  {text}")
            out.append("```")
            out.append("")

        if unenriched_words:
            out.extend([
                "## Unenriched emotion-domain source words",
                "",
                "These resolve to a synset but have ZERO entries in "
                "`synset_properties` — the LLM hasn't been pointed at "
                "them yet at all. Surgical enrichment (S04 sub-task) "
                "would fix these.",
                "",
                "```",
            ])
            for word, sid in unenriched_words:
                out.append(f"  {word!s:<14}  synset_id={sid}")
            out.append("```")
            out.append("")

        out.extend([
            "## Per-word enrichment dump",
            "",
            "Full LLM output for each enriched word, with each property "
            "classified and its snap status shown. Read these to triage "
            "H1/H2/H3 — is the model emitting sensorimotor properties? "
            "Did snap accept them? Is the property mix dominated by "
            "abstract/effect categories the prompt arguably encourages?",
            "",
        ])
        out.extend(sections)

        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text("\n".join(out))
        print(f"Wrote {OUTPUT}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
