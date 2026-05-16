# M02-S04 — Prompt rename A/B test (multi-domain: body, society, relationship)

Test cohort: **['blood', 'bone', 'fist', 'authority', 'censorship', 'bureaucracy', 'betrayal', 'devotion', 'enmity']**. Each word's existing enrichment (under the `physical` prompt) is shown next to a fresh enrichment under the renamed `sensorimotor` prompt. Watch for tag drift on sensorimotor-rooted descriptors (`heavy`, `warm`, `burning`, `bright`, etc.) — these should move from `emotional`/`effect` into `sensorimotor` on the abstract synsets if the rename is doing the work.

## `blood` (synset `58122`, domain=body)

**Definition:** temperament or disposition

**Existing enrichment (current prompt, `physical` tag):** 2/17 tagged `physical`.

| text | salience | type |
|---|---|---|
| `innate` | 0.90 | functional |
| `deep` | 0.85 | physical 🎯 |
| `defining` | 0.80 | functional |
| `hereditary` | 0.80 | social |
| `inherited` | 0.80 | social |
| `ancestral` | 0.75 | social |
| `constitutional` | 0.75 | functional |
| `essential` | 0.75 | functional |
| `passionate` | 0.70 | emotional |
| `unchangeable` | 0.70 | behaviour |
| `visceral` | 0.70 | emotional |
| `vital` | 0.70 | physical 🎯 |
| `volatile` | 0.70 | behaviour |
| `flowing` | 0.65 | behaviour |
| `primal` | 0.65 | emotional |
| `unalterable` | 0.60 | effect |
| `energising` | 0.50 | effect |

**New enrichment (renamed prompt, `sensorimotor` tag):** 4/14 tagged `sensorimotor`.

| text | salience | type |
|---|---|---|
| `warm` | 0.75 | sensorimotor 🎯 |
| `pulsing` | 0.65 | sensorimotor 🎯 |
| `viscous` | 0.45 | sensorimotor 🎯 |
| `crimson` | 0.55 | sensorimotor 🎯 |
| `inherited` | 0.85 | behaviour |
| `persistent` | 0.70 | behaviour |
| `volatile` | 0.50 | behaviour |
| `defining` | 0.80 | effect |
| `inescapable` | 0.70 | effect |
| `motivating` | 0.75 | functional |
| `passionate` | 0.80 | emotional |
| `primal` | 0.70 | emotional |
| `ancestral` | 0.75 | social |
| `familial` | 0.65 | social |

## `bone` (synset `6507`, domain=body)

**Definition:** consisting of or made up of bone

**Existing enrichment (current prompt, `physical` tag):** 10/12 tagged `physical`.

| text | salience | type |
|---|---|---|
| `hard` | 0.95 | physical 🎯 |
| `rigid` | 0.90 | physical 🎯 |
| `dense` | 0.85 | physical 🎯 |
| `calcified` | 0.80 | physical 🎯 |
| `pale` | 0.80 | physical 🎯 |
| `durable` | 0.75 | physical 🎯 |
| `structural` | 0.75 | functional |
| `smooth` | 0.70 | physical 🎯 |
| `organic` | 0.60 | physical 🎯 |
| `porous` | 0.55 | physical 🎯 |
| `tactile` | 0.50 | physical 🎯 |
| `carved` | 0.40 | social |

**New enrichment (renamed prompt, `sensorimotor` tag):** 7/15 tagged `sensorimotor`.

| text | salience | type |
|---|---|---|
| `hard` | 0.95 | sensorimotor 🎯 |
| `smooth` | 0.80 | sensorimotor 🎯 |
| `dense` | 0.85 | sensorimotor 🎯 |
| `ivory` | 0.75 | sensorimotor 🎯 |
| `rigid` | 0.85 | sensorimotor 🎯 |
| `porous` | 0.60 | sensorimotor 🎯 |
| `calcified` | 0.65 | sensorimotor 🎯 |
| `brittle` | 0.65 | behaviour |
| `structural` | 0.90 | functional |
| `protective` | 0.75 | functional |
| `durable` | 0.70 | effect |
| `anchoring` | 0.60 | functional |
| `morbid` | 0.55 | emotional |
| `primal` | 0.45 | emotional |
| `ceremonial` | 0.35 | social |

