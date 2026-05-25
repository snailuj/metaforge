"""M02-S04 — A/B test the `physical` → `sensorimotor` prompt rename.

Hypothesis: renaming the `physical` type field to `sensorimotor` will
shift how the model tags perceptual-descriptor properties on abstract
synsets. The audit (`M02-S04-prompt-audit-emotion.md`) found that
words like `heavy`, `warm`, `burning` on `grief` were getting tagged
as `emotional` rather than `physical` — because the model parses
"physical" as a property of the SYNSET (is grief physical? no), not
of the property word (is heavy a physical descriptor? yes).

"Sensorimotor" plausibly cleaves that interpretation: it can only be
read as "does this word describe a perception/movement?" — which has
a different (and correct-for-our-purpose) answer.

This script:
  1. Holds a copy of BATCH_PROMPT_V2 with every instance of `physical`
     swapped for `sensorimotor` in the type field, type definitions,
     and worked examples. The minimum-count rule (≥4) is preserved.
  2. Picks 5 already-enriched emotion-domain apt-cohort synsets so we
     can compare existing tags vs new tags directly.
  3. Runs one-synset batches via the same claude_client.prompt_json
     path as production. ~$0.25 total cost.
  4. Writes a side-by-side comparison to
     `data-pipeline/sweeps/M02-S04-prompt-rename-test.md`.

Does NOT modify the production prompt or DB. The output JSONs are
inspection-only.
"""
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from claude_client import prompt_json
from evaluate_aptness import lookup_primary_synset

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "data-pipeline" / "output" / "lexicon_v2.db"
OUTPUT = REPO_ROOT / "data-pipeline" / "sweeps" / "M02-S04-prompt-rename-test.md"

# Test cohort: 5 emotion-domain words from the M02-S04-A apt-cohort
# audit, all already enriched under the existing prompt so we can A/B.
TEST_WORDS = ["grief", "love", "anxiety", "contentment", "shame"]

# Multi-domain cohort for the regression + curiosity sweep:
#   * body (concrete) — regression check: did rename break what was
#     already working (5.6 physical/synset under the old prompt)?
#   * society + relationship (abstract) — curiosity: does the rename
#     deliver the same dramatic lift as it did for emotion?
TEST_WORDS_MULTI_DOMAIN = [
    # body — concrete, regression check
    ("body", "blood"),
    ("body", "bone"),
    ("body", "fist"),
    # society — abstract, curiosity
    ("society", "authority"),
    ("society", "censorship"),
    ("society", "bureaucracy"),
    # relationship — abstract, curiosity
    ("relationship", "betrayal"),
    ("relationship", "devotion"),
    ("relationship", "enmity"),
]

