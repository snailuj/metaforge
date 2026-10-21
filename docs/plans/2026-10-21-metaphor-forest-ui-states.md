# Metaphor forest: UI state machine

Status: judged by the designer and built, 2026-10-21, branch `forest/web`. The worker's draft (26 states, 86 transitions) was checked against `~/.claude/skills/ui-state-design/SKILL.md` and simplified. Section 3 records every change and its reason. Spec: `docs/plans/2026-10-21-metaphor-forest.md`. Accessibility bar: `~/.claude/skills/ux-floor/SKILL.md`.

Paths are relative to the repository root. `file:line` citations are against `forest/web` at the time of writing.

## 1. Scope and fixed constraints

The forest overlays the browse (thesaurus) graph for the committed word. Grade mode is out of scope except where a mode switch touches the forest.

Rulings quoted verbatim. The tables fill the cells around them and do not override them.

| Source | Quote |
|---|---|
| owner, via the build brief | "see a forest of branching options from one source to many metaphorical endpoints, visible on the graph, with each link showing the meaning its two words share." |
| build brief | "hovering an endpoint, a hop or a metaphor link lights every path through it, nodes and links, and dims the rest" |
| spec:32 | "The forest overlays the thesaurus graph for the looked-up word; thesaurus links dim while a forest is shown." |
| spec:77 | "An empty forest (every path rejected) is still 200 with empty `nodes` apart from the source, and empty `edges` and `endpoints`." |
| spec:112 | "Map 503, 429 and 504 to distinct user-facing messages." |
| spec:115 | "Focus or hover on an item lights its path. It is the accessible surface and must work at phone width." |
| spec:30 | "Caching: None." (Each press can return a different forest, so a replaced forest cannot be restored.) |

## 2. Where it lives

| Part | Where |
|---|---|
| The whole state machine, as a pure reducer | `web/src/forest/state.ts:72` (`reduceForest`), `:68` (`litTarget`) |
| Effects: start, abort, recompose, lit set | `web/src/components/mf-app.ts:574` (`dispatchForest`), `:602` (`runForest`), `:630` (`recomposeGraph`) |
| Soft lookup | `web/src/components/mf-app.ts:1070`, 404 branch `:1093`; forest double-click `:544` |
| Client and error mapping | `web/src/api/client.ts:94` (`fetchForest`), `:74` (status kinds), `:127` (body shape check) |
| Transform, overlay, lit paths, depth force | `web/src/graph/forest.ts:51`, `:104`, `:143`, `:173` |
| Graph rendering and gestures | `web/src/components/mf-force-graph.ts:339` onward (forest accessors), `:409` (hover, touch guard), `:685` (background click), `:738` (forest-node click) |
| Panel (the accessible surface) | `web/src/components/mf-forest-panel.ts`; status and alert regions `:573`, `:576`; phone sheet `:353` |
| Copy | `web/public/strings/v1/ui.ftl`, section "Metaphor forest panel" |

Existing behaviour the design relies on, unchanged: lookups are latest-wins through `lookupId`; a lookup error sets `appState = 'error'` and leaves `result` and the graph in place; `errorMessage` is shared by lookup, grade and auth errors; single click arms a 300 ms timer and a second click inside it navigates; the results panel collapses at 768 px and below.

## 3. Changes from the draft

