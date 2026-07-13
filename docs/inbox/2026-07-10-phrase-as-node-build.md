# Phrase-as-Node build report + cutover runbook (2026-07-10)

*Autonomous build under the operator's AFK authorisation. Spec `docs/superpowers/specs/2026-07-10-phrase-as-node-design.md` · plan `docs/superpowers/plans/2026-07-10-phrase-as-node.md`.*

## Build outcome — all 10 tasks passed

Workflow `wf_9c31e694-890`: 3 lanes (Sonnet workers → diff-only Sonnet checkers → Opus fixer → Fable judge). 24 agents, ~1.76M tokens, 61 min. 8 tasks first-pass, 2 pass-after-fix (T3 migration summary counter; T7 label coverage on the 3D grade-mode graph nodes), **zero judge escalations**.

| Lane | Branch | HEAD | Suites |
|---|---|---|---|
| W1 pipeline | `metaphor-graph/phrase-as-node` | `4d0a6847` | 282 py green |
| W2 grading | `grading/phrase-as-node` (cherry-picked → `grading-code` @ `a843c6cc`) | `2515d654` | 207 py + vitest + tsc + e2e green |
| W3 harness | `metaphor-graph/judge-harness` | `f62e1d81` | 94 harness green (28 pre-existing DB-vintage import failures, untouched by T10) |

## Migration + validation (real corpus, $0)

`migrate_chain_v2.py` over the 4 canonical chain files (copies in
`data-pipeline/output/pan_migration/`; **grading-data originals untouched**):

- **7,515/7,515** records migrated; signatures byte-preserved; schema-valid.
- **195/195** distinct gold verdict signatures resolve against the v2 corpus.
- **872 steps (2.7%) changed intended sense**, concentrated in **769 chains (10.2%)** — this is the *noun-prior* increment (cross-POS fixes). The June gloss-backfill had already done the token/embed lifting.
- **976 vec: admissions** (steps with no noun-synset candidate — previously bare-lemma fallback snaps or generation drops); **0 low-confidence** snaps.
- Artifacts: `chain-topics_{curated,spike_r1,spike_r2,stock}_v2.jsonl`, `sense_inventories_provisional.jsonl`, `regrade_candidates.jsonl` (27 rows).

## ⚠️ Honest finding — wrong-noun-sense snaps are NOT fixed at snap time

Only **1 of the 27** bad_sense/quarantined gold rows gained a changed step from
migration. The operator's known bad cases (fissure→"explosive sound",
livery→wrong noun sense) are **wrong-NOUN-sense** snaps: the migration re-snaps
from the same stored glosses with the same embed, so only cross-POS errors
moved. For the wrong-noun class the operative fix in this milestone is the
**sense fan** — the operator sees per-hop intended glosses and can tick the
correct sense at grading time, so bad snaps become *correctable signal* (clean
gold + `step_apt_senses`) instead of quarantine losses. Snap-time prevention of
wrong-noun-sense remains partially open; candidate follow-ups if the next batch
misses the ≤10% target: distinctive-token weighting in the embed match, or an
LLM re-snap pass for fan-corrected steps.

## Success criteria posture (measured on the next guided-walk batch, post-cutover)

| Metric | Target | Posture |
|---|---|---|
| bad_sense (incl. interior) | ≤10% | fan-correction + noun-prior + intended-gloss display; wrong-noun caveat above |
| bad_head display-loss | ~0 | phrase-first labels shipped (panel + 3D graph nodes) |
| vehicle-skip in next gen run | 0 | vec: admission shipped in the generation path |
| verdicts resolving | 234 lines / 195 sigs | **195/195 ✓ (pre-cutover)** |
| judge κ | no worse than 0.524 | re-baseline post-cutover (corpus unchanged until then) |

## Cutover runbook (one sitting; needs sudo)

The live tool currently runs old code + v1 files — fully untouched. Cutover order matters:

```bash
# 1. Restart the sidecar FIRST (new code reads v1 AND v2; old code would reject v2 files)
sudo systemctl restart metaforge-grading

# 2. Back up + swap the chain files in grading-data (atomic, canonical names)
GD=/home/agent/projects/metaforge/.worktrees/grading-data/data-pipeline/grading
PM=/home/agent/projects/metaforge/.worktrees/phrase-as-node/data-pipeline/output/pan_migration
mkdir -p $GD/backup_pre_v2_20260710
cp $GD/chain-topics_curated.jsonl $GD/chain-topics_spike_r1.jsonl \
   $GD/chain-topics_spike_r2.jsonl $GD/stock/chain-topics_stock.jsonl \
   $GD/backup_pre_v2_20260710/
cp $PM/chain-topics_curated_v2.jsonl  $GD/chain-topics_curated.jsonl
cp $PM/chain-topics_spike_r1_v2.jsonl $GD/chain-topics_spike_r1.jsonl
cp $PM/chain-topics_spike_r2_v2.jsonl $GD/chain-topics_spike_r2.jsonl
cp $PM/chain-topics_stock_v2.jsonl    $GD/stock/chain-topics_stock.jsonl

# 3. Land the fan's inventory + the re-grade list
cp $PM/sense_inventories_provisional.jsonl $GD/
cp $PM/regrade_candidates.jsonl $GD/

# 4. Rebuild the frontend (Caddy serves dist/ from disk)
cd /home/agent/projects/metaforge/.worktrees/next/web && npm run build

# 5. Hard-refresh the grading tool; verify: phrase-first labels, sense fan opens
#    on a step, glosses render, vec: steps show the no-synset affordance.
```

Rollback: restore `$GD/backup_pre_v2_20260710/*` over the canonical names (the
new sidecar reads v1 fine, no second restart needed).

## Post-cutover follow-ups

1. Re-grade walk over `regrade_candidates.jsonl` (27 rows — recovers quarantined gold).
2. Judge κ sanity re-baseline (gate: no worse than 0.524).
3. Tee up guided-walk batch 4 from the v2 stock corpus → measures the success criteria.
4. `metaphor-graph/schema-base`: apply `docs/designs/2026-07-10-phrase-as-node-ddl.md` at Block 3.
