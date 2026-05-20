# M02-S04 — Prompt-quality audit (cross-domain apt cohort)

**DB:** `data-pipeline/output/lexicon_v2.db`  
**Cohort:** 271 cross-domain apt-pair source words.  
**Generator:** `data-pipeline/scripts/m02_s04_prompt_audit.py --cross-domain`

Three hypotheses under test:

- **H1 — Model limitation:** the model just isn't good at   extracting sensorimotor properties.
- **H2 — Synset-side limitation:** common abstract words   genuinely lack sensorimotor properties to extract.
- **H3 — Prompt limitation:** the system prompt is   overconstraining, or asking for too many properties,   pushing the model into abstract-vocab panic.

## Headline

- Words audited: **271** (25 unenriched, 246 have LLM properties).
- Total LLM properties across the cohort: **2948**
- Properties matching the sensorimotor wordlist: **159** (5.4%)

### Classification mix

| class | count | % |
|---|---|---|
| effect-functional | 737 | 25.0% |
| behaviour | 651 | 22.1% |
| emotional | 447 | 15.2% |
| social | 393 | 13.3% |
| physical-other | 390 | 13.2% |
| unknown | 171 | 5.8% |
| sensorimotor | 159 | 5.4% |

### Per-domain stratification

The prompt says ≥4 physical-typed properties per synset (10–15 properties total). The columns below test whether abstract domains (emotion/cognition/society) under-emit physical-typed properties relative to concrete domains (body/nature) — i.e. does the under-emission pattern track abstractness or is it pervasive?

| domain | enriched | unenriched | avg props/synset | physical-typed/synset | sensorimotor (heuristic) % |
|---|---|---|---|---|---|
| body | 30 | 1 | 13.1 | 5.6 | 12.2% |
| cognition | 40 | 1 | 12.9 | 1.7 | 3.1% |
| creativity | 16 | 4 | 12.2 | 1.6 | 2.6% |
| emotion | 37 | 14 | 9.9 | 1.3 | 8.2% |
| nature | 26 | 2 | 10.9 | 2.5 | 8.1% |
| relationship | 23 | 2 | 11.4 | 0.5 | 4.6% |
| society | 37 | 0 | 12.9 | 0.9 | 1.7% |
| time | 37 | 1 | 12.4 | 1.6 | 3.7% |

### Most-frequent properties per class (top 10 each)

**sensorimotor**

```
   13  warm
   11  quiet
    8  rhythmic
    7  loud
    7  cold
    7  tense
    6  heavy
    6  smooth
    6  rigid
    6  still
```

**physical-other**

```
   14  fragile
   13  invisible
    9  visible
    8  abstract
    6  durable
    6  delicate
    5  structured
    5  deep
    4  energetic
    4  layered
```

**emotional**

```
    9  hopeful
    8  precious
    7  anxious
    6  weighty
    6  fearful
    6  inspiring
    6  uncomfortable
    6  peaceful
    5  vulnerable
    5  nostalgic
```

**behaviour**

```
   15  deliberate
   14  persistent
   11  enduring
   11  transient
   10  sudden
   10  gradual
    7  continuous
    7  involuntary
    7  energetic
    7  cumulative
```

**effect-functional**

```
   19  transformative
   16  irreversible
   14  protective
    9  motivating
    9  influential
    8  dangerous
    8  purposeful
    7  destabilising
    7  persuasive
    7  structured
```

**social**

```
   11  formal
   11  collective
    9  social
    9  authoritative
    9  rare
    7  universal
    7  ancient
    6  isolating
    5  shared
    5  personal
```

**unknown**

```
    4  impermanent
    3  destabilizing
    3  ecstatic
    2  unforgiving
    2  desiring
    2  jealous
    2  unrealistic
    2  tyrannical
    1  expecting
    1  hoping
```

## Unenriched emotion-domain source words

These resolve to a synset but have ZERO entries in `synset_properties` — the LLM hasn't been pointed at them yet at all. Surgical enrichment (S04 sub-task) would fix these.

```
  sorrow          synset_id=72867
  anxiety         synset_id=72810
  contentment     synset_id=72848
  shame           synset_id=72713
  elation         synset_id=72829
  nostalgia       synset_id=72603
  frustration     synset_id=72899
  humiliation     synset_id=71623
  yearning        synset_id=72598
  delight         synset_id=72624
  longing         synset_id=72598
  gratitude       synset_id=72700
  awe             synset_id=72733
  disgust         synset_id=72693
  anticipation    synset_id=72738
  hypothesis      synset_id=70830
  joint           synset_id=73120
  hardship        synset_id=71764
  wildness        synset_id=72567
  heartbreak      synset_id=72870
  empathy         synset_id=72983
  eloquence       synset_id=70367
  poetry          synset_id=70463
  comedy          synset_id=70072
  metaphor        synset_id=70546
```

## Per-word enrichment dump

Full LLM output for each enriched word, with each property classified and its snap status shown. Read these to triage H1/H2/H3 — is the model emitting sensorimotor properties? Did snap accept them? Is the property mix dominated by abstract/effect categories the prompt arguably encourages?

### `anger` (synset `30227`) — 11 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `provocative` | 0.85 | behaviour | behaviour |
| `triggering` | 0.85 | behaviour | behaviour |
| `inflammatory` | 0.80 | effect | effect-functional |
| `interpersonal` | 0.80 | social | social |
| `charged` | 0.75 | emotional | emotional |
| `destabilising` | 0.75 | effect | effect-functional |
| `heated` | 0.70 | physical | physical-other |
| `reactive` | 0.70 | behaviour | behaviour |
| `confrontational` | 0.65 | social | social |
| `escalating` | 0.65 | behaviour | behaviour |
| `abrupt` | 0.60 | behaviour | behaviour |

### `grief` (synset `64254`) — 11 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `painful` | 0.95 | effect | effect-functional |
| `devastating` | 0.90 | effect | effect-functional |
| `heavy` | 0.85 | emotional | sensorimotor |
| `sorrowful` | 0.85 | emotional | emotional |
| `heartbreaking` | 0.80 | emotional | emotional |
| `lasting` | 0.75 | behaviour | behaviour |
| `burdensome` | 0.70 | effect | effect-functional |
| `overwhelming` | 0.70 | effect | effect-functional |
| `tragic` | 0.65 | emotional | emotional |
| `inescapable` | 0.60 | behaviour | behaviour |
| `isolating` | 0.60 | social | social |

### `love` (synset `72913`) — 10 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `positive` | 0.95 | emotional | emotional |
| `warm` | 0.95 | emotional | sensorimotor |
| `strong` | 0.90 | emotional | emotional |
| `bonding` | 0.85 | effect | effect-functional |
| `enduring` | 0.80 | behaviour | behaviour |
| `nurturing` | 0.80 | effect | effect-functional |
| `selfless` | 0.75 | behaviour | behaviour |
| `wholehearted` | 0.75 | emotional | emotional |
| `transformative` | 0.70 | effect | effect-functional |
| `universal` | 0.65 | social | social |

### `fear` (synset `30157`) — 13 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `softening` | 0.90 | functional | effect-functional |
| `apologetic` | 0.88 | social | social |
| `diplomatic` | 0.85 | social | social |
| `polite` | 0.85 | social | social |
| `regretful` | 0.82 | emotional | emotional |
| `reluctant` | 0.80 | emotional | emotional |
| `hedging` | 0.78 | functional | effect-functional |
| `indirect` | 0.75 | behaviour | behaviour |
| `formal` | 0.72 | social | social |
| `understated` | 0.70 | social | social |
| `distancing` | 0.65 | social | social |
| `anticipatory` | 0.60 | behaviour | behaviour |
| `empathetic` | 0.55 | emotional | emotional |

### `hope` (synset `30810`) — 19 properties, 2 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `expecting` | 1.00 | — | unknown |
| `hoping` | 1.00 | — | unknown |
| `anticipatory` | 0.85 | behaviour | behaviour |
| `uncertain` | 0.85 | emotional | emotional |
| `expectant` | 0.80 | emotional | emotional |
| `sustaining` | 0.80 | effect | effect-functional |
| `yearning` | 0.80 | emotional | emotional |
| `desirous` | 0.75 | emotional | emotional |
| `warm` | 0.75 | emotional | sensorimotor |
| `wishful` | 0.75 | emotional | emotional |
| `fragile` | 0.70 | emotional | emotional |
| `longing` | 0.70 | emotional | emotional |
| `trusting` | 0.70 | emotional | emotional |
| `motivating` | 0.65 | effect | effect-functional |
| `quiet` | 0.60 | behaviour | sensorimotor |
| `vulnerable` | 0.60 | emotional | emotional |
| `wistful` | 0.60 | emotional | emotional |
| `tender` | 0.55 | emotional | emotional |
| `passive` | 0.50 | behaviour | behaviour |

### `joy` (synset `64235`) — 12 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `heartwarming` | 1.00 | — | unknown |
| `delightful` | 0.95 | emotional | emotional |
| `uplifting` | 0.85 | effect | effect-functional |
| `cherished` | 0.80 | emotional | emotional |
| `brightening` | 0.75 | effect | effect-functional |
| `precious` | 0.75 | emotional | emotional |
| `sought` | 0.70 | behaviour | behaviour |
| `energising` | 0.65 | effect | effect-functional |
| `shared` | 0.60 | social | social |
| `animating` | 0.55 | effect | effect-functional |
| `memorable` | 0.50 | effect | effect-functional |
| `generous` | 0.45 | social | social |

### `rage` (synset `43806`) — 11 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `aggressive` | 0.92 | behaviour | behaviour |
| `explosive` | 0.90 | behaviour | behaviour |
| `uncontrolled` | 0.88 | behaviour | behaviour |
| `forceful` | 0.85 | behaviour | behaviour |
| `loud` | 0.85 | behaviour | sensorimotor |
| `intimidating` | 0.82 | emotional | emotional |
| `threatening` | 0.80 | social | social |
| `erratic` | 0.75 | behaviour | behaviour |
| `destabilising` | 0.72 | effect | effect-functional |
| `consuming` | 0.65 | effect | effect-functional |
| `transient` | 0.60 | behaviour | behaviour |

### `despair` (synset `72905`) — 1 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `drowning` | 1.00 | — | unknown |

### `time` (synset `445`) — 20 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `continuous` | 0.95 | behaviour | behaviour |
| `inexorable` | 0.95 | behaviour | behaviour |
| `irreversible` | 0.95 | effect | effect-functional |
| `constant` | 0.90 | behaviour | behaviour |
| `flowing` | 0.90 | behaviour | behaviour |
| `universal` | 0.90 | social | social |
| `invisible` | 0.85 | physical | physical-other |
| `linear` | 0.85 | behaviour | sensorimotor |
| `abstract` | 0.80 | physical | physical-other |
| `experiential` | 0.80 | emotional | emotional |
| `infinite` | 0.80 | physical | physical-other |
| `sequential` | 0.80 | behaviour | behaviour |
| `measured` | 0.75 | functional | effect-functional |
| `ordering` | 0.75 | functional | effect-functional |
| `precious` | 0.70 | emotional | emotional |
| `pressuring` | 0.70 | emotional | emotional |
| `mysterious` | 0.65 | emotional | emotional |
| `melancholy` | 0.60 | emotional | emotional |
| `weighty` | 0.55 | emotional | emotional |
| `cyclical` | 0.50 | behaviour | behaviour |

### `life` (synset `92`) — 16 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `vital` | 0.90 | emotional | emotional |
| `diverse` | 0.85 | physical | physical-other |
| `complex` | 0.80 | functional | effect-functional |
| `dynamic` | 0.80 | behaviour | behaviour |
| `teeming` | 0.80 | behaviour | behaviour |
| `cyclical` | 0.75 | behaviour | behaviour |
| `generative` | 0.75 | functional | effect-functional |
| `interconnected` | 0.75 | social | social |
| `abundant` | 0.70 | physical | physical-other |
| `resilient` | 0.70 | behaviour | behaviour |
| `fragile` | 0.65 | physical | physical-other |
| `competitive` | 0.60 | behaviour | behaviour |
| `ancient` | 0.55 | social | social |
| `noisy` | 0.55 | physical | physical-other |
| `mortal` | 0.50 | effect | effect-functional |
| `sacred` | 0.45 | social | social |

### `death` (synset `4731`) — 16 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `irreversible` | 0.95 | effect | effect-functional |
| `final` | 0.90 | effect | effect-functional |
| `consequential` | 0.80 | effect | effect-functional |
| `dark` | 0.80 | physical | sensorimotor |
| `fearful` | 0.80 | emotional | emotional |
| `intentional` | 0.80 | behaviour | behaviour |
| `traumatic` | 0.80 | emotional | emotional |
| `violent` | 0.80 | physical | physical-other |
| `abrupt` | 0.75 | behaviour | behaviour |
| `deliberate` | 0.75 | behaviour | behaviour |
| `criminal` | 0.70 | social | social |
| `culpable` | 0.70 | social | social |
| `grievous` | 0.70 | emotional | emotional |
| `criminalised` | 0.65 | social | social |
| `sudden` | 0.65 | behaviour | behaviour |
| `powerful` | 0.60 | behaviour | behaviour |

### `memory` (synset `64741`) — 19 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `past` | 0.90 | functional | effect-functional |
| `emotional` | 0.80 | functional | effect-functional |
| `nostalgic` | 0.80 | emotional | emotional |
| `persistent` | 0.80 | behaviour | behaviour |
| `personal` | 0.80 | social | social |
| `evocative` | 0.75 | effect | effect-functional |
| `reconstructive` | 0.75 | behaviour | behaviour |
| `sensory` | 0.75 | physical | physical-other |
| `meaningful` | 0.70 | functional | effect-functional |
| `selective` | 0.70 | functional | effect-functional |
| `vivid` | 0.70 | physical | physical-other |
| `associative` | 0.65 | behaviour | behaviour |
| `fading` | 0.65 | behaviour | behaviour |
| `narrative` | 0.65 | functional | effect-functional |
| `bittersweet` | 0.60 | emotional | emotional |
| `fragmentary` | 0.60 | physical | physical-other |
| `involuntary` | 0.55 | behaviour | behaviour |
| `precious` | 0.55 | emotional | emotional |
| `distorted` | 0.50 | effect | effect-functional |

### `childhood` (synset `99787`) — 15 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `developing` | 0.90 | behaviour | behaviour |
| `playful` | 0.90 | behaviour | behaviour |
| `innocent` | 0.88 | emotional | emotional |
| `dependent` | 0.85 | social | social |
| `growing` | 0.85 | behaviour | behaviour |
| `curious` | 0.82 | behaviour | behaviour |
| `formative` | 0.80 | effect | effect-functional |
| `learning` | 0.78 | functional | effect-functional |
| `energetic` | 0.75 | behaviour | behaviour |
| `fleeting` | 0.75 | effect | effect-functional |
| `protected` | 0.72 | social | social |
| `carefree` | 0.70 | emotional | emotional |
| `nostalgic` | 0.68 | emotional | emotional |
| `impressionable` | 0.65 | behaviour | behaviour |
| `social` | 0.55 | social | social |

### `age` (synset `59579`) — 17 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `measurable` | 0.90 | functional | effect-functional |
| `cumulative` | 0.85 | behaviour | behaviour |
| `temporal` | 0.85 | physical | physical-other |
| `continuous` | 0.80 | behaviour | behaviour |
| `accumulated` | 0.75 | behaviour | behaviour |
| `indicative` | 0.75 | functional | effect-functional |
| `irreversible` | 0.75 | effect | effect-functional |
| `objective` | 0.70 | functional | effect-functional |
| `historical` | 0.65 | social | social |
| `revealing` | 0.65 | effect | effect-functional |
| `significant` | 0.65 | functional | effect-functional |
| `invisible` | 0.60 | physical | physical-other |
| `relative` | 0.60 | social | social |
| `visible` | 0.60 | physical | physical-other |
| `contextual` | 0.55 | social | social |
| `durable` | 0.55 | physical | physical-other |
| `archaeological` | 0.50 | social | social |

### `youth` (synset `75585`) — 9 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `energetic` | 0.88 | physical | physical-other |
| `collective` | 0.85 | social | social |
| `idealistic` | 0.82 | emotional | emotional |
| `vibrant` | 0.78 | physical | physical-other |
| `hopeful` | 0.75 | emotional | emotional |
| `impressionable` | 0.72 | behaviour | behaviour |
| `changemaking` | 0.68 | effect | effect-functional |
| `powerful` | 0.65 | social | social |
| `rebellious` | 0.65 | behaviour | behaviour |

### `dawn` (synset `104394`) — 11 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `emergent` | 0.90 | behaviour | behaviour |
| `hopeful` | 0.85 | emotional | emotional |
| `nascent` | 0.85 | behaviour | behaviour |
| `awakening` | 0.80 | effect | effect-functional |
| `transitional` | 0.80 | behaviour | behaviour |
| `illuminating` | 0.75 | effect | effect-functional |
| `transformative` | 0.75 | effect | effect-functional |
| `inspiring` | 0.70 | emotional | emotional |
| `tentative` | 0.70 | behaviour | behaviour |
| `pioneering` | 0.65 | social | social |
| `brief` | 0.55 | behaviour | behaviour |

### `knowledge` (synset `359`) — 17 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `accumulated` | 0.85 | behaviour | behaviour |
| `illuminating` | 0.80 | effect | effect-functional |
| `transformative` | 0.80 | effect | effect-functional |
| `empowering` | 0.75 | effect | effect-functional |
| `expansive` | 0.75 | physical | physical-other |
| `invisible` | 0.75 | physical | physical-other |
| `reliable` | 0.75 | functional | effect-functional |
| `structured` | 0.75 | physical | physical-other |
| `connective` | 0.70 | behaviour | behaviour |
| `transferable` | 0.70 | functional | effect-functional |
| `validated` | 0.70 | functional | effect-functional |
| `earned` | 0.65 | social | social |
| `layered` | 0.65 | physical | physical-other |
| `weighty` | 0.65 | physical | physical-other |
| `confident` | 0.60 | emotional | emotional |
| `dynamic` | 0.60 | behaviour | behaviour |
| `fragile` | 0.40 | physical | physical-other |

### `ignorance` (synset `65010`) — 12 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `unknowing` | 1.00 | — | unknown |
| `absent` | 0.95 | physical | physical-other |
| `limiting` | 0.90 | effect | effect-functional |
| `blinding` | 0.80 | effect | effect-functional |
| `vulnerable` | 0.75 | effect | effect-functional |
| `dangerous` | 0.70 | effect | effect-functional |
| `correctable` | 0.60 | functional | effect-functional |
| `uncomfortable` | 0.55 | emotional | emotional |
| `involuntary` | 0.50 | behaviour | behaviour |
| `stigmatised` | 0.50 | social | social |
| `shameful` | 0.45 | emotional | emotional |
| `prevalent` | 0.40 | social | social |

### `idea` (synset `64981`) — 18 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `actionable` | 0.90 | functional | effect-functional |
| `purposeful` | 0.90 | behaviour | behaviour |
| `deliberate` | 0.85 | behaviour | behaviour |
| `directed` | 0.85 | behaviour | behaviour |
| `mental` | 0.80 | physical | physical-other |
| `planned` | 0.80 | behaviour | behaviour |
| `motivated` | 0.75 | emotional | emotional |
| `motivating` | 0.75 | effect | effect-functional |
| `invisible` | 0.70 | physical | physical-other |
| `shaping` | 0.70 | functional | effect-functional |
| `specific` | 0.70 | behaviour | behaviour |
| `anticipatory` | 0.65 | emotional | emotional |
| `committed` | 0.65 | emotional | emotional |
| `formed` | 0.60 | behaviour | behaviour |
| `fragile` | 0.60 | effect | effect-functional |
| `consequential` | 0.55 | effect | effect-functional |
| `private` | 0.55 | social | social |
| `flexible` | 0.40 | behaviour | sensorimotor |

### `argument` (synset `67993`) — 11 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `assertive` | 0.90 | behaviour | behaviour |
| `evidential` | 0.90 | functional | effect-functional |
| `verifiable` | 0.80 | functional | effect-functional |
| `logical` | 0.75 | functional | effect-functional |
| `structured` | 0.75 | physical | physical-other |
| `definitive` | 0.70 | behaviour | behaviour |
| `persuasive` | 0.70 | functional | effect-functional |
| `formal` | 0.65 | social | social |
| `authoritative` | 0.60 | social | social |
| `contestable` | 0.60 | social | social |
| `concise` | 0.50 | physical | physical-other |

### `theory` (synset `64516`) — 12 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `tentative` | 0.95 | behaviour | behaviour |
| `explanatory` | 0.90 | functional | effect-functional |
| `provisional` | 0.90 | physical | physical-other |
| `unverified` | 0.90 | physical | physical-other |
| `testable` | 0.85 | functional | effect-functional |
| `falsifiable` | 0.80 | functional | effect-functional |
| `speculative` | 0.80 | behaviour | behaviour |
| `predictive` | 0.75 | functional | effect-functional |
| `insightful` | 0.70 | emotional | emotional |
| `generative` | 0.65 | effect | effect-functional |
| `intellectual` | 0.60 | social | social |
| `courageous` | 0.45 | emotional | emotional |

### `mind` (synset `63153`) — 12 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `analytical` | 0.85 | behaviour | behaviour |
| `sharp` | 0.80 | physical | sensorimotor |
| `powerful` | 0.75 | functional | effect-functional |
| `discerning` | 0.70 | behaviour | behaviour |
| `rigorous` | 0.70 | behaviour | behaviour |
| `capacious` | 0.65 | physical | physical-other |
| `abstract` | 0.60 | physical | physical-other |
| `illuminating` | 0.60 | effect | effect-functional |
| `cultivated` | 0.55 | social | social |
| `disciplined` | 0.55 | behaviour | behaviour |
| `admired` | 0.50 | emotional | emotional |
| `expansive` | 0.50 | physical | physical-other |

