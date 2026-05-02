---
estimated_steps: 1
estimated_files: 2
skills_used: []
---

# T03: Add threshold guard to cluster_vocab

Add a warning log to cluster_vocab() when any pairwise chunk produces more than 100k above-threshold pairs. This is a canary for threshold misconfiguration that could cause combinatoric explosion. The guard goes inside the inner loop at cluster_vocab.py:137, after the np.where call. TDD: write a test with a low threshold that triggers the warning, assert it was logged.

## Inputs

- `Current inner loop at cluster_vocab.py:123-138`
- `np.where result at lines 132-135`

## Expected Output

- `log.warning when len(rows) > 100_000 in any chunk`
- `Test that triggers the warning with a deliberately low threshold`

## Verification

python -m pytest data-pipeline/scripts/test_cluster_vocab.py -v
