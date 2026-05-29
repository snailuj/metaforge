# Captures Inbox

_Loose ideas and observations captured during work. Triage periodically: promote, defer, or discard._

_Migrated from `.gsd/CAPTURES.md` on 2026-05-03 during GSD decommission._


### CAP-b55cb5d1
**Text:** adding CI is probably something we should do sooner than later
**Captured:** 2026-05-02T00:05:05.438Z
**Status:** resolved
**Classification:** defer
**Resolution:** Defer to a dedicated future milestone for CI/CD pipeline setup. Already listed as an MVP-complete requirement in CLAUDE.md.
**Rationale:** CI/CD setup is out of scope for M002 (pipeline memory optimisation). It is its own cross-cutting concern that warrants a dedicated milestone rather than being shoe-horned into the current memory work.
**Resolved:** 2026-05-02T07:11:39.000Z
**Milestone:** M002-kitkng
**Executed:** 2026-05-02T07:12:23.806Z

### CAP-snap-recon
**Text:** Snapping reconciliation + sense-accuracy (DEFERRED — must return soon). The Go `/forge/suggest` endpoint and the Python eval harness sometimes snap the same topic to different synsets (a significant Karpathy-loop deviation source). Separately, polysemy means a lemma can have genuinely different senses; the current `lookup_primary_synset` heuristic (noun-preferred/least-polysemous) fixes coverage but ignores the per-topic `_gloss` and so does not solve sense-accuracy. The gloss (present in `spike_2_topics.json` and the phase2 dumps) is the lever for accurate, gloss-grounded disambiguation. Need a single deterministic snapper shared by Go + Python (or Go accepting a pre-resolved synset_id), gloss-based sense selection, and a re-evaluation of whether prior loop results shift once unified. Stage A handles this minimally (single-source the Python side, flag the cascade-score-sense caveat); full reconciliation is the follow-up.
**Captured:** 2026-05-29
**Status:** open
**Classification:** defer (must return — verify snapping is as tight as realistically possible)
