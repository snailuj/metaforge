# M02-S04 — Prompt rename A/B test (physical → sensorimotor)

Test cohort: **['grief', 'love', 'anxiety', 'contentment', 'shame']**. Each word's existing enrichment (under the `physical` prompt) is shown next to a fresh enrichment under the renamed `sensorimotor` prompt. Watch for tag drift on sensorimotor-rooted descriptors (`heavy`, `warm`, `burning`, `bright`, etc.) — these should move from `emotional`/`effect` into `sensorimotor` on the abstract synsets if the rename is doing the work.

## `grief` (synset `64254`)

**Definition:** something that causes great unhappiness

**Existing enrichment (current prompt, `physical` tag):** 0/11 tagged `physical`.

| text | salience | type |
|---|---|---|
| `painful` | 0.95 | effect |
| `devastating` | 0.90 | effect |
| `heavy` | 0.85 | emotional |
| `sorrowful` | 0.85 | emotional |
| `heartbreaking` | 0.80 | emotional |
| `lasting` | 0.75 | behaviour |
| `burdensome` | 0.70 | effect |
| `overwhelming` | 0.70 | effect |
| `tragic` | 0.65 | emotional |
| `inescapable` | 0.60 | behaviour |
| `isolating` | 0.60 | social |

**New enrichment (renamed prompt, `sensorimotor` tag):** 5/13 tagged `sensorimotor`.

| text | salience | type |
|---|---|---|
| `heavy` | 0.90 | sensorimotor 🎯 |
| `dark` | 0.80 | sensorimotor 🎯 |
| `hollow` | 0.75 | sensorimotor 🎯 |
| `cold` | 0.65 | sensorimotor 🎯 |
| `raw` | 0.70 | sensorimotor 🎯 |
| `overwhelming` | 0.85 | behaviour |
| `persistent` | 0.75 | behaviour |
| `consuming` | 0.80 | effect |
| `isolating` | 0.70 | effect |
| `aching` | 0.85 | emotional |
| `oppressive` | 0.70 | emotional |
| `debilitating` | 0.65 | functional |
| `universal` | 0.50 | social |

## `love` (synset `72913`)

**Definition:** a strong positive emotion of regard and affection

**Existing enrichment (current prompt, `physical` tag):** 0/10 tagged `physical`.

| text | salience | type |
|---|---|---|
| `positive` | 0.95 | emotional |
| `warm` | 0.95 | emotional |
| `strong` | 0.90 | emotional |
| `bonding` | 0.85 | effect |
| `enduring` | 0.80 | behaviour |
| `nurturing` | 0.80 | effect |
| `selfless` | 0.75 | behaviour |
| `wholehearted` | 0.75 | emotional |
| `transformative` | 0.70 | effect |
| `universal` | 0.65 | social |

**New enrichment (renamed prompt, `sensorimotor` tag):** 5/15 tagged `sensorimotor`.

| text | salience | type |
|---|---|---|
| `warm` | 0.92 | sensorimotor 🎯 |
| `soft` | 0.78 | sensorimotor 🎯 |
| `radiant` | 0.72 | sensorimotor 🎯 |
| `enveloping` | 0.68 | sensorimotor 🎯 |
| `sweet` | 0.62 | sensorimotor 🎯 |
| `consuming` | 0.82 | behaviour |
| `enduring` | 0.74 | behaviour |
| `yearning` | 0.70 | behaviour |
| `bonding` | 0.88 | effect |
| `transformative` | 0.72 | effect |
| `joyful` | 0.86 | emotional |
| `tender` | 0.82 | emotional |
| `vulnerable` | 0.66 | emotional |
| `nurturing` | 0.76 | functional |
| `universal` | 0.60 | social |

## `anxiety` (synset `72810`)

**Definition:** a vague unpleasant emotion that is experienced in anticipation of some (usually ill-defined) misfortune

**Existing enrichment (current prompt, `physical` tag):** 0/0 tagged `physical`.

| text | salience | type |
|---|---|---|

