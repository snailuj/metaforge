# Plan: switch the graph to a hand-rolled canvas

Status: approved by snailuj on 2026-11-19. Drafted 2026-11-11, revised 2026-11-19. Exported from the shared plan document.

## Summary

The graph moves from the 3d-force-graph library to a renderer we write, drawn on a 2D canvas. The layout physics, the forest model and the growth rules stay. The rest of the app keeps talking to the graph through the same properties and events.

This plan covers the graph switch only. The new panels, start screen and phone tab bar from the mockup need their own plan.

The work runs in this order. Nothing after step 1 starts until the glow test has a result.

1. Run the glow speed test on the S22 Ultra and pick the glow method from the numbers.
2. Pull the layout physics out of the library and define the drawing interface.
3. Build the canvas renderer for browsing, behind a switch, with the old renderer still the default.
4. Bring the forest and steady growth to the same behaviour as today, and mark grade mode deprecated.
5. Make the new renderer the default, then remove the library.

The review table at the end records what was approved.

## What exists today and what carries over

The graph component is 1,381 lines and makes 50 calls into the library. Ten helper modules add 1,419 lines. Seven of the ten do not touch the library and carry over unchanged. These figures come from a read of the code at commit `500f119`, not from a build.

| Part | Today | After the switch |
| --- | --- | --- |
| Layout physics | d3-force-3d, reached through the library | Same engine and settings, as a direct dependency |
| Forest model, colours, cross-links, arrival batching, ghost fade, types | Own modules, no library use | Unchanged |
| Expand, re-centre, glimpse (transform) | Relies on the physics engine's link format | Unchanged, because the engine stays |
| Growth rules (seed at parent, hold settled words) | Reads one library-only field | Small edit to drop that field |
| Labels | HTML elements placed by a three.js add-on | Drawn on the canvas, with overlap avoidance |
| Camera and drag | The library's orbit controls, plus a guard for one of its quirks | Own camera module. The guard and its 6 tests are deleted |
| Hover and click | The library's 3D ray test, plus a second test for label boxes | One hit test against what was drawn |
| Arrows, moving particles, flicker on unjudged paths | Library features | Redrawn by the canvas renderer |

The contract with the rest of the app stays as it is: the same tag, the same properties, `focusNode`, and the six events (`mf-node-select`, `mf-node-navigate`, `mf-node-copy`, `mf-forest-hover`, `mf-forest-select`, `chain-selected`).

Tests need the most rewriting. The 122 component tests assert on calls to a mocked library, so they are rewritten to assert on the frame handed to the renderer. Eight browser tests read the three.js scene and camera and are rewritten against the new hit test. The 132 tests on the helper modules that carry over stay as they are.

## Drawing interface

Every layer draws from one shared frame and knows nothing else about the graph. That is what lets a WebGL layer be added later without changing the layout, the camera, the hit test or the component.

Flow: graph state -> layout (physics, unchanged) -> camera (turn, zoom, project) -> frame (what to draw now). The same frame goes to the hit test, which also takes input (mouse, touch, wheel), to the canvas layer built in this plan, and to a WebGL layer that can be added later.

A frame is a plain list of what to draw this instant: each word with its screen position, depth, size, colour, opacity and label, and each line between words. The camera module works out screen positions once per frame, so a 2D layer and a WebGL layer cannot disagree about where a word is.

```ts
interface Layer {
  mount(host: HTMLElement): void
  resize(width: number, height: number, pixelRatio: number): void
  draw(frame: Frame): void
  destroy(): void
}

interface Frame {
  time: number
  nodes: DrawNode[]   // screen x, y, depth, radius, kind, label, colour, opacity, lit
  edges: DrawEdge[]   // two node indexes, colour, opacity, optional label, flicker phase
  glow: 'full' | 'sprite' | 'off'
}
```

Three rules keep the interface small.

- A layer only draws. It never reads graph state, runs physics or answers clicks.
- Clicks and hovers are answered by one pure function, `pick(frame, x, y)`, which tests against the same frame the layers drew. A WebGL layer therefore needs no hit test of its own.
- The component holds an ordered list of layers. Today the list has one entry, the canvas layer. A star-field or glow layer in WebGL would be a second entry drawn beneath it.

