# STATUS — Context-free edge population (glanceable dashboard)

_Last update: 2026-06-03, **checkpoint C8 — DECISION-READY + Council-hardened.** See `FINAL_REPORT.md` + `ALGORITHMS.md`._

## Council-hardening pass (added after the core investigation)
- **Operator-requested approaches tested & folded in:** unified-graph multi-hop traversal (uniform PageRank + AA/RA/CN/BFS), signal-**guided** beam search (4 schemes × depth{2,3} × beam{300–2000}), **hub-penalty** variant (down-weight god-node hops) — all NOT VIABLE; gloss-as-features (4th substrate) — NOT VIABLE; tiered LLM **judge feasibility** (64–75% vs Julian, κ 0.31–0.44, zero FP).
- **11-agent fact-check** re-ran every harness vs the report: 10/11 `MATCH`; **1 real bug found & fixed** (PageRank all-zero transition matrix → corrected to AUC 0.62, still anti-correlated; re-run). Cosmetic precision fixes applied throughout.
- **`ALGORITHMS.md`** added: data structures + faithful pseudocode per approach (verified against code).
- **Completeness + Feasibility(cost+time) + Correctness** sections added for the Council's three test axes.
- Spend updated to true **$6.65** (was the judge probe).


## NEEDS_OPERATOR
_(none blocking. One decision is teed up for you — see "Operator decision" below — but the investigation is conclusive and does not require it to stand.)_

## Bottom line
**Do not build a derivation/retrieval pipeline — it is refuted 5 ways and on human labels. Generate edges per-topic (cheap), and put the ≤4×/few-weeks budget into the one thing that actually gates quality at scale: an automated live/dead JUDGE calibrated to your grading (which does not yet exist).**

- **Primary hypothesis (derive from the 80k enrichments): FALSE.** Shared-features AUC 0.55 / recall 2% / anti-correlated; embeddings anti-correlated (median apt rank 2,870/81k); WordNet relations 0/7; only 0.31% of an LLM's own claimed bridge-features are in both concepts' enrichments. **Multi-hop unified-graph traversal (operator-requested) also fails:** personalized PageRank at chance (0.502), apt vehicles buried at rank ~31k, every pair 2–4 hops apart via mega-hubs. Holds on human labels too — not circular. Refuted across 4 substrates AND both pairwise + graph-traversal framings.
- **Generation works and is affordable:** ~$0.06 Haiku + ~$0.19 Sonnet per topic → ~$20–29k for 100k (~$6k Haiku-only; ~halved API-direct; ~$3–10k at the realistic ~15–35k queryable frontier). Orders cheaper than the rejected retrieve-verify ($86k–878k). **Cost is not the constraint.**
- **The constraint is QUALITY ADMISSION:** no judge exists; human ground truth is ~12–21 verdicts over 3 concrete topics (zero on the abstract-emotion core).

## Phase
**Complete.** P0 grounding → P1 six-approach swarm → P2 direct cost measurement → P3 internal red-team → P4 synthesis. Stopping condition met: no approach remains plausibly viable as a *derivation* within constraints, and the recommendation is decision-ready.

## Approaches resolved
H-A / H-A-refined / H-B / H-C / H-E / H-F / WordNet-relations / gloss-as-features / **multi-hop unified-graph traversal (PPR+AA+RA)** → **all NOT VIABLE as derivation.** H-D → routing not needed (generation already cheap). Generation → **the surviving mechanism.** (Verdicts + artifacts in `FINAL_REPORT.md` and `claims-ledger.md`.)

## Corrections applied (from internal red-team, all verified first-hand)
1. **Concreteness retracted** as "the one usable signal" — inverts on human labels (AUC 0.375), a Karpathy-Loop-1 / G8 cohort artifact.
2. **Stale grading data fixed** — live data is in `.worktrees/next` (21 chains / 3 concrete topics), per the CLAUDE.md deploy topology; earlier G4 read a stale main-checkout file.
3. **Cost corrected** — direct-measured rates supersede H-D's stale $0.005 (≈15× low); full 100k ≈ $20–29k, not $2k.
4. **`relations` (234,810 rows) tested** — 0/7 live; refutation now spans 4 substrates.
5. **Target re-sized** — queryable frontier ~15–35k (`frequencies`), not 100k.

## Operator decision (non-blocking)
The next milestone implied by this report is **"build + validate an automated live/dead judge, and expand human grading across topic classes"** — i.e. scale the existing grading-tool bootstrap loop, query-weighted — *in place of* any context-free-edge derivation milestone. Recommended default if no reply: file this into `PIPELINE.md` Inbox as the successor to the (now-refuted) derivation idea. The derivation idea should be marked **closed-negative**, not parked.

## Spend
Metered API: **$1.10** (11 measurement calls). Everything else API-free. Orchestration: 10 subagents / 2 workflows.