| Change | Reason |
|---|---|
| Request and content are two independent variables. The `reloading` and `failed-kept` families are gone. | A re-roll or a failure never touches the content, so each transition is written once and keeping the shown forest costs nothing. |
| Confirm-Before-Clear and the whole clear-confirmation region are replaced by a reversible "Show on graph" checkbox. | Hiding loses nothing, so no confirmation is needed and floor items 14 and 15 no longer apply; it uses visibility, so the layout does not jump. |
| The 429 cooldown timer, its event and its "forge is ready" announcement are dropped. The primary stays enabled after a 429. | An early retry costs one cheap 429 with a fresh `Retry-After`, and the message already says when to retry. |
| The lookup-ready guard (G) is dropped from every row. | The panel names the committed word, and a lookup that commits another word aborts the request, so a wrong forest cannot render. |
| Hops-Inert-In-Flight is dropped; the select is always live. | A change mid-flight only sets the next request, so there is nothing to protect. |
| Stale-Hops-Note is dropped. | The select sits beside New forest and plainly shows the setting for the next press. |
| Highlight targets are nodes, links and paths. Hover on a hop or a link lights every path through it. | The build brief overrules Hover-Endpoints-Only. |
| Graph-hover and panel-hover merge into one hover source; sources are hover, focus, selection. | One pointer is in one place, so the priority rule is "hover, else focus, else selection". |
| Pin becomes selection: a click or tap on any forest node or metaphor link, or the panel's Highlight path toggle. A background click and Escape in the list clear it. | Touch has no hover, so a tap must be able to light paths; clicking empty space is the natural way out. |
| A selection draws a gold ring on its node's label; hover never does. The draft's panel "Pinned" badge is dropped (the pressed Highlight path button carries it). | Without a graph mark, a click that toggles the selection under the pointer shows no change: the blocker the draft named Pin-Is-Visibly-Different. |
| Soft lookup covers every lookup started from the forest (panel Look up, double-click on any forest node), not only forest-only words. | One rule instead of an origin split; the 404 toast is harmless for a word the thesaurus has. |
| The Look up button stays active while a lookup runs. | `doLookup` is latest-wins, so a second press supersedes the first rather than duplicating it. |
| A mode switch aborts nothing and clears only hover and focus. | The request is already paid for; letting it land keeps the forest for the way back. Only pointer and focus sources go stale when the panel unmounts. |
| One-Phone-Panel-Open is done by stacking: an opened results panel slides over the forest sheet. | Same outcome with one CSS rule and no new cross-component event. |
| The next Forge clears an empty result. | Nothing on screen is worth keeping, and `empty` then only ever pairs with an idle request. |
| Failure kinds are named (`invalid-word`, `busy`, `failed`, `not-configured`, `timeout`, `network`), not numbered by status. | Names say what to do; statuses stay in the logs. |
| "Max hops" is "Max steps" in the UI, and all copy was rewritten to name the next action. | Plain language and floor item 17. |
| Composition: a new forest is framed by the camera, its rings clear the thesaurus cloud and flatten toward the default camera, thesaurus labels recede, and lit words stay above ground labels. | The owner must see the forest at a glance; these came from the visual check. |

## 4. Context held by `mf-app`

One `ForestState` (`web/src/forest/state.ts`), plus effect handles.

| Field | Meaning |
|---|---|
| `word` | The committed word (`result.word`). Requests always send it, never the search box text. |
| `seq` | Bumped on every Forge, Cancel and word change. A response applies only if its `seq` is current, a request is in flight, and its `source` normalises to `word`. Whenever `seq` moves, `mf-app` aborts the request in flight. |
| `request` | `idle`, `loading`, or `failed(kind, retryAfterSeconds)`. |
| `content` | `none`, `forest(response)` (at least one endpoint) or `empty(response)`. |
| `maxHops` | 1 to 5, default 3. Survives word changes and failures. |
| `onGraph` | Show on graph. Reset to true by a new forest and by a word change. |
| `notice` | One-off outcome to announce: `found`, `empty-kept`, `cancelled`, or none. Cleared by the next Forge or word. |
| `hover`, `focus`, `selection` | Highlight sources (section 6). |

Forest failures never use `errorMessage`: that string is shared with lookup and grade errors and is cleared by every lookup.

## 5. Region A: forest lifecycle

### 5.1 States

Request: `idle`, `loading`, `failed(kind)`. Content: `none`, `forest`, `empty`. Seven combinations are reachable; `empty` with `loading` or `failed` is not, because Forge clears an empty result.

