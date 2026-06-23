"""One-time LLM sense-disambiguation pass — the hard sense-accuracy gate.

`lexicon_v2.db` carries no sense-frequency data (WordNet/SemCor tagcounts were
never imported), so the deterministic heuristics (least-polysemous synset,
lowest synset_id) mis-pick the dominant sense of common words — house ->
'playing house', feel -> genital, must -> 'grape juice'. Mass-generating
metaphors on those senses is garbage.

This pass picks the everyday sense properly: for each frequency-head content
lemma it presents ALL noun senses to a cheap model (Haiku) and takes the
dominant everyday sense, or ABSTAINS when none is clearly dominant. Output is a
vetted topics file ({word, topic_synset_id, gloss}) the generation runner
consumes directly. Lemmas are BATCHED per call so the ~$0.06 cold-call floor
amortises (≈ $20-50 for ~10k lemmas, vs ~$600 per-lemma).

DB reads are plain SQL; LLM access is injected (prompt_fn) for testing.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))  # claude_client

log = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-haiku-4-5-20251001"

# Closed-class + ultra-common-but-not-a-concept words whose noun-senses are poor
# metaphor topics. Conservative: removes obvious junk, keeps real concepts
# (anger, time, fire, river...). (Copied verbatim from the superseded
# select_topics.py.)
STOP = set("""
the and for was are but not you all can her his out day get has him how man new now
old see two way who boy did its let put say she too use any try ask men run own end few
lot yes yet set got per via etc inc the there here will know good back look right well
this that with from they have been were what when your said each which their them then
than upon onto into over under about above below such very just only also more most some
many much both came come does done dont cant wont thats whats hes shes its
one two three four five six seven eight nine ten able away done gone okay sure
am is be do go he hi if in it me my no of on or so to up us we
""".split())


# ---------------------------------------------------------------------------
# Candidate selection (DB)
# ---------------------------------------------------------------------------

def wn_noun_primary(conn: sqlite3.Connection, lemma: str) -> bool:
    """Free WordNet POS-dominance heuristic: is `lemma` PRIMARILY a noun?

    True iff it has >=1 noun sense AND noun senses >= verb senses AND noun
    senses > adjective senses. This catches the verb-heavy (overlook n1/v5) and
    adjective-heavy (possible n2/a2, kosher n1/s2) sneak-ins for free. It still
    MISSES gerunds (WordNet nominalises `-ing`, so browsing reads noun-only) and
    balanced noun-heavy-but-verb-used words (thaw n3/v1) — those need usage
    frequency the DB lacks; the grading loop filters that residual.
    """
    rows = dict(conn.execute(
        "SELECT s.pos, COUNT(*) FROM lemmas l JOIN synsets s ON s.synset_id = l.synset_id "
        "WHERE l.lemma = ? GROUP BY s.pos",
        (lemma,),
    ).fetchall())
    n = rows.get("n", 0)
    v = rows.get("v", 0)
    a = rows.get("a", 0) + rows.get("s", 0)  # WordNet adjective + satellite-adjective
    return n >= 1 and n >= v and n > a


def head_lemmas(conn: sqlite3.Connection, *, limit: int = 10000, min_zipf: float = 2.5,
                noun_primary_only: bool = True) -> list[dict]:
    """Frequency-head content lemmas that are enriched nouns, zipf-desc.

    A lemma qualifies if it has at least one curated, enriched NOUN synset and a
    zipf >= min_zipf and length >= 3. Stopwords are dropped, and (default)
    non-noun-primary lemmas are dropped via the free WordNet POS heuristic.
    Returns at most `limit` rows after filtering.
    """
    rows = conn.execute(
        """
        SELECT pvc.lemma AS lemma, MAX(f.zipf) AS zipf
        FROM property_vocab_curated pvc
        JOIN frequencies f               ON f.lemma = pvc.lemma
        JOIN synsets s                   ON s.synset_id = pvc.synset_id
        JOIN synset_properties_curated spc ON spc.synset_id = pvc.synset_id
        WHERE pvc.pos = 'n' AND f.zipf IS NOT NULL AND f.zipf >= ?
          AND length(pvc.lemma) >= 3
        GROUP BY pvc.lemma
        ORDER BY zipf DESC
        """,
        (min_zipf,),
    ).fetchall()
    out: list[dict] = []
    for lemma, zipf in rows:
        if lemma.strip().lower() in STOP:
            continue
        if noun_primary_only and not wn_noun_primary(conn, lemma):
            continue
        out.append({"lemma": lemma, "zipf": zipf})
        if len(out) >= limit:
            break
    return out


def candidate_senses(conn: sqlite3.Connection, lemma: str) -> list[dict]:
    """All noun senses of `lemma`, as [{synset_id, gloss}], stable order.

    Drops obvious junk glosses ('letter of the alphabet') so the model never has
    to consider them."""
    rows = conn.execute(
        """
        SELECT s.synset_id, s.definition
        FROM lemmas l JOIN synsets s ON s.synset_id = l.synset_id
        WHERE l.lemma = ? AND s.pos = 'n'
        ORDER BY s.synset_id
        """,
        (lemma,),
    ).fetchall()
    return [
        {"synset_id": sid, "gloss": defn}
        for sid, defn in rows
        if "letter of the" not in (defn or "").lower()
    ]


def select_candidate_topics(conn: sqlite3.Connection, *, limit: int = 10000, min_zipf: float = 2.5,
                            noun_primary_only: bool = True) -> list[dict]:
    """Head lemmas with their candidate noun senses: [{lemma, zipf, senses}]."""
    out: list[dict] = []
    for row in head_lemmas(conn, limit=limit, min_zipf=min_zipf, noun_primary_only=noun_primary_only):
        senses = candidate_senses(conn, row["lemma"])
        if senses:
            out.append({"lemma": row["lemma"], "zipf": row["zipf"], "senses": senses})
    return out


def _norm_gloss(s: str) -> str:
    return " ".join((s or "").lower().split())


def vetted_topics_from_glossed(
    conn: sqlite3.Connection,
    glossed: list[dict],
    *,
    prompt_fn=None,
    model: str = DEFAULT_MODEL,
    chunk_size: int = 30,
) -> list[dict]:
    """Resolve a PRE-GLOSSED cohort (e.g. the 200 spike topics: {word, gloss})
    to vetted {word, topic_synset_id, gloss} with maximum confidence and minimum
    spend:

      1. exact gloss->synset match  (the curated gloss IS a synset definition),
      2. single-sense lemma         (no ambiguity),
      3. otherwise LLM-disambiguate  (only the genuinely ambiguous remainder).

    The curated input gloss is preserved on output (it pins the intended sense);
    only the synset_id is resolved. Words with no noun sense are dropped.
    """
    resolved: list[dict] = []
    need_llm: list[dict] = []
    for g in glossed:
        word, gloss = g["word"], g["gloss"]
        senses = candidate_senses(conn, word)
        if not senses:
            log.info("drop %r: no noun sense", word)
            continue
        exact = [s for s in senses if _norm_gloss(s["gloss"]) == _norm_gloss(gloss)]
        if exact:
            resolved.append({"word": word, "topic_synset_id": exact[0]["synset_id"], "gloss": gloss})
        elif len(senses) == 1:
            resolved.append({"word": word, "topic_synset_id": senses[0]["synset_id"], "gloss": gloss})
        else:
            need_llm.append({"lemma": word, "gloss": gloss, "senses": senses})

    # Disambiguate the genuine remainder by GLOSS-MATCH (steered by the curated
    # gloss), not dominant-sense — so the synset_id is consistent with the gloss.
    if prompt_fn is None:
        from claude_client import prompt_json
        prompt_fn = prompt_json
    gloss_by_word = {c["lemma"]: c["gloss"] for c in need_llm}
    for chunk in _chunks(need_llm, chunk_size):
        prompt = build_gloss_match_prompt(chunk)
        try:
            raw = prompt_fn(prompt, model=model)
        except Exception as exc:  # noqa: BLE001 — a chunk failure abstains, never crashes
            log.warning("gloss-match chunk failed (abstained): %s", exc)
            continue
        items = [{"lemma": c["lemma"], "senses": c["senses"]} for c in chunk]
        for o in parse_disambiguation_batch(raw if isinstance(raw, dict) else {}, items):
            resolved.append({**o, "gloss": gloss_by_word.get(o["word"], o["gloss"])})
    return resolved


# ---------------------------------------------------------------------------
# Disambiguation prompt + parse (pure)
# ---------------------------------------------------------------------------

def build_disambiguation_prompt(items: list[dict]) -> str:
    """Prompt asking for the dominant everyday noun sense per lemma (or abstain)."""
    blocks = []
    for it in items:
        lines = [f'LEMMA "{it["lemma"]}":']
        for i, s in enumerate(it["senses"], 1):
            lines.append(f'  {i}. {s["gloss"]}')
        blocks.append("\n".join(lines))
    body = "\n\n".join(blocks)
    return f"""You disambiguate word senses for a metaphor dataset.

