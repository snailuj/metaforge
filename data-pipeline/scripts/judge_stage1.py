"""Stage-1 construction (linkage) judge — structural rubric, NOT the liveness
persona (plan §4).

Builds the prompt for one chain-construction verdict and parses the model's
reply back to the y_link convention (1 = bad linkage). The rubric forces "bad"
on the three structural faults the operator tags — bad_head (head mis-extracted
from its phrase), leap (unjustified jump between adjacent steps) and merge (a
leap hidden behind accumulated context: the step is licensed only by the two
priors taken together, breaking the context-free-hop requirement; currently
inert in live data, kept for forward-compat) — while padding (a
bloated-but-valid path) stays "good".
Liveness, aptness and vividness are explicitly out of scope: Stage-2 owns the
pairing judgement and Stage-1 must not import it.

Rows may arrive context-free (no attach_chain_context join): a missing or empty
chain renders as "(chain unavailable)" rather than crashing — the judge then
sees only the endpoints, and a poor verdict there is a measurement the harness
should record, not an exception.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS_DIR))  # sibling judge_llm

import judge_llm  # noqa: E402

EXAMPLES_HEADER = "## Worked examples"
ITEM_HEADER = "## Chain to judge"

# The structural contract: do NOT judge metaphor quality here.
_RUBRIC = """\
You are reviewing the STRUCTURE of metaphor derivation chains. A chain walks
from a topic concept to a vehicle concept through intermediate steps; each
step has a head word extracted from a longer phrase.

Judge ONLY the construction of the chain — not whether the metaphor is apt,
vivid or alive. The verdict is "bad" if ANY of these structural faults is
present:

- bad head: a step's head word is mis-extracted from its phrase (the head is
  not what the phrase is about);
- leap: a hop between adjacent steps is an unjustified jump, with no shared
  sense licensing the move;
- merge: a leap hidden behind accumulated context — a step that does not
  follow from its immediate predecessor alone, only from the previous two
  steps taken together (the two priors acting as one multi-word concept
  smeared across two links). Every hop must be context-free: a step must
  license its successor by itself, without leaning on the step before it.

A bloated-but-valid path (padding: redundant yet individually justified
steps) is "good" — verbosity is not a structural fault."""

_RESPONSE_DEMAND = ('Respond with STRICT JSON and nothing else: '
                    '{"verdict": "good"} or {"verdict": "bad"}.')

_VERDICT_TO_Y = {"bad": 1, "good": 0}  # y_link convention: 1 = bad linkage

_JSON_OBJECT_RE = re.compile(r"\{.*?\}", re.DOTALL)


def _gloss_suffix(gloss) -> str:
    if not gloss or not gloss.get("definition"):
        return ""
    pos = gloss.get("pos")
    return f" ({pos}: {gloss['definition']})" if pos else f" ({gloss['definition']})"


def _render_steps(chain) -> str:
    if not chain:
        return "  (chain unavailable)"
    lines = []
    for i, step in enumerate(chain, start=1):
        head = step.get("head") or step.get("phrase") or "?"
        phrase = step.get("phrase")
        # The phrase rides beside the head ONLY when extraction changed it —
        # that contrast is exactly what a bad_head verdict hinges on.
        aside = f' — from "{phrase}"' if phrase and phrase != head else ""
        lines.append(f"  {i}. {head}{aside}")
    return "\n".join(lines)


def _render_chain_block(row: dict) -> str:
    return "\n".join([
        f"Topic: {row.get('topic')}{_gloss_suffix(row.get('topic_gloss'))}",
        f"Vehicle: {row.get('vehicle')}{_gloss_suffix(row.get('vehicle_gloss'))}",
        "Chain:",
        _render_steps(row.get("chain")),
    ])


def build_prompt(few_shot: list[dict], item: dict) -> str:
    """Rubric, k worked examples (chain + gold verdict), then the item LAST and
    verdict-free — the prompt must be byte-identical whatever the item's gold
    label is (the leakage property the harness asserts hardest)."""
    parts = [_RUBRIC]
    if few_shot:
        examples = [EXAMPLES_HEADER]
        for i, ex in enumerate(few_shot, start=1):
            # Index y_link directly: a non-construction row here is a
            # programming error and must surface, not render a blank verdict.
            verdict = "bad" if int(ex["y_link"]) else "good"
            examples.append(f"### Example {i}\n{_render_chain_block(ex)}\n"
                            f"Verdict: {verdict}")
        parts.extend(examples)
    parts.append(f"{ITEM_HEADER}\n{_render_chain_block(item)}")
    parts.append(_RESPONSE_DEMAND)
    return "\n\n".join(parts)


def _candidate_objects(text: str) -> list:
    """Every parseable JSON object embedded in a string reply. The reply is
    json.loads-ed whole first (the strict-compliance path), then scanned for
    {...} snippets — models pad with prose/code fences despite instructions."""
    try:
        return [json.loads(text)]
    except ValueError:
        pass
    objects = []
    for match in _JSON_OBJECT_RE.finditer(text):
        try:
            objects.append(json.loads(match.group(0)))
        except ValueError:
            continue
    return objects


def parse_verdict(raw) -> int:
    """Map a model reply to y_link: 1 = bad, 0 = good; JudgeAbstain otherwise.

    raw is whatever judge_llm hands over: prompt_json yields a parsed dict,
    but a cached transcript or custom prompt_fn may yield a string.

    Tolerance decision: prose-wrapped JSON (code fences, "Sure! {...}") is
    accepted — the embedded object is unambiguous and abstaining on it would
    only re-spend. Bare non-JSON words ("good") abstain: without a JSON anchor
    a substring match could silently invert polarity. If a reply carries BOTH
    polarities (e.g. an echo of the instruction line) it is ambiguous and
    abstains rather than trusting first-match order. Verdict strings are
    case/whitespace-normalised; anything non-string (numerics included) is
    off-contract and abstains.
    """
    objects = _candidate_objects(raw) if isinstance(raw, str) else [raw]
    verdicts = set()
    for obj in objects:
        if not isinstance(obj, dict):
            continue
        verdict = obj.get("verdict")
        if isinstance(verdict, str) and verdict.strip().lower() in _VERDICT_TO_Y:
            verdicts.add(_VERDICT_TO_Y[verdict.strip().lower()])
    if len(verdicts) != 1:
        raise judge_llm.JudgeAbstain(f"unparseable stage-1 verdict: {raw!r}")
    return verdicts.pop()


def make_judge(model: str = "haiku", prompt_fn=None, cache_path=None):
    """Stage-1 JudgeFn: (few_shot, item) -> 0/1, cached + abstention-bounded
    by judge_llm. Haiku by default — the κ harness, not hand-tuning, decides
    whether a bigger model earns its cost (plan §7)."""
    return judge_llm.make_llm_judge(build_prompt, parse_verdict, model,
                                    prompt_fn=prompt_fn, cache_path=cache_path)
