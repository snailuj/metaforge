# Gloss-Reconciliation Analysis — subagent flags & snapper vs human sense-gold

*Remediation Block 1. Every metric is computed against the operator's sense-labels, never against the subagent (an unmeasured oracle, demoted to a pre-sorter).*

## Sample
- Raw labels: **128** → distinct endpoints: **121** (4 verdict revisions = changed minds).
- Verdict distribution (deduped): `{'unsure': 11, 'wrong': 41, 'right': 20, 'split': 49}`
- Strata: **88** subagent-flagged, **33** unflagged (random). Unflagged roles: `{'vehicle': 30, 'topic': 3}`.
  - Flagged verdicts: `{'unsure': 10, 'wrong': 37, 'right': 6, 'split': 35}`
  - Unflagged verdicts: `{'right': 14, 'split': 14, 'unsure': 1, 'wrong': 4}`

## Subagent reliability (can the 111-flag worklist drive Endpoint Cleanup?)
- Positive = current snap is WRONG; predicted-positive = subagent flagged. Excluded (unsure / split-without-apt): **21**.
- Confusion: TP 45 · FP 23 · FN 5 · TN 27
- **Precision 66.2%** · **Recall 90.0%** · F1 76.3%

## Silent noise — contamination the subagent MISSED
- Among **32** unflagged determinate endpoints, **5** are WRONG → **15.6%** (Wilson 95% CI [6.9%, 31.8%]).

## Sense promiscuity (single-sense classifier vs sense-SET model)
- Split rate: **49/110 = 44.5%** of determinate labels.
- Poly-apt endpoints (≥2 apt senses): **37**; apt-cardinality distribution `{3: 9, 2: 16, 8: 1, 5: 5, 4: 4, 7: 2, 1: 2}`, mean **3.18** apt senses per split.
- Mean share of a lemma's candidate senses marked apt: **66.6%** (n=39).

## Calibration drift (did ratings move toward Split?)
- First half split rate 31.6% (n=57) → second half 56.9% (n=58); **Δ +25.3pp**.

## Re-snapper baseline (static dominant-SemCor-tagcount prior)
- Scored **100** labels (0 uncovered: target sense absent from the candidate set).
- Current snap accuracy 51.0% → dominant-prior 61.0%.
- Of the **50** wrong snaps, a tagcount prior recovers an apt sense in **22** (**44.0%**). The Gloss-Matched Snapper adds gloss/Lesk WSD on top, so this is a floor, not the ceiling.
