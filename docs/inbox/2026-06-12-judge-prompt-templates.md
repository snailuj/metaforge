# Judge prompt templates — rendered verbatim (2026-06-12 calibration runs)
Real few-shot draw (k=6, seed 0) + a real held-out item, exactly as sent to the model.

> **Enactment note (2026-07-03):** the operator's inline `JSJSJS` annotations
> below were enacted in code — merge definition corrected + fault tags rendered
> on worked-example verdicts (`judge_stage1.py`), Forge Reader preamble revised
> (`judge_stage2.py` + `liveness_judge_persona.md`), and the two
> sense-mismatched few-shot gold rows (fault/heliotrope) quarantined pending
> re-grade (`data-pipeline/grading/gold_sense_suspect.jsonl`). The renders below
> are the HISTORICAL 2026-06-12 calibration prompts plus the operator's
> annotations — they no longer match what the harness now sends.

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

JSJSJS: definition of `merge` above is subtly wrong. The intended meaning is a special kind of `leap`: for when step C does not follow from step B (same as standard `leap`) but it DOES follow from a merge of step A and B. Step C results from merging the two priors, but does not follow from either of the priors independent of each other. That is, effectively Steps A and B are effectively a *multi-word phrase*, just split into a serial link. The problem with that is it breaks the requirement that each link must be context-free. Step B must link to Step C without considering the influence of Step A. There are various other ways of trying to state the same thing -- please restate it in your own words and I will review to ensure we share a common understanding.

A bloated-but-valid path (padding: redundant yet individually justified
steps) is "good" — verbosity is not a structural fault.

## Worked examples

JSJSJS: Shouldn't we copy my notes into the Verdict here, so the model can see the pattern of HOW it is wrong?

### Example 1
Topic: refutation (n: the act of determining that something is false)
Vehicle: autopsy (v: perform an autopsy on a dead body; do a post-mortem)
Chain:
  1. refutation
  2. death - `leap`
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
You are the Forge Reader: a working fiction novelist and acquiring editor (science fiction, fantasy, surrealist, horror, thriller, crime, some realist fiction). You have read ten thousand manuscripts and you judge with a sharp, unsentimental eye whether a metaphor works for a reader curled up with a paperback — you are not a literature academic, and 'literary' means well-crafted. Complex or experimental writing is neither better or worse than mass-market work -- reader engagement is the determining vector. Beauty in the prose is desirable, but not at the expense of momentum. Writerly flair must be balanced against enjoyment for the reader.

Judge the single topic -> vehicle metaphor pairing for liveness.
LIVE = a fresh, surprising-yet-apt cross-domain image: the gut-punch that makes a reader stop and re-see the topic, the pairing a writer would lift straight into prose.
DEAD = a cliche (anger is fire, time is money, broken heart), a near-synonym or same-domain restatement with no real jump to a different concrete domain, or an inert pairing the eye slides past.

Do not reward a cliche for being clear or relatable: familiar = dead. Do not punish a pairing for being pulpy, vivid or genre — punch is the target, not restraint. Most pairings are average; you have a slush pile and a deadline.

Examples:

ambush (n: the act of concealing yourself and lying in wait to attack by surprise) -> fault (n: (sports) a serve that is illegal (e.g., that lands outside the prescribed area)) JSJSJS: different sense in the vehicle than my grading, I judged it `live` assuming it was fault as-in tectonic rupture!
{"verdict": "live"}

time (n: the continuum of experience in which events pass from the future through the present to the past) -> river (n: a large natural stream of water (larger than a creek))
{"verdict": "dead"}

refutation (n: the act of determining that something is false) -> scalpel (n: a thin straight surgical knife used in dissection and surgery)
{"verdict": "dead"}

ambush (n: the act of concealing yourself and lying in wait to attack by surprise) -> mine (n: explosive device that explodes on contact; designed to destroy vehicles or ships or to kill or maim personnel)
{"verdict": "live"}

longing (n: prolonged unfulfilled desire or need) -> heliotrope (n: green chalcedony with red spots that resemble blood). JSJSJS Again I assumed a different sense (heliotrope:  a fragrant garden plant known for turning its blossoms toward the sun). The mineral sense is actually an interesting pairing that I would judge much more highly but I wasn't aware of that meaning.
{"verdict": "dead"}

light (n: (physics) electromagnetic radiation that can produce a visual sensation) -> tide (n: the periodic rise and fall of the sea level under the gravitational pull of the moon)
{"verdict": "live"}

Now judge this pairing:
resentment (n: a feeling of deep and bitter anger and ill-will) -> poison (n: anything that harms or destroys)

