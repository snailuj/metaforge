# SQLUNET Seed-Source — Complete Data Strategy Review

**Date:** 2026-06-05
**Author:** Claude (ultracode orchestration — 12 subsystem evaluators + adversarial verification)
**Provided copy:** `~/.local/share/metaforge/sqlunet.db` (569 MiB / 596 MB, 117 tables, 123 indexes, 0 views)
**Method:** read-only SQL against the complete source DB + the current `lexicon_v2.db`; every figure is queried, not recalled. All 117 source tables accounted for across 12 clusters (integrity-checked: 0 unaccounted).
**Status:** recommendation requiring operator sign-off. **No project data was modified.** Nothing imported.

---

## Executive summary

Import three things now, all cheap and non-redundant; park four for when their consumer is built; exclude the rest — led by FrameNet's 234 MB / 10.2 M-row annotation corpus, the single biggest deliberate "leave out." **(1) SemCor sense-frequency** (`senses.tagcount`, dropped because `senses` was read only for lemma pairs) is the one omission that serves the live binding goal: it directly unblocks the held ~$1.9k 10k-topic generation run, giving a deterministic dominant-sense prior with a **91% unique-winner rate** on multi-sense tagged topic lemmas plus a **POS-dominance filter** that flags 672 verb-dominant noun heads (say/take/get) to cull — at ~1.2 MB. **(2) WordNet `domains`** (and the dropped `synsets.domainid`) is a free, 100%-coverage, 45-class semantic-type label per synset — strong infrastructure for M05/Bridge/thesaurus — but the data measures it as a *background condition* of forge output (89% of pairs are cross-domain regardless of live/dead), so import it as a type/grouping signal and **never wire it into the cascade as an aptness feature**. **(3) `sources` + `meta`** (11 rows) closes the documented seed-provenance gap the Pipeline Architectural Review wants and de-risks licensing. The negative space is deliberate: everything verb-centric (PropBank, Predicate Matrix, VerbNet's FOL layer, FrameNet's verb-only grounding) is either redundant with the already-imported VerbNet or unreachable from the project's noun-dominated topic spine, and your own *context-free-edges* finding (relation/role substrates measured dead for aptness, AUC ≈ 0.55) means none of it helps the forge's positive signal.

---

## Selection criteria (confirmed by operator, 2026-06-04)

A dataset is import-worthy only if it clears these, judged in this order. **Default = exclude** unless it clears spine-joinability **and** (serves a binding goal **or** adds non-redundant value at proportionate cost). The negative space is part of the recommendation.