| Request, content | Panel controls | Status region (polite) | Alert region | Body | Graph |
|---|---|---|---|---|---|
| idle, none | Max steps, Forge | empty, or "Forging stopped." after a cancel | empty | Intro: "Grow fresh metaphors for "{word}". Each one is a path of shared qualities, drawn on the graph." | Thesaurus only |
| loading, none | Max steps, "Forging…" (aria-disabled), Cancel | spinner and "Forging metaphors for "{word}". This can take up to a minute." | empty | empty | Thesaurus only |
| idle, forest | Max steps, New forest, Show on graph, phone sheet toggle | "Found {n} metaphors for "{word}". {k} are live." until the next request, or the empty-kept or cancelled line | empty | Legend and endpoint list | Forest drawn, thesaurus links and labels receded |
| loading, forest | Max steps, "Forging…", Cancel, Show on graph | spinner and "Forging a new forest for "{word}". The current one stays until it arrives." | empty | The kept list | The kept forest |
| idle, empty | Max steps, Forge | "No metaphors passed the quality check for "{word}" this time. The forge tried {generated} and kept none. Press Forge to try again, or look up another word." | empty | empty | Thesaurus only, nothing receded |
| failed, none | Max steps, Forge | empty | The kind's message (5.4) | empty | Thesaurus only |
| failed, forest | Max steps, New forest, Show on graph | empty | The kind's message plus " Your last forest is still shown." | The kept list | The kept forest |

Presentation discriminates every pair: the primary label (Forge, Forging…, New forest), Cancel present only in flight, Show on graph present only with a forest, the status text, and the alert text. No state is told apart by colour alone.

### 5.2 Events

1. forge: the primary button (click, tap, Enter, Space).
2. settled, at least one endpoint (200).
3. settled, no endpoints (200).
4. failed(kind): any non-200, a network failure, or a 200 whose body breaks the contract.
5. stale: any settle whose `seq` is not current, or arrives with no request in flight, or whose `source` is not the committed word, and every AbortError.
6. cancel.
7. word-committed: a lookup succeeds. Same word or another word.
8. set-max-hops.
9. Not events for this region (explicit no-ops): lookup start, lookup failure (hard or soft), a second-order expansion (it recomposes the graph only), and mode switches (section 8.3).

### 5.3 Transitions

Request view. Every cell is a transition or a no-op with its reason.

| Event | idle | loading | failed(kind) |
|---|---|---|---|
| forge | -> loading, `seq` + 1, fetch `(word, maxHops)`. An empty result is cleared; notice cleared. | No-op: single flight. The button is aria-disabled, the handler returns early, and the reducer returns the same state. | -> loading, alert cleared. Otherwise as idle. |
| settled, endpoints | Stale (nothing in flight): dropped. | -> idle. Content becomes the new forest, highlight sources cleared, `onGraph` true, notice `found`. On a phone the sheet opens; the camera frames the new forest. Focus does not move. | Stale: dropped. |
| settled, no endpoints | Stale: dropped. | -> idle. A shown forest is kept with notice `empty-kept`; otherwise content becomes `empty`. | Stale: dropped. |
| failed(kind) | Stale: dropped. | -> failed(kind). Content unchanged. Alert announced once. | Stale: dropped. |
| stale | Dropped. Nothing renders or is announced; one `console.debug` line. | Same. | Same. |
| cancel | No-op: the control is not rendered. | -> idle, `seq` + 1, request aborted, notice `cancelled`. Content unchanged. Focus moves to the primary because Cancel disappears. | No-op: the control is not rendered. |
| word-committed, another word | -> idle, `seq` + 1, content none, highlights cleared, `onGraph` true. Max steps kept. | Same, and the request is aborted. | Same; the alert is cleared. |
| word-committed, same word | No-op: a repeat search must not destroy a forest. The graph is recomposed on the fresh thesaurus base. | No-op: the request keeps running. | No-op. |
| set-max-hops | `maxHops` set (clamped 1 to 5). | `maxHops` set; the request in flight keeps the old value. | `maxHops` set; the alert stays until the next action. |

Content view of the same events.

| Event | none | forest | empty |
|---|---|---|---|
| forge | Unchanged. | Unchanged: kept until a better one lands. | -> none. |
| settled, endpoints | -> forest. | -> forest (replaced). | Unreachable: forge cleared it. |
| settled, no endpoints | -> empty. | Unchanged, notice `empty-kept`. | Unreachable. |
| failed | Unchanged. | Unchanged. | Unreachable. |
| cancel | Unchanged. | Unchanged. | Unreachable: no request. |
| word-committed, another word | Unchanged (already none). | -> none. | -> none. |

