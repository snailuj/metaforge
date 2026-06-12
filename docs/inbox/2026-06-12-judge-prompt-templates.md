# Judge prompt templates — rendered verbatim (2026-06-12 calibration runs)
Real few-shot draw (k=6, seed 0) + a real held-out item, exactly as sent to the model.

## Stage-1 construction judge (haiku & sonnet arms — both FAILED the gate)

```text
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
- merge: two adjacent steps restate one concept, so the hop adds no movement.

A bloated-but-valid path (padding: redundant yet individually justified
steps) is "good" — verbosity is not a structural fault.

## Worked examples

### Example 1
Topic: refutation (n: the act of determining that something is false)
Vehicle: autopsy (v: perform an autopsy on a dead body; do a post-mortem)
Chain:
  1. refutation
  2. death
  3. post-mortem
  4. autopsy
Verdict: bad

### Example 2
Topic: dread (n: fearful expectation or anticipation)
Vehicle: knell (v: make (bells) ring, often for the purposes of musical edification)
Chain:
  1. dread
  2. doom — from "tolling doom"
  3. count — from "measured count"
  4. knell
Verdict: good

### Example 3
Topic: hospitality (n: kindness in welcoming guests or strangers)
Vehicle: feast (n: something experienced with great delight)
Chain:
  1. hospitality
  2. generosity
  3. abundance
  4. feast
Verdict: good

### Example 4
Topic: ambush (n: the act of concealing yourself and lying in wait to attack by surprise)
Vehicle: avalanche (n: a slide of large masses of snow and ice and mud down a mountain)
Chain:
  1. ambush
  2. accumulation — from "hidden accumulation"
  3. mass — from "building mass"
  4. instability — from "triggered instability"
  5. surge — from "overwhelming surge"
  6. avalanche
Verdict: bad

### Example 5
Topic: hospitality (n: kindness in welcoming guests or strangers)
Vehicle: hearth (n: an open recess in a wall at the base of a chimney where a fire can be built)
Chain:
  1. hospitality
  2. welcome
  3. warmth
  4. hearth
Verdict: good

### Example 6
Topic: ambush (n: the act of concealing yourself and lying in wait to attack by surprise)
Vehicle: trapdoor
Chain:
  1. ambush
  2. preparation — from "buried preparation"
  3. threshold — from "concealed threshold"
  4. mechanism — from "triggered mechanism"
  5. engulfment — from "sudden engulfment"
  6. trapdoor
Verdict: bad

## Chain to judge
Topic: refutation (n: the act of determining that something is false)
Vehicle: scalpel (n: a thin straight surgical knife used in dissection and surgery)
Chain:
  1. refutation
  2. cutting
  3. precision
  4. scalpel

Respond with STRICT JSON and nothing else: {"verdict": "good"} or {"verdict": "bad"}.
```

## Stage-2 liveness judge (sonnet — IN FLIGHT)

```text
You are the Forge Reader: a working genre-fiction novelist and acquiring editor (science fiction, fantasy, horror, thriller, crime). You have read ten thousand manuscripts and you judge with a sharp, unsentimental eye whether a metaphor works for a reader curled up with a paperback — you are not a literature academic, and 'literary' means well-crafted, never highbrow.

Judge the single topic -> vehicle metaphor pairing for liveness.
LIVE = a fresh, surprising-yet-apt cross-domain image: the gut-punch that makes a reader stop and re-see the topic, the pairing a writer would lift straight into prose.
DEAD = a cliche (anger is fire, time is money, broken heart), a near-synonym or same-domain restatement with no real jump to a different concrete domain, or an inert pairing the eye slides past.

Do not reward a cliche for being clear or relatable: familiar = dead. Do not punish a pairing for being pulpy, vivid or genre — punch is the target, not restraint. Most pairings are average; you have a slush pile and a deadline.

Examples:

ambush (n: the act of concealing yourself and lying in wait to attack by surprise) -> fault (n: (sports) a serve that is illegal (e.g., that lands outside the prescribed area))
{"verdict": "live"}

time (n: the continuum of experience in which events pass from the future through the present to the past) -> river (n: a large natural stream of water (larger than a creek))
{"verdict": "dead"}

refutation (n: the act of determining that something is false) -> scalpel (n: a thin straight surgical knife used in dissection and surgery)
{"verdict": "dead"}

ambush (n: the act of concealing yourself and lying in wait to attack by surprise) -> mine (n: explosive device that explodes on contact; designed to destroy vehicles or ships or to kill or maim personnel)
{"verdict": "live"}

longing (n: prolonged unfulfilled desire or need) -> heliotrope (n: green chalcedony with red spots that resemble blood)
{"verdict": "dead"}

light (n: (physics) electromagnetic radiation that can produce a visual sensation) -> tide (n: the periodic rise and fall of the sea level under the gravitational pull of the moon)
{"verdict": "live"}

Now judge this pairing:
resentment (n: a feeling of deep and bitter anger and ill-will) -> poison (n: anything that harms or destroys)

Respond with ONLY strict JSON, exactly one of: {"verdict": "live"} or {"verdict": "dead"}.
```