## `fist` (synset `62872`, domain=body)

**Definition:** a hand with the fingers clenched in the palm (as for hitting)

**Existing enrichment (current prompt, `physical` tag):** 6/12 tagged `physical`.

| text | salience | type |
|---|---|---|
| `clenched` | 0.95 | physical 🎯 |
| `hard` | 0.90 | physical 🎯 |
| `striking` | 0.90 | functional |
| `compact` | 0.85 | physical 🎯 |
| `powerful` | 0.85 | effect |
| `aggressive` | 0.80 | behaviour |
| `threatening` | 0.80 | emotional |
| `tense` | 0.75 | physical 🎯 |
| `knuckled` | 0.70 | physical 🎯 |
| `blunt` | 0.65 | physical 🎯 |
| `dominant` | 0.60 | social |
| `defiant` | 0.55 | emotional |

**New enrichment (renamed prompt, `sensorimotor` tag):** 5/12 tagged `sensorimotor`.

| text | salience | type |
|---|---|---|
| `hard` | 0.90 | sensorimotor 🎯 |
| `compact` | 0.85 | sensorimotor 🎯 |
| `bony` | 0.75 | sensorimotor 🎯 |
| `tense` | 0.80 | sensorimotor 🎯 |
| `rigid` | 0.75 | sensorimotor 🎯 |
| `forceful` | 0.85 | behaviour |
| `sudden` | 0.50 | behaviour |
| `crushing` | 0.70 | effect |
| `bruising` | 0.65 | effect |
| `aggressive` | 0.80 | emotional |
| `threatening` | 0.75 | social |
| `defiant` | 0.60 | social |

## `authority` (synset `66900`, domain=society)

**Definition:** an authoritative written work

**Existing enrichment (current prompt, `physical` tag):** 2/11 tagged `physical`.

| text | salience | type |
|---|---|---|
| `definitive` | 0.95 | functional |
| `respected` | 0.85 | social |
| `trustworthy` | 0.85 | emotional |
| `canonical` | 0.80 | social |
| `influential` | 0.80 | effect |
| `scholarly` | 0.80 | social |
| `cited` | 0.75 | behaviour |
| `comprehensive` | 0.75 | physical 🎯 |
| `formal` | 0.70 | social |
| `weighty` | 0.65 | physical 🎯 |
| `enduring` | 0.60 | effect |

**New enrichment (renamed prompt, `sensorimotor` tag):** 5/14 tagged `sensorimotor`.

| text | salience | type |
|---|---|---|
| `dense` | 0.80 | sensorimotor 🎯 |
| `heavy` | 0.65 | sensorimotor 🎯 |
| `worn` | 0.50 | sensorimotor 🎯 |
| `yellowed` | 0.40 | sensorimotor 🎯 |
| `printed` | 0.55 | sensorimotor 🎯 |
| `definitive` | 0.95 | functional |
| `exhaustive` | 0.75 | functional |
| `cited` | 0.85 | behaviour |
| `enduring` | 0.70 | behaviour |
| `legitimising` | 0.80 | effect |
| `canonical` | 0.90 | social |
| `prestigious` | 0.70 | social |
| `trustworthy` | 0.85 | emotional |
| `intimidating` | 0.50 | emotional |

## `censorship` (synset `16271`, domain=society)

**Definition:** counterintelligence achieved by banning or deleting any information of value to the enemy

**Existing enrichment (current prompt, `physical` tag):** 0/13 tagged `physical`.

| text | salience | type |
|---|---|---|
| `sanitizing` | 1.00 | — |
| `suppressive` | 0.92 | behaviour |
| `controlling` | 0.88 | behaviour |
| `restrictive` | 0.85 | effect |
| `protective` | 0.80 | functional |
| `redacting` | 0.78 | behaviour |
| `authoritative` | 0.75 | social |
| `wartime` | 0.72 | social |
| `preventive` | 0.70 | functional |
| `covert` | 0.65 | behaviour |
| `deliberate` | 0.65 | behaviour |
| `bureaucratic` | 0.60 | social |
| `intrusive` | 0.60 | emotional |

**New enrichment (renamed prompt, `sensorimotor` tag):** 5/14 tagged `sensorimotor`.