### `thought` (synset `64255`) — 19 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `mental` | 0.95 | physical | physical-other |
| `abstract` | 0.85 | physical | physical-other |
| `central` | 0.85 | functional | effect-functional |
| `intangible` | 0.85 | physical | physical-other |
| `forming` | 0.80 | behaviour | behaviour |
| `invisible` | 0.80 | physical | physical-other |
| `connecting` | 0.75 | behaviour | behaviour |
| `generative` | 0.75 | functional | effect-functional |
| `fluid` | 0.70 | behaviour | behaviour |
| `illuminating` | 0.70 | effect | effect-functional |
| `associative` | 0.65 | behaviour | behaviour |
| `compelling` | 0.60 | emotional | emotional |
| `expansive` | 0.60 | behaviour | behaviour |
| `shared` | 0.60 | social | social |
| `variable` | 0.60 | behaviour | behaviour |
| `expressible` | 0.55 | functional | effect-functional |
| `formless` | 0.55 | physical | physical-other |
| `persistent` | 0.55 | behaviour | behaviour |
| `unconscious` | 0.50 | behaviour | behaviour |

### `wisdom` (synset `59407`) — 10 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `insightful` | 0.92 | functional | effect-functional |
| `experienced` | 0.88 | functional | effect-functional |
| `respected` | 0.88 | social | social |
| `discerning` | 0.85 | functional | effect-functional |
| `measured` | 0.80 | behaviour | behaviour |
| `guiding` | 0.78 | functional | effect-functional |
| `thoughtful` | 0.75 | behaviour | behaviour |
| `calm` | 0.72 | emotional | emotional |
| `grounded` | 0.68 | emotional | emotional |
| `rare` | 0.62 | social | social |

### `power` (synset `84934`) — 19 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `authoritative` | 0.90 | social | social |
| `influential` | 0.90 | functional | effect-functional |
| `dominant` | 0.85 | behaviour | behaviour |
| `formidable` | 0.85 | emotional | emotional |
| `commanding` | 0.80 | social | social |
| `decisive` | 0.80 | behaviour | behaviour |
| `centralised` | 0.75 | social | social |
| `respected` | 0.75 | social | social |
| `feared` | 0.70 | emotional | emotional |
| `present` | 0.70 | behaviour | behaviour |
| `strategic` | 0.70 | behaviour | behaviour |
| `connected` | 0.65 | social | social |
| `uncontested` | 0.65 | behaviour | behaviour |
| `imposing` | 0.60 | physical | physical-other |
| `structural` | 0.60 | social | social |
| `visible` | 0.60 | social | social |
| `wealthy` | 0.60 | social | social |
| `ambitious` | 0.55 | emotional | emotional |
| `durable` | 0.55 | behaviour | behaviour |

### `freedom` (synset `100320`) — 20 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `spared` | 1.00 | — | unknown |
| `unburdened` | 0.90 | physical | physical-other |
| `liberating` | 0.88 | emotional | emotional |
| `privileged` | 0.85 | social | social |
| `relieved` | 0.85 | emotional | emotional |
| `relieving` | 0.82 | emotional | emotional |
| `unbinding` | 0.80 | effect | effect-functional |
| `official` | 0.78 | social | social |
| `legal` | 0.75 | functional | effect-functional |
| `protected` | 0.75 | functional | effect-functional |
| `conditional` | 0.72 | functional | effect-functional |
| `advantageous` | 0.70 | functional | effect-functional |
| `granted` | 0.70 | social | social |
| `permissive` | 0.68 | functional | effect-functional |
| `exclusive` | 0.65 | social | social |
| `asymmetric` | 0.60 | social | social |
| `formal` | 0.60 | social | social |
| `documented` | 0.55 | functional | effect-functional |
| `invisible` | 0.50 | physical | physical-other |
| `temporary` | 0.40 | behaviour | behaviour |

### `law` (synset `67386`) — 18 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `binding` | 0.95 | functional | effect-functional |
| `regulatory` | 0.90 | functional | effect-functional |
| `written` | 0.90 | physical | physical-other |
| `authoritative` | 0.85 | social | social |
| `enforceable` | 0.85 | functional | effect-functional |
| `specific` | 0.85 | functional | effect-functional |
| `formal` | 0.80 | physical | physical-other |
| `precise` | 0.80 | functional | effect-functional |
| `codified` | 0.75 | physical | physical-other |
| `prescriptive` | 0.75 | behaviour | behaviour |
| `public` | 0.75 | social | social |
| `consequential` | 0.70 | effect | effect-functional |
| `restrictive` | 0.70 | effect | effect-functional |
| `structured` | 0.70 | physical | physical-other |
| `procedural` | 0.65 | behaviour | behaviour |
| `impersonal` | 0.60 | social | social |
| `punitive` | 0.60 | effect | effect-functional |
| `changeable` | 0.55 | behaviour | behaviour |

### `corruption` (synset `3346`) — 11 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `immoral` | 0.95 | emotional | emotional |
| `betrayal` | 0.90 | effect | effect-functional |
| `covert` | 0.90 | behaviour | behaviour |
| `illegal` | 0.90 | social | social |
| `transactional` | 0.85 | functional | effect-functional |
| `destructive` | 0.80 | effect | effect-functional |
| `secretive` | 0.80 | behaviour | behaviour |
| `insidious` | 0.75 | behaviour | behaviour |
| `shameful` | 0.75 | emotional | emotional |
| `corrosive` | 0.70 | effect | effect-functional |
| `pervasive` | 0.65 | behaviour | behaviour |

### `revolution` (synset `18402`) — 12 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `destabilizing` | 1.00 | — | unknown |
| `transformative` | 0.95 | effect | effect-functional |
| `collective` | 0.80 | social | social |
| `violent` | 0.80 | behaviour | behaviour |
| `popular` | 0.75 | social | social |
| `chaotic` | 0.70 | behaviour | behaviour |
| `dangerous` | 0.70 | effect | effect-functional |
| `ideological` | 0.70 | social | social |
| `irreversible` | 0.65 | effect | effect-functional |
| `historic` | 0.60 | social | social |
| `sudden` | 0.60 | behaviour | behaviour |
| `hopeful` | 0.50 | emotional | emotional |

### `justice` (synset `14402`) — 22 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `authoritative` | 1.00 | — | unknown |
| `binding` | 1.00 | — | unknown |
| `ceremonial` | 1.00 | — | unknown |
| `consequential` | 1.00 | — | unknown |
| `decisive` | 1.00 | — | unknown |
| `deliberate` | 1.00 | — | unknown |
| `formal` | 1.00 | — | unknown |
| `impartial` | 1.00 | — | unknown |
| `measured` | 1.00 | — | unknown |
| `procedural` | 1.00 | — | unknown |
| `retributive` | 1.00 | — | unknown |
| `solemn` | 1.00 | — | unknown |
| `weighing` | 1.00 | — | unknown |
| `deliberative` | 0.90 | behaviour | behaviour |
| `balanced` | 0.85 | functional | effect-functional |
| `weighty` | 0.85 | emotional | emotional |
| `moral` | 0.75 | emotional | emotional |
| `balancing` | 0.70 | behaviour | behaviour |
| `structured` | 0.65 | functional | effect-functional |
| `punitive` | 0.60 | effect | effect-functional |
| `rewardful` | 0.60 | effect | effect-functional |
| `restorative` | 0.45 | effect | effect-functional |

### `democracy` (synset `65923`) — 16 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `egalitarian` | 0.90 | functional | effect-functional |
| `ideological` | 0.90 | social | social |
| `participatory` | 0.90 | behaviour | behaviour |
| `inclusive` | 0.85 | functional | effect-functional |
| `representative` | 0.85 | functional | effect-functional |
| `collective` | 0.80 | social | social |
| `principled` | 0.80 | functional | effect-functional |
| `civic` | 0.75 | social | social |
| `influential` | 0.75 | effect | effect-functional |
| `liberating` | 0.75 | emotional | emotional |
| `aspirational` | 0.70 | emotional | emotional |
| `normative` | 0.70 | functional | effect-functional |
| `contested` | 0.65 | social | social |
| `evolving` | 0.65 | behaviour | behaviour |
| `pluralistic` | 0.65 | social | social |
| `progressive` | 0.60 | social | social |

### `heart` (synset `51552`) — 17 properties, 3 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `suit-marked` | 1.00 | — | unknown |
| `red` | 0.97 | physical | sensorimotor |
| `flat` | 0.82 | physical | physical-other |
| `numbered` | 0.82 | functional | effect-functional |
| `ranked` | 0.82 | functional | effect-functional |
| `familiar` | 0.75 | emotional | emotional |
| `glossy` | 0.72 | physical | sensorimotor |
| `symbolic` | 0.72 | emotional | emotional |
| `lightweight` | 0.70 | physical | physical-other |
| `printed` | 0.68 | physical | physical-other |
| `romantic` | 0.65 | emotional | emotional |
| `strategic` | 0.65 | functional | effect-functional |
| `smooth` | 0.62 | physical | sensorimotor |
| `competitive` | 0.60 | social | social |
| `rectangular` | 0.58 | physical | physical-other |
| `collectible` | 0.55 | functional | effect-functional |
| `lucky` | 0.55 | emotional | emotional |

### `blood` (synset `58122`) — 17 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `innate` | 0.90 | functional | effect-functional |
| `deep` | 0.85 | physical | physical-other |
| `defining` | 0.80 | functional | effect-functional |
| `hereditary` | 0.80 | social | social |
| `inherited` | 0.80 | social | social |
| `ancestral` | 0.75 | social | social |
| `constitutional` | 0.75 | functional | effect-functional |
| `essential` | 0.75 | functional | effect-functional |
| `passionate` | 0.70 | emotional | emotional |
| `unchangeable` | 0.70 | behaviour | behaviour |
| `visceral` | 0.70 | emotional | emotional |
| `vital` | 0.70 | physical | physical-other |
| `volatile` | 0.70 | behaviour | behaviour |
| `flowing` | 0.65 | behaviour | behaviour |
| `primal` | 0.65 | emotional | emotional |
| `unalterable` | 0.60 | effect | effect-functional |
| `energising` | 0.50 | effect | effect-functional |

### `breath` (synset `16473`) — 12 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `vital` | 0.95 | functional | effect-functional |
| `rhythmic` | 0.92 | behaviour | sensorimotor |
| `continuous` | 0.88 | behaviour | behaviour |
| `cyclical` | 0.88 | behaviour | behaviour |
| `involuntary` | 0.82 | behaviour | behaviour |
| `gaseous` | 0.75 | physical | physical-other |
| `expansive` | 0.72 | physical | physical-other |
| `audible` | 0.62 | physical | physical-other |
| `calming` | 0.60 | emotional | emotional |
| `controllable` | 0.55 | behaviour | behaviour |
| `meditative` | 0.50 | emotional | emotional |
| `muscular` | 0.45 | physical | physical-other |

### `bone` (synset `6507`) — 12 properties, 4 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `hard` | 0.95 | physical | sensorimotor |
| `rigid` | 0.90 | physical | sensorimotor |
| `dense` | 0.85 | physical | sensorimotor |
| `calcified` | 0.80 | physical | physical-other |
| `pale` | 0.80 | physical | physical-other |
| `durable` | 0.75 | physical | physical-other |
| `structural` | 0.75 | functional | effect-functional |
| `smooth` | 0.70 | physical | sensorimotor |
| `organic` | 0.60 | physical | physical-other |
| `porous` | 0.55 | physical | physical-other |
| `tactile` | 0.50 | physical | physical-other |
| `carved` | 0.40 | social | social |

### `skin` (synset `55774`) — 16 properties, 4 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `outermost` | 0.90 | physical | physical-other |
| `thin` | 0.90 | physical | sensorimotor |
| `covering` | 0.85 | functional | effect-functional |
| `boundary` | 0.80 | functional | effect-functional |
| `protective` | 0.80 | functional | effect-functional |
| `smooth` | 0.75 | physical | sensorimotor |
| `flexible` | 0.70 | physical | sensorimotor |
| `visible` | 0.70 | physical | physical-other |
| `continuous` | 0.65 | physical | physical-other |
| `defining` | 0.65 | functional | effect-functional |
| `delicate` | 0.60 | physical | physical-other |
| `fragile` | 0.60 | physical | physical-other |
| `taut` | 0.60 | physical | sensorimotor |
| `tensile` | 0.55 | physical | physical-other |
| `permeable` | 0.50 | physical | physical-other |
| `varied` | 0.40 | physical | physical-other |

### `eye` (synset `78198`) — 17 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `central` | 0.95 | physical | physical-other |
| `focal` | 0.85 | functional | effect-functional |
| `equidistant` | 0.80 | physical | physical-other |
| `enclosed` | 0.75 | physical | physical-other |
| `surrounded` | 0.75 | physical | physical-other |
| `convergent` | 0.70 | functional | effect-functional |
| `still` | 0.70 | behaviour | sensorimotor |
| `orienting` | 0.65 | functional | effect-functional |
| `pivotal` | 0.65 | functional | effect-functional |
| `bounded` | 0.60 | physical | physical-other |
| `defined` | 0.60 | physical | physical-other |
| `nodal` | 0.60 | functional | effect-functional |
| `calm` | 0.55 | emotional | emotional |
| `sheltered` | 0.55 | effect | effect-functional |
| `concentrated` | 0.50 | physical | physical-other |
| `geographic` | 0.45 | physical | physical-other |
| `symbolic` | 0.40 | social | social |

### `silence` (synset `59903`) — 10 properties, 2 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `still` | 0.95 | physical | sensorimotor |
| `empty` | 0.85 | physical | physical-other |
| `calming` | 0.80 | effect | effect-functional |
| `peaceful` | 0.80 | emotional | emotional |
| `restorative` | 0.70 | effect | effect-functional |
| `meditative` | 0.65 | emotional | emotional |
| `vast` | 0.65 | physical | sensorimotor |
| `penetrating` | 0.60 | behaviour | behaviour |
| `stark` | 0.60 | emotional | emotional |
| `rare` | 0.55 | social | social |

### `loneliness` (synset `58089`) — 10 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `solitary` | 0.95 | behaviour | behaviour |
| `withdrawn` | 0.80 | behaviour | behaviour |
| `reclusive` | 0.75 | behaviour | behaviour |
| `reserved` | 0.75 | social | social |
| `introspective` | 0.70 | behaviour | behaviour |
| `quiet` | 0.70 | behaviour | sensorimotor |
| `contemplative` | 0.60 | behaviour | behaviour |
| `independent` | 0.60 | functional | effect-functional |
| `melancholic` | 0.50 | emotional | emotional |
| `serene` | 0.40 | emotional | emotional |

### `chaos` (synset `66058`) — 12 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `fractal` | 1.00 | — | unknown |
| `unpredictable` | 0.95 | behaviour | behaviour |
| `sensitive` | 0.92 | behaviour | behaviour |
| `nonlinear` | 0.88 | behaviour | behaviour |
| `complex` | 0.85 | functional | effect-functional |
| `diverging` | 0.82 | behaviour | behaviour |
| `unstable` | 0.80 | behaviour | behaviour |
| `deterministic` | 0.75 | functional | effect-functional |
| `aperiodic` | 0.72 | behaviour | behaviour |
| `counterintuitive` | 0.65 | emotional | emotional |
| `mathematical` | 0.60 | social | social |
| `bounded` | 0.55 | physical | physical-other |

### `peace` (synset `97322`) — 18 properties, 2 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `ceasefire` | 1.00 | — | unknown |
| `pacific` | 1.00 | — | unknown |
| `safe` | 0.95 | emotional | emotional |
| `stable` | 0.90 | effect | effect-functional |
| `diplomatic` | 0.80 | social | social |
| `valued` | 0.80 | emotional | emotional |
| `silent` | 0.75 | physical | sensorimotor |
| `civil` | 0.70 | social | social |
| `enabling` | 0.70 | functional | effect-functional |
| `prosperous` | 0.70 | effect | effect-functional |
| `fragile` | 0.65 | behaviour | behaviour |
| `hopeful` | 0.65 | emotional | emotional |
| `rebuilding` | 0.60 | effect | effect-functional |
| `unarmed` | 0.60 | physical | physical-other |
| `celebrated` | 0.55 | social | social |
| `normalising` | 0.55 | social | social |
| `enduring` | 0.50 | behaviour | behaviour |
| `quiet` | 0.50 | physical | sensorimotor |

### `truth` (synset `64180`) — 19 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `confirmed` | 0.95 | functional | effect-functional |
| `verified` | 0.95 | functional | effect-functional |
| `certain` | 0.90 | emotional | emotional |
| `objective` | 0.85 | physical | physical-other |
| `solid` | 0.85 | physical | physical-other |
| `immovable` | 0.80 | physical | physical-other |
| `revealing` | 0.80 | effect | effect-functional |
| `stable` | 0.80 | behaviour | behaviour |
| `clarifying` | 0.75 | effect | effect-functional |
| `grounded` | 0.75 | physical | physical-other |
| `tested` | 0.75 | behaviour | behaviour |
| `enduring` | 0.70 | behaviour | behaviour |
| `foundational` | 0.70 | functional | effect-functional |
| `grounding` | 0.65 | emotional | emotional |
| `immutable` | 0.65 | behaviour | behaviour |
| `resilient` | 0.65 | behaviour | behaviour |
| `authoritative` | 0.60 | social | social |
| `universal` | 0.55 | social | social |
| `confronting` | 0.50 | emotional | emotional |

### `jealousy` (synset `63614`) — 12 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `vigilant` | 0.95 | behaviour | behaviour |
| `protective` | 0.90 | functional | effect-functional |
| `alert` | 0.85 | behaviour | behaviour |
| `intense` | 0.80 | emotional | emotional |
| `tireless` | 0.75 | behaviour | behaviour |
| `territorial` | 0.70 | behaviour | behaviour |
| `possessive` | 0.65 | emotional | emotional |
| `controlling` | 0.60 | behaviour | behaviour |
| `steadfast` | 0.60 | behaviour | behaviour |
| `anxious` | 0.55 | emotional | emotional |
| `devoted` | 0.50 | social | social |
| `solemn` | 0.40 | emotional | emotional |

### `ambition` (synset `72585`) — 10 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `envisioned` | 1.00 | — | unknown |
| `cherished` | 0.90 | emotional | emotional |
| `hopeful` | 0.85 | emotional | emotional |
| `motivating` | 0.85 | functional | effect-functional |
| `personal` | 0.80 | social | social |
| `defining` | 0.70 | social | social |
| `sustaining` | 0.70 | effect | effect-functional |
| `vulnerable` | 0.65 | emotional | emotional |
| `specific` | 0.60 | functional | effect-functional |
| `galvanising` | 0.55 | effect | effect-functional |

### `conscience` (synset `59189`) — 9 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `guiding` | 0.92 | functional | effect-functional |
| `moral` | 0.90 | social | social |
| `inward` | 0.88 | emotional | emotional |
| `restraining` | 0.80 | functional | effect-functional |
| `persistent` | 0.78 | behaviour | behaviour |
| `judgmental` | 0.75 | behaviour | behaviour |
| `weighty` | 0.72 | emotional | emotional |
| `nagging` | 0.68 | behaviour | behaviour |
| `silent` | 0.60 | behaviour | sensorimotor |

### `imagination` (synset `63189`) — 11 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `vivid` | 0.85 | physical | physical-other |
| `unbounded` | 0.80 | behaviour | behaviour |
| `visual` | 0.80 | physical | physical-other |
| `creative` | 0.75 | functional | effect-functional |
| `internal` | 0.70 | physical | physical-other |
| `fluid` | 0.65 | behaviour | behaviour |
| `inspiring` | 0.65 | emotional | emotional |
| `fertile` | 0.60 | functional | effect-functional |
| `private` | 0.60 | social | social |
| `escapist` | 0.55 | emotional | emotional |
| `childlike` | 0.50 | social | social |

### `fate` (synset `79798`) — 11 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `inevitable` | 0.95 | effect | effect-functional |
| `inescapable` | 0.90 | effect | effect-functional |
| `predetermined` | 0.90 | functional | effect-functional |
| `controlling` | 0.85 | functional | effect-functional |
| `weighty` | 0.80 | emotional | emotional |
| `abstract` | 0.75 | physical | physical-other |
| `mysterious` | 0.75 | emotional | emotional |
| `cosmic` | 0.70 | social | social |
| `purposeful` | 0.70 | functional | effect-functional |
| `humbling` | 0.65 | emotional | emotional |
| `ancient` | 0.55 | social | social |

### `fury` (synset `72773`) — 1 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `volcanic` | 1.00 | — | unknown |

### `melancholy` (synset `24456`) — 13 properties, 4 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `doleful` | 1.00 | — | unknown |
| `sorrowful` | 0.95 | emotional | emotional |
| `heavy` | 0.85 | emotional | sensorimotor |
| `quiet` | 0.80 | behaviour | sensorimotor |
| `wistful` | 0.80 | emotional | emotional |
| `introspective` | 0.75 | emotional | emotional |
| `persistent` | 0.70 | behaviour | behaviour |
| `grey` | 0.65 | physical | sensorimotor |
| `slow` | 0.65 | behaviour | sensorimotor |
| `isolating` | 0.60 | effect | effect-functional |
| `tender` | 0.60 | emotional | emotional |
| `beautiful` | 0.55 | emotional | emotional |
| `autumnal` | 0.50 | social | social |

### `resentment` (synset `72950`) — 1 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `unforgiving` | 1.00 | — | unknown |

### `dread` (synset `30151`) — 17 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `threatening` | 0.90 | functional | effect-functional |
| `primal` | 0.88 | emotional | emotional |
| `alarming` | 0.85 | effect | effect-functional |
| `visceral` | 0.82 | physical | physical-other |
| `intense` | 0.80 | emotional | emotional |
| `paralysing` | 0.80 | effect | effect-functional |
| `paralyzing` | 0.78 | effect | effect-functional |
| `overwhelming` | 0.75 | emotional | emotional |
| `urgent` | 0.75 | behaviour | behaviour |
| `avoidant` | 0.72 | behaviour | behaviour |
| `cold` | 0.70 | physical | sensorimotor |
| `constricting` | 0.70 | physical | physical-other |
| `primitive` | 0.70 | emotional | emotional |
| `involuntary` | 0.65 | behaviour | behaviour |
| `anticipatory` | 0.60 | behaviour | behaviour |
| `irrational` | 0.55 | behaviour | behaviour |
| `contagious` | 0.50 | social | social |

