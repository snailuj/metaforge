# M02-S04 — Sonnet vs Haiku enrichment comparison

Same 51 emotion-domain apt-cohort synsets, same `physical → sensorimotor` renamed prompt, same `--batch-size 5`. Only the model differs.

## Aggregate

| metric | sonnet | haiku | Δ |
|---|---|---|---|
| n_synsets | 51 | 51 | +0 |
| total properties | 637 | 690 | +53 |
| avg props/synset | 12.5 | 13.5 | +1.0 |
| sensorimotor tags total | 234 | 277 | +43 |
| sensorimotor per synset | 4.6 | 5.4 | +0.8 |
| sensorimotor % of total | 36.7% | 40.1% | +3.4pp |
| unique-text vocab | 331 | 363 | +32 |
| wall time (s) | 1123 | 716.9 | -406.1 |
| wall time (m:ss) | 18m 43s | 11m 56s | 0.64× |

**Per-synset text-set overlap (Jaccard) between Sonnet and Haiku:** median 0.25, mean 0.26. (1.0 = identical vocabulary on a synset; 0 = no shared texts.)

## Per-synset sensorimotor + total counts

| synset | lemma | s_n | h_n | s_sm | h_sm | sm Δ |
|---|---|---|---|---|---|---|
| 100334 | irritation | 12 | 12 | 7 | 6 | -1 |
| 100401 | vulnerability | 13 | 13 | 5 | 4 | -1 |
| 15373 | anger | 13 | 14 | 4 | 4 | 0 |
| 24456 | melancholy | 13 | 15 | 4 | 5 | +1 |
| 30151 | fear | 12 | 15 | 4 | 6 | +2 |
| 30157 | fear | 12 | 14 | 4 | 6 | +2 |
| 30227 | anger | 12 | 14 | 4 | 5 | +1 |
| 30349 | hurt | 12 | 12 | 5 | 4 | -1 |
| 30810 | hope | 12 | 14 | 5 | 6 | +1 |
| 30821 | envy | 12 | 14 | 4 | 7 | +3 |
| 42988 | go | 12 | 14 | 4 | 5 | +1 |
| 43806 | storm | 12 | 12 | 4 | 5 | +1 |
| 58112 | tenderness | 13 | 13 | 4 | 5 | +1 |
| 58161 | indifference | 13 | 14 | 5 | 5 | 0 |
| 59094 | compassion | 12 | 15 | 5 | 5 | 0 |
| 59234 | courage | 13 | 15 | 4 | 4 | 0 |
| 59481 | quiet | 13 | 11 | 4 | 6 | +2 |
| 59971 | bitter | 12 | 13 | 6 | 7 | +1 |
| 63614 | jealousy | 12 | 13 | 4 | 3 | -1 |
| 64149 | love | 12 | 13 | 4 | 6 | +2 |
| 64235 | joy | 12 | 13 | 5 | 5 | 0 |
| 64254 | grief | 12 | 14 | 5 | 8 | +3 |
| 71602 | shame | 12 | 11 | 4 | 4 | 0 |
| 71623 | humiliation | 12 | 12 | 6 | 4 | -2 |
| 72598 | longing | 14 | 14 | 5 | 4 | -1 |
| 72603 | nostalgia | 13 | 15 | 4 | 5 | +1 |
| 72624 | delight | 12 | 14 | 4 | 4 | 0 |
| 72693 | disgust | 12 | 14 | 4 | 6 | +2 |
| 72700 | gratitude | 12 | 13 | 5 | 4 | -1 |
| 72713 | shame | 14 | 12 | 5 | 8 | +3 |
| 72733 | awe | 13 | 15 | 5 | 6 | +1 |
| 72773 | madness | 12 | 14 | 4 | 4 | 0 |
| 72777 | outrage | 12 | 13 | 5 | 5 | 0 |
| 72785 | harassment | 13 | 13 | 4 | 4 | 0 |
| 72810 | anxiety | 13 | 14 | 4 | 6 | +2 |
| 72829 | lightness | 12 | 14 | 5 | 7 | +2 |
| 72836 | euphoria | 12 | 14 | 4 | 6 | +2 |
| 72848 | contentment | 12 | 15 | 5 | 6 | +1 |
| 72859 | gloom | 12 | 13 | 6 | 7 | +1 |
| 72867 | sorrow | 14 | 12 | 5 | 8 | +3 |
| 72875 | remorse | 13 | 11 | 5 | 6 | +1 |
| 72899 | frustration | 13 | 15 | 5 | 6 | +1 |
| 72905 | despair | 12 | 15 | 5 | 6 | +1 |
| 72913 | love | 13 | 15 | 4 | 5 | +1 |
| 72950 | bitterness | 13 | 10 | 4 | 5 | +1 |
| 97412 | bliss | 13 | 15 | 5 | 7 | +2 |
| 97413 | ecstasy | 12 | 13 | 4 | 6 | +2 |
| 99187 | numbness | 13 | 15 | 5 | 6 | +1 |
| 99192 | suffering | 13 | 14 | 5 | 6 | +1 |
| 99680 | panic | 12 | 13 | 4 | 4 | 0 |