### 5.4 Failure kinds

Every message says what happened and the next action, blames no one, and goes into the `role="alert"` region, which is always in the DOM. The server's own `error` text is never shown.

| Kind | Cause | Message | Recovery |
|---|---|---|---|
| invalid-word | 400 | ""{word}" can't be forged. The forge takes words and short phrases made of letters, spaces, hyphens and apostrophes, up to 40 characters. Look up a different word to try again." | Look up another word. |
| busy | 429 | "The forge is busy right now. Try again in {n} seconds." ("1 second"; "in a moment" when `Retry-After` is missing, not whole seconds, or under 1.) | Wait, then press the primary. |
| failed | 502, any unlisted status, or a contract-breaking 200 (logged with the real status) | "The forge couldn't grow a forest this time. Try again; each try can give different metaphors." | The primary. |
| not-configured | 503 | "The metaphor forest isn't turned on for this server. The thesaurus still works. Ask the site owner to turn the forest on." | Names who can act. The primary stays enabled; a repeat costs no model call. |
| timeout | 504 | "The forge took too long and stopped. Try again, or choose fewer steps." | The primary, or Max steps. |
| network | fetch rejects (not our abort) | "Couldn't reach the server. Check your connection, then try again." | The primary. |

### 5.5 Lookups started from the forest (soft lookup)

The panel's Look up button and a double-click on any forest node run `doLookup` in soft mode:

- The search box changes only on success.
- `appState` is `loading` while it runs.
- Success behaves as word-committed (usually another word, which clears the forest).
- A 404 restores `appState = 'ready'`, leaves the forest, any request and the search box alone, and shows the toast ""{word}" isn't in the thesaurus. Your forest is unchanged." for 5 s (`role="status"`). Focus does not move.
- Any other failure takes the existing lookup error path.

## 6. Region B: highlight

Targets: a path (by endpoint id), a forest node, or a metaphor link. A target lights every kept path that contains it (`litEndpoints`, `web/src/graph/forest.ts:143`).

Sources, highest priority first:

1. hover: a mouse or pen over a forest node or metaphor link on the graph, or over a list item. Touch never sets hover (the graph remembers the last `pointerType`; the panel checks it on `pointerenter`).
2. focus: keyboard focus inside a list item.
3. selection: a click or tap on a forest node or metaphor link (after the 300 ms double-click window), or the item's Highlight path toggle.

The lit target is the first source that is set. States are named by the winning source.

Presentation. Graph: lit nodes and links bright, lit branches wider with more sparks, grounds shown at each lit link, lit words drawn above ground labels; every other forest mark and the whole thesaurus dimmed. A selection also rings its node's label in gold (for a path, the endpoint; for a link, its head node). Panel: lit items carry a cyan rule and tint; a selection made with Highlight path also shows the button pressed (`aria-pressed="true"`). Hover and focus never draw the ring or press the button, so selection always reads differently from a transient light.

| Event | unlit | lit-hover | lit-focus | lit-selected |
|---|---|---|---|---|
| pointer enters a forest node, metaphor link or list item (mouse or pen) | -> lit-hover. | Target switches; stays lit-hover. | -> lit-hover; focus kept underneath. | -> lit-hover; selection kept underneath. |
| pointer leaves | No-op: no hover set. | -> lit-focus if focus is set, else lit-selected if a selection is set, else unlit. | No-op: hover was not set. | No-op: hover was not set. |
| touch on the graph | No hover. A tap is a click (row below). | Same. | Same. | Same. |
| focus enters a list item | -> lit-focus. | Stays lit-hover; focus stored. | Target switches. | -> lit-focus; selection kept. |
| focus leaves a list item | No-op. | Stays lit-hover; focus dropped. | -> lit-selected if set, else unlit. | No-op. |
| click or tap a forest node or metaphor link; Highlight path | Selection set -> lit-selected, ring drawn. | Selection set; ring drawn; stays lit-hover until the pointer leaves. | Selection set; stays lit-focus. | Same target: selection cleared, ring removed (-> next source down, else unlit). Another target: selection moves. |
| background click on the graph | No-op (nothing selected). | Selection cleared; stays lit-hover. | Selection cleared; stays lit-focus. | -> unlit. |
| Escape in the list | No-op; on a phone with the sheet open, the sheet collapses. | Selection cleared if set. | Selection cleared if set. | -> unlit. Focus stays. |
| new forest arrives, or another word is committed | No-op. | -> unlit, all sources cleared. | -> unlit. | -> unlit. |
| Show on graph unchecked | Graph shows nothing lit; the panel still marks lit items. Sources kept. | Same. | Same. | Same. |
| mode switch to grade | No-op. | -> unlit (hover cleared). | -> unlit or lit-selected (focus cleared). | Unchanged; shown again on return. |