1. **Spine-joinability** — joins to `synset_id`/`sensekey` (precise, node-placeable) ≫ joins only to lemma-string (sense-ambiguous) ≫ none. **Soft weighting factor, not a hard gate** (operator's call) — a lemma-level attach can still qualify if value is high.
2. **Serves an active goal** — **Tier-1** (import now): unblocks/improves the live sense-accuracy + topic-quality work (the held 10k run). **Tier-2** (park — document + revisit, do *not* import now): serves only the visual thesaurus or the future Bridge feature. Else exclude.
3. **Non-redundant** with existing data.
4. **Cost/footprint proportionate** — rows, storage MB, schema complexity, transform effort.
5. **Risk** — noise, sparsity, redundancy, staleness, licence, maintenance.

Two operator rulings shaped the evaluation: spine-joinability is a **soft factor** (so FrameNet/PropBank got a genuine hearing, not a gate-out), and the *context-free-edges refutation* does **not** auto-discount relation/role data — each was **re-evaluated on its own merits** against the live DB.

---

## What was originally imported, and the reconstructed rationale

The build (`import_raw.sh`) reads `sqlunet_master.db` and lifts **three** SQLUNET subsystems, each partially:

| Subsystem | Imported into `lexicon_v2.db` | Dropped |
|---|---|---|
| **WordNet/OEWN** | `synsets`(id, pos, definition); `words`⋈`senses`→`lemmas` (185k pairs); `semrelations`(234,810)→`relations` | **`senses.tagcount/.sensekey/.sensenum`** (SemCor); **`synsets.domainid`**; `lexrelations`(294,690); `domains`, `samples`, `usages`, `ilis`, `wikidatas`, morphology, pronunciations |
| **SyntagNet** | `sn_syntagms` (87,265) ✓ full | — |
| **VerbNet** | `vn_classes`, `vn_members_senses`→`vn_class_members`, `vn_roles`, `vn_examples` | 15 other `vn_*` (frames, FOL semantics, predicates, syntaxes, groupings, restrictions) |
| **FrameNet** | nothing (empty `fn_frames`/`fn_frame_synsets` landing tables exist — import *anticipated*, never run) | all 43 `fn_*` |
| **PropBank / Predicate Matrix / SemLink / BNC** | nothing | all |

External (non-SQLUNET) sources also imported: Brysbaert familiarity + concreteness, SUBTLEX-UK frequencies (→ `frequencies`, **word-level, no POS, no sense**), FastText vectors.

**Charitable reconstruction:** the original extract took the WordNet **synset / lemma / semantic-relation spine** needed for a thesaurus, plus two verb-structure conveniences (SyntagNet collocations, VerbNet classes). The exclusions are **coherent, not random**: everything dropped is (a) verb-predicate-argument machinery (PropBank/FrameNet/PredicateMatrix/SemLink) irrelevant to a noun/adjective concept graph, (b) FrameNet's annotation corpus (41% of the DB by size), or (c) WordNet satellites (morphology, pronunciation, ILI, Wikidata). The decision was *under-documented*, not *wrong*. **The one exclusion that now bites is `senses.tagcount`** — discarded as collateral because `senses` was consulted only to manufacture lemma→synset pairs.

**Source provenance (from `sources`/`meta`, previously unimported):** WordNet 3.1 spine, OEWN 2025, English Namenet, VerbNet 3.4, PropBank 3.4, SemLink 1.2.2c, FrameNet 1.7, PredicateMatrix 1.3, BNC 2001, SyntagNet 1.0. Build branch `3_oewn_with_collocations`, commit `e653734f`, created 2026-01-04, dbsize 595,996,672.

---

## Schema map — subsystems, sizes, and link to the synset/sense spine

The spine is the WordNet **synset** (`synsets.synsetid` ↔ lexicon `synset_id` = `CAST(synsetid AS TEXT)`) with **`sensekey`** as the stable cross-resource sense id.

| Cluster (status) | tables | rows | storage | spine link & quality |
|---|---|---|---|---|
| WordNet core *(imported)* | synsets, words, senses, semrelations | 107,519 / 127,311 / 185,129 / 234,810 | ~30 MB | **native synsetid** |
| **SemCor** `senses.tagcount` | senses (3 dropped cols) | 34,767 tagged | **1.2 MB** | synsetid — **53%** curated, sensekey-backed |
| **domains** (+`synsets.domainid`) | domains | 45 (+col on 107,519) | **0.1 MB** | synsetid — **100%** |
| `lexrelations` | lexrelations, relations | 294,690 | 12.3 MB | synsetid — **100%** (sense-level) |
| BNC frequency | bnc_bncs (+3) | 28,449 | 0.74 MB | wordid→lemma — **18%**, +POS |
| samples / usages | samples, usages | 53,588 | 2.9 MB | synsetid — **34.6%** (noun 13.7%) |
| ILI / Wikidata | ilis, wikidatas | 114,248 | 1.94 MB | synsetid — ILI 97%, Wikidata 9% |
| VerbNet expansion | 19 `vn_*`/`v*` | 76,220 | 1.55 MB | synsetid (generic 99.9%; **FOL 35%, verb-only**) |
| FrameNet schema | 14 `fn_*` + pm_fn | 76,437 | 1.14–5.1 MB | via pm_fn — **2.9%, verb-only** |
| **FrameNet annotation** | 21 `fn_*` | **10,152,388** | **233.7 MB** | **none (0%)** |
| PropBank | 16 `pb_*` + pm_pb | 213,779 | 8.96 MB | via pm_pb — **4.3%, verb-only** |
| PredicateMatrix + SemLink | 6 `pm_*` + 2 `sl_*` | 195,503 | 15.18 MB | synsetid — **11%, verb-only** |
| Morphology residual | 11 lookup/satellite | 242,664 | 4.74 MB | mostly wordid / none |

**Join graph (to the spine):**
- **Native `synsetid`** (precise, node-placeable): `senses`, `semrelations`, `lexrelations`, `samples`, `usages`, `ilis`, `wikidatas`, `domains`(via `domainid`), `senses_vframes/vtemplates/adjpositions`, `sn_syntagms`, `vn_members_senses`, and the Predicate-Matrix tables `pm_pms/pm_fn/pm_pb/pm_vn`.
- **`sensekey`** secondary sense key: `senses`, `sn_syntagms`, `vn_members_senses`, `pm_pms`.
- **Lemma-string only** (`wordid`→`words.word`, sense-ambiguous): `bnc_*`, `lexes`, `casedwords`, all `fn_*` (via `fn_words`), all `pb_*` (via `pb_words`).
- **Class-mediated** (via `vn_classes`, already imported): `vn_frames/semantics/predicates/syntaxes`.
- **Sealed (no spine path whatsoever):** the 21-table FrameNet annotation corpus — confirmed by a schema grep finding zero `synsetid`/`sensekey` columns and no FrameNet↔WordNet bridge table in the DB.

**Decisive structural fact:** every cross-resource role layer (FrameNet, PropBank, Predicate Matrix, VerbNet's FOL semantics) grounds to the spine **only on verb senses**. The project's vetted topic manifest is **198/198 nouns**. So these subsystems touch **zero** topic nodes — a hard, untunable mismatch, not a coverage gap that more data fixes.

---

## Omission diff (current import vs complete source)

Present in source, absent from the project (the omission set), grouped by disposition:

- **Sense-level WordNet data:** `senses.tagcount`, `.sensekey`, `.sensenum` (SemCor); `lexrelations` (294,690 sense-level relations); `senses_vframes/vtemplates/adjpositions`.
- **Synset attributes:** `synsets.domainid` + `domains` (45 lexicographer domains); `samples` (53,516 gold example sentences); `usages` (72); `ilis` (104,335); `wikidatas` (9,913).
- **Frequency:** `bnc_*` (POS-resolved corpus frequency).
- **Verb-predicate machinery:** 15 `vn_*` expansion tables; all 43 `fn_*` (schema + annotation corpus); all 16 `pb_*`; all `pm_*`/`sl_*`.
- **Morphology/lookup/provenance:** `lexes`, `lexes_morphs`, `morphs`, `lexes_pronunciations`, `pronunciations`, `casedwords`, `adjpositions`, `poses`, `sources`, `meta`.

---

## Candidate evaluations

Every omitted subsystem, scored against the confirmed criteria. Verdicts in **bold** were adversarially re-computed by an independent skeptic; "verify" notes the outcome.

| # | Subsystem | Spine | Tier-1 (forge) value | Tier-2 (thesaurus/Bridge) value | Cost | Key risk | **Verdict** | verify |
|---|---|---|---|---|---|---|---|---|
| 1 | **SemCor `tagcount`** | synsetid 53% | **Unblocks held run**: 91% unique-winner WSD on 8,243 multi-sense tagged topic lemmas; POS filter flags 672 verb-dominant noun heads | per-sense salience for thesaurus/Bridge | 1.2 MB | 47% coverage gap → LLM fallback stays | **IMPORT (Tier-1)** | revised→import (40%→**91%**, stronger) |
| 2 | **`domains`** (+domainid) | synsetid 100% | none (background condition, not discriminator) | **45-class type label** for M05/Bridge/thesaurus, 100% coverage, zero LLM | 0.1 MB | misuse as aptness feature | **IMPORT (cheap infra)** | confirmed |
| 3 | **`sources`+`meta`** | n/a (DB-level) | none | closes provenance/licence gap (Architectural Review) | 0.008 MB | none | **IMPORT (provenance)** | recovered eval |
| 4 | BNC POS-freq | wordid 18% | sharpens POS filter: 995 verb-dominant vs SemCor's 604; **58% SemCor-invisible** | redundant word-freq for UI | 0.66 MB | redundant as raw freq; sense-blind | **DEFER → import w/ SemCor** | confirmed (exact) |
| 5 | `lexrelations` (antonym+deriv+pertainym) | synsetid 100% | low (relation class measured dead) | **Bridge edges**: derivation 96% cross-POS; thesaurus antonyms | 12.3 MB (88.9k-row subset) | collocation 59% is noise → exclude it | **DEFER (Tier-2)** | revised→unchanged (0 row overlap confirmed) |
| 6 | VerbNet FOL layer | class-mediated 35%, verb-only | none (0% noun topics) | predicate edges for verb-metaphor/Bridge | 0.2 MB subset | verb-only; needs FOL parse | **DEFER (Tier-2)** | confirmed |
| 7 | `samples` | synsetid 34.6% (noun 13.7%) | weak (usage_example already 98.6% filled) | gold "show usage" for thesaurus on 32% of nodes | 2.9 MB | noun-sparse; redundant slot | **DEFER (Tier-2)** | confirmed |
| 8 | FrameNet schema | pm_fn 2.9%, verb-only | none (0 topic nodes) | frame-relation graph (3,569 edges) for Bridge; landing tables pre-built | 1.14 MB | verb-confined; depends on pm_fn | **DEFER (Tier-2)** | confirmed (0 topic intersection) |
| 9 | ILI + Wikidata | synsetid 97% / 9% | none | Wikidata "see also" needs unbuilt external fetch; 6% of topics | 1.94 MB | opaque pointers; scope creep | **EXCLUDE** | confirmed |
| 10 | PropBank | pm_pb 4.3%, verb-only | none | **83% redundant** with imported VerbNet; 770 net-new verb synsets | 8.96 MB | redundant; dangling FN pointers | **EXCLUDE** | confirmed |
| 11 | PredicateMatrix + SemLink | synsetid 11%, verb-only | none | *right vehicle* for roles IF ever wanted; SemLink 75–79% subsumed by pm_pms | 15.18 MB | verb-only; redundant w/ VerbNet | **EXCLUDE (park option note)** | recovered eval |
| 12 | FrameNet annotation corpus | **none 0%** | none | none (luid-keyed, sealed from spine) | **233.7 MB / 10.2 M rows** | 41% of DB; pure dead weight | **EXCLUDE** | confirmed |
| — | Morphology/pronunciation/casedwords/poses | wordid/none | none | product polish, no consumer | 4.7 MB | redundant w/ FastText+lemmatiser | **EXCLUDE** | recovered eval |

---

## Ranked recommendation (import set)

### A. Import in the next base-DB build — cheap, non-redundant, no reason to wait

**1. SemCor sense-frequency** — *Criterion 2 (binding goal) + 1 (synsetid) + 3 (non-redundant)*
The only omission that serves the active blocker. Lift the tagged senses onto a new sense-level table; the dominant-sense prior replaces LLM disambiguation for the large majority of hard multi-sense topic lemmas (skeptic re-computed **91% unique-winner**, up from the evaluator's 40%), and the POS-dominance aggregate culls verb-dominant noun heads. LLM disambiguation remains the fallback for the 47% untagged tail — a prior+filter, not an oracle.

**2. WordNet domains** — *Criterion 1 (100% synsetid) + 3 (45-way type vs 4-way pos) + 4 (≈0 cost)*
Re-add the dropped `synsets.domainid` column + the 45-row `domains` table. A free, complete, zero-LLM semantic-type label — infrastructure for M05 type-aligned scoring, Bridge cross-domain annotation, and thesaurus node-grouping. **Guard (Criterion 5):** import as a *type/grouping* signal only; do **not** wire `domain-distance` into the cascade as an aptness predictor — measured 89% cross-domain background rate with no live/dead separation (consistent with the AUC ≈ 0.55 refutation). Restoring a dropped NOT-NULL column at 0.1 MB makes parking pointless.

**3. Provenance (`sources` + `meta`)** — *Criterion 5 (licence/provenance) + 4 (11 rows)*
The lexicon has no provenance table. These 11 rows document every upstream dataset with versions/URLs/references plus the build commit and WordNet version — exactly the seed-data provenance the Pipeline Architectural Review flagged as missing, and the only licence-audit anchor in the DB.

### A′. Import in the same pass *if* the POS-dominance topic filter ships with SemCor

**4. BNC POS-split (`bnc_bncs`)** — *Criterion 3 (the only non-redundant axis: POS)*
The held milestone already includes a POS-dominance filter (Inbox line 107). SemCor alone flags 672 verb-dominant noun heads; BNC flags **995**, of which **58% are invisible to SemCor** (no n+v tagcount pair), at 0.66 MB. If you're building the filter now, bring BNC as SemCor's companion; if not, park it. Import *only* the `(lemma, noun_freq, verb_freq)` pivot — the raw word-frequency is 100% redundant with `frequencies`.

### B. Park (Tier-2 — real, non-redundant value; import when the consumer is built)

5. **`lexrelations`** antonym + derivation + pertainym subset (~88,900 rows; **exclude** the 174,436-row collocation noise) — Bridge traversal (derivation is 96% cross-POS, stitching noun↔verb↔adj families the synset taxonomy can't) + core thesaurus relations. Zero row-overlap with the imported relation graph.
6. **VerbNet FOL layer** (`vn_semantics` + `vn_predicates` + `vn_predicates_semantics`, ~3,875 rows) — predicate-shared traversal edges for a *future verb-metaphor / Bridge* consumer. Exclude the bulk generic-frame tables (`senses_vframes` etc.).
7. **`samples`** — gold WordNet example sentences for a thesaurus "show usage" affordance on 32% of nodes. Parked because the LLM `usage_example` slot is already 98.6% filled and coverage is noun-sparse; adopt gold-preferred display when the browse UX is built.
8. **FrameNet schema** (`fn_frames` + `fn_frames_related` + `pm_fn` grounding) — the 3,569-edge curated frame-relation graph for the Bridge; the empty `fn_frames`/`fn_frame_synsets` landing tables show this was the project's original intent. Verb-confined, so unreachable from noun-topic queries until the Bridge exists.

### C. Deliberate exclusions (negative space) — see below.

---

## Deliberate exclusions (documented, revisitable)

- **FrameNet annotation corpus (21 tables, 10.15 M rows, 233.7 MB — 41% of the source DB).** Zero spine-joinability (no `synsetid`/`sensekey` anywhere; the corpus is structurally sealed from WordNet). Raw frame-parsing training data with no consumer; importing would near-double the lexicon footprint across every worktree for no node-placed signal. The single largest leave-out, and the clearest.
- **PropBank (16 tables, 8.96 MB).** 83% of its synset-linked senses are already covered by the imported VerbNet (which supplies the same thematic-role abstraction *with* synset links); verb-only, 4.3% spine coverage, 0% topic coverage; its PB→FrameNet maps would dangle against the empty `fn_frames`. Net-new value is 770 verb synsets behind a 15-table import. Not proportionate.
- **Predicate Matrix + SemLink (8 tables, 15.18 MB).** Verb-only, 11% spine coverage, redundant with imported VerbNet; SemLink is 75–79% subsumed by `pm_pms`. *Option note:* `pm_pms` **is** the technically-correct single vehicle to land VN/PB/FN roles on the spine **if** verb-frame role data is ever wanted for the Bridge — revisit it then and retire `sl_*` + raw `pb_*`/`fn_*`-schema. Not now.
- **ILI + Wikidata (1.94 MB).** ILI is an opaque interop pointer with no project consumer. Wikidata covers only 6% of actual topics and yields nothing without an unbuilt external-fetch layer (the named-entity-skew hypothesis was refuted — all links are common-noun concepts). Revisit Wikidata only alongside a future external-enrichment design.
- **Morphology / pronunciations / casedwords / poses / `lexes` (≈4.7 MB).** Morphology is redundant with FastText + the existing WordNet lemmatiser fallback; pronunciations have no audio/phonetics surface; casedwords is display polish; `poses` duplicates `synsets.pos`. `senses_adjpositions` and pronunciations are faint Tier-2 polish — park, don't import.

---

## Extraction & validation plan (per recommended dataset)

> All extractions run against the **source** with the lexicon attached read-only; the INSERT target is a *new base-DB build*, never the live `lexicon_v2.db`. Pattern:
> `sqlite3 -readonly "$SRC" -cmd "ATTACH 'file:$LEX?mode=ro' AS lex" "…"`

### 1. SemCor `sense_tagcounts`
```sql
CREATE TABLE sense_tagcounts (
  synset_id TEXT NOT NULL,   -- == CAST(senses.synsetid AS TEXT)
  sensekey  TEXT,            -- stable cross-resource sense id (100% populated for tagged)
  sensenum  INTEGER,
  tagcount  INTEGER NOT NULL,
  PRIMARY KEY (synset_id, sensekey)
);
INSERT INTO sense_tagcounts
SELECT CAST(s.synsetid AS TEXT), s.sensekey, s.sensenum, s.tagcount
FROM senses s WHERE s.tagcount > 0;        -- 34,767 rows
CREATE INDEX idx_sense_tagcounts_synset ON sense_tagcounts(synset_id);
```
Dominant-sense pick: `JOIN lemmas USING(synset_id) … ORDER BY tagcount DESC LIMIT 1`. POS filter: aggregate `tagcount` per `(lemma, synsets.posid)`, drop noun heads where `verb_tc > noun_tc`.
**Validation:** (a) row count == 34,767, 0 orphan synset_ids, 100% sensekey non-null; (b) pin curated-frontier coverage 18,536/35,000 (53%) as a fixture; (c) spot-check `fire`→71587, plus `light`/`bank`/`spring`; assert ~91% unique-winner among multi-sense tagged topic lemmas; (d) assert the 672-noun verb-dominant cull contains say/take/get/regard; (e) **goal metric** — on a human-gold sample of multi-sense topic heads, compare top-1 sense accuracy LLM-only vs tagcount-prior+LLM-fallback; expect higher accuracy and fewer mis-picked common-word senses.

### 2. WordNet domains
```sql
ALTER TABLE synsets ADD COLUMN domainid INTEGER;          -- or rebuild from SCHEMA.sql
CREATE TABLE domains (domainid INTEGER PRIMARY KEY, domain TEXT, domainname TEXT, posid TEXT);
-- backfill (note the CAST DIRECTION — cast the TEXT lexicon id to INT so the source PK index is used;
--  casting the source side to TEXT triggers a full-scan-per-row that hangs on the 107k×107k join):
UPDATE synsets SET domainid = (SELECT s.domainid FROM src.synsets s WHERE s.synsetid = CAST(synsets.synset_id AS INTEGER));
```
**Validation:** `COUNT(domains)`==45; 0 NULL `domainid` after backfill (target 107,519/107,519); per-domain histogram matches source (noun.artifact 11,985, noun.person 7,848, adj.all 14,496, noun.motive 41); **misuse tripwire** — re-run the discriminative-aptness eval with/without a domain-distance feature and confirm it does *not* change `separation_score` (expected null; guards against treating type-mismatch as aptness).

### 3. Provenance
```sql
CREATE TABLE seed_sources (idsource INT PRIMARY KEY, name TEXT, version TEXT, wnversion TEXT, url TEXT, provider TEXT, reference TEXT);
CREATE TABLE seed_meta    (created TEXT, dbsize INT, build TEXT);
-- INSERT … SELECT … FROM src.sources / src.meta (10 + 1 rows)
```
**Validation:** row counts 10 and 1; assert the WordNet-3.1 and OEWN-2025 rows are present (licence-audit anchors); adds reference tables only → re-run forge eval, assert unchanged.

### 4. BNC POS-split (conditional)
```sql
CREATE TABLE lemma_pos_freq AS
SELECT w.word AS lemma,
       SUM(CASE WHEN b.posid='n' THEN b.freq ELSE 0 END) AS noun_freq,
       SUM(CASE WHEN b.posid='v' THEN b.freq ELSE 0 END) AS verb_freq
FROM bnc_bncs b JOIN words w ON w.wordid=b.wordid
GROUP BY w.word;   -- 22,865 lemmas
```
**Validation:** 22,865 lemmas, all present in `lemmas`; canonical verb-dominant set (be/do/make/go/take) flagged; 826 current noun lemmas flagged verb-dominant; **goal metric** — false-noun rate in the auto-selected topic set before/after, run jointly with SemCor; expect ~+391 incremental drops over SemCor alone, >90% true positives.

### 5–8. Parked datasets
Each carries its extraction sketch + the coverage figure in the candidate evals above so a future session need not re-measure. Gate every Tier-2 import on its consumer (Bridge / thesaurus-relations / verb-metaphor) actually being scheduled, and validate against *path-coverage / UX*, **never** against `aptness_rate`/`separation_score` — the project already measured this signal class dead there.

---

## Open questions (for the operator)

1. **WordNet version skew.** The source `meta` records a **WordNet 3.1** spine with OEWN 2025 collocations; the project docs describe "OEWN." Confirm the lexicon's synset ids are the WN-3.1/OEWN ids the source uses (they join 100%, so this is provenance hygiene, not a blocker) — worth recording in the seed-provenance doc.
2. **POS-dominance source choice.** SemCor and BNC both supply the verb-dominant-noun filter; BNC catches 58% more but is sense-blind, SemCor is sense-precise but sparser. Run *both* (cheap), or SemCor-only for v1? Recommendation: both, in one pass.
3. **`sensekey` as a second key.** SemCor's `sensekey` is 100%-populated on tagged senses and is the join key for SyntagNet/VerbNet/PredicateMatrix. Worth persisting `sensekey` on the lexicon's sense layer now (free) so any later cross-resource work has the key ready?
4. **`domains` misuse risk.** Confirm the guard: import domains as type/grouping infra, explicitly **not** as a cascade aptness feature. If a larger graded set ever shows domain-mismatch separating live/dead (it doesn't at n=13), revisit.
5. **lexrelations collocation subset.** The 174,436-row collocation type is excluded as noise — confirm, or is collocation co-occurrence wanted for any thesaurus "goes-with" affordance?
6. **Re-import vs in-place upgrade.** SemCor + domains + provenance can land via a base-DB rebuild from `import_raw.sh` (clean) or an in-place migration on the live DB (faster, but the project's schema-drift history argues for the rebuild). Which path?

---

*Appendix — working artefacts (not committed): full source schema `~/.local/share/metaforge/sqlunet_schema.txt`; per-subsystem evaluation JSON `~/.local/share/metaforge/eval_results.json`. Integrity check: all 117 source tables mapped to a cluster, 0 unaccounted.*