## Side-by-side property dump (first 5 synsets)

### `irritation` (synset `100334`)

**Sonnet properties:**

```
  inflamed           sal=0.90 type=sensorimotor
  raw                sal=0.85 type=sensorimotor
  stinging           sal=0.85 type=sensorimotor
  itchy              sal=0.80 type=sensorimotor
  swollen            sal=0.75 type=sensorimotor
  tender             sal=0.80 type=sensorimotor
  red                sal=0.70 type=sensorimotor
  reactive           sal=0.85 type=behaviour
  persistent         sal=0.70 type=behaviour
  localised          sal=0.65 type=functional
  aggravated         sal=0.75 type=effect
  uncomfortable      sal=0.60 type=emotional
```

**Haiku properties:**

```
  tender             sal=0.90 type=sensorimotor
  raw                sal=0.85 type=sensorimotor
  inflamed           sal=0.90 type=sensorimotor
  stinging           sal=0.85 type=sensorimotor
  burning            sal=0.80 type=sensorimotor
  swollen            sal=0.75 type=sensorimotor
  reactive           sal=0.85 type=behaviour
  heightened         sal=0.80 type=behaviour
  persistent         sal=0.70 type=behaviour
  painful            sal=0.90 type=effect
  protective         sal=0.75 type=functional
  worsening          sal=0.65 type=effect
```

### `vulnerability` (synset `100401`)

**Sonnet properties:**

```
  exposed            sal=0.95 type=sensorimotor
  raw                sal=0.80 type=sensorimotor
  naked              sal=0.75 type=sensorimotor
  trembling          sal=0.65 type=sensorimotor
  soft               sal=0.70 type=sensorimotor
  hesitant           sal=0.70 type=behaviour
  open               sal=0.85 type=functional
  risky              sal=0.80 type=effect
  uncertain          sal=0.75 type=effect
  fearful            sal=0.80 type=emotional
  anxious            sal=0.75 type=emotional
  powerless          sal=0.70 type=emotional
  dependent          sal=0.65 type=social
```

**Haiku properties:**

```
  bare               sal=0.85 type=sensorimotor
  thin               sal=0.80 type=sensorimotor
  transparent        sal=0.75 type=sensorimotor
  fragile            sal=0.80 type=sensorimotor
  trembling          sal=0.70 type=behaviour
  hesitant           sal=0.70 type=behaviour
  withdrawn          sal=0.65 type=behaviour
  undefended         sal=0.85 type=effect
  susceptible        sal=0.80 type=effect
  exposed            sal=0.90 type=effect
  fearful            sal=0.80 type=emotional
  anxious            sal=0.75 type=emotional
  ashamed            sal=0.65 type=emotional
```

### `anger` (synset `15373`)

**Sonnet properties:**