**New enrichment (renamed prompt, `sensorimotor` tag):** 6/15 tagged `sensorimotor`.

| text | salience | type |
|---|---|---|
| `constricting` | 0.85 | sensorimotor 🎯 |
| `hollow` | 0.75 | sensorimotor 🎯 |
| `breathless` | 0.70 | sensorimotor 🎯 |
| `trembling` | 0.65 | sensorimotor 🎯 |
| `clammy` | 0.60 | sensorimotor 🎯 |
| `shadowy` | 0.50 | sensorimotor 🎯 |
| `spiralling` | 0.80 | behaviour |
| `restless` | 0.70 | behaviour |
| `relentless` | 0.65 | behaviour |
| `paralysing` | 0.70 | effect |
| `consuming` | 0.65 | effect |
| `unsettling` | 0.85 | emotional |
| `ominous` | 0.80 | emotional |
| `anticipatory` | 0.80 | functional |
| `isolating` | 0.55 | social |

## `contentment` (synset `72848`)

**Definition:** happiness with one's situation in life

**Existing enrichment (current prompt, `physical` tag):** 0/0 tagged `physical`.

| text | salience | type |
|---|---|---|

**New enrichment (renamed prompt, `sensorimotor` tag):** 5/14 tagged `sensorimotor`.

| text | salience | type |
|---|---|---|
| `warm` | 0.80 | sensorimotor 🎯 |
| `full` | 0.80 | sensorimotor 🎯 |
| `still` | 0.70 | sensorimotor 🎯 |
| `soft` | 0.65 | sensorimotor 🎯 |
| `quiet` | 0.60 | sensorimotor 🎯 |
| `settled` | 0.75 | behaviour |
| `steady` | 0.70 | behaviour |
| `unhurried` | 0.55 | behaviour |
| `peaceful` | 0.85 | emotional |
| `accepting` | 0.75 | emotional |
| `calming` | 0.70 | effect |
| `grounding` | 0.65 | effect |
| `sustaining` | 0.55 | functional |
| `modest` | 0.45 | social |

## `shame` (synset `72713`)

**Definition:** a painful emotion resulting from an awareness of inadequacy or guilt

**Existing enrichment (current prompt, `physical` tag):** 0/0 tagged `physical`.

| text | salience | type |
|---|---|---|

**New enrichment (renamed prompt, `sensorimotor` tag):** 5/15 tagged `sensorimotor`.

| text | salience | type |
|---|---|---|
| `burning` | 0.85 | sensorimotor 🎯 |
| `heavy` | 0.80 | sensorimotor 🎯 |
| `sinking` | 0.75 | sensorimotor 🎯 |
| `suffocating` | 0.65 | sensorimotor 🎯 |
| `flushing` | 0.70 | sensorimotor 🎯 |
| `shrinking` | 0.80 | behaviour |
| `avoidant` | 0.75 | behaviour |
| `paralyzing` | 0.60 | behaviour |
| `isolating` | 0.70 | effect |
| `silencing` | 0.65 | effect |
| `excruciating` | 0.85 | emotional |
| `crushing` | 0.75 | emotional |
| `humiliating` | 0.90 | emotional |
| `exposing` | 0.70 | social |
| `stigmatising` | 0.55 | social |

## A/B Summary

| word | existing `physical` count | new `sensorimotor` count | delta |
|---|---|---|---|
| `grief` | 0 | 5 | +5 |
| `love` | 0 | 5 | +5 |
| `anxiety` | 0 | 6 | +6 |
| `contentment` | 0 | 5 | +5 |
| `shame` | 0 | 5 | +5 |

**Verdict heuristics:**
- If the rename consistently shifts sensorimotor-rooted descriptors (`heavy`, `warm`, `burning`, `bright`) into the `sensorimotor` tag where they were `emotional`/`effect` before, the conflation was the binding bug.
- If new sensorimotor counts are still ≪ 4 across the cohort, the rename alone wasn't enough — escalate to the tagging-disambiguation clarification or the count drop.
- If counts swing wildly or quality regresses, the rename destabilised the prompt — revert and try a softer change.