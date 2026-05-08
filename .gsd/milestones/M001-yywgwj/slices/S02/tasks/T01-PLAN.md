---
estimated_steps: 8
estimated_files: 2
skills_used: []
---

# T01: Make evaluate_aptness.py scoring formula pluggable via a registry

Refactor `evaluate_aptness.py` so the scoring function is selected via a named registry rather than being hard-coded as salience-weighted Jaccard. This is the prerequisite for the sweep harness — without a pluggable scoring interface there is nothing meaningful to sweep over.

Add a `SCORING_FNS` dict mapping a string name → a callable with signature `(pa: dict[int,float], pb: dict[int,float]) -> float` where `pa`/`pb` are `{cluster_id: salience_sum}` mappings (the existing internal shape). Register at minimum:
- `jaccard_salience` (current behaviour — salience-weighted Jaccard, becomes the default)
- `jaccard_raw` (unweighted set-Jaccard over shared cluster_ids — control for whether salience weighting helps)
- `cosine_salience` (cosine similarity over the salience vectors aligned by cluster_id)

Thread the chosen scoring function through `score_pair()` and `evaluate()`. Add a `--scoring NAME` CLI flag (default `jaccard_salience`) and record the chosen name + threshold_percentile in the output's `config` block. The PairScore status semantics (`scored`/`unresolved`/`no_properties`) MUST be preserved unchanged — a scoring formula that returns 0.0 is still `scored`, distinct from a coverage gap.

Add unit tests: at least one focused test per registered scoring function exercising a known-overlap case + a no-overlap case + a salience-asymmetric case. Use the existing in-memory SQLite fixture pattern from `test_evaluate_aptness.py`. Verify CLI dispatch by invoking `main()` with a controlled sys.argv via `monkeypatch`.

Note (autonomous-mode assumption): registry keys live in lowercase snake_case; cosine over salience vectors uses zero-padding for cluster_ids missing from one side (standard sparse-cosine convention). Document both in the module docstring.

## Inputs

- ``data-pipeline/scripts/evaluate_aptness.py``
- ``data-pipeline/scripts/test_evaluate_aptness.py``
- ``data-pipeline/output/lexicon_v2.db``

## Expected Output

- ``data-pipeline/scripts/evaluate_aptness.py` — adds SCORING_FNS registry, --scoring CLI flag, scoring name in output config`
- ``data-pipeline/scripts/test_evaluate_aptness.py` — adds tests for each registered scoring function`

## Verification

source .venv/bin/activate && python -m pytest data-pipeline/scripts/test_evaluate_aptness.py -v && python data-pipeline/scripts/evaluate_aptness.py --scoring jaccard_raw --db data-pipeline/output/lexicon_v2.db --output /tmp/aptness_jaccard_raw.json && grep -q '"scoring":' /tmp/aptness_jaccard_raw.json
