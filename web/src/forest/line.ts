/**
 * The generator writes each line as "SOURCE is ENDPOINT, <elaboration>" because
 * the judge checks that shape for a swapped source and endpoint. The reader
 * already sees the source and the endpoint, so the panel shows only the
 * elaboration. Stored and cached forests keep the full line; this runs at
 * display time only.
 */
const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

// A word as the model may inflect it: case-free, spaces flexible, optional plural.
const wordPattern = (w: string) => `(?<!\\w)${escape(w.trim()).replace(/\s+/g, '\\s+')}(?:e?s)?(?!\\w)`

export function displayLine(line: string, source: string, endpoint: string): string {
  if (!source.trim() || !endpoint.trim()) return line
  const opening = new RegExp(
    // Optional determiner or possessive ("Her patience"), then the copula, then
    // anything short of punctuation up to the endpoint, then the separator.
    `^\\s*(?:\\w+\\s+)?${wordPattern(source)}\\s+(?:is|are|was|were)\\s+[^,:;.!?\\u2013\\u2014]*?${wordPattern(endpoint)}` +
      `\\s*(?:[,:;\\u2013\\u2014]|\\s-{1,2})\\s*`,
    'i',
  )
  const m = opening.exec(line)
  if (!m) return line
  const rest = line.slice(m[0].length).trim()
  if (!/\p{L}/u.test(rest)) return line
  return rest.charAt(0).toLocaleUpperCase() + rest.slice(1)
}
