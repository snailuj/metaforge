"""Stage-2 liveness/pairing judge — the Forge Reader on (topic, vehicle) pairs.

Plan §5: the unit judged is the topic -> vehicle PAIRING, never the chain.
Feeding the intermediate steps would import lazy-path noise (a meandering
chain can still end at a live pairing, and vice versa), so build_prompt
renders ONLY the two endpoints with their glosses — chain steps, tags, notes
and the item's own gold fields must never reach the prompt. This also makes
bad_head rows judgeable for free: the endpoints are canonicalised, so the
pairing stays valid even where the chain extraction broke.

The persona preamble is distilled from
data-pipeline/grading/liveness_judge_persona.md ("the Forge Reader"),
collapsing its 0-10 rubric to the binary the harness scores: LIVE (the 7+
"hit" bar) vs DEAD.

Default model is sonnet (the live-metaphor engine); the harness drives a
haiku baseline through the same make_judge(model=...) seam to quantify the
lift, so model stays parameterised.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling judge_llm

import judge_llm  # noqa: E402  (import-safe offline: CLI path loads lazily)

DEFAULT_MODEL = "sonnet"

# Public so callers (tests, transcript tooling) can locate the judged item —
# everything before it is preamble + examples, everything after is the item.
ITEM_HEADER = "Now judge this pairing:"

PERSONA = (
    "You are the Forge Reader: a working genre-fiction novelist and acquiring "
    "editor (science fiction, fantasy, horror, thriller, crime). You have "
    "read ten thousand manuscripts and you judge with a sharp, unsentimental "
    "eye whether a metaphor works for a reader curled up with a paperback — "
    "you are not a literature academic, and 'literary' means well-crafted, "
    "never highbrow.\n"
    "\n"
    "Judge the single topic -> vehicle metaphor pairing for liveness.\n"
    "LIVE = a fresh, surprising-yet-apt cross-domain image: the gut-punch "
    "that makes a reader stop and re-see the topic, the pairing a writer "
    "would lift straight into prose.\n"
    "DEAD = a cliche (anger is fire, time is money, broken heart), a "
    "near-synonym or same-domain restatement with no real jump to a "
    "different concrete domain, or an inert pairing the eye slides past.\n"
    "\n"
    "Do not reward a cliche for being clear or relatable: familiar = dead. "
    "Do not punish a pairing for being pulpy, vivid or genre — punch is the "
    "target, not restraint. Most pairings are average; you have a slush pile "
    "and a deadline."
)

_FORMAT_RULE = ('Respond with ONLY strict JSON, exactly one of: '
                '{"verdict": "live"} or {"verdict": "dead"}.')


def _endpoint(word, gloss) -> str:
    """`word (pos: definition)`, degrading gracefully — the contract allows
    topic_gloss/vehicle_gloss to be None, and a gloss may lack pos."""
    definition = (gloss or {}).get("definition")
    if not definition:
        return str(word)
    pos = (gloss or {}).get("pos")
    return f"{word} ({pos}: {definition})" if pos else f"{word} ({definition})"


def _pairing(row: dict) -> str:
    return (f"{_endpoint(row['topic'], row.get('topic_gloss'))} -> "
            f"{_endpoint(row['vehicle'], row.get('vehicle_gloss'))}")


def build_prompt(few_shot: list[dict], item: dict) -> str:
    """Pairing-only prompt: persona + class-balanced examples + the item.

    Reads ONLY topic/vehicle (+ glosses) from every row — never the chain,
    tags or notes, and never the item's own gold fields (a prompt that varies
    with the gold label measures leakage, not skill). Few-shot rows must carry
    the liveness_rows y_live stamp; a missing key fails loudly rather than
    silently rendering an unlabelled example.
    """
    lines = [PERSONA, ""]
    if few_shot:
        lines += ["Examples:", ""]
        for ex in few_shot:
            verdict = "live" if int(ex["y_live"]) == 1 else "dead"
            lines += [_pairing(ex), f'{{"verdict": "{verdict}"}}', ""]
    lines += [ITEM_HEADER, _pairing(item), "", _FORMAT_RULE]
    return "\n".join(lines)


def parse_verdict(raw) -> int:
    """{"verdict": "live"|"dead"} -> 1|0. Case/surrounding whitespace are
    normalised (the only benign drift a JSON-constrained output shows);
    anything else — wrong key, wrong type, a hedged string — is a
    JudgeAbstain, never a guess."""
    verdict = raw.get("verdict") if isinstance(raw, dict) else None
    if isinstance(verdict, str):
        verdict = verdict.strip().lower()
    if verdict == "live":
        return 1
    if verdict == "dead":
        return 0
    raise judge_llm.JudgeAbstain(f"unparseable stage-2 verdict: {raw!r}")


def make_judge(model: str = DEFAULT_MODEL, prompt_fn=None, cache_path=None):
    """JudgeFn `(few_shot, item) -> 0/1` for the liveness axis (y_live)."""
    return judge_llm.make_llm_judge(build_prompt, parse_verdict, model,
                                    prompt_fn=prompt_fn, cache_path=cache_path)
