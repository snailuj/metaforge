# M05 Type-Aligned Structural Matching — Review Loop

Branch: `m05/type-aligned`
Base: `main` (merge-base `4399abff`)
Adapters: pr-review-toolkit, superpowers, standards (ux-designer skipped — no UI changes)
Started: 2026-05-23

## Commits Under Review

```
9977c003 docs(m05): γ-sweep verdict — type-diversity confirmed, γ=0 default for now
25ab7aa9 feat(api,sweeps): M05 S04 prep — Gamma CLI/env + sweep runner γ-axis + Lakoff γ-grid
72426410 feat(forge): M05 S03 — type-diversity bonus in EvaluateCascadePair
46e261b3 feat(db): M05 S02 — load vocab_clusters.dominant_type into CascadeCache
7746783c feat(snap): M05 S01 — propagate property type into vocab_clusters.dominant_type
```

## Files In Scope

- api/cmd/metaforge/main.go
- api/internal/db/cascade_cache.go
- api/internal/db/cascade_cache_test.go
- api/internal/forge/cascade.go
- api/internal/forge/cascade_test.go
- api/internal/handler/cascade_pipeline.go
- api/internal/handler/handler_cascade_test.go
- data-pipeline/SCHEMA.sql
- data-pipeline/scripts/cluster_vocab.py
- data-pipeline/scripts/m04_sweep_runner.py
- data-pipeline/scripts/snap_properties.py
- data-pipeline/scripts/test_snap_properties.py
- data-pipeline/sweeps/m05_lakoff_gamma.yaml
- data-pipeline/sweeps/m05_lakoff_gamma_verdict.md
- docs/inbox/m05-brainstorming-notes.md

## Deferrals Ledger

(empty at round 1 start)

## Pre-existing known issues (informational, NOT deferred from this loop)

These were established at the M04 v1 merge point (commit 985ef696) and have separate deferral entries in earlier review logs:

1. `TestCascadeUnion_LatencyBudget` (api/internal/handler/handler_cascade_test.go:647) — load-sensitive environmental flake; identical 5.3s elapsed at HEAD and on main today (confirmed reproducible on main with M05 reverted). Not an M05 regression.
2. `TestCascadeUnion_ClassicalPairsSurface_AsCandidates` — times out under heavy load (TopK=10000); skipped via `-skip` flag in full-suite runs.

Reviewers should treat these as pre-existing if surfaced; they are not in this loop's deferral ledger.

---

## Round 1 — Combined (2026-05-23T16:50:00Z)

**Adapters dispatched in parallel:** pr-review-toolkit (code-reviewer, silent-failure-hunter, type-design-analyzer), superpowers (code-reviewer), standards (general-purpose).

UX adapter skipped per orchestrator config (no UI changes in scope).

### Items Found (merged, deduped across 5 reviewers)

**IMPORTANT (6):**

- [important] **snap_properties.py is not idempotent for dominant_type** (`data-pipeline/scripts/snap_properties.py:484-516`) — re-snap leaves stale dominant_type on clusters with no matches in current run. Violates CLAUDE.md Idempotency standard. Raised by pr-review-toolkit:code-reviewer, silent-failure-hunter, standards.
  - Decision: **fix** → 5fb3afca
  - Rationale: Real correctness bug; <20 LOC fix; reviewers converged on the same issue.

- [important] **Gamma>0 + CompositionMultiplicative produces unvalidated score shape** (`api/internal/forge/cascade.go:402-430`) — sweep verdict only validated additive composition. Raised by pr-review-toolkit:code-reviewer.
  - Decision: **fix** → 927216ba
  - Rationale: Validate() guard < 10 LOC; matches existing fail-loud-at-startup pattern.

- [important] **γ-sweep verdict overclaims confidence — n=1 inapt sample** (`docs/inbox/m05-brainstorming-notes.md:269`) — separation_score is mean(apt) vs single inapt datum; "M05 hypothesis confirmed" wording is statistically inadequate. Raised by superpowers:code-reviewer.
  - Decision: **fix** → 49e7747e
  - Rationale: Pure documentation tightening; would mislead operator decisions otherwise.

- [important] **Atomic commit hygiene — snap_dropped.jsonl/results.json should be gitignored** (`data-pipeline/output/`) — docs(m05) commit smuggled +45k lines of regenerated diagnostic data. Raised by standards, superpowers.
  - Decision: **fix** → 0d19560c
  - Rationale: Hygiene + commit-message-accuracy; trivial to gitignore + git rm --cached.