For each LEMMA below, choose the ONE sense that an everyday speaker means by
default — the dominant, most common, ordinary sense of the noun. Ignore
technical, archaic, slang, or obscure senses unless that genuinely is the
everyday meaning.

If NO sense is clearly the dominant everyday one (the lemma is genuinely
ambiguous, or every sense is technical/obscure), ABSTAIN by returning null for
sense_index — do not guess. Abstaining is correct and safe; a wrong everyday
sense pollutes the dataset.

{body}

Respond with STRICT JSON and nothing else. sense_index is the 1-based number of
the chosen sense, or null to abstain:
{{"picks": [{{"lemma": "<lemma>", "sense_index": <int or null>}}, ...]}}"""


def build_gloss_match_prompt(items: list[dict]) -> str:
    """Prompt asking which candidate sense MATCHES a given target gloss.

    Distinct from build_disambiguation_prompt (dominant-everyday-sense): a
    pre-glossed cohort already encodes the intended sense in its gloss, so the
    synset must be picked to MATCH that gloss, not by frequency."""
    blocks = []
    for it in items:
        lines = [f'LEMMA "{it["lemma"]}"  — target meaning: {it["gloss"]}', "  candidate senses:"]
        for i, s in enumerate(it["senses"], 1):
            lines.append(f'    {i}. {s["gloss"]}')
        blocks.append("\n".join(lines))
    body = "\n\n".join(blocks)
    return f"""You align word senses to a target meaning for a metaphor dataset.

