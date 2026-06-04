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

def head_lemmas(conn: sqlite3.Connection, *, limit: int = 10000, min_zipf: float = 2.5) -> list[dict]:
    """Frequency-head content lemmas that are enriched nouns, zipf-desc.

    A lemma qualifies if it has at least one curated, enriched NOUN synset and a
    zipf >= min_zipf and length >= 3. Stopwords are dropped. Returns at most
    `limit` rows after filtering.
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


def select_candidate_topics(conn: sqlite3.Connection, *, limit: int = 10000, min_zipf: float = 2.5) -> list[dict]:
    """Head lemmas with their candidate noun senses: [{lemma, zipf, senses}]."""
    out: list[dict] = []
    for row in head_lemmas(conn, limit=limit, min_zipf=min_zipf):
        senses = candidate_senses(conn, row["lemma"])
        if senses:
            out.append({"lemma": row["lemma"], "zipf": row["zipf"], "senses": senses})
    return out


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


def disambiguate(candidates: list[dict], *, prompt_fn=None, model: str = DEFAULT_MODEL,
                 chunk_size: int = 30) -> list[dict]:
    """Resolve candidates to vetted topics.

    Single-sense lemmas are auto-accepted (no LLM cost — no ambiguity to
    resolve). Multi-sense lemmas are batched to the model; a chunk whose call
    fails abstains that chunk and the run continues.
    """
    if prompt_fn is None:
        from claude_client import prompt_json
        prompt_fn = prompt_json

    resolved: list[dict] = [
        {"word": c["lemma"], "topic_synset_id": c["senses"][0]["synset_id"], "gloss": c["senses"][0]["gloss"]}
        for c in candidates if len(c["senses"]) == 1
    ]
    multi = [c for c in candidates if len(c["senses"]) > 1]
    for chunk in _chunks(multi, chunk_size):
        prompt = build_disambiguation_prompt(chunk)
        try:
            raw = prompt_fn(prompt, model=model)
        except Exception as exc:  # noqa: BLE001 — a chunk failure abstains, never crashes the pass
            log.warning("disambiguation chunk failed (abstained): %s", exc)
            continue
        resolved.extend(parse_disambiguation_batch(raw if isinstance(raw, dict) else {}, chunk))
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
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    try:
        cands = select_candidate_topics(conn, limit=args.limit, min_zipf=args.min_zipf)
    finally:
        conn.close()
    n_multi = sum(1 for c in cands if len(c["senses"]) > 1)
    log.info("candidates: %d lemmas (%d need disambiguation, %d single-sense)",
             len(cands), n_multi, len(cands) - n_multi)

    topics = disambiguate(cands, model=args.model, chunk_size=args.chunk_size)
    write_topics_file(topics, args.output)
    log.info("wrote %d vetted topics (%d abstained) -> %s",
             len(topics), len(cands) - len(topics), args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
