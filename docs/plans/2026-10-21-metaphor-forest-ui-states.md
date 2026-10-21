# Metaphor forest: UI state machine

Status: draft for designer review, 2026-10-21. Written to `docs/plans/2026-10-21-metaphor-forest.md` (the spec, "Frontend" section line 110 onward). Method: `~/.claude/skills/ui-state-design/SKILL.md`. Accessibility bar: `~/.claude/skills/ux-floor/SKILL.md`. No code is changed by this document.

Paths below are relative to the repository root. `file:line` citations are against branch `forest/web` at the time of writing.

## 1. Scope and fixed constraints

The forest overlays the browse (thesaurus) graph for the committed word. Grade mode is out of scope except where a mode switch changes the forest (section 4, events 13 and 14).

Constraints quoted from the spec and fixed here. The table fills the cells around them and does not override them.

| Source | Quote |
|---|---|
| spec:32 | "The forest overlays the thesaurus graph for the looked-up word; thesaurus links dim while a forest is shown." |
| spec:77 | "An empty forest (every path rejected) is still 200 with empty `nodes` apart from the source, and empty `edges` and `endpoints`." |
| spec:112 | "Map 503, 429 and 504 to distinct user-facing messages." |
| spec:114 | "hover on an endpoint lights its whole path and dims the rest; thesaurus links dim while a forest is shown." |
| spec:115 | "Focus or hover on an item lights its path. It is the accessible surface and must work at phone width." |
| spec:30 | "Caching: None." (Each press can return a different forest, so a discarded forest cannot be restored.) |

## 2. What exists today

| Fact | Where |
|---|---|
| Lookup is latest-wins: `lookupId` is bumped on entry and checked after the await, on both success and error paths. | `web/src/components/mf-app.ts:953`, `:961`, `:971` |
| A lookup sets `currentWord` and `appState = 'loading'` before the response, and clears `errorMessage`. The search box binds to `currentWord`. | `mf-app.ts:955-957`, `:987` |
| A 404 sets `appState = 'error'` with `results-word-not-found`; anything else sets `error-generic`. `result` and `graphData` are left as they were, so the old graph stays behind the message. | `mf-app.ts:970-978` |
| Four callers reach `doLookup`: search, node double-click, results-panel chip, URL hash (initial load and `hashchange`). | `mf-app.ts:513-515`, `:517-522`, `:539-541`, `:479-482`, `:494-499` |
| Single click (`mf-node-select`) fetches the clicked word and merges second-order nodes into `baseGraphData` after stripping earlier ones. Central is ignored. A failure only logs. Latest-wins by `selectId`; `doLookup` also bumps `selectId`. | `mf-app.ts:524-537`, `:954`; `web/src/graph/transform.ts:198-212` |
| `errorMessage` is one shared string. Lookup errors, grade errors and the auth-expiry message all write it. It renders in two places: the centre status line and `mf-error-banner`. The banner has no `role`. | `mf-app.ts:550`, `:610`, `:629`, `:666`, `:957`, `:973-976`, `:1003`, `:1269-1271`; `web/src/components/mf-error-banner.ts:20-23` |
| The lookup loading and error text sits in one `role="status" aria-live="polite" aria-atomic` region. | `mf-app.ts:992-1009` |
| `mf-toast` is a `role="status" aria-live="polite"` element, default duration 1500 ms, shown through `toast.show(msg, duration)`. | `web/src/components/mf-toast.ts:36`, `:51-52`; `mf-app.ts:543-546`, `:1294` |
| Mode switch swaps the whole subtree. Browse mode mounts `mf-force-graph` and `mf-results-panel`; grade mode does not, so `disconnectedCallback` disposes the WebGL renderer. `result` and `graphData` live in `mf-app` and survive. | `mf-app.ts:553-560`, `:981-1047`, `:1284-1292`; `web/src/components/mf-force-graph.ts:604-618` |
| The grade-mode graph is wired to the same `mf-node-select` and `mf-node-navigate` handlers. | `mf-app.ts:1070-1072` |
| Click handling: first click arms a 300 ms timer (`mf-node-select` on expiry); a second click inside it cancels the timer and fires `mf-node-navigate`. Clicks on `order === 2` nodes are swallowed. | `mf-force-graph.ts:17`, `:400-439` |
| Node hover only toggles a label CSS class. The whole-path highlight pattern exists for grade mode: `hoveredChainSig`, read by `linkColor` and `linkWidth`, applied by `refreshLinkStyles()` without calling `graphData()`, so the force sim does not re-heat. | `mf-force-graph.ts:138`, `:363-378`, `:380-388`, `:452-465`, `:522-525`, `:583-585` |
| Any change to the `graphData` prop re-feeds the library and restarts the sim. | `mf-force-graph.ts:528-537`, `:567-573` |
| The rarity filter hides nodes by `rarity ?? 'unusual'`, so a node with no rarity vanishes when "unusual" is unticked. | `mf-force-graph.ts:297-314` |
| `mf-results-panel` is collapsed by default at 768px and below, with a toggle. Its whole panel is `aria-live="polite"`. Word chips are `span role="button"` and handle Enter only. | `web/src/components/mf-results-panel.ts:68-72`, `:224-229`, `:236-238`, `:271-275`, `:277-291`, `:385` |
| Browse node ids may be `word__synsetId`. | `web/src/graph/types.ts:27` |
| Strings live in Fluent, loaded at start. | `web/public/strings/v1/ui.ftl`, `web/src/lib/strings.ts:23-60` |