- [important] **TypeDiversityBonus + SharedTypesCount not threaded onto forge.Match** (`api/internal/handler/cascade_pipeline.go:320`) — diagnostic surface is dead at wire boundary. Raised by pr-review-toolkit:type-design-analyzer.
  - Decision: **fix** → c175b346
  - Rationale: Wire-up needed for operators to inspect bonus contribution; `omitempty` keeps wire contract identical at Gamma=0.

- [important] **cluster_vocab.py CREATE TABLE — re-run could wipe dominant_type** (`data-pipeline/scripts/cluster_vocab.py:78`) — ordering hazard. Raised by pr-review-toolkit:type-design-analyzer.
  - Decision: **fix** (regression guard test) → b6fb12b9
  - Rationale: cluster_vocab.py already includes dominant_type (added in S01); test locks the invariant.

**LOW (12 surfaced; all addressed):**

- [low] M05 verdict file inherits M04 headings + "ratify SourcesUnion" recommendation. Raised by pr-review-toolkit:code-reviewer, superpowers.
  - Decision: **fix** → 255c29ea (parametrise write_verdict by `axis`/`verdict_title`).
- [low] TypeDiversityBonus doc says SharedTypesCount range 0..7 but implementation is 0..6. Raised by silent-failure-hunter.
  - Decision: **fix** → cb1809df.
- [low] snap_dropped.jsonl loses property_type. Raised by silent-failure-hunter.
  - Decision: **fix** → ee6b27b1 (Fix 2 of snap batch).
- [low] Gamma>0 on all-NULL DB silently emits zero bonus per-request with no signal. Raised by silent-failure-hunter.
  - Decision: **skip** with rationale.
  - Rationale: startup Warn at `cascade_cache.go:86` already covers the all-NULL case with `untyped_pct` field. Per-request observability for partial-coverage DB is a separate concern (would need a counter+periodic-log pattern); cost/value is poor and reviewer's own SHA-suggestion ("Debug-level slog with topic+vehicle pair") would be noise in prod. Real fix is operator awareness of `untyped_pct` startup metric — already exists.
- [low] SharedTypesCount=0 conflates "no shared" vs "shared all unknown". Raised by pr-review-toolkit:code-reviewer, superpowers.
  - Decision: **resolved by other fix** — 7f1afbd3 aligns TypeDiversityBonus pointer with SharedTypesCount, so both fields now agree on "M05 evaluated".
- [low] aptness_rate / separation_score @property absent from JSON dump. Raised by superpowers.
  - Decision: **fix** → 255c29ea (sweep runner now materialises both fields on CellResult).
- [low] M05 type bonus skips when one side has no_properties. Raised by superpowers.
  - Decision: **skip** with rationale.
  - Rationale: Genuine design call for a future milestone. M05's scope is type-diversity bonus on cluster overlap; scoring asymmetric-property pairs is a different feature (would need new bonus shape for "topic has rich type profile, vehicle has none"). Not a defect — the no_properties short-circuit is correct M03/M04 behaviour. Logged as a known design boundary in m05-brainstorming-notes.md.
- [low] Unused `prop_type` binding in snap drop branch. Raised by standards.
  - Decision: **fix** → ee6b27b1 (passes prop_type into _record_drop).
- [low] No handler-level integration test for ClusterTypes plumbing. Raised by standards.
  - Decision: **fix** → c175b346 (B1 fix added `TestForgeSuggest_CascadeEnabled_GammaPositive_SurfacesM05Diagnostics`).
- [low] TypeDiversityMaxDistinct=6 magic — no cross-language guard. Raised by pr-review-toolkit:type-design-analyzer, standards.
  - Decision: **fix** → 15cd3667 (Python test reads Go constant, asserts equality with `len(CANONICAL_TYPES)`).
- [low] ClusterTypes nil-vs-empty design comment not honored. Raised by pr-review-toolkit:type-design-analyzer.
  - Decision: **resolved by other fix** — 7f1afbd3 alignment fix makes the runtime behaviour consistent across both states; semantic doc nuance is now N/A since both states produce identical diagnostic output.
- [medium] Gamma should be a domain newtype (proof-of-validity at construction). Raised by pr-review-toolkit:type-design-analyzer.
  - Decision: **deferred → challenger → re-triaged as fix** → 416ea0b6.
  - Challenger verdict: `reject_defer`, subtype `cost_under_1h`, fix-now sketch was 30-60min / 30-50 LOC. Scope-boundary claim ("touches many call-sites") failed on inspection (Go blast radius: 4 files, 1 construction site). Patch sketch followed verbatim.

**COSMETIC (7):**

