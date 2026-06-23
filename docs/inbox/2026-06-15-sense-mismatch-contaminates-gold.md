# Sense-mismatch contaminates the gold labels — a measurement-validity caveat

**Date:** 2026-06-15. **Source:** operator annotations on the rendered judge few-shot examples (`2026-06-12-judge-prompt-templates.md`). Two of his own gold verdicts were graded against a DIFFERENT word-sense than the one the pipeline snapped:

- `ambush → fault`: graded **live** assuming `fault` = *tectonic rupture* (geology). The snapped sense (and the gloss the judge sees) is *"(sports) a serve that is illegal."* Different sense → his "live" is for a pairing the data doesn't represent.
- `longing → heliotrope`: graded **dead** assuming `heliotrope` = *the garden plant that turns its blossoms toward the sun* (a lovely longing image). The snapped sense is *"green chalcedony with red spots"* (the mineral). Operator: *"the mineral sense is actually an interesting pairing I would judge much more highly but I wasn't aware of that meaning."* → his "dead" is for the wrong sense; the recorded edge might actually be **live**.

## Why this is foundational, not cosmetic

1. **The gold corpus is sense-contaminated.** An unknown fraction of labels judge the sense the operator *pictured*, not the `vehicle_synset_id` the edge records. Every κ figure downstream is computed on partly-mismatched labels.
2. **It deflates every κ we've measured — as NOISE, not taste.**
   - Blind self-κ 0.47: on re-grade he may picture a *different* sense than the first pass → inconsistency that is sense-confusion, not taste-inconsistency. True taste-reliability is likely **higher** than 0.47.
   - Judge κ 0.332: see below — the judge may be unfairly penalised.
3. **The judge is MORE sense-disciplined than the gold.** The judge prompt always shows the gloss (`fault (n: (sports) a serve...)`), so the judge judges the *recorded* sense. On the heliotrope row, a sense-grounded judge would weigh the mineral (and might call it live), while the gold says "dead" for the flower the operator imagined. That divergence counts AGAINST the judge's κ even though the judge is arguably the *more correct* grader. **⇒ the true judge quality may be better than 0.332; part of the 0.33→0.47 gap could close just by sense-grounding the gold.**

## The subtle part — "fix" ≠ "snap to the dominant sense"

The interesting metaphor is frequently the *rare* sense (`heliotrope`-mineral ≻ `heliotrope`-flower, per the operator). So a SemCor-tagcount re-snap to the *dominant* sense would actively pick the *worse* metaphor here. Sense is **load-bearing for liveness**, and the right sense is the one that makes the best pairing — not the most frequent. This:
- **confirms the edge must be synset-keyed, not word-keyed** (the same word pair has different liveness by sense) — supports the synset-edge / completion model; word-level completion would be ambiguous.
- argues for **sense-aware grading** (the grader must SEE and grade the actual snapped sense, or flag `wrong_sense` and pick the intended one), possibly **per-sense edges** (one word pair → multiple synset edges, graded independently).

## Remediation options (to discuss / sequence)
- **Grading UX:** make the vehicle (and topic) gloss + an example sentence *unmissable* at grade time — the gloss block exists but the brain still defaults to the common sense. Consider requiring a sense-confirm tap, or showing the gloss adjacent to the verdict buttons.
- **Gold cleaning via the judge:** use the sense-grounded judge to FLAG gold rows where its verdict diverges, surface those to the operator for a sense-check re-grade. The judge becomes a gold-hygiene instrument (turns its "disagreements" into a worklist, not just a κ penalty).
- **Re-grade the known sense-ambiguous few-shot rows** (fault, heliotrope) now — they're poisoning the judge's few-shot examples specifically.
- **Quantify:** sample the gold for vehicles whose snapped sense is NOT the most-frequent sense (these are the high-risk-of-mismatch rows); estimate the contamination fraction.

## Net
This doesn't invalidate the programme — it likely means **the judge and the operator's taste-consistency are both BETTER than measured**, masked by a sense-grounding defect. But it does mean κ figures carry a sense-noise floor we haven't subtracted, and that **sense-grounding the grading is a prerequisite for trusting any κ as a taste measurement.** It also connects to the bad_head endpoint-sense bug (`anger`/`anchor` → verb senses) — same root: the recorded synset is sometimes not the sense in play.