Highlight changes are applied through accessor refreshes and label DOM attributes, never `graphData()`, so the simulation does not re-heat. Highlight is live on a kept forest during a re-roll and after a failed one. With no forest, every row is a no-op (the reducer ignores the event).

Single click on a forest node never expands it and double-click looks it up softly; nodes with no forest role keep every existing behaviour (Forest-Role-Wins-Clicks). Right-click still copies the word.

## 7. Region C: Show on graph

Present only while there is a forest.

| Event | on | off |
|---|---|---|
| uncheck | -> off. Forest-only nodes and metaphor links hidden by visibility, thesaurus restored, labels rebuilt, no re-feed. | Unreachable. |
| check | Unreachable. | -> on, the reverse. |
| new forest arrives | Stays on. | -> on (the user asked for it). |
| another word committed | Control removed; resets to on. | Same. |
| failure, cancel, empty re-roll | Unchanged. | Unchanged. |

## 8. Region D: layout, phone and keyboard

### 8.1 Panel structure

`mf-forest-panel`, rendered in browse mode whenever a word has been looked up. A `section` landmark named by its `h2` "Metaphor forest" (`tabindex="-1"`).

1. Controls: "Max steps" select (visible label), the primary button, Cancel in flight.
2. "Show on graph" checkbox with a visible label, only with a forest.
3. `role="status"` polite atomic region, always in the DOM.
4. `role="alert"` region, always in the DOM.
5. Body: intro, legend and list, or nothing.

One list item per endpoint, in API order (score descending, then shorter path):

- Endpoint word (`h3`), "✦ Live" text when the score is 7 or more, then "{score}/10" with the hidden text "Score {score} out of 10".
- The line, in italic.
- The path as an ordered list named "Path from "{source}" to "{endpoint}"": each word, with the ground that joins it to the next word set beneath it (hidden prefix "joined by").
- "Highlight path" toggle (`aria-pressed`, named "Highlight the path to "{endpoint}"") and "Look up" (named "Look up "{endpoint}" in the thesaurus").
- The judge's `reason` is not shown (the spec lists line, path and score).

### 8.2 Phone width

At 768 px and below the panel is a bottom sheet (75 dvh maximum, safe-area padding). The bar (heading, controls, status, alert) is always there, so Forge is one tap away. The list shows only while the sheet is open. Every fact and action is in the list, so the graph is never needed.

| Event | desktop | sheet collapsed | sheet open |
|---|---|---|---|
| sheet toggle (`aria-expanded`, "Show {n} metaphors" or "Hide metaphors"; rendered only with a forest) | Hidden by CSS. | -> open. | -> collapsed; focus stays on the toggle. |
| Escape in the list with no selection | No-op. | No-op. | -> collapsed; focus to the toggle. |
| new forest arrives | No-op. | -> open; focus does not move. | Stays open. |
| content leaves forest (another word) | No-op. | No-op. | -> collapsed. |
| the results panel opens | No-op. | It slides over the sheet (z-order). | Same. |
| viewport crosses 768 px | CSS only; state kept. | Same. | Same. |

### 8.3 Live regions, focus and mode switches

Polite (`role="status"`): loading, re-roll loading, found, empty, empty re-roll kept, cancelled; the soft-lookup toast. Assertive (`role="alert"`): each failure, once. Not announced: highlight changes, max steps, Show on graph (native controls announce themselves), stale drops.