# Prompt body — verbatim copy of BATCH_PROMPT_V2 in enrich_properties.py
# with EXACTLY the following substitutions:
#   * "physical" (when referring to the type field value) → "sensorimotor"
#   * type-list definitions: the "physical:" line label → "sensorimotor:"
#   * worked-example tags: "physical" → "sensorimotor"
#   * the ≥4 minimum rule: "type "physical"" → "type "sensorimotor""
# Other text (e.g. "concrete nouns", "physical qualities" in explanatory
# prose) is left unchanged — those are domain-level statements about
# the world, not type-field instructions.
BATCH_PROMPT_V2_SM = """You are extracting sensory and behavioural properties for specific word senses, with salience weights and metadata.

These properties power a metaphor discovery engine that finds cross-domain conceptual links between unrelated words. For example, "anger" connects to "fire" via shared properties like "destructive", "consuming", "intense". Prioritise properties that could bridge between concepts from different domains — the more transferable and evocative a property, the more valuable it is.

CRITICAL: The definition tells you WHICH sense of the word to analyse. Many words have multiple meanings — focus ONLY on the sense described in the definition.

For each word sense, provide:

1. **usage_example**: A natural sentence using the word in this specific sense.

2. **properties**: 10-15 properties, each as a JSON object:
   - "text": exactly ONE word (no hyphens, no compounds, no spaces)
     GOOD: flickering, frigid, shrill, dense, molten, conical, pungent
     BAD: cold metal (two words), high-pitched (hyphenated), lava-formed (compound)
     If you need "cold metal", choose ONE word: frigid, metallic, or icy
   - "salience": 0.0-1.0 — how immediately/strongly this property comes to mind for this concept
     - 0.9-1.0: Defining, inescapable (fire → hot, ice → cold)
     - 0.6-0.8: Strong association (fire → dangerous, ice → slippery)
     - 0.3-0.5: Secondary/contextual (fire → ancient, ice → seasonal)
   - "type": one of "sensorimotor", "behaviour", "effect", "functional", "emotional", "social"
   - "relation": short phrase linking word to property (e.g. "fire emits heat")

   Property types:
   - sensorimotor: texture, weight, temperature, luminosity, sound, colour, shape, size, material, smell, taste. Sensorimotor properties are the primary bridge for cross-domain metaphors (concrete → abstract).
   - behaviour: speed, rhythm, intensity, duration, pattern of movement
   - effect: what it causes, its consequences, its aftermath
   - functional: what it does, enables, or is used for
   - emotional: feelings it evokes or is associated with
   - social: cultural, relational, or status associations

   IMPORTANT: At least 4 of your properties must have type "sensorimotor". Most concrete nouns
   have at least 4 sensorimotor qualities. If the concept genuinely has fewer, include as many
   as truly apply.

3. **lemma_metadata**: For EACH listed lemma, provide:
   - "lemma": the word form
   - "register": "formal", "neutral", "informal", or "slang"
   - "connotation": "positive", "neutral", or "negative"

IMPORTANT: in your output, **use the exact ID string from the input** for each synset. The IDs are opaque tokens — do not prefix them with `oewn-`, do not append `-n`/`-v`/`-a`, do not guess a format. Whatever ID appeared after `ID:` in the input is what you should put in the `id` field of your output object.

Examples:

ID: 12345
Word: candle
Lemmas: candle, taper
Definition: stick of wax with a wick; gives light when burning

{{"id": "12345", "usage_example": "She lit a candle and watched the flame flicker in the draught.", "properties": [{{"text": "warm", "salience": 0.9, "type": "sensorimotor", "relation": "candle emits warmth"}}, {{"text": "flickering", "salience": 0.85, "type": "behaviour", "relation": "flame flickers"}}, {{"text": "ephemeral", "salience": 0.7, "type": "effect", "relation": "candle burns away"}}, {{"text": "luminous", "salience": 0.8, "type": "sensorimotor", "relation": "candle gives light"}}, {{"text": "waxy", "salience": 0.75, "type": "sensorimotor", "relation": "made of wax"}}, {{"text": "fragile", "salience": 0.6, "type": "sensorimotor", "relation": "wick is delicate"}}, {{"text": "aromatic", "salience": 0.5, "type": "effect", "relation": "scented candles smell"}}, {{"text": "ceremonial", "salience": 0.4, "type": "social", "relation": "used in rituals"}}, {{"text": "intimate", "salience": 0.65, "type": "emotional", "relation": "evokes closeness"}}, {{"text": "ancient", "salience": 0.3, "type": "social", "relation": "pre-electric lighting"}}], "lemma_metadata": [{{"lemma": "candle", "register": "neutral", "connotation": "positive"}}, {{"lemma": "taper", "register": "formal", "connotation": "neutral"}}]}}

ID: 67890
Word: volcano
Lemmas: volcano
Definition: a mountain formed by volcanic material

{{"id": "67890", "usage_example": "The volcano erupted, sending a plume of ash into the sky.", "properties": [{{"text": "hot", "salience": 0.95, "type": "sensorimotor", "relation": "volcano radiates extreme heat"}}, {{"text": "conical", "salience": 0.8, "type": "sensorimotor", "relation": "volcano has cone shape"}}, {{"text": "towering", "salience": 0.85, "type": "sensorimotor", "relation": "volcano is very tall"}}, {{"text": "molten", "salience": 0.9, "type": "sensorimotor", "relation": "contains molten lava"}}, {{"text": "ashy", "salience": 0.7, "type": "sensorimotor", "relation": "produces ash"}}, {{"text": "eruptive", "salience": 0.85, "type": "behaviour", "relation": "volcano erupts violently"}}, {{"text": "destructive", "salience": 0.75, "type": "effect", "relation": "eruptions destroy surroundings"}}, {{"text": "dormant", "salience": 0.5, "type": "behaviour", "relation": "may be inactive for years"}}, {{"text": "rumbling", "salience": 0.65, "type": "sensorimotor", "relation": "produces low sounds"}}, {{"text": "ancient", "salience": 0.4, "type": "social", "relation": "geological timescale"}}], "lemma_metadata": [{{"lemma": "volcano", "register": "neutral", "connotation": "negative"}}]}}
(NOT: magmatic, pyroclastic, geological — these are taxonomic labels, not experiential properties)

Now extract properties for each of these word senses:

{batch_items}

Output ONLY a valid JSON array (no markdown, no explanation):
[{{"id": "...", "usage_example": "...", "properties": [...], "lemma_metadata": [...]}}, ...]
"""


