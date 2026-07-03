# State of Metaforge — breadth survey (2026-06-22)

> Validate-first pass across six surfaces (frontend build, frontend UX/A11y, backend Go+pipeline, infra/deploy+CI, forge/judge/generation, repo/branches). Findings are read-and-verify; the deep forge thread is the binding constraint on the product KPI. A held "Prototype queue (Lane B)" is parked at the bottom — to seed *after* this pass.

## 1. Executive summary

The runtime surfaces are healthy and the engineering thread is in good order — but the product KPI is blocked, not stuck. All three live services (prod API :8080, staging API :8081, grading sidecar :53775) respond on loopback and public HTTPS; the frontend passes all four gates (tsc 0, 414 Vitest, vite build, 9 Playwright e2e); the Python pipeline (1016) and grading sidecar (185) are green. The two real engineering wounds are (a) **zero CI/CD** — `.github` is absent entirely, which is an MVP-required item, while two Go cascade tests are already red (both DB-state drift, not logic regressions: stale velvet/silence parity crib + a truth/hammer embedding-coverage hole); and (b) **the metaphor-graph substrate does not exist yet** — `metaphor_bridges` is 0 rows in every DB, all 90 resolved verdicts sit in JSONL on the grading-live branch, and `separation_score → 0.3` is fully blocked on the judge+grading bootstrap because the structural property-overlap family (M02/M03/M04/M05) is exhausted at chance (AUC ≈ 0.50). The cheapest unblock is the **Liveness Re-measure on sense-cleaned gold** (~$2–5, no new code; gloss-backfill already lifted snap accuracy 52%→78%). On the UX side the grading views — Julian's daily-use, mobile-via-remote surface — carry real operator-productivity gaps (unstyled grade-view-toggle, missing loading states, dropped focus on verdict submit, Notes button absent outside topic view, mobile grade-top density). Repo hygiene is the quiet liability: 29 branches, 9 worktrees, a 310-commit integration tip (`generation/emit-the-sense`) that subsumes most milestones but does **not** subsume judge-harness, completion-harness, or tmp-head-test — any careless merge to main strands them.

## 2. Surface-by-surface

| Surface | Works | Top risk | Top opportunity |
|---|---|---|---|
| frontend build (Lit+Vite+TS, web/) | yes | Single 1.4 MB JS bundle, no code-splitting (low) | Code-split 3d-force-graph / Three.js (M/med) |
| frontend UX/IA/A11y | unknown (read-only) | Unstyled grade-view-toggle → mobile overflow (high) | Lift grade-view-toggle to styled segmented control (S/high) |
| backend (Go API + pipeline) | partial | 2 Go tests red (DB drift) + stale `lexicon_v2.sql` (high) | Update velvet/silence parity fixture (S/high) |
| infra/deploy + CI | partial | No CI/CD at all — `.github` absent (high) | Minimal GitHub Actions CI: go+npm+sidecar (S/high) |
| forge/judge/generation | partial | `metaphor_bridges` 0 rows — no graph to complete (high) | Liveness Re-measure on sense-cleaned gold (S/high) |
| repo/branches/worktrees | unknown | 29 branches / 9 worktrees; 3 unmerged branches not subsumed by integration tip (high) | Merge `generation/emit-the-sense` → main (M/high) |

jsjsjs Thesaurus not evaluated?

## 3. Risk register (high → low, tagged by surface)

### High
- **[forge]** `metaphor_bridges` is 0 rows everywhere — the metaphor-graph-completion hypothesis has no graph to complete. All 90 resolved verdicts are JSONL on a deploy branch, never ingested. The 9-task JSONL→bridges plan exists but has never run; Block 3 cannot start. JSJSJS: known issue, calculated risk that pays for itself by retaining maximum flexibility and rapid prototyping of forge graph algo

- **[forge]** `separation_score` target (>0.3) is entirely blocked on the judge+grading bootstrap. The pointwise-similarity family (M02/M03/M04/M05) is exhausted; the only remaining lever is judged-edge substrate → completion → distilled judge feeding the forge. JSJSJS: known issue, this just restates the current WIP
None of sense-clean→re-measure→scaled-grading→promotion is done. JSJSJS: now done