### `envy` (synset `30821`) — 11 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `desiring` | 1.00 | — | unknown |
| `jealous` | 1.00 | — | unknown |
| `bittersweet` | 0.90 | emotional | emotional |
| `comparative` | 0.90 | social | social |
| `admiring` | 0.85 | emotional | emotional |
| `yearning` | 0.85 | behaviour | behaviour |
| `mixed` | 0.80 | emotional | emotional |
| `social` | 0.80 | social | social |
| `persistent` | 0.65 | behaviour | behaviour |
| `quiet` | 0.60 | behaviour | sensorimotor |
| `aspirational` | 0.55 | emotional | emotional |

### `bliss` (synset `97412`) — 13 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `ecstatic` | 1.00 | — | unknown |
| `joyful` | 0.95 | emotional | emotional |
| `serene` | 0.85 | emotional | emotional |
| `fulfilled` | 0.80 | emotional | emotional |
| `peaceful` | 0.80 | emotional | emotional |
| `complete` | 0.75 | functional | effect-functional |
| `warm` | 0.75 | physical | sensorimotor |
| `radiant` | 0.70 | physical | physical-other |
| `weightless` | 0.70 | physical | physical-other |
| `dreamy` | 0.65 | emotional | emotional |
| `elevated` | 0.65 | emotional | emotional |
| `glowing` | 0.60 | physical | physical-other |
| `timeless` | 0.55 | behaviour | behaviour |

### `bitterness` (synset `59971`) — 10 properties, 2 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `harsh` | 0.90 | physical | physical-other |
| `unpleasant` | 0.90 | emotional | emotional |
| `sharp` | 0.85 | physical | sensorimotor |
| `astringent` | 0.80 | physical | physical-other |
| `lingering` | 0.80 | behaviour | behaviour |
| `aversive` | 0.75 | effect | effect-functional |
| `intense` | 0.75 | physical | physical-other |
| `drying` | 0.70 | effect | effect-functional |
| `pungent` | 0.65 | physical | sensorimotor |
| `acquired` | 0.60 | social | social |

### `tenderness` (synset `58112`) — 12 properties, 3 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `gentle` | 0.95 | behaviour | behaviour |
| `affectionate` | 0.90 | emotional | emotional |
| `caring` | 0.90 | functional | effect-functional |
| `warm` | 0.90 | emotional | sensorimotor |
| `soft` | 0.85 | physical | sensorimotor |
| `intimate` | 0.80 | social | social |
| `nurturing` | 0.75 | functional | effect-functional |
| `empathetic` | 0.70 | social | social |
| `soothing` | 0.70 | effect | effect-functional |
| `healing` | 0.65 | effect | effect-functional |
| `vulnerable` | 0.65 | emotional | emotional |
| `quiet` | 0.60 | behaviour | sensorimotor |

### `euphoria` (synset `72836`) — 3 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `cloud-like` | 1.00 | — | unknown |
| `giddy` | 1.00 | — | unknown |
| `unrealistic` | 1.00 | — | unknown |

### `apathy` (synset `58161`) — 13 properties, 3 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `uninvested` | 1.00 | — | unknown |
| `passive` | 0.90 | behaviour | behaviour |
| `detached` | 0.85 | emotional | emotional |
| `disengaged` | 0.80 | social | social |
| `unresponsive` | 0.80 | behaviour | behaviour |
| `flat` | 0.75 | behaviour | behaviour |
| `draining` | 0.70 | effect | effect-functional |
| `resigned` | 0.70 | emotional | emotional |
| `isolating` | 0.65 | effect | effect-functional |
| `stagnant` | 0.65 | effect | effect-functional |
| `heavy` | 0.60 | physical | sensorimotor |
| `slow` | 0.60 | behaviour | sensorimotor |
| `grey` | 0.55 | physical | sensorimotor |

### `remorse` (synset `72875`) — 2 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `corroding` | 1.00 | — | unknown |
| `self-reproaching` | 1.00 | — | unknown |

### `ecstasy` (synset `42988`) — 15 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `ecstatic` | 1.00 | — | unknown |
| `empathogenic` | 1.00 | — | unknown |
| `euphoric` | 0.95 | emotional | emotional |
| `illegal` | 0.90 | social | social |
| `energetic` | 0.85 | behaviour | behaviour |
| `stimulating` | 0.85 | effect | effect-functional |
| `social` | 0.80 | social | social |
| `risky` | 0.75 | effect | effect-functional |
| `taboo` | 0.75 | social | social |
| `dangerous` | 0.70 | effect | effect-functional |
| `dehydrating` | 0.70 | effect | effect-functional |
| `transient` | 0.70 | behaviour | behaviour |
| `nocturnal` | 0.65 | social | social |
| `synthetic` | 0.60 | physical | physical-other |
| `crystalline` | 0.55 | physical | physical-other |

### `serenity` (synset `59481`) — 11 properties, 3 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `serene` | 0.90 | emotional | emotional |
| `still` | 0.90 | physical | sensorimotor |
| `untroubled` | 0.80 | effect | effect-functional |
| `mild` | 0.75 | behaviour | behaviour |
| `steady` | 0.75 | behaviour | sensorimotor |
| `passive` | 0.70 | behaviour | behaviour |
| `gentle` | 0.65 | emotional | emotional |
| `smooth` | 0.65 | physical | sensorimotor |
| `detached` | 0.60 | emotional | emotional |
| `soothing` | 0.55 | social | social |
| `deep` | 0.50 | physical | physical-other |

### `panic` (synset `99680`) — 12 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `sudden` | 0.95 | behaviour | behaviour |
| `contagious` | 0.90 | behaviour | behaviour |
| `overwhelming` | 0.85 | emotional | emotional |
| `frantic` | 0.80 | behaviour | behaviour |
| `irrational` | 0.80 | behaviour | behaviour |
| `collective` | 0.75 | social | social |
| `urgent` | 0.75 | behaviour | behaviour |
| `breathless` | 0.70 | physical | physical-other |
| `loud` | 0.70 | physical | sensorimotor |
| `scattered` | 0.65 | behaviour | behaviour |
| `anticipatory` | 0.60 | emotional | emotional |
| `destabilising` | 0.55 | effect | effect-functional |

### `wrath` (synset `15373`) — 12 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `explosive` | 0.95 | behaviour | behaviour |
| `consuming` | 0.90 | behaviour | behaviour |
| `destructive` | 0.90 | effect | effect-functional |
| `violent` | 0.90 | effect | effect-functional |
| `burning` | 0.85 | physical | sensorimotor |
| `uncontrolled` | 0.85 | behaviour | behaviour |
| `overwhelming` | 0.80 | emotional | emotional |
| `righteous` | 0.75 | emotional | emotional |
| `retributive` | 0.70 | functional | effect-functional |
| `sinful` | 0.70 | social | social |
| `primal` | 0.65 | emotional | emotional |
| `regrettable` | 0.55 | emotional | emotional |

### `pity` (synset `71602`) — 2 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `dismaying` | 1.00 | — | unknown |
| `setback` | 1.00 | — | unknown |

### `gloom` (synset `72859`) — 1 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `dreadful` | 1.00 | — | unknown |

### `agony` (synset `99192`) — 11 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `intense` | 0.95 | physical | physical-other |
| `acute` | 0.90 | behaviour | behaviour |
| `overwhelming` | 0.90 | effect | effect-functional |
| `consuming` | 0.85 | emotional | emotional |
| `distressing` | 0.85 | emotional | emotional |
| `immobilising` | 0.80 | effect | effect-functional |
| `inescapable` | 0.80 | emotional | emotional |
| `exhausting` | 0.75 | effect | effect-functional |
| `urgent` | 0.75 | functional | effect-functional |
| `isolating` | 0.70 | social | social |
| `physiological` | 0.70 | physical | physical-other |

### `compassion` (synset `59094`) — 13 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `moved` | 1.00 | — | unknown |
| `empathetic` | 0.90 | emotional | emotional |
| `warm` | 0.90 | physical | sensorimotor |
| `humane` | 0.85 | social | social |
| `generous` | 0.80 | behaviour | behaviour |
| `selfless` | 0.80 | social | social |
| `gentle` | 0.75 | physical | physical-other |
| `healing` | 0.75 | effect | effect-functional |
| `active` | 0.70 | behaviour | behaviour |
| `tender` | 0.70 | emotional | emotional |
| `binding` | 0.65 | social | social |
| `patient` | 0.65 | behaviour | behaviour |
| `sorrowful` | 0.60 | emotional | emotional |

### `indignation` (synset `72777`) — 1 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `outraged` | 1.00 | — | unknown |

### `torment` (synset `72785`) — 1 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `tormenting` | 1.00 | — | unknown |

### `rapture` (synset `97413`) — 14 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `ecstatic` | 1.00 | — | unknown |
| `exultant` | 1.00 | — | unknown |
| `elated` | 0.95 | emotional | emotional |
| `intense` | 0.90 | emotional | emotional |
| `euphoric` | 0.85 | emotional | emotional |
| `overwhelming` | 0.85 | behaviour | behaviour |
| `rapturous` | 0.80 | emotional | emotional |
| `breathless` | 0.75 | physical | physical-other |
| `transcendent` | 0.75 | emotional | emotional |
| `radiant` | 0.70 | physical | physical-other |
| `trembling` | 0.65 | physical | physical-other |
| `unbounded` | 0.65 | behaviour | behaviour |
| `speechless` | 0.60 | effect | effect-functional |
| `timeless` | 0.50 | behaviour | behaviour |

### `irritation` (synset `100334`) — 12 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `oversensitive` | 1.00 | — | unknown |
| `heightened` | 0.92 | physical | physical-other |
| `reactive` | 0.90 | behaviour | behaviour |
| `sensitised` | 0.90 | physical | physical-other |
| `painful` | 0.85 | effect | effect-functional |
| `uncomfortable` | 0.85 | emotional | emotional |
| `inflamed` | 0.82 | physical | physical-other |
| `burning` | 0.80 | physical | sensorimotor |
| `persistent` | 0.78 | behaviour | behaviour |
| `involuntary` | 0.72 | behaviour | behaviour |
| `disruptive` | 0.70 | effect | effect-functional |
| `localised` | 0.65 | physical | physical-other |

### `courage` (synset `59234`) — 14 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `gutsy` | 1.00 | — | unknown |
| `stalwart` | 1.00 | — | unknown |
| `valiant` | 1.00 | — | unknown |
| `fearless` | 0.92 | emotional | emotional |
| `resolute` | 0.88 | behaviour | behaviour |
| `admired` | 0.78 | social | social |
| `inspiring` | 0.75 | emotional | emotional |
| `active` | 0.70 | behaviour | behaviour |
| `enduring` | 0.68 | behaviour | behaviour |
| `tested` | 0.65 | effect | effect-functional |
| `dignified` | 0.62 | emotional | emotional |
| `protective` | 0.58 | functional | effect-functional |
| `rare` | 0.50 | social | social |
| `earned` | 0.45 | social | social |

### `vulnerability` (synset `100401`) — 12 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `exposed` | 0.95 | physical | physical-other |
| `susceptible` | 0.90 | behaviour | behaviour |
| `unguarded` | 0.88 | physical | physical-other |
| `exploitable` | 0.85 | functional | effect-functional |
| `undefended` | 0.85 | physical | physical-other |
| `fragile` | 0.82 | physical | physical-other |
| `open` | 0.82 | physical | physical-other |
| `anxious` | 0.80 | emotional | emotional |
| `permeable` | 0.78 | physical | physical-other |
| `precarious` | 0.78 | behaviour | behaviour |
| `uncomfortable` | 0.72 | emotional | emotional |
| `contingent` | 0.60 | behaviour | behaviour |

### `numbness` (synset `99187`) — 13 properties, 3 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `disconcerting` | 1.00 | — | unknown |
| `absent` | 0.95 | physical | physical-other |
| `disconnected` | 0.85 | emotional | emotional |
| `pathological` | 0.85 | effect | effect-functional |
| `diagnostic` | 0.80 | functional | effect-functional |
| `tingling` | 0.80 | physical | sensorimotor |
| `alarming` | 0.75 | emotional | emotional |
| `spreading` | 0.75 | behaviour | behaviour |
| `cold` | 0.70 | physical | sensorimotor |
| `silent` | 0.70 | physical | sensorimotor |
| `debilitating` | 0.65 | effect | effect-functional |
| `transient` | 0.60 | behaviour | behaviour |
| `protective` | 0.35 | functional | effect-functional |

### `passion` (synset `64149`) — 16 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `cherished` | 0.95 | emotional | emotional |
| `devoted` | 0.90 | behaviour | behaviour |
| `enduring` | 0.85 | behaviour | behaviour |
| `meaningful` | 0.85 | emotional | emotional |
| `personal` | 0.85 | emotional | emotional |
| `central` | 0.80 | functional | effect-functional |
| `irreplaceable` | 0.80 | functional | effect-functional |
| `precious` | 0.80 | emotional | emotional |
| `idealised` | 0.75 | emotional | emotional |
| `nurturing` | 0.75 | behaviour | behaviour |
| `comforting` | 0.70 | emotional | emotional |
| `consuming` | 0.70 | behaviour | behaviour |
| `inspiring` | 0.70 | effect | effect-functional |
| `familiar` | 0.65 | social | social |
| `formative` | 0.65 | effect | effect-functional |
| `known` | 0.60 | functional | effect-functional |

### `spite` (synset `30349`) — 11 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `wounding` | 0.90 | effect | effect-functional |
| `interpersonal` | 0.85 | social | social |
| `bruising` | 0.80 | physical | physical-other |
| `lasting` | 0.75 | effect | effect-functional |
| `invisible` | 0.70 | physical | physical-other |
| `rejecting` | 0.70 | emotional | emotional |
| `tender` | 0.70 | emotional | emotional |
| `isolating` | 0.65 | emotional | emotional |
| `unexpected` | 0.65 | behaviour | behaviour |
| `accumulating` | 0.60 | behaviour | behaviour |
| `silencing` | 0.60 | effect | effect-functional |

### `mortality` (synset `60284`) — 11 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `finite` | 0.95 | functional | effect-functional |
| `inevitable` | 0.95 | effect | effect-functional |
| `universal` | 0.85 | social | social |
| `existential` | 0.80 | emotional | emotional |
| `fearful` | 0.75 | emotional | emotional |
| `heavy` | 0.70 | physical | sensorimotor |
| `solemn` | 0.70 | emotional | emotional |
| `humbling` | 0.65 | emotional | emotional |
| `biological` | 0.60 | physical | physical-other |
| `motivating` | 0.50 | effect | effect-functional |
| `sacred` | 0.45 | social | social |

### `eternity` (synset `104424`) — 12 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `interminable` | 1.00 | — | unknown |
| `patience-testing` | 1.00 | — | unknown |
| `dragging` | 0.90 | behaviour | behaviour |
| `frustrating` | 0.85 | emotional | emotional |
| `oppressive` | 0.85 | emotional | emotional |
| `static` | 0.80 | behaviour | behaviour |
| `tedious` | 0.80 | emotional | emotional |
| `distorted` | 0.75 | effect | effect-functional |
| `heavy` | 0.75 | emotional | sensorimotor |
| `anxious` | 0.70 | emotional | emotional |
| `subjective` | 0.65 | functional | effect-functional |
| `isolating` | 0.55 | emotional | emotional |

### `ageing` (synset `28342`) — 12 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `gradual` | 0.90 | behaviour | behaviour |
| `inevitable` | 0.90 | effect | effect-functional |
| `irreversible` | 0.85 | effect | effect-functional |
| `biological` | 0.80 | physical | physical-other |
| `cumulative` | 0.80 | behaviour | behaviour |
| `universal` | 0.80 | social | social |
| `slow` | 0.75 | behaviour | sensorimotor |
| `visible` | 0.75 | physical | physical-other |
| `weakening` | 0.70 | effect | effect-functional |
| `transformative` | 0.65 | effect | effect-functional |
| `melancholic` | 0.55 | emotional | emotional |
| `dignified` | 0.40 | emotional | emotional |

### `transience` (synset `60269`) — 11 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `impermanent` | 1.00 | — | unknown |
| `transient` | 0.95 | behaviour | behaviour |
| `ephemeral` | 0.90 | effect | effect-functional |
| `fleeting` | 0.90 | behaviour | behaviour |
| `momentary` | 0.85 | behaviour | behaviour |
| `swift` | 0.80 | behaviour | sensorimotor |
| `precious` | 0.70 | emotional | emotional |
| `wistful` | 0.65 | emotional | emotional |
| `elusive` | 0.60 | behaviour | behaviour |
| `concentrated` | 0.55 | physical | physical-other |
| `memorable` | 0.50 | emotional | emotional |

### `decay` (synset `94423`) — 10 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `gradual` | 0.90 | behaviour | behaviour |
| `directional` | 0.85 | behaviour | behaviour |
| `measurable` | 0.85 | physical | physical-other |
| `continuous` | 0.80 | behaviour | behaviour |
| `invisible` | 0.75 | physical | physical-other |
| `exponential` | 0.65 | behaviour | behaviour |
| `inevitable` | 0.60 | effect | effect-functional |
| `silent` | 0.55 | physical | sensorimotor |
| `precise` | 0.50 | functional | effect-functional |
| `technical` | 0.40 | social | social |

### `maturity` (synset `103787`) — 9 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `responsible` | 0.85 | social | social |
| `independent` | 0.80 | behaviour | behaviour |
| `stable` | 0.65 | emotional | emotional |
| `burdensome` | 0.60 | emotional | emotional |
| `purposeful` | 0.55 | behaviour | behaviour |
| `prolonged` | 0.50 | physical | physical-other |
| `transitional` | 0.50 | behaviour | behaviour |
| `irreversible` | 0.45 | effect | effect-functional |
| `reflective` | 0.40 | emotional | emotional |

### `infancy` (synset `103733`) — 10 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `nascent` | 0.90 | behaviour | behaviour |
| `fragile` | 0.85 | physical | physical-other |
| `undeveloped` | 0.85 | physical | physical-other |
| `formative` | 0.80 | effect | effect-functional |
| `vulnerable` | 0.80 | effect | effect-functional |
| `dependent` | 0.75 | social | social |
| `promising` | 0.70 | emotional | emotional |
| `rapid` | 0.70 | behaviour | sensorimotor |
| `experimental` | 0.65 | behaviour | behaviour |
| `uncertain` | 0.60 | emotional | emotional |

### `brevity` (synset `60269`) — 11 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `impermanent` | 1.00 | — | unknown |
| `transient` | 0.95 | behaviour | behaviour |
| `ephemeral` | 0.90 | effect | effect-functional |
| `fleeting` | 0.90 | behaviour | behaviour |
| `momentary` | 0.85 | behaviour | behaviour |
| `swift` | 0.80 | behaviour | sensorimotor |
| `precious` | 0.70 | emotional | emotional |
| `wistful` | 0.65 | emotional | emotional |
| `elusive` | 0.60 | behaviour | behaviour |
| `concentrated` | 0.55 | physical | physical-other |
| `memorable` | 0.50 | emotional | emotional |

### `legacy` (synset `93322`) — 11 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `estate-based` | 1.00 | — | unknown |
| `posthumous` | 0.95 | social | social |
| `legal` | 0.90 | functional | effect-functional |
| `intentional` | 0.85 | behaviour | behaviour |
| `transferable` | 0.85 | functional | effect-functional |
| `binding` | 0.80 | functional | effect-functional |
| `documented` | 0.80 | functional | effect-functional |
| `final` | 0.80 | emotional | emotional |
| `personal` | 0.75 | social | social |
| `meaningful` | 0.70 | emotional | emotional |
| `generous` | 0.65 | emotional | emotional |

### `rebirth` (synset `1892`) — 12 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `spiritual` | 0.95 | social | social |
| `transformative` | 0.95 | effect | effect-functional |
| `profound` | 0.90 | emotional | emotional |
| `renewing` | 0.85 | effect | effect-functional |
| `emotional` | 0.80 | emotional | emotional |
| `enlightening` | 0.80 | emotional | emotional |
| `irreversible` | 0.75 | effect | effect-functional |
| `purposeful` | 0.70 | functional | effect-functional |
| `sudden` | 0.70 | behaviour | behaviour |
| `cathartic` | 0.65 | emotional | emotional |
| `communal` | 0.60 | social | social |
| `testimonial` | 0.60 | social | social |

### `patience` (synset `11026`) — 9 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `solitary` | 0.95 | social | social |
| `repetitive` | 0.80 | behaviour | behaviour |
| `sequential` | 0.80 | behaviour | behaviour |
| `meditative` | 0.75 | emotional | emotional |
| `random` | 0.70 | behaviour | behaviour |
| `absorbing` | 0.65 | emotional | emotional |
| `tactile` | 0.60 | physical | physical-other |
| `traditional` | 0.50 | social | social |
| `portable` | 0.45 | functional | effect-functional |

### `urgency` (synset `60876`) — 9 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `immediate` | 0.95 | behaviour | behaviour |
| `pressing` | 0.90 | functional | effect-functional |
| `critical` | 0.85 | effect | effect-functional |
| `demanding` | 0.80 | functional | effect-functional |
| `intense` | 0.80 | emotional | emotional |
| `prioritised` | 0.75 | functional | effect-functional |
| `anxious` | 0.70 | emotional | emotional |
| `tense` | 0.70 | emotional | sensorimotor |
| `accelerating` | 0.65 | behaviour | behaviour |

### `impermanence` (synset `60278`) — 11 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `impermanent` | 1.00 | — | unknown |
| `fleeting` | 0.90 | behaviour | behaviour |
| `temporary` | 0.90 | functional | effect-functional |
| `transient` | 0.85 | behaviour | behaviour |
| `fragile` | 0.80 | physical | physical-other |
| `melancholic` | 0.65 | emotional | emotional |
| `poignant` | 0.65 | emotional | emotional |
| `delicate` | 0.60 | physical | physical-other |
| `beautiful` | 0.50 | emotional | emotional |
| `philosophical` | 0.45 | social | social |
| `liberating` | 0.40 | emotional | emotional |