For each LEMMA below, choose the candidate sense whose meaning is the SAME as
(or closest to) the given target meaning. The target meaning is authoritative —
pick the sense that matches it, NOT the most common sense.

If NO candidate sense matches the target meaning, ABSTAIN by returning null for
sense_index — do not force a poor match.

{body}

Respond with STRICT JSON and nothing else. sense_index is the 1-based number of
the matching sense, or null to abstain:
{{"picks": [{{"lemma": "<lemma>", "sense_index": <int or null>}}, ...]}}"""


def parse_disambiguation_batch(raw: dict, items: list[dict]) -> list[dict]:
    """Map model picks back to vetted topics. Conservative: a missing lemma,
    null/garbled index, or out-of-range index is DROPPED (abstain), never
    guessed."""
    by_lemma = {it["lemma"]: it for it in items}
    picks = raw.get("picks", []) if isinstance(raw, dict) else []
    out: list[dict] = []
    for pk in picks:
        if not isinstance(pk, dict):
            continue
        lemma = pk.get("lemma")
        idx = pk.get("sense_index")
        it = by_lemma.get(lemma)
        if it is None or not isinstance(idx, int) or isinstance(idx, bool):
            continue
        if idx < 1 or idx > len(it["senses"]):
            continue
        sense = it["senses"][idx - 1]
        out.append({"word": lemma, "topic_synset_id": sense["synset_id"], "gloss": sense["gloss"]})
    return out


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def _chunks(seq: list, n: int):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def _read_checkpoint(path: str | None) -> dict:
    """word -> resolved topic dict, from a checkpoint JSONL (for resume)."""
    if not path or not Path(path).exists():
        return {}
    done: dict[str, dict] = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                log.warning("checkpoint: skipping malformed line")
                continue
            if d.get("word"):
                done[d["word"]] = d
    return done


def _append_checkpoint(path: str | None, topic: dict) -> None:
    if not path:
        return
    with open(path, "a") as f:
        f.write(json.dumps(topic, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def disambiguate(candidates: list[dict], *, prompt_fn=None, model: str = DEFAULT_MODEL,
                 chunk_size: int = 30, checkpoint_path: str | None = None) -> list[dict]:
    """Resolve candidates to vetted topics — resumable + observable.

    Single-sense lemmas are auto-accepted (no LLM cost). Multi-sense lemmas are
    batched to the model; a chunk whose call fails abstains that chunk and the
    run continues. Each resolved topic is flushed to `checkpoint_path` as it is
    produced, and already-checkpointed lemmas are skipped on resume — so a crash
    in a hours-long pass loses at most one chunk, never the whole run.
    """
    if prompt_fn is None:
        from claude_client import prompt_json
        prompt_fn = lambda p, model: prompt_json(p, model=model, max_retries=3)

    done = _read_checkpoint(checkpoint_path)
    resolved: list[dict] = list(done.values())
    seen = set(done)

    for c in candidates:
        if len(c["senses"]) == 1 and c["lemma"] not in seen:
            t = {"word": c["lemma"], "topic_synset_id": c["senses"][0]["synset_id"],
                 "gloss": c["senses"][0]["gloss"]}
            resolved.append(t)
            seen.add(c["lemma"])
            _append_checkpoint(checkpoint_path, t)

    multi = [c for c in candidates if len(c["senses"]) > 1 and c["lemma"] not in seen]
    n_chunks = (len(multi) + chunk_size - 1) // chunk_size
    for i, chunk in enumerate(_chunks(multi, chunk_size), 1):
        prompt = build_disambiguation_prompt(chunk)
        try:
            raw = prompt_fn(prompt, model=model)
        except Exception as exc:  # noqa: BLE001 — a chunk failure abstains, never crashes the pass
            log.warning("disambiguation chunk %d/%d failed (abstained): %s", i, n_chunks, exc)
            continue
        items = [{"lemma": c["lemma"], "senses": c["senses"]} for c in chunk]
        for t in parse_disambiguation_batch(raw if isinstance(raw, dict) else {}, items):
            resolved.append(t)
            _append_checkpoint(checkpoint_path, t)
        log.info("disambiguation chunk %d/%d done (%d topics resolved so far)", i, n_chunks, len(resolved))
    return resolved


def write_topics_file(topics: list[dict], path: str) -> None:
    """Write a runner-ingestible vetted topics file."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps({"n": len(topics), "topics": topics}, indent=1, ensure_ascii=False)
    )


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="LLM sense-disambiguation -> vetted topics file.")
    ap.add_argument("--db", default="data-pipeline/output/lexicon_v2.db")
    ap.add_argument("--limit", type=int, default=10000, help="how many head lemmas")
    ap.add_argument("--min-zipf", type=float, default=2.5)
    ap.add_argument("--chunk-size", type=int, default=30, help="lemmas per Haiku call")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("-o", "--output", default="data-pipeline/output/generation_topics_vetted.json")
    ap.add_argument("--no-pos-filter", action="store_true",
                    help="keep verb/adjective-primary lemmas (default drops them via WordNet POS ratio).")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    try:
        cands = select_candidate_topics(conn, limit=args.limit, min_zipf=args.min_zipf,
                                        noun_primary_only=not args.no_pos_filter)
    finally:
        conn.close()
    n_multi = sum(1 for c in cands if len(c["senses"]) > 1)
    log.info("candidates: %d noun-primary lemmas (%d need disambiguation, %d single-sense)",
             len(cands), n_multi, len(cands) - n_multi)

    # Checkpoint alongside the output → resumable + observable. Re-run to resume.
    checkpoint = args.output + ".partial.jsonl"
    topics = disambiguate(cands, model=args.model, chunk_size=args.chunk_size,
                          checkpoint_path=checkpoint)
    write_topics_file(topics, args.output)
    log.info("wrote %d vetted topics (%d abstained) -> %s  [checkpoint: %s]",
             len(topics), len(cands) - len(topics), args.output, checkpoint)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
