---
name: metaforge-pipeline
description: Surface the current Metaforge programme pipeline — active milestone, next milestone, queued, backlog. Use when starting milestone-level work, when picking what to do next, when the user asks "what's next" / "what should I work on" / "where are we", when a milestone completes, or when a new idea needs filing into the queue. Read docs/roadmap/PIPELINE.md and report concisely.
---

# Metaforge Pipeline

The single source of truth for what comes next in Metaforge is `docs/roadmap/PIPELINE.md`. This skill makes it easy to surface that without anyone having to remember the path.

## When to fire

- User asks "what's next", "what should I work on", "where are we", or any variant
- User starts milestone-level work (mentions M02, M03, etc., or talks about which milestone to begin)
- A milestone has just shipped — confirm the move from Active → Done and ask which Queued item promotes to Next
- User describes a new idea that doesn't fit the active milestone — propose filing it under Backlog (or as a new Queued milestone with name + why + depends-on + detail-doc-path)
- User asks "is this on the pipeline" — read and report

## What to do

1. **Read** `docs/roadmap/PIPELINE.md`.
2. **Report concisely.** Surface the current Active item (if any), the Next item (the one to pick up if Active is empty), and the count of Queued and Backlog items. Don't dump the whole file unless asked.
3. **If the user wants more detail** on a specific milestone, read its detail doc at `docs/roadmap/M0X-name-roadmap.md` and `docs/roadmap/M0X-name-context.md`.
4. **If a state change is happening** (something just shipped; new milestone starting; new backlog idea), propose the edit to PIPELINE.md and apply it on confirmation. Update the Done section with a one-line summary and merge date when a milestone ships.

## Format for a quick report

```
**Active:** <name>  (or "none — pick from Next")
**Next:** <name> — <one-line why>
**Queued:** N items — <comma-separated names>
**Backlog:** N items — <topical headers, not full list>
**Done:** N items
```

If there's no Active item, the question to put in front of the user is: *"Promote Next (<name>) to Active?"*

## Conventions

- New milestones land in **Queued** with at minimum: name, why, depends-on, detail-doc link.
- Move to **Next** when M-1 is done.
- Move to **Active** when work starts. Flesh out the detail doc; create per-slice sub-docs as needed.
- Move to **Done** with a one-line summary and merge date when shipped.
- **Backlog** items have no slot yet — promote to Queued when a milestone slot opens up.

## Cross-references

- Programme overview, milestone context, and per-slice detail docs all live under `docs/roadmap/`.
- Decisions log: `docs/decisions/log.md`.
- Idea inbox: `docs/inbox/captures.md`.
- Code-review-loop ref branches (e.g. `review/m01-and-snap-memopt`) are cross-listed in PIPELINE's Backlog when they need attention.