Focus never moves on a response. It moves only when the focused control disappears: Cancel (to the primary) and a word change while focus is in the panel (to the heading). The primary uses `aria-disabled` plus a guard rather than `disabled`, so focus is not dropped in flight.

Mode switch to grade: the panel and browse graph unmount; hover and focus are cleared; a request in flight keeps running and its result is shown on return. Mode switch to browse: a new graph mounts with the composed graph.

## 9. Repeated gestures

| Gesture | Second time | Decision |
|---|---|---|
| Forge or New forest while in flight | No request. | Idempotent (single flight, floor 12). |
| Forge or New forest after it settles | A new request, usually a different forest. | Counter; the shown forest stays until the new one lands. |
| Cancel | The control is gone. | Idempotent. |
| Max steps to the same value | No `change` event; the reducer returns the same state. | Idempotent. |
| Show on graph | Flips back. | Toggle. |
| Click or tap the same forest node or link | Clears the selection. | Toggle. |
| Highlight path on the same item | Clears the selection. | Toggle. |
| Background click | Nothing more to clear. | Idempotent. |
| Escape | Clears the selection, then collapses the sheet, then nothing. | Idempotent per layer. |
| Look up, or double-click a forest node, while a lookup runs | The newer lookup wins. | Supersede. |
| Sheet toggle | Flips back. | Toggle. |

## 10. Mutations and their inverses

| Mutation | Inverse, or why it is irreversible |
|---|---|
| A new forest replaces the shown one | Irreversible: no caching (spec:30) and each forest is random. Mitigated: the old forest stays until the new one lands, and a failed or empty re-roll keeps it. Not a destructive action under floor D: the user asked for the replacement and the label "New forest" names it. |
| Cancel | Inverse is Forge (a new request; the result may differ). |
| Show on graph | Check it again. |
| Selection | Select again, Escape, or a background click. |
| Max steps | Choose the old value. |
| Another word discards the forest | Irreversible for the same reasons as a replacement; the forest belongs to the word it was forged for. |

## 11. Graph composition rules

- Composed graph = the thesaurus graph on screen (base plus any second-order expansion), then the forest overlay (`composeForest`).
- Forest words match thesaurus nodes on the normalised word (or the same id). A match keeps the thesaurus node object, so the simulation keeps its position and no node is drawn twice.
- Metaphor links are their own objects, never merged with a thesaurus link on the same pair, and get fresh string ends on every composition so a re-fed simulation never holds a node object from an earlier lookup.
- Forest-only node objects are created once per response and reused by every composition, so a second-order expansion does not reset them.
- Forest nodes skip the rarity filter; forest-only nodes and metaphor links hide with Show on graph.
- Roles: the source keeps the central gold and gets a larger root label in a gold ring; endpoints are larger white-hot spheres with pill labels and a gold ✦ when live; hops are small teal joints with small italic labels.
- While a forest is shown, thesaurus links dim and thesaurus labels recede.
- Sparks flow from each link's source to its target, which the transform orients from the source word outward. Under `prefers-reduced-motion: reduce` the sparks are off and short arrows show direction instead; camera moves are instant.
- A depth force rings the forest around the source (ring 1 clears the thesaurus cloud, later rings follow at the link distance) and draws it toward the plane facing the default camera, so it reads as a burst from the source.
- The camera frames the graph shortly after a new forest lands, and again as it settles. Highlight and recomposition never reframe.
- Ground labels hang just below each link, a little nearer the parent word; lit words are kept above them.
- The forest is never drawn in grade mode.
- All model text (words, grounds, lines) reaches the DOM through `textContent` or Lit's escaping, never as markup.

## 12. Decisions