## 3. Context held by `mf-app`

| Variable | Meaning |
|---|---|
| `forest` | The last accepted 200 body, or null. Holds `source`, `max_hops`, `nodes`, `edges`, `endpoints`, `stats`. |
| `request` | `idle`, `loading`, or `failed(kind)` with kind one of 400, 429, 502, 503, 504, network. |
| `forestSeq`, `controller` | A counter bumped on every start, cancel, clear and commit of a different word, plus the `AbortController` for the call in flight. A response renders only if its counter is current and `forest.source` equals the committed word. |
| `hops` | 1 to 5, default 3. Survives word changes and failures. |
| `pinned` | Endpoint id whose path is pinned, or null. |
| committed word | `result.word` (`mf-app.ts:962`). Forge always sends this, never `currentWord`, because `currentWord` changes before a lookup succeeds. |
| lookup ready | `appState === 'ready'`. Called G below. |

Forest failures do not use `errorMessage`. Reason: that string is shared with lookup and grade errors, is cleared by every lookup (`mf-app.ts:957`), and renders in two places that would show a forest failure out of context.

## 4. Region A: forest lifecycle

The surface is two axes, content kept on screen (none, shown, empty) and request (idle, loading, failed). Failures never destroy a shown forest, so a failed or loading request over a shown forest is its own state.

### 4.1 States

Seven families, 17 observable states (`failed` and `failed-kept` each carry one of six kinds; `failed-kept(400)` is defensive, since the word already succeeded once).

| State | Meaning | Graph | Panel controls | Panel body |
|---|---|---|---|---|
| none | No forest, nothing in flight. | Thesaurus only, links at normal strength. | Max hops select. Primary "Forge". | Intro line: "Forge finds fresh metaphors for "{word}" and draws them on the graph." |
| loading | In flight, nothing kept. | Thesaurus only. | Hops select aria-disabled. Primary "Forging..." aria-disabled. "Cancel". | Decorative spinner plus "Forging metaphors for "{word}". This can take up to a minute." |
| reloading | In flight, a shown forest kept. | The kept forest. | Hops aria-disabled. Primary "Forging..." aria-disabled. "Cancel". "Clear forest". | Line "Forging a new forest. This one stays until it arrives." above the kept list, list `aria-busy="true"`. |
| shown | At least one endpoint. | Forest drawn, thesaurus links dimmed. | Hops enabled. Primary "New forest". "Clear forest". | Summary "{n} metaphors, {k} live", then the endpoint list (section 7.1). If `hops` differs from `forest.max_hops`: "Built with up to {max_hops} hops. New forest will use {hops}." |
| empty | 200, no endpoints. | Thesaurus only (nothing to emphasise, so no dimming). | Hops enabled. Primary "Forge". | "No metaphors passed the quality check for "{word}" this time. The forge checked {generated} candidates and kept none. Press Forge to try again, or look up a different word." |
| failed(kind) | Failed, nothing kept. | Thesaurus only. | Hops enabled. Primary "Forge" (aria-disabled while a 429 cooldown runs). | The message for the kind (section 4.4) in the alert region. |
| failed-kept(kind) | Failed, shown forest kept. | The kept forest. | Hops enabled. Primary "New forest" (aria-disabled during 429 cooldown). "Clear forest". | The message for the kind plus " Your previous forest is still shown.", then the kept list. |

Presentation discriminates every pair: primary label (Forge, Forging..., New forest), the presence of Cancel and Clear forest, the body text, and the alert region content. `loading` and `reloading` differ by the kept list and Clear forest. `shown` and `failed-kept` differ by the alert text. No colour-only cue is used.

Controls other than Clear forest, Cancel, pinning, highlighting and lookup are inert when G is false (a lookup is loading or failed). The panel then shows "Forge is off until the word lookup succeeds." in place of the intro line or above the body. This is a guard on every row below, not a separate state.

### 4.2 Events

1. press-forge: the primary button (click, tap, Enter, Space).
2. response-ok: 200 with at least one endpoint.
3. response-empty: 200 with no endpoints.
4. response-fail(kind): 400, 429, 502, 503, 504, network, any other status, or a 200 whose body fails the shape check.
5. response-stale: any settle (success, failure, AbortError) whose counter is not current or whose `source` is not the committed word.
6. press-cancel.
7. press-clear (opens the confirmation, region C).
8. confirm-discard (region C, section 6).
9. hops-change.
10. lookup-start: any `doLookup` begins, from any caller.
11. lookup-commit-same: a lookup succeeds and `result.word` equals the previous committed word.
12. lookup-commit-other: a lookup succeeds with a different word.
13. lookup-fail: a lookup fails and the app is in the error state (hard), or a soft lookup returns 404 (soft; section 4.5).
14. mode-to-grade.
15. mode-to-browse.
16. cooldown-elapsed (timer).
17. expand-second-order: single click on a thesaurus node (`mf-node-select`).