- [cosmetic] ClusterTypes map capacity hint 5000 undersized. → **fix** e2dd2ef6 (bumped to 40000 to match Centroids).
- [cosmetic] setdefault(cid, Counter()) wastes ~245k allocations. → **fix** 911b9e76 (defaultdict(Counter)).
- [cosmetic] loadClusterTypes lacks divergence detection. → **fix** 6ef708d1 (slog.Warn on divergence).
- [cosmetic] "other" terminology is fragile across layers. → **skip** with rationale.
  - Rationale: Diagnostic/naming nit. Three-layer terminology is internally consistent (Python CANONICAL_TYPES = 6 discriminating; Python _CANONICAL_ORDER = 7 incl "other"; Go TypeDiversityMaxDistinct = 6 excludes "other"). Cross-language guard test (15cd3667) locks the discriminating-set count. Renaming everything would touch ~10 sites without behaviour change.
- [cosmetic] Per-pair shared slice could be sync.Pool'd. → **skip** with rationale.
  - Rationale: Premature optimisation. Profile-driven optimisation, not standards. M05 ships dormant; perf concern is theoretical until a benchmark shows it material.
- [cosmetic] gamma log key naming consistency. → **fix** cae732fd (renamed to `forge_gamma`).
- [cosmetic] loadClusterTypes comment misdescribes vocab_clusters PK. → **fix** 5d4276b0.

### Deferral Challenges This Round

- **Gamma newtype refactor** (initial defer, challenger dispatched 2026-05-23T17:10:00Z)
  - Verdict: `reject_defer`
  - Verdict subtype: `cost_under_1h`
  - Fix-now cost estimate: time `30-60min`, loc `20-100`
  - Scope-boundary claim "touches many call-sites in tests, fixtures, sweep configs": **fails** — Go blast radius is 4 files / 1 construction site; sweep YAMLs operate on Python dataclass, not Go struct.
  - Why-out-of-scope claim "M05 ships dormant, no active risk + Validate() is second line of defence": **handwavy** — per-request hot path does not re-validate, so construction-time guarantee is the only real defence against post-startup mutation. CLAUDE.md "Refactor Mercilessly" applies.
  - Outcome: re-triage to **fix** → 416ea0b6.

### Critique Sections (persisted verbatim from reviewer responses)

**PRIOR_FINDINGS_CRITIQUE (all 5 reviewers):** prior_reviewer N/A — first round; populated with categories_checked.

**APPLIED_FIXES_CRITIQUE (all 5 reviewers):** N/A — no fixes applied since last round (first round).

**DEFERRAL_LEDGER_REVIEW (all 5 reviewers):** ledger_size: 0; entries: []; summary: "ledger empty".

### Fixes Applied

17 commits across snap, cascade scorer, cascade cache, handler, main, sweep runner, brainstorming notes, gitignore — see git log `ac21a37e..HEAD`.

### Files Modified

- `api/cmd/metaforge/main.go`
- `api/internal/db/cascade_cache.go`
- `api/internal/forge/cascade.go`
- `api/internal/forge/cascade_test.go`
- `api/internal/forge/forge.go`
- `api/internal/forge/forge_test.go`
- `api/internal/handler/cascade_pipeline.go`
- `api/internal/handler/handler_cascade_test.go`
- `data-pipeline/scripts/cluster_vocab.py`
- `data-pipeline/scripts/m04_sweep_runner.py`
- `data-pipeline/scripts/snap_properties.py`
- `data-pipeline/scripts/test_cluster_vocab.py`
- `data-pipeline/scripts/test_m04_sweep_runner.py`
- `data-pipeline/scripts/test_snap_properties.py`
- `data-pipeline/sweeps/m04_embedding_band.yaml`
- `data-pipeline/sweeps/m04v2_lakoff_band.yaml`
- `data-pipeline/sweeps/m05_lakoff_gamma.yaml`
- `docs/inbox/m05-brainstorming-notes.md`
- `.gitignore`

### Test Results

- Go: full suite passes (skipping known flake `TestCascadeUnion_LatencyBudget` + heavy-load `TestCascadeUnion_ClassicalPairsSurface_AsCandidates`). Forge package 1.27s, db 40.13s, handler 391.92s, thesaurus 185.70s.
- Python: data-pipeline pytest passes (exit 0).
- Post-Gamma-newtype targeted re-test: forge + handler packages pass (0.03s + 7.31s).

### Cumulative

Total rounds: 1 | Items resolved: 27 (17 fixes + 6 skips + 4 resolved-by-other-fix) | Active deferrals: 0 | Superseded deferrals: 1 (Gamma newtype → fixed via challenger re-triage) | Elapsed: ~3h


---

## Round 2 — Combined (2026-05-23T17:30:00Z)

