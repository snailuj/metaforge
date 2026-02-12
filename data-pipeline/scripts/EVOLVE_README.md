# Evolutionary Prompt Optimisation

Search the space of enrichment prompts using evolutionary selection: **explore** with radical mutations, **exploit** survivors with targeted tweaks, all scored by MRR against curated metaphor pairs.

## How It Works

```
Baseline prompt (Variant C)
    │
    ├── Exploration: 5 radically different prompts evaluated
    │   ├── persona_poet    — poetic/sensory vocabulary
    │   ├── contrastive     — discriminative properties
    │   ├── narrative        — embodied/experiential
    │   ├── taxonomic        — systematic dimensional coverage
    │   └── embodied         — multi-sensory (no vision)
    │
    ├── Survivors = valid prompts with MRR > baseline
    │   (invalid trials from infra failures are excluded)
    │
    └── Exploitation: for each survivor
        ├── LLM generates a targeted tweak (exploit_model)
        ├── Prompt improver refines the tweak (improver_model)
        ├── Fixture vocabulary guard rejects leaked test words
        ├── Evaluate tweaked prompt
        ├── Keep if MRR improves, revert if not
        ├── Infra failures don't count toward consecutive failure limit
        └── Repeat until max_tweaks or K consecutive failures
```

Each trial runs the full pipeline: enrich synsets → populate DB → compute IDF → compute similarity → start API → query metaphor pairs → compute MRR.

## Quick Start

```bash
cd data-pipeline

# Check run counts before committing
.venv/bin/python3 scripts/evolve_prompts.py --dry-run

# Run exploration only (6 trials: baseline + 5 prompts)
.venv/bin/python3 scripts/evolve_prompts.py --phase explore --size 700 --port 9091

# Run exploitation on survivors (reads exploration log)
.venv/bin/python3 scripts/evolve_prompts.py --phase exploit --size 700 --port 9091

# Run both phases end-to-end
.venv/bin/python3 scripts/evolve_prompts.py --size 700 --port 9091

# Run with verbose logging to diagnose batch failures
.venv/bin/python3 scripts/evolve_prompts.py --phase explore --size 700 --port 9091 --verbose

# Use a stronger model for tweak generation and prompt improvement
.venv/bin/python3 scripts/evolve_prompts.py --phase exploit --exploit-model sonnet --improver-model sonnet
```

## CLI Reference

```
python evolve_prompts.py [OPTIONS]

Options:
  --model, -m         Claude model for enrichment (default: haiku)
  --size, -s          Synsets to enrich per trial (default: 700)
  --port, -p          API server port (default: 9091)
  --output-dir, -o    Output directory (default: output/evolution/)
  --max-tweaks        Max exploitation tweaks per survivor (default: 7)
  --phase             Run phase: both | explore | exploit (default: both)
  --exploit-model     Model for tweak generation in exploitation (default: haiku)
  --improver-model    Model for prompt improvement stage (default: sonnet)
  --verbose           Enable DEBUG logging for raw LLM request/response
  --dry-run           Print run count estimate and exit
```

## Run Counts

With default settings (5 prompts, 7 max tweaks):

| Phase | Runs |
|-------|:----:|
| Exploration (baseline + 5) | 6 |
| Exploitation (worst case: all 5 survive × 7 tweaks) | 35 |
| **Total (worst case)** | **41** |

In practice, early stopping (K=3 consecutive failures) reduces exploitation runs by 30-50%.

## Output Files

All output goes to `output/evolution/` (or `--output-dir`):

| File | Contents |
|------|----------|
| `exploration_log.json` | Exploration trials (saved after each trial — crash-safe) |
| `exploitation_<name>_log.json` | Exploitation trials per survivor lineage |
| `experiment_log.json` | Complete experiment log (all trials) |

Each trial record contains:

```json
{
  "trial_id": "exploit-contrastive-g2",
  "prompt_name": "contrastive",
  "prompt_text": "...",
  "mrr": 0.18,
  "per_pair": [{"source": "anger", "target": "fire", "rank": 1, ...}],
  "secondary": {"unique_properties": 80, "hapax_rate": 0.56, ...},
  "parent_id": "exploit-contrastive-g1",
  "generation": 2,
  "mutation": "Added emphasis on tactile and thermal properties",
  "survived": true,
  "timestamp": "2026-02-12T10:15:00+00:00",
  "enrichment_coverage": 0.97,
  "valid": true
}
```

## Infrastructure Reliability

### Enrichment Coverage Tracking

`run_enrichment()` returns an `EnrichmentResult` dataclass:

```python
@dataclass
class EnrichmentResult:
    output_file: str
    requested: int
    succeeded: int
    failed: int
    failed_ids: list[str]

    @property
    def coverage(self) -> float:
        return self.succeeded / self.requested if self.requested else 1.0
```

Coverage is checked against a threshold (default 90%). Trials below threshold are marked `valid=False`.

### How Infra Failures Are Handled

