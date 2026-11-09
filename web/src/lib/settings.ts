// Hidden settings: no UI, set by hand in the browser console, e.g.
//   localStorage.setItem('mf-hold-graph', '1')
// and read once, when the app loads.

const HOLD_GRAPH_KEY = 'mf-hold-graph'

/** Hold words already on the graph still while newcomers settle. Off by default:
 *  the lookup overlay locks the graph during nearby-word lookups instead. */
export function holdGraphEnabled(stored: () => string | null = () => localStorage.getItem(HOLD_GRAPH_KEY)): boolean {
  try {
    return stored() === '1'
  } catch (err) {
    console.warn('[settings] could not read the hold-graph setting; it stays off', err)
    return false
  }
}
