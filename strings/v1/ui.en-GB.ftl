## Core Thesaurus — UI strings (en-GB)

search-placeholder = Search for a word…
search-aria-label = Search the thesaurus

status-idle = Type a word to explore
status-loading = Looking up…
error-generic = Something went wrong. Please try again.

results-word-not-found = "{$word}" was not found in the thesaurus.
results-aria-label = Thesaurus results
results-synonyms = Synonyms
results-broader = Broader terms
results-narrower = Narrower terms
results-similar = Similar

word-chip-title = Click to look up, right-click to copy
toast-copied = Copied "{$word}"

## Rarity badges
rarity-common = common
rarity-unusual = unusual
rarity-rare = rare

## Collapsible results panel
panel-expand = Explore »
panel-collapse-label = Collapse results panel

## HUD filter toggles
filter-common = Common
filter-unusual = Unusual
filter-rare = Rare
filter-aria-label = Filter by word rarity

## Metaphor forest panel
forest-heading = Metaphor forest
forest-intro = Grow fresh metaphors for “{ $word }”. Each one is a path of shared qualities, drawn on the graph.
forest-max-steps = Max steps
forest-steps-option = { $n ->
    [one] 1 step
   *[other] { $n } steps
  }
forest-forge = Forge
forest-forge-new = New forest
forest-forging = Forging…
forest-cancel = Cancel
forest-show-on-graph = Show on graph
forest-loading = Forging metaphors for “{ $word }”. This can take up to a minute.
forest-loading-kept = Forging a new forest for “{ $word }”. The current one stays until it arrives.
forest-found = { $n ->
    [one] Found 1 metaphor
   *[other] Found { $n } metaphors
  } for “{ $word }”. { $live ->
    [0] None are live.
    [one] 1 is live.
   *[other] { $live } are live.
  }
forest-empty = No metaphors passed the quality check for “{ $word }” this time. The forge tried { $generated } and kept none. Press Forge to try again, or look up another word.
forest-empty-kept = The new forest had no metaphors that passed the quality check, so your last forest is still shown. Press New forest to try again.
forest-cancelled = Forging stopped.
forest-cancelled-kept = Forging stopped. Your last forest is still shown.
forest-error-invalid-word = “{ $word }” can’t be forged. The forge takes words and short phrases made of letters, spaces, hyphens and apostrophes, up to 40 characters. Look up a different word to try again.
forest-error-busy = The forge is busy right now. Try again in { $seconds ->
    [one] 1 second
   *[other] { $seconds } seconds
  }.
forest-error-busy-soon = The forge is busy right now. Try again in a moment.
forest-error-failed = The forge couldn’t grow a forest this time. Try again; each try can give different metaphors.
forest-error-not-configured = The metaphor forest isn’t turned on for this server. The thesaurus still works. Ask the site owner to turn the forest on.
forest-error-timeout = The forge took too long and stopped. Try again, or choose fewer steps.
forest-error-network = Couldn’t reach the server. Check your connection, then try again.
forest-error-kept = Your last forest is still shown.
forest-list-label = Metaphors for “{ $word }”, best first
forest-legend = Live means the judge rated it 7 or more out of 10.
forest-live = Live
forest-score = Score { $score } out of 10
forest-path-label = Path from “{ $source }” to “{ $endpoint }”
forest-joined-by = joined by
forest-highlight = Highlight path
forest-highlight-name = Highlight the path to “{ $endpoint }”
forest-lookup = Look up
forest-lookup-name = Look up “{ $endpoint }” in the thesaurus
forest-sheet-show = { $n ->
    [one] Show 1 metaphor
   *[other] Show { $n } metaphors
  }
forest-sheet-hide = Hide metaphors
forest-lookup-missing = “{ $word }” isn’t in the thesaurus. Your forest is unchanged.