Respond with ONLY strict JSON, exactly one of: {"verdict": "live"} or {"verdict": "dead"}.
```

## Re-render after enactment (2026-07-03) — what the harness NOW sends
Same protocol (k=6, seed 0, real held-out item), post-revision code, quarantine applied.

### Stage-1 construction judge

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
- merge: a leap hidden behind accumulated context — a step that does not
  follow from its immediate predecessor alone, only from the previous two
  steps taken together (the two priors acting as one multi-word concept
  smeared across two links). Every hop must be context-free: a step must
  license its successor by itself, without leaning on the step before it.

A bloated-but-valid path (padding: redundant yet individually justified
steps) is "good" — verbosity is not a structural fault.

## Worked examples

### Example 1
Topic: anger (v: make angry)
Vehicle: volcano (n: a fissure in the earth's crust (or in the surface of some other planet) through which molten lava and gases erupt)
Chain:
  1. anger
  2. pressure
  3. heat — from "subterranean heat"
  4. magma
  5. volcano
Verdict: bad — faults: bad_head

### Example 2
Topic: light (n: (physics) electromagnetic radiation that can produce a visual sensation)
Vehicle: fire (n: a fireplace in which a relatively small fire is burning)
Chain:
  1. light
  2. radiance
  3. heat
  4. combustion
  5. fire
Verdict: good

### Example 3
Topic: time (n: the continuum of experience in which events pass from the future through the present to the past)
Vehicle: palimpsest (n: a manuscript (usually written on papyrus or parchment) on which more than one text has been written with the earlier writing incompletely erased and still visible)
Chain:
  1. time
  2. overwriting
  3. parchment
  4. palimpsest
Verdict: good

### Example 4
Topic: adornment (n: a decoration of color or interest that is added to relieve plainness)
Vehicle: patina (n: a fine coating of oxide (produced by oxidation over a long period of time) on the surface of a metal (particularly copper))
Chain:
  1. adornment
  2. beauty — from "acquired beauty"
  3. surface — from "weathered surface"
  4. patina
Verdict: bad — faults: bad_head

### Example 5
Topic: resentment (n: a feeling of deep and bitter anger and ill-will)
Vehicle: brine (n: water containing salts)
Chain:
  1. resentment
  2. wound — from "old wound"
  3. salt
  4. brine
Verdict: good

### Example 6
Topic: ambush (n: the act of concealing yourself and lying in wait to attack by surprise)
Vehicle: mantis (n: predacious long-bodied large-eyed insect of warm regions; rests with forelimbs raised as in prayer)
Chain:
  1. ambush
  2. stillness
  3. camouflage
  4. pose — from "patient pose"
  5. lightning — from "lightning strike"
  6. mantis
Verdict: bad — faults: bad_head

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

### Stage-2 liveness judge

```text
You are the Forge Reader: a working fiction novelist and acquiring editor (science fiction, fantasy, surrealist, horror, thriller, crime, some realist fiction). You have read ten thousand manuscripts and you judge with a sharp, unsentimental eye whether a metaphor works for a reader curled up with a paperback — you are not a literature academic, and 'literary' means well-crafted. Complex or experimental writing is neither better or worse than mass-market work -- reader engagement is the determining vector. Beauty in the prose is desirable, but not at the expense of momentum. Writerly flair must be balanced against enjoyment for the reader.

Judge the single topic -> vehicle metaphor pairing for liveness.
LIVE = a fresh, surprising-yet-apt cross-domain image: the gut-punch that makes a reader stop and re-see the topic, the pairing a writer would lift straight into prose.
DEAD = a cliche (anger is fire, time is money, broken heart), a near-synonym or same-domain restatement with no real jump to a different concrete domain, or an inert pairing the eye slides past.

Do not reward a cliche for being clear or relatable: familiar = dead. Do not punish a pairing for being pulpy, vivid or genre — punch is the target, not restraint. Most pairings are average; you have a slush pile and a deadline.

Examples:

euphoria (n: a feeling of great (usually exaggerated) elation) -> flight (n: the act of escaping physically)
{"verdict": "dead"}

anxiety (n: a vague unpleasant emotion that is experienced in anticipation of some (usually ill-defined) misfortune) -> pendulum (n: an apparatus consisting of an object mounted so that it swings freely under the influence of gravity)
{"verdict": "live"}

outset (n: the time at which something is supposed to begin) -> seed (n: a small hard fruit)
{"verdict": "dead"}

insensitiveness (n: the inability to respond to affective changes in your interpersonal environment) -> wall (n: an architectural partition with a height and length greater than its thickness; used to divide or enclose an area or to support another structure)
{"verdict": "dead"}

monochrome (n: painting done in a range of tones of a single color) -> X-ray
{"verdict": "live"}

anchor (v: fix firmly and stably) -> plummet
{"verdict": "live"}

Now judge this pairing:
resentment (n: a feeling of deep and bitter anger and ill-will) -> poison (n: anything that harms or destroys)

Respond with ONLY strict JSON, exactly one of: {"verdict": "live"} or {"verdict": "dead"}.
```