New modules, all under `web/src/graph/`: `layout.ts` (the physics, with today's settings), `camera.ts` (rotate, zoom, fly to a word, project to the screen), `frame.ts` (builds the frame from graph state, filters and the lit path), `pick.ts`, `input.ts` (mouse, touch and wheel) and `render/canvas2d.ts`.

## Glow speed test on the S22 Ultra

The test answers one question before any renderer code exists: can a 2D canvas draw 100 glowing words at the phone's full screen sharpness without dropping below 60 frames a second?

Your part takes about 3 minutes. Open one link in Chrome on the phone, tap Run, wait about 40 seconds, tap Copy results and paste them here. No marking or judging is asked of you; the pass mark is checked from the numbers.

The test page is a single file with no backend. It draws a turning graph the size of a busy real one: 100 words with labels, 150 lines and 12 glowing pills. It runs the same scene four ways for 10 seconds each.

| Run | How the glow is made | What it tells us |
| --- | --- | --- |
| No glow | None | The floor: cost of words, lines and labels alone |
| Live blur | The canvas blur setting on every glowing shape, every frame | The simplest code, and the likely slow one |
| Pre-drawn glow | Each glow painted once to a small image, then stamped | The usual fix when live blur is slow |
| Pre-drawn glow, sharpness capped at 2 | As above, on a smaller drawing area scaled up | The fallback if the screen's full sharpness costs too much |

For each run the page records the time between frames and reports the median, the 95th percentile, and the share of frames slower than 16.7 ms. It also reports the screen's pixel ratio, refresh rate and browser version, because the S22 Ultra can run at 120 Hz and at more than one resolution.

Pass mark: 95 of every 100 frames arrive within 16.7 ms. The first run in the table order that passes, counting from Live blur down, becomes the glow method. If none passes, glow is switched off while the graph is moving and drawn only when it rests, and the option of a WebGL glow layer moves from later to now.

The same frame timer then goes into the real renderer behind the existing timing flag, so later phones can be checked the same way. With the flag off it does nothing.

Two limits on what the test proves. It measures a synthetic scene, so the real renderer is measured again once it exists. And one phone is one data point: the S22 Ultra is a fast phone, so a pass there does not clear slower ones.

## Low-spec phones

Added 19 November. The aim is a smooth graph on slow phones, at about 100 words. At that size the physics is a small share of each frame, so moving it to Rust and Wasm would not show. This is an estimate until the test below measures it. What costs a slow phone is drawing: the number of pixels, the glow and the text.

Four measures go into the canvas renderer for this.

- Rest when settled. Once the layout stops moving, the physics stops and the canvas redraws only when something changes. A resting graph then costs nothing.
- Quality steps. The renderer watches its own frame times. When they run slow it steps down: pre-drawn glow, then a lower sharpness cap, then glow only at rest. It steps back up when there is headroom.
- Fewer labels when crowded. Overlap avoidance already limits how much text is drawn per frame.
- Smaller download. Removing three.js cuts what a slow phone must fetch and compile. Wasm would add to it.

The test page gains a physics timer and a slow-phone run. The page reports physics time and drawing time per frame as two numbers, so the split is measured and not assumed. The slow-phone run uses Chrome's 6x processor slowdown on a desktop, which is a rough stand-in, and a real low-spec phone if you have one to hand.

If the numbers show physics taking more than a fifth of the frame budget on the slow run, Rust and Wasm physics comes back as its own plan. The layout already sits behind its own module, so that swap would not touch drawing.

## Free flight, effects and grade mode

Added 19 November from your decisions.

Free flight is in from the start. The camera is a full perspective camera the visitor can steer through the words, and words behind the viewer are not drawn. Flying to a word, which exists today, becomes a guided move of the same camera. The graph rests only when both the layout and the camera are still.

Steering needs a control scheme, and touch is the hard part. The proposal, open for your call in the review table:

| Input | Look around | Move | Other |
| --- | --- | --- | --- |
| Mouse and keys | Drag | W A S D or arrow keys, wheel for forward and back | Double click a word to fly to it |
| Touch | One-finger drag | Pinch for forward and back, two-finger drag to slide sideways | Tap a word to select, double tap to fly to it |

A "Return to word" button brings the camera back to the central word, so nobody gets lost. With reduced motion set, guided moves cut to their end point with no flight.

Effects are not in this plan. Star-field and particles come later as a WebGL layer beneath the canvas, in a fifth pull request. The camera hands each layer the same view, so that layer needs no change to the camera or the words.

The layout hands positions to drawing as one flat array of numbers. That costs nothing now and means a Rust physics engine could replace the current one later without touching drawing.

Grade mode is retired. It is not moved to the new renderer, and every code path that feeds it gets a deprecation note. One question follows from this and is held in the review table: grade mode's graphs use the old library, so they stop working when the library is removed.

## Build steps

The work lands as four pull requests. Each step starts with a failing test for the rule in its row, and each green test is its own commit. The old renderer stays the default until the fourth pull request, so staging keeps working throughout.

| PR | Step | What is built | Rule the tests guard |
| --- | --- | --- | --- |
| 1 | Glow-Speed-Gate | The test page and its frame timer | The timer reports the same median and 95th percentile as a hand-computed list of frame times |
| 2 | Layout-Stays-The-Same | `layout.ts` on d3-force-3d as a direct dependency, with today's settings | A word that had settled keeps its position when the same data is given again |
| 2 | Camera-Projects-Once | `camera.ts`: a full perspective camera with free flight, fly to a word, and projection to the screen | Turning by an angle and back returns every word to the same screen point, and a nearer word never draws smaller than a farther one, and a word behind the viewer is never drawn |
| 2 | Frame-Holds-What-Is-Drawn | `frame.ts` and the `Layer` types | The frame lists every word the filters allow and no other, each with a screen position |
| 3 | Canvas-Draws-The-Frame | `render/canvas2d.ts`: words, pills, lines, depth fade, glow by the method the gate chose | Drawing the same frame twice gives the same pixels |
| 3 | Labels-Never-Overlap | Label placement with overlap avoidance | No two drawn label boxes overlap, and the central word and lit-path labels are always drawn |
| 3 | Pick-Matches-The-Picture | `pick.ts` and `input.ts`: click, double click, right-click, long-press to copy, and free-flight controls for mouse, keys and touch | A click on any pixel of a drawn word or its label picks that word, at every pixel ratio, and the nearest word wins |
| 3 | Contract-Is-Unchanged | The component on the new parts, behind a renderer switch | Each property, `focusNode` and each of the six events behaves the same under both renderers |
| 4 | Forest-Looks-The-Same | Gold source pill, cyan endpoints, hop squares, grounds on a lit path, flicker on unjudged paths, fade on dropped ones | A lit path shows its grounds and dims every label off the path, and an unjudged path flickers until judged |
| 4 | Growth-Stays-Steady | The existing seed, hold and batch rules wired to the new layout | A word that had settled moves less than the existing limit while newcomers arrive |
| 4 | Grade-Mode-Deprecated | A deprecation note on every code path that feeds grade mode. Grade mode is not moved to the new renderer | A test lists every grade-mode entry point and fails if one lacks its deprecation note |
| 4 | Library-Is-Gone | New renderer as default, then removal of 3d-force-graph, three, the label add-on and the orbit guard | The build contains no three.js code, and the full test suite passes |

The renderer switch is a browser setting read at load, in the same style as the existing timing flag. It lets you compare the two renderers on staging before the fourth pull request removes the old one.

The fourth pull request also records the decision in `docs/decisions/log.md`, which replaces the earlier decision that chose the library, and updates `docs/roadmap/PIPELINE.md`.

## Risks

- The 122 component tests are rewritten, not ported. While that happens a behaviour could lose its test. The contract tests in the third pull request run against both renderers to catch this.
- Hand-written camera and touch code has more edge cases than it looks: pinch and drag together, a drag that ends outside the canvas, the 300 ms wait that tells a click from a double click. The library handled these, with one quirk we had to guard against.
- Label overlap avoidance hides some labels when words crowd. Which labels give way needs a rule you agree with. The proposal is that the central word and the lit path always win, then nearer words beat farther ones.
- Worst case cost per frame is the label overlap check. Checked pair by pair it grows with the square of the word count, which is fine at 100 and slow at 1,000. The plan uses a grid lookup so the cost grows in line with the word count.
- The mockup's graph was nearly flat. The real layout already places words in three dimensions, so a full turn works. This is a reading of the settings, not something run.
- Bundle size should fall, because three.js leaves. The saving has not been measured; the fourth pull request reports the before and after.
- Keyboard users cannot reach words on the canvas itself, as today. The word panel remains the keyboard route to every word.

## Review

This table is the reviewed state. snailuj answered one HOLD row in the Override column and approved every other row as written on 2026-11-19. The two HOLD rows with a blank Override (Slow-phone run, Flight controls) had no stated choice. Until one is given, the 6x desktop slowdown stands in for a slow phone, and the proposed flight controls stand. The line and call counts in this plan come from a read of the code, not a build, and the frame-rate pass mark is a proposal with no measurement behind it yet.

| Item | Proposed action | Override | Reason |
| --- | --- | --- | --- |
| Plan scope | Cover the graph switch only |  | The new panels and start screen do not depend on the renderer and can be planned once this is agreed. |
| Glow test first | Run the phone test before any renderer code |  | Its result picks the glow method the renderer is built around. |
| Glow test hosting | Publish the test page as a private link you open in Chrome on the phone |  | It needs no staging deploy, so you can run it the same day. |
| Glow pass mark | Require 95 of 100 frames within 16.7 ms at the phone's own pixel ratio |  | 60 frames a second is the point where turning the graph looks smooth. |
| Glow fallback order | Try live blur, then pre-drawn glow, then capped sharpness, then glow only at rest |  | Each step gives up a little quality for speed, so the first pass keeps the most. |
| Layout physics | Keep d3-force-3d with today's settings |  | The growth and expand rules depend on its behaviour and are already tested. |
| Drawing interface | Use layers that draw from one shared frame, with the hit test outside the layers |  | A WebGL layer can then be added without touching layout, camera or clicks. |
| Component contract | Keep the tag, properties, method and six events unchanged |  | The rest of the app then needs no edits for the switch. |
| Old renderer during the build | Keep it as the default behind a switch until the fourth pull request |  | Staging stays usable and the two can be compared side by side. |
| Label overlap | Add overlap avoidance, with the central word and lit path always shown |  | Overlapping labels are the most visible fault in the current graph. |
| Touch copy | Add long-press to copy a word |  | Right-click has no touch equivalent today. |
| Grade mode graph | Move grade mode to the new renderer in the same work | Grade mode is retired, should be marked deprecated on all code paths that feed it | The library cannot be removed while grade mode still uses it. |
| Pull request shape | Land four pull requests in the order shown |  | Each one leaves staging working and is small enough to review. |
| Decision log | Record this as replacing the earlier choice of the library |  | The log should show why the library went. |
| Plan home | Copy this plan into `docs/plans/` in the first pull request |  | The repository keeps its plans there. |
| Rust and Wasm physics | Leave out of this plan and keep the current physics |  | At about 100 words physics is a small share of each frame, so the gain would not show on a slow phone. |
| Physics and drawing split | Measure physics time and drawing time separately in the test page |  | The case against Rust rests on an estimate, and this replaces it with a number. |
| Slow-phone run | HOLD: do you have a low-spec phone to run the test on, or should the 6x slowdown on desktop stand in? |  | The S22 Ultra is fast, so a pass there says little about slow phones. |
| Rest when settled | Stop physics and redraw only on change once the layout settles |  | A resting graph then uses no processor time or battery. |
| Quality steps | Step glow and sharpness down when frames run slow, and back up when there is headroom |  | One build then suits both fast and slow phones without a setting. |
| Camera | Build a full perspective camera with free flight from the start | Free flight from the start (your message, 19 Nov) | Adding flight later would mean rewriting the camera and the hit test. |
| Flight controls | HOLD: is the proposed scheme right (one finger looks, pinch moves, two fingers slide; drag and W A S D on desktop)? |  | How flight feels in the hand is a matter of taste that tests cannot settle. |
| Effects layer | Defer star-field and particles to a fifth pull request, as a WebGL layer | Not needed straight away (your message, 19 Nov) | The switch can ship without them and the layer design leaves room. |
| Flat position array | Hand positions from layout to drawing as one flat array of numbers |  | A Rust physics engine could then replace the current one without touching drawing. |
| Grade mode after the library goes | HOLD: when the old library is removed, delete grade mode's graph views, or keep the library until grade mode itself is deleted? | Delete grade mode's views | Grade mode's graphs use the old library and are not being moved. |

Evidence (not for review): code read at commit `500f119` on `main`. Component `web/src/components/mf-force-graph.ts` (1,381 lines; library set-up at lines 1010-1155). Helper modules in `web/src/graph/`. Library versions from `web/package-lock.json`: 3d-force-graph 1.79.1, three 0.182.0, d3-force-3d 3.0.6 (transitive today). Earlier decision: `docs/decisions/log.md` line 16. Flicker requirement: the same file, line 22. Timing flag: `web/src/lib/timing.ts` lines 14-45.
