# Can Fable 5 grade? — blind agreement experiment + the sense-noise finding

**Date:** 2026-07-03
**Branch:** `metaphor-graph/judge-harness`
**Context:** Operator asked whether the Fable 5 main-loop model could grade
metaphors well enough to bootstrap gold tonight. Gold can't be minted by a
model (κ is fit-to-Julian; the judged corpus IS his taste), so instead we ran
Fable as a *blind judge* against Julian's existing final-form gold and measured
κ(Fable, Julian) directly, then Julian adjudicated every disagreement.

## Method

- Blind set: 41 liveness pairings from the post-floor final-form gold
  (`--gold-since 2026-06-11`, sense-suspects excluded), with the 6 render-exposed
  verdicts held out. Fable saw only `topic (gloss) -> vehicle (gloss)` — no chain,
  tags, notes, or gold label.
- Fable graded live/dead with a one-line reason each.
- Scored against Julian's gold; Julian then adjudicated all 19 disagreements
  inline (confirm / flip / "wrong sense").

## Result — three lenses

| lens | n | agreement | κ |
|---|---|---|---|
| A. Raw blind (naive) | 41 | 0.537 | **0.167** |
| B. Sense-cleaned only (quarantines removed, no taste flips — UNANCHORED) | 34 | 0.647 | **0.311** |
| C. + taste adjudications (partly circular — Fable argued Julian toward its verdicts) | 34 | 0.824 | **0.598** |

**Headline = B.** Fable zero-shot, after removing gold rows whose recorded
sense ≠ the sense Julian graded, agrees at **κ 0.311 — statistically level with
the tuned Sonnet judge's 0.332** (measured against the same gold). No few-shot,
no persona, no calibration. C (0.598) is the ceiling if Fable also learns the
residual boundary cases, but Fable helped move that target, so it is NOT the
result — it's an optimistic bound.

⚠️ n=34 is small; all three κ have wide bands. Directional, not validated.

## The finding that matters: the gold is sense-contaminated, and it caps EVERY judge

**44% of the disagreements (7 of ~16 non-duplicate) were gold sense-mismatches,
not taste.** Julian repeatedly graded a more vivid/different sense than the
pipeline recorded:

| pairing | Julian graded | recorded synset | verdict at recorded sense |
|---|---|---|---|
| optics → eye | seeing organ | "central area within a region" (eye of storm) | dead |
| outset → overture | musical prelude | "tentative diplomatic suggestion" | dead |
| outset → threshold | physical doorway | "abstract starting point" | dead (restatement) |
| foreboding → smoke | concrete smoke rising | "indication of hidden activity" (figurative) | dead (synonym) |
| nostalgia → ruin | verb *to ruin* | noun "a ruined building" | dead |
| publicity → aperture | camera iris (exposure control) | "man-made opening, usually small" | dead |
| anchor → tendon | (misread) | verb "fix firmly and stably" | dead |

All 7 quarantined to `gold_sense_suspect.jsonl` (10 rows total with the 3 from
the earlier enactment pass), status `pending_regrade`.

**Implication:** Sonnet's κ 0.332 was ALSO measured against this ~1-in-6
sense-noisy gold. Cleaning the gold (re-grade at correct sense) should lift the
measured κ of *every* candidate judge. **The binding lever on the judge is not
model choice — it is the snapper/sense-fidelity of the vehicle (Track B
phrase-as-node).** This converges with the whole programme thesis yet again.

## Fable's residual genuine-taste errors (named, symmetric, few-shot-able)

- **Too generous on apt-but-familiar.** `anxiety → quicksand` (both chains):
  Fable graded live on mechanistic aptness (struggling makes you sink = the
  phenomenology). Julian holds dead: worry-as-quicksand is *overused*, and
  **familiar = dead even when the mechanism is apt.** Fable under-weighted
  overuse vs mechanism.
- **Too strict on "affective shadow" pairings.** Julian holds live where the
  vehicle imports a connotation the topic lacks:
  - `euphoria → vertigo`, `euphoria → combustion` — the vehicle carries a
    darker/self-consuming edge that recolours the bright topic; that dark shadow
    IS the leap, even when the surface mapping looks near-synonymous.
  - `anxiety → pendulum` — the mapping is *recurrence / inevitable return*, not
    oscillation-per-se; anxiety recurs.
  - `nostalgia → photograph` — metonymy that still reads live to Julian
    (Fable objected it's the literal artefact).

  Lesson: grade the connotative shadow the vehicle casts back on the topic, not
  just its denotation.

## Topic-selection side-finding

`optics` (a branch of physics) is near-un-metaphorable — all three optics→X
pairings were troubled. Abstract academic-domain topics lack experiential
handholds AND are off-target (Metaforge targets emotional/experiential concepts
for genre writers). **The topic pool needs a filter, separate from the judge.**

## What this means for "get the judge on the road tonight"

1. Fable can't mint gold — but zero-shot it's already ~Sonnet-parity once the
   gold sense-noise is removed. A cheap in-session judge is closer than the
   raw 0.167 suggested.
2. The re-grade queue writes itself: 10 quarantined + 6 flipped rows, re-graded
   through the tool at correct sense, both clean AND grow the final-form gold
   (latest-wins ts restores them automatically).
3. Next honest test: few-shot-calibrate Fable on the 6 named boundary lessons,
   then grade a FRESH unanchored batch and re-measure — target is Sonnet's
   0.332 on the *cleaned* gold, not this anchored 0.598.

## Artifacts
- Blind pairings + Fable verdicts + adjudications preserved in this session;
  quarantine records in `data-pipeline/grading/gold_sense_suspect.jsonl`.
