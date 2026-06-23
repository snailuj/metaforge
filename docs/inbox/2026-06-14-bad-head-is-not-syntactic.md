# bad_head is NOT (mostly) a syntactic intermediate-head defect — measured

**Date:** 2026-06-14. **Trigger:** operator flagged "we need to fix the bad head extraction" before launching Phase B generation. Built a deterministic head-fixer; in measuring it against the operator's actual `bad_head` tags, found the held belief was wrong.

## What we believed
`bad_head` = the generating model emits the wrong word as the single-word lexical head of an intermediate phrase (e.g. "hidden accumulation" → emits "hidden" instead of "accumulation"). Endpoints are canonical, so bad_head was thought to corrupt only intermediate heads + path geometry. The prior prompt-clause fix halved the cohort rate (54%→26-33%), implying a residual syntactic error to chase.

## What the data says (measured on the operator's 44 bad_head-tagged chains)
- Of 119 intermediate steps in the tagged chains, **~92% emit a syntactically-correct head** (last-token premodifier→noun, which is right).
- A deterministic syntactic head-extractor (nltk POS + WordNet noun-membership, confident-only) found **32 genuine syntactic head errors corpus-wide (~0 regressions)** — but **ALL 32 land in UNGRADED chains. ZERO in the operator's 44 bad_head-tagged chains, ZERO in any of the 132 graded chains.**
- **Conclusion: the operator's `bad_head` tag does NOT correlate with the syntactic premodifier-over-noun error.** Whatever the operator is tagging, it is largely orthogonal to the deterministically-fixable syntactic class.

## So what IS the operator tagging?
Two non-deterministic candidates (not yet disambiguated — cheap follow-up below):
1. **Bad sense-snap** — the head TOKEN is syntactically correct ("accumulation"), but `lookup_primary_synset` resolved it to the WRONG synset, so the grading tool displays a wrong sense/gloss → reads as a bad head. This is the known sense-snapping noise; the real lever would be the **deferred SemCor-tagcount re-snap**.
2. **Semantic-head disagreement** — the head is grammatically valid but the wrong CONCEPT for what the step is metaphorically about; the operator disagrees with the model's choice of pivot. Needs a model (or a better generation prompt), not a parser.

## What got built (kept — it cleans a real, orthogonal defect)
Deterministic no-LLM syntactic head extractor + backfill entrypoint (`head_extractor.py`, `head_extraction_backfill.py --resnap-file`, 28 tests green, commits `8032383b`..`86f435c1`). Confident-only by default (replaces head ONLY for adjective/participle-premodifier + compound-restore classes; `--unconditional` to override). Backfill-ready for existing + future chain.v1 round files (re-derives head from the always-correct `phrase`, re-snaps synset). Fixes 32 corpus chains the operator never tagged — worth keeping, but does NOT address the operator's bad_head tax.

## Implications
- **Phase B launch is NOT gated on a head fix** — confirmed twice over: (a) heads are backfillable from phrases, (b) the deterministic fix doesn't even touch what the operator tags, so holding the launch for it would be pointless.
- **The operator's bad_head tax is real but mis-attributed.** The real lever is likely the SemCor-tagcount re-snap (sense-snapping), possibly + a generation-prompt semantic-head pass. Invest there, not in more syntactic head work.
- **Cheap follow-up to disambiguate (1)/(2):** sample the 44 bad_head-tagged chains with their snapped synset glosses AND the operator's free-text notes on those tags; categorise wrong-sense-snap vs semantic-disagreement. ~$0, read-only. Do before any re-snap or prompt investment.

## Prompt-hardening recommendation (NOT applied — separate decision)
The one syntactic class the model still gets wrong is premodifier-over-noun. Generation prompt could add: *"The head is the NOUN the phrase is about, never an adjective/modifier in front of it: 'lightning strike'→'strike', 'boundary line'→'line'. For 'X of Y' keep X: 'ritual of engagement'→'ritual'."* Marginal (reduces backfill load on the 32-chain class), does not touch the operator's bad_head.