Clicking or hovering the graph for highlight, and double-clicking a forest node, are covered by region B and by events 10 to 13.

### 4.3 Transitions

Every row is a cell. "Guard G" means the row is a no-op when lookup is not ready.

Event 1, press-forge

| State | Result | Feedback |
|---|---|---|
| none | -> loading. Counter bumped, new `AbortController`, `fetchForest(result.word, hops)`. Guard G. | Status: "Forging metaphors for "{word}". This can take up to a minute." |
| loading | No-op. Single flight: the button is aria-disabled and the handler returns early. | None. |
| reloading | No-op, same guard. | None. |
| shown | -> reloading. Kept forest stays. Guard G. | Status: "Forging a new forest for "{word}". The current one stays until it arrives." |
| empty | -> loading. Empty message is replaced. Guard G. | Status as for none. |
| failed(kind) | -> loading. Alert region emptied. Guard G. No-op while a 429 cooldown runs. | Status as for none. |
| failed-kept(kind) | -> reloading. Alert region emptied. Guard G. No-op while a 429 cooldown runs. | Status as for shown. |

Event 2, response-ok (counter current, source matches)

| State | Result | Feedback |
|---|---|---|
| none | Stale; see event 5. | None. |
| loading | -> shown. | Status: "Found {n} metaphors for "{word}", {k} rated live." (singular for 1). Focus does not move. |
| reloading | -> shown. The new forest replaces the kept one; `pinned` is cleared. | Same status. |
| shown | Stale; see event 5. | None. |
| empty | Stale. | None. |
| failed(kind) | Stale. | None. |
| failed-kept(kind) | Stale. | None. |

Event 3, response-empty

| State | Result | Feedback |
|---|---|---|
| loading | -> empty. | Status: the empty-state sentence. |
| reloading | -> shown. The kept forest stays, because an empty re-roll is no better than what is on screen. | Status: "The new forest had no metaphors that passed the quality check. Your previous forest is still shown." |
| none, shown, empty, failed, failed-kept | Stale. | None. |

Event 4, response-fail(kind)

| State | Result | Feedback |
|---|---|---|
| loading | -> failed(kind). A 429 starts the cooldown timer. | Alert: message for kind (4.4). |
| reloading | -> failed-kept(kind). A 429 starts the cooldown timer. | Alert: message for kind plus " Your previous forest is still shown." |
| none, shown, empty, failed, failed-kept | Stale. | None. |

Event 5, response-stale

| State | Result | Feedback |
|---|---|---|
| any of the seven | Dropped. Nothing renders, nothing is announced. One `console.debug` line records word, counter and outcome. An AbortError caused by our own `abort()` is always stale. | None. |

Event 6, press-cancel

| State | Result | Feedback |
|---|---|---|
| loading | -> none. `abort()`, counter bumped. | Status: "Forging cancelled." Focus moves to the primary button, because Cancel is removed. |
| reloading | -> shown. `abort()`, counter bumped. | Status: "Forging cancelled. Your previous forest is still shown." Focus to the primary button. |
| none, shown, empty, failed, failed-kept | No-op. The control is not rendered. | None. |

Event 7, press-clear

| State | Result | Feedback |
|---|---|---|
| shown, reloading, failed-kept | Region C opens. State unchanged. | Confirmation prompt, focus on "Keep forest". |
| none, loading, empty, failed | No-op. The control is not rendered. Loading has Cancel; the others have nothing to discard. | None. |

Event 8, confirm-discard

| State | Result | Feedback |
|---|---|---|
| shown | -> none. `forest` cleared, `pinned` cleared. | Status: "Forest cleared." Focus to primary button. |
| reloading | -> none. `abort()`, counter bumped, forest cleared. | Same. |
| failed-kept(kind) | -> none. Forest and alert cleared, cooldown timer cleared. | Same. |
| none, loading, empty, failed | Unreachable (region C is closed in these states). | None. |

Inverse: none. The action is irreversible and the confirmation says so.

Event 9, hops-change

| State | Result | Feedback |
|---|---|---|
| none | `hops` updated. No request. | None beyond the select's own announcement. |
| loading, reloading | No-op. Select is aria-disabled. Reason: the request in flight already used the old value. | None. |
| shown, failed-kept | `hops` updated. No request. The forest is unchanged. If the value differs from `forest.max_hops` the "Built with up to..." line appears; if it matches, it disappears. | None. |
| empty, failed | `hops` updated. No request. An error stays until the next action. | None. |

Event 10, lookup-start

| State | Result | Feedback |
|---|---|---|
| any of the seven | State unchanged. G becomes false, so Forge, New forest and the hops select go inert and the guard line appears. Any request in flight keeps running and may land (it is still for the displayed word). Region C stays as it is. | Existing lookup status ("Looking up..."). |

Event 11, lookup-commit-same

| State | Result | Feedback |
|---|---|---|
| any of the seven | State unchanged. The graph is recomposed: fresh thesaurus base, forest overlaid again (section 8). A request in flight keeps running. Reason: the forest belongs to the word, and a repeat lookup (search again, double-click the central node) must not destroy it. | None. |