def fetch_synset_meta(conn, synset_id):
    """(lemma, definition, pos) for the synset's most-familiar lemma."""
    row = conn.execute(
        """
        WITH ranked AS (
            SELECT l.lemma, s.definition, s.pos,
                   COALESCE(f.familiarity, 0) AS fam,
                   ROW_NUMBER() OVER (
                       PARTITION BY s.synset_id
                       ORDER BY COALESCE(f.familiarity, 0) DESC, l.lemma
                   ) AS rn
            FROM synsets s
            JOIN lemmas l ON l.synset_id = s.synset_id
            LEFT JOIN frequencies f ON f.lemma = l.lemma
            WHERE s.synset_id = ?
        )
        SELECT lemma, definition, pos FROM ranked WHERE rn = 1
        """,
        (synset_id,),
    ).fetchone()
    return row


def existing_enrichment(conn, synset_id):
    """List of (text, salience, type) for the synset's existing
    enrichment (per synset_properties)."""
    cols = [r[1] for r in conn.execute(
        "PRAGMA table_info(property_vocabulary)"
    ).fetchall()]
    text_col = "property_text" if "property_text" in cols else "text"
    rows = conn.execute(
        f"""
        SELECT pv.{text_col}, sp.salience, sp.property_type
        FROM synset_properties sp
        JOIN property_vocabulary pv ON pv.property_id = sp.property_id
        WHERE sp.synset_id = ?
        ORDER BY sp.salience DESC, pv.{text_col}
        """,
        (synset_id,),
    ).fetchall()
    return rows


def format_one_synset_prompt_items(synset_id, lemma, definition):
    """One-synset batch item for the BATCH_PROMPT_V2_SM template."""
    return (
        f"ID: {synset_id}\n"
        f"Word: {lemma}\n"
        f"Lemmas: {lemma}\n"
        f"Definition: {definition}\n"
    )


def run_one(conn, word):
    """Resolve word → synset → call LLM under the renamed prompt →
    return (synset_id, lemma, definition, new_properties_list).
    """
    sid = lookup_primary_synset(conn, word)
    if sid is None:
        return None
    meta = fetch_synset_meta(conn, sid)
    if not meta:
        return None
    lemma, definition, pos = meta
    batch_items = format_one_synset_prompt_items(sid, lemma, definition)
    prompt = BATCH_PROMPT_V2_SM.format(batch_items=batch_items)
    results = prompt_json(prompt, model="sonnet", expect=list)
    if not results or not isinstance(results, list):
        return None
    r = results[0]
    return {
        "synset_id": sid,
        "lemma": lemma,
        "definition": definition,
        "new_properties": r.get("properties", []),
    }


