# Phrase-as-Node — design spec (Block 2)

*Status: operator-approved design, 2026-07-10 (brainstorm session; all forks resolved with Julian).*
*Design brief: `docs/designs/phrase-as-node-prototype.md` · UI-side spec (deferred): `docs/designs/2026-06-25-graph-native-feature-specs.md` §D.*
*Supersedes: the standalone snapper fix (task #19 pre-fold; `dominant_sense_prior.choose_sense` on `generation/snapper-sense-prior` is reused as a building block).*

## 1. Problem

Every node in the metaphor pipeline is a single-word WordNet synset. That one
representational choice is the measured root of three defect classes (batch-3
guided-walk evidence, 2026-07-08):

- **`bad_sense` 33%** of fresh stock candidates (was 62% pre-endpoint-filter;
  residual is 100% interior-hop — an endpoint filter structurally cannot reach it).
- **`bad_head` 25%** — a multi-word phrase impoverished to its head noun
  (`buried wound → wound`); the modifier that carried the metaphor is lost.
- **Vehicle-skip ~3.5%** — multi-word/OOV vehicles (`pressed flower`) dropped
  at generation because `ChainRecord.vehicle_synset_id` is a required field.

The same sense-noise contaminates the grading gold and caps the liveness judge
(κ 0.524 out-of-sample ≈ the gold-noise ceiling; judge tuning is paused).

## 2. Contract (operator-resolved forks)

All four forks were resolved explicitly with the operator on 2026-07-10:

1. **Scope = pipeline + grading tool.** Public-surface UI (phrase pills, sense
   orbits) is out of scope, gated on the cinematic-base spike.
2. **Node = phrase + sense inventory; apt-set is per-OCCURRENCE.** The node
   carries its context-free sense inventory; each *occurrence* of a node in a
   chain carries its own apt sense-subset. A global apt-set would re-introduce
   the collapse (forcing `glance` to have identical live senses in every chain).
3. **vec: nodes anywhere, gated.** A no-synset phrase is a first-class node at
   any chain position (endpoint or intermediate hop). Admission gate: vec: only
   when **neither the full phrase nor its head lemma has any noun-synset
   candidate** in WordNet (multi-word/OOV) — never as a low-confidence escape
   hatch. Every admission
   is logged. A failed snap that fails the gate is recorded flagged, never
   silently dropped.
4. **Verdict grain = the intended path.** A chain with per-hop sense-sets is a
   *lattice* of sense-resolved chains. A verdict asserts liveness of the
   **intended sense-path only** — the emit-the-sense gloss-match per hop, the
   reading the operator actually experiences. Operator **ticks** assert *local
   co-aptness* ("this sense ALSO fits at this position"), not fully-judged
   paths. Sibling paths are **derived, discounted, provenance-tagged** —
   completion (Block 3) may expand a judged-live path to co-apt siblings as
   weak positives. **Record the judged/derived provenance distinction now;
   defer all weighting to Block 3.** Ticks are optional: a verdict with zero
   ticks is fully valid, it just yields no siblings.

## 3. Record schema — `chain.v2` (JSONL; SQL follows at Block 3)

Approach A (operator-confirmed): the contract lands in the JSONL record shape
where the chains live; SQLite materialisation is *designed* (§8) but not built.

### 3.1 ChainStep v2 (additive over v1)

```jsonc
{
  "phrase": "buried wound",          // v1 field, now load-bearing (never impoverished)
  "head": "wound",                   // v1 field, DEMOTED to display/search only
  "gloss": "…",                      // v1 (emit-the-sense) — the model's intended gloss
  "node_ref": "syn:82241",           // NEW: "syn:<synset_id>" | "vec:<canonical_phrase>"
  "synset_id": "82241",              // v1 field, kept = intended synset (null for vec:)
  "apt_senses": [                    // NEW, optional: local co-aptness ticks
    { "synset_id": "82241", "source": "intended" },
    { "synset_id": "82304", "source": "operator" }
  ]
}
```

- `synset_id` (v1 name) **is** the intended sense — no duplicate field; `node_ref`
  makes the syn/vec kind explicit. Absent `node_ref` derives from `synset_id`
  (`syn:` prefix) so every v1 record reads as v2 without rewrite.
- `apt_senses` sources are **`intended` and `operator` only**. The snapper never
  asserts co-aptness it can't validate; tagcount/`choose_sense` rank the grading
  *display fan*, and the operator's tick is what promotes a sense to apt.
- The `intended` row is implicit (derivable from `synset_id`); writers MAY
  materialise it, readers MUST treat `synset_id` as apt regardless.

### 3.2 ChainRecord v2

- `schema_version: "chain.v2"`.
- `vehicle_synset_id` / `topic_synset_id` become **optional**; new optional
  `vehicle_node_ref` / `topic_node_ref` (required for vec: endpoints). The
  endpoint-canonicalisation validator compares against `node_ref` when synset
  ids are absent.
- **`chain_signature` is unchanged**: `sha256(proposer + normalised phrases)`,
  already phrase-based and deliberately snap-stable → all 234 existing verdicts
  and all sense labels remain valid across migration. Any change that would
  alter a signature is a defect.
- v1 records remain valid v2 inputs forever (additive-only; readers default
  missing fields).

### 3.3 Canonicalisation

The canonical phrase key reuses the **existing `normalise_phrase`** (it already
keys `chain_signature` — one canonicaliser, never two). Modifier order is
preserved (`pressed flower` ≠ `flower pressed`). `vec:` refs use the canonical
phrase with spaces → underscores: `vec:pressed_flower`. De-duplication of nodes
is on the canonical form.

## 4. Snapper — per-hop, sense-aware

Runs at generation (new chains) and as migration re-snap (existing corpus):

1. **Gloss-match per hop** — existing `snap_by_gloss` (Lesk) with
   `snap_by_gloss_embed` (FastText) fallback, applied to **every** step (v1
   applied end-to-end but consumers only trusted endpoints). Output =
   `synset_id` (intended sense).
2. **Same-POS prior, not gate** — candidates matching the phrase head's noun
   reading are preferred; cross-POS snaps stay possible when gloss evidence is
   decisive (protects `anger→simmer`, `deadline→loom` — operator-found 2026-06-18).
3. **vec: gate** — if neither the full phrase nor its head lemma has any
   noun-synset candidate, admit as `vec:<canonical>`; log the admission. If candidates exist but gloss-match
   fails, snap to the best candidate and flag (`snap_confidence: "low"`) — never
   fall through to vec:, never drop.
4. **Fan ranking (grading display)** — the sense inventory for the fan is ranked
   by SemCor tagcount with same-POS boost; `dominant_sense_prior.choose_sense`
   is reused as the ranking primitive (its single-pick override mode is NOT used).

## 5. Migration ($0, idempotent, signature-preserving)

The 2026-06-19 gloss-backfill already produced per-node glosses for all 7,515
chains (`*_glossed_embed` corpus). Migration = per-hop embed re-snap off those
stored glosses (no LLM spend), emitting `chain.v2` files **alongside** the
originals (originals untouched), exactly the gloss-backfill playbook that
lifted endpoint snap accuracy 52%→78%.

- Idempotent: re-runnable; skips steps already carrying v2 fields.
- Verified invariant: every emitted record's `chain_signature` byte-equals its
  source record's.
- Post-migration: the 25 bad_sense-quarantined gold rows become re-grade
  candidates (their steps now carry corrected intended senses) — surfaced as a
  list, not auto-un-quarantined.
- Backup before promotion: the live grading chain files are copied aside before
  any in-place swap (same discipline as the 2026-06-20 promotion).

## 6. Grading tool consumption

Code changes on a dev branch off `grading-code`, cherry-picked to the deploy
branch (deploy-only discipline; see `feedback_grading_code_deploy_only`).

- **Phrase-first display** in all chain renderers: the step label is
  `step.phrase`, never `step.head`. `bad_head` *as display-loss* dissolves; the
  tag remains for genuine generation garbage.
- **Sense fan**: the shipped per-hop gloss tap (hover/tap → gloss) extends to a
  fan of the node's sense inventory (tagcount-ranked, intended sense pre-lit).
  Multi-tick → `apt_senses` with `source: "operator"`.
- **Verdict payload**: additive optional `step_apt_senses: [{step_idx, synset_id}]`
  on `judgement.v2` — same file, no schema break, v1/v2 verdicts co-read.
- **vec: steps** render the phrase + a "vector node — no synset" affordance in
  place of a gloss; fully gradeable.
- Sidecar Pydantic models mirror the TS types (`models.py` ↔ `grading.ts`), as
  with every prior grading round.

## 7. Judge / harness consumption

- `judge_corpus` gains a v2 reader (v1 fall-through). Prompts render the
  intended-path glosses (already the behaviour post gloss-fix `ec889f9a`);
  vec: steps render the bare phrase.
- **No judge re-tune in this milestone** — the judge is parked at the gold-noise
  ceiling; re-baseline runs as a post-build sanity check only (§9).

## 8. SQL DDL (designed now, built at Block 3)

Node-first primitive stack, replacing the synset-keyed NOT-NULL FKs on
`metaphor-graph/schema-base` (which vec:/sense-set nodes violate):

```sql
CREATE TABLE nodes (
    node_id   INTEGER PRIMARY KEY,
    phrase    TEXT NOT NULL,               -- canonical form, never impoverished
    head      TEXT,                        -- display/search only
    kind      TEXT NOT NULL CHECK (kind IN ('syn','vec')),
    UNIQUE (phrase)
);
CREATE TABLE node_senses (                 -- context-free sense inventory
    node_id   INTEGER NOT NULL REFERENCES nodes(node_id),
    synset_id TEXT NOT NULL REFERENCES synsets(synset_id),
    PRIMARY KEY (node_id, synset_id)
);
CREATE TABLE chain_steps (                 -- occurrence layer
    chain_signature TEXT NOT NULL,
    step_idx        INTEGER NOT NULL,
    node_id         INTEGER NOT NULL REFERENCES nodes(node_id),
    intended_synset_id TEXT,               -- NULL for vec:
    PRIMARY KEY (chain_signature, step_idx)
);
CREATE TABLE step_apt_senses (             -- per-occurrence co-aptness
    chain_signature TEXT NOT NULL,
    step_idx        INTEGER NOT NULL,
    synset_id       TEXT NOT NULL,
    source          TEXT NOT NULL CHECK (source IN ('intended','operator')),
    PRIMARY KEY (chain_signature, step_idx, synset_id),
    FOREIGN KEY (chain_signature, step_idx)
        REFERENCES chain_steps(chain_signature, step_idx)
);
-- metaphor_bridges / bridge_steps become node-referencing; the sense-grain
-- edge view for completion derives (judged vs derived provenance) at read
-- time. Deliverable here: updated SCHEMA.sql on schema-base + design note —
-- NO data build, NO sidecar DB dependency (it stays file-based).
```

## 9. Success criteria (measured on the next guided-walk batch post-build)

| Metric | Now | Target |
|---|---|---|
| `bad_sense` rate (incl. interior hops) | 33% | **≤ 10%** |
| `bad_head` from display impoverishment | 25% | **~0** (tag reserved for real garbage) |
| Vehicle-skip drops in next generation run | ~3.5% | **0** (vec: admission) |
| Existing verdicts/signatures resolving | 234/234 | **234/234 (unchanged)** |
| Judge κ re-baseline | 0.524 | **no worse** (sanity, not a target) |

## 10. Error handling, logging, observability

- Every vec: admission, low-confidence snap, and migration skip is logged with
  the phrase + position (tracing per the observability standard).
- No silent chain loss anywhere: drop paths are replaced by flagged records.
- Migration and snapper batch functions are idempotent (recovery never wastes
  prior work).

## 11. Testing

TDD (red/green) per module. Real fixture chains (not synthetic) for migration
tests. Frontend: component tests + **real-bundle headless Playwright** for the
sense fan, phrase-first labels, and vec: affordance (global UI-debug pref).
Sidecar: route tests for the `step_apt_senses` verdict payload (v1 verdict
POSTs must still validate). Harness: v2/v1 reader mix. Migration: idempotency +
signature-preservation asserted over the full real corpus.

## 12. Out of scope

Public-surface UI (cinematic base gate) · SQL data build (design only, §8) ·
sibling-path weighting and any completion logic (Block 3) · judge re-tune ·
compositor.