**Adapters dispatched in parallel (same 5 as Round 1).**

### Items Found (merged across 5 reviewers, 21 unique)

**IMPORTANT (7) — all fixed in this round:**

- [important] loadClusterTypes divergence check has false-negative branches (NULL→non-NULL and non-NULL→NULL silently overwrite) → **fix** 602f0b1b
- [important] divergence Warn unbounded → log-flood risk → **fix** 93febc6d (cap at 10 + summary Error)
- [important] Committed verdict file stale (still M04 title) — write_verdict was parametrised in R1 but artefact never regenerated → **fix** 89e51a94 (regenerated against current code)
- [important] forge.Match.SharedTypesCount int+omitempty defeats wire-shape diagnostic → **fix** e9f3078d (int → *int)
- [important] envFloat swallows malformed METAFORGE_FORGE_GAMMA → silently defaults to 0 → **fix** c0545c38 (explicit ParseFloat + log.Fatalf)
- [important] snap_dropped.jsonl persists across DB rollback (misleading authoritative artefact) → **fix** 46efc6fc (atomic-rename .tmp→canonical post-commit) + 5df7384a (CLAUDE.md doc)
- [important] m04_sweep_runner __getattribute__ override leaks computation exceptions through plain attribute access → **fix** 16692031 (replace with @property)

**MEDIUM (4) — all re-triaged via challenger to fix:**