### `decline` (synset `15918`) — 10 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `firm` | 0.90 | behaviour | behaviour |
| `definitive` | 0.85 | functional | effect-functional |
| `deliberate` | 0.85 | behaviour | behaviour |
| `distancing` | 0.80 | social | social |
| `assertive` | 0.75 | behaviour | behaviour |
| `final` | 0.75 | effect | effect-functional |
| `polite` | 0.75 | social | social |
| `verbal` | 0.65 | behaviour | behaviour |
| `principled` | 0.60 | emotional | emotional |
| `uncomfortable` | 0.55 | emotional | emotional |

### `epoch` (synset `104301`) — 11 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `ancient` | 0.85 | physical | physical-other |
| `vast` | 0.85 | physical | sensorimotor |
| `deep` | 0.80 | physical | physical-other |
| `measured` | 0.80 | functional | effect-functional |
| `scientific` | 0.80 | social | social |
| `layered` | 0.75 | physical | physical-other |
| `systematic` | 0.75 | functional | effect-functional |
| `sequential` | 0.70 | behaviour | behaviour |
| `subdivided` | 0.70 | functional | effect-functional |
| `formative` | 0.60 | effect | effect-functional |
| `immovable` | 0.55 | behaviour | behaviour |

### `routine` (synset `69275`) — 10 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `entertaining` | 0.90 | functional | effect-functional |
| `brief` | 0.85 | behaviour | behaviour |
| `rehearsed` | 0.80 | behaviour | behaviour |
| `energetic` | 0.75 | behaviour | behaviour |
| `showbiz` | 0.75 | social | social |
| `memorable` | 0.70 | effect | effect-functional |
| `structured` | 0.70 | functional | effect-functional |
| `climactic` | 0.65 | emotional | emotional |
| `varied` | 0.60 | functional | effect-functional |
| `rhythmic` | 0.55 | behaviour | sensorimotor |

### `procrastination` (synset `20038`) — 12 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `dilatory` | 1.00 | — | unknown |
| `postponing` | 1.00 | — | unknown |
| `procrastinating` | 1.00 | — | unknown |
| `delaying` | 0.95 | behaviour | behaviour |
| `avoidant` | 0.85 | behaviour | behaviour |
| `passive` | 0.75 | behaviour | behaviour |
| `habitual` | 0.70 | behaviour | behaviour |
| `anxious` | 0.65 | emotional | emotional |
| `stressful` | 0.65 | emotional | emotional |
| `indecisive` | 0.60 | behaviour | behaviour |
| `rationalising` | 0.55 | behaviour | behaviour |
| `cyclical` | 0.50 | behaviour | behaviour |

### `haste` (synset `99918`) — 19 properties, 2 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `anxious` | 1.00 | — | unknown |
| `compelled` | 1.00 | — | unknown |
| `constrained` | 1.00 | — | unknown |
| `demanding` | 1.00 | — | unknown |
| `driven` | 1.00 | — | unknown |
| `immediate` | 1.00 | — | unknown |
| `necessary` | 1.00 | — | unknown |
| `pressured` | 1.00 | — | unknown |
| `stressful` | 1.00 | — | unknown |
| `tense` | 1.00 | — | sensorimotor |
| `time-critical` | 1.00 | — | unknown |
| `urgent` | 1.00 | — | unknown |
| `rushed` | 0.92 | behaviour | behaviour |
| `rapid` | 0.88 | behaviour | sensorimotor |
| `frantic` | 0.78 | emotional | emotional |
| `breathless` | 0.65 | physical | physical-other |
| `chaotic` | 0.58 | effect | effect-functional |
| `transient` | 0.55 | behaviour | behaviour |
| `purposeful` | 0.50 | functional | effect-functional |

### `endurance` (synset `97278`) — 20 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `persistent` | 0.90 | behaviour | behaviour |
| `enduring` | 0.85 | behaviour | behaviour |
| `resilient` | 0.85 | behaviour | behaviour |
| `tenacious` | 0.85 | behaviour | behaviour |
| `urgent` | 0.85 | behaviour | behaviour |
| `instinctive` | 0.80 | behaviour | behaviour |
| `primal` | 0.80 | emotional | emotional |
| `adaptive` | 0.75 | behaviour | behaviour |
| `exhausting` | 0.75 | emotional | emotional |
| `raw` | 0.75 | physical | physical-other |
| `scarred` | 0.75 | physical | physical-other |
| `precarious` | 0.70 | physical | physical-other |
| `stripped` | 0.70 | physical | physical-other |
| `hardening` | 0.65 | effect | effect-functional |
| `minimal` | 0.65 | physical | physical-other |
| `uncertain` | 0.65 | emotional | emotional |
| `hardened` | 0.60 | effect | effect-functional |
| `purposeful` | 0.55 | functional | effect-functional |
| `solitary` | 0.55 | social | social |
| `triumphant` | 0.50 | emotional | emotional |

### `obsolescence` (synset `94755`) — 10 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `declining` | 0.85 | behaviour | behaviour |
| `irreversible` | 0.80 | effect | effect-functional |
| `superseded` | 0.80 | effect | effect-functional |
| `gradual` | 0.75 | behaviour | behaviour |
| `inevitable` | 0.70 | effect | effect-functional |
| `neglected` | 0.65 | effect | effect-functional |
| `technological` | 0.60 | social | social |
| `cumulative` | 0.55 | behaviour | behaviour |
| `melancholic` | 0.55 | emotional | emotional |
| `quiet` | 0.45 | behaviour | sensorimotor |

### `permanence` (synset `60270`) — 11 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `enduring` | 0.95 | behaviour | behaviour |
| `stable` | 0.90 | physical | physical-other |
| `unchanging` | 0.85 | behaviour | behaviour |
| `immovable` | 0.80 | physical | physical-other |
| `reliable` | 0.80 | functional | effect-functional |
| `solid` | 0.80 | physical | physical-other |
| `reassuring` | 0.75 | emotional | emotional |
| `timeless` | 0.75 | behaviour | behaviour |
| `immutable` | 0.70 | behaviour | behaviour |
| `indestructible` | 0.65 | effect | effect-functional |
| `monumental` | 0.55 | social | social |

### `stagnation` (synset `97537`) — 9 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `static` | 0.92 | behaviour | behaviour |
| `dormant` | 0.90 | behaviour | behaviour |
| `unproductive` | 0.88 | functional | effect-functional |
| `stifling` | 0.82 | effect | effect-functional |
| `decline` | 0.78 | effect | effect-functional |
| `frustrating` | 0.75 | emotional | emotional |
| `depressing` | 0.72 | emotional | emotional |
| `moribund` | 0.65 | functional | effect-functional |
| `grey` | 0.55 | emotional | sensorimotor |

### `senescence` (synset `94280`) — 12 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `changing` | 1.00 | — | unknown |
| `gradual` | 0.90 | behaviour | behaviour |
| `inevitable` | 0.90 | effect | effect-functional |
| `natural` | 0.85 | physical | physical-other |
| `universal` | 0.85 | social | social |
| `cumulative` | 0.80 | behaviour | behaviour |
| `visible` | 0.80 | physical | physical-other |
| `irreversible` | 0.75 | effect | effect-functional |
| `progressive` | 0.75 | behaviour | behaviour |
| `transformative` | 0.65 | effect | effect-functional |
| `cellular` | 0.60 | physical | physical-other |
| `melancholic` | 0.55 | emotional | emotional |

### `resurrection` (synset `19714`) — 14 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `reawakening` | 1.00 | — | unknown |
| `reborn` | 1.00 | — | unknown |
| `rekindling` | 1.00 | — | unknown |
| `renewed` | 0.90 | effect | effect-functional |
| `revived` | 0.90 | effect | effect-functional |
| `restorative` | 0.80 | functional | effect-functional |
| `hopeful` | 0.75 | emotional | emotional |
| `energising` | 0.70 | effect | effect-functional |
| `emergent` | 0.65 | behaviour | behaviour |
| `transformative` | 0.65 | effect | effect-functional |
| `cyclical` | 0.60 | behaviour | behaviour |
| `symbolic` | 0.60 | social | social |
| `surprising` | 0.55 | emotional | emotional |
| `dynamic` | 0.50 | behaviour | behaviour |

### `ephemera` (synset `104298`) — 12 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `impermanent` | 1.00 | — | unknown |
| `fleeting` | 0.95 | behaviour | behaviour |
| `transient` | 0.90 | behaviour | behaviour |
| `momentary` | 0.85 | behaviour | behaviour |
| `delicate` | 0.80 | physical | physical-other |
| `fragile` | 0.80 | physical | physical-other |
| `precious` | 0.75 | emotional | emotional |
| `bittersweet` | 0.70 | emotional | emotional |
| `poignant` | 0.70 | emotional | emotional |
| `nostalgic` | 0.65 | emotional | emotional |
| `light` | 0.60 | physical | sensorimotor |
| `overlooked` | 0.55 | social | social |

### `heritage` (synset `1649`) — 13 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `birthright` | 1.00 | — | unknown |
| `hereditary` | 0.92 | social | social |
| `generational` | 0.88 | social | social |
| `legal` | 0.85 | social | social |
| `transferable` | 0.85 | functional | effect-functional |
| `entitling` | 0.80 | functional | effect-functional |
| `formal` | 0.78 | social | social |
| `prestigious` | 0.72 | social | social |
| `inevitable` | 0.62 | behaviour | behaviour |
| `ancient` | 0.55 | social | social |
| `patrilineal` | 0.55 | social | social |
| `burdensome` | 0.45 | emotional | emotional |
| `contested` | 0.40 | effect | effect-functional |

### `deadline` (synset `103919`) — 12 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `unforgiving` | 1.00 | — | unknown |
| `fixed` | 0.95 | physical | physical-other |
| `urgent` | 0.90 | emotional | emotional |
| `finite` | 0.85 | functional | effect-functional |
| `stressful` | 0.85 | emotional | emotional |
| `binding` | 0.80 | social | social |
| `looming` | 0.80 | behaviour | behaviour |
| `pressurising` | 0.80 | effect | effect-functional |
| `consequential` | 0.75 | effect | effect-functional |
| `motivating` | 0.70 | effect | effect-functional |
| `imposed` | 0.65 | social | social |
| `clarifying` | 0.50 | functional | effect-functional |

### `momentum` (synset `60184`) — 10 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `forceful` | 0.90 | physical | physical-other |
| `cumulative` | 0.85 | behaviour | behaviour |
| `propulsive` | 0.85 | functional | effect-functional |
| `directional` | 0.80 | behaviour | behaviour |
| `kinetic` | 0.75 | physical | physical-other |
| `unstoppable` | 0.75 | effect | effect-functional |
| `inertial` | 0.70 | physical | physical-other |
| `accelerating` | 0.65 | behaviour | behaviour |
| `energising` | 0.60 | emotional | emotional |
| `transferable` | 0.50 | effect | effect-functional |

### `perpetuity` (synset `60271`) — 11 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `endless` | 0.95 | behaviour | behaviour |
| `timeless` | 0.90 | effect | effect-functional |
| `boundless` | 0.85 | physical | physical-other |
| `unchanging` | 0.80 | behaviour | behaviour |
| `immutable` | 0.75 | functional | effect-functional |
| `abstract` | 0.70 | physical | physical-other |
| `inevitable` | 0.65 | effect | effect-functional |
| `reassuring` | 0.55 | emotional | emotional |
| `overwhelming` | 0.50 | emotional | emotional |
| `oppressive` | 0.45 | emotional | emotional |
| `sacred` | 0.40 | social | social |

### `confusion` (synset `8384`) — 9 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `blending` | 0.85 | behaviour | behaviour |
| `chaotic` | 0.80 | behaviour | behaviour |
| `misleading` | 0.75 | effect | effect-functional |
| `obscuring` | 0.75 | effect | effect-functional |
| `tangled` | 0.70 | physical | physical-other |
| `disorienting` | 0.65 | emotional | emotional |
| `irreversible` | 0.60 | effect | effect-functional |
| `damaging` | 0.55 | effect | effect-functional |
| `unintentional` | 0.50 | behaviour | behaviour |

### `understanding` (synset `68633`) — 18 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `promise-based` | 1.00 | — | unknown |
| `mutual` | 0.95 | behaviour | behaviour |
| `binding` | 0.90 | functional | effect-functional |
| `reciprocal` | 0.85 | behaviour | behaviour |
| `collaborative` | 0.80 | social | social |
| `negotiated` | 0.75 | behaviour | behaviour |
| `obligatory` | 0.70 | functional | effect-functional |
| `stabilising` | 0.70 | effect | effect-functional |
| `clarifying` | 0.65 | effect | effect-functional |
| `formal` | 0.65 | social | social |
| `transactional` | 0.65 | social | social |
| `enforceable` | 0.60 | functional | effect-functional |
| `relational` | 0.60 | social | social |
| `structured` | 0.60 | physical | physical-other |
| `social` | 0.55 | social | social |
| `stable` | 0.55 | effect | effect-functional |
| `documented` | 0.50 | functional | effect-functional |
| `provisional` | 0.40 | behaviour | behaviour |

### `curiosity` (synset `63499`) — 12 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `unsatisfied` | 1.00 | — | unknown |
| `wondering` | 1.00 | — | unknown |
| `eager` | 0.90 | behaviour | behaviour |
| `exploratory` | 0.85 | behaviour | behaviour |
| `open` | 0.85 | behaviour | behaviour |
| `questioning` | 0.80 | behaviour | behaviour |
| `hungry` | 0.75 | physical | physical-other |
| `restless` | 0.75 | behaviour | behaviour |
| `energising` | 0.70 | effect | effect-functional |
| `pleasurable` | 0.65 | emotional | emotional |
| `bright` | 0.60 | physical | sensorimotor |
| `valued` | 0.50 | social | social |

### `delusion` (synset `64555`) — 15 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `baseless` | 1.00 | — | unknown |
| `misconceived` | 1.00 | — | unknown |
| `unfounded` | 1.00 | — | unknown |
| `wrong` | 1.00 | — | unknown |
| `false` | 0.95 | functional | effect-functional |
| `irrational` | 0.85 | functional | effect-functional |
| `distorting` | 0.80 | effect | effect-functional |
| `persistent` | 0.80 | behaviour | behaviour |
| `convincing` | 0.75 | emotional | emotional |
| `deceptive` | 0.75 | effect | effect-functional |
| `rigid` | 0.70 | behaviour | sensorimotor |
| `entrenched` | 0.65 | behaviour | behaviour |
| `harmful` | 0.65 | effect | effect-functional |
| `invisible` | 0.60 | physical | physical-other |
| `isolating` | 0.60 | social | social |

### `insight` (synset `63638`) — 11 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `clear` | 0.90 | functional | effect-functional |
| `deep` | 0.85 | functional | effect-functional |
| `sharp` | 0.80 | functional | sensorimotor |
| `accurate` | 0.75 | functional | effect-functional |
| `revealing` | 0.75 | effect | effect-functional |
| `analytical` | 0.70 | behaviour | behaviour |
| `illuminating` | 0.70 | effect | effect-functional |
| `sudden` | 0.60 | behaviour | behaviour |
| `concise` | 0.55 | functional | effect-functional |
| `rare` | 0.55 | social | social |
| `actionable` | 0.50 | functional | effect-functional |

### `reason` (synset `68488`) — 19 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `justifying` | 0.95 | functional | effect-functional |
| `motivating` | 0.85 | functional | effect-functional |
| `purposive` | 0.80 | behaviour | behaviour |
| `validating` | 0.80 | effect | effect-functional |
| `necessary` | 0.75 | functional | effect-functional |
| `persuasive` | 0.75 | effect | effect-functional |
| `enabling` | 0.70 | effect | effect-functional |
| `logical` | 0.70 | behaviour | behaviour |
| `abstract` | 0.65 | physical | physical-other |
| `contested` | 0.65 | social | social |
| `grounding` | 0.65 | emotional | emotional |
| `authoritative` | 0.60 | social | social |
| `ethical` | 0.60 | social | social |
| `moral` | 0.60 | social | social |
| `scrutinised` | 0.60 | behaviour | behaviour |
| `defensive` | 0.55 | functional | effect-functional |
| `retrospective` | 0.55 | behaviour | behaviour |
| `social` | 0.55 | social | social |
| `contextual` | 0.50 | functional | effect-functional |

### `intuition` (synset `64658`) — 13 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `pre-cognitive` | 1.00 | — | unknown |
| `instinctive` | 0.85 | behaviour | behaviour |
| `tentative` | 0.85 | functional | effect-functional |
| `unproven` | 0.85 | functional | effect-functional |
| `alerting` | 0.75 | effect | effect-functional |
| `nagging` | 0.75 | behaviour | behaviour |
| `anticipatory` | 0.70 | functional | effect-functional |
| `uneasy` | 0.70 | emotional | emotional |
| `private` | 0.65 | social | social |
| `visceral` | 0.65 | physical | physical-other |
| `cautionary` | 0.60 | effect | effect-functional |
| `swift` | 0.60 | behaviour | sensorimotor |
| `fallible` | 0.55 | functional | effect-functional |

### `obsession` (synset `78921`) — 11 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `repetitive` | 0.95 | behaviour | behaviour |
| `intrusive` | 0.90 | behaviour | behaviour |
| `involuntary` | 0.90 | behaviour | behaviour |
| `distressing` | 0.85 | emotional | emotional |
| `irrational` | 0.85 | behaviour | behaviour |
| `persistent` | 0.85 | behaviour | behaviour |
| `anxious` | 0.80 | emotional | emotional |
| `consuming` | 0.75 | effect | effect-functional |
| `trivial` | 0.75 | functional | effect-functional |
| `ritualistic` | 0.70 | behaviour | behaviour |
| `shameful` | 0.60 | social | social |

### `clarity` (synset `58486`) — 13 properties, 3 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `limpid` | 1.00 | — | unknown |
| `transparent` | 0.95 | physical | physical-other |
| `colourless` | 0.90 | physical | physical-other |
| `pure` | 0.85 | physical | physical-other |
| `clean` | 0.80 | functional | effect-functional |
| `pristine` | 0.70 | emotional | emotional |
| `reflective` | 0.70 | physical | physical-other |
| `luminous` | 0.65 | physical | sensorimotor |
| `refreshing` | 0.65 | emotional | emotional |
| `cool` | 0.60 | physical | sensorimotor |
| `still` | 0.60 | physical | sensorimotor |
| `readable` | 0.55 | functional | effect-functional |
| `deep` | 0.50 | physical | physical-other |

### `doubt` (synset `14297`) — 13 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `disbelieving` | 1.00 | — | unknown |
| `unconvinced` | 1.00 | — | unknown |
| `sceptical` | 0.92 | emotional | emotional |
| `questioning` | 0.85 | behaviour | behaviour |
| `withholding` | 0.80 | behaviour | behaviour |
| `cautious` | 0.75 | emotional | emotional |
| `resistant` | 0.70 | emotional | emotional |
| `unresolved` | 0.70 | effect | effect-functional |
| `distancing` | 0.65 | behaviour | behaviour |
| `analytical` | 0.60 | functional | effect-functional |
| `protective` | 0.55 | functional | effect-functional |
| `internal` | 0.50 | physical | physical-other |
| `deflating` | 0.40 | effect | effect-functional |

### `concentration` (synset `8272`) — 11 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `reductive` | 0.90 | behaviour | behaviour |
| `chemical` | 0.85 | functional | effect-functional |
| `intensifying` | 0.85 | effect | effect-functional |
| `controlled` | 0.80 | behaviour | behaviour |
| `technical` | 0.80 | social | social |
| `measurable` | 0.75 | functional | effect-functional |
| `precise` | 0.75 | functional | effect-functional |
| `purifying` | 0.75 | effect | effect-functional |
| `deliberate` | 0.70 | behaviour | behaviour |
| `gradual` | 0.70 | behaviour | behaviour |
| `transformative` | 0.65 | effect | effect-functional |

### `perception` (synset `63629`) — 12 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `attentional` | 1.00 | — | unknown |
| `sensory` | 0.90 | physical | physical-other |
| `active` | 0.80 | behaviour | behaviour |
| `immediate` | 0.80 | behaviour | behaviour |
| `automatic` | 0.75 | behaviour | behaviour |
| `continuous` | 0.75 | behaviour | behaviour |
| `selective` | 0.70 | behaviour | behaviour |
| `interpretive` | 0.65 | functional | effect-functional |
| `constructive` | 0.60 | functional | effect-functional |
| `neural` | 0.60 | physical | physical-other |
| `embodied` | 0.55 | physical | physical-other |
| `fallible` | 0.50 | effect | effect-functional |

### `epiphany` (synset `104004`) — 9 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `religious` | 0.90 | social | social |
| `ceremonial` | 0.75 | social | social |
| `festive` | 0.75 | emotional | emotional |
| `symbolic` | 0.70 | social | social |
| `closing` | 0.65 | effect | effect-functional |
| `wintry` | 0.65 | physical | physical-other |
| `communal` | 0.60 | social | social |
| `joyful` | 0.60 | emotional | emotional |
| `ancient` | 0.55 | social | social |

### `prejudice` (synset `14179`) — 14 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `biasing` | 1.00 | — | unknown |
| `manipulating` | 1.00 | — | unknown |
| `preconditioning` | 1.00 | — | unknown |
| `predisposing` | 1.00 | — | unknown |
| `biased` | 0.90 | effect | effect-functional |
| `manipulative` | 0.90 | behaviour | behaviour |
| `preemptive` | 0.85 | behaviour | behaviour |
| `distorting` | 0.80 | effect | effect-functional |
| `influential` | 0.80 | effect | effect-functional |
| `intentional` | 0.75 | behaviour | behaviour |
| `covert` | 0.70 | behaviour | behaviour |
| `persuasive` | 0.70 | behaviour | behaviour |
| `unethical` | 0.70 | social | social |
| `corrosive` | 0.65 | effect | effect-functional |

