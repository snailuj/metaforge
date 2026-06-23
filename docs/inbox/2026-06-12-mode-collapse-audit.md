# Mode-Collapse Audit — Generated-Chain Corpus (2026-06-12)

$0 read-only audit of the live Sonnet chain corpus. No LLM calls; pure counting.
Helper script: `/tmp/mode_collapse_audit.py` (+ `/tmp/mode_collapse_followup.py`), run with the project venv.

**Data:** `/home/agent/projects/metaforge/.worktrees/next/data-pipeline/grading/sonnet_chains_provisional_r{1,2,2_handpicked}.jsonl` — 200 + 1,804 + 746 lines, deduped by `chain_signature` (later file wins). **Zero duplicate signatures** across the three files — `r2_handpicked` is a separate generation batch, not a sub-selection of `r2`.

---

## Headline verdict

**Yes, there is vehicle mode-collapse, and it is concentrated rather than diffuse.** The top-10 vehicles — 0.87 % of an 1,146-vehicle vocabulary — carry **10.5 %** of all 2,750 chains (~12× the uniform share); `fermentation` alone is bolted onto **43 of 260 topics** (48 chains); vehicle-count Gini = **0.46**. The tail is healthy (56.5 % of vehicles used exactly once) — the problem is a head of ~30–50 stock vehicles that the generator reaches for across unrelated topics.

---

## 1. Corpus totals

| Measure | Value |
|---|---|
| Unique chains (post-dedup) | 2,750 |
| Unique topics | 260 |
| Unique vehicles | 1,146 |
| Chains per topic | mean 10.6, median 10, max 20 |
| Vehicles per topic | mean 10.2, median 10, min 7, max 17 |

Vehicles-per-topic histogram: `{7: 2, 8: 2, 9: 25, 10: 212, 12: 1, 13: 5, 14: 2, 15: 5, 16: 4, 17: 2}` — within-topic diversity is fine (essentially one vehicle per chain per topic). The collapse is **cross-topic**.

## 2. Vehicle concentration

Top 30 vehicles by chain count (chains | distinct topics):

| Vehicle | Chains | Topics | | Vehicle | Chains | Topics |
|---|---|---|---|---|---|---|
| fermentation | 48 | 43 | | shadow | 15 | 15 |
| tide | 38 | 33 | | mirror | 15 | 14 |
| amber | 35 | 33 | | avalanche | 14 | 13 |
| undertow | 33 | 32 | | scar | 14 | 13 |
| sediment | 28 | 26 | | suture | 14 | 14 |
| river | 24 | 19 | | seed | 13 | 12 |
| palimpsest | 22 | 20 | | threshold | 13 | 13 |
| knot | 21 | 21 | | debt | 12 | 12 |
| eclipse | 20 | 20 | | keystone | 12 | 11 |
| echo | 19 | 17 | | static | 12 | 11 |
| glacier | 17 | 16 | | quicksand | 12 | 11 |
| fog | 17 | 16 | | prism | 11 | 11 |
| mycelium | 16 | 16 | | thread | 10 | 9 |
| compass | 16 | 15 | | garden | 10 | 9 |
| patina | 16 | 16 | | chrysalis | 10 | 9 |

(The by-distinct-topic ranking is near-identical — chains:topics ≈ 1:1 for the head, i.e. these vehicles are almost never reused *within* a topic, always *across* topics. That is the mode-collapse signature.)

Concentration numbers:

- **CR5 6.6 % · CR10 10.5 % · CR20 16.1 % · CR30 20.3 % · CR50 26.8 %** of all chains
- Gini of the vehicle chain-count distribution: **0.460**
- Vehicles used exactly once: 647/1,146 (**56.5 %**); vehicles spanning >1 topic: 479 (41.8 %)
- Uniform-draw baseline for top-10 share would be 0.9 % → observed is **~12×** over.

## 3. The 2026-06-05 triage claim — CONFIRMED on reuse, REFINED on deadness

The claimed counts (fermentation 20×, undertow 19×, amber 16×, tide 12×, eclipse 12×) match the **handpicked file alone** (n=746: 16/19/16/10/12) almost exactly — the triage looked at one batch. On the **full corpus the reuse is 1.5–3× worse**:

| Vehicle | Claimed | Full corpus | Topics |
|---|---|---|---|
| fermentation | 20× | **48** | 43 |
| undertow | 19× | **33** | 32 |
| amber | 16× | **35** | 33 |
| tide | 12× | **38** | 33 |
| eclipse | 12× | **20** | 20 |

"Bolted onto many topics": **confirmed** — each spans 20–43 distinct topics.

"Mostly dead": **not confirmed as a blanket claim — it is per-vehicle.** Two independent reads:

- *Julian's gold verdicts* (132 latest-per-signature, signal-prioritised sample — biased, tiny): chains with a top-10 vehicle are 10 live / 3 dead (n=13) vs 53 % live for other vehicles. No deadness penalty visible at this n.
- *Triage-judge scores* (2,550 joined, judge unvalidated against gold): top-10 vehicles mean 5.17 vs 5.38 for the rest — mild. But per vehicle: **river 84 % scored ≤4, tide 62 %, undertow 58 %** (dead-ish), while **amber 0 % ≤4 (mean 6.0) and palimpsest 0 % ≤4 (mean 6.9)** — heavily reused *and* well-scored.