Event 12, lookup-commit-other

| State | Result | Feedback |
|---|---|---|
| any of the seven | -> none. `abort()` if in flight, counter bumped, forest, `pinned`, alert and cooldown timer cleared, region C closed, highlight sources cleared. `hops` kept. Panel heading takes the new word. | No extra announcement (the lookup's own status covers it). If focus was inside the panel it moves to the panel heading (`tabindex="-1"`). |

Event 13, lookup-fail

| State | Result | Feedback |
|---|---|---|
| any of the seven | Hard failure: state unchanged, G stays false (`appState = 'error'`). The guard line explains why controls are inert. Soft 404 (4.5): `appState` returns to ready, G true, state unchanged, forest and any request in flight untouched. | Hard: existing lookup error text. Soft: toast (4.5). |

Event 14, mode-to-grade

| State | Result | Feedback |
|---|---|---|
| none, shown, empty | State unchanged. Panel and browse graph unmount. `pinned`, hover and focus sources cleared. Region C closed. | None. |
| loading | -> none. `abort()`, counter bumped. | None (nobody is looking at the panel). |
| reloading | -> shown. `abort()`, counter bumped. | None. |
| failed(kind) | -> none. Alert and cooldown timer cleared. Reason: the error described a request the user has left. | None. |
| failed-kept(kind) | -> shown. Same clearing. | None. |

Event 15, mode-to-browse

| State | Result | Feedback |
|---|---|---|
| any of the seven (only none, shown, empty occur after event 14) | State unchanged. A new `mf-force-graph` mounts and is fed the composed graph; the sim runs from scratch, as the browse graph already does after a mode switch. | None. |

Event 16, cooldown-elapsed

| State | Result | Feedback |
|---|---|---|
| failed(429) | -> none. Primary re-enabled. | Status: "The forge is ready. Press Forge to try again." |
| failed-kept(429) | -> shown. Primary re-enabled. | Status: "The forge is ready. Press New forest to try again." |
| all other states | Unreachable. The timer is cleared on every exit from a 429 state. | None. |

Event 17, expand-second-order (`mf-node-select` on a node with no forest role)

| State | Result | Feedback |
|---|---|---|
| any of the seven | State unchanged. The existing expansion runs. The composed graph is built when the response applies, from the forest as it is then, so a forest cleared or replaced meanwhile is respected. Nodes with a forest role never take this path; see 7.2. | None. |

### 4.4 Failure kinds

Common to all kinds: each message names the next action and none blames the user. Alerts use `role="alert"` in a container that is in the DOM before the message is inserted. Every message is assertive.

| Kind | Cause | Exact message | Recovery action | Cooldown |
|---|---|---|---|---|
| 400 | `word` fails the server's rule (spec:38), shown by `result.word`. `max_hops` cannot be wrong because the select only offers 1 to 5. | "This word can't be forged. The forest takes words and short phrases of letters, spaces, hyphens and apostrophes, up to 40 characters. Look up a different word." | Look up another word. | No. |
| 429 | Concurrency or per-minute cap (global). `Retry-After` in seconds. | "The forge is busy. Try again in {seconds} seconds." ("1 second" when 1.) | Wait, then the primary re-enables on its own. | Yes. Seconds taken from `Retry-After`; missing, non-numeric or under 1 gives 10; capped at 60. The text is fixed at response time and does not tick. |
| 502 | Model error, refusal, `max_tokens`, unparseable output. Also: any other non-OK status, and a 200 whose body fails the shape check (logged with the real status). | "The forge could not build a forest this time. Try again; each attempt can give different results." | Primary. | No. |
| 503 | No API key configured (spec:86). | "The metaphor forest is not set up on this server. The thesaurus still works. Ask the site owner to turn the forest on." | The user has none; the message says who does. The primary stays enabled, because a repeat costs no model call and the server may be configured later. | No. |
| 504 | Request deadline (75 s). | "The forge took too long and stopped. Try again, or lower the max hops." | Primary, or the hops select. | No. |
| network | `fetch` rejects with a TypeError. | "The forest could not reach the server. Check your connection and try again." | Primary. | No. |

The server's own `error` strings are never shown. Reason: they are written for logs and one of them (503) would read as a fault in the page.

### 4.5 Navigating from a forest node (soft lookup)

A forest node whose word is not in the thesaurus graph (origin `forest`) is likely to 404 on lookup. A node that is in the thesaurus graph (origin `both`) keeps the existing lookup behaviour, including the existing error state.

For an origin-`forest` double-click, or the panel's "Look up" button on such an item, `doLookup` runs in soft mode:

- `currentWord` and the search box change only on success.
- `appState` is `loading` while it runs, so G is false.
- On success it behaves as lookup-commit-same or lookup-commit-other.
- On 404 it restores `appState = 'ready'`, leaves forest and request alone, and calls `toast.show('"{word}" is not in the thesaurus. Your forest is unchanged.', 5000)`. The toast is `role="status"`. Focus does not move (it is on the Look up button, or on the canvas).
- Any other failure follows the existing path (`error-generic`, `appState = 'error'`).

### 4.6 Repeated gestures

| Gesture | Second time | Decision |
|---|---|---|
| Forge or New forest while in flight | No-op, no second request. | Single flight (floor 12). Test: two activations before resolve, fetch mock called once. |
| Forge or New forest after it settles | A new request, usually a different forest. | Counter by design; replacing a shown forest keeps the old one until the new one arrives. |
| Cancel | Control is gone after the first press. | Idempotent. |
| Clear forest, with the prompt open | The button is replaced by the prompt. | Idempotent. |
| Discard forest | Control is gone. | Idempotent. |
| Hops select to the same value | No `change` event. | No-op. |
| Single click on an endpoint | Toggles `pinned`. | Toggle. |
| Highlight button on a list item | Toggles `pinned` (`aria-pressed`). | Toggle. |
| Double-click a forest node while a lookup is loading | Latest wins through `lookupId`. | Supersede. |
| Look up button while a lookup is loading | Inert (aria-disabled). | Single flight for panel-originated lookups. |
| Mode toggle | Alternates. | Toggle. |

## 5. Region B: path highlight

An endpoint is the last node of one kept path, so a path is identified by its endpoint id.

Four sources, in priority order:

1. graph-hover: a pointer is over an endpoint node or its label.
2. panel-hover: a pointer is over a list item.
3. panel-focus: focus is inside a list item (focus-within).
4. pinned: the id in `pinned`.

The lit path is the first source that is set. Graph-hover and panel-hover cannot both be set (one pointer). Pointer events count only when `pointerType` is `mouse` or `pen`; touch sets no hover, which avoids sticky hover on tap.

States are named by the winning source: unlit, lit-hover, lit-focus, lit-pinned.

Presentation, graph: the lit path's links are widened and brightened, every other forest link and node and all thesaurus links are dimmed further, and endpoint labels stay on (dimmed). A pinned endpoint also keeps a ring on its node regardless of which path is lit. Presentation, panel: the lit item has a visible outline; a pinned item also shows a "Pinned" text badge and a pressed Highlight button. Hover or focus highlight with no pin shows no ring and no badge. This is what lets a user tell "lit because the pointer is here" from "pinned".

Highlight is applied through a `highlightedPath` property and `refreshLinkStyles()` (`mf-force-graph.ts:522-525`), never through `graphData`, so it cannot re-heat the sim.

Only endpoint nodes are highlight targets. Hop nodes and links are not (spec:114). A hop has a default cursor and no hover effect.

| Event | unlit | lit-hover | lit-focus | lit-pinned |
|---|---|---|---|---|
| enter endpoint node or list item (mouse or pen) | -> lit-hover. | Switches path (the pointer moved to another target); stays lit-hover. | -> lit-hover. Focus source is kept underneath. | -> lit-hover. Pin kept underneath. |
| leave endpoint node or list item | No-op. | -> lit-focus if a focus source is set, else lit-pinned if pinned is set, else unlit. | No-op (hover was not the winner). | No-op. |
| focus enters a list item | -> lit-focus. | Stays lit-hover; the focus source is stored. | Switches path; stays lit-focus. | -> lit-focus. |
| focus leaves the items | No-op. | Stays lit-hover; focus source dropped. | -> lit-pinned if pinned is set, else unlit. | No-op. |
| single click on endpoint node (after the 300 ms timer) | pinned set -> lit-pinned. | pinned set; stays lit-hover until the pointer leaves. | pinned set; stays lit-focus. | Same endpoint: pinned cleared -> unlit (or the next source down). Different endpoint: pinned moves; stays lit-pinned. |
| press Highlight button on a list item | pinned set -> lit-pinned. | Same as the click row. | Same. | Same. |
| forest replaced or cleared, lookup-commit-other, mode-to-grade, confirm-discard | No-op. | -> unlit. All four sources cleared. | -> unlit. | -> unlit. |
| response arrives into reloading and replaces the forest | No-op. | -> unlit. | -> unlit. | -> unlit. |
| escape key while a list item has focus | No-op. | No-op. | No-op (focus is not removed). | No-op. |

Hover and highlight on the kept forest are live in `reloading` and `failed-kept`, because the kept forest is on screen and valid. In `none`, `loading`, `empty` and `failed` there are no endpoints, so every row is a no-op.

Right-click on a forest node copies its word and shows the existing "Copied" toast (`mf-force-graph.ts:440-451`). Unchanged.

## 6. Region C: clear confirmation

Clear forest discards an artifact that cannot be regenerated (spec:30, each press may differ), so floor items 14 and 15 apply. The prompt is inline in the panel, not a modal, so no focus trap; Escape closes it.

States: closed, open.

Open presentation: the Clear forest button is replaced by the text "Discard this forest? It cannot be restored. Forging again may give different metaphors." (in `reloading`, append " The forest being forged will be stopped too."), then "Keep forest" and "Discard forest". Initial focus is on "Keep forest". Keep is first in tab order.

| Event | closed | open |
|---|---|---|
| press-clear (shown, reloading, failed-kept only) | -> open. Focus to "Keep forest". | Unreachable; the button is not rendered. |
| press "Keep forest" | Unreachable. | -> closed. Focus to the Clear forest button. No data change. |
| press "Discard forest" | Unreachable. | -> closed and region A event 8. Focus to the primary button. |
| Escape | No-op. | -> closed, same as Keep. |
| region A leaves the state the prompt opened in (response lands, cancel, cooldown, lookup-commit-other, mode switch) | No-op. | -> closed. If the Clear forest button still exists focus goes to it; otherwise to the primary button. Reason: the user judged one forest and a different one may now be on screen. |
| hops-change, region B events, lookup-start, lookup-fail | No-op. | Stays open. |

## 7. Region D: layout, phone and keyboard

### 7.1 Panel structure

`mf-forest-panel`, rendered only in browse mode and only when `result` is set (same rule as `mf-results-panel`, `mf-results-panel.ts:373-375`).

1. Heading `h2`, "Metaphor forest for "{word}"", `tabindex="-1"` so focus can be sent to it.
2. Controls: a labelled `select` "Max hops" (1 to 5), the primary button, then Cancel or Clear forest.
3. A `role="status"` polite region, always in the DOM, atomic.
4. A `role="alert"` region, always in the DOM.
5. Body (intro, loading text, empty text, or the list).

List item, one per endpoint, in API order (score descending, then path length ascending):

- Endpoint word, then "{score} of 10", with the word "Live" when the score is 7 or more.
- The `line` text.
- The path as an ordered list: each step reads "{from} to {to}, because {ground}", using `path[i]` and `grounds[i]` (spec:76).
- A "Highlight path" toggle button (`aria-pressed`) and a "Look up "{endpoint}"" button.
- The judge's `reason` is not shown (spec lists line, path and score only).

There is no virtualisation. A forest has at most about 16 endpoints.

### 7.2 Graph gestures and their panel equivalents

Every graph gesture has a keyboard and touch path in the panel, because the canvas is not keyboard-operable.

| Graph gesture | Panel equivalent |
|---|---|
| Hover endpoint, light path | Focus inside the item |
| Single click endpoint, pin | Highlight path button |
| Double-click forest node, look up | Look up button |
| Right-click, copy word | None (existing gap for chips too; not widened here) |

Behaviour follows presentation. A node with a forest role (hop, endpoint or source) is drawn in forest styling whether or not it is also a thesaurus neighbour. On such a node:

- Single click on an endpoint pins its path; on a hop it does nothing.
- The existing second-order expansion and the order-2 click swallow (`mf-force-graph.ts:412-418`) do not apply.
- Double-click looks up the word (soft if origin is `forest`, existing path if `both`).

Nodes with no forest role keep every existing behaviour. The cost: a thesaurus neighbour that is also a forest hop cannot be expanded while a forest is on screen. Clearing the forest restores it.

### 7.3 Phone width

Breakpoint 768px and below, matching `mf-results-panel.ts:68` and `:226`. Also covers 200% zoom on a 1280px window (floor 24).

Above 768px the panel is docked on the opposite side to the results panel, below the mode toggle, 360px wide.

At 768px and below it is a bottom sheet:

- Collapsed bar (at least 56px high): heading, the status and alert text in full (wrapping), the hops select, the primary button, and Cancel when present. The primary button is reachable in one tap.
- Expanded sheet (at most 70dvh, scrolls): the bar plus the body, including the full list. The graph stays visible above it and is never needed. Every fact (line, path, grounds, score) and every action (highlight, look up, clear) is a button or text in the list.
- Expanded is possible only while a list exists (shown, reloading, failed-kept). The toggle (`aria-expanded`, "Show forest list" or "Hide forest list") is rendered only then.
- The bottom of the sheet pads by `env(safe-area-inset-bottom)` as `mf-app.ts:358` does.
- `mf-toast` (fixed, bottom 2rem, `mf-toast.ts:7-11`) must sit above the sheet's collapsed bar at this width.

Only one of the results panel and the forest sheet is expanded at a time at this width. This needs `mf-results-panel` to emit an event when it toggles (it emits none today); that change belongs to the implementation task.

| Event | docked | sheet-collapsed | sheet-expanded |
|---|---|---|---|
| viewport becomes narrow | -> sheet-collapsed. | No-op. | No-op. |
| viewport becomes wide | No-op. | -> docked. | -> docked. |
| press sheet toggle | Unreachable (control hidden). | -> sheet-expanded (only when a list exists). | -> sheet-collapsed. Focus stays on the toggle. |
| Escape with focus inside the sheet | No-op. | No-op. | -> sheet-collapsed. Focus to the toggle. |
| region A first reaches shown (loading -> shown) | No-op. | -> sheet-expanded. Focus does not move. | No-op. |
| region A leaves list states, or lookup-commit-other | No-op. | No-op. | -> sheet-collapsed. |
| results panel expands | No-op. | No-op. | -> sheet-collapsed. |

The forest survives every layout change. These events change position only.

### 7.4 Live regions and focus

Announced politely through the panel's `role="status"` (and the toast for the soft 404):

- loading started, reloading started, found n (and the k live), empty result, empty re-roll kept, cancelled, forest cleared, cooldown elapsed.

Announced assertively through `role="alert"`:

- every failure message in 4.4, once, when it is inserted.

Not announced: hover and focus highlight changes (focus is announced by the browser and the list items' own text), pin changes (`aria-pressed` does that), hops changes (the select does that), graph re-layout, and `response-stale` drops.

Focus never moves on a response. It moves only where the focused control disappears: Cancel (to primary), Discard and Keep (see region C), the Look up button after lookup-commit-other (to the heading). The primary button uses `aria-disabled="true"` plus a guard rather than the `disabled` attribute while loading, so a keyboard user does not lose focus to the body.

## 8. Graph composition rules

These bind the transform and `mf-force-graph`.

- Composed graph = (browse base, with second-order nodes merged as today) then forest overlay. The overlay is applied after `stripSecondOrderNodes` (`transform.ts:198-212`), never before.
- Forest nodes match thesaurus nodes on normalised `word`, not on `id`, because browse ids can be `word__synsetId` (`types.ts:27`). A match keeps the thesaurus node object and adds the forest role. Origin is `thesaurus`, `forest` or `both`.
- Metaphor links are their own kind and are never merged with a thesaurus link between the same pair.
- Thesaurus links dim only while forest content is on screen: shown, reloading, failed-kept.
- Forest-role nodes are exempt from the rarity filter. Forest-only nodes have no rarity and would otherwise disappear when "unusual" is unticked (`mf-force-graph.ts:304`).
- Recomposition reuses node and link objects whose ids are unchanged, so a second-order expansion or a same-word re-lookup does not make the forest jump.
- Directional particles are off under `prefers-reduced-motion: reduce`, set from `matchMedia`, since the library animates in JS.
- The forest is never drawn in grade mode; the grade graph builds from `gradeChains` and ignores `graphData` (`mf-force-graph.ts:513-518`).

## 9. Decisions

| Id | Choice | Reason |
|---|---|---|
| Single-Flight-Press | Forge pressed in flight is ignored, not a cancel-and-restart. | Floor 12; restart would double model spend on a global cap. |
| Keep-Forest-While-Reforging | A re-roll leaves the shown forest on screen, and failures never remove it. | Each forest is unrepeatable and costs a model call; losing it to a 504 is the worst outcome. |
| Empty-Reroll-Keeps-Previous | A 200 with no endpoints over a shown forest keeps the shown forest. | Same reason; an empty result is not better than what is there. |
| Add-Cancel-Control | A Cancel button while in flight. | The deadline is 75 s; floor 13 forbids a dead end. Not in the brief; the designer may drop it. |
| Confirm-Before-Clear | Two-step inline confirmation for Clear forest on a shown forest. | Floor 14; the forest cannot be restored. |
| Empty-Needs-No-Confirm | Empty has no Clear control and no confirmation. | Nothing is lost. |
| Own-Error-Channel | Forest failures live in the panel, not in `errorMessage`. | Shared string, cleared by every lookup. |
| Forge-Uses-Committed-Word | Requests send `result.word`. | `currentWord` changes before a lookup succeeds (`mf-app.ts:955`). |
| Forest-Follows-Committed-Word | A same-word commit keeps the forest, another word clears it, a lookup start or failure changes nothing. | One sentence; a typo or a repeat search must not destroy a forest. |
| Controls-Inert-Unless-Ready | Forge, New forest and hops are inert unless `appState === 'ready'`. | Avoids forging for a word the search box no longer shows. |
| Aria-Disabled-Keeps-Focus | `aria-disabled` plus guard, not `disabled`, on the primary button. | The `disabled` attribute drops keyboard focus to the body. |
| Soft-Lookup-For-Forest-Words | Forest-only words use a soft lookup that survives a 404. | These words are phrases the thesaurus will often not have. |
| Forest-Role-Wins-Clicks | Forest-role nodes pin or navigate; they never expand. | Behaviour must follow what is drawn. |
| Hover-Endpoints-Only | Only endpoints highlight a path. | spec:114; a hop belongs to several paths. |
| Pointer-Beats-Focus-Beats-Pin | Priority graph-hover, panel-hover, focus, pin; each source clears itself. | The most transient input wins, and the next one down returns when it ends. |
| Pin-Is-Visibly-Different | A pin has a ring and badge that hover and focus lack. | Otherwise a click to unpin looks like nothing happened while the pointer is still there. |
| Mouse-Pen-Hover-Only | Touch sets no hover source. | Avoids sticky hover on tap. |
| Errors-Clear-On-Mode-Switch | Failures are dismissed on the way to grade mode. | The user left the request. |
| Cooldown-Returns-To-Calm | A 429 resolves to none or shown after `Retry-After`, with a polite status. | No separate "ready" error state; no ticking text. |
| Retry-After-Clamped | Missing or bad gives 10 s; maximum 60 s. | A header the server controls must not freeze the button. |
| Other-Statuses-As-502 | Unlisted statuses and bad bodies use the 502 copy and are logged. | One recovery action, and the real status stays in the log. |
| Hops-Persist | `hops` survives word changes and failures. | A preference, not a result. |
| Hops-Inert-In-Flight | The select is inert while a request runs. | The request already used the old value. |
| Stale-Hops-Note | A note shows when the selected hops differ from the shown forest's. | The select and the forest would otherwise disagree silently. |
| Phone-Bottom-Sheet | Panel is a bottom sheet at 768px and below, primary button in the collapsed bar. | One tap to forge; matches the results panel breakpoint. |
| Expand-Needs-A-List | Expanded sheet only exists with a list. | An empty expanded sheet has nothing to show. |
| One-Phone-Panel-Open | Only one of results and forest expanded on a phone. | They would overlap. |
| Reason-Not-Shown | The judge `reason` is omitted. | Not in the spec's panel contents. |

## 10. UX floor

| Item | Status |
|---|---|
| 1 contrast, tokens | Applies. Panel styles use `var(--...)` tokens, no literal colours. The dimmed state must still meet 3:1 for graph marks and 4.5:1 for text. |
| 2 semantic elements, names | Applies. All controls are `button` or `select`. The existing `span role="button"` chips are not copied. Icon-only controls carry `aria-label`; none are planned. |
| 3 keyboard, focus | Applies. Tab order: hops, primary, Cancel or Clear, then each item's Highlight and Look up buttons. Focus rules in 7.4. Region C is inline, not a modal, so no trap. |
| 4 touch targets | Applies. Buttons and the select are at least 44 by 44 CSS px, at phone width too. |
| 5 colour not sole | Applies. Live is the word "Live" plus the number; pinned is a badge and `aria-pressed`; errors are text in an alert. |
| 6 reduced motion | Applies. The spinner, panel transitions and graph particles are off under `prefers-reduced-motion: reduce`. |
| 7 automated audit | Applies. One axe run per visually distinct state: none, loading, reloading, shown, empty, one failed, one failed-kept, confirm open, phone collapsed, phone expanded. |
| 8 labels | Applies to the hops select (visible "Max hops" label). |
| 9 invalid field | N/A. The select offers only valid values. |
| 10 values preserved | Met. `hops` survives a failure. |
| 11 announcements | Met (7.4). Failures in `role="alert"`, outcomes in `role="status"`. |
| 12 single flight | Met (event 1, 4.6). |
| 13 no dead end | Met. Every failure names a recovery in 4.4; 503 names who can act. |
| 14, 15 destructive | Met by region C: asymmetric labels, consequence in the confirm control, safe alternative first and focused, irreversibility in the copy. |
| 16 CTAs | Met. "Forge", "New forest", "Cancel", "Clear forest", "Discard forest", "Keep forest", "Highlight path", "Look up". |
| 17 error copy | Met. Each message states what happened and the next action. |
| 18 empty copy | Met. States why and what to do. |
| 19 one term | Met. "Forge" for the operation, "forest" for the result, "Clear" for the action on a shown forest and "Discard" only on the confirm control that names it. |
| 20 multi-step | N/A. Forging is one step. |
| 21 navigation | N/A. The panel adds no primary navigation. |
| 22 layout | Applies. The primary button is the one primary action; Cancel, Clear and Look up are secondary. |
| 23 images | N/A. No `<img>`, audio or video. The canvas has no text alternative today; the panel is the accessible equivalent of the forest. |
| 24 light, dark, 200% zoom | Dark: N/A, the app ships one dark theme and the panel uses the shared tokens so it follows when others land. 200% zoom: applies and lands in the phone layout. |
| 25 RTL, expansion | Applies to the new panel: logical properties (`inset-inline-end`, `padding-inline`), no fixed text widths or heights. |

## 11. Negative criteria

One per no-op cell that matters. Each is a test the implementation must pass.

- Two activations of Forge before the response: `fetchForest` called once.
- Forge pressed while a lookup is loading or failed: no request.
- A response whose counter is stale or whose `source` differs from the committed word: nothing renders, no announcement.
- A failed re-roll (any kind) leaves the shown forest and its list on screen.
- An empty re-roll leaves the shown forest on screen.
- A lookup that fails (hard or soft 404) leaves forest, pin and any in-flight request unchanged.
- A same-word lookup keeps the forest; a different word clears it, including a request in flight.
- Soft 404 leaves the search box on the old word.
- Single click on a forest-role node never calls `lookupWord`.
- Clear forest never clears on the first press when a forest is shown; initial focus is not on "Discard forest".
- Hover end with a pin set falls back to the pin; with focus set, to the focus.
- Touch input never sets the hover source.
- Highlight changes never call `graphData()`.
- Unticking "unusual" does not hide forest nodes.
- A 429 `Retry-After` of 3 disables the primary for 3 s and re-enables it with one polite announcement.
- Mode switch to grade aborts a request in flight and renders no forest in the grade graph.
- At phone width, with the graph canvas absent, every list action still works.

## 12. For the designer

Calls most worth overruling or confirming:

1. Keep-Forest-While-Reforging doubles the failure states (the `failed-kept` family) to protect an unrepeatable result. Dropping it halves the table.
2. Confirm-Before-Clear adds friction for a clear button. The alternative is a timed undo, which the floor does not let replace the confirmation.
3. Forest-Role-Wins-Clicks removes second-order expansion from shared nodes while a forest is shown.
4. Add-Cancel-Control is outside the brief.
5. The loading text promises "up to a minute"; check it against measured latency once an API key exists.
6. A cancelled or cleared request relies on the Go handler stopping its model call when the client disconnects. Not checked; the spec does not say.
