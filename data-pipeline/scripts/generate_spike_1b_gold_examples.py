"""One-off Sonnet pass to generate gold few-shot examples for Phase 1b.

Architecture: Sonnet-as-prompt-engineer. We run Sonnet ONCE on three
example topics chosen to be outside the 20-topic Phase 1b test set, for
both the apt and inapt prompts. The resulting JSON objects are written
to ``spike_1b_gold_examples.json`` and baked into the Phase 1b runner's
few-shot block. After that, Phase 1b uses Haiku-only — Sonnet's
contribution is amortised across all 40 Haiku calls.

Example topics (deliberately disjoint from Phase 1b's 20 test topics):
    love       — Lakoff-classic emotion abstraction
    knowledge  — abstract noun with rich metaphor inventory
    fear       — emotion with beast / cold / paralysis canonical mappings

Usage::

    python data-pipeline/scripts/generate_spike_1b_gold_examples.py \\
        --output data-pipeline/scripts/spike_1b_gold_examples.json

Idempotent: re-running overwrites the output file with a fresh Sonnet
sample. Commit the output file to git so Phase 1b is reproducible
without re-incurring the Sonnet cost.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from claude_client import prompt_json, ClaudeError
from metaphor_spike_1a import (
    build_apt_prompt,
    build_inapt_prompt,
    validate_apt_response,
    validate_inapt_response,
    MODEL_SONNET,
)

log = logging.getLogger(__name__)


EXAMPLE_TOPICS: list[dict[str, str]] = [
    {
        "word": "love",
        "gloss": "a strong feeling of affection or care toward another",
    },
    {
        "word": "knowledge",
        "gloss": "what is known; facts and understanding acquired through experience or learning",
    },
    {
        "word": "fear",
        "gloss": "an unpleasant feeling caused by perceived danger or threat",
    },
]


def generate(output: Path) -> None:
    """Run Sonnet on the example topics, write a structured JSON file.

    Output shape::

        {
          "model": "claude-sonnet-4-6",
          "topics": [
            {
              "word": "love",
              "gloss": "...",
              "apt":   {...full apt response...},
              "inapt": {...full inapt response...}
            },
            ...
          ]
        }

    Validation failures abort the run — a malformed gold example would
    poison Haiku's few-shot context and we'd rather know now.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    results: list[dict] = []
    for topic in EXAMPLE_TOPICS:
        word = topic["word"]
        gloss = topic["gloss"]
        log.info("topic=%s", word)

        apt_prompt = build_apt_prompt(word, gloss)
        try:
            apt = prompt_json(apt_prompt, model=MODEL_SONNET, expect=dict)
        except ClaudeError as e:
            raise SystemExit(f"Sonnet apt call failed for {word!r}: {e}") from e
        v_apt = validate_apt_response(apt)
        if not v_apt.schema_ok:
            raise SystemExit(
                f"Sonnet apt response failed validation for {word!r}: "
                f"{v_apt.schema_errors}"
            )
        log.info("  apt ok: %d vehicles, %d concepts (%d single-word)",
                 v_apt.n_vehicles, v_apt.n_concepts, v_apt.n_single_word_concepts)

        inapt_prompt = build_inapt_prompt(word, gloss)
        try:
            inapt = prompt_json(inapt_prompt, model=MODEL_SONNET, expect=dict)
        except ClaudeError as e:
            raise SystemExit(f"Sonnet inapt call failed for {word!r}: {e}") from e
        v_inapt = validate_inapt_response(inapt)
        if not v_inapt.schema_ok:
            raise SystemExit(
                f"Sonnet inapt response failed validation for {word!r}: "
                f"{v_inapt.schema_errors}"
            )
        log.info("  inapt ok: %d vehicles", v_inapt.n_vehicles)

        # Drop any LLM-echoed gloss key — keep the JSON tight.
        apt.pop("_gloss", None)
        inapt.pop("_gloss", None)
        results.append({"word": word, "gloss": gloss, "apt": apt, "inapt": inapt})

    payload = {"model": MODEL_SONNET, "topics": results}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("wrote %s (%d topics)", output, len(results))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--output", type=Path,
        default=Path(__file__).resolve().parent / "spike_1b_gold_examples.json",
        help="Path to write the gold examples JSON (default: alongside this script).",
    )
    args = ap.parse_args(argv)
    generate(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
