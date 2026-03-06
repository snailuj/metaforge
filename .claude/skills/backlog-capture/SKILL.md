---
name: backlog-capture
description: >
  Use when you encounter deferred work, a known limitation, or a future idea
  during development. Creates a GitHub Issue with layer and type labels to
  capture context while it's fresh.
---

# Backlog Capture

When you encounter something that should be tracked but isn't part of the
current task — a limitation, a deferred improvement, a future idea — create
a GitHub Issue immediately.

## When to Use

- You hit a ceiling or limitation (e.g. coverage gap, performance cliff)
- You defer something to stay focused on the current task
- You spot an opportunity for improvement outside current scope
- You notice a bug that isn't blocking current work

## How to Create the Issue

```bash
gh issue create \
  --title "<layer>: <terse description>" \
  --label "<layer-label>,<type-label>" \
  --body "<context>"
```

### Title Convention

Prefix with the layer, keep it terse:
- `data-pipeline: concreteness coverage ceiling at 68.8% (OOV synsets)`
- `api: rate limiting on /forge endpoints`
- `frontend: 2nd-order edge node rendering`

### Labels

**Layer** (pick one): `api`, `data-pipeline`, `frontend`, `infra`

**Type** (pick one): `enhancement`, `bug`, `idea`

### Body

Include enough context for someone (or an agent) encountering the issue cold:
- What was tried or observed
- Why it was deferred
- Candidate solutions if known
- Link to relevant code, design docs, or eval results

## Example

```bash
gh issue create \
  --title "data-pipeline: concreteness coverage ceiling at 68.8% (OOV synsets)" \
  --label "data-pipeline,enhancement" \
  --body "$(cat <<'BODY'
## Context

The concreteness regression (k-NN r=0.91) fills scores for synsets that have
at least one lemma in FastText vocabulary. 33,592 synsets have no in-vocabulary
lemmas, capping coverage at 68.8% vs the 80% target.

## Options

1. **Definition-based embeddings** — encode synset definitions with a sentence
   transformer, use those as features when lemma embeddings are unavailable.
2. **Larger vocabulary model** — FastText wiki-news-300d has 1M words. The
   crawl-300d model has 2M. May recover some OOV lemmas.
3. **Subword embeddings** — FastText's .bin format supports subword inference
   for OOV words (vs .vec which is lookup-only).

## References

- Shootout results: `data-pipeline/output/concreteness_shootout.json`
- Design: `docs/plans/2026-02-25-fasttext-concreteness-regression-design.md`
BODY
)"
```
