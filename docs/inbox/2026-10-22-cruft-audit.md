# Cruft audit — 2026-10-22

Read-only sweep of every tracked file (913 files) across `api/`, `web/`, `data-pipeline/` + `lib/` + `scripts/`, and docs/root/config/deploy. Nothing has been changed. Each item has an ID so you can approve or reject it by ID.

**Confidence** says how sure we are the item isn't needed: **H** = verified dead or duplicate, **M** = probably dead but tied to a decision, **L** = keep unless you want to tidy.

**Cross-cutting facts:**
- Deleting files from HEAD will **not** shrink `.git` (161 MB). Every large blob is still in history; only a history rewrite (`git filter-repo`) would reclaim that space.
- One decision unlocks most of the bulk: **retire the static forge (`/forge/suggest` + the cascade)?** (PIPELINE.md Inbox already asks this.) It is not dead today: the web has never called it, but these Python eval and sweep tools drive it: `evaluate_mrr.py`, `evaluate_discrimination.py`, `m04_sweep_runner.py`, `parity_test_go_vs_python.py`, `loop1_eyeball_harness.py`, `metaphor_graph_enrich_cascade.py`. Items marked **[F]** fall together if the answer is yes.

---

## 0. Real bugs found in passing (not cruft — fix regardless)

| ID | Where | Problem |
|----|-------|---------|
| B1 | `api/internal/db/db.go:36` | `sql.Open("sqlite3", path+"?mode=ro&immutable=1")` has no `file:` prefix. go-sqlite3 then ignores `mode`/`immutable`, opens read-write, and **creates an empty DB if the path is missing**. This also stops the test helpers' "skip if DB missing" from ever skipping. A `go test` run during this audit created a 0-byte `output/lexicon_v2.db`; it has since been removed. Fix: `"file:"+path+"?mode=ro&immutable=1"`. |
| B2 | `.claude/skills/metaforge-pipeline-management/SKILL.md:78,201`, `data-pipeline/CLAUDE.md` | The rebuild uses `--from-json data-pipeline/output/enrichment_*.json`, which pulls in **every old run** (see D-items). With INSERT OR IGNORE the first file wins, so a rebuild today would **not** reproduce the current DB. |
| B3 | `deploy/cleanup-legacy-services.sh` | It stops and disables `julianit-caddy`, which is now the live Caddy unit (CLAUDE.md). Running it would take every site down. → delete (A1). |
| B4 | `.claude/skills/backlog-capture/SKILL.md` | It tells agents to `gh issue create` for internal deferred work, which contradicts the CLAUDE.md rule that issues are for external work only and internal items go to the PIPELINE.md Inbox. → delete or rewrite to append to `## Inbox`. |
| B5 | `data-pipeline/grading_sidecar/routes/calibration.py:19` | It reads `sonnet_chains_provisional_r{N}.jsonl`, a name that no longer exists after the `chain-topics_*` rename, so `/calibration-sample` always 404s (web never calls it). `scripts/build_next_round_prompt.py:90` uses the same dead glob. |
| B6 | `data-pipeline/requirements.txt` | Imported but not listed: `pyyaml` (`m04_sweep_runner.py`, `run_sweep.py`) and `scipy` (`predict_concreteness.py`). |
| B7 | `web/vite.config.ts` | No `/api` proxy, so in `npm run dev` Vite's index.html fallback may answer `/api/grading/healthz` with 200 and wrongly enable grading mode. *Unverified.* |

---

## A. Safe deletes (H — duplicates, broken, or self-declared done)