### `logic` (synset `65673`) — 12 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `precise` | 0.90 | behaviour | behaviour |
| `rigorous` | 0.90 | behaviour | behaviour |
| `systematic` | 0.90 | behaviour | behaviour |
| `abstract` | 0.85 | functional | effect-functional |
| `analytical` | 0.85 | behaviour | behaviour |
| `deductive` | 0.85 | functional | effect-functional |
| `formal` | 0.80 | functional | effect-functional |
| `foundational` | 0.80 | functional | effect-functional |
| `objective` | 0.80 | functional | effect-functional |
| `influential` | 0.70 | effect | effect-functional |
| `universal` | 0.70 | effect | effect-functional |
| `ancient` | 0.60 | social | social |

### `stupidity` (synset `63306`) — 10 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `oblivious` | 0.90 | behaviour | behaviour |
| `repetitive` | 0.85 | behaviour | behaviour |
| `frustrating` | 0.80 | emotional | emotional |
| `blinkered` | 0.75 | behaviour | behaviour |
| `derided` | 0.75 | social | social |
| `costly` | 0.70 | effect | effect-functional |
| `persistent` | 0.65 | behaviour | behaviour |
| `unteachable` | 0.65 | functional | effect-functional |
| `contemptible` | 0.60 | social | social |
| `impulsive` | 0.55 | behaviour | behaviour |

### `genius` (synset `63158`) — 17 properties, 3 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `extraordinary` | 0.95 | physical | physical-other |
| `rare` | 0.90 | social | social |
| `dazzling` | 0.80 | effect | effect-functional |
| `swift` | 0.80 | behaviour | sensorimotor |
| `luminous` | 0.75 | emotional | sensorimotor |
| `analytical` | 0.70 | functional | effect-functional |
| `intuitive` | 0.70 | behaviour | behaviour |
| `rapid` | 0.70 | behaviour | sensorimotor |
| `penetrating` | 0.65 | physical | physical-other |
| `transformative` | 0.65 | effect | effect-functional |
| `effortless` | 0.60 | behaviour | behaviour |
| `inborn` | 0.60 | physical | physical-other |
| `productive` | 0.60 | functional | effect-functional |
| `celebrated` | 0.55 | social | social |
| `intimidating` | 0.55 | emotional | emotional |
| `precocious` | 0.55 | behaviour | behaviour |
| `isolating` | 0.45 | social | social |

### `abstraction` (synset `64357`) — 11 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `non-physical` | 1.00 | — | unknown |
| `conceptual` | 0.95 | physical | physical-other |
| `intangible` | 0.95 | physical | physical-other |
| `generalised` | 0.90 | functional | effect-functional |
| `universal` | 0.85 | functional | effect-functional |
| `disembodied` | 0.80 | physical | physical-other |
| `elusive` | 0.75 | emotional | emotional |
| `structural` | 0.70 | functional | effect-functional |
| `foundational` | 0.60 | social | social |
| `debatable` | 0.55 | social | social |
| `precise` | 0.50 | behaviour | behaviour |

### `focus` (synset `99833`) — 20 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `spotlit` | 1.00 | — | unknown |
| `prominent` | 0.92 | physical | physical-other |
| `deliberate` | 0.88 | behaviour | behaviour |
| `intentional` | 0.85 | behaviour | behaviour |
| `weighted` | 0.85 | physical | physical-other |
| `selective` | 0.82 | functional | effect-functional |
| `focused` | 0.80 | functional | effect-functional |
| `communicative` | 0.78 | functional | effect-functional |
| `foregrounded` | 0.75 | effect | effect-functional |
| `rhetorical` | 0.75 | functional | effect-functional |
| `clarifying` | 0.70 | effect | effect-functional |
| `directive` | 0.70 | functional | effect-functional |
| `hierarchical` | 0.70 | effect | effect-functional |
| `purposeful` | 0.70 | functional | effect-functional |
| `contrastive` | 0.65 | effect | effect-functional |
| `memorable` | 0.65 | effect | effect-functional |
| `persuasive` | 0.65 | functional | effect-functional |
| `rhythmic` | 0.55 | behaviour | sensorimotor |
| `brief` | 0.50 | behaviour | behaviour |
| `tonal` | 0.45 | physical | physical-other |

### `revelation` (synset `64122`) — 13 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `eye-opening` | 1.00 | — | unknown |
| `shocking` | 0.90 | emotional | emotional |
| `sudden` | 0.85 | behaviour | behaviour |
| `exposing` | 0.80 | functional | effect-functional |
| `momentous` | 0.80 | emotional | emotional |
| `transformative` | 0.80 | effect | effect-functional |
| `dramatic` | 0.75 | behaviour | behaviour |
| `irreversible` | 0.75 | effect | effect-functional |
| `clarifying` | 0.70 | effect | effect-functional |
| `public` | 0.70 | social | social |
| `destabilising` | 0.65 | effect | effect-functional |
| `disorienting` | 0.60 | emotional | emotional |
| `sacred` | 0.45 | social | social |

### `forgetfulness` (synset `63450`) — 11 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `lapsing` | 1.00 | — | unknown |
| `unreliable` | 0.95 | behaviour | behaviour |
| `habitual` | 0.85 | behaviour | behaviour |
| `absentminded` | 0.80 | behaviour | behaviour |
| `frustrating` | 0.80 | emotional | emotional |
| `disorganised` | 0.70 | behaviour | behaviour |
| `intermittent` | 0.70 | behaviour | behaviour |
| `embarrassing` | 0.65 | social | social |
| `accumulating` | 0.60 | behaviour | behaviour |
| `benign` | 0.50 | effect | effect-functional |
| `compensated` | 0.50 | functional | effect-functional |

### `learning` (synset `63852`) — 12 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `effortful` | 0.85 | behaviour | behaviour |
| `gradual` | 0.85 | behaviour | behaviour |
| `cumulative` | 0.80 | behaviour | behaviour |
| `progressive` | 0.75 | behaviour | behaviour |
| `transformative` | 0.75 | effect | effect-functional |
| `active` | 0.70 | behaviour | behaviour |
| `neurological` | 0.70 | physical | physical-other |
| `repetitive` | 0.70 | behaviour | behaviour |
| `purposeful` | 0.65 | functional | effect-functional |
| `rewarding` | 0.65 | emotional | emotional |
| `errorful` | 0.60 | behaviour | behaviour |
| `social` | 0.55 | social | social |

### `belief` (synset `64647`) — 12 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `uncertain` | 0.85 | functional | effect-functional |
| `intuitive` | 0.80 | behaviour | behaviour |
| `unverified` | 0.80 | functional | effect-functional |
| `personal` | 0.75 | social | social |
| `diffuse` | 0.70 | physical | physical-other |
| `subtle` | 0.70 | physical | physical-other |
| `partial` | 0.65 | functional | effect-functional |
| `compelling` | 0.60 | emotional | emotional |
| `fleeting` | 0.60 | behaviour | behaviour |
| `influential` | 0.60 | effect | effect-functional |
| `guiding` | 0.55 | functional | effect-functional |
| `honest` | 0.55 | social | social |

### `rumination` (synset `2428`) — 9 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `postprandial` | 1.00 | — | unknown |
| `reflux` | 1.00 | — | unknown |
| `regurgitative` | 0.95 | behaviour | behaviour |
| `digestive` | 0.90 | physical | physical-other |
| `involuntary` | 0.85 | behaviour | behaviour |
| `physiological` | 0.75 | physical | physical-other |
| `passive` | 0.70 | behaviour | behaviour |
| `effortless` | 0.65 | behaviour | behaviour |
| `benign` | 0.60 | effect | effect-functional |

### `creativity` (synset `63185`) — 12 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `generative` | 0.90 | functional | effect-functional |
| `original` | 0.85 | behaviour | behaviour |
| `imaginative` | 0.80 | behaviour | behaviour |
| `expressive` | 0.70 | functional | effect-functional |
| `fluid` | 0.70 | behaviour | behaviour |
| `inspiring` | 0.70 | emotional | emotional |
| `playful` | 0.65 | emotional | emotional |
| `transformative` | 0.65 | effect | effect-functional |
| `unpredictable` | 0.60 | behaviour | behaviour |
| `valued` | 0.60 | social | social |
| `energetic` | 0.55 | physical | physical-other |
| `cultivable` | 0.45 | functional | effect-functional |

### `madness` (synset `59383`) — 11 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `frenzied` | 0.92 | behaviour | behaviour |
| `energetic` | 0.88 | behaviour | behaviour |
| `loud` | 0.85 | physical | sensorimotor |
| `chaotic` | 0.82 | behaviour | behaviour |
| `contagious` | 0.80 | effect | effect-functional |
| `infectious` | 0.78 | effect | effect-functional |
| `spontaneous` | 0.75 | behaviour | behaviour |
| `joyful` | 0.72 | emotional | emotional |
| `overwhelming` | 0.70 | emotional | emotional |
| `collective` | 0.68 | social | social |
| `transient` | 0.62 | behaviour | behaviour |

### `scepticism` (synset `64968`) — 11 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `agnostic` | 1.00 | — | unknown |
| `questioning` | 0.95 | behaviour | behaviour |
| `doubting` | 0.90 | behaviour | behaviour |
| `critical` | 0.85 | behaviour | behaviour |
| `probing` | 0.75 | behaviour | behaviour |
| `intellectual` | 0.70 | social | social |
| `philosophical` | 0.70 | social | social |
| `cautious` | 0.65 | behaviour | behaviour |
| `rigorous` | 0.60 | behaviour | behaviour |
| `unsettling` | 0.60 | emotional | emotional |
| `liberating` | 0.45 | emotional | emotional |

### `awareness` (synset `63473`) — 12 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `pre-reflective` | 1.00 | — | unknown |
| `primal` | 0.90 | behaviour | behaviour |
| `diffuse` | 0.85 | physical | physical-other |
| `raw` | 0.80 | physical | physical-other |
| `sensory` | 0.75 | physical | physical-other |
| `animal` | 0.70 | social | social |
| `elemental` | 0.65 | functional | effect-functional |
| `fleeting` | 0.65 | behaviour | behaviour |
| `quiet` | 0.60 | behaviour | sensorimotor |
| `fragile` | 0.55 | physical | physical-other |
| `mysterious` | 0.50 | emotional | emotional |
| `continuous` | 0.45 | behaviour | behaviour |

### `deception` (synset `15278`) — 12 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `misleading` | 0.95 | effect | effect-functional |
| `concealing` | 0.90 | behaviour | behaviour |
| `deliberate` | 0.90 | behaviour | behaviour |
| `duplicitous` | 0.85 | social | social |
| `hidden` | 0.85 | behaviour | behaviour |
| `manipulative` | 0.85 | functional | effect-functional |
| `calculated` | 0.80 | behaviour | behaviour |
| `damaging` | 0.80 | effect | effect-functional |
| `corrosive` | 0.70 | effect | effect-functional |
| `shameful` | 0.70 | social | social |
| `crafty` | 0.65 | behaviour | behaviour |
| `performative` | 0.60 | behaviour | behaviour |

### `tyranny` (synset `77868`) — 15 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `despotic` | 1.00 | — | unknown |
| `totalizing` | 1.00 | — | unknown |
| `tyrannical` | 1.00 | — | unknown |
| `absolute` | 0.95 | functional | effect-functional |
| `authoritarian` | 0.90 | social | social |
| `oppressive` | 0.90 | effect | effect-functional |
| `centralised` | 0.85 | functional | effect-functional |
| `unchecked` | 0.85 | behaviour | behaviour |
| `coercive` | 0.80 | effect | effect-functional |
| `fearful` | 0.80 | emotional | emotional |
| `repressive` | 0.80 | effect | effect-functional |
| `brutal` | 0.70 | behaviour | behaviour |
| `totalising` | 0.65 | functional | effect-functional |
| `unstable` | 0.50 | effect | effect-functional |
| `isolating` | 0.45 | social | social |

### `oppression` (synset `9353`) — 12 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `dehumanizing` | 1.00 | — | unknown |
| `tyrannical` | 1.00 | — | unknown |
| `cruel` | 0.95 | behaviour | behaviour |
| `coercive` | 0.90 | behaviour | behaviour |
| `dehumanising` | 0.90 | emotional | emotional |
| `traumatic` | 0.90 | effect | effect-functional |
| `resentment` | 0.85 | emotional | emotional |
| `systematic` | 0.85 | behaviour | behaviour |
| `collective` | 0.80 | social | social |
| `enduring` | 0.80 | behaviour | behaviour |
| `suffocating` | 0.80 | emotional | emotional |
| `resistance` | 0.75 | effect | effect-functional |

### `propaganda` (synset `68133`) — 10 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `biased` | 0.95 | behaviour | behaviour |
| `manipulative` | 0.90 | effect | effect-functional |
| `ideological` | 0.85 | social | social |
| `persuasive` | 0.85 | functional | effect-functional |
| `deceptive` | 0.80 | effect | effect-functional |
| `powerful` | 0.75 | effect | effect-functional |
| `repetitive` | 0.75 | behaviour | behaviour |
| `simplistic` | 0.70 | physical | physical-other |
| `strategic` | 0.70 | functional | effect-functional |
| `distrustful` | 0.65 | emotional | emotional |

### `bureaucracy` (synset `75923`) — 12 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `departmentalized` | 1.00 | — | unknown |
| `process-driven` | 1.00 | — | unknown |
| `administrative` | 0.90 | functional | effect-functional |
| `appointed` | 0.90 | social | social |
| `hierarchical` | 0.85 | social | social |
| `structured` | 0.85 | functional | effect-functional |
| `formal` | 0.80 | social | social |
| `impersonal` | 0.75 | social | social |
| `specialised` | 0.70 | functional | effect-functional |
| `stable` | 0.70 | behaviour | behaviour |
| `powerful` | 0.65 | social | social |
| `distant` | 0.60 | emotional | emotional |

### `rebellion` (synset `21772`) — 11 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `defiant` | 0.95 | behaviour | behaviour |
| `subversive` | 0.85 | effect | effect-functional |
| `autonomous` | 0.80 | functional | effect-functional |
| `determined` | 0.75 | behaviour | behaviour |
| `disruptive` | 0.70 | effect | effect-functional |
| `principled` | 0.70 | social | social |
| `dangerous` | 0.65 | effect | effect-functional |
| `liberating` | 0.65 | emotional | emotional |
| `passionate` | 0.60 | emotional | emotional |
| `youthful` | 0.45 | social | social |
| `isolating` | 0.35 | effect | effect-functional |

### `inequality` (synset `58719`) — 11 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `asymmetric` | 0.95 | physical | physical-other |
| `stratified` | 0.85 | social | social |
| `divisive` | 0.80 | effect | effect-functional |
| `pervasive` | 0.80 | behaviour | behaviour |
| `unjust` | 0.80 | emotional | emotional |
| `entrenched` | 0.75 | behaviour | behaviour |
| `systemic` | 0.70 | social | social |
| `demoralising` | 0.65 | emotional | emotional |
| `measurable` | 0.65 | functional | effect-functional |
| `cumulative` | 0.60 | behaviour | behaviour |
| `invisible` | 0.50 | physical | physical-other |

### `authority` (synset `66900`) — 11 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `definitive` | 0.95 | functional | effect-functional |
| `respected` | 0.85 | social | social |
| `trustworthy` | 0.85 | emotional | emotional |
| `canonical` | 0.80 | social | social |
| `influential` | 0.80 | effect | effect-functional |
| `scholarly` | 0.80 | social | social |
| `cited` | 0.75 | behaviour | behaviour |
| `comprehensive` | 0.75 | physical | physical-other |
| `formal` | 0.70 | social | social |
| `weighty` | 0.65 | physical | physical-other |
| `enduring` | 0.60 | effect | effect-functional |

### `censorship` (synset `16271`) — 13 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `sanitizing` | 1.00 | — | unknown |
| `suppressive` | 0.92 | behaviour | behaviour |
| `controlling` | 0.88 | behaviour | behaviour |
| `restrictive` | 0.85 | effect | effect-functional |
| `protective` | 0.80 | functional | effect-functional |
| `redacting` | 0.78 | behaviour | behaviour |
| `authoritative` | 0.75 | social | social |
| `wartime` | 0.72 | social | social |
| `preventive` | 0.70 | functional | effect-functional |
| `covert` | 0.65 | behaviour | behaviour |
| `deliberate` | 0.65 | behaviour | behaviour |
| `bureaucratic` | 0.60 | social | social |
| `intrusive` | 0.60 | emotional | emotional |

### `diplomacy` (synset `59156`) — 10 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `tactful` | 0.92 | behaviour | behaviour |
| `subtle` | 0.88 | behaviour | behaviour |
| `skilled` | 0.82 | functional | effect-functional |
| `smooth` | 0.80 | behaviour | sensorimotor |
| `measured` | 0.78 | behaviour | behaviour |
| `respectful` | 0.75 | social | social |
| `graceful` | 0.72 | emotional | emotional |
| `restrained` | 0.70 | behaviour | behaviour |
| `persuasive` | 0.65 | functional | effect-functional |
| `adaptive` | 0.60 | behaviour | behaviour |

### `tradition` (synset `63419`) — 11 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `repeated` | 0.95 | behaviour | behaviour |
| `inherited` | 0.90 | functional | effect-functional |
| `communal` | 0.85 | social | social |
| `stable` | 0.80 | behaviour | behaviour |
| `meaningful` | 0.75 | emotional | emotional |
| `binding` | 0.70 | social | social |
| `conservative` | 0.70 | social | social |
| `ceremonial` | 0.65 | social | social |
| `comforting` | 0.65 | emotional | emotional |
| `ancient` | 0.60 | physical | physical-other |
| `codified` | 0.55 | functional | effect-functional |

### `reform` (synset `8503`) — 13 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `rehabilitating` | 1.00 | — | unknown |
| `transformative` | 0.90 | effect | effect-functional |
| `corrective` | 0.85 | functional | effect-functional |
| `moral` | 0.80 | social | social |
| `redemptive` | 0.80 | emotional | emotional |
| `difficult` | 0.75 | effect | effect-functional |
| `gradual` | 0.70 | behaviour | behaviour |
| `guided` | 0.70 | functional | effect-functional |
| `hopeful` | 0.70 | emotional | emotional |
| `lasting` | 0.65 | effect | effect-functional |
| `coercive` | 0.60 | behaviour | behaviour |
| `disciplined` | 0.60 | behaviour | behaviour |
| `resistant` | 0.55 | effect | effect-functional |

### `sovereignty` (synset `99878`) — 11 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `powerful` | 0.88 | functional | effect-functional |
| `absolute` | 0.85 | functional | effect-functional |
| `commanding` | 0.82 | behaviour | behaviour |
| `majestic` | 0.78 | emotional | emotional |
| `hereditary` | 0.75 | social | social |
| `ceremonial` | 0.72 | social | social |
| `temporal` | 0.70 | effect | effect-functional |
| `institutional` | 0.68 | social | social |
| `weighty` | 0.62 | emotional | emotional |
| `historical` | 0.60 | social | social |
| `distant` | 0.55 | social | social |

### `anarchy` (synset `97337`) — 13 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `anarchic` | 1.00 | — | unknown |
| `ungoverned` | 0.95 | functional | effect-functional |
| `chaotic` | 0.90 | behaviour | behaviour |
| `unpredictable` | 0.90 | behaviour | behaviour |
| `dangerous` | 0.85 | effect | effect-functional |
| `unrestrained` | 0.85 | behaviour | behaviour |
| `fearful` | 0.80 | emotional | emotional |
| `violent` | 0.80 | effect | effect-functional |
| `collapsed` | 0.75 | effect | effect-functional |
| `fragmented` | 0.75 | effect | effect-functional |
| `threatening` | 0.75 | emotional | emotional |
| `desperate` | 0.65 | emotional | emotional |
| `loud` | 0.55 | physical | sensorimotor |

### `privilege` (synset `39800`) — 11 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `exclusive` | 0.85 | social | social |
| `empowering` | 0.80 | effect | effect-functional |
| `selective` | 0.80 | social | social |
| `elevating` | 0.75 | effect | effect-functional |
| `valuable` | 0.75 | emotional | emotional |
| `asymmetric` | 0.70 | social | social |
| `differentiating` | 0.70 | social | social |
| `honorific` | 0.65 | social | social |
| `significant` | 0.65 | functional | effect-functional |
| `gratifying` | 0.60 | emotional | emotional |
| `institutional` | 0.60 | social | social |

### `poverty` (synset `100134`) — 12 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `scarce` | 0.95 | physical | physical-other |
| `limiting` | 0.90 | effect | effect-functional |
| `hungry` | 0.85 | physical | physical-other |
| `stressful` | 0.85 | emotional | emotional |
| `cold` | 0.80 | physical | sensorimotor |
| `grinding` | 0.80 | behaviour | behaviour |
| `material` | 0.75 | physical | physical-other |
| `stigmatised` | 0.70 | social | social |
| `inherited` | 0.65 | social | social |
| `undignified` | 0.65 | emotional | emotional |
| `cyclic` | 0.60 | behaviour | behaviour |
| `invisible` | 0.60 | social | social |

### `progress` (synset `33052`) — 11 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `forward` | 0.95 | behaviour | behaviour |
| `directional` | 0.90 | behaviour | behaviour |
| `improving` | 0.85 | effect | effect-functional |
| `purposeful` | 0.80 | behaviour | behaviour |
| `incremental` | 0.75 | behaviour | behaviour |
| `momentum` | 0.70 | behaviour | behaviour |
| `optimistic` | 0.70 | emotional | emotional |
| `effortful` | 0.65 | behaviour | behaviour |
| `accumulating` | 0.60 | effect | effect-functional |
| `measurable` | 0.60 | functional | effect-functional |
| `inevitable` | 0.55 | emotional | emotional |

