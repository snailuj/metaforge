# M002-kitkng: Pipeline Memory Optimisation

**Vision:** Reduce data-pipeline peak memory from ~11 GB to under 2 GB so the enrichment pipeline runs comfortably on the 3.9 GB VPS without swap-thrashing. Fixes the critical FastText loader representation, eliminates redundant vector loads, and streams large result sets instead of materialising them.

## Success Criteria

- Pipeline completes enrichment run with peak RSS under 2 GB (measured via /usr/bin/time -v or psutil)
- All existing data-pipeline tests pass after refactor
- FastText vectors stored as numpy float32 matrix, not Python tuples
- No double-load of FastText vectors across pipeline stages
- snap_properties streams rows via cursor instead of full materialisation
- cluster_vocab logs a warning when pairwise chunk exceeds 100k pairs

## Slices

- [x] **S01: S01** `risk:high` `depends:[]`
  > After this: Pipeline loads FastText vectors in ~1.2 GB RSS instead of ~11 GB. All tests pass.

- [ ] **S02: Pipeline memory streamlining** `risk:medium` `depends:[S01]`
  > After this: Pipeline runs without 294 MB snap_properties spike, without double FastText load, and cluster_vocab warns on excessive pair counts.

## Boundary Map

Not provided.