- **[forge]** Single-word-WordNet-synset vehicle requirement filters out the most evocative Phase B candidates (pressed flower, supersaturation, wax cylinder, groundwater); ~3.5% vehicle-skip rate. Phrase-as-node (Block 2) is the structural fix, not yet started. JSJSJS: known issue, current WIP includes this but check captured in PIPELINE 

- **[infra]** No CI/CD whatsoever — `.github` absent, no other CI config. MVP-required. Two Go packages already failing with no automated gate; CLAUDE.md's "no merging with failing tests" is unenforceable. JSJSJS: deprioritise, single dev project with no active users, CI/CD is overkill

- **[backend/infra]** Two Go test packages red on `generation/emit-the-sense`: `internal/forge` parity (silence/velvet — crib expects `no_properties`, DB now has 12 props) and `internal/handler` union (truth/hammer not in 6180 candidates even at TopK=10000, DMax=2.0). Both DB-state drift, not logic regressions; both would red any new CI gate. JSJSJS: quick fix only, if no quick fix available just rip out the test. This project is not mature enough to harden around DB state

- **[backend]** `lexicon_v2.sql` (committed dump, May 26) is 9 tables behind the live DB: missing metaphor_bridges, metaphor_bridge_steps, metaphor_judgments, sense_attributes, domains, bnc_frequencies, seed_meta, seed_sources, graph_edges. Any CI restore from this dump produces a schema-incompatible DB. JSJSJS: quick fix
- **[ux]** ARIA combobox incomplete in `mf-search-bar`: input has aria-expanded/aria-autocomplete/aria-activedescendant but no `role='combobox'` and no aria-controls to the `<ul role='listbox'>` (siblings in shadow root → no ownership tree). Screen readers won't announce suggestions on Arrow Down. (lines 317–355) JSJSJS: quick fix
- **[ux]** `mf-topic-picker` (grade mode) has no ARIA at all — filter input no aria-label/role, `<ul>` no listbox, `<li>` no option. Opaque on a screen reader or keyboard-only. JSJSJS: ARIA compatibility not required for the grading tool
- **[ux]** 3D graph (`mf-force-graph`) entirely inaccessible to keyboard/AT — WebGL canvas, no keyboard path, no fallback. In browse mode on mobile it always loads (touch-grab is the only option); the chip tooltip says "right-click to copy" with no mobile equivalent. (mf-force-graph.ts 157–158; mf-results-panel.ts 288) JSJSJS: skip
- **[ux]** Breakpoint mismatch: results panel 768px (CSS media) vs grade-mode layout 900px (JS viewportWidth). Between 769–899px the panel renders desktop-expanded while grade mode shows mobile layout; two uncoordinated systems that diverge if either threshold moves. (mf-results-panel.ts 226; mf-app.ts 1291) JSJSJS: defer
- **[ux]** `grade-view-toggle` has `role='group'` but no grouping styles (no `.grade-view-toggle` CSS); renders four unstyled default buttons. On mobile (≤375px) these four + Signal Report button overflow/wrap unpredictably. (mf-app.ts 808–824) JSJSJS: skip
- **[repo]** Branch sprawl: 29 local branches, 9 worktrees. Integration tip `generation/emit-the-sense` (310 ahead) subsumes grading-code, sqlunet-import, enrich-stage-a, ux-tag-notes-signal, gloss-reconciliation, schema-base, eyeballer, grading-tool, grading-rhs-affordances — but **not** judge-harness (12 unique), completion-harness (6 unique), or tmp-head-test (21 unique). Any merge/rebase missing those three silently strands them. JSJSJS: fix with brainstorm
- **[repo]** `grading-data` is a live auto-commit data stream (15-min wip autosaves from the grading-live service), 247 ahead, never meant to merge — but has no README/branch-purpose note; a future operator may "clean it up" and destroy grading-corpus history. JSJSJS: fix