| Id | Choice | Reason |
|---|---|---|
| Two-Axis-Forest-State | Request and content are separate variables in one pure reducer. | Each transition is written once; the reducer is unit-testable cell by cell. |
| Single-Flight-Press | Forge in flight is ignored. | Floor 12; a restart would double model spend on a global cap. |
| Keep-Forest-While-Reforging | A re-roll leaves the shown forest up; failures and empty results never remove it. | Each forest is unrepeatable and costs a model call. |
| Show-On-Graph-Not-Clear | A reversible visibility toggle replaces Clear and its confirmation. | Nothing is lost, so no confirmation; no re-feed, so no layout jump. |
| Cancel-In-Flight | A Cancel button while a request runs. | The deadline is 75 s; a wait with no way out is a dead end. |
| No-Client-Cooldown | A 429 leaves the primary enabled. | The message says when; an early retry is a cheap 429. |
| Own-Error-Channel | Forest failures live in the panel, not `errorMessage`. | Shared string, cleared by every lookup. |
| Forge-Uses-Committed-Word | Requests send `result.word`. | The search box changes before a lookup succeeds. |
| Forest-Follows-Committed-Word | Same word keeps the forest, another word clears it, a lookup start or failure changes nothing. | A typo or a repeat search must not destroy a forest. |
| Stale-By-Seq-And-Source | A response applies only under the current `seq`, with a request in flight, for the committed word. | Belt and braces against late responses and our own aborts. |
| Soft-Lookup-From-Forest | Every lookup started from the forest survives a 404. | Forest words are often phrases the thesaurus lacks. |
| Forest-Role-Wins-Clicks | Forest nodes select or navigate; they never expand. | Behaviour follows what is drawn. |
| Hover-Lights-Every-Path | Hover on an endpoint, hop or link lights every path through it. | Build brief. |
| Hover-Beats-Focus-Beats-Selection | One priority rule over three sources. | The most transient input wins and the next one returns when it ends. |
| Selection-Ring | A selection rings its node's label; hover never does. | Presentation must tell a selection from a hover. |
| Touch-Never-Hovers | Touch sets no hover source. | No sticky light after a tap. |
| Mode-Switch-Keeps-Request | Leaving browse mode aborts nothing. | The result is paid for and shown on return. |
| Hops-Persist | Max steps survives word changes and failures. | A preference, not a result. |
| Phone-Bottom-Sheet | A bottom sheet at 768 px and below, with the primary in the always-visible bar. | One tap to forge; the list never needs the graph. |
| Results-Over-Sheet | On a phone an opened results panel slides over the sheet. | One open panel at a time without a new event. |
| Reason-Not-Shown | The judge's `reason` is omitted. | Not in the spec's panel contents. |

## 13. UX floor