| text | salience | type |
|---|---|---|
| `concealing` | 0.90 | functional |
| `silent` | 0.85 | sensorimotor 🎯 |
| `blank` | 0.75 | sensorimotor 🎯 |
| `dark` | 0.65 | sensorimotor 🎯 |
| `muted` | 0.60 | sensorimotor 🎯 |
| `sharp` | 0.45 | sensorimotor 🎯 |
| `systematic` | 0.75 | behaviour |
| `surgical` | 0.60 | behaviour |
| `protective` | 0.85 | functional |
| `covert` | 0.65 | functional |
| `blinding` | 0.75 | effect |
| `preventive` | 0.70 | effect |
| `authoritative` | 0.70 | social |
| `oppressive` | 0.55 | emotional |

## `bureaucracy` (synset `75923`, domain=society)

**Definition:** a government that is administered primarily by bureaus that are staffed with nonelective officials

**Existing enrichment (current prompt, `physical` tag):** 0/12 tagged `physical`.

| text | salience | type |
|---|---|---|
| `departmentalized` | 1.00 | — |
| `process-driven` | 1.00 | — |
| `administrative` | 0.90 | functional |
| `appointed` | 0.90 | social |
| `hierarchical` | 0.85 | social |
| `structured` | 0.85 | functional |
| `formal` | 0.80 | social |
| `impersonal` | 0.75 | social |
| `specialised` | 0.70 | functional |
| `stable` | 0.70 | behaviour |
| `powerful` | 0.65 | social |
| `distant` | 0.60 | emotional |

**New enrichment (renamed prompt, `sensorimotor` tag):** 5/15 tagged `sensorimotor`.

| text | salience | type |
|---|---|---|
| `slow` | 0.90 | behaviour |
| `rigid` | 0.85 | behaviour |
| `hierarchical` | 0.90 | social |
| `impersonal` | 0.85 | emotional |
| `frustrating` | 0.85 | emotional |
| `obstructive` | 0.80 | effect |
| `dense` | 0.75 | sensorimotor 🎯 |
| `ponderous` | 0.70 | sensorimotor 🎯 |
| `grey` | 0.65 | sensorimotor 🎯 |
| `stifling` | 0.70 | sensorimotor 🎯 |
| `cold` | 0.65 | sensorimotor 🎯 |
| `grinding` | 0.70 | behaviour |
| `entrenched` | 0.75 | social |
| `opaque` | 0.70 | functional |
| `repetitive` | 0.60 | behaviour |

## `betrayal` (synset `59350`, domain=relationship)

**Definition:** the quality of aiding an enemy

**Existing enrichment (current prompt, `physical` tag):** 0/12 tagged `physical`.

| text | salience | type |
|---|---|---|
| `perfidious` | 1.00 | — |
| `treacherous` | 0.95 | behaviour |
| `damaging` | 0.90 | effect |
| `harmful` | 0.88 | effect |
| `condemned` | 0.85 | social |
| `shocking` | 0.82 | emotional |
| `shameful` | 0.80 | social |
| `secretive` | 0.78 | behaviour |
| `distrustful` | 0.75 | social |
| `dangerous` | 0.72 | effect |
| `irreversible` | 0.70 | effect |
| `calculated` | 0.65 | behaviour |

**New enrichment (renamed prompt, `sensorimotor` tag):** 4/14 tagged `sensorimotor`.

| text | salience | type |
|---|---|---|
| `bitter` | 0.85 | sensorimotor 🎯 |
| `cold` | 0.80 | sensorimotor 🎯 |
| `sharp` | 0.75 | sensorimotor 🎯 |
| `corrosive` | 0.70 | sensorimotor 🎯 |
| `covert` | 0.90 | behaviour |
| `calculated` | 0.80 | behaviour |
| `subversive` | 0.75 | behaviour |
| `devastating` | 0.90 | effect |
| `destabilising` | 0.80 | effect |
| `isolating` | 0.65 | effect |
| `painful` | 0.85 | emotional |
| `shocking` | 0.70 | emotional |
| `shameful` | 0.85 | social |
| `treacherous` | 0.80 | social |

## `devotion` (synset `19623`, domain=relationship)

**Definition:** (usually plural) religious observance or prayers (usually spoken silently)

**Existing enrichment (current prompt, `physical` tag):** 0/11 tagged `physical`.

