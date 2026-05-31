# Raycaster hit-test offset — diagnostic findings (browse mode)

Date: 2026-05-31
Branch: `metaphor-graph/grading-tool`
Task: DOM label layer plan, Task 11 (diagnose only — **no fix applied**)
Spec: `web/e2e/raycaster-offset.spec.ts` (run for real under Playwright 1.60.0 / chromium)
Raw data: `/tmp/raycaster-dpr1.json`, `/tmp/raycaster-dpr2.json`

## Symptom under investigation

Long-standing report (present since the graph was first built): in browse mode
you must point roughly **one item-height away** from a node — specifically
*below* it — before the hover registers. Aiming directly at, or just above, a
node fails to highlight it.

## Research hypothesis (entering)

Medium confidence: a `devicePixelRatio` mismatch in `three-render-objects`'
pointer→NDC mapping. The WebGL canvas does `setPixelRatio(min(2, dPR))`
(drawing-buffer px), but the pointer position is divided by `state.width`, which
is CSS px (set via `graph.width(clientWidth)`). If those two used different units
the hit point would drift, and the drift would **scale with dPR**.

## Method

Two independent measurements, each at `deviceScaleFactor` 1 and 2, viewport
1000×800, browse-mode constellation fixture (`web/e2e/fixture-browse.html`):

- **(A) Authoritative — manual raycast silhouette.** Project the target node via
  the library's own projector (`graph2ScreenCoords`), then sweep a `THREE.Raycaster`
  vertically through the node's isolated hit-sphere in 0.5px steps using
  `three-render-objects`' *exact* pointer→NDC formula (`sx/width*2-1`,
  `-(sy/height)*2+1`). The centre of the symmetric silhouette band minus the
  projected Y is the offset. Deterministic — no event plumbing, no throttle.
- **(B) Cross-check — real Playwright mouse.** `page.mouse.move` drives genuine
  pointer events through the production listener; read the `.label-hovered` class
  the component toggles in `onNodeHover`. Coarser (2px steps + 50ms raycaster
  throttle) but exercises the full live path.

Anti-self-confirmation: (A) uses the projector and raycaster as two independent
code paths sharing only the camera; (B) never touches internal coords. Enlarging
the hit-sphere for a measurable band cannot move its centre, so it cannot
fabricate an offset. Hiding neighbour meshes isolates the target.

A series of throwaway probes (sweep-direction independence; per-dy comparison of
the library's stored `pointerPos` against a manual raycast at those same coords;
link-occlusion test; DOM-frame mapping) pinned the mechanism — summarised below.

## Measured data

| Measurement | dPR 1 | dPR 2 | Scales with dPR? |
|---|---|---|---|
| (A) manual raycast vertical band | `[-23.5, +23.5]` | `[-23.5, +23.5]` | no |
| (A) **vertical offset** (band centre vs projected Y) | **0 px** | **0 px** | **no** |
| (A) horizontal offset | 0 px | 0 px | no |
| (B) real-mouse hover band | `[-4, +22]` | `[0, +22]` | no (within 2px noise) |
| (B) real-mouse band centre | +9 px | +11 px | no (2px sweep noise) |
| **canvas top − container top** | **18 px** | **18 px** | **no** |
| overlay (CSS2D) top − container top | 0 px | 0 px | no |
| canvas drawing-buffer height | 800 | 1600 | yes (expected) |
| canvas CSS height | 800 | 800 | no |

The pointer coordinate the library actually stores was probed directly: moving
the real mouse to `projectedY + 13` made the listener compute
`pointerPos.y = projectedY + 13.00000` at **both** dPRs (sub-micron error). The
pointer→library→NDC→raycaster path is exact and unit-consistent in CSS px.

## Conclusion — hypothesis REFUTED

The dPR hypothesis is **refuted**. Every dPR-sensitive quantity that matters to
hit-testing is identical at dPR 1 and dPR 2:

- The raycaster NDC math is internally consistent in CSS px. `setPixelRatio`
  scales only the *drawing buffer* (800→1600), which never enters the hit math.
- The authoritative manual-raycast silhouette is perfectly **symmetric about the
  projected point (offset 0)** at both dPRs.
- The only non-zero offset is the **canvas's 18px vertical displacement** from
  the container — and that is **18px at both dPRs**, i.e. dPR-independent.

### True root cause: two raycasters keyed to two different reference frames, split by an 18px canvas line-box

Inside the component's shadow root the DOM nests like this (measured):

```
#graph-container            top 0   ← three-render-objects' state.container
  └ div                     top 0       (its pointermove listener lives here;
      └ div                 top 0        pointerPos = pageY − container.rect.top)
          └ div.scene-container  top 0  (position: relative)
              └ <canvas>    top 18  ← three.js DragControls' domElement
```

The `<canvas>` is `display:block; position:static; vertical-align:baseline`, and
its parent `.scene-container` establishes an inline formatting context whose
leading line-box pushes the replaced canvas element **down 18px** (the classic
canvas baseline gap). The container and the CSS2D label overlay both sit at top 0.