### Med
- **[backend/forge]** metaphor_bridges, metaphor_bridge_steps, metaphor_judgments exist in schema but 0 rows — the graph layer is unmaterialised. Downstream code/tests assuming populated bridges silently operate on empty results. JSJSJS: defer
- **[backend/infra]** `test_export_chain_glosses.py` / `test_resnap_glossed_corpus.py` use bare/CWD-relative imports — pytest from repo root (the documented command) fails with ModuleNotFoundError; passes only from `data-pipeline/scripts/`. The CLAUDE.md CI command triggers this. JSJSJS: defer all CI/CD work
- **[infra]** Deploy scripts have no test gate: `deploy/{production,staging}/deploy.sh` do git pull → build → restart → health-check but never run tests. A broken-but-compiling commit reaches production if `/health` responds. JSJSJS: defer
- **[infra]** Python test-runner path is fragile/undocumented: scripts tests need `data-pipeline/.venv` (numpy/fasttext); sidecar tests need `.worktrees/next/data-pipeline/.venv` (no numpy); neither is the repo-root `.venv` in CLAUDE.md Setup. Wrong-venv CI hits 42 collection errors (confirmed: no module numpy). JSJSJS: fix

- **[infra]** `deploy/staging/Caddyfile.active` is committed (not gitignored) and references the now-gone `.worktrees/main/web/dist` path — a stale artefact contradicting the `*.active` gitignore convention. JSJSJS: cleanup
- **[forge]** Grading-app Round 1 reconciliation (the immediate unblocked Next) is NOT done: stock context + sense-checker skip button + code/data separation in grading-live + ChainStore fall-through reader TDD. Blocks sense-check labelling → Liveness Re-measure. JSJSJS: fix if not already done
- **[forge]** Gold corpus is sense-contaminated (operator graded different senses than snapped synsets; named cases fault=tectonic-vs-tennis, heliotrope=flower-vs-mineral). Every κ figure (self 0.47, judge 0.332) is deflated by sense-noise not taste variance; Gloss-Reconciliation shows 15.6% silent noise in unflagged endpoints. True judge quality likely > 0.332. JSJSJS: flag with me if still incomplete 

- **[ux]** Grade-mode loading states absent — `initGradeMode()`/`handleTopicSelected()` are async with no in-flight indicator; slow topic switch shows empty list indistinguishable from "no chains". Browse-mode loading ring not reused. (mf-app.ts 615–630) JSJSJS: DEFER

- **[ux]** Fixed Notes button only appears in `renderGradeModeMobile` (topic view) — absent in walk, regrade, sensecheck. Mobile operator has no design-notes access while walking/blind-regrading/sense-checking. (mf-app.ts 1154–1165, 1174–1265) jsjsjs: defer

- **[ux]** Focus management missing across grade views — verdict submit sets `selectedChain=null`, unmounts the panel, focus falls to body; walk auto-advance drops focus too. On mobile the operator must reach up to tap a card. (mf-app.ts handleVerdictSubmit 855) jsjsjs: fix
- **[ux]** `mf-topic-picker` list items suppress focus outline (`outline:none` line 31) — keyboard nav has no visible focus indicator. jsjsjs: skip
- **[ux]** Walk-bar wraps poorly on 375px (Prev / counter / "N left" / Next / "✓ graded" / dwell text / Skip-graded); flex-wrap produces a multi-line toolbar; position readout and dwell text repeat the same "which-out-of-how-many" in two framings. (mf-grade-walk.ts 100–113) jsjsjs: fix
- **[ux]** `grade-top` always pads `padding-right:9rem` for the mode-toggle-bar; on 375px that leaves ~195px for 4 toggle buttons + Signal Report + topic picker + path filter → overflow/wrap. (mf-app.ts 178) jsjsjs: fix
- **[ux]** `mf-error-banner` has a `level` prop ('error'|'warn') but mf-app always renders default 'error' red — pending-verdicts retry messages (informational) render with full error weight. (mf-error-banner.ts 17; mf-app.ts 1270): jsjsjs: fix

### Low - jsjsjs: skip items unless noted otherwise
- **[frontend]** Single 1.4 MB JS bundle (3d-force-graph + Three.js), no code-splitting; build already warns. Parse cost noticeable on low-end mobile; no architectural urgency yet.
- **[frontend]** ECONNREFUSED :3000 stderr during unit tests (mf-app.test.ts) — graceful real-fetch failure; tests pass but noise could mask a real CI connectivity failure.
- **[backend]** `lemma_embeddings` has 56,181 entries vs 107,519 synsets (~half coverage); embedding-path candidate generation sparse for rare/abstract lemmas — the truth/hammer miss is one visible symptom. jsjsjs: defer to backlog
- **[forge]** DB provenance drift — no per-row (model, prompt_variant, run_date), so Go parity fixtures silently desync with DB state as enrichment accumulates.jsjsjs: fix