- **Exploration:** Invalid trials get `survived=False` regardless of MRR — they are not used for elimination decisions.
- **Exploitation:** Invalid trials don't increment the consecutive failure counter, preventing infra failures from triggering early stop.
- **Reports:** Infrastructure failures are separated from degenerate prompts (MRR=0 with valid enrichment). The exploration results table shows "Infra fail" for affected trials.

### Verbose Logging

Use `--verbose` to capture every CLI interaction at DEBUG level:

- Full prompt sent to Claude CLI (first 500 chars)
- Raw stdout/stderr before parsing
- Parsed result or exception

This makes the 128-batch-failure scenario from the first experiment fully diagnosable.

## Prompt Leakage Prevention

The exploitation pipeline prevents test fixture vocabulary from leaking into generated prompts:

1. **Aggregate-only meta-prompt:** The tweak generator receives hit counts and tier-level rates, not concrete `"anger → fire"` pairs.
2. **Fixture vocabulary guard:** After tweak generation, new words are checked against the fixture vocabulary. Words already in the base prompt are allowed (delta approach avoids false positives on common words like "light").
3. **Second-stage improver:** The raw tweak passes through `improve_prompt()` which applies prompt engineering best practices via a stronger model. This stage explicitly forbids adding example words or domain content.

The exploitation chain is:

```
generate_tweak(exploit_model) → improve_prompt(improver_model) → fixture_guard(vocab) → evaluate
```

## Crash Safety

- Exploration log is saved after **every** trial, not just at the end
- If the process dies mid-exploration, re-run `--phase explore` — it starts from scratch but previous logs are preserved for reference
- Exploitation logs are per-survivor and also saved after each trial
- Use `--phase exploit` to resume exploitation from a completed exploration log

## Usage Exhaustion Handling

If Claude's API rate limit is hit during a trial:

1. The `UsageExhaustedError` surfaces immediately (no wasted retries)
2. The orchestrator saves current state
3. Polls every 5 minutes with a trivial API ping
4. Resumes the current trial once usage renews

## Architecture

```
evolve_prompts.py          Orchestrator: run_exploration → run_exploitation → generate_report
    ├── prompt_templates.py    5 exploration prompts + LLM tweak generator + prompt improver
    ├── evaluate_mrr.py        MRR evaluation with coverage gating
    ├── enrich_properties.py   LLM enrichment with EnrichmentResult + verbose logging
    └── enrich_pipeline.py     Downstream: curate → populate → IDF → similarity → centroids
```

Key features across modules:

- **`enrich_properties.py`** — `EnrichmentResult` dataclass, `UsageExhaustedError`, `prompt_template` param, `verbose` logging
- **`evaluate_mrr.py`** — Coverage gating (`coverage_threshold`), `valid`/`invalid_reason` in results, `verbose` threading
- **`prompt_templates.py`** — Aggregate-only meta-prompt, `improve_prompt()`, `load_fixture_vocabulary()`, fixture guard
- **`evolve_prompts.py`** — `TrialResult` with `enrichment_coverage`/`valid`, infra-aware elimination, `exploit_model`/`improver_model`
- **`generate_evolution_report.py`** — `_infrastructure_failed_trials()`, separate failure cause tracking in briefing

## Tests

```bash
# Run all tests (147 total)
.venv/bin/pytest scripts/ -v

# Run only evolution tests
.venv/bin/pytest scripts/test_evolve_prompts.py scripts/test_prompt_templates.py -v

# Run only the modified module tests
.venv/bin/pytest scripts/test_enrich_properties.py scripts/test_evaluate_mrr.py -v

# Run report generator tests
.venv/bin/pytest scripts/test_generate_evolution_report.py -v
```

All tests are fully mocked — no LLM calls, no real DB, no FastText vectors.

| Test file | Count | Covers |
|-----------|:-----:|--------|
| `test_enrich_properties.py` | 23 | EnrichmentResult, coverage tracking, verbose logging, UsageExhaustedError |
| `test_evaluate_mrr.py` | 18 | Coverage gating, valid/invalid results, prompt_template threading |
| `test_prompt_templates.py` | 17 | Exploration prompts, tweak generator, improver, fixture guard, aggregate meta-prompt |
| `test_evolve_prompts.py` | 23 | TrialResult validity, infra-aware elimination, exploit/improver models, fixture vocab threading |
| `test_generate_evolution_report.py` | 40 | Infra failure separation, legacy compatibility, all report sections |

## Adding New Exploration Prompts

Edit `prompt_templates.py` and add to `EXPLORATION_PROMPTS`:

```python
EXPLORATION_PROMPTS["my_new_approach"] = """Your new prompt here.

Extract 10-15 short (1-2 word) properties per word sense.

CRITICAL: The definition tells you WHICH sense of the word to analyse.

{batch_items}

Output ONLY a valid JSON array (no markdown, no explanation):
[{{"id": "...", "properties": [...]}}, ...]
"""
```

Requirements:
- Must contain `{batch_items}` placeholder
- Must request JSON output format
- Must request 10-15 properties (controlled variable)
- Double all braces that aren't `{batch_items}`: `{{` and `}}`