### `ideology` (synset `63979`) — 14 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `impractical` | 1.00 | — | unknown |
| `unrealistic` | 1.00 | — | unknown |
| `utopian` | 1.00 | — | unknown |
| `abstract` | 0.90 | physical | physical-other |
| `visionary` | 0.85 | emotional | emotional |
| `speculative` | 0.80 | behaviour | behaviour |
| `imaginative` | 0.75 | behaviour | behaviour |
| `detached` | 0.70 | behaviour | behaviour |
| `unrealised` | 0.70 | effect | effect-functional |
| `persuasive` | 0.65 | functional | effect-functional |
| `prescriptive` | 0.65 | functional | effect-functional |
| `systematic` | 0.60 | behaviour | behaviour |
| `fervent` | 0.55 | emotional | emotional |
| `totalising` | 0.55 | behaviour | behaviour |

### `solidarity` (synset `58775`) — 11 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `collective` | 0.95 | social | social |
| `cohesive` | 0.90 | physical | physical-other |
| `mutual` | 0.85 | social | social |
| `unifying` | 0.85 | effect | effect-functional |
| `protective` | 0.80 | functional | effect-functional |
| `empowering` | 0.75 | emotional | emotional |
| `sustaining` | 0.75 | functional | effect-functional |
| `resolute` | 0.70 | behaviour | behaviour |
| `warm` | 0.70 | emotional | sensorimotor |
| `political` | 0.65 | social | social |
| `visible` | 0.60 | behaviour | behaviour |

### `dissent` (synset `16028`) — 12 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `oppositional` | 0.95 | social | social |
| `deliberate` | 0.90 | behaviour | behaviour |
| `challenging` | 0.85 | effect | effect-functional |
| `principled` | 0.85 | emotional | emotional |
| `assertive` | 0.80 | behaviour | behaviour |
| `independent` | 0.80 | functional | effect-functional |
| `courageous` | 0.75 | emotional | emotional |
| `minority` | 0.75 | social | social |
| `isolated` | 0.70 | social | social |
| `vocal` | 0.70 | behaviour | behaviour |
| `uncomfortable` | 0.60 | emotional | emotional |
| `formal` | 0.55 | social | social |

### `patriotism` (synset `59341`) — 9 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `proud` | 0.90 | emotional | emotional |
| `devoted` | 0.88 | emotional | emotional |
| `sacrificial` | 0.85 | behaviour | behaviour |
| `collective` | 0.78 | social | social |
| `inspiring` | 0.70 | emotional | emotional |
| `fervent` | 0.68 | emotional | emotional |
| `nostalgic` | 0.55 | emotional | emotional |
| `ceremonial` | 0.52 | social | social |
| `divisive` | 0.48 | effect | effect-functional |

### `duty` (synset `21030`) — 14 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `binding` | 0.90 | social | social |
| `weighty` | 0.85 | emotional | emotional |
| `inescapable` | 0.80 | behaviour | behaviour |
| `serious` | 0.80 | emotional | emotional |
| `burdensome` | 0.75 | emotional | emotional |
| `constraining` | 0.75 | effect | effect-functional |
| `demanding` | 0.75 | behaviour | behaviour |
| `moral` | 0.75 | social | social |
| `internal` | 0.70 | emotional | emotional |
| `motivating` | 0.70 | effect | effect-functional |
| `social` | 0.70 | social | social |
| `persistent` | 0.65 | behaviour | behaviour |
| `honourable` | 0.60 | social | social |
| `empowering` | 0.35 | emotional | emotional |

### `empire` (synset `74238`) — 8 properties, 3 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `crisp` | 0.90 | physical | physical-other |
| `firm` | 0.80 | physical | physical-other |
| `sweet` | 0.80 | physical | sensorimotor |
| `juicy` | 0.75 | physical | physical-other |
| `round` | 0.70 | physical | sensorimotor |
| `tart` | 0.65 | physical | physical-other |
| `fragrant` | 0.50 | physical | sensorimotor |
| `autumnal` | 0.45 | social | social |

### `liberty` (synset `97447`) — 11 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `voluntary` | 0.90 | behaviour | behaviour |
| `autonomous` | 0.85 | functional | effect-functional |
| `empowering` | 0.80 | emotional | emotional |
| `independent` | 0.80 | behaviour | behaviour |
| `unrestricted` | 0.80 | behaviour | behaviour |
| `intentional` | 0.75 | behaviour | behaviour |
| `personal` | 0.75 | social | social |
| `open` | 0.70 | physical | physical-other |
| `expansive` | 0.65 | physical | physical-other |
| `affirming` | 0.60 | emotional | emotional |
| `dignifying` | 0.60 | social | social |

### `exploitation` (synset `18191`) — 13 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `constructing` | 1.00 | — | unknown |
| `industrializing` | 1.00 | — | unknown |
| `urbanizing` | 1.00 | — | unknown |
| `transformative` | 0.90 | effect | effect-functional |
| `economic` | 0.85 | functional | effect-functional |
| `profitable` | 0.85 | effect | effect-functional |
| `physical` | 0.80 | physical | physical-other |
| `planned` | 0.80 | behaviour | behaviour |
| `infrastructural` | 0.70 | functional | effect-functional |
| `permanent` | 0.70 | effect | effect-functional |
| `disruptive` | 0.65 | effect | effect-functional |
| `contested` | 0.60 | social | social |
| `progressive` | 0.60 | behaviour | behaviour |

### `servitude` (synset `97465`) — 10 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `coerced` | 1.00 | — | unknown |
| `involuntary` | 0.92 | functional | effect-functional |
| `exhausting` | 0.87 | effect | effect-functional |
| `dehumanising` | 0.85 | effect | effect-functional |
| `ownership` | 0.78 | social | social |
| `hierarchical` | 0.75 | social | social |
| `shame` | 0.72 | emotional | emotional |
| `punitive` | 0.70 | functional | effect-functional |
| `despair` | 0.68 | emotional | emotional |
| `historical` | 0.50 | social | social |

### `constitution` (synset `5133`) — 16 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `instituting` | 1.00 | — | unknown |
| `purposeful` | 0.85 | behaviour | behaviour |
| `deliberate` | 0.80 | behaviour | behaviour |
| `institutional` | 0.80 | social | social |
| `structured` | 0.80 | effect | effect-functional |
| `foundational` | 0.75 | effect | effect-functional |
| `collaborative` | 0.70 | social | social |
| `ordered` | 0.70 | effect | effect-functional |
| `transformative` | 0.70 | effect | effect-functional |
| `enduring` | 0.65 | effect | effect-functional |
| `systematic` | 0.65 | behaviour | behaviour |
| `complex` | 0.60 | behaviour | behaviour |
| `historic` | 0.60 | social | social |
| `effortful` | 0.55 | emotional | emotional |
| `creative` | 0.50 | functional | effect-functional |
| `formal` | 0.50 | social | social |

### `civilisation` (synset `77097`) — 17 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `collective` | 0.90 | social | social |
| `complex` | 0.88 | social | social |
| `temporal` | 0.85 | behaviour | behaviour |
| `distinctive` | 0.82 | effect | effect-functional |
| `expressive` | 0.80 | functional | effect-functional |
| `monumental` | 0.80 | physical | physical-other |
| `inherited` | 0.78 | social | social |
| `rooted` | 0.75 | physical | physical-other |
| `stratified` | 0.75 | social | social |
| `cohesive` | 0.72 | social | social |
| `accumulative` | 0.70 | behaviour | behaviour |
| `bounded` | 0.70 | physical | physical-other |
| `evolving` | 0.70 | behaviour | behaviour |
| `rich` | 0.68 | emotional | emotional |
| `perishable` | 0.65 | behaviour | behaviour |
| `fragile` | 0.60 | physical | physical-other |
| `luminous` | 0.50 | emotional | sensorimotor |

### `war` (synset `15970`) — 16 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `combative` | 0.90 | behaviour | behaviour |
| `sustained` | 0.90 | behaviour | behaviour |
| `targeted` | 0.88 | functional | effect-functional |
| `metaphorical` | 0.85 | social | social |
| `organised` | 0.85 | functional | effect-functional |
| `urgent` | 0.85 | emotional | emotional |
| `prolonged` | 0.82 | behaviour | behaviour |
| `collective` | 0.80 | social | social |
| `institutional` | 0.80 | social | social |
| `moralistic` | 0.75 | social | social |
| `persistent` | 0.75 | behaviour | behaviour |
| `eradicating` | 0.72 | functional | effect-functional |
| `political` | 0.70 | social | social |
| `contentious` | 0.65 | social | social |
| `strategic` | 0.65 | behaviour | behaviour |
| `polarising` | 0.60 | effect | effect-functional |

### `soul` (synset `17966`) — 13 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `epitomizing` | 1.00 | — | unknown |
| `incarnate` | 1.00 | — | unknown |
| `personifying` | 1.00 | — | unknown |
| `quintessential` | 0.90 | functional | effect-functional |
| `central` | 0.80 | functional | effect-functional |
| `exemplary` | 0.80 | social | social |
| `living` | 0.80 | physical | physical-other |
| `symbolic` | 0.70 | functional | effect-functional |
| `admired` | 0.65 | emotional | emotional |
| `inspiring` | 0.65 | effect | effect-functional |
| `sincere` | 0.65 | emotional | emotional |
| `influential` | 0.60 | effect | effect-functional |
| `rare` | 0.55 | social | social |

### `muscle` (synset `61005`) — 18 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `forceful` | 0.90 | behaviour | behaviour |
| `authoritative` | 0.85 | social | social |
| `coercive` | 0.85 | effect | effect-functional |
| `intimidating` | 0.80 | emotional | emotional |
| `physical` | 0.75 | physical | physical-other |
| `political` | 0.75 | social | social |
| `raw` | 0.75 | physical | physical-other |
| `blunt` | 0.70 | behaviour | behaviour |
| `leveraged` | 0.70 | functional | effect-functional |
| `strategic` | 0.70 | behaviour | behaviour |
| `threatening` | 0.70 | emotional | emotional |
| `aggressive` | 0.65 | behaviour | behaviour |
| `concentrated` | 0.65 | physical | physical-other |
| `decisive` | 0.65 | effect | effect-functional |
| `feared` | 0.65 | emotional | emotional |
| `credible` | 0.60 | social | social |
| `visible` | 0.60 | social | social |
| `respected` | 0.55 | social | social |

### `vein` (synset `92684`) — 11 properties, 2 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `branching` | 0.92 | physical | physical-other |
| `networked` | 0.88 | physical | physical-other |
| `conducting` | 0.85 | functional | effect-functional |
| `structural` | 0.82 | functional | effect-functional |
| `visible` | 0.75 | physical | physical-other |
| `hierarchical` | 0.72 | physical | physical-other |
| `thin` | 0.70 | physical | sensorimotor |
| `intricate` | 0.65 | physical | physical-other |
| `rigid` | 0.65 | physical | sensorimotor |
| `symmetrical` | 0.60 | physical | physical-other |
| `pale` | 0.55 | physical | physical-other |

### `nerve` (synset `30528`) — 13 properties, 2 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `steeling` | 1.00 | — | unknown |
| `tensing` | 1.00 | — | unknown |
| `resolute` | 0.90 | emotional | emotional |
| `deliberate` | 0.85 | behaviour | behaviour |
| `hardening` | 0.85 | effect | effect-functional |
| `bracing` | 0.80 | physical | physical-other |
| `tense` | 0.80 | physical | sensorimotor |
| `focused` | 0.75 | behaviour | behaviour |
| `inward` | 0.75 | behaviour | behaviour |
| `anticipatory` | 0.70 | behaviour | behaviour |
| `courageous` | 0.70 | emotional | emotional |
| `protective` | 0.65 | functional | effect-functional |
| `quiet` | 0.60 | behaviour | sensorimotor |

### `spine` (synset `56085`) — 12 properties, 2 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `identifying` | 0.90 | functional | effect-functional |
| `labelled` | 0.90 | functional | effect-functional |
| `narrow` | 0.85 | physical | sensorimotor |
| `textual` | 0.85 | functional | effect-functional |
| `visible` | 0.85 | functional | effect-functional |
| `vertical` | 0.75 | physical | physical-other |
| `binding` | 0.70 | functional | effect-functional |
| `coloured` | 0.70 | physical | physical-other |
| `flat` | 0.70 | physical | physical-other |
| `durable` | 0.65 | physical | physical-other |
| `rigid` | 0.65 | physical | sensorimotor |
| `decorative` | 0.45 | physical | physical-other |

### `brain` (synset `73636`) — 10 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `nutrient-dense` | 1.00 | — | unknown |
| `soft` | 0.95 | physical | sensorimotor |
| `delicate` | 0.85 | physical | physical-other |
| `fatty` | 0.85 | physical | physical-other |
| `pale` | 0.80 | physical | physical-other |
| `rich` | 0.80 | physical | physical-other |
| `offal` | 0.75 | social | social |
| `polarising` | 0.65 | social | social |
| `traditional` | 0.55 | social | social |
| `nutritious` | 0.50 | functional | effect-functional |

### `stomach` (synset `72593`) — 10 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `desiring` | 1.00 | — | unknown |
| `hunger` | 1.00 | — | unknown |
| `bodily` | 0.80 | physical | physical-other |
| `instinctive` | 0.75 | behaviour | behaviour |
| `variable` | 0.75 | behaviour | behaviour |
| `pleasurable` | 0.70 | emotional | emotional |
| `motivating` | 0.65 | effect | effect-functional |
| `restorative` | 0.65 | effect | effect-functional |
| `selective` | 0.60 | behaviour | behaviour |
| `fragile` | 0.55 | physical | physical-other |

### `lung` (synset `62003`) — 11 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `inflating` | 1.00 | — | unknown |
| `expanding` | 0.90 | behaviour | behaviour |
| `vital` | 0.90 | functional | effect-functional |
| `elastic` | 0.85 | physical | physical-other |
| `rhythmic` | 0.85 | behaviour | sensorimotor |
| `spongy` | 0.85 | physical | physical-other |
| `airy` | 0.75 | physical | physical-other |
| `paired` | 0.75 | physical | physical-other |
| `large` | 0.70 | physical | physical-other |
| `pink` | 0.70 | physical | physical-other |
| `vulnerable` | 0.65 | effect | effect-functional |

### `flesh` (synset `61366`) — 11 properties, 3 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `soft` | 0.95 | physical | sensorimotor |
| `moist` | 0.80 | physical | physical-other |
| `warm` | 0.80 | physical | sensorimotor |
| `perishable` | 0.75 | effect | effect-functional |
| `dense` | 0.70 | physical | sensorimotor |
| `sensory` | 0.70 | functional | effect-functional |
| `vulnerable` | 0.65 | emotional | emotional |
| `elastic` | 0.60 | physical | physical-other |
| `nourishing` | 0.60 | functional | effect-functional |
| `mortal` | 0.55 | emotional | emotional |
| `corporeal` | 0.50 | social | social |

### `skull` (synset `62752`) — 11 properties, 3 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `bony` | 0.95 | physical | physical-other |
| `hard` | 0.95 | physical | sensorimotor |
| `protective` | 0.90 | functional | effect-functional |
| `hollow` | 0.85 | physical | physical-other |
| `mortality` | 0.75 | emotional | emotional |
| `white` | 0.70 | physical | sensorimotor |
| `durable` | 0.65 | physical | physical-other |
| `ominous` | 0.65 | emotional | emotional |
| `socketed` | 0.65 | physical | physical-other |
| `ancient` | 0.60 | social | social |
| `heavy` | 0.60 | physical | sensorimotor |

### `hair` (synset `31776`) — 18 properties, 3 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `filamentous` | 0.95 | physical | physical-other |
| `projecting` | 0.90 | behaviour | behaviour |
| `slender` | 0.90 | physical | physical-other |
| `thin` | 0.90 | physical | sensorimotor |
| `elongated` | 0.85 | physical | physical-other |
| `biological` | 0.80 | functional | effect-functional |
| `delicate` | 0.75 | physical | physical-other |
| `microscopic` | 0.75 | physical | physical-other |
| `flexible` | 0.70 | physical | sensorimotor |
| `absorptive` | 0.65 | functional | effect-functional |
| `sensory` | 0.65 | functional | effect-functional |
| `numerous` | 0.60 | physical | physical-other |
| `protective` | 0.60 | functional | effect-functional |
| `anchoring` | 0.50 | functional | effect-functional |
| `dense` | 0.50 | physical | sensorimotor |
| `adhesive` | 0.45 | functional | effect-functional |
| `varied` | 0.40 | physical | physical-other |
| `cellular` | 0.35 | physical | physical-other |

### `tongue` (synset `97065`) — 14 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `elongated` | 0.90 | physical | physical-other |
| `transient` | 0.90 | behaviour | behaviour |
| `projecting` | 0.85 | physical | physical-other |
| `thin` | 0.85 | physical | sensorimotor |
| `ephemeral` | 0.80 | effect | effect-functional |
| `fleeting` | 0.80 | behaviour | behaviour |
| `directional` | 0.75 | physical | physical-other |
| `delicate` | 0.70 | physical | physical-other |
| `dynamic` | 0.70 | behaviour | behaviour |
| `visual` | 0.70 | functional | effect-functional |
| `tapering` | 0.65 | physical | physical-other |
| `penetrating` | 0.60 | physical | physical-other |
| `fragile` | 0.50 | physical | physical-other |
| `eerie` | 0.45 | emotional | emotional |

### `voice` (synset `70141`) — 11 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `melodic` | 0.90 | physical | physical-other |
| `layered` | 0.85 | behaviour | behaviour |
| `harmonic` | 0.80 | functional | effect-functional |
| `tonal` | 0.80 | physical | physical-other |
| `interwoven` | 0.75 | behaviour | behaviour |
| `complementary` | 0.70 | social | social |
| `distinct` | 0.70 | physical | physical-other |
| `independent` | 0.65 | behaviour | behaviour |
| `rhythmic` | 0.65 | behaviour | sensorimotor |
| `structural` | 0.60 | functional | effect-functional |
| `contrapuntal` | 0.50 | functional | effect-functional |

### `tear` (synset `8663`) — 11 properties, 2 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `forceful` | 0.90 | behaviour | behaviour |
| `irreversible` | 0.85 | effect | effect-functional |
| `destructive` | 0.80 | effect | effect-functional |
| `sudden` | 0.80 | behaviour | behaviour |
| `jagged` | 0.75 | physical | physical-other |
| `audible` | 0.70 | physical | physical-other |
| `rapid` | 0.70 | behaviour | sensorimotor |
| `tactile` | 0.65 | physical | physical-other |
| `violent` | 0.60 | behaviour | behaviour |
| `exposing` | 0.55 | effect | effect-functional |
| `linear` | 0.50 | physical | sensorimotor |

### `sweat` (synset `87172`) — 13 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `beaded` | 1.00 | — | unknown |
| `droplet-covered` | 1.00 | — | unknown |
| `surface-clinging` | 1.00 | — | unknown |
| `wet` | 0.90 | physical | physical-other |
| `beading` | 0.85 | behaviour | behaviour |
| `cold` | 0.85 | physical | sensorimotor |
| `transparent` | 0.80 | physical | physical-other |
| `dripping` | 0.70 | behaviour | behaviour |
| `thermal` | 0.70 | functional | effect-functional |
| `ephemeral` | 0.65 | behaviour | behaviour |
| `fine` | 0.65 | physical | physical-other |
| `slick` | 0.60 | physical | physical-other |
| `diffuse` | 0.55 | behaviour | behaviour |

### `pulse` (synset `28043`) — 13 properties, 2 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `cycling` | 1.00 | — | unknown |
| `intermittent` | 0.95 | behaviour | behaviour |
| `rhythmic` | 0.85 | behaviour | sensorimotor |
| `signal` | 0.85 | functional | effect-functional |
| `transient` | 0.85 | behaviour | behaviour |
| `precise` | 0.80 | behaviour | behaviour |
| `controlled` | 0.75 | functional | effect-functional |
| `invisible` | 0.75 | physical | physical-other |
| `modulated` | 0.70 | functional | effect-functional |
| `rapid` | 0.70 | behaviour | sensorimotor |
| `energetic` | 0.65 | physical | physical-other |
| `technical` | 0.60 | social | social |
| `penetrating` | 0.55 | effect | effect-functional |

### `womb` (synset `62647`) — 12 properties, 2 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `gestational` | 1.00 | — | unknown |
| `pelvic` | 1.00 | — | unknown |
| `muscular` | 0.90 | physical | physical-other |
| `protective` | 0.90 | functional | effect-functional |
| `hollow` | 0.85 | physical | physical-other |
| `nurturing` | 0.85 | functional | effect-functional |
| `internal` | 0.80 | physical | physical-other |
| `warm` | 0.80 | physical | sensorimotor |
| `elastic` | 0.75 | physical | physical-other |
| `intimate` | 0.70 | emotional | emotional |
| `moist` | 0.65 | physical | physical-other |
| `rhythmic` | 0.65 | behaviour | sensorimotor |

### `rib` (synset `54918`) — 10 properties, 2 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `structural` | 0.90 | functional | effect-functional |
| `curved` | 0.85 | physical | sensorimotor |
| `rigid` | 0.85 | physical | sensorimotor |
| `arching` | 0.80 | behaviour | behaviour |
| `skeletal` | 0.80 | physical | physical-other |
| `internal` | 0.75 | physical | physical-other |
| `slender` | 0.70 | physical | physical-other |
| `parallel` | 0.65 | physical | physical-other |
| `organic` | 0.60 | emotional | emotional |
| `repeating` | 0.60 | behaviour | behaviour |

### `fist` (synset `62872`) — 12 properties, 3 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `clenched` | 0.95 | physical | physical-other |
| `hard` | 0.90 | physical | sensorimotor |
| `striking` | 0.90 | functional | effect-functional |
| `compact` | 0.85 | physical | sensorimotor |
| `powerful` | 0.85 | effect | effect-functional |
| `aggressive` | 0.80 | behaviour | behaviour |
| `threatening` | 0.80 | emotional | emotional |
| `tense` | 0.75 | physical | sensorimotor |
| `knuckled` | 0.70 | physical | physical-other |
| `blunt` | 0.65 | physical | physical-other |
| `dominant` | 0.60 | social | social |
| `defiant` | 0.55 | emotional | emotional |