- **[infra]** Grading sidecar `deploy.sh` uses `sleep 2` health-check timing rather than polling-until-ready — false positive possible under load. jsjsjs: fix
- **[ux]** was-prior verdict affordance (inset box-shadow #4d5566) is very low-contrast with no aria-pressed/aria-current; screen readers won't convey prior selection. (mf-grade-panel.ts 100, 315–320)
- **[ux]** `/` focus-shortcut hint is small muted text many users miss; not present in grade mode.
- **[ux]** `mf-design-notes` Ctrl/Cmd+S only; 30s auto-save timer never surfaced (no saved/unsaved indicator). On mobile the Save button is the only affordance.
- **[ux]** `mf-results-panel` collapsed expand button (left:0,top:0) may overlap the absolute search-bar on small screens; panel not rendered at all when result is null. jsjsjs: defer
- **[repo]** `tmp-head-test` (21 commits, last 2026-06-08) appears a duplicate mobile-walk UAT series also landed via sqlunet-import/grading-code; risk of losing a non-duplicate fix, or dead weight with a misleading name. jsjsjs: cleanup
- **[repo]** `production` worktree is on branch `production` (746 behind main, 0 unique) — frozen deploy snapshot; needs a clear "DO NOT rebase/merge" note.
- **[repo]** `feat/umami-analytics` (4 unique, ~3mo old) and `feat/steal-shamelessly` (2 unique, ~3mo) untouched since March, not in PIPELINE, touch web/ files 200+ commits have since changed — merge now is a conflict minefield. jsjsjs: remove
- **[repo]** `loop-meta` has 1 docs-only unique commit; cosmetic.

### Colour-contrast note (med, ux)
`--colour-text-muted` (#6b6560) on `--colour-bg-primary` (#1a1a2e) ≈ 3.2:1 — below WCAG AA 4.5:1 for normal text. Used for search placeholder, `/` hint, grade-panel group labels (0.75rem), sense-label (0.68rem), last-saved (0.78rem), walk dwell text, browse idle prompt. Small sizes (0.68–0.75rem) worsen it. Primary action buttons and chain text are adequately contrasted.

> Scope note: the frontend is a single-operator internal tool, so WCAG impact is bounded — but Julian works on mobile via remote control, so the mobile/focus/density gaps are operator-productivity issues, not theoretical accessibility. The 3D-graph A11y gap is architectural (needs a separate list view) — noted, not blocking. The two Go failures predate this branch (no Go source touched on emit-the-sense).

## 4. Opportunity backlog (Inbox-ready, value→effort, tagged)

### value: high
- Add minimal GitHub Actions CI (`.github/workflows/ci.yml`): job1 `go test ./...` (api/), job2 `npm test -- --run` (web/), job3 `pytest data-pipeline/grading_sidecar/tests/` (no-numpy subset); skip the 1016-test scripts suite (nightly). Covers 414 web + ~300 Go + 185 sidecar per PR; satisfies MVP-required CI/CD. [S/high · infra] jsjsjs: skip
- Lift `grade-view-toggle` to a styled segmented control matching `.path-filter` (copy the bordered inline-flex block + aria-pressed); fixes mobile overflow — the 4 view buttons fit one row. [S/high · ux]jsjsjs: fix
- Liveness Re-measure on sense-cleaned gold (~$2–5, ~565 pairings) using the existing judge harness; gloss-backfill prerequisite is DONE (52%→78%); gives the first reliable post-clean κ and a deploy/no-deploy call for Block 3. No new code; operator-go only. [S/high · forge] jsjsjs: done
- Grading-app Round 1 reconciliation: ChainStore fall-through reader + sense-checker skip button + code/data separation in grading-live (3 scoped TDD tasks); unblocks sense-check labelling → Liveness Re-measure → Block 2 step-snap audit. [S/high · forge] jsjsjs: skip, obsolete
- Update cascade parity fixture for the silence/velvet pair (crib `no_properties` → `scored` + numeric fields; re-run Python or update manually); restores `internal/forge` to green. [S/high · backend] jsjsjs: fix
- Deploy the 3,125 Phase B stock chains (chain-topics_stock.jsonl, rescued at a23b0107) to `.worktrees/next` for grading — expands the gradeable corpus 1.3× with no new generation spend; the ChainStore reader makes them visible. [S/high · forge] jsjsjs: fix
- Diagnose/fix the truth/hammer union miss: query `lemma_embeddings` to measure actual truth↔hammer cosine and confirm whether it's within [0,2.0]; decide stale-claim vs coverage hole vs `t.Skip` with a pointer. [M/high · backend] jsjsjs: fix
- Merge `generation/emit-the-sense` → main (the integration tip; 310 ahead, 0 behind) — lands 5+ milestones in one PR; everything else sequences off this event. [M/high · repo] jsjsjs: done
- Merge `metaphor-graph/judge-harness` → main (12 unique; Stage-2 liveness harness, κ 0.332 MARGINAL PASS + 2026-06-22 re-measure lift to 0.335; Phase B unblock). [S/high · repo] jsjsjs: fix
- Reduce grade-top density on mobile — conditionally omit topic picker + path filter in walk/regrade/sensecheck (they aren't needed there); halves grade-top height and frees the 9rem padding-right concern. [M/high · ux] jsjsjs: fix
- Materialise `metaphor_bridges` from the graded corpus (~90 paths) — turns verdicts into queryable rows; gated on Block 2 (phrase-as-node + step-snap audit) per Block 3 sequencing. [L/high · forge] jsjsjs: will fix when ready
- Compositor (forge runtime) design once edge-harvest substrate is populated — fine-tuned-local or conditioned-SOTA renders a harvested (topic_synset, vehicle_synset) seed with modifiers/register at query time; may shift the KPI from separation_score to judged-edge acceptance. [L/high · forge] jsjsjs: known future work

### value: med
- Code-split 3d-force-graph / Three.js (lazy-import the graph component on demand) — halves initial parse cost and clears the Rollup chunk-size warning. [M/med · frontend] jsjsjs: defer
- Add loading indicators in grade mode (per-async `gradeLoading` @state + reuse `.loading-ring`/`.status-message`) — kills the blank-on-slow-network ambiguity. [S/med · ux] jsjsjs: fix
- Surface the Notes button + overlay across walk/regrade/sensecheck by lifting it to `render()` (the overlay is self-contained). [S/med · ux] jsjsjs: skip
- Return focus to a sensible element after verdict submit — topic view → chain-list/first card; walk view → `[data-testid=walk-next]`. [S/med · ux] jsjsjs: fix
- Complete the ARIA combobox in `mf-search-bar` (add `role='combobox'`, `id`/`aria-controls` to the listbox) — closes WCAG 4.1.2 with three attribute additions, no behaviour change. [S/med · ux] jsjsjs: skip
- Add ARIA to `mf-topic-picker` (aria-label + combobox/controls/expanded on the input; listbox + option/aria-selected on the list) — enables keyboard+SR use, no behaviour change. [S/med · ux] jsjsjs: skip
- Add visible `:focus-visible` indicators to grade-panel verdict/linkage/tier/chip/conf buttons (gold outline matching the chip style). [S/med · ux] jsjsjs: skip
- Add a result/chain count + progress summary after topic load ("23 chains — 8 graded, 15 ungraded"); data already in gradeChains + verdictedSignatures; valuable on mobile with no graph overview. [S/med · ux] jsjsjs: fix
- Add a keyboard-accessible visually-hidden `aria-live` summary for the 3D graph in browse mode (central node + synonym/hypernym/hyponym counts), fed from the same LookupResult prop. [M/med · ux] jsjsjs: fix
- Replace right-click copy with a long-press / explicit copy button on mobile (the `navigator.clipboard` call is already there). [M/med · ux] jsjsjs: fix
- Align mobile/desktop breakpoints to one value (`--mf-desktop-breakpoint`) so the 768px CSS and 900px JS thresholds stay in sync. [S/med · ux] jsjsjs: fix
- Regenerate `lexicon_v2.sql` from the live DB (`.dump`); consider schema-only (`--schema`) + separate data restore given the 780 MB size. [S/med · backend] jsjsjs: fix with schema-only and data restore step

- Add a conftest.py to `data-pipeline/scripts/` (sys.path.insert) so pytest runs from repo root without ModuleNotFoundError, matching the documented command. [S/med · backend] jsjsjs: quick fix
- Add a test-gate step to deploy scripts (`go test ./... || exit 1`, `npm test -- --run || exit 1` after build) — local safety net independent of CI. [S/med · infra] jsjsjs: fix
- Write a repo-root Makefile (`make test`/`build`/`deploy`) that unifies the three test invocations and documents which venv per suite. [S/med · infra] jsjsjs: fix
- Merge `metaphor-graph/completion-harness` → main (6 unique; learning-curve + path-geometry harness; the verified max_hop_cos 0.64–0.67 result feeds judge feature selection). [S/med · repo] jsjsjs: fix
- Investigate and archive/delete `tmp-head-test` (`git diff tmp-head-test generation/emit-the-sense -- data-pipeline/ web/`); cherry-pick if unique, delete if duplicate. [S/med · repo] jsjsjs: fix
- Archive fully-merged historic branches (spike/*, m02/*, m03/*, review/*, staging, workspace/eval-experiments, loop, loop-meta) — 0 unique commits each; cleans `git branch` and `for-each-ref` scans. [S/med · repo] jsjsjs: fix
- Linkage judge re-tune on coherent labels — PARKED until phrase-as-node (Block 2) rewrites bad_head; reasoned-verdicts-in-few-shot + corrected merge def are banked in PIPELINE.md. [M/med · forge] jsjsjs: todo after phrase-as-node
- Block 3 JSONL→bridges materialisation (the existing 9-task plan) once Block 2 lands — turns 90 verdicts into queryable rows, unblocks completion experiments. [M/med · forge] jsjsjs: todo after phrase-as-node

### value: low
- Mock/stub network in unit tests to suppress the ECONNREFUSED :3000 stderr (fetch-mock or vi.stubGlobal). [S/low · frontend]
- Add a vitest typecheck project so type errors surface during the test run without a separate tsc step. [S/low · frontend]
- Use `level='warn'` on the pending-verdicts banner (amber) and keep default 'error' for auth/load failures — restores the designed semantic distinction. [S/low · ux] jsjsjs: fix
- Fix the `test_resnap_glossed_corpus.py` import path for root-invocation (`Path(__file__).parent` or a conftest.py). [S/low · forge]
- Track the `Caddyfile.active` stale artefact — gitignore it (per the `*.active` convention) or update it to the current topology. [S/low · infra] jsjsjs: fix
- Add a branch-purpose note for `grading-data` ("LIVE DATA STREAM — do not merge or delete") in CLAUDE.md / PIPELINE.md or via `git branch --edit-description`. [S/low · repo] jsjsjs: fix
- Remove the `.worktrees/qodo-triage` worktree (on review/m01-and-snap-memopt, fully merged) — `git worktree remove --force`. [S/low · repo] jsjsjs: fix
- Decide the fate of `feat/umami-analytics` and `feat/steal-shamelessly` (cherry-pick the Umami script if analytics still wanted; close if superseded). [M/low · repo] jsjsjs: kill them

## 5. Prototype queue (held — Lane B)

> Operator-chosen UX-prototype targets. **Held until the validate-first pass above lands.** Seed these *after*, not before. One line each on what the prototype should explore.

- **Bridge feature** — prototype the user-facing surfacing of a harvested `(topic_synset → vehicle_synset)` bridge: how a single judged metaphor edge is presented, justified, and acted on in the UI once `metaphor_bridges` is materialised (the substrate this whole report says is still 0 rows).
- **3D graph navigation / 2nd-order edge nodes** — prototype rendering and traversing second-order edge nodes in the force graph (the MVP-required "2nd-Order Edge Node Rendering"), and a keyboard/touch-navigable path through the 3D scene that doubles as the accessible fallback the A11y review flagged.
- **Forge UI** — prototype the session-conditioned generation front-end (topic blend + sensibility knobs) that the forge-not-index thesis calls for, sitting on top of the cascade `/forge/suggest` endpoint and, later, the distilled judge.
- **Phrase-as-Node (deferred sense-SET architecture)** — prototype the phrase-as-node / sense-SET representation (Block 2): how multi-word evocative vehicles (pressed flower, supersaturation) become first-class graph nodes, unblocking the ~3.5% vehicle-skip and making intermediate path steps sense-clean for max_hop_cos path completion.