| Item | Status |
|---|---|
| 1 contrast, tokens | Met for the panel: every colour is a `var(--…)` token (`web/src/styles/tokens.css`, forest section); primary text on the panel is about 14:1, secondary about 7:1, grounds about 11:1, the focus ring about 9:1. WebGL colours cannot read CSS properties, so the canvas palette is `FOREST_COLOURS` in `web/src/graph/colours.ts`, mirrored as tokens. Dimmed and receded graph labels fall below 4.5:1 on purpose: they are incidental text in a visualisation, and every word is in the panel or the results panel at full contrast. |
| 2 semantic elements | Met: buttons, a select and a checkbox, all named; no `role="button"` spans. List items only observe pointer and focus. |
| 3 keyboard, focus | Met: Max steps, primary, Cancel, Show on graph, sheet toggle, then each item's Highlight path and Look up; visible `:focus-visible` ring; focus rules in 8.3. No modal. |
| 4 touch targets | Met: buttons, select and the checkbox label are at least 2.75 rem (44 px) high and wider than 44 px. |
| 5 colour not sole | Met: "Live" is text, a selection is a ring and `aria-pressed`, a lit item has a structural rule, failures are text in an alert. |
| 6 reduced motion | Met: every transition and animation sits in `prefers-reduced-motion: no-preference` (the pre-existing label transition was moved into one too); sparks off and arrows on under reduce; camera framing is instant. |
| 7 automated audit | Met in Chromium with axe-core 4.10.2 per state (none, loading, shown, failed, phone sheet open): zero violations inside the forest panel. Five page-level violations pre-date the forest (search input `aria-expanded`, viewport `user-scalable=no`, no main landmark, no `h1`, canvas and filters outside landmarks). No jest-axe in the unit harness. |
| 8 labels | Met: "Max steps" and "Show on graph" are visible `label for` elements. |
| 9 invalid field | N/A: the select offers only valid values and the checkbox has no invalid state. |
| 10 values preserved | Met: Max steps survives failures and word changes. |
| 11 announcements | Met (8.3). |
| 12 single flight | Met at three layers: button, handler guard, reducer. |
| 13 no dead ends | Met: each failure names its recovery (5.4). |
| 14, 15 destructive | N/A: no destructive action on this surface. Clear was replaced by a reversible toggle, and New forest replaces model output the user asked to replace (section 10). |
| 16 CTAs | Met: Forge, New forest, Cancel, Highlight path, Look up, Show on graph. |
| 17 error copy | Met (5.4). |
| 18 empty copy | Met: says why and what to do next. |
| 19 one term | Met: "forge" for the operation, "forest" for the result, "step" for a hop, "metaphor" for an item. |
| 20 multi-step | N/A: forging is one step. |
| 21 navigation | N/A: no navigation added. |
| 22 layout | Met: four text sizes in the panel (1.25, 1.05, 0.9 and 0.8 rem), spacing on the `--space-*` scale, one gold primary. |
| 23 images | N/A: no `img`, audio or video. The canvas has no text alternative; the panel is its accessible equivalent. |
| 24 light, dark, 200% zoom | Dark only: the app ships one dark theme and the panel uses the shared tokens. 200% zoom on a 1280 px window lands in the phone layout, checked at 390 px. Text boxes use relative units. Pinch zoom is blocked by the pre-existing `user-scalable=no`. |
| 25 RTL, expansion | Met for the panel: logical properties throughout, no fixed text widths or heights. Not checked under `dir="rtl"`. |

## 14. Negative criteria and the tests that guard them

| Criterion | Test |
|---|---|
| Two Forge presses before the response issue one request. | `mf-app.test.ts` "issues one request for two Forge presses before the response"; `mf-forest-panel.test.ts` "the primary emits forge once…"; `state.test.ts` "Forge while a request is in flight changes nothing" |
| A response for a word that is no longer current never renders. | `mf-app.test.ts` "aborts and drops a forest whose word was replaced by another lookup"; `state.test.ts` "stale responses" block |
| A failed or empty re-roll leaves the shown forest and its list. | `state.test.ts` "a shown forest survives a re-roll…"; `mf-forest-panel.test.ts` "says the last forest is still shown…" |
| A same-word lookup and a second-order expansion keep the forest; another word clears it. | `mf-app.test.ts` "keeps the forest through a repeat lookup…", "clears the forest when another word is committed" |
| A forest lookup that 404s leaves search box, forest and app state as they were. | `mf-app.test.ts` "a forest lookup that 404s…" |
| Single click on a forest node never expands it. | `mf-force-graph.test.ts` "single click on a forest node selects it and never fires mf-node-select" |
| Touch never sets hover. | `mf-force-graph.test.ts` "never sets a forest hover from touch input"; `mf-forest-panel.test.ts` "…touch sets no hover" |
| Highlight changes never call `graphData()`. | `mf-force-graph.test.ts` "lights the paths in forestLit and dims the rest without calling graphData()" |
| Hiding the forest never re-feeds the graph. | `mf-app.test.ts` "hides the forest from the graph without re-feeding the graph data" |
| Unticking every rarity does not hide forest nodes. | `mf-force-graph.test.ts` "keeps forest nodes visible when their rarity is filtered out…" |
| A selection always looks different from a hover. | `mf-force-graph.test.ts` "rings the selected forest node label, whatever else is lit" |
| Model text never renders as markup. | `label-layer.test.ts` "renders model text…", "a ground label shows each ground…"; `mf-forest-panel.test.ts` "renders model text as text, never as markup"; `mf-force-graph.test.ts` hostile word and ground cases |
| A server error string never reaches the UI. | `client.test.ts` "maps HTTP %i to the %s kind" |
| A contract-breaking 200 is a failure, never data. | `client.test.ts` "treats a 200 with %s as a failed forest, never as data" |
