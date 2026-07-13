# Batch 4 — the Phrase-as-Node success-criteria measurement (2026-07-13)

*24 fresh out-of-sample topics, RANDOM unfiltered v2 stock (no endpoint filter, no judge prediction), graded blind in the guided walk. This is the wild-conditions verdict on the P-a-N build.*

## Scorecard vs the spec (§9)

| Metric | Target | Batch 4 | Verdict |
|---|---|---|---|
| `bad_sense` (incl. interior) | ≤10% | **8/24 = 33%** (batch 3: 33%) | **MISSED — unchanged** |
| `bad_head` | ~0 | **5/24 = 21%** (batch 3: 25%) | **MISSED — reframed (below)** |
| Verdicts/signatures resolving | all | all | ✅ |
| Judge κ | no worse than 0.524 | 0.515, band tightened [0.451,0.551] | ✅ |
| Vehicle-skip in next gen run | 0 | not yet measurable (no gen run) | pending |

## The two residual diseases, now precisely named

**1. `bad_sense` 33% = wrong-NOUN-sense at snap time, interior steps (2/3/4).**
Exactly the class the migration could NOT touch (it fixed cross-POS only; same
glosses + embed → same noun picks). All 8 cites are interior. One new subclass
(operator note, undertow→siphon): *"this lemma has no good sense for the
intended meaning"* — a **sense-gap**, where NO WordNet sense fits the model's
intent; strictly outside any snapper's reach, points at the sense-SET/vec
endgame. Candidate levers, in rough cost order: (a) LLM re-snap pass over
suspect/flagged steps only (cheap, targeted); (b) distinctive-token weighting
in the embed match; (c) accept-and-correct at grading (the fan makes every
mis-snap visible + fixable, but it taxes the operator ~1 tag per 3 chains).

**2. `bad_head` 21% = SEMANTIC impoverishment, not display impoverishment.**
Checked against the corpus: every cited step carries its full multi-word phrase
(`tangled passage`, `thorned growth`, `no-return point`, `collective pulling`,
`narcotic bloom`, `resistant formation`) and displays phrase-first. What the
operator is tagging: the step's **semantic identity is the bare head's synset**
("tangled passage" *is* a "passage" sense to the graph/judge), so the modifier
that carries the metaphor has no semantic representation and the hop-logic
breaks ("loses 'tangled'", "loses 'no-return', breaks everything"). The
phrase-as-node contract fixed capture + display; the remaining layer is
**phrase-level semantics** — a hybrid identity for snapped multi-word steps
(head synset + FastText phrase-vector, i.e. treat them as syn+vec dual nodes)
so hop geometry reads the phrase, not the head. This is the natural Block-2
completion and feeds directly into Path Completion's geometry.

## Bright spots

- **Live-rate 62% (15/24)** on random unfiltered stock vs ~33% on batch 3's
  filtered draw — suggestive (n=24, sample luck possible) that corrected-sense
  reading substantially raises the live yield; consistent with the re-grade
  fold where sense-fixes flipped dead→live almost uniformly.
- Structural tags collapsed otherwise: 2 padding, 2 leap — the chains are
  mostly sound; the residual defects are concentrated in the two named classes.
- **Sense ticks: 0/24 used.** The fan was used diagnostically (8 bad_sense
  tags) but no co-aptness ticks — either nothing felt genuinely co-apt, the
  affordance doesn't fit grading flow, or ticking feels like extra tax.
  Operator input wanted before drawing a conclusion.

## Recommendation

The P-a-N core did its job (capture, display, correctability, gold-healing,
κ-band tightening) — mark the milestone landed. The two residuals are new,
precisely-scoped work items, and both point the same way as the flat completion
curve: **semantic precision per step** (LLM re-snap for wrong-noun-sense +
phrase-vector semantics for multi-word steps) **before** Path Completion reads
step geometry. Neither needs a big-bang build; both are targeted follow-ups.