def main():
    multi_domain = "--multi-domain" in sys.argv
    if multi_domain:
        cohort = TEST_WORDS_MULTI_DOMAIN
        words = [w for _, w in cohort]
        word_to_domain = {w: d for d, w in cohort}
        out_path = REPO_ROOT / "data-pipeline" / "sweeps" / \
            "M02-S04-prompt-rename-multidomain.md"
        title_suffix = " (multi-domain: body, society, relationship)"
    else:
        words = TEST_WORDS
        word_to_domain = {w: "emotion" for w in words}
        out_path = OUTPUT
        title_suffix = " (emotion cohort)"
    conn = sqlite3.connect(str(DB_PATH))
    try:
        out = [
            f"# M02-S04 — Prompt rename A/B test{title_suffix}",
            "",
            f"Test cohort: **{words}**. Each word's existing "
            "enrichment (under the `physical` prompt) is shown next to a "
            "fresh enrichment under the renamed `sensorimotor` prompt. "
            "Watch for tag drift on sensorimotor-rooted descriptors "
            "(`heavy`, `warm`, `burning`, `bright`, etc.) — these should "
            "move from `emotional`/`effect` into `sensorimotor` on the "
            "abstract synsets if the rename is doing the work.",
            "",
        ]
        per_word_sm_count = {}
        per_word_existing_phys_count = {}
        per_word_total_new = {}
        per_word_total_existing = {}
        for word in words:
            print(f"Calling LLM under renamed prompt for {word}...")
            res = run_one(conn, word)
            if res is None:
                out.append(f"## `{word}` — could not resolve or call failed.\n")
                continue
            sid = res["synset_id"]
            existing = existing_enrichment(conn, sid)
            new_props = res["new_properties"]

            existing_phys = [p for p in existing if p[2] == "physical"]
            new_sm = [p for p in new_props if p.get("type") == "sensorimotor"]
            per_word_sm_count[word] = len(new_sm)
            per_word_existing_phys_count[word] = len(existing_phys)
            per_word_total_new[word] = len(new_props)
            per_word_total_existing[word] = len(existing)

            domain = word_to_domain.get(word, "?")
            out.extend([
                f"## `{word}` (synset `{sid}`, domain={domain})",
                "",
                f"**Definition:** {res['definition']}",
                "",
                f"**Existing enrichment (current prompt, `physical` tag):** "
                f"{len(existing_phys)}/{len(existing)} tagged `physical`.",
                "",
                "| text | salience | type |",
                "|---|---|---|",
            ])
            for text, salience, ptype in existing:
                marker = " 🎯" if ptype == "physical" else ""
                out.append(f"| `{text}` | {salience:.2f} | {ptype or '—'}{marker} |")
            out.extend([
                "",
                f"**New enrichment (renamed prompt, `sensorimotor` tag):** "
                f"{len(new_sm)}/{len(new_props)} tagged `sensorimotor`.",
                "",
                "| text | salience | type |",
                "|---|---|---|",
            ])
            for p in new_props:
                ptype = p.get("type")
                marker = " 🎯" if ptype == "sensorimotor" else ""
                out.append(
                    f"| `{p.get('text', '')}` | {p.get('salience', 0):.2f} | "
                    f"{ptype or '—'}{marker} |"
                )
            out.append("")

        # Headline summary
        out.extend([
            "## A/B Summary",
            "",
            "| word | domain | existing total/`physical` | new total/`sensorimotor` | "
            "delta |",
            "|---|---|---|---|---|",
        ])
        for w in words:
            ex_phys = per_word_existing_phys_count.get(w, "—")
            ex_total = per_word_total_existing.get(w, "—")
            sm = per_word_sm_count.get(w, "—")
            new_total = per_word_total_new.get(w, "—")
            dom = word_to_domain.get(w, "?")
            if isinstance(ex_phys, int) and isinstance(sm, int):
                delta = f"+{sm - ex_phys}" if sm >= ex_phys else f"{sm - ex_phys}"
            else:
                delta = "n/a"
            out.append(
                f"| `{w}` | {dom} | {ex_total}/{ex_phys} | "
                f"{new_total}/{sm} | {delta} |"
            )
        out.extend([
            "",
            "**Verdict heuristics:**",
            "- If the rename consistently shifts sensorimotor-rooted "
            "descriptors (`heavy`, `warm`, `burning`, `bright`) into the "
            "`sensorimotor` tag where they were `emotional`/`effect` "
            "before, the conflation was the binding bug.",
            "- If new sensorimotor counts are still ≪ 4 across the "
            "cohort, the rename alone wasn't enough — escalate to the "
            "tagging-disambiguation clarification or the count drop.",
            "- If counts swing wildly or quality regresses, the rename "
            "destabilised the prompt — revert and try a softer change.",
        ])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(out))
        print(f"Wrote {out_path}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