| ID | Path | Evidence |
|----|------|----------|
| A1 | `deploy/cleanup-legacy-services.sh` | See B3. Nothing references it. |
| A2 | `data-pipeline/output/enrichment_4000_sonnet_v2_test.json` (9 MB) | sha256-identical to `…_20260224.json`. Zero refs. |
| A3 | `data-pipeline/output/enrichment_2000_gemini-flash_20260215.json` (774 KB) | sha256-identical to `property_pilot_2k.json` (the name the docs use). |
| A4 | `data-pipeline/output/checkpoint_enrich.json.curated-props-20260517` (50 MB), `.rescue-complete-20260520` (1.3 MB) | Synset-ID sets match the committed curated-props and rescue enrichment JSONs exactly. They got past `.gitignore` because of the suffix → also add `checkpoint_*.json.*`. |
| A5 | `data-pipeline/output/snap_dropped.json` (4.1 MB) | Superseded by `.jsonl`. `test_snap_properties.py:789` asserts the old file is *not* created. |
| A6 | `data-pipeline/output/lexicon_v2.db.pre-purge-20260517.keep-for-m03-baseline` | Its own deletion condition (M03 done) has been met. |
| A7 | `data-pipeline/evolve_trials.sh` | Broken: its target `evolve_prompts.py` is in `scripts/_archive/`. Also drop its row from the data-pipeline/CLAUDE.md "Shell Scripts" table. |
| A8 | `data-pipeline/output/evolution/*` (5 files) | Only the archived evolve scripts read or write them. |
| A9 | Duplicate PDF *AI-based estimates of word familiarity final.pdf* (1.5 MB) | Byte-identical in `docs/designs/research/` and `data-pipeline/input/multilex-en/`. Keep one and repoint links (PRD:949 → docs copy; `word-freq-fam.md:25` and the 2026-02-12 brainstorm → input copy). |
| A10 | `data-pipeline/input/subtlex-uk/familiarity-document.pdf` (201 B) | Not a PDF: a two-line text note holding an osf.io link. |
| A11 | `requirements.txt`: `tqdm`, `tenacity`; `grading_sidecar/requirements.txt`: `pytest-asyncio` | Never imported, and there are no async tests. |
| A12 | `.claude-skills/` (105 files, 920 KB, superpowers 4.1.1 copy) + the "Superpowers Skills" section of CLAUDE.md | Nothing loads it: Claude Code reads `.claude/skills`, not this directory. Out of date: it still uses the `docs/plans/` layout, while current work uses `docs/superpowers/`. `docs/plans/2026-02-27-changelog-and-backlog-design.md:134` already calls it YAGNI. |
| A13 | `web/src/graph/colours.ts:20-29` `FORGE_TIER_COLOURS`, `graph/types.ts:24-25` `ForgeTier`, `colours.test.ts:24-37` | Only its own test imports it. Leftover from the static-index tiers. |
| A14 | `web/src/config.ts` (`SUGGEST_MODE`) and its branches in `mf-search-bar.ts:206-224` | Hard-coded to `'dropdown'`. The `auto-load` branch can never run, and `inline` is just a TODO. |
| A15 | `web/src/components/mf-results-panel.ts:177-180` `.connotation-neutral` | Never matches, because line 298 never renders `neutral`. |
| A16 | `web/src/styles/tokens.css` `--colour-node-*`, `--colour-edge-*`, `--colour-forest-hop-label` | No `var()` reference anywhere. Graph colours come from `colours.ts`. |
| A17 | Go code unused outside its own tests: `handler.NewHandler`; `db.Synset` + `GetSynset` (reads old tables); `GetForgeMatchesCurated` (superseded by `…ByLemma`); `GetSynsetIDForLemma`; `GetLemmaForSynset`; `embeddings.GetPropertyEmbedding`, `BlobToFloats` wrapper, `EmbeddingDim` alias; `forge.ReRankBonus` (prod uses `…Pow`) | `staticcheck` can't see these because the tests use them. Delete with their tests. |
| A18 | `db/cascade.go:136` unused `threshold` param of `GetForgeCascadeCandidatesByLemma` | Its own comment admits the SQL no longer reads it. |
| A19 | `docs/inbox/captures.md` | Marked RETIRED, kept only as a pointer. First fix the metaforge-pipeline skill and PIPELINE.md references to it. |

## B. Stale docs and comments to update (H — no deletion, just correct)