| text | salience | type |
|---|---|---|
| `reverent` | 0.85 | emotional |
| `silent` | 0.85 | behaviour |
| `meditative` | 0.80 | behaviour |
| `private` | 0.75 | social |
| `humbling` | 0.70 | emotional |
| `rhythmic` | 0.70 | behaviour |
| `peaceful` | 0.65 | emotional |
| `repetitive` | 0.65 | behaviour |
| `focused` | 0.60 | behaviour |
| `ritualistic` | 0.60 | social |
| `grounding` | 0.50 | emotional |

**New enrichment (renamed prompt, `sensorimotor` tag):** 5/15 tagged `sensorimotor`.

| text | salience | type |
|---|---|---|
| `hushed` | 0.85 | sensorimotor 🎯 |
| `kneeling` | 0.75 | sensorimotor 🎯 |
| `bowed` | 0.70 | sensorimotor 🎯 |
| `still` | 0.60 | sensorimotor 🎯 |
| `dim` | 0.40 | sensorimotor 🎯 |
| `repetitive` | 0.70 | behaviour |
| `rhythmic` | 0.60 | behaviour |
| `reverent` | 0.85 | emotional |
| `earnest` | 0.80 | emotional |
| `humble` | 0.75 | emotional |
| `contemplative` | 0.65 | functional |
| `calming` | 0.65 | effect |
| `sacred` | 0.80 | social |
| `private` | 0.70 | social |
| `traditional` | 0.50 | social |

## `enmity` (synset `97375`, domain=relationship)

**Definition:** a state of deep-seated ill-will

**Existing enrichment (current prompt, `physical` tag):** 0/11 tagged `physical`.

| text | salience | type |
|---|---|---|
| `irreconcilable` | 1.00 | — |
| `bitter` | 0.85 | emotional |
| `persistent` | 0.85 | behaviour |
| `tense` | 0.80 | emotional |
| `aggressive` | 0.75 | behaviour |
| `cold` | 0.75 | emotional |
| `corrosive` | 0.70 | effect |
| `isolating` | 0.70 | social |
| `threatening` | 0.70 | effect |
| `oppressive` | 0.65 | effect |
| `inherited` | 0.45 | social |

**New enrichment (renamed prompt, `sensorimotor` tag):** 5/14 tagged `sensorimotor`.

| text | salience | type |
|---|---|---|
| `cold` | 0.82 | sensorimotor 🎯 |
| `heavy` | 0.72 | sensorimotor 🎯 |
| `sharp` | 0.78 | sensorimotor 🎯 |
| `dark` | 0.68 | sensorimotor 🎯 |
| `tense` | 0.85 | sensorimotor 🎯 |
| `smouldering` | 0.80 | behaviour |
| `festering` | 0.74 | behaviour |
| `persistent` | 0.76 | behaviour |
| `corrosive` | 0.82 | effect |
| `alienating` | 0.78 | effect |
| `threatening` | 0.88 | emotional |
| `oppressive` | 0.80 | emotional |
| `divisive` | 0.75 | social |
| `defensive` | 0.60 | functional |

## A/B Summary

| word | domain | existing total/`physical` | new total/`sensorimotor` | delta |
|---|---|---|---|---|
| `blood` | body | 17/2 | 14/4 | +2 |
| `bone` | body | 12/10 | 15/7 | -3 |
| `fist` | body | 12/6 | 12/5 | -1 |
| `authority` | society | 11/2 | 14/5 | +3 |
| `censorship` | society | 13/0 | 14/5 | +5 |
| `bureaucracy` | society | 12/0 | 15/5 | +5 |
| `betrayal` | relationship | 12/0 | 14/4 | +4 |
| `devotion` | relationship | 11/0 | 15/5 | +5 |
| `enmity` | relationship | 11/0 | 14/5 | +5 |

**Verdict heuristics:**
- If the rename consistently shifts sensorimotor-rooted descriptors (`heavy`, `warm`, `burning`, `bright`) into the `sensorimotor` tag where they were `emotional`/`effect` before, the conflation was the binding bug.
- If new sensorimotor counts are still ≪ 4 across the cohort, the rename alone wasn't enough — escalate to the tagging-disambiguation clarification or the count drop.
- If counts swing wildly or quality regresses, the rename destabilised the prompt — revert and try a softer change.