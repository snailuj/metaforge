// Where the page finds the Rust physics module. The single-file build embeds it
// as base64 so the page makes no network request; the dev page fetches it from
// the dev server.

const DEV_URL = '/src/perf/wasm/physics.wasm'
const MAGIC = [0x00, 0x61, 0x73, 0x6d]

const NOT_BUILT = 'The Rust physics module is missing. Build it with: npm run build:wasm'

export async function loadWasmBytes(embeddedBase64: string | undefined, fetchFn: typeof fetch): Promise<Uint8Array<ArrayBuffer>> {
  if (embeddedBase64 !== undefined) {
    return Uint8Array.from(atob(embeddedBase64), c => c.charCodeAt(0))
  }
  const res = await fetchFn(DEV_URL)
  if (!res.ok) throw new Error(`${NOT_BUILT} (${DEV_URL} answered ${res.status})`)
  const bytes = new Uint8Array(await res.arrayBuffer())
  // A dev server may answer a missing file with its HTML page and status 200.
  if (!MAGIC.every((b, i) => bytes[i] === b)) throw new Error(`${NOT_BUILT} (${DEV_URL} is not a WebAssembly module)`)
  return bytes
}
