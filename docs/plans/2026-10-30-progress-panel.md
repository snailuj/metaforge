# Search progress panel and steady graph growth

Status: draft for approval, 2026-10-30. Follows PR #26 (merged), so this is a new PR from `main`.

## Why the graph lags and jumps

- After a lookup, every non-central word on the graph is owed a glimpse: its own lookup, which adds its synonyms one level down. With 20-30 words on screen and at most 4 lookups at a time (`MAX_GLIMPSE_LOOKUPS`), the second-order words arrive in 5-8 waves. An expansion queues the same for its children, which gives the third order. The lookup timings have not been measured yet.
- Each finished glimpse calls `graphData()` on the force graph. That resets the simulation to full heat, runs 50 warm-up ticks in one frame, and lets every node drift for up to 30 s. New nodes also start near the origin rather than near their parent. Together these move the whole layout once per arrival.
- The forest already reuses node objects, so its nodes keep their positions; the thesaurus glimpses are the main cause of the jumps.

## Steady growth (answer: yes)

1. New nodes start at their parent's position plus a small random offset, so they grow out of it instead of flying in from the centre.
2. When new nodes arrive, nodes already on screen are held in place (`fx/fy/fz`) while the newcomers settle. They are released once arrivals stop and the newcomers have settled, so the layout can relax slowly instead of in one jump. Dragging a node keeps working as today.
3. Arrivals are batched: glimpse results that finish within about 300 ms of each other go to the graph in one `graphData()` call, not one call each.
4. Rule the tests guard: a node that had settled before an arrival moves less than a small distance during that arrival's warm-up.

## Progress panel

Collapsed (bottom right on desktop):
- While anything is loading: a throbber and a label that cycles "Foraging ...", "Forging ...", "Fording ...", "Foresting ..." every 1.5 s.
- When nothing is loading: a small "Activity" button, so the log stays reachable. It shows no throbber.

Expanded:
- A summary line first: what is still coming, for example "Still loading 12 nearby words and the metaphor forest. More will appear on the graph."
- Then a log, newest last, with one line per stage. Lines that count update in place rather than adding a line per word:
  - "Looked up patience: 4 senses, 23 words."
  - "Fetching nearby words: 11 of 23."
  - "Forging metaphors: 6 paths drafted, 2 kept, 1 dropped."
  - "Judging metaphors for 'dormant seed'."
  - Failures: "3 nearby words could not be fetched."
- When everything has arrived: "All loaded." The panel stays open if the user opened it.

What feeds it:
- Lookups, glimpses and expansions are tracked in the client, which already knows each one's start and end.
- The forest stream already sends `hop`, `kept` and `rejected` events. It does not say when the server is waiting on the model or judging. A new `stage` event (`{"stage": "drafting" | "judging" | "retrying", "facet": i}`) fills those gaps. Older clients ignore unknown events.

Behaviour:
- The collapsed control is a button with `aria-expanded`; Escape closes the expanded panel and returns focus to it.
- Screen readers hear new log lines through a polite live region. The cycling label is not announced.
- With reduced motion set, the throbber does not spin and the label stays on "Foraging ...".
- The forest panel (top right) gets a lower maximum height while the progress panel is open, so the two never overlap.
- On a phone the collapsed control sits bottom right above the forest sheet; expanded, it opens as a sheet across the bottom.
- The open or closed choice is remembered in this browser.
- Hidden in grade mode, which has its own controls in that corner.

## Measuring the lag

Each lookup and glimpse logs its duration (behind the existing timing flag). The PR reports how long the waves take on staging. If lookups dominate, a follow-up can fetch many glimpses in one request; that is not part of this PR.

## Tests (red first)

- Graph: new nodes start at their parent's position; settled nodes stay within the limit across an arrival; arrivals within the window cause one `graphData()` call.
- Progress model: each stage line is created once and updated in place; counts match the glimpses started and finished; "All loaded" appears only when nothing is pending; a superseded lookup clears the log.
- Panel: collapsed shows the throbber only while work is pending; the label cycles; reduced motion holds it still; Escape returns focus; live region gets log lines, not label changes.
- Server: the stream emits `stage` events in order (drafting before the first hop, judging before a facet's verdicts), and a client without `stage` handling still works.

## Review

Fill Override in the review pane (`/review-pane` opens it), or reply with `Item: override` lines. A blank Override keeps the proposal once you have reviewed this table; a blank cell alone does not authorise the work. The lag figures above are a reading of the code, not a measurement.

| Item | Proposed action | Override | Reason |
| --- | --- | --- | --- |
| PR shape | Open one new PR from `main` for the panel and steady growth | | PR #26 is merged, and both parts touch the same graph update path. |
| Seed at parent | Start new nodes at their parent's position | | Removes the fly-in from the centre. |
| Hold settled nodes | Pin on-screen nodes while newcomers settle, then release | | Stops the whole layout moving on each arrival. |
| Batch arrivals | Group glimpse results within about 300 ms into one graph update | | Fewer reheats while waves arrive. |
| Label cycle | Cycle the four labels on a 1.5 s timer, not tied to the stage | | Matches your description; the log carries the real stage. |
| Idle state | Show a small "Activity" button when nothing is loading | | Keeps the log reachable after loading finishes. |
| Stage events | Add a `stage` event to the forest stream | | The client cannot see model waits or judging otherwise. |
| Phone layout | Collapsed control above the forest sheet, expanded as a bottom sheet | | Bottom right is free on desktop but shared on phones. |
| Grade mode | Hide the panel in grade mode | | Grade mode already uses that corner. |
| Faster glimpses | Measure in this PR; leave batched lookups to a follow-up | | Unmeasured lag should not drive a new endpoint. |
