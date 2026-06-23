# bad_head disambiguated — it's PHRASE IMPOVERISHMENT, not sense-snap, not syntax

**Date:** 2026-06-14. **Method:** $0 read-only forensic on the operator's 44 `bad_head`-tagged chains — joined to chain steps, intermediate `synset_id`s resolved to glosses from `lexicon_v2.db`, and the operator's free-text `notes` read verbatim. (Supersedes the hypothesis in `2026-06-14-bad-head-is-not-syntactic.md` that the real lever was the SemCor re-snap.)

## The finding
`bad_head` is **semantic head IMPOVERISHMENT**: head-extraction collapses a rich, metaphor-bearing multi-word phrase to its bare grammatical head-noun, dropping the **modifier that carries the metaphor**. The operator's own notes say this ~24× verbatim, in the shape `bad head: <evocative phrase> -> <generic word>`:

- `subterranean heat → heat` · `buried wound → wound` · `curdled warmth → warmth` (the modifier *inverts* the meaning — curdled warmth ≠ warmth) · `decorative layer → layer` · `gold leaf → leaf` · `weathered surface → surface` · `contested ground → ground` · `lost footing → footing` · `layered past → past`.

The retained noun is a grammatically-valid token (so NOT the syntactic error — that was 0/44, confirmed again), but it is a generic **"god-node"** (the operator's term: "hidden stress → stress is a god-node"). Collapsing every chain to a handful of near-synonym hubs (stress/pressure/tension/heat/wound) destroys both the metaphor *and* any path-geometry separation.

## Category counts over the 44 (evidence in the subagent report)
| Category | ~Primary | The lever it points to |
|---|---|---|
| **2. Semantic-head impoverishment** (phrase→bare-noun; modifier dropped) | **~30** | the **generation/node contract** — keep the multi-word phrase as the node |
| 1. Bad sense-snap (head word right, wrong synset) | ~2-3 flagged (**~15 present** in glosses) | SemCor re-snap — REAL but mostly UNFLAGGED; mine from glosses, not the tag |
| 5. Other / catch-all (bare "step N", "prefer X", diversity gripe) | ~11 | generation critique / corpus-diversity (a different signal) |
| 3. Endpoint-sense bug (topic snapped to wrong/verb sense) | 3 latent, 0 flagged | topic-selection sense fix (breaks canonicalisation) |
| 4. Genuine bad head-token (syntactic) | **0** | none — confirmed |

## Corrections to the record
1. **The lever is NOT SemCor re-snap.** Re-snapping the bare head can pick a better *sense of `wound`* but cannot recover the dropped modifier `buried`. So re-snap fixes ~none of the dominant 30/44. **The lever is the generation/head-extraction contract: stop collapsing phrases to bare nouns.**
2. **SemCor re-snap is a real SECONDARY lever for a SEPARATE, mostly-unflagged defect** — ~15 chains have genuinely wrong intermediate senses (`patience`→Solitaire, `wash`→break-even, `mass`→Catholic-Mass, `fire`→fireplace, `forces`→"legal validity"). Worth fixing for path geometry, but `bad_head` is a poor label-source for it; mine the glosses directly.
3. **Endpoint-sense bug (3 rows):** `anger`→sid 30227 (verb "make angry"), `anchor`→sid 23626 (verb "fix firmly") — the TOPIC endpoint itself snapped to the wrong (verb) sense, despite canonicalisation. Real latent bug in topic selection; no note flags it. (Phase B is unaffected — handpicked-324 has curated synset_ids.)

## Why this matters beyond the grading tax
- **It's the same disease as the "pressed flower" vehicle problem, at a second site.** The single-word-WordNet-node contract impoverishes intermediate *heads* (`buried wound → wound`) exactly as it drops multi-word *vehicles* (`pressed flower` → skipped). The phrase-node architecture question is not a future Level-2 concern — it is the **live cause of ~30/44 bad_head tags right now.**
- **It explains the Stage-1 judge failure (κ 0.13).** `bad_head` is a *polysemous* tag — it means impoverishment OR wrong-sense OR "I'd prefer word X" OR a bare positional pointer. No judge can learn a coherent function for a label that conflates four phenomena. The construction judge wasn't (only) failing because construction is unjudgeable; it was failing because the **label is incoherent**. A coherent construction signal requires decomposing the tag (or fixing impoverishment at source so it becomes rare + uniform).
- **It may be implicated in the dead path-geometry.** The audit found topology doesn't recur (5/248 edges). If every chain routes through the same god-node hubs, there IS no distinctive intermediate structure to recur — impoverishment could be a *cause* of the dead topology, not just a co-symptom.

## Does it block the first completion test? NO.
Completion operates on EDGES (endpoint topic→vehicle seeds), which are mostly clean (Phase B's handpicked topics are sense-clean; the endpoint-sense bug is 3 legacy rows). The impoverished intermediates are the demoted PATH layer. So: **let Phase B run, proceed to the first completion test on endpoint edges.** The phrase-node contract fix is the high-value lever for the bad_head tax + (possibly) reviving path geometry — but it's the deferred architecture brainstorm, now with evidence it's load-bearing. Do NOT hotfix mid-Phase-B; plan it deliberately.

Full evidence (all 44 rows, verbatim notes, resolved glosses, worked examples per category) in the dispatching subagent's report this session.
