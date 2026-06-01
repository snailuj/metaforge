# Metaforge — Codebase Handoff (two jobs)

This bundle asks Claude Code to do **two sequenced jobs** in the `snailuj/metaforge` repo.
They are ordered: do **Job 1 first** so Job 2 lands on a unified foundation.

## The goal
Unify the codebase on **one** design system — not just visual parity, but a single token +
theming architecture as the source of truth. The shipped `tokens.css` has **drifted** (it is
dark-only and likely carries hardcoded colour values in places); this bundle's design system
restores the intended structure: **structural tokens in `:root`, every `--colour-*` scoped to a
`data-theme` block, two skins (Dark + Parchment), and translucent washes derived with
`color-mix()`** so a skin is a pure token swap and no component knows which theme is active.

---

## Job 1 — Adopt the unified Design System
**Folder:** `01_design_system/`
**Read:** `01_design_system/ADOPTION.md`

Reconcile the repo's `web/src/styles/tokens.css` with the canonical `colors_and_type.css` here:
adopt the two-theme token-swap architecture, add the **Parchment** skin, replace any hardcoded
colours in the `mf-*` components with semantic `var(--colour-*)` tokens, and verify against the
specimen cards. After this, the whole app themes for free and there is a single system.

Reference material included:
- `colors_and_type.css` — **the canonical token file** (import of record).
- `DESIGN_SYSTEM_GUIDE.md` — the full system guide (voice, visual foundations, theming, tokens).
- `preview/` — specimen cards (colours, type, components, spacing) — use as **visual acceptance**.
- `ui_kits/web-app/` — a faithful recreation of the shipped app built **correctly** against the
  unified system (the Dark/Parchment toggle demonstrates the target architecture).
- `assets/MetaforgeConcept.png` — concept art (aspirational only).

## Job 2 — Implement Grade Mode
**Folder:** `02_grade_mode/`
**Read:** `02_grade_mode/README.md`

With the unified system in place, build Grade Mode — the keyboard-first metaphor-grading surface
that toggles with Browse. The README is a complete spec (layout, axes, keyboard, data model,
graph overlays, copy, tokens) plus the interactive prototype and screenshots. It already
references everything by the **same semantic tokens** Job 1 establishes, so it drops in cleanly.

---

## Why this order
Grade Mode is specified entirely in semantic tokens (`--colour-forge-strong`, `--hairline`,
`--colour-bg-hud`, …). If those tokens and the theming architecture aren't unified first, Grade
Mode would either re-introduce drift or fail to theme. Job 1 makes Job 2 a token-clean drop-in —
and the new surface inherits both skins automatically.