```
  burning            sal=0.95 type=sensorimotor
  hot                sal=0.90 type=sensorimotor
  red                sal=0.80 type=sensorimotor
  seething           sal=0.85 type=sensorimotor
  explosive          sal=0.85 type=behaviour
  escalating         sal=0.80 type=behaviour
  consuming          sal=0.85 type=behaviour
  destructive        sal=0.85 type=effect
  blinding           sal=0.80 type=effect
  righteous          sal=0.75 type=emotional
  overwhelming       sal=0.80 type=emotional
  sinful             sal=0.85 type=social
  feared             sal=0.70 type=social
```

**Haiku properties:**

```
  hot                sal=0.95 type=sensorimotor
  burning            sal=0.90 type=sensorimotor
  sharp              sal=0.80 type=sensorimotor
  intense            sal=0.90 type=sensorimotor
  explosive          sal=0.85 type=behaviour
  rapid              sal=0.80 type=behaviour
  consuming          sal=0.85 type=behaviour
  escalating         sal=0.75 type=behaviour
  destructive        sal=0.85 type=effect
  blinding           sal=0.75 type=effect
  overwhelming       sal=0.80 type=effect
  hostile            sal=0.85 type=emotional
  indignant          sal=0.80 type=emotional
  confrontational    sal=0.75 type=social
```

### `melancholy` (synset `24456`)

**Sonnet properties:**

```
  heavy              sal=0.90 type=sensorimotor
  grey               sal=0.85 type=sensorimotor
  muted              sal=0.80 type=sensorimotor
  still              sal=0.75 type=sensorimotor
  slow               sal=0.80 type=behaviour
  lingering          sal=0.75 type=behaviour
  subdued            sal=0.70 type=behaviour
  isolating          sal=0.65 type=effect
  reflective         sal=0.70 type=effect
  sorrowful          sal=0.90 type=emotional
  wistful            sal=0.75 type=emotional
  pensive            sal=0.70 type=emotional
  poetic             sal=0.50 type=social
```

**Haiku properties:**

```
  grey               sal=0.85 type=sensorimotor
  dim                sal=0.80 type=sensorimotor
  heavy              sal=0.85 type=sensorimotor
  cool               sal=0.65 type=sensorimotor
  muted              sal=0.70 type=sensorimotor
  slow               sal=0.75 type=behaviour
  lingering          sal=0.80 type=behaviour
  downward           sal=0.75 type=behaviour
  inert              sal=0.65 type=behaviour
  draining           sal=0.70 type=effect
  isolating          sal=0.70 type=effect
  sorrowful          sal=0.90 type=emotional
  contemplative      sal=0.75 type=emotional
  resigned           sal=0.60 type=emotional
  withdrawn          sal=0.70 type=social
```

### `fear` (synset `30151`)

**Sonnet properties:**

```
  cold               sal=0.80 type=sensorimotor
  trembling          sal=0.85 type=sensorimotor
  tense              sal=0.90 type=sensorimotor
  sharp              sal=0.70 type=sensorimotor
  freezing           sal=0.80 type=behaviour
  vigilant           sal=0.75 type=behaviour
  paralysing         sal=0.80 type=effect
  draining           sal=0.65 type=effect
  dreadful           sal=0.90 type=emotional
  overwhelming       sal=0.75 type=emotional
  primal             sal=0.60 type=social
  isolating          sal=0.55 type=social
```

**Haiku properties:**

```
  sharp              sal=0.85 type=sensorimotor
  cold               sal=0.80 type=sensorimotor
  trembling          sal=0.80 type=sensorimotor
  tight              sal=0.85 type=sensorimotor
  acute              sal=0.85 type=sensorimotor
  piercing           sal=0.75 type=sensorimotor
  paralyzing         sal=0.85 type=behaviour
  fleeing            sal=0.75 type=behaviour
  vigilant           sal=0.75 type=behaviour
  urgent             sal=0.80 type=behaviour
  overwhelming       sal=0.85 type=effect
  destabilizing      sal=0.75 type=effect
  terrified          sal=0.90 type=emotional
  protective         sal=0.70 type=functional
  communicable       sal=0.65 type=social
```
