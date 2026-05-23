# M05 Lakoff γ-Sweep Verdict

> **⚠️ Read this caveat before quoting any number below.**
>
> This grid was regenerated against a DB state where almost no cohort vehicles resolved through the API (`apt_miss ≈ 71–80 / 80`, `inapt_miss = 90 / 90` across every cell). Every cell collapses to `separation_score = 0.0000` because **no inapt pair returned a score for the metric to discriminate against**. The numbers below are not evidence γ has no effect — they are evidence the cohort did not survive the gate/resolution path on this DB state.
>
> The earlier substantive γ-sweep numbers cited elsewhere in the milestone (e.g. `docs/inbox/m05-brainstorming-notes.md:260–269`, showing `separation_score` moving monotonically from -0.2695 at γ=0 to +0.3193 at γ=2) were produced on a different DB state. Treat the brainstorming notes' table as the authoritative directional signal **with the n=1 inapt caveat recorded alongside it** (single inapt survivor → metric is sensitive to which one survived, not to real distributional difference).
>
> Before ratifying any production γ value, the cohort/gate resolution failure must be diagnosed: instrument the sweep driver to tag each drop with its cause (vehicle not in vocab / concreteness gate / no properties / no overlap) so the gap can be interpreted. See `docs/inbox/m05-brainstorming-notes.md` Caveat #3.

_Baseline (cluster_only): separation_score = 0.0000, aptness_rate = 0.0000_

## Results Grid

| Cell | d_min | d_max | gamma | separation_score | aptness_rate | cluster | embedding | both | apt_miss | inapt_miss |
|------|------:|------:|------:|-----------------:|-------------:|--------:|----------:|-----:|---------:|-----------:|
| gamma0.00_dmax0.85 | 0.4 | 0.85 | 0.0 | 0.0000 | 0.0000 | 3 | 0 | 0 | 77 | 90 |
| gamma0.25_dmax0.85 | 0.4 | 0.85 | 0.25 | 0.0000 | 0.0000 | 4 | 0 | 0 | 76 | 90 |
| gamma0.50_dmax0.85 | 0.4 | 0.85 | 0.5 | 0.0000 | 0.0000 | 2 | 0 | 0 | 78 | 90 |
| gamma1.00_dmax0.85 | 0.4 | 0.85 | 1.0 | 0.0000 | 0.0000 | 3 | 0 | 0 | 77 | 90 |
| gamma2.00_dmax0.85 | 0.4 | 0.85 | 2.0 | 0.0000 | 0.0000 | 0 | 0 | 0 | 80 | 90 |
| gamma1.00_dmax0.75 | 0.5 | 0.75 | 1.0 | 0.0000 | 0.0000 | 9 | 0 | 0 | 71 | 90 |

## Best Cell: `gamma0.00_dmax0.85`
- d_min = 0.4, d_max = 0.85, gamma = 0.0
- separation_score = **0.0000**
- aptness_rate = 0.0000
- vs baseline (0.0000): Δ separation_score = +0.0000 (non-regressive)