- [medium] GammaWeight newtype bypassable through untyped numeric literals — defined-type form is informational documentation only, not unforgeable. Challenger: `reject_defer / cost_under_1h` → **fix** 533dc038 (struct-wrap with unexported field + .Value() accessor)
- [medium] vocab_clusters.dominant_type has no CHECK constraint — breaks SCHEMA convention; cross-language test pins count only, not contents. Challenger: `reject_defer / cost_under_1h` (DROP+CREATE on every cluster_vocab run = no migration concern) → **fix** 70234123 (CHECK constraint + set-contents test)
- [medium] _canonical_type silently groups None/empty/unknown/explicit-other into single "other" bucket. Challenger: `reject_defer / scope_claim_false` (JSONL stores canonicalised value, jq can't recover) → **fix** a39e5f0a (3-bucket Counter + summary log)
- [medium] t.Skip on M05 integration test silently greens stale-DB CI environments. Challenger: `reject_defer / cost_under_1h` (h.cache.ClusterTypes is mutable public map) → **fix** (bundled into 533dc038 by pre-commit hook concurrency; t.Skip removed, in-place mutation injected)

**LOW (6):**

- [low] ClusterTypes empty-map check inconsistent with docstring → **fix** 78b4af43 (tighten to len > 0)
- [low] cluster_vocab.py DROP+CREATE wipes dominant_type with no operator notification → **fix** 31869682 (logger.warning on completion)
- [low] data-pipeline/CLAUDE.md Operations §3 missing property_type schema update → **fix** 5df7384a
- [low] R1's "Gamma>0 on all-NULL DB silent zero per-request log" skip rationale partly inaccurate (startup Warn only covers all-NULL extreme, not partial coverage) → **skip** with refined rationale: partial-coverage observability would need a periodic counter (M07-class observability work, not M05 scope). The pointed-out wording overclaim in R1 is fair; the skip decision still holds.
- [low] R1's "ClusterTypes nil-vs-empty resolved by alignment fix" claim was partial — the alignment fixed in-memory struct but not wire shape. **Now resolved** by Batch C fixes (e9f3078d *int + 78b4af43 len>0 gate).
- [low] R1's "SharedTypesCount=0 conflates 'no shared' vs 'shared all unknown'" — same as above, **now resolved** by e9f3078d.

**COSMETIC (4):**

- [cosmetic] cascade_cache.go map-size hint comment overstates row vs cluster count → **skip** (1-line nit, no behaviour impact; comment still useful)
- [cosmetic] TypeDiversityMaxDistinct dual-use as max + denom-1 → **skip** (constant is correctly used; naming is local to forge package)
- [cosmetic] Permanent commit subject 9977c003 says "confirmed" while body downgraded → **skip** (cannot rewrite landed history without force-push)
- [cosmetic] Cross-language guard regex substring-match limitation → **skip** (current test catches what it set out to catch; tightening regex is defensive)

**REVIEWER ERRORS (2):**

- [reviewer-error] R2.STD claimed no direct NewGamma unit test exists → **skip**: `TestNewGamma_RejectsNegativeNaNInf` (cascade_test.go:378) and `TestNewGamma_AcceptsZeroAndPositive` (cascade_test.go:407) both exist from R1 fix 416ea0b6.
- [reviewer-error] R2.SP.CR's "GammaWeight pattern drift vs Composition/CandidateMode" — both patterns (constructor vs Valid()) are defensible Go idioms. Subsumed by struct-wrap fix anyway (NewGamma is now the ONLY construction path, more strictly enforced than .Valid()).

### Deferral Challenges This Round

Four challengers dispatched:

1. **GammaWeight encapsulation** (2026-05-23T17:50:00Z) — `reject_defer / cost_under_1h`. Scope claim "broader refactor of all 4 float64 params" failed (Alpha/DCap/ConcretenessThreshold have no operator entry point, struct-wrap precedent does not apply). 30-60min sketch followed → fix 533dc038.

2. **dominant_type CHECK constraint** (2026-05-23T17:50:00Z) — `reject_defer / cost_under_1h`. Scope claim "live-DB migration required" failed (cluster_vocab.py DROP+CREATE recreates table every run). <30min sketch followed → fix 70234123.

3. **_canonical_type 3-bucket Counter** (2026-05-23T17:50:00Z) — `reject_defer / scope_claim_false`. Deferral claimed downstream jq could recover the breakdown; challenger proved snap_properties.py:311 writes the CANONICAL value to JSONL, so the breakdown is unrecoverable downstream. <30min → fix a39e5f0a.

4. **t.Skip on M05 integration test** (2026-05-23T17:50:00Z) — `reject_defer / cost_under_1h`. Scope claim "synthetic in-memory cache pattern is structural refactor" failed (h.cache.ClusterTypes is mutable public map). <30min → fix bundled into 533dc038.

All 4 challengers verdict-confirmed the upgraded skill's "fix-now bias" — every deferral attempted in R2 was rejected and re-triaged to fix. **The deferral discipline is working.**

### Critique Sections (persisted verbatim from reviewer responses)

(Full responses preserved in the orchestrator's transcript; per-section verdicts and per-fix assessments are above.)

### Fixes Applied (13 commits this round)

702341237 feat(schema): CHECK constraint on vocab_clusters.dominant_type closes rename-drift gap
533dc038 refactor(forge): GammaWeight struct-wrap — unforgeable construction via NewGamma
a39e5f0a feat(snap): three-bucket canonical_type breakdown closes silent-grouping observability gap
78b4af43 fix(forge): tighten ClusterTypes gate to len > 0 (match docstring)
c0545c38 fix(main): malformed METAFORGE_FORGE_GAMMA fails loud instead of silently defaulting
e9f3078d fix(forge): emit shared_types_count=0 on wire when M05 finds zero distinct types
5df7384a docs(data-pipeline): snap_dropped.jsonl schema includes property_type + atomic-rename note
46efc6fc fix(snap_properties): atomic-rename snap_dropped.jsonl post-commit
31869682 feat(cluster_vocab): warn operator that dominant_type was wiped on rebuild
16692031 refactor(m04_sweep_runner): replace CellResult __getattribute__ with @property accessors
93febc6d fix(cascade_cache): rate-limit divergence Warn flood with summary Error
602f0b1b fix(cascade_cache): tighten loadClusterTypes divergence check on canonical pair
89e51a94 docs(m05): regenerate verdict with M05-axis-aware title and content

### Files Modified

- api/cmd/metaforge/main.go (+main_test.go new)
- api/internal/db/cascade_cache.go + cascade_cache_test.go
- api/internal/forge/cascade.go + cascade_test.go
- api/internal/forge/forge.go + forge_test.go
- api/internal/handler/cascade_pipeline.go + handler_cascade_test.go
- data-pipeline/CLAUDE.md
- data-pipeline/SCHEMA.sql
- data-pipeline/scripts/cluster_vocab.py + test_cluster_vocab.py
- data-pipeline/scripts/m04_sweep_runner.py + test_m04_sweep_runner.py
- data-pipeline/scripts/snap_properties.py + test_snap_properties.py
- data-pipeline/sweeps/m05_lakoff_gamma_verdict.md
- .gitignore

### Test Results

- Go: full suite passes (excluding known flake + heavy-load skip). cmd/metaforge 4.76s, blobconv 0.004s, db 39.88s, forge 2.03s, handler 239.26s, observe 0.02s, thesaurus 111.15s — all green.
- Python: data-pipeline pytest passes (exit 0).
- Targeted post-Batch-D retest: forge + handler + db packages green.

### Cumulative

Total rounds: 2 | Items resolved this round: 21 (13 fix + 6 skip + 2 reviewer-error) | Active deferrals: 0 (4 attempted, all challenged + re-triaged to fix) | Superseded deferrals (R1 + R2): 5 | Elapsed: ~5h

