# M001-yywgwj: Automated Eval Harness

**Vision:** Replace MRR as the primary forge algorithm KPI with a discriminative aptness evaluator and automated parameter sweep, enabling algorithm research at the speed of hypothesis → sweep → evidence → commit. Once this milestone is complete, every subsequent algorithm change (M2–M5) can be validated in minutes, not hours.

## Success Criteria

- Discriminative aptness evaluator separates gold-standard pairs from inapt controls with >0.3 separation score
- Parameter sweep completes a 10-point grid in under 30 minutes
- Baseline metrics recorded for current algorithm (MRR + aptness rate + separation score)
- MRR retained as secondary regression metric alongside new primary KPIs
- V2 enrichment data (10,530 synsets) imported and accessible via forge API

## Slices

- [ ] **S01: V2 Foundation + Aptness Evaluator** `risk:medium` `depends:[]`
  > After this: Run aptness evaluator on 50 known-good pairs + 50 MUNCH inapt controls, display per-pair scores and aggregate separation statistics alongside V2 baseline MRR

- [ ] **S02: Parameter Sweep Harness** `risk:low` `depends:[S01]`
  > After this: Run sweep with 3 scoring parameter variations, show ranked comparison table with aptness rate + MRR + separation score for each

- [ ] **S03: Baseline and Sensitivity Validation** `risk:low` `depends:[S02]`
  > After this: Show baseline metrics for current algorithm alongside metrics from deliberately degraded parameters, confirming the harness detects the difference

- [ ] **S04: Baseline and Sensitivity Validation** `risk:low` `depends:[S03]`
  > After this: Show baseline metrics for current algorithm alongside metrics from deliberately degraded parameters, confirming the harness detects the difference

## Boundary Map

Not provided.
