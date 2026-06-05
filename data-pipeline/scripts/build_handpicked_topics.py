#!/usr/bin/env python3
"""Build a hand-curated topics file for the generation runner.

SemCor hasn't landed, so the frequency-head auto-selector still lets
verb/function lemmas sneak in via a rare noun sense. This bypasses that
entirely: a human-curated list of noun-DOMINANT, conceptually-rich words
(good metaphor topics), each resolved to its primary NOUN synset + gloss,
with a belt-and-braces noun-dominance check (noun senses >= verb senses)
dropping anything that slipped through.

Output: {n, topics:[{word, topic_synset_id, gloss}]} — the runner's format.
Deduped against an existing topics file (the already-generated 200 cohort).
"""
from __future__ import annotations
import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Curated, noun-dominant, metaphor-rich words. Grouped only for review; order
# is irrelevant. Deliberately excludes bare verbs / function words and words
# whose dominant sense is verbal (the sneak-in failure mode).
WORDS: list[str] = [
    # emotion / affect
    "grief", "longing", "dread", "euphoria", "melancholy", "serenity", "anguish",
    "jealousy", "nostalgia", "awe", "resentment", "elation", "despair", "remorse",
    "contempt", "trepidation", "sorrow", "panic", "envy", "gratitude", "humiliation",
    "ecstasy", "loneliness", "bitterness", "yearning", "foreboding", "infatuation",
    "tenderness", "apprehension", "indignation", "exhilaration", "desolation",
    "rapture", "wrath", "agitation", "complacency", "discontent", "wistfulness",
    # cognition / mind
    "intuition", "obsession", "delusion", "epiphany", "amnesia", "clarity",
    "confusion", "insight", "conviction", "paranoia", "fixation", "reverie",
    "premonition", "scepticism", "curiosity", "imagination", "perception",
    "concentration", "introspection", "denial", "certainty", "ambivalence",
    "preoccupation", "hindsight", "foresight", "delirium", "stupor", "lucidity",
    # social / relational
    "alliance", "rivalry", "betrayal", "loyalty", "hierarchy", "kinship",
    "solidarity", "estrangement", "reconciliation", "conformity", "camaraderie",
    "mentorship", "feud", "truce", "diplomacy", "hospitality", "reputation",
    "prestige", "stigma", "scandal", "propaganda", "ostracism", "courtship",
    "fellowship", "rapport", "intimacy", "allegiance", "factionalism",
    # moral / ethical
    "integrity", "hypocrisy", "virtue", "corruption", "cruelty", "mercy",
    "redemption", "atonement", "piety", "temptation", "innocence", "depravity",
    "nobility", "treachery", "honour", "deceit", "righteousness", "villainy",
    "purity", "wickedness", "candour", "duplicity", "magnanimity",
    # conflict / power
    "tyranny", "rebellion", "conquest", "siege", "mutiny", "insurgency",
    "oppression", "domination", "resistance", "subjugation", "uprising",
    "blockade", "stalemate", "surrender", "retaliation", "vendetta", "crusade",
    "persecution", "ambush", "skirmish", "onslaught", "reprisal", "annexation",
    # time / change
    "decay", "momentum", "stagnation", "transition", "renewal", "erosion",
    "demise", "genesis", "epoch", "inertia", "culmination", "aftermath",
    "prelude", "threshold", "brink", "resurgence", "obsolescence", "infancy",
    "twilight", "dawn", "watershed", "turning point", "heyday",
    # process / abstract / physics-flavoured
    "equilibrium", "symmetry", "friction", "turbulence", "cascade", "convergence",
    "divergence", "oscillation", "resonance", "entropy", "catalyst", "fusion",
    "gravitation", "feedback", "amplification", "saturation", "fracture",
    "momentum", "trajectory", "vortex", "tension", "leverage", "ripple",
    "undercurrent", "groundswell", "spiral", "crescendo",
    # communication / language
    "rhetoric", "eloquence", "satire", "allegory", "irony", "paradox", "riddle",
    "manifesto", "sermon", "confession", "testimony", "narrative", "monologue",
    "silence", "whisper", "echo", "murmur", "cadence", "rumour", "innuendo",
    "platitude", "diatribe", "eulogy", "prophecy", "lament", "anthem",
    # nature / phenomena (as topics)
    "wilderness", "drought", "famine", "deluge", "avalanche", "eruption",
    "tempest", "eclipse", "mirage", "undertow", "whirlpool", "quicksand",
    "wildfire", "frost", "harvest", "migration", "hibernation", "metamorphosis",
    "monsoon", "blizzard", "tundra", "wasteland", "tide", "current",
    # aesthetic / quality
    "elegance", "grandeur", "splendour", "squalor", "austerity", "opulence",
    "harmony", "dissonance", "symmetry", "minimalism", "ornament", "patina",
    "lustre", "radiance", "decadence", "refinement", "vulgarity", "subtlety",
    # institution / structure / belief
    "bureaucracy", "monarchy", "democracy", "oligarchy", "empire", "regime",
    "doctrine", "ideology", "orthodoxy", "dogma", "sect", "syndicate", "cartel",
    "monopoly", "establishment", "regimen", "protocol", "ritual", "tradition",
    "institution", "fraternity", "covenant",
    # body / sensation (metaphor-rich)
    "pulse", "heartbeat", "nerve", "sinew", "marrow", "scar", "wound", "fever",
    "ache", "numbness", "vertigo", "hunger", "thirst", "exhaustion", "adrenaline",
    "shiver", "tremor", "flush", "spasm", "pang",
    # economy / value
    "poverty", "wealth", "debt", "bankruptcy", "inflation", "surplus", "scarcity",
    "abundance", "speculation", "windfall", "ransom", "bounty", "tribute",
    "famine", "dividend", "recession", "boom", "glut", "deficit",
    # structure / journey / space (concrete-but-evocative)
    "labyrinth", "crossroads", "frontier", "horizon", "abyss", "summit",
    "precipice", "sanctuary", "fortress", "citadel", "threshold", "gateway",
    "crucible", "anchor", "compass", "beacon", "lighthouse", "scaffold",
    "foundation", "keystone", "bridge", "chasm", "fault line", "watershed",
    # misc abstract / states
    "chaos", "order", "void", "limbo", "purgatory", "oblivion", "destiny",
    "fate", "fortune", "doom", "salvation", "ruin", "legacy", "myth", "legend",
    "taboo", "omen", "curse", "blessing", "miracle", "illusion", "facade",
    "veneer", "mosaic", "tapestry", "kaleidoscope", "spectrum", "continuum",
]


