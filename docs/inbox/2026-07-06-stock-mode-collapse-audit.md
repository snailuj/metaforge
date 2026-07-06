# Stock-Corpus Mode-Collapse Audit + AVOID Re-tune (2026-07-06)

$0 read-only audit of the banked **stock** corpus (broad noun lexicon, emit-the-sense
run). No LLM calls; pure counting. Helper: `/tmp/stock_mode_collapse_audit.py`.
Trigger: operator flagged `palimpsest` as a "tell" (the model reaching); this audit
checks whether the AVOID list is tuned for the broad lexicon and re-tunes it.

**Data:** `.worktrees/grading-data/data-pipeline/grading/stock/chain-topics_stock.jsonl`
— 3,125 chains (deduped by signature), 324 topics.

---

## Headline

**Two findings.** (1) The stock corpus is **healthily diverse overall** — 1,468
distinct vehicles, Gini 0.424, 61% of vehicles used exactly once — with a
concentrated head of ~20 crutches, same shape as the June audit. (2) **AVOID is
whack-a-mole.** The stock run WAS launched with the 16-vehicle AVOID list applied
(confirmed: memory `stock_run_emit_launched`, and the 2026-06-27 pause QA —
"AVOID working: top vehicles palimpsest/loom/mycelium, no banned clichés"). All
16 have **zero** chains in the corpus — they were successfully *suppressed*, not
regime-mismatched (an earlier draft of this doc wrongly attributed the zero
footprint to regime). With the top crutches banned, the model's mode-collapse
pressure **redirected to the next tier** — palimpsest surged from June's #7 (22
chains) to #1 (50), and amber/avalanche/etc. rose behind it. Adding these to
AVOID will suppress *this* tier and almost certainly surface a *third*.

## Corpus totals

| Measure | Stock | (June graded corpus) |
|---|---|---|
| Unique chains | 3,125 | 2,750 |
| Unique topics | 324 | 260 |
| Unique vehicles | 1,468 | 1,146 |
| Vehicles used once | 61% | 56.5% |
| Gini (vehicle chain-count) | 0.424 | 0.460 |
| CR10 (top-10 share) | 7.5% (11× uniform) | 10.5% (12×) |

Diversity is marginally *better* than June. The collapse is the head, not the body.

## The stock crutch head (chains | distinct topics — ratio ≈ 1:1 = cross-topic reach)

| Vehicle | Chains | Topics | graded live/total |
|---|---|---|---|
| **palimpsest** | 50 | 50 | 3/5 |
| amber | 25 | 25 | 2/2 |
| avalanche | 24 | 24 | 0/1 |
| ratchet | 21 | 21 | — |
| gangrene | 21 | 21 | — |
| patina | 21 | 21 | 1/1 |
| mycelium | 21 | 21 | — |
| quicksand | 18 | 18 | 0/2 |
| taxidermy | 16 | 16 | 1/1 |
| murmuration | 16 | 16 | — |
| stampede | 16 | 16 | — |
| keystone | 16 | 16 | — |
| chrysalis | 15 | 15 | 0/1 |
| suture | 15 | 15 | — |

The chains:topics ratio is exactly 1:1 across the whole head — each is reached for
once per topic, across 15–50 *unrelated* topics. That is the mode-collapse
signature (cross-topic, never within-topic), identical to June.

**Aptness is mixed and the grade sample is too thin to rank on** (1–5 each). The
sparse signal hints amber/patina/scar are versatile-and-apt while
avalanche/quicksand/chrysalis lean reach — but AVOID is a *soft* diversity nudge,
not a ban, so the robust **breadth** signal drives the list; aptness is flagged,
not decisive. (Corroboration: quicksand and chrysalis were both graded *dead* in
the 2026-07-03 blind experiment — they are reaches.)

## AVOID re-tune

**Added** (13 stock crutches, chains ≥ 15 & breadth ≥ 15, not already listed):
`amber, avalanche, ratchet, gangrene, patina, mycelium, quicksand, taxidermy,
murmuration, stampede, keystone, chrysalis, suture` — plus `palimpsest` (added
earlier). **Kept** the 16 original entries — they are *actively suppressing* their
crutches (that's why they're at zero); dropping them would let those clichés
return. The list now bans both tiers. Watch-list, just below the cut (chains
11–14): `scar, blight, tourniquet, lacquer, static, mosaic, reliquary,
counterpoint` — likely the third tier next run.

## Strategic implication: AVOID is a treadmill, the judge is the real filter

Because banning a tier redirects collapse to the next, AVOID tuning has
**diminishing returns** — you can't ban your way to diversity; each round buys one
tier of suppression and surfaces another. AVOID is worth keeping as a cheap
diversity nudge, but it is NOT the fix for mode-collapse. Two better levers: (a)
generation-side — sampling temperature / prompt-diversity / per-topic vehicle
variety, attacking the *cause* not the symptom; (b) the **live/dead judge** —
which gates crutch-reaches at harvest regardless of how the model over-reaches
(the past/memory palimpsest lives, the bureaucracy→palimpsest reach dies). The
judge makes the whack-a-mole moot for the *product*: over-reached vehicles that
don't fit simply don't become edges. So do NOT over-invest in AVOID tuning — one
audit per corpus to knock down the worst tier, then rely on the judge.

**Operator vetoes to consider:** the sparse live signal makes `amber` (2/2),
`patina` (1/1), `taxidermy` (1/1), `scar` (1/1) look apt-though-overused. AVOID
only *discourages*, so keeping them nudges the model toward finding *other* apt
vehicles for those topics — but pull any you'd rather keep unconstrained.

## What this does NOT change

The banked palimpsest/crutch chains **stay** — grading gates which are apt (the
past/memory cluster grades live; the reaches grade dead and are useful hard
negatives). AVOID is forward-only. See the 2026-07-05 discussion.
