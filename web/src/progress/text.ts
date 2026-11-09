// Words for the activity log, shared by the activity panel and the lookup overlay.

import { getString } from '@/lib/strings'
import { pendingOf, type ProgressLine, type ProgressState } from '@/progress/model'

/** The collapsed label; cycles on a timer, not with the stage (the log carries the stage). */
export function label(i: number): string {
  switch (i % 4) {
    case 0: return getString('progress-label-foraging')
    case 1: return getString('progress-label-forging')
    case 2: return getString('progress-label-fording')
    default: return getString('progress-label-foresting')
  }
}

export function lineText(l: ProgressLine): string {
  switch (l.kind) {
    case 'lookup': return getString('progress-line-lookup', { word: l.word, senses: l.senses, words: l.words })
    case 'lookup-failed': return getString('progress-line-lookup-failed', { word: l.word })
    case 'nearby': return getString('progress-line-nearby', { done: l.done, total: l.total })
    case 'nearby-failed': return getString('progress-line-nearby-failed', { n: l.n })
    case 'expanded': return getString('progress-line-expanded', { word: l.word, words: l.words })
    case 'expand-failed': return getString('progress-line-expand-failed', { word: l.word })
    case 'forging': return getString('progress-line-forging', { drafted: l.drafted, kept: l.kept, dropped: l.dropped })
    case 'retrying': return getString('progress-line-retrying')
    case 'judging': return getString('progress-line-judging', { word: l.word })
    case 'forest-ready': return getString('progress-line-forest-ready', { n: l.n })
    case 'forest-failed': return getString('progress-line-forest-failed')
    case 'forest-cancelled': return getString('progress-line-forest-cancelled')
    case 'all-loaded': return getString('progress-line-all-loaded')
  }
}

/** What is still coming, as one sentence; or that nothing is. */
export function summaryText(s: ProgressState): string {
  const p = pendingOf(s)
  const items = [
    p.lookup !== null ? getString('progress-pending-lookup', { word: p.lookup }) : '',
    p.nearby > 0 ? getString('progress-pending-nearby', { n: p.nearby }) : '',
    p.expansions > 0 ? getString('progress-pending-opened', { n: p.expansions }) : '',
    p.forest ? getString('progress-pending-forest') : '',
  ].filter(Boolean)
  if (items.length) return getString('progress-summary', { items: new Intl.ListFormat('en-GB', { type: 'conjunction' }).format(items) })
  return s.lines.length ? getString('progress-summary-idle') : getString('progress-empty')
}