# Words whose primary-noun resolution lands on a rare/technical sense, NOT the
# common one a reader expects (the intra-noun sense-selection gap SemCor would
# close). Reviewed by hand from the resolved glosses; dropped rather than
# shipped with a misleading gloss. There's ample surplus, so dropping costs
# nothing. (e.g. melancholy->kidney humour, empire->apple, order->architecture,
# monopoly->board game, riddle->sieve, inflation->filling-with-air.)
DROP_WRONG_SENSE = {
    "melancholy", "jealousy", "ecstasy", "bitterness", "epiphany", "clarity",
    "preoccupation", "conviction", "eruption", "empire", "regime", "pulse",
    "sinew", "boom", "flush", "bridge", "order", "riddle", "legend", "abundance",
    "inflation", "resonance", "monopoly", "lustre", "ripple", "surrender",
    "horizon", "renewal",
}


def _noun_senses(conn, lemma):
    return conn.execute(
        "SELECT s.synset_id, s.definition FROM lemmas l JOIN synsets s "
        "ON l.synset_id = s.synset_id WHERE l.lemma = ? AND s.pos = 'n'",
        (lemma,),
    ).fetchall()


def _pos_counts(conn, lemma):
    rows = conn.execute(
        "SELECT s.pos, COUNT(*) FROM lemmas l JOIN synsets s "
        "ON l.synset_id = s.synset_id WHERE l.lemma = ? GROUP BY s.pos",
        (lemma,),
    ).fetchall()
    return {pos: n for pos, n in rows}


def resolve(conn, lemma, *, trust_curation=False):
    """Return (synset_id, gloss) for the primary NOUN sense, or None.

    Always drops a word with no noun sense. Without `trust_curation`, also
    drops words whose verb senses outnumber noun senses — a crude POS guard
    for FREQUENCY-selected lists (the SemCor-gap sneak-in mode). For a
    HAND-curated list the human already judged dominance-in-usage, and the
    WordNet sense-COUNT ratio false-drops common nouns with many rare verb
    senses (hunger/ache/doom/eclipse), so trust_curation relaxes it to
    noun-exists-only."""
    from metaphor_graph import lookup_primary_synset
    noun = _noun_senses(conn, lemma)
    if not noun:
        return None, "no_noun_sense"
    if not trust_curation:
        counts = _pos_counts(conn, lemma)
        n_noun, n_verb = counts.get("n", 0), counts.get("v", 0)
        if n_noun < n_verb:                   # not noun-dominant -> sneak-in risk
            return None, f"verb_dominant(n={n_noun},v={n_verb})"
    # Prefer the curated/primary resolver's pick when it lands on a noun sense;
    # else take the first noun sense (lemmas are ordered least-polysemous first
    # in the curated build, a reasonable dominant-sense proxy pre-SemCor).
    primary = lookup_primary_synset(conn, lemma)
    by_id = {sid: defn for sid, defn in noun}
    if primary in by_id:
        return primary, by_id[primary]
    return noun[0][0], noun[0][1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--exclude", default=None, help="Existing topics JSON to dedupe against.")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--limit", type=int, default=None, help="Cap the number of topics emitted.")
    ap.add_argument("--trust-curation", action="store_true",
                    help="Relax the verb-dominance guard (hand-curated list) -> drop only no-noun-sense.")
    args = ap.parse_args()

    exclude_words, exclude_sids = set(), set()
    if args.exclude:
        ex = json.load(open(args.exclude))
        for t in ex.get("topics", ex if isinstance(ex, list) else []):
            exclude_words.add(t["word"].lower())
            exclude_sids.add(str(t["topic_synset_id"]))

    conn = sqlite3.connect(args.db)
    topics, dropped, seen = [], [], set()
    try:
        for w in WORDS:
            wl = w.lower()
            if wl in seen or wl in exclude_words:
                continue
            seen.add(wl)
            if wl in DROP_WRONG_SENSE:
                dropped.append((w, "wrong_sense_resolution"))
                continue
            sid, info = resolve(conn, wl, trust_curation=args.trust_curation)
            if sid is None:
                dropped.append((w, info))
                continue
            if str(sid) in exclude_sids:
                dropped.append((w, "synset_already_done"))
                continue
            topics.append({"word": w, "topic_synset_id": str(sid), "gloss": info})
            if args.limit and len(topics) >= args.limit:
                break
    finally:
        conn.close()

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    json.dump({"n": len(topics), "topics": topics}, open(args.output, "w"), indent=2)
    print(f"kept {len(topics)} topics -> {args.output}")
    print(f"dropped {len(dropped)} (sneak-in guard / no-noun / dup):")
    for w, why in dropped:
        print(f"  - {w}: {why}")


if __name__ == "__main__":
    main()