### `wrinkle` (synset `23353`) — 14 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `bunching` | 1.00 | — | unknown |
| `scrunching` | 1.00 | — | unknown |
| `wrinkling` | 1.00 | — | unknown |
| `contracting` | 0.90 | behaviour | behaviour |
| `puckering` | 0.90 | physical | physical-other |
| `gathering` | 0.85 | behaviour | behaviour |
| `expressive` | 0.80 | social | social |
| `tense` | 0.80 | physical | sensorimotor |
| `facial` | 0.75 | social | social |
| `rounded` | 0.75 | physical | physical-other |
| `deliberate` | 0.70 | behaviour | behaviour |
| `temporary` | 0.70 | effect | effect-functional |
| `skeptical` | 0.60 | emotional | emotional |
| `focused` | 0.50 | emotional | emotional |

### `scar` (synset `58442`) — 14 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `blemished` | 1.00 | — | unknown |
| `marred` | 1.00 | — | unknown |
| `visible` | 0.90 | physical | physical-other |
| `evidence` | 0.85 | functional | effect-functional |
| `surface` | 0.85 | physical | physical-other |
| `detracting` | 0.70 | effect | effect-functional |
| `localised` | 0.70 | physical | physical-other |
| `permanent` | 0.65 | effect | effect-functional |
| `scarring` | 0.65 | effect | effect-functional |
| `telling` | 0.65 | functional | effect-functional |
| `discoloured` | 0.60 | physical | physical-other |
| `irreversible` | 0.60 | effect | effect-functional |
| `worn` | 0.55 | physical | physical-other |
| `tactile` | 0.50 | physical | physical-other |

### `teeth` (synset `61440`) — 16 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `hard` | 0.85 | physical | sensorimotor |
| `functional` | 0.80 | functional | effect-functional |
| `structured` | 0.80 | physical | physical-other |
| `varied` | 0.80 | physical | physical-other |
| `arranged` | 0.75 | physical | physical-other |
| `countable` | 0.75 | physical | physical-other |
| `diagnostic` | 0.75 | functional | effect-functional |
| `biological` | 0.72 | functional | effect-functional |
| `sequential` | 0.70 | behaviour | behaviour |
| `permanent` | 0.65 | physical | physical-other |
| `bilateral` | 0.60 | physical | physical-other |
| `indicative` | 0.60 | effect | effect-functional |
| `numerical` | 0.60 | physical | physical-other |
| `symmetrical` | 0.60 | physical | physical-other |
| `developmental` | 0.58 | behaviour | behaviour |
| `evolutionary` | 0.55 | social | social |

### `belly` (synset `35471`) — 12 properties, 2 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `ground-facing` | 1.00 | — | unknown |
| `underneath` | 1.00 | — | unknown |
| `ventral` | 1.00 | — | unknown |
| `anatomical` | 0.85 | functional | effect-functional |
| `vulnerable` | 0.80 | effect | effect-functional |
| `pale` | 0.75 | physical | physical-other |
| `soft` | 0.70 | physical | sensorimotor |
| `smooth` | 0.65 | physical | sensorimotor |
| `scaled` | 0.60 | physical | physical-other |
| `streamlined` | 0.55 | physical | physical-other |
| `sensory` | 0.50 | functional | effect-functional |
| `protective` | 0.45 | functional | effect-functional |

### `skeleton` (synset `96173`) — 11 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `bare` | 0.95 | physical | physical-other |
| `minimal` | 0.92 | functional | effect-functional |
| `essential` | 0.85 | functional | effect-functional |
| `structural` | 0.85 | functional | effect-functional |
| `sparse` | 0.80 | physical | physical-other |
| `exposed` | 0.75 | physical | physical-other |
| `foundational` | 0.70 | functional | effect-functional |
| `gaunt` | 0.70 | physical | physical-other |
| `austere` | 0.65 | emotional | emotional |
| `reductive` | 0.60 | effect | effect-functional |
| `fragile` | 0.55 | physical | physical-other |

### `solitude` (synset `78714`) — 12 properties, 2 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `quiet` | 0.95 | physical | sensorimotor |
| `remote` | 0.90 | physical | physical-other |
| `empty` | 0.85 | physical | physical-other |
| `isolated` | 0.85 | social | social |
| `peaceful` | 0.80 | emotional | emotional |
| `still` | 0.80 | physical | sensorimotor |
| `contemplative` | 0.75 | emotional | emotional |
| `restorative` | 0.65 | effect | effect-functional |
| `free` | 0.60 | emotional | emotional |
| `introspective` | 0.60 | effect | effect-functional |
| `untouched` | 0.55 | physical | physical-other |
| `austere` | 0.50 | physical | physical-other |

### `adversity` (synset `71763`) — 1 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `destabilizing` | 1.00 | — | unknown |

### `resilience` (synset `60103`) — 12 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `shape-memory` | 1.00 | — | unknown |
| `elastic` | 0.90 | physical | physical-other |
| `recoverable` | 0.90 | behaviour | behaviour |
| `restoring` | 0.85 | behaviour | behaviour |
| `springy` | 0.85 | physical | physical-other |
| `flexible` | 0.80 | physical | sensorimotor |
| `absorbing` | 0.70 | functional | effect-functional |
| `durable` | 0.65 | physical | physical-other |
| `tensile` | 0.60 | physical | physical-other |
| `bounded` | 0.50 | functional | effect-functional |
| `intrinsic` | 0.50 | physical | physical-other |
| `invisible` | 0.45 | physical | physical-other |

### `growth` (synset `77852`) — 15 properties, 3 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `green` | 0.90 | physical | sensorimotor |
| `leafy` | 0.85 | physical | physical-other |
| `organic` | 0.85 | physical | physical-other |
| `spreading` | 0.85 | behaviour | behaviour |
| `alive` | 0.80 | physical | physical-other |
| `dense` | 0.75 | physical | sensorimotor |
| `natural` | 0.75 | physical | physical-other |
| `abundant` | 0.65 | effect | effect-functional |
| `rooted` | 0.65 | physical | physical-other |
| `textured` | 0.65 | physical | physical-other |
| `wild` | 0.65 | behaviour | behaviour |
| `seasonal` | 0.60 | behaviour | behaviour |
| `tangled` | 0.60 | physical | physical-other |
| `encroaching` | 0.55 | behaviour | behaviour |
| `fragrant` | 0.45 | physical | sensorimotor |

### `turmoil` (synset `97361`) — 13 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `destabilizing` | 1.00 | — | unknown |
| `disruptive` | 0.90 | effect | effect-functional |
| `violent` | 0.90 | behaviour | behaviour |
| `destabilising` | 0.85 | effect | effect-functional |
| `intense` | 0.85 | behaviour | behaviour |
| `uncontrolled` | 0.80 | behaviour | behaviour |
| `fearful` | 0.75 | emotional | emotional |
| `sudden` | 0.75 | behaviour | behaviour |
| `sweeping` | 0.75 | behaviour | behaviour |
| `loud` | 0.65 | physical | sensorimotor |
| `transformative` | 0.65 | effect | effect-functional |
| `bodily` | 0.60 | physical | physical-other |
| `exhausting` | 0.60 | emotional | emotional |

### `abundance` (synset `96494`) — 10 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `crustal` | 1.00 | — | unknown |
| `measurable` | 0.90 | functional | effect-functional |
| `geological` | 0.85 | physical | physical-other |
| `proportional` | 0.85 | functional | effect-functional |
| `elemental` | 0.80 | functional | effect-functional |
| `distributed` | 0.75 | physical | physical-other |
| `scientific` | 0.70 | social | social |
| `stable` | 0.70 | behaviour | behaviour |
| `comparative` | 0.65 | functional | effect-functional |
| `trace` | 0.60 | physical | physical-other |

### `barrenness` (synset `60754`) — 10 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `futile` | 0.95 | effect | effect-functional |
| `unproductive` | 0.90 | functional | effect-functional |
| `empty` | 0.85 | physical | physical-other |
| `wasted` | 0.85 | effect | effect-functional |
| `sterile` | 0.80 | functional | effect-functional |
| `disappointing` | 0.75 | emotional | emotional |
| `dry` | 0.75 | physical | physical-other |
| `hollow` | 0.70 | emotional | emotional |
| `stagnant` | 0.65 | behaviour | behaviour |
| `exhausting` | 0.60 | emotional | emotional |

### `renewal` (synset `5895`) — 10 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `restorative` | 0.90 | functional | effect-functional |
| `transformative` | 0.90 | effect | effect-functional |
| `regenerative` | 0.85 | effect | effect-functional |
| `gradual` | 0.80 | behaviour | behaviour |
| `productive` | 0.80 | functional | effect-functional |
| `hopeful` | 0.75 | emotional | emotional |
| `purposeful` | 0.75 | behaviour | behaviour |
| `visible` | 0.65 | physical | physical-other |
| `costly` | 0.60 | effect | effect-functional |
| `communal` | 0.55 | social | social |

### `danger` (synset `15992`) — 13 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `risky` | 0.95 | functional | effect-functional |
| `bold` | 0.90 | behaviour | behaviour |
| `uncertain` | 0.90 | effect | effect-functional |
| `consequential` | 0.85 | effect | effect-functional |
| `reckless` | 0.85 | behaviour | behaviour |
| `voluntary` | 0.80 | functional | effect-functional |
| `courageous` | 0.75 | emotional | emotional |
| `exposed` | 0.75 | physical | physical-other |
| `thrilling` | 0.70 | emotional | emotional |
| `impulsive` | 0.65 | behaviour | behaviour |
| `singular` | 0.60 | behaviour | behaviour |
| `calculated` | 0.55 | behaviour | behaviour |
| `ambivalent` | 0.50 | emotional | emotional |

### `calm` (synset `6646`) — 12 properties, 2 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `still` | 0.95 | physical | sensorimotor |
| `windless` | 0.95 | physical | physical-other |
| `quiet` | 0.88 | physical | sensorimotor |
| `peaceful` | 0.85 | emotional | emotional |
| `stable` | 0.80 | behaviour | behaviour |
| `mild` | 0.75 | physical | physical-other |
| `clear` | 0.72 | physical | physical-other |
| `safe` | 0.70 | effect | effect-functional |
| `serene` | 0.70 | emotional | emotional |
| `flat` | 0.65 | physical | physical-other |
| `inviting` | 0.62 | emotional | emotional |
| `temporary` | 0.45 | behaviour | behaviour |

### `upheaval` (synset `12183`) — 15 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `agitated` | 0.90 | behaviour | behaviour |
| `turbulent` | 0.90 | behaviour | behaviour |
| `disruptive` | 0.85 | effect | effect-functional |
| `loud` | 0.85 | physical | sensorimotor |
| `collective` | 0.80 | social | social |
| `emotional` | 0.80 | emotional | emotional |
| `passionate` | 0.80 | emotional | emotional |
| `public` | 0.80 | social | social |
| `energetic` | 0.75 | behaviour | behaviour |
| `volatile` | 0.75 | behaviour | behaviour |
| `confrontational` | 0.70 | social | social |
| `visible` | 0.70 | physical | physical-other |
| `chaotic` | 0.65 | behaviour | behaviour |
| `urgent` | 0.65 | emotional | emotional |
| `political` | 0.55 | social | social |

### `prosperity` (synset `100116`) — 11 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `expansive` | 0.85 | behaviour | behaviour |
| `productive` | 0.85 | functional | effect-functional |
| `optimistic` | 0.80 | emotional | emotional |
| `rising` | 0.80 | behaviour | behaviour |
| `confident` | 0.75 | emotional | emotional |
| `employed` | 0.75 | social | social |
| `active` | 0.70 | behaviour | behaviour |
| `tangible` | 0.65 | physical | physical-other |
| `stabilising` | 0.60 | effect | effect-functional |
| `cyclical` | 0.55 | behaviour | behaviour |
| `unequal` | 0.45 | social | social |

### `fertility` (synset `104443`) — 11 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `population-based` | 1.00 | — | unknown |
| `statistical` | 0.95 | functional | effect-functional |
| `demographic` | 0.90 | functional | effect-functional |
| `annual` | 0.80 | behaviour | behaviour |
| `comparative` | 0.75 | functional | effect-functional |
| `normalised` | 0.75 | functional | effect-functional |
| `predictive` | 0.70 | effect | effect-functional |
| `declining` | 0.65 | behaviour | behaviour |
| `generational` | 0.60 | social | social |
| `cultural` | 0.55 | social | social |
| `epidemiological` | 0.50 | social | social |

### `desolation` (synset `71756`) — 1 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `erasure` | 1.00 | — | unknown |

### `temptation` (synset `63559`) — 11 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `alluring` | 0.95 | physical | physical-other |
| `irresistible` | 0.90 | effect | effect-functional |
| `seductive` | 0.90 | behaviour | behaviour |
| `magnetic` | 0.85 | behaviour | behaviour |
| `beckoning` | 0.80 | behaviour | behaviour |
| `forbidden` | 0.80 | social | social |
| `pleasurable` | 0.75 | emotional | emotional |
| `sweet` | 0.75 | physical | sensorimotor |
| `dangerous` | 0.70 | effect | effect-functional |
| `persistent` | 0.65 | behaviour | behaviour |
| `destabilising` | 0.60 | effect | effect-functional |

### `transformation` (synset `8844`) — 11 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `visible` | 0.85 | physical | physical-other |
| `dramatic` | 0.75 | emotional | emotional |
| `complete` | 0.70 | effect | effect-functional |
| `irreversible` | 0.65 | effect | effect-functional |
| `surprising` | 0.65 | emotional | emotional |
| `structural` | 0.60 | physical | physical-other |
| `sudden` | 0.55 | behaviour | behaviour |
| `energetic` | 0.50 | physical | physical-other |
| `gradual` | 0.50 | behaviour | behaviour |
| `purposeful` | 0.50 | functional | effect-functional |
| `disorienting` | 0.45 | emotional | emotional |

### `instability` (synset `58981`) — 12 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `shaky` | 1.00 | — | unknown |
| `unpredictable` | 0.90 | behaviour | behaviour |
| `unreliable` | 0.90 | functional | effect-functional |
| `precarious` | 0.85 | physical | physical-other |
| `volatile` | 0.80 | behaviour | behaviour |
| `dangerous` | 0.75 | effect | effect-functional |
| `threatening` | 0.75 | emotional | emotional |
| `anxious` | 0.70 | emotional | emotional |
| `shifting` | 0.70 | behaviour | behaviour |
| `disruptive` | 0.65 | effect | effect-functional |
| `collapsible` | 0.60 | effect | effect-functional |
| `temporary` | 0.40 | behaviour | behaviour |

### `purity` (synset `59196`) — 10 properties, 2 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `chaste` | 0.95 | social | social |
| `fragile` | 0.88 | emotional | emotional |
| `valued` | 0.88 | social | social |
| `protected` | 0.82 | social | social |
| `modest` | 0.80 | behaviour | behaviour |
| `irreversible` | 0.78 | effect | effect-functional |
| `restrained` | 0.72 | behaviour | behaviour |
| `patriarchal` | 0.68 | social | social |
| `white` | 0.60 | physical | sensorimotor |
| `silent` | 0.52 | behaviour | sensorimotor |

### `complexity` (synset `58782`) — 11 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `layered` | 0.90 | physical | physical-other |
| `dense` | 0.85 | physical | sensorimotor |
| `interconnected` | 0.85 | behaviour | behaviour |
| `challenging` | 0.80 | effect | effect-functional |
| `compound` | 0.80 | physical | physical-other |
| `bewildering` | 0.75 | emotional | emotional |
| `deep` | 0.75 | physical | physical-other |
| `nuanced` | 0.70 | behaviour | behaviour |
| `resistant` | 0.65 | behaviour | behaviour |
| `rich` | 0.60 | emotional | emotional |
| `structured` | 0.55 | functional | effect-functional |

### `fragility` (synset `60211`) — 10 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `fragile` | 0.90 | physical | physical-other |
| `vulnerable` | 0.85 | effect | effect-functional |
| `breakable` | 0.80 | physical | physical-other |
| `protective` | 0.75 | functional | effect-functional |
| `soft` | 0.75 | physical | sensorimotor |
| `tender` | 0.70 | physical | physical-other |
| `lightweight` | 0.65 | physical | physical-other |
| `ephemeral` | 0.60 | effect | effect-functional |
| `precious` | 0.55 | emotional | emotional |
| `dependent` | 0.50 | social | social |

### `stubbornness` (synset `59264`) — 11 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `unyielding` | 0.93 | behaviour | behaviour |
| `resistant` | 0.90 | behaviour | behaviour |
| `rigid` | 0.88 | behaviour | sensorimotor |
| `frustrating` | 0.80 | emotional | emotional |
| `entrenched` | 0.75 | behaviour | behaviour |
| `defiant` | 0.70 | emotional | emotional |
| `blinkered` | 0.65 | behaviour | behaviour |
| `tenacious` | 0.60 | behaviour | behaviour |
| `exhausting` | 0.58 | effect | effect-functional |
| `condemned` | 0.55 | social | social |
| `isolating` | 0.52 | effect | effect-functional |

### `menace` (synset `68455`) — 11 properties, 2 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `intimidating` | 0.95 | emotional | emotional |
| `hostile` | 0.90 | behaviour | behaviour |
| `looming` | 0.80 | behaviour | behaviour |
| `coercive` | 0.75 | functional | effect-functional |
| `oppressive` | 0.70 | emotional | emotional |
| `tense` | 0.70 | emotional | sensorimotor |
| `deliberate` | 0.65 | behaviour | behaviour |
| `targeted` | 0.65 | behaviour | behaviour |
| `dark` | 0.60 | emotional | sensorimotor |
| `destabilising` | 0.55 | effect | effect-functional |
| `criminal` | 0.50 | social | social |

### `trust` (synset `14798`) — 17 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `conviction-filled` | 1.00 | — | unknown |
| `confident` | 0.95 | emotional | emotional |
| `assured` | 0.90 | emotional | emotional |
| `certain` | 0.85 | emotional | emotional |
| `optimistic` | 0.85 | emotional | emotional |
| `internal` | 0.80 | behaviour | behaviour |
| `cognitive` | 0.75 | functional | effect-functional |
| `steadfast` | 0.75 | behaviour | behaviour |
| `grounded` | 0.70 | emotional | emotional |
| `persuasive` | 0.70 | social | social |
| `resolute` | 0.70 | behaviour | behaviour |
| `calm` | 0.65 | emotional | emotional |
| `committed` | 0.65 | behaviour | behaviour |
| `resilient` | 0.65 | behaviour | behaviour |
| `social` | 0.65 | social | social |
| `motivating` | 0.60 | effect | effect-functional |
| `unverified` | 0.45 | functional | effect-functional |

### `betrayal` (synset `59350`) — 12 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `perfidious` | 1.00 | — | unknown |
| `treacherous` | 0.95 | behaviour | behaviour |
| `damaging` | 0.90 | effect | effect-functional |
| `harmful` | 0.88 | effect | effect-functional |
| `condemned` | 0.85 | social | social |
| `shocking` | 0.82 | emotional | emotional |
| `shameful` | 0.80 | social | social |
| `secretive` | 0.78 | behaviour | behaviour |
| `distrustful` | 0.75 | social | social |
| `dangerous` | 0.72 | effect | effect-functional |
| `irreversible` | 0.70 | effect | effect-functional |
| `calculated` | 0.65 | behaviour | behaviour |

### `intimacy` (synset `58250`) — 18 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `warm` | 0.90 | emotional | sensorimotor |
| `comfortable` | 0.85 | emotional | emotional |
| `bonded` | 0.80 | social | social |
| `intimate` | 0.80 | emotional | emotional |
| `trusting` | 0.80 | social | social |
| `informal` | 0.75 | social | social |
| `longstanding` | 0.75 | behaviour | behaviour |
| `safe` | 0.75 | emotional | emotional |
| `affectionate` | 0.70 | emotional | emotional |
| `open` | 0.70 | behaviour | behaviour |
| `reciprocal` | 0.70 | social | social |
| `enduring` | 0.65 | behaviour | behaviour |
| `relaxed` | 0.65 | emotional | emotional |
| `unspoken` | 0.65 | behaviour | behaviour |
| `nurturing` | 0.60 | social | social |
| `shared` | 0.60 | social | social |
| `layered` | 0.55 | physical | physical-other |
| `habitual` | 0.50 | behaviour | behaviour |

### `rivalry` (synset `21631`) — 9 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `adversarial` | 0.85 | social | social |
| `striving` | 0.80 | behaviour | behaviour |
| `intense` | 0.75 | behaviour | behaviour |
| `motivating` | 0.75 | emotional | emotional |
| `energetic` | 0.70 | behaviour | behaviour |
| `measured` | 0.70 | functional | effect-functional |
| `stressful` | 0.70 | emotional | emotional |
| `public` | 0.60 | social | social |
| `selective` | 0.55 | effect | effect-functional |

### `loyalty` (synset `59338`) — 10 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `steadfast` | 0.92 | behaviour | behaviour |
| `reliable` | 0.88 | functional | effect-functional |
| `trusting` | 0.80 | emotional | emotional |
| `valued` | 0.78 | social | social |
| `binding` | 0.75 | social | social |
| `protective` | 0.70 | functional | effect-functional |
| `principled` | 0.68 | functional | effect-functional |
| `unconditional` | 0.65 | behaviour | behaviour |
| `reciprocal` | 0.62 | social | social |
| `warm` | 0.58 | emotional | sensorimotor |

### `attachment` (synset `44324`) — 12 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `coupling` | 1.00 | — | unknown |
| `holding` | 0.95 | functional | effect-functional |
| `joining` | 0.90 | functional | effect-functional |
| `strong` | 0.90 | physical | physical-other |
| `tight` | 0.85 | physical | physical-other |
| `durable` | 0.75 | physical | physical-other |
| `structural` | 0.70 | functional | effect-functional |
| `tensile` | 0.70 | physical | physical-other |
| `adhesive` | 0.65 | physical | physical-other |
| `reliable` | 0.65 | emotional | emotional |
| `mechanical` | 0.60 | physical | physical-other |
| `invisible` | 0.50 | physical | physical-other |