| ID | Where | What's wrong |
|----|-------|--------------|
| C1 | `README.md` | Route list is `/lookup /graph /forge/suggest /strings`; the real routes are `/thesaurus/lookup`, `/thesaurus/autocomplete`, `/forge/forest`, `/strings/*` and `/health`, and there is no `/graph`. Other stale lines: "~370 tests" (actual ≈ 2,500 test functions); "What's next: Metaphor Forge UI" (built); "~8,000 synsets"; Project Structure is missing forest/llm/observe/grading and places `PRE_ENRICH.sql` wrongly. |
| C2 | `CLAUDE.md` | Labels `metaforge.julianit.me` as staging; it is **production**, and staging is `-next`. "~300 tests". Design Status table says Thesaurus frontend and 3D graph "not started", and the forest "tuning pending", which contradicts the same file. "IndexedDB" (code uses only localStorage). CI/CD and canary rows are written as if in force, but no `.github/` workflow exists. Grading auto-commit path (now the `.worktrees/grading-data` worktree). |
| C3 | `data-pipeline/CLAUDE.md` + `metaforge-pipeline-creation` skill:108 | Say SQL dumps (`PRE_ENRICH.sql`, `lexicon_v2.sql`) are committed; `.gitignore` excludes them and none are tracked. Also says "5 operations" in one place and "4" in another; two different venv paths; every Data Sources URL and licence cell is TODO. `evaluate_mrr` is listed as op 4 (see F-items). |
| C4 | `TESTING.md` | `go test ./...` without `cd api` (no go.mod at root); Playwright not mentioned; duplicates README and CLAUDE.md. → fix, or fold into README and delete. |
| C5 | `deploy/grading/metaforge-grading.service:15` | Comment says `.worktrees/next` tracks branch `grading-live`; it tracks `main`. |
| C6 | `docs/roadmap/programme-overview.md` | "Current State" is about 5 months stale. Its pointer to `archive/2026-05-03-gsd-final-snapshot.md` "preserving REQUIREMENTS.md verbatim" is false (that file is a 1.4 KB note). |
| C7 | `docs/roadmap/PIPELINE.md` | Broken link `docs/inbox/2026-06-12-judge-prompt-templates.md` (line 42). Inbox item "stream partial forests if latency hurts" is already done (`forest/stream.go`). |
| C8 | Go comments | `forge/cascade.go` says "until task 6" (it's done), "Gamma=0 by default" (the default is 1.0), and IN-chunking "parked" (it's done). `db/cascade_embedding.go:314` says `GetSynsetClusterPropertiesBatch` chunks (it doesn't). `forest/service.go:14` says "both calls non-streaming", and `handler/forest.go:20` / `main.go:174` say "two sequential calls"; the stream path runs up to 4 parallel judge calls. `main.go:1` says "Sprint Zero MVP". `cascade_test.go:479` cites a non-existent `sweeps/m05_lakoff_gamma_phase2_verdict.md`. |
| C9 | Web comments | `colours.ts` says "used in results panel" (false; only `NODE_COLOURS.central` is read in production). `mf-search-bar.ts:158` references "line 76". `mf-force-graph.ts:114` says the fix is "guarded by raycaster-offset.spec.ts", but that spec asserts nothing (see E5). |
| C10 | Historical status lines in `docs/designs/` and `docs/plans/` | `core-thesaurus.md` ("no frontend"), `metaphor-forge.md` (superseded by the forest), `curated-property-vocabulary.md` and `word-freq-fam.md` ("not yet implemented", both are), `2026-02-06-core-thesaurus-frontend.md` ("ready"), `2026-10-21-forest-streaming.md` ("draft for approval", it's built; also its forestprobe rationale is wrong, since forestprobe doesn't call HTTP). `docs/designs/README.md` references `Metaforge-Build-Map.md`, which has never existed. → add a "Historical / superseded" banner rather than rewrite. |
| C11 | `Metaforge-PRD-2.md` Metaphor Forge section | Describes the static forge as "already built / next UI". → add a pointer to the Live-Model-Metaphor-Forest decision. |
| C12 | `data-pipeline/grading/README.md`, `grading_sidecar/paths.py` | Document the old `sonnet_chains_provisional_*` names. `paths.py` names `build_sense_inventories.py`, which isn't in the repo. |
| C13 | `.gitignore` | `data-pipeline/input/brysbaert-concreteness/` is used nowhere; redundant patterns (`output/*.db` vs `*.db`, three venv variants); boilerplate for unused stacks (`.next/`, `target/`, `vendor/`); `!.env.example` matches nothing. Optional tidy. |

## C. Archive candidates (M — finished work kept as history; move to `docs/archive/` or `scripts/_archive/`, or delete since git keeps it)

| ID | Path | Notes |
|----|------|-------|
| E1 | `docs/reports/*` except `2026-02-22-cross-domain-scoring.md` (12 files) | Sprint Zero agent outputs (task reports, PR reviews, code reviews). Unlinked. |
| E2 | `docs/reviews/2026-02-06-requesting-code-review.md`, `20260217-sense-alignment-mrr0.07-analysis.md` | Unreferenced. Keep `sqlunet-datasets/*`, which is linked. |
| E3 | `docs/property-vocab-spike-findings.md` | Loose at the docs root; unreferenced. Move it. |
| E4 | `docs/plans/2026-04-26-gsd-migration-plan.md`, `20260207-prd-reconciliation-scratchpad.md`, `2026-02-12-evolution-v2-*` | The GSD tooling was decommissioned; the PRD has been reconciled; the evolve code is already archived. |
| E5 | `web/e2e/raycaster-offset.spec.ts` + `fixture-browse.html` | A diagnostic with no `expect`; writes `/tmp/*.json` on every Playwright run. Either turn it into a real assertion (`canvasTopMinusContainerTop === 0`) or delete it. |
| E6 | One-off pipeline scripts whose job is done (+ their tests): `filter_metaphor_pairs.py` (+ `fixtures/metaphor_pairs_generated.json`), `analysis/monosemy_coverage.py`, `migrate_add_sqlunet_tables.py`, `metaphor_disambiguate.py`, `head_extraction_backfill.py` + `head_extractor.py` (reads `/tmp/stagea_spike`), `audit_physical_coverage.py`, `gap_fill_physical.py` | → `scripts/_archive/`. Confirm first that the prod dump already has the sqlunet tables. |
| E7 | Metaphor spike runners: `metaphor_spike_1b.py`, `metaphor_spike_2.py`, `generate_spike_1b_gold_examples.py`, `curate_spike_2_topics.py`, `spike_1b_gold_examples.json`, `test_metaphor_spike_1b.py`, plus outputs `metaphor_spike_*phase1a*` / `*phase1b*` / `scores_phase2*` / `scoring_phase2*` | **Keep** `metaphor_spike_1a.py` (imported by live scripts) and `spike_2_topics.json` (used by 5 scripts). |
| E8 | Metaphor-graph Stage A ingest: `metaphor_graph_enrich_{cascade,haiku,inapt,run,sonnet,topics}.py` + 6 tests | They fill the `metaphor_bridges` tables, which no Go or web code reads (parked static index). Keep `metaphor_graph.py`, which is imported. |
| E9 | `docs/inbox/2026-06-03-context-free-edges/` interim files (`FINDINGS_SO_FAR.md`, the non-`_FIXED` `multihop_graph_result.txt`) | Superseded by `FINAL_REPORT.md` and `_FIXED`. |
| E10 | `docs/inbox/m05-brainstorming-notes.md` | Not cruft, but undated; rename with its 2026-05-23 date. |
| E11 | `data-pipeline/scripts/_archive/` (29 files) | Already archived; could be deleted outright since git has it. The roadmap and a review log name it. |

## D. Needs your decision (M/L — data, licences, or live-ish code)

| ID | Question | Context |
|----|----------|---------|
| F0 | **Retire the static forge?** | If yes, everything marked **[F]** goes (about 4.5k lines of Go tests, a dozen-plus Python scripts, sweeps). If no, consider moving `/forge/suggest` behind a dev-only flag; production currently serves the legacy path to anyone who hits it directly. |
| F1 [F] | Go static forge | `HandleSuggest`, `handleSuggestLegacy`, `handleSuggestCascade`, `handler/cascade_*.go`, `internal/forge/*`, `internal/db/cascade*.go`, `GetForgeMatchesCuratedByLemma`, the 15 `-cascade*`/`-forge-*`/`-gamma`/`-gate-*` flags in `main.go`, the whole `embeddings` package (its last production user is the legacy path), and the permanently skipped `TestCascadeUnion_LatencyBudget`. Also: the startup required-table check (`handler.go:50-53`) demands forge-only tables while not checking the thesaurus's own tables → shrink it to the thesaurus's own tables. |
| F2 [F] | Unreachable cascade options even if kept | `CompositionMultiplicative` (no flag sets it); `OrtonyScoring` (only one value is accepted; parity script sets it); legacy `Alpha`/`Beta`/`CompositeScore`; `Match.OverlapCount` "backward compat" (no consumer); duplicate cosine helpers; `-cascade-timing` now also gates forest timers → rename. |
| F3 [F] | Karpathy-loop + parity harness | `evaluate_loop_{harness,metric}.py`, `loop_iter_wrap.py`, `loop1_eyeball_*`, `parity_test_go_vs_python.py` + tests; `loop_baseline.json`, `loop1_eyeball_*`; `fixtures/lakoff_*.jsonl`; `metaphor_spike_{apt,inapt}_phase2_*.jsonl`. |
| F4 [F] | Sweeps | `run_sweep.py`, `m04_sweep_runner.py`, `m05_cohort_diagnose.py`, `m03_diagnostics.py` + tests; `sweeps/` (13 yaml + 16 md; move the verdict md files to docs); `eval_baseline_v2.json`, `m03_preflight_diagnostics.json`, `m04*_results.json`; `fixtures/munch_*` (4.2 MB). **Caution:** keep `evaluate_cascade.py`, which `export_chain_geometry.py` (sidecar data) imports, and `evaluate_aptness.py` (spikes). |
| F5 [F] | MRR / discrimination eval (pre-M01, superseded by MUNCH aptness) | `evaluate_mrr.py`, `evaluate_discrimination.py` + tests; about 15 `eval_*` / `mrr_*` outputs (incl. `eval_enrichment.json` 956 KB); `fixtures/metaphor_pairs{,_v2}.json`. Remove op 4 from CLAUDE.md and the skill. |
| F6 | `cmd/forestprobe` | A live prompt-tuning harness, but it reimplements the one-shot flow. Production now streams with per-facet judging, so probe results no longer match production. Keep and rebase it on `GenerateStream`, or delete. Either way, dedupe `callMaxTokens=16000` (defined 3×). |
| F7 | Non-stream forest path (`Service.Generate`, JSON branch of `HandleForest`, web `fetchForest`) | The web always streams, and `fetchForest` is used only by tests. Recommend **keep** the Go JSON path (curl/debug, cheap). Deleting `fetchForest` means moving its tests onto `streamForest`'s JSON branch. |
| F8 | Superseded enrichment runs in `output/` (≈ 45 MB) | `enrichment_2000_sonnet`, `8000_sonnet`, `4000_sonnet_v2`, `8000_sonnet_v2` (16.6 MB), `cohort_haiku-sm`, `top1630_haiku-sm`, `emotion-sm_*`, `gap_fill_physical*`, `ab_variant_*`, `benchmark_500`, `property_spike`, and ~10 synset-ID input lists. **Confirm the live DB = curated-props + rescue + remainder.gz.** These are the only copies of paid LLM output → archive outside `output/` (also fixes B2) rather than delete. |
| F9 | `output/baseline_lexicon.sql.gz` (51 MB) | Nothing references it; old schema (lacks concreteness, domains, BNC, seeds); the only DB snapshot in git. Delete, or replace with a current gzipped `PRE_ENRICH`? Related: are the SQL dumps meant to be tracked (C3)? |
| F10 | Unused input spreadsheets: `Cleaned list GPT4…xlsx` (7 MB), `Multilex English.xlsx` (17 MB), `SUBTLEX-UK.xlsx` (25 MB) + their dead `utils.py` constants | Importers read only `Full list…xlsx` and `SUBTLEX-UK-flemmas.xlsx`. CLAUDE.md says raw files belong in `~/.local/share/metaforge/`. Third-party datasets → check redistribution terms. |
| F11 | `data-pipeline/future-work/metaphor-vehicles/` | **LCC data under CC-BY-NC-SA 4.0 (non-commercial).** Licence risk if Metaforge is commercial. Get a licensing opinion before deciding. |
| F12 | `output/aptness_eval_baseline.json` vs `aptness_eval.json` | Same content apart from metadata paths. Keep one. |
| F13 | 4 tracked files that `.gitignore` (`*_results.json`) excludes: `m04_embedding_band_results`, `m04v2_lakoff_band_results`, `mrr_12k_results`, `mrr_8k_results` | `git rm --cached` or add `!` exceptions. Probably resolved by F4/F5. |
| F14 | `data-pipeline/grading/*` (~13 MB) | A dev copy, stale against the live `.worktrees/grading-data`, but possibly the only copy on GitHub. Refresh, drop, or keep? |
| F15 | Chain-generation and gloss tooling (`generate_metaphor_edges.py`, `run_chain_spike.py`, `run_generation_loop.sh`, `metaphor_live_rate.py`, `compare_chain_cohorts.py`, `gloss_backfill*`, `resnap_glossed_corpus.py`, `validate_gloss_backfill.py`, `gloss_reconciliation_analysis.py`, `generation_topics_*.json`) | Gloss promotion finished 2026-06-20 and the Stock Run is parked, but these might seed the unbuilt live-versus-dead forest eval. Lean **keep** for now. |
| F16 | `CHANGELOG.md` + empty `.changelog/` + `changelog-entry`/`changelog-squash` skills | `[Unreleased]` stops around March 2026 and still claims staging = `metaforge.julianit.me` and "GitHub Issues backlog". Catch it up, or drop the mechanism. |
| F17 | `docs/design-system/02_grade_mode/` | 6 files are byte-identical to `01_design_system/`. Grade Mode has shipped. Prune the duplicates (keep its README, which the spec cites)? |
| F18 | `docs/designs/research/Brysbaert-2014-40k-Concreteness-Ratings.pdf` | Unreferenced. Keep as a citation or drop. |
| F19 | `data-pipeline/enrich.sh`, `scripts/m02_s04_*` | Already in PIPELINE.md backlog; listed for completeness. |

## E. Low-value tidies (L — probably keep)

- `web/tsconfig.json` excludes `*.test.ts` from `tsc` and vitest doesn't type-check, so test files are **never type-checked**. This is how test-only drift (A13) goes unnoticed. Worth a decision.
- `web/src/styles/tokens.css` names Playfair / Crimson / JetBrains Mono, but nothing loads them, so the fallback fonts always render.
- `web/src/types/force-graph-augments.d.ts` header vs the local shim `3d-force-graph.d.ts`: one of the two explanations is out of date (check after `npm ci && tsc`).
- `mf-force-graph.ts:306` `labelSize` (never set) and `mf-error-banner` `level: 'warn'` (production never uses it): unused hooks.
- Tests that only assert something was removed (`mf-force-graph.test.ts:224`, `mf-app.test.ts:1345`).
- Unnecessary `export`s on file-local types (`forest/state.ts`, `types/api.ts`, `types/grading.ts`).
- `vite.config.ts` `/health` proxy (nothing calls it); no `e2e` npm script.
- `MetaforgeConcept.png` (3.9 MB, mode 755) could be compressed and have the executable bit dropped.
- `.claude/settings.json` (`{"enabledPlugins": {}}`) is a no-op.
- `deploy/grading/deploy.sh` has skipped step numbers and stale "T11" notes.
- **Gap, not cruft:** there is no `forest.env.example`, though both API units load `/etc/metaforge/forest.env`.

## Checked and not cruft

All web deps, fixtures and ftl strings (`strings-audit.test.ts` enforces them); all 17 `GradingClient` methods; v1 `Label` / `normaliseJudgement` (the live JSONL still has v1 rows); `go.mod` (tidy-clean), `go vet` and `staticcheck` clean; `lib/`; `scripts/pre_commit_secret_scan.py`; `docs/superpowers/*`; `docs/design-system/01_*` (adoption is deferred to the Browse milestone); the core enrichment chain (the thesaurus reads `synset_properties` and `synset_centroids`); `metaphor_spike_1a.py`, `metaphor_graph.py`, `evaluate_cascade.py`, `evaluate_aptness.py` (all imported by live code).