3d-force-graph wires up **two** pointer raycasters:

1. **`three-render-objects` hover** — listener on `state.container` (top 0).
   Computes `pointerPos = pageX/Y − container.getBoundingClientRect()`. This path
   is correct: drives `onNodeHover` → the `.label-hovered` class.
2. **three.js `DragControls`** (`node_modules/three/examples/jsm/controls/DragControls.js`,
   `_updatePointer`, lines 165–170) — keyed to `renderer.domElement`, i.e. the
   **canvas** (top 18). Computes NDC as
   `(clientY − canvasRect.top) / rect.height`. Because the canvas is 18px low,
   DragControls believes the cursor is **18px higher** than it is. DragControls
   runs its own raycaster every `pointermove`, gates the drag-cursor and
   `dragstart`, and competes with the hover detector for the perceived hot-zone.

The net effect a user feels: the practical hover/grab zone is shifted, and you
must aim *below* the visible node — exactly the reported symptom. The live
`.label-hovered` band measured in (B) sits at centre ≈ +9/+11 (vs the geometric 0
from the throttle-free path (A)), confirming the live path inherits a downward
bias that the pure raycaster geometry does not have. The magnitude (~18px frame
split, ~8–11px effective band shift at 2px sampling) is consistent across runs.

Two corroborating probe results that rule out alternatives:
- Hiding all link objects did **not** symmetrise the live band → not link
  occlusion.
- Camera did not drift between projection and raycast (`enableDamping` idle at
  rest) → not a stale-camera tween.

So the offset is a **CSS-layout frame mismatch between the canvas and its
container, surfacing through the canvas-keyed DragControls raycaster** — not a
pixel-ratio bug and not a defect in the NDC arithmetic.

> Note on the existing comment at `mf-force-graph.ts` `firstUpdated()`
> ("Sync renderer dimensions to actual container size (fixes hit-test offset)"):
> that `syncDimensions()` call fixes the *size* (width/height) mismatch, but it
> does **not** address the canvas's 18px vertical *position* offset within the
> container, which is the residual cause measured here.

## Fix options — ranked by blast radius (smallest first). NO FIX APPLIED.

Decision reserved for Julian.

### Option 1 (recommended): kill the canvas line-box gap in our own CSS — container-local

Smallest blast radius, fully inside code we own, zero dependency surgery. The
18px gap is the canvas baseline gap; neutralise it so the canvas sits at the
container's top 0, aligning DragControls' frame with the container frame.

Candidates (any one should collapse the gap; verify with the spec):
- `#graph-container canvas { display: block; vertical-align: top; }` in the
  component's shadow styles, or
- set `line-height: 0` / `font-size: 0` on `.scene-container` (the canvas's
  inline-formatting parent), or
- force the canvas `position: absolute; top: 0` to remove it from inline flow.

Blast radius: one CSS rule scoped to the component's shadow root. Cannot affect
other surfaces. Re-runnable proof already exists (this spec asserts
`canvasTopMinusContainerTop`). Risk: a future `three-render-objects` markup
change could reintroduce a different wrapper — the spec guards against silent
regression.

### Option 2: container-level pointer-coord correction in `mf-force-graph`

Medium blast radius, still inside our code. Intercept pointer events at the
container and normalise so both raycasters see a consistent frame — e.g. shift
incoming `clientY` by the measured canvas offset before DragControls sees it, or
disable DragControls (`graph.enableNodeDrag(false)`) if node-dragging is not a
browse-mode feature (it currently is not used in grade mode and is questionable
in browse mode). Disabling DragControls removes the *second*, mis-framed
raycaster entirely and leaves only the correct `three-render-objects` hover.

Blast radius: component behaviour change (loses node-drag if disabled) or a
pointer-shim that must track the library's internal frame assumptions. More
moving parts than Option 1; couples us to library internals.

### Option 3: `patch-package` on `three-render-objects` / three `DragControls`

Larger blast radius. Patch `DragControls._updatePointer` (or the
`three-render-objects` wiring) so its raycaster keys off the same container frame
the hover detector uses, instead of `renderer.domElement`.

Blast radius: a vendored patch that must be re-applied on every dependency bump,
touches third-party code, and risks divergence from upstream. Only worth it if
Options 1–2 prove insufficient.

### Option 4: upstream issue to `three-render-objects` / 3d-force-graph

Largest latency, zero local blast radius. File upstream: the canvas's inline
line-box offset desynchronises DragControls' raycaster from the
`three-render-objects` hover raycaster inside a shadow-root host. Good as a
parallel long-term track, but does not unblock us — pair it with Option 1 as the
local fix.

## Recommendation

Apply **Option 1** (container-local CSS to remove the canvas baseline gap) once
Julian green-lights a fix, and keep this diagnostic spec as a regression guard on
`canvasTopMinusContainerTop === 0`. Optionally file Option 4 upstream in parallel.
The dPR hypothesis can be closed.