### `infatuation` (synset `64148`) — 11 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `idealised` | 0.95 | functional | effect-functional |
| `consuming` | 0.90 | effect | effect-functional |
| `temporary` | 0.90 | behaviour | behaviour |
| `intense` | 0.85 | emotional | emotional |
| `magnetic` | 0.85 | effect | effect-functional |
| `blinding` | 0.80 | effect | effect-functional |
| `intoxicating` | 0.75 | emotional | emotional |
| `projected` | 0.75 | functional | effect-functional |
| `fragile` | 0.70 | physical | physical-other |
| `volatile` | 0.65 | behaviour | behaviour |
| `elusive` | 0.60 | functional | effect-functional |

### `reconciliation` (synset `22204`) — 11 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `conciliatory` | 0.85 | social | social |
| `healing` | 0.80 | effect | effect-functional |
| `restorative` | 0.80 | effect | effect-functional |
| `hopeful` | 0.75 | emotional | emotional |
| `gradual` | 0.70 | behaviour | behaviour |
| `mutual` | 0.70 | social | social |
| `diplomatic` | 0.65 | social | social |
| `warm` | 0.65 | emotional | sensorimotor |
| `vulnerable` | 0.60 | emotional | emotional |
| `tentative` | 0.55 | behaviour | behaviour |
| `symbolic` | 0.50 | social | social |

### `estrangement` (synset `72688`) — 1 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `estranged` | 1.00 | — | unknown |

### `friendship` (synset `97121`) — 15 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `mutual` | 0.90 | social | social |
| `trusting` | 0.90 | social | social |
| `reciprocal` | 0.85 | social | social |
| `supportive` | 0.85 | functional | effect-functional |
| `warm` | 0.85 | emotional | sensorimotor |
| `comfortable` | 0.80 | emotional | emotional |
| `enduring` | 0.80 | behaviour | behaviour |
| `loyal` | 0.80 | behaviour | behaviour |
| `comforting` | 0.75 | emotional | emotional |
| `joyful` | 0.75 | emotional | emotional |
| `voluntary` | 0.75 | social | social |
| `shared` | 0.70 | social | social |
| `nurturing` | 0.65 | functional | effect-functional |
| `affirming` | 0.55 | emotional | emotional |
| `informal` | 0.50 | social | social |

### `romance` (synset `66674`) — 10 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `melodramatic` | 1.00 | — | unknown |
| `idealized` | 0.95 | emotional | emotional |
| `escapist` | 0.90 | functional | effect-functional |
| `adventurous` | 0.75 | behaviour | behaviour |
| `fantastical` | 0.70 | physical | physical-other |
| `immersive` | 0.70 | effect | effect-functional |
| `elevated` | 0.65 | social | social |
| `heroic` | 0.65 | social | social |
| `nostalgic` | 0.60 | emotional | emotional |
| `elaborate` | 0.55 | behaviour | behaviour |

### `manipulation` (synset `3318`) — 14 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `exploitative` | 0.95 | behaviour | behaviour |
| `calculating` | 0.90 | behaviour | behaviour |
| `covert` | 0.85 | behaviour | behaviour |
| `deceptive` | 0.85 | behaviour | behaviour |
| `controlling` | 0.80 | functional | effect-functional |
| `cunning` | 0.80 | behaviour | behaviour |
| `hidden` | 0.80 | behaviour | behaviour |
| `instrumental` | 0.75 | functional | effect-functional |
| `opportunistic` | 0.75 | behaviour | behaviour |
| `predatory` | 0.75 | behaviour | behaviour |
| `cold` | 0.70 | emotional | sensorimotor |
| `reprehensible` | 0.70 | emotional | emotional |
| `corrosive` | 0.65 | effect | effect-functional |
| `asymmetric` | 0.60 | social | social |

### `devotion` (synset `19623`) — 11 properties, 2 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `reverent` | 0.85 | emotional | emotional |
| `silent` | 0.85 | behaviour | sensorimotor |
| `meditative` | 0.80 | behaviour | behaviour |
| `private` | 0.75 | social | social |
| `humbling` | 0.70 | emotional | emotional |
| `rhythmic` | 0.70 | behaviour | sensorimotor |
| `peaceful` | 0.65 | emotional | emotional |
| `repetitive` | 0.65 | behaviour | behaviour |
| `focused` | 0.60 | behaviour | behaviour |
| `ritualistic` | 0.60 | social | social |
| `grounding` | 0.50 | emotional | emotional |

### `rejection` (synset `4351`) — 11 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `dismissive` | 0.90 | behaviour | behaviour |
| `excluding` | 0.85 | effect | effect-functional |
| `decisive` | 0.80 | behaviour | behaviour |
| `final` | 0.80 | effect | effect-functional |
| `unwanted` | 0.80 | emotional | emotional |
| `distancing` | 0.75 | effect | effect-functional |
| `painful` | 0.75 | emotional | emotional |
| `deliberate` | 0.70 | behaviour | behaviour |
| `cold` | 0.65 | emotional | sensorimotor |
| `abrupt` | 0.60 | behaviour | behaviour |
| `formal` | 0.50 | social | social |

### `forgiveness` (synset `22547`) — 12 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `merciful` | 0.90 | emotional | emotional |
| `releasing` | 0.85 | effect | effect-functional |
| `healing` | 0.80 | effect | effect-functional |
| `reconciling` | 0.80 | social | social |
| `deliberate` | 0.75 | behaviour | behaviour |
| `gracious` | 0.75 | social | social |
| `transformative` | 0.70 | effect | effect-functional |
| `virtuous` | 0.70 | social | social |
| `cathartic` | 0.65 | emotional | emotional |
| `selfless` | 0.65 | emotional | emotional |
| `unconditional` | 0.60 | behaviour | behaviour |
| `spiritual` | 0.50 | social | social |

### `possessiveness` (synset `59689`) — 12 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `jealous` | 1.00 | — | unknown |
| `controlling` | 0.92 | behaviour | behaviour |
| `clinging` | 0.82 | behaviour | behaviour |
| `domineering` | 0.80 | social | social |
| `suffocating` | 0.80 | effect | effect-functional |
| `territorial` | 0.78 | behaviour | behaviour |
| `insecure` | 0.75 | emotional | emotional |
| `toxic` | 0.75 | social | social |
| `isolating` | 0.72 | effect | effect-functional |
| `obsessive` | 0.70 | behaviour | behaviour |
| `intrusive` | 0.65 | behaviour | behaviour |
| `fearful` | 0.60 | emotional | emotional |

### `flirtation` (synset `11443`) — 10 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `playful` | 0.92 | behaviour | behaviour |
| `suggestive` | 0.85 | behaviour | behaviour |
| `teasing` | 0.85 | behaviour | behaviour |
| `ambiguous` | 0.80 | behaviour | behaviour |
| `alluring` | 0.75 | effect | effect-functional |
| `exciting` | 0.72 | emotional | emotional |
| `charged` | 0.70 | emotional | emotional |
| `performative` | 0.65 | behaviour | behaviour |
| `intimate` | 0.60 | social | social |
| `reciprocal` | 0.60 | social | social |

### `commitment` (synset `22759`) — 11 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `binding` | 0.95 | functional | effect-functional |
| `financial` | 0.95 | functional | effect-functional |
| `contractual` | 0.90 | social | social |
| `obligatory` | 0.90 | functional | effect-functional |
| `formal` | 0.85 | social | social |
| `enforceable` | 0.80 | functional | effect-functional |
| `serious` | 0.75 | emotional | emotional |
| `documented` | 0.70 | functional | effect-functional |
| `irrevocable` | 0.70 | behaviour | behaviour |
| `transactional` | 0.70 | social | social |
| `risky` | 0.65 | effect | effect-functional |

### `separation` (synset `22127`) — 12 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `goodbye` | 1.00 | — | unknown |
| `ritualized` | 1.00 | — | unknown |
| `distance` | 0.90 | physical | physical-other |
| `painful` | 0.85 | emotional | emotional |
| `farewell` | 0.80 | social | social |
| `grief` | 0.75 | emotional | emotional |
| `longing` | 0.75 | emotional | emotional |
| `disruptive` | 0.70 | social | social |
| `bittersweet` | 0.65 | emotional | emotional |
| `rupture` | 0.60 | social | social |
| `transitional` | 0.60 | behaviour | behaviour |
| `voluntary` | 0.45 | behaviour | behaviour |

### `dependency` (synset `78092`) — 9 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `subjugated` | 0.90 | social | social |
| `controlled` | 0.85 | functional | effect-functional |
| `dependent` | 0.85 | social | social |
| `distant` | 0.85 | physical | physical-other |
| `exploited` | 0.80 | effect | effect-functional |
| `administered` | 0.75 | functional | effect-functional |
| `asymmetric` | 0.75 | social | social |
| `marginalised` | 0.70 | social | social |
| `resentful` | 0.65 | emotional | emotional |

### `kinship` (synset `96452`) — 11 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `attractive` | 0.85 | behaviour | behaviour |
| `mutual` | 0.80 | social | social |
| `similar` | 0.80 | functional | effect-functional |
| `bonding` | 0.75 | effect | effect-functional |
| `connective` | 0.75 | functional | effect-functional |
| `natural` | 0.75 | behaviour | behaviour |
| `intuitive` | 0.70 | emotional | emotional |
| `resonant` | 0.70 | emotional | emotional |
| `harmonious` | 0.65 | emotional | emotional |
| `warm` | 0.60 | emotional | sensorimotor |
| `enduring` | 0.55 | behaviour | behaviour |

### `enmity` (synset `97375`) — 11 properties, 3 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `irreconcilable` | 1.00 | — | unknown |
| `bitter` | 0.85 | emotional | sensorimotor |
| `persistent` | 0.85 | behaviour | behaviour |
| `tense` | 0.80 | emotional | sensorimotor |
| `aggressive` | 0.75 | behaviour | behaviour |
| `cold` | 0.75 | emotional | sensorimotor |
| `corrosive` | 0.70 | effect | effect-functional |
| `isolating` | 0.70 | social | social |
| `threatening` | 0.70 | effect | effect-functional |
| `oppressive` | 0.65 | effect | effect-functional |
| `inherited` | 0.45 | social | social |

### `seduction` (synset `3373`) — 12 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `amorous` | 1.00 | — | unknown |
| `courting` | 1.00 | — | unknown |
| `alluring` | 0.90 | emotional | emotional |
| `intimate` | 0.85 | social | social |
| `persuasive` | 0.80 | behaviour | behaviour |
| `charismatic` | 0.75 | social | social |
| `romantic` | 0.75 | emotional | emotional |
| `pleasurable` | 0.70 | emotional | emotional |
| `powerful` | 0.70 | social | social |
| `calculated` | 0.65 | behaviour | behaviour |
| `transgressive` | 0.55 | social | social |
| `asymmetric` | 0.50 | social | social |

### `inspiration` (synset `64071`) — 14 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `flash` | 1.00 | — | unknown |
| `sudden` | 0.95 | behaviour | behaviour |
| `energising` | 0.90 | emotional | emotional |
| `intuitive` | 0.90 | behaviour | behaviour |
| `electric` | 0.85 | physical | physical-other |
| `exciting` | 0.85 | emotional | emotional |
| `illuminating` | 0.85 | effect | effect-functional |
| `brief` | 0.75 | behaviour | behaviour |
| `connecting` | 0.70 | effect | effect-functional |
| `productive` | 0.70 | effect | effect-functional |
| `unforced` | 0.70 | behaviour | behaviour |
| `rare` | 0.65 | physical | physical-other |
| `mysterious` | 0.60 | emotional | emotional |
| `memorable` | 0.55 | effect | effect-functional |

### `melody` (synset `63650`) — 13 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `singable` | 1.00 | — | unknown |
| `pleasant` | 0.90 | emotional | emotional |
| `flowing` | 0.85 | behaviour | behaviour |
| `sequential` | 0.85 | behaviour | behaviour |
| `organised` | 0.80 | functional | effect-functional |
| `satisfying` | 0.80 | emotional | emotional |
| `memorable` | 0.75 | effect | effect-functional |
| `temporal` | 0.75 | physical | physical-other |
| `cohesive` | 0.70 | functional | effect-functional |
| `harmonious` | 0.70 | physical | physical-other |
| `aesthetic` | 0.65 | emotional | emotional |
| `effortless` | 0.60 | behaviour | behaviour |
| `expressive` | 0.60 | emotional | emotional |

### `prose` (synset `66712`) — 12 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `unmetered` | 1.00 | — | unknown |
| `unrhymed` | 0.90 | physical | physical-other |
| `flowing` | 0.85 | behaviour | behaviour |
| `metreless` | 0.85 | physical | physical-other |
| `continuous` | 0.80 | behaviour | behaviour |
| `natural` | 0.80 | physical | physical-other |
| `flexible` | 0.75 | functional | sensorimotor |
| `readable` | 0.70 | functional | effect-functional |
| `versatile` | 0.70 | functional | effect-functional |
| `direct` | 0.65 | behaviour | behaviour |
| `everyday` | 0.60 | social | social |
| `narrative` | 0.60 | functional | effect-functional |

### `rhetoric` (synset `65703`) — 12 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `persuasive` | 0.95 | functional | effect-functional |
| `influential` | 0.85 | effect | effect-functional |
| `strategic` | 0.85 | functional | effect-functional |
| `performative` | 0.80 | behaviour | behaviour |
| `structured` | 0.80 | functional | effect-functional |
| `studied` | 0.75 | functional | effect-functional |
| `vocal` | 0.75 | physical | physical-other |
| `adaptable` | 0.70 | behaviour | behaviour |
| `authoritative` | 0.70 | social | social |
| `ancient` | 0.65 | social | social |
| `empowering` | 0.60 | emotional | emotional |
| `controversial` | 0.55 | social | social |

### `narrative` (synset `11140`) — 11 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `plot-based` | 1.00 | — | unknown |
| `story-driven` | 1.00 | — | unknown |
| `sequential` | 0.90 | behaviour | behaviour |
| `structured` | 0.90 | functional | effect-functional |
| `temporal` | 0.85 | behaviour | behaviour |
| `immersive` | 0.70 | emotional | emotional |
| `purposeful` | 0.70 | functional | effect-functional |
| `engaging` | 0.65 | emotional | emotional |
| `literary` | 0.65 | social | social |
| `interpretive` | 0.55 | functional | effect-functional |
| `descriptive` | 0.50 | functional | effect-functional |

### `satire` (synset `104946`) — 12 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `critical` | 0.95 | functional | effect-functional |
| `humorous` | 0.90 | emotional | emotional |
| `exposing` | 0.85 | effect | effect-functional |
| `subversive` | 0.85 | social | social |
| `exaggerated` | 0.80 | behaviour | behaviour |
| `sharp` | 0.80 | behaviour | sensorimotor |
| `political` | 0.75 | social | social |
| `performative` | 0.70 | functional | effect-functional |
| `literary` | 0.65 | social | social |
| `uncomfortable` | 0.65 | emotional | emotional |
| `cathartic` | 0.60 | emotional | emotional |
| `moralistic` | 0.55 | social | social |

### `tragedy` (synset `70081`) — 1 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `emotionally-intense` | 1.00 | — | unknown |

### `originality` (synset `58950`) — 12 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `novel` | 0.95 | functional | effect-functional |
| `creative` | 0.90 | behaviour | behaviour |
| `authentic` | 0.85 | functional | effect-functional |
| `independent` | 0.80 | behaviour | behaviour |
| `rare` | 0.80 | social | social |
| `pioneering` | 0.75 | functional | effect-functional |
| `surprising` | 0.70 | emotional | emotional |
| `admired` | 0.65 | social | social |
| `influential` | 0.65 | effect | effect-functional |
| `disruptive` | 0.60 | effect | effect-functional |
| `energising` | 0.55 | emotional | emotional |
| `risky` | 0.40 | effect | effect-functional |

### `expression` (synset `68444`) — 13 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `equational` | 1.00 | — | unknown |
| `symbolic` | 0.95 | physical | physical-other |
| `precise` | 0.90 | functional | effect-functional |
| `abstract` | 0.85 | physical | physical-other |
| `compact` | 0.80 | physical | sensorimotor |
| `logical` | 0.80 | functional | effect-functional |
| `structured` | 0.75 | behaviour | behaviour |
| `reusable` | 0.70 | functional | effect-functional |
| `universal` | 0.70 | functional | effect-functional |
| `terse` | 0.65 | physical | physical-other |
| `technical` | 0.60 | social | social |
| `immutable` | 0.55 | behaviour | behaviour |
| `intellectual` | 0.50 | emotional | emotional |

### `improvisation` (synset `2005`) — 12 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `unrehearsed` | 1.00 | — | unknown |
| `spontaneous` | 0.95 | behaviour | behaviour |
| `creative` | 0.85 | behaviour | behaviour |
| `adaptive` | 0.80 | behaviour | behaviour |
| `inventive` | 0.80 | behaviour | behaviour |
| `fluid` | 0.75 | behaviour | behaviour |
| `skilful` | 0.75 | functional | effect-functional |
| `expressive` | 0.70 | emotional | emotional |
| `risky` | 0.70 | effect | effect-functional |
| `unique` | 0.70 | effect | effect-functional |
| `energetic` | 0.65 | behaviour | behaviour |
| `exciting` | 0.65 | emotional | emotional |

### `style` (synset `19391`) — 11 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `identifying` | 0.90 | functional | effect-functional |
| `labelling` | 0.90 | functional | effect-functional |
| `distinguishing` | 0.80 | functional | effect-functional |
| `categorical` | 0.75 | functional | effect-functional |
| `conferring` | 0.70 | behaviour | behaviour |
| `official` | 0.70 | social | social |
| `authoritative` | 0.65 | social | social |
| `clarifying` | 0.65 | effect | effect-functional |
| `symbolic` | 0.60 | effect | effect-functional |
| `permanent` | 0.55 | effect | effect-functional |
| `hierarchical` | 0.50 | social | social |

### `harmony` (synset `97317`) — 12 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `balanced` | 0.90 | physical | physical-other |
| `pleasing` | 0.85 | emotional | emotional |
| `unified` | 0.85 | physical | physical-other |
| `consonant` | 0.80 | physical | physical-other |
| `integrated` | 0.80 | functional | effect-functional |
| `peaceful` | 0.80 | emotional | emotional |
| `coherent` | 0.75 | physical | physical-other |
| `ordered` | 0.75 | physical | physical-other |
| `whole` | 0.75 | physical | physical-other |
| `aesthetic` | 0.70 | emotional | emotional |
| `proportional` | 0.70 | physical | physical-other |
| `resonant` | 0.65 | physical | physical-other |

### `dissonance` (synset `63689`) — 13 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `unmusical` | 1.00 | — | unknown |
| `unpleasant` | 0.95 | emotional | emotional |
| `harsh` | 0.90 | physical | physical-other |
| `chaotic` | 0.85 | behaviour | behaviour |
| `dissonant` | 0.85 | physical | physical-other |
| `jarring` | 0.85 | effect | effect-functional |
| `intrusive` | 0.80 | effect | effect-functional |
| `irregular` | 0.80 | behaviour | behaviour |
| `loud` | 0.75 | physical | sensorimotor |
| `stressful` | 0.75 | emotional | emotional |
| `distracting` | 0.70 | effect | effect-functional |
| `fatiguing` | 0.70 | effect | effect-functional |
| `involuntary` | 0.60 | social | social |

### `masterpiece` (synset `629`) — 12 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `exceptional` | 0.95 | functional | effect-functional |
| `skilful` | 0.90 | functional | effect-functional |
| `celebrated` | 0.85 | social | social |
| `rare` | 0.80 | social | social |
| `inspiring` | 0.75 | emotional | emotional |
| `revered` | 0.75 | social | social |
| `timeless` | 0.75 | effect | effect-functional |
| `definitive` | 0.70 | functional | effect-functional |
| `legacy` | 0.70 | effect | effect-functional |
| `elevated` | 0.65 | social | social |
| `singular` | 0.65 | effect | effect-functional |
| `ambitious` | 0.60 | behaviour | behaviour |

### `artistry` (synset `63267`) — 18 properties, 0 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `mastered` | 0.90 | functional | effect-functional |
| `expert` | 0.85 | social | social |
| `learned` | 0.85 | functional | effect-functional |
| `refined` | 0.85 | behaviour | behaviour |
| `deliberate` | 0.80 | behaviour | behaviour |
| `disciplined` | 0.80 | behaviour | behaviour |
| `precise` | 0.75 | behaviour | behaviour |
| `admirable` | 0.70 | emotional | emotional |
| `effortful` | 0.70 | behaviour | behaviour |
| `elegant` | 0.65 | physical | physical-other |
| `nuanced` | 0.65 | functional | effect-functional |
| `rare` | 0.65 | social | social |
| `earned` | 0.60 | emotional | emotional |
| `intuitive` | 0.60 | behaviour | behaviour |
| `iterative` | 0.60 | behaviour | behaviour |
| `admired` | 0.55 | social | social |
| `prestigious` | 0.55 | social | social |
| `teachable` | 0.50 | functional | effect-functional |

### `language` (synset `63336`) — 17 properties, 1 sensorimotor

| text | salience | LLM type | classification |
|---|---|---|---|
| `expressive` | 0.95 | functional | effect-functional |
| `symbolic` | 0.90 | functional | effect-functional |
| `vocal` | 0.90 | physical | physical-other |
| `social` | 0.85 | social | social |
| `shared` | 0.80 | social | social |
| `universal` | 0.80 | social | social |
| `generative` | 0.75 | functional | effect-functional |
| `innate` | 0.75 | functional | effect-functional |
| `acquired` | 0.70 | functional | effect-functional |
| `developmental` | 0.70 | behaviour | behaviour |
| `powerful` | 0.70 | functional | effect-functional |
| `structured` | 0.70 | behaviour | behaviour |
| `neurological` | 0.65 | physical | physical-other |
| `rapid` | 0.65 | behaviour | sensorimotor |
| `empowering` | 0.60 | emotional | emotional |
| `unconscious` | 0.55 | behaviour | behaviour |
| `fragile` | 0.45 | effect | effect-functional |