So reuse and deadness are separate axes. The avoid-list case rests on **positional-goods diversity** (a vehicle stamped onto 43 topics is a generator tic that self-destructs the product's freshness), not on measured deadness — except for river/tide/undertow, which are both overused *and* dead-leaning.

## 4. Intermediate-step mode-collapse (chain[1:-1])

6,366 intermediate steps, 2,268 unique heads, Gini **0.503**. Top 20 heads = **11.1 %** of all intermediate steps:

`pressure` 53, `point` 50, `force` 47, `surface` 47, `current` 45, `pull` 42, `light` 42, `flow` 34, `heat` 33, `layer` 33, `form` 31, `mark` 30, `weight` 29, `passage` 29, `mass` 29, `tension` 28, `growth` 28, `transformation` 27, `wound` 26, `pattern` 26.

These are generic physical abstractions — partly by design (chains pass through a shared abstraction layer), but `pressure/force/surface/current/pull` recurring across 30–43 topics each means many chains share the same middle and differ only at the endpoints. Worth watching; not the Phase-B priority.

## 5. Proposer / round breakdown

- **Proposer:** `sonnet_v1` for all 2,750 chains — no variation to compare.
- **Round:** r1 = 200 chains / 20 topics (Gini 0.189, top-10 share 18.0 % — small-n artefact of only 20 topics); r2 = 2,550 chains / 259 topics (Gini **0.444**, top-10 share 10.1 %). The same offenders top both rounds (`fermentation` is #1 in each) — concentration **persisted through the round-2 scale-up**; it is a stable generator habit, not a one-batch fluke.

## 6. Topic-pair vehicle overlap

- 33,670 topic pairs; 17.6 % share ≥1 vehicle; mean Jaccard **0.0117**, max **0.429**.
- Top 5 overlapping pairs (all near-synonym or same-affect pairs):
  1. guilt ↔ remorse — J=0.429 (debt, rust, sediment, stain, undertow, wound)
  2. commitment ↔ covenant — J=0.429 (keystone, knot, seal, sinew, suture, weld)
  3. therapy ↔ tuition — J=0.333 (calibration, cartography, fermentation, gardening, midwifery)
  4. nostalgia ↔ wistfulness — J=0.333 (amber, echo, palimpsest, photograph, ruin)
  5. despair ↔ stupor — J=0.333 (amber, eclipse, permafrost, sediment, undertow)

Global overlap is low — the collapse lives in the head vehicles, and it **skews to emotion-class topics**: with a rough 35-topic emotion wordlist (13 % of topics, 15 % of chain slots), `eclipse` lands on 55 % emotion topics, `undertow` 47 %, `fermentation` and `amber` 33 % each. Abstract-affect topics pull the generator into the same dark-water / geology / preservation grooves.

---

## Phase-B steering recommendation

**AVOID-list payload** — earned a place by `distinct-topics ≥ 10` in the current corpus (33 vehicles, 587 chains = 21.3 % of the corpus). Paste-ready:

```json
{"avoid_vehicles": [
  "fermentation", "tide", "amber", "undertow", "sediment", "knot",
  "palimpsest", "eclipse", "river", "echo", "glacier", "mycelium",
  "fog", "patina", "shadow", "compass", "mirror", "suture",
  "avalanche", "scar", "threshold", "debt", "seed", "keystone",
  "static", "quicksand", "prism", "drought", "crucible", "fossil",
  "rust", "anchor", "aurora"
]}
```

- Threshold rationale: ≥10 topics is ~4× the head-tail knee (mean reuse is 2.4 chains/vehicle; 96 % of vehicles sit below 10 topics). Dropping to ≥8 adds 16 vehicles (forge, thread, loom, garden, erosion, chrysalis, wound, bellows, spring, permafrost, ember, fuse, graft, splinter, labyrinth, cipher) for 26.5 % coverage — use this wider list if the prompt budget allows.
- **Do not hard-ban on deadness grounds**: amber and palimpsest score *well* — the ban is for diversity. If you want a "worst offenders, never" sub-tier, it is the overuse∩dead-ish set: **river, tide, undertow** (84 %/62 %/58 % triage-dead-ish).

**Per-vehicle reuse cap (generation-time tripwire):** cap each vehicle at **3 distinct topics per 100-topic batch**, reject-and-resample on breach; corpus-wide ceiling **1 % of topics** (10 topics in a 1k-topic Phase-B run). This flattens the head without touching the healthy 56 % single-use tail. Implement in the runner alongside the existing money tripwire — it is a cheap counter, idempotent across resumed runs if keyed on (vehicle, topic).

**Topic-class note:** steering matters most for **abstract emotion/affect topics** — they attract the same dark-water/geology/preservation set at 2–4× base rate (eclipse 55 %, undertow 47 % emotion-topic share vs 13 % baseline). Near-synonym topic pairs (guilt/remorse, nostalgia/wistfulness, despair/stupor) currently buy almost the same vehicle set twice; if Phase-B's 1k topics contain synonym clusters, consider applying the cap at the topic-cluster level, not the surface-form level.

**Secondary (flag, no action):** intermediate-head collapse (`pressure/force/surface/current/pull` in 30–43 topics each) is real but milder; revisit if Phase-B chains still feel same-y after vehicle steering.
