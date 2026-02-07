# Phase 1 MVP: 3D Force Graph + HUD Results Panel

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the Metaforge frontend — a 3D force-directed graph with a semi-transparent HUD results panel, wired to the existing Go API.

**Architecture:** Vite + Lit web components + TypeScript. `3d-force-graph` (wrapping Three.js + d3-force-3d) for the 3D graph rendered on a full-viewport WebGL canvas. Lit components for the HUD overlay (search bar, results panel). API client fetches from the Go backend (`/thesaurus/lookup`). Fluent (`.ftl`) for UI strings.

**Tech Stack:** Vite, Lit, TypeScript, 3d-force-graph, d3-force-3d, Three.js (via 3d-force-graph), @fluent/bundle, vitest

**Existing backend endpoints (already working, 38 tests passing):**
- `GET /thesaurus/lookup?word=<word>` — senses, synonyms, relations
- `GET /forge/suggest?word=<word>` — metaphor matches (Phase 2, not this plan)
- `GET /strings/v1/ui.ftl` — Fluent strings, immutable cache
- `GET /health` — health check

**API response shape** (from `/thesaurus/lookup?word=melancholy`):
```json
{
  "word": "melancholy",
  "senses": [
    {
      "synset_id": "72858",
      "pos": "noun",
      "definition": "a feeling of thoughtful sadness",
      "synonyms": [
        { "word": "black bile", "synset_id": "62100" }
      ],
      "relations": {
        "hypernyms": [{ "word": "sadness", "synset_id": "72855" }],
        "hyponyms": [
          { "word": "gloom", "synset_id": "72859" },
          { "word": "heavyheartedness", "synset_id": "72860" }
        ],
        "similar": []
      }
    }
  ]
}
```

**Node counts:** "melancholy" produces ~15 unique nodes. "fire" produces ~130 (21 senses). The graph transform must handle both gracefully — cap at ~80 nodes for usability, prioritising synonyms then hyponyms.

**Design reference:** `Metaforge-PRD-2.md` (authoritative PRD), `docs/plans/20260207-prd-reconciliation-scratchpad.md` (decision log)

**File structure we're building:**
```
web/
  index.html
  vite.config.ts
  tsconfig.json
  package.json
  src/
    types/api.ts              # TypeScript types mirroring Go response
    api/client.ts             # lookupWord() fetch wrapper
    graph/
      transform.ts            # LookupResult → GraphData (nodes + links)
      transform.test.ts       # TDD: pure function, highly testable
      types.ts                # GraphNode, GraphLink, GraphData
    lib/
      strings.ts              # Fluent client
      strings.test.ts
    components/
      mf-app.ts               # Root shell — wires search → API → graph + HUD
      mf-search-bar.ts        # Search input with / shortcut
      mf-search-bar.test.ts
      mf-force-graph.ts       # 3d-force-graph wrapper
      mf-results-panel.ts     # HUD overlay with word info
      mf-results-panel.test.ts
    styles/
      tokens.css              # Dark Academic design tokens
      reset.css               # Minimal CSS reset
```

---

## Batch 1: Project Setup + Pure Data Layer

No UI yet. Establish the project, types, API client, and graph transform. All highly testable pure functions.

---

### Task 1: Vite + Lit + TypeScript project scaffolding

**Files:**
- Create: `web/package.json`
- Create: `web/tsconfig.json`
- Create: `web/vite.config.ts`
- Create: `web/index.html`
- Create: `web/src/main.ts`

**Step 1: Create package.json**

```json
{
  "name": "metaforge-web",
  "private": true,
  "version": "0.0.1",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "3d-force-graph": "^1.77.0",
    "lit": "^3.2.0",
    "@fluent/bundle": "^0.18.0"
  },
  "devDependencies": {
    "typescript": "^5.7.0",
    "vite": "^6.1.0",
    "vitest": "^3.0.0",
    "@vitest/coverage-v8": "^3.0.0",
    "happy-dom": "^17.0.0"
  }
}
```

**Step 2: Create tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "moduleResolution": "bundler",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "isolatedModules": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "allowImportingTsExtensions": true,
    "noEmit": true,
    "experimentalDecorators": true,
    "useDefineForClassFields": false,
    "baseUrl": ".",
    "paths": {
      "@/*": ["src/*"]
    }
  },
  "include": ["src"]
}
```

**Step 3: Create vite.config.ts**

```typescript
import { defineConfig } from 'vite'
import { resolve } from 'path'

export default defineConfig({
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/thesaurus': 'http://localhost:8080',
      '/forge': 'http://localhost:8080',
      '/strings': 'http://localhost:8080',
      '/health': 'http://localhost:8080',
    },
  },
  test: {
    environment: 'happy-dom',
    include: ['src/**/*.test.ts'],
  },
})
```

**Step 4: Create index.html**

```html
<!doctype html>
<html lang="en-GB">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Metaforge</title>
    <link rel="stylesheet" href="/src/styles/reset.css" />
    <link rel="stylesheet" href="/src/styles/tokens.css" />
  </head>
  <body>
    <mf-app></mf-app>
    <script type="module" src="/src/main.ts"></script>
  </body>
</html>
```

**Step 5: Create src/main.ts (placeholder)**

```typescript
// App entry — component imports will go here as we build them
console.log('Metaforge starting...')
```

**Step 6: Create src/styles/reset.css**

```css
*, *::before, *::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

html, body {
  height: 100%;
  width: 100%;
  overflow: hidden;
  font-family: var(--font-body);
  background: var(--colour-bg-primary);
  color: var(--colour-text-primary);
}
```

**Step 7: Create src/styles/tokens.css**

```css
:root {
  /* Backgrounds */
  --colour-bg-primary: #1a1a2e;
  --colour-bg-secondary: #16213e;
  --colour-bg-hud: rgba(22, 33, 62, 0.6);

  /* Text */
  --colour-text-primary: #e8e0d4;
  --colour-text-secondary: #a89f94;
  --colour-text-muted: #6b6560;

  /* Accents */
  --colour-accent-gold: #d4af37;
  --colour-accent-gold-dim: rgba(212, 175, 55, 0.5);

  /* Node colours */
  --colour-node-central: #d4af37;
  --colour-node-synonym: #c4956a;
  --colour-node-hypernym: #8b6f47;
  --colour-node-hyponym: #6a8b6f;
  --colour-node-similar: #7a6a8b;

  /* Edges */
  --colour-edge-default: rgba(232, 224, 212, 0.15);
  --colour-edge-highlight: rgba(212, 175, 55, 0.4);

  /* Typography */
  --font-heading: 'Playfair Display', Georgia, serif;
  --font-body: 'Crimson Text', 'Times New Roman', serif;
  --font-mono: 'JetBrains Mono', 'Fira Code', monospace;

  /* Spacing */
  --space-xs: 0.25rem;
  --space-sm: 0.5rem;
  --space-md: 1rem;
  --space-lg: 1.5rem;
  --space-xl: 2rem;

  /* HUD */
  --hud-width: 320px;
  --hud-border: 1px solid rgba(212, 175, 55, 0.2);
  --hud-radius: 4px;
}
```

**Step 8: Install dependencies and verify build**

Run: `cd web && npm install`
Run: `cd web && npx vite build`
Expected: Build succeeds with no errors.

**Step 9: Commit**

```bash
git add web/
git commit -m "feat: scaffold Vite + Lit + TypeScript frontend with Dark Academic tokens"
```

---

### Task 2: TypeScript API types

**Files:**
- Create: `web/src/types/api.ts`

These types mirror the Go response structs exactly.

**Step 1: Create the types file**

```typescript
/** Mirrors Go thesaurus.RelatedWord */
export interface RelatedWord {
  word: string
  synset_id: string
}

/** Mirrors Go thesaurus.Relations */
export interface Relations {
  hypernyms: RelatedWord[]
  hyponyms: RelatedWord[]
  similar: RelatedWord[]
}

/** Mirrors Go thesaurus.Sense */
export interface Sense {
  synset_id: string
  pos: string
  definition: string
  synonyms: RelatedWord[]
  relations: Relations
}

/** Mirrors Go thesaurus.LookupResult */
export interface LookupResult {
  word: string
  senses: Sense[]
}
```

**Step 2: Verify it compiles**

Run: `cd web && npx tsc --noEmit`
Expected: No errors.

**Step 3: Commit**

```bash
git add web/src/types/api.ts
git commit -m "feat: add TypeScript types mirroring Go API response"
```

---

### Task 3: Graph data types

**Files:**
- Create: `web/src/graph/types.ts`

**Step 1: Create graph types**

```typescript
/** Relationship type between nodes — determines colour and edge style */
export type RelationType =
  | 'central'
  | 'synonym'
  | 'hypernym'
  | 'hyponym'
  | 'similar'

/** A node in the force graph */
export interface GraphNode {
  id: string            // Unique: word or word__synsetId for disambiguation
  word: string          // Display label
  synsetId?: string     // Optional synset reference for navigation
  relationType: RelationType
  val: number           // Affects node size in 3d-force-graph
}

/** A link (edge) in the force graph */
export interface GraphLink {
  source: string        // GraphNode.id
  target: string        // GraphNode.id
  relationType: RelationType
}

/** Complete graph data, ready for 3d-force-graph */
export interface GraphData {
  nodes: GraphNode[]
  links: GraphLink[]
}
```

**Step 2: Verify it compiles**

Run: `cd web && npx tsc --noEmit`
Expected: No errors.

**Step 3: Commit**

```bash
git add web/src/graph/types.ts
git commit -m "feat: add graph node/link types for 3d-force-graph"
```

---

### Task 4: Graph data transform (TDD)

The core pure function. Transforms `LookupResult` into `GraphData`. This is the most important piece to get right — it determines what the user sees.

**Files:**
- Create: `web/src/graph/transform.ts`
- Create: `web/src/graph/transform.test.ts`

**Step 1: Write the failing tests**

```typescript
import { describe, it, expect } from 'vitest'
import { transformLookupToGraph } from './transform'
import type { LookupResult } from '@/types/api'

const melancholy: LookupResult = {
  word: 'melancholy',
  senses: [
    {
      synset_id: '62100',
      pos: 'noun',
      definition: 'a humor once believed to cause sadness',
      synonyms: [{ word: 'black bile', synset_id: '62100' }],
      relations: {
        hypernyms: [{ word: 'bodily fluid', synset_id: '62054' }],
        hyponyms: [],
        similar: [],
      },
    },
    {
      synset_id: '72858',
      pos: 'noun',
      definition: 'a feeling of thoughtful sadness',
      synonyms: [],
      relations: {
        hypernyms: [{ word: 'sadness', synset_id: '72855' }],
        hyponyms: [
          { word: 'gloom', synset_id: '72859' },
          { word: 'heavyheartedness', synset_id: '72860' },
        ],
        similar: [],
      },
    },
  ],
}

describe('transformLookupToGraph', () => {
  it('creates a central node for the searched word', () => {
    const graph = transformLookupToGraph(melancholy)
    const central = graph.nodes.find(n => n.relationType === 'central')
    expect(central).toBeDefined()
    expect(central!.word).toBe('melancholy')
    expect(central!.val).toBeGreaterThan(1)
  })

  it('creates synonym nodes with links to central', () => {
    const graph = transformLookupToGraph(melancholy)
    const blackBile = graph.nodes.find(n => n.word === 'black bile')
    expect(blackBile).toBeDefined()
    expect(blackBile!.relationType).toBe('synonym')

    const link = graph.links.find(
      l => l.target === blackBile!.id && l.relationType === 'synonym',
    )
    expect(link).toBeDefined()
  })

  it('creates hypernym nodes with links', () => {
    const graph = transformLookupToGraph(melancholy)
    const sadness = graph.nodes.find(n => n.word === 'sadness')
    expect(sadness).toBeDefined()
    expect(sadness!.relationType).toBe('hypernym')
  })

  it('creates hyponym nodes with links', () => {
    const graph = transformLookupToGraph(melancholy)
    const gloom = graph.nodes.find(n => n.word === 'gloom')
    expect(gloom).toBeDefined()
    expect(gloom!.relationType).toBe('hyponym')
  })

  it('deduplicates nodes that appear in multiple senses', () => {
    const graph = transformLookupToGraph(melancholy)
    const words = graph.nodes.map(n => n.word)
    const unique = new Set(words)
    expect(words.length).toBe(unique.size)
  })

  it('caps nodes at maxNodes (default 80)', () => {
    // Build a big fake response
    const bigResult: LookupResult = {
      word: 'test',
      senses: [
        {
          synset_id: '1',
          pos: 'noun',
          definition: 'test',
          synonyms: Array.from({ length: 100 }, (_, i) => ({
            word: `syn${i}`,
            synset_id: `${i + 100}`,
          })),
          relations: { hypernyms: [], hyponyms: [], similar: [] },
        },
      ],
    }
    const graph = transformLookupToGraph(bigResult)
    expect(graph.nodes.length).toBeLessThanOrEqual(80)
  })

  it('prioritises synonyms over hyponyms when capping', () => {
    const mixedResult: LookupResult = {
      word: 'test',
      senses: [
        {
          synset_id: '1',
          pos: 'noun',
          definition: 'test',
          synonyms: Array.from({ length: 40 }, (_, i) => ({
            word: `syn${i}`,
            synset_id: `${i + 100}`,
          })),
          relations: {
            hypernyms: Array.from({ length: 20 }, (_, i) => ({
              word: `hyper${i}`,
              synset_id: `${i + 200}`,
            })),
            hyponyms: Array.from({ length: 40 }, (_, i) => ({
              word: `hypo${i}`,
              synset_id: `${i + 300}`,
            })),
            similar: [],
          },
        },
      ],
    }
    const graph = transformLookupToGraph(mixedResult)
    // All 40 synonyms should be present (they're prioritised)
    const synNodes = graph.nodes.filter(n => n.relationType === 'synonym')
    expect(synNodes.length).toBe(40)
  })

  it('returns empty graph for empty senses', () => {
    const empty: LookupResult = { word: 'xyz', senses: [] }
    const graph = transformLookupToGraph(empty)
    expect(graph.nodes.length).toBe(1) // just the central node
    expect(graph.links.length).toBe(0)
  })
})
```

**Step 2: Run tests to verify they fail**

Run: `cd web && npx vitest run src/graph/transform.test.ts`
Expected: FAIL — `transformLookupToGraph` does not exist.

**Step 3: Implement the transform**

```typescript
import type { LookupResult, RelatedWord } from '@/types/api'
import type { GraphData, GraphLink, GraphNode, RelationType } from './types'

const DEFAULT_MAX_NODES = 80

/**
 * Transform a LookupResult from the API into GraphData for 3d-force-graph.
 *
 * - Central node = the searched word (gold, larger)
 * - Synonym/relation nodes radiate outward
 * - Deduplicate: same word across senses -> one node, first relation type wins
 * - Cap at maxNodes, prioritising: synonyms > hyponyms > hypernyms > similar
 */
export function transformLookupToGraph(
  result: LookupResult,
  maxNodes = DEFAULT_MAX_NODES,
): GraphData {
  const centralId = result.word
  const nodeMap = new Map<string, GraphNode>()
  const links: GraphLink[] = []

  // Central node — always present
  nodeMap.set(centralId, {
    id: centralId,
    word: result.word,
    relationType: 'central',
    val: 8,
  })

  // Collect all related words by priority tier
  const tiers: { words: RelatedWord[]; type: RelationType }[] = [
    { words: [], type: 'synonym' },
    { words: [], type: 'hyponym' },
    { words: [], type: 'hypernym' },
    { words: [], type: 'similar' },
  ]

  for (const sense of result.senses) {
    tiers[0].words.push(...sense.synonyms)
    tiers[1].words.push(...sense.relations.hyponyms)
    tiers[2].words.push(...sense.relations.hypernyms)
    tiers[3].words.push(...sense.relations.similar)
  }

  // Add nodes by priority until we hit the cap
  let remaining = maxNodes - 1 // minus central node

  for (const tier of tiers) {
    if (remaining <= 0) break

    for (const rw of tier.words) {
      if (remaining <= 0) break
      if (rw.word === result.word) continue // skip self-references

      const nodeId = rw.word
      if (nodeMap.has(nodeId)) continue // deduplicate

      nodeMap.set(nodeId, {
        id: nodeId,
        word: rw.word,
        synsetId: rw.synset_id,
        relationType: tier.type,
        val: tier.type === 'synonym' ? 4 : 2,
      })

      links.push({
        source: centralId,
        target: nodeId,
        relationType: tier.type,
      })

      remaining--
    }
  }

  return {
    nodes: Array.from(nodeMap.values()),
    links,
  }
}
```

**Step 4: Run tests to verify they pass**

Run: `cd web && npx vitest run src/graph/transform.test.ts`
Expected: All 8 tests PASS.

**Step 5: Commit**

```bash
git add web/src/graph/
git commit -m "feat: add graph data transform with dedup, priority tiers, and node cap"
```

---

### Task 5: API client

**Files:**
- Create: `web/src/api/client.ts`

**Step 1: Create the API client**

```typescript
import type { LookupResult } from '@/types/api'

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

/**
 * Look up a word in the thesaurus.
 * Vite dev server proxies /thesaurus/* to localhost:8080.
 */
export async function lookupWord(word: string): Promise<LookupResult> {
  const encoded = encodeURIComponent(word.trim().toLowerCase())
  const response = await fetch(`/thesaurus/lookup?word=${encoded}`)

  if (!response.ok) {
    const body = await response.json().catch(() => ({ error: 'Unknown error' }))
    throw new ApiError(body.error || `HTTP ${response.status}`, response.status)
  }

  return response.json()
}
```

**Step 2: Verify it compiles**

Run: `cd web && npx tsc --noEmit`
Expected: No errors.

**Step 3: Commit**

```bash
git add web/src/api/client.ts
git commit -m "feat: add API client with lookupWord fetch wrapper"
```

---

### Task 6: Fluent strings client (TDD)

**Files:**
- Create: `web/src/lib/strings.ts`
- Create: `web/src/lib/strings.test.ts`

**Step 1: Write the failing test**

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { initStrings, getString } from './strings'

const MOCK_FTL = `
search-placeholder = Search for a word...
results-word-not-found = "{$word}" was not found in the thesaurus.
pos-noun = noun
`

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('Fluent strings', () => {
  it('returns a translated string after init', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve(MOCK_FTL),
    }))

    await initStrings()
    expect(getString('search-placeholder')).toBe('Search for a word...')
  })

  it('interpolates variables', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve(MOCK_FTL),
    }))

    await initStrings()
    const result = getString('results-word-not-found', { word: 'xyzzy' })
    expect(result).toContain('xyzzy')
    expect(result).toContain('was not found in the thesaurus.')
  })

  it('returns the message ID as fallback if not found', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve(MOCK_FTL),
    }))

    await initStrings()
    expect(getString('nonexistent-key')).toBe('nonexistent-key')
  })
})
```

**Step 2: Run tests to verify they fail**

Run: `cd web && npx vitest run src/lib/strings.test.ts`
Expected: FAIL — module does not exist.

**Step 3: Implement**

```typescript
import { FluentBundle, FluentResource } from '@fluent/bundle'

let bundle: FluentBundle | null = null

/**
 * Fetch and parse the Fluent strings file.
 * Call once at app startup.
 */
export async function initStrings(locale = 'en-GB'): Promise<void> {
  const response = await fetch('/strings/v1/ui.ftl')
  if (!response.ok) {
    console.error('Failed to load strings:', response.status)
    return
  }

  const ftl = await response.text()
  bundle = new FluentBundle(locale)
  const resource = new FluentResource(ftl)
  const errors = bundle.addResource(resource)
  if (errors.length) {
    console.error('Fluent parse errors:', errors)
  }
}

/**
 * Get a translated string by message ID.
 * Returns the ID itself as fallback if not found.
 */
export function getString(
  id: string,
  args?: Record<string, string | number>,
): string {
  if (!bundle) return id

  const message = bundle.getMessage(id)
  if (!message?.value) return id

  return bundle.formatPattern(message.value, args)
}
```

**Step 4: Run tests to verify they pass**

Run: `cd web && npx vitest run src/lib/strings.test.ts`
Expected: All 3 tests PASS.

**Step 5: Commit**

```bash
git add web/src/lib/
git commit -m "feat: add Fluent strings client with init and getString"
```

---

## Batch 2: Graph Rendering + Search Component

Wire up the 3D graph and the search bar. After this batch, you can type a word and see nodes bloom.

---

### Task 7: Force graph wrapper component

**Files:**
- Create: `web/src/components/mf-force-graph.ts`

This component wraps `3d-force-graph`. It's hard to unit-test (WebGL), so we test it via integration later.

**Step 1: Create the component**

```typescript
import { LitElement, html, css } from 'lit'
import { customElement, property, state } from 'lit/decorators.js'
import ForceGraph3D from '3d-force-graph'
import type { GraphData, GraphNode } from '@/graph/types'

// Colour map for node types
const NODE_COLOURS: Record<string, string> = {
  central: '#d4af37',
  synonym: '#c4956a',
  hypernym: '#8b6f47',
  hyponym: '#6a8b6f',
  similar: '#7a6a8b',
}

const EDGE_COLOUR = 'rgba(232, 224, 212, 0.15)'

@customElement('mf-force-graph')
export class MfForceGraph extends LitElement {
  static styles = css`
    :host {
      display: block;
      width: 100%;
      height: 100%;
      position: absolute;
      top: 0;
      left: 0;
    }
  `

  @state() private graph: ReturnType<typeof ForceGraph3D> | null = null
  private container: HTMLDivElement | null = null
  private clickTimer: ReturnType<typeof setTimeout> | null = null

  @property({ type: Object }) graphData: GraphData = { nodes: [], links: [] }

  protected firstUpdated(): void {
    this.container = this.renderRoot.querySelector('#graph-container') as HTMLDivElement
    if (!this.container) return

    this.graph = ForceGraph3D(this.container, {
      controlType: 'fly',
    })
      .backgroundColor('#1a1a2e')
      .nodeLabel((node: GraphNode) => node.word)
      .nodeColor((node: GraphNode) => NODE_COLOURS[node.relationType] || '#e8e0d4')
      .nodeVal((node: GraphNode) => node.val)
      .nodeOpacity(0.9)
      .linkColor(() => EDGE_COLOUR)
      .linkWidth(1)
      .linkOpacity(0.6)
      .onNodeClick((node: GraphNode) => {
        if (this.clickTimer) {
          // Double click — navigate
          clearTimeout(this.clickTimer)
          this.clickTimer = null
          this.dispatchEvent(
            new CustomEvent('mf-node-navigate', {
              detail: node, bubbles: true, composed: true,
            }),
          )
        } else {
          // Maybe single click — wait to see if double
          this.clickTimer = setTimeout(() => {
            this.clickTimer = null
            this.dispatchEvent(
              new CustomEvent('mf-node-select', {
                detail: node, bubbles: true, composed: true,
              }),
            )
          }, 300)
        }
      })
      .onNodeRightClick((node: GraphNode, event: MouseEvent) => {
        event.preventDefault()
        navigator.clipboard.writeText(node.word)
        this.dispatchEvent(
          new CustomEvent('mf-node-copy', {
            detail: { word: node.word },
            bubbles: true,
            composed: true,
          }),
        )
      })
      .onNodeHover((node: GraphNode | null) => {
        if (this.container) {
          this.container.style.cursor = node ? 'pointer' : 'default'
        }
      })

    if (this.graphData.nodes.length) {
      this.graph.graphData(this.graphData)
    }
  }

  updated(changed: Map<string, unknown>): void {
    if (changed.has('graphData') && this.graph && this.graphData.nodes.length) {
      this.graph.graphData(this.graphData)
    }
  }

  disconnectedCallback(): void {
    super.disconnectedCallback()
    if (this.clickTimer) clearTimeout(this.clickTimer)
    this.graph = null
  }

  render() {
    return html`<div id="graph-container" style="width:100%;height:100%;"></div>`
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'mf-force-graph': MfForceGraph
  }
}
```

**Step 2: Verify it compiles**

Run: `cd web && npx tsc --noEmit`
Expected: No errors. (May need to create `web/src/types/3d-force-graph.d.ts` with `declare module '3d-force-graph'` if type declarations are missing.)

**Step 3: Commit**

```bash
git add web/src/components/mf-force-graph.ts
git commit -m "feat: add 3d-force-graph wrapper with fly controls, click/dblclick/rightclick"
```

---

### Task 8: Search bar component (TDD)

**Files:**
- Create: `web/src/components/mf-search-bar.ts`
- Create: `web/src/components/mf-search-bar.test.ts`

**Step 1: Write the failing tests**

```typescript
import { describe, it, expect, vi } from 'vitest'
import { MfSearchBar } from './mf-search-bar'

describe('MfSearchBar', () => {
  it('is defined as a custom element', () => {
    expect(MfSearchBar).toBeDefined()
    expect(customElements.get('mf-search-bar')).toBeDefined()
  })

  it('fires mf-search event with trimmed, lowercased word', async () => {
    const el = document.createElement('mf-search-bar') as MfSearchBar
    document.body.appendChild(el)
    await el.updateComplete

    const handler = vi.fn()
    el.addEventListener('mf-search', handler)

    // Simulate typing and submitting
    const input = el.shadowRoot!.querySelector('input')!
    input.value = '  Melancholy  '
    input.dispatchEvent(new Event('input'))
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }))

    expect(handler).toHaveBeenCalledOnce()
    expect(handler.mock.calls[0][0].detail.word).toBe('melancholy')

    document.body.removeChild(el)
  })

  it('does not fire mf-search for empty input', async () => {
    const el = document.createElement('mf-search-bar') as MfSearchBar
    document.body.appendChild(el)
    await el.updateComplete

    const handler = vi.fn()
    el.addEventListener('mf-search', handler)

    const input = el.shadowRoot!.querySelector('input')!
    input.value = '   '
    input.dispatchEvent(new Event('input'))
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }))

    expect(handler).not.toHaveBeenCalled()

    document.body.removeChild(el)
  })
})
```

**Step 2: Run tests to verify they fail**

Run: `cd web && npx vitest run src/components/mf-search-bar.test.ts`
Expected: FAIL.

**Step 3: Implement**

```typescript
import { LitElement, html, css } from 'lit'
import { customElement, state } from 'lit/decorators.js'

@customElement('mf-search-bar')
export class MfSearchBar extends LitElement {
  static styles = css`
    :host {
      display: block;
      position: relative;
      z-index: 10;
    }

    .search-wrapper {
      display: flex;
      align-items: center;
      gap: var(--space-sm, 0.5rem);
      padding: var(--space-sm, 0.5rem) var(--space-md, 1rem);
      background: var(--colour-bg-hud, rgba(22, 33, 62, 0.6));
      border: var(--hud-border, 1px solid rgba(212, 175, 55, 0.2));
      border-radius: var(--hud-radius, 4px);
      backdrop-filter: blur(8px);
    }

    input {
      flex: 1;
      background: transparent;
      border: none;
      outline: none;
      color: var(--colour-text-primary, #e8e0d4);
      font-family: var(--font-body, serif);
      font-size: 1.1rem;
    }

    input::placeholder {
      color: var(--colour-text-muted, #6b6560);
    }

    .shortcut-hint {
      color: var(--colour-text-muted, #6b6560);
      font-size: 0.75rem;
      font-family: var(--font-mono, monospace);
    }
  `

  @state() private value = ''

  connectedCallback(): void {
    super.connectedCallback()
    document.addEventListener('keydown', this.handleGlobalKeydown)
  }

  disconnectedCallback(): void {
    super.disconnectedCallback()
    document.removeEventListener('keydown', this.handleGlobalKeydown)
  }

  private handleGlobalKeydown = (e: KeyboardEvent) => {
    if (e.key === '/' && document.activeElement !== this.inputEl) {
      e.preventDefault()
      this.inputEl?.focus()
    }
  }

  private get inputEl(): HTMLInputElement | null {
    return this.shadowRoot?.querySelector('input') ?? null
  }

  private handleInput(e: Event) {
    this.value = (e.target as HTMLInputElement).value
  }

  private handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter') {
      this.submit()
    }
    if (e.key === 'Escape') {
      this.value = ''
      if (this.inputEl) this.inputEl.value = ''
      this.inputEl?.blur()
    }
  }

  private submit() {
    const word = this.value.trim().toLowerCase()
    if (!word) return

    this.dispatchEvent(
      new CustomEvent('mf-search', {
        detail: { word },
        bubbles: true,
        composed: true,
      }),
    )
  }

  render() {
    return html`
      <div class="search-wrapper">
        <input
          type="text"
          placeholder="Search for a word..."
          .value=${this.value}
          @input=${this.handleInput}
          @keydown=${this.handleKeydown}
          aria-label="Search for a word"
          role="searchbox"
        />
        <span class="shortcut-hint">/</span>
      </div>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'mf-search-bar': MfSearchBar
  }
}
```

**Step 4: Run tests to verify they pass**

Run: `cd web && npx vitest run src/components/mf-search-bar.test.ts`
Expected: All 3 tests PASS.

**Step 5: Commit**

```bash
git add web/src/components/mf-search-bar.ts web/src/components/mf-search-bar.test.ts
git commit -m "feat: add search bar component with / shortcut and mf-search event"
```

---

### Task 9: Results panel component (TDD)

**Files:**
- Create: `web/src/components/mf-results-panel.ts`
- Create: `web/src/components/mf-results-panel.test.ts`

**Step 1: Write the failing tests**

```typescript
import { describe, it, expect, vi } from 'vitest'
import { MfResultsPanel } from './mf-results-panel'
import type { LookupResult } from '@/types/api'

const melancholy: LookupResult = {
  word: 'melancholy',
  senses: [
    {
      synset_id: '72858',
      pos: 'noun',
      definition: 'a feeling of thoughtful sadness',
      synonyms: [{ word: 'sadness', synset_id: '72855' }],
      relations: {
        hypernyms: [{ word: 'emotion', synset_id: '1' }],
        hyponyms: [{ word: 'gloom', synset_id: '2' }],
        similar: [],
      },
    },
  ],
}

describe('MfResultsPanel', () => {
  it('is defined as a custom element', () => {
    expect(MfResultsPanel).toBeDefined()
    expect(customElements.get('mf-results-panel')).toBeDefined()
  })

  it('renders the word heading when result is set', async () => {
    const el = document.createElement('mf-results-panel') as MfResultsPanel
    el.result = melancholy
    document.body.appendChild(el)
    await el.updateComplete

    const heading = el.shadowRoot!.querySelector('h2')
    expect(heading?.textContent).toContain('melancholy')

    document.body.removeChild(el)
  })

  it('renders sense definitions', async () => {
    const el = document.createElement('mf-results-panel') as MfResultsPanel
    el.result = melancholy
    document.body.appendChild(el)
    await el.updateComplete

    const defs = el.shadowRoot!.querySelectorAll('.definition')
    expect(defs.length).toBeGreaterThan(0)
    expect(defs[0].textContent).toContain('thoughtful sadness')

    document.body.removeChild(el)
  })

  it('fires mf-word-navigate on double-click of a related word', async () => {
    const el = document.createElement('mf-results-panel') as MfResultsPanel
    el.result = melancholy
    document.body.appendChild(el)
    await el.updateComplete

    const handler = vi.fn()
    el.addEventListener('mf-word-navigate', handler)

    const wordEl = el.shadowRoot!.querySelector('[data-word]')
    wordEl?.dispatchEvent(new MouseEvent('dblclick', { bubbles: true }))

    expect(handler).toHaveBeenCalledOnce()

    document.body.removeChild(el)
  })
})
```

**Step 2: Run tests to verify they fail**

Run: `cd web && npx vitest run src/components/mf-results-panel.test.ts`
Expected: FAIL.

**Step 3: Implement**

```typescript
import { LitElement, html, css, nothing } from 'lit'
import { customElement, property } from 'lit/decorators.js'
import type { LookupResult, Sense, RelatedWord } from '@/types/api'

@customElement('mf-results-panel')
export class MfResultsPanel extends LitElement {
  static styles = css`
    :host {
      display: block;
      position: absolute;
      top: var(--space-xl, 2rem);
      left: var(--space-md, 1rem);
      bottom: var(--space-xl, 2rem);
      width: var(--hud-width, 320px);
      z-index: 10;
      overflow-y: auto;
      scrollbar-width: thin;
      scrollbar-color: var(--colour-accent-gold-dim) transparent;
    }

    .panel {
      background: var(--colour-bg-hud, rgba(22, 33, 62, 0.6));
      border: var(--hud-border, 1px solid rgba(212, 175, 55, 0.2));
      border-radius: var(--hud-radius, 4px);
      backdrop-filter: blur(8px);
      padding: var(--space-md, 1rem);
    }

    h2 {
      font-family: var(--font-heading, serif);
      color: var(--colour-accent-gold, #d4af37);
      font-size: 1.5rem;
      margin-bottom: var(--space-sm, 0.5rem);
    }

    .sense {
      margin-bottom: var(--space-md, 1rem);
      padding-bottom: var(--space-md, 1rem);
      border-bottom: 1px solid rgba(212, 175, 55, 0.1);
    }

    .sense:last-child {
      border-bottom: none;
      margin-bottom: 0;
      padding-bottom: 0;
    }

    .pos-badge {
      display: inline-block;
      font-size: 0.75rem;
      color: var(--colour-text-secondary, #a89f94);
      font-style: italic;
      margin-bottom: var(--space-xs, 0.25rem);
    }

    .definition {
      font-size: 0.95rem;
      line-height: 1.5;
      margin-bottom: var(--space-sm, 0.5rem);
    }

    .section-label {
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--colour-text-muted, #6b6560);
      margin-bottom: var(--space-xs, 0.25rem);
      margin-top: var(--space-sm, 0.5rem);
    }

    .word-list {
      display: flex;
      flex-wrap: wrap;
      gap: var(--space-xs, 0.25rem);
    }

    .word-chip {
      font-size: 0.9rem;
      color: var(--colour-text-primary, #e8e0d4);
      cursor: pointer;
      padding: 2px 6px;
      border-radius: 3px;
      transition: background 0.15s;
    }

    .word-chip:hover {
      background: rgba(212, 175, 55, 0.15);
    }

    .word-chip.synonym { color: #c4956a; }
    .word-chip.hypernym { color: #8b6f47; }
    .word-chip.hyponym { color: #6a8b6f; }
    .word-chip.similar { color: #7a6a8b; }
  `

  @property({ type: Object }) result: LookupResult | null = null

  private handleWordDblClick(word: string) {
    this.dispatchEvent(
      new CustomEvent('mf-word-navigate', {
        detail: { word },
        bubbles: true,
        composed: true,
      }),
    )
  }

  private handleWordRightClick(e: MouseEvent, word: string) {
    e.preventDefault()
    navigator.clipboard.writeText(word)
    this.dispatchEvent(
      new CustomEvent('mf-word-copy', {
        detail: { word },
        bubbles: true,
        composed: true,
      }),
    )
  }

  private renderWordChip(rw: RelatedWord, type: string) {
    return html`
      <span
        class="word-chip ${type}"
        data-word=${rw.word}
        @dblclick=${() => this.handleWordDblClick(rw.word)}
        @contextmenu=${(e: MouseEvent) => this.handleWordRightClick(e, rw.word)}
        title="Double-click to navigate, right-click to copy"
      >${rw.word}</span>
    `
  }

  private renderSense(sense: Sense) {
    return html`
      <div class="sense">
        <span class="pos-badge">${sense.pos}</span>
        <div class="definition">${sense.definition}</div>

        ${sense.synonyms.length
          ? html`
              <div class="section-label">Synonyms</div>
              <div class="word-list">
                ${sense.synonyms.map(s => this.renderWordChip(s, 'synonym'))}
              </div>
            `
          : nothing}

        ${sense.relations.hypernyms.length
          ? html`
              <div class="section-label">Broader terms</div>
              <div class="word-list">
                ${sense.relations.hypernyms.map(h => this.renderWordChip(h, 'hypernym'))}
              </div>
            `
          : nothing}

        ${sense.relations.hyponyms.length
          ? html`
              <div class="section-label">Narrower terms</div>
              <div class="word-list">
                ${sense.relations.hyponyms.map(h => this.renderWordChip(h, 'hyponym'))}
              </div>
            `
          : nothing}

        ${sense.relations.similar.length
          ? html`
              <div class="section-label">Similar</div>
              <div class="word-list">
                ${sense.relations.similar.map(s => this.renderWordChip(s, 'similar'))}
              </div>
            `
          : nothing}
      </div>
    `
  }

  render() {
    if (!this.result) {
      return nothing
    }

    return html`
      <div class="panel" role="region" aria-label="Thesaurus results">
        <h2>${this.result.word}</h2>
        ${this.result.senses.map(s => this.renderSense(s))}
      </div>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'mf-results-panel': MfResultsPanel
  }
}
```

**Step 4: Run tests to verify they pass**

Run: `cd web && npx vitest run src/components/mf-results-panel.test.ts`
Expected: All 4 tests PASS.

**Step 5: Commit**

```bash
git add web/src/components/mf-results-panel.ts web/src/components/mf-results-panel.test.ts
git commit -m "feat: add HUD results panel with sense display, word chips, and navigation events"
```

---

## Batch 3: App Shell + Integration

Wire everything together. After this batch, the app is usable end-to-end.

---

### Task 10: App shell component

**Files:**
- Create: `web/src/components/mf-app.ts`
- Create: `web/src/components/mf-toast.ts`
- Modify: `web/src/main.ts`

This is the orchestrator — wires search -> API -> transform -> graph + results panel.

**Step 1: Create the toast component**

```typescript
import { LitElement, html, css } from 'lit'
import { customElement, state } from 'lit/decorators.js'

@customElement('mf-toast')
export class MfToast extends LitElement {
  static styles = css`
    :host {
      position: fixed;
      bottom: var(--space-xl, 2rem);
      left: 50%;
      transform: translateX(-50%);
      z-index: 100;
      pointer-events: none;
    }

    .toast {
      background: var(--colour-accent-gold, #d4af37);
      color: var(--colour-bg-primary, #1a1a2e);
      padding: var(--space-xs, 0.25rem) var(--space-md, 1rem);
      border-radius: var(--hud-radius, 4px);
      font-family: var(--font-body, serif);
      font-size: 0.9rem;
      opacity: 0;
      transition: opacity 0.2s ease;
    }

    .toast.visible {
      opacity: 1;
    }
  `

  @state() private message = ''
  @state() private visible = false
  private hideTimer: ReturnType<typeof setTimeout> | null = null

  show(message: string, duration = 1500) {
    this.message = message
    this.visible = true

    if (this.hideTimer) clearTimeout(this.hideTimer)
    this.hideTimer = setTimeout(() => {
      this.visible = false
    }, duration)
  }

  render() {
    return html`
      <div class="toast ${this.visible ? 'visible' : ''}">${this.message}</div>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'mf-toast': MfToast
  }
}
```

**Step 2: Create the app shell**

```typescript
import { LitElement, html, css } from 'lit'
import { customElement, state } from 'lit/decorators.js'
import { lookupWord, ApiError } from '@/api/client'
import { transformLookupToGraph } from '@/graph/transform'
import { initStrings } from '@/lib/strings'
import type { LookupResult } from '@/types/api'
import type { GraphData } from '@/graph/types'
import type { MfToast } from './mf-toast'

// Import components so they register
import './mf-search-bar'
import './mf-force-graph'
import './mf-results-panel'
import './mf-toast'

type AppState = 'idle' | 'loading' | 'ready' | 'error'

@customElement('mf-app')
export class MfApp extends LitElement {
  static styles = css`
    :host {
      display: block;
      width: 100vw;
      height: 100vh;
      position: relative;
      overflow: hidden;
      background: var(--colour-bg-primary, #1a1a2e);
    }

    .search-container {
      position: absolute;
      top: var(--space-md, 1rem);
      left: 50%;
      transform: translateX(-50%);
      width: min(480px, calc(100% - 2rem));
      z-index: 20;
    }

    mf-force-graph {
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      z-index: 1;
    }

    mf-results-panel {
      z-index: 10;
    }

    .status-message {
      position: absolute;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      color: var(--colour-text-muted, #6b6560);
      font-family: var(--font-body, serif);
      font-size: 1.1rem;
      text-align: center;
      z-index: 5;
    }

    .error-message {
      color: #c47a7a;
    }

    .loading-ring {
      width: 40px;
      height: 40px;
      border: 3px solid var(--colour-accent-gold-dim, rgba(212, 175, 55, 0.3));
      border-top-color: var(--colour-accent-gold, #d4af37);
      border-radius: 50%;
      animation: spin 1s linear infinite;
      margin: 0 auto var(--space-md, 1rem);
    }

    @keyframes spin {
      to { transform: rotate(360deg); }
    }
  `

  @state() private appState: AppState = 'idle'
  @state() private result: LookupResult | null = null
  @state() private graphData: GraphData = { nodes: [], links: [] }
  @state() private errorMessage = ''

  async connectedCallback(): Promise<void> {
    super.connectedCallback()
    await initStrings()

    // Check URL hash for initial word
    const hashWord = this.getWordFromHash()
    if (hashWord) {
      this.doLookup(hashWord)
    }

    window.addEventListener('hashchange', this.handleHashChange)
  }

  disconnectedCallback(): void {
    super.disconnectedCallback()
    window.removeEventListener('hashchange', this.handleHashChange)
  }

  private handleHashChange = () => {
    const word = this.getWordFromHash()
    if (word) {
      this.doLookup(word)
    }
  }

  private getWordFromHash(): string | null {
    const match = window.location.hash.match(/^#\/word\/(.+)$/)
    return match ? decodeURIComponent(match[1]) : null
  }

  private setWordHash(word: string) {
    const newHash = `#/word/${encodeURIComponent(word)}`
    if (window.location.hash !== newHash) {
      window.location.hash = newHash
    }
  }

  private async handleSearch(e: CustomEvent<{ word: string }>) {
    this.doLookup(e.detail.word)
  }

  private async handleNodeNavigate(e: CustomEvent) {
    const node = e.detail
    if (node?.word) {
      this.doLookup(node.word)
    }
  }

  private handleWordNavigate(e: CustomEvent<{ word: string }>) {
    this.doLookup(e.detail.word)
  }

  private handleCopy(e: CustomEvent<{ word: string }>) {
    const toast = this.shadowRoot?.querySelector('mf-toast') as MfToast | null
    toast?.show(`Copied "${e.detail.word}"`)
  }

  private async doLookup(word: string) {
    this.appState = 'loading'
    this.errorMessage = ''

    try {
      const result = await lookupWord(word)
      this.result = result
      this.graphData = transformLookupToGraph(result)
      this.appState = 'ready'
      this.setWordHash(word)
    } catch (err) {
      this.appState = 'error'
      if (err instanceof ApiError && err.status === 404) {
        this.errorMessage = `"${word}" was not found in the thesaurus.`
      } else {
        this.errorMessage = 'Something went wrong. Please try again.'
      }
    }
  }

  render() {
    return html`
      <div class="search-container">
        <mf-search-bar @mf-search=${this.handleSearch}></mf-search-bar>
      </div>

      <div role="status" aria-live="polite" aria-atomic="true">
        ${this.appState === 'loading'
          ? html`
              <div class="status-message">
                <div class="loading-ring"></div>
                Loading...
              </div>
            `
          : ''}

        ${this.appState === 'error'
          ? html`<div class="status-message error-message">${this.errorMessage}</div>`
          : ''}

        ${this.appState === 'idle'
          ? html`<div class="status-message">Search for a word to begin exploring.</div>`
          : ''}
      </div>

      <mf-force-graph
        .graphData=${this.graphData}
        @mf-node-select=${() => {}}
        @mf-node-navigate=${this.handleNodeNavigate}
        @mf-node-copy=${this.handleCopy}
      ></mf-force-graph>

      <mf-results-panel
        .result=${this.result}
        @mf-word-navigate=${this.handleWordNavigate}
        @mf-word-copy=${this.handleCopy}
      ></mf-results-panel>

      <mf-toast></mf-toast>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'mf-app': MfApp
  }
}
```

**Step 3: Update main.ts**

```typescript
// App entry — register all components
import './components/mf-app'
```

**Step 4: Verify it compiles**

Run: `cd web && npx tsc --noEmit`
Expected: No errors.

**Step 5: Commit**

```bash
git add web/src/components/mf-app.ts web/src/components/mf-toast.ts web/src/main.ts
git commit -m "feat: add app shell wiring search -> API -> graph + HUD panel + toast"
```

---

### Task 11: Manual integration test

This is a visual/manual verification that the whole stack works end to end.

**Step 1: Start the Go API server**

Use skill: `metaforge-api-test health` (or manually start the server).

**Step 2: Start the Vite dev server**

```bash
cd web && npm run dev
```

**Step 3: Open browser and verify**

Navigate to `http://localhost:5173`

Check:
- [ ] Dark Academic background renders (deep navy `#1a1a2e`)
- [ ] Search bar visible top-centre with gold border on focus
- [ ] `/` key focuses the search bar
- [ ] Type "melancholy" + Enter -> loading spinner -> graph blooms
- [ ] Central node is gold, synonyms amber, hypernyms brown, hyponyms green
- [ ] HUD panel on left shows senses, definitions, word chips
- [ ] WASD moves the camera, mouse look works
- [ ] Single-click a node -> select event (no navigation)
- [ ] Double-click a node -> graph reshuffles to new word
- [ ] Right-click a node -> word copied + "Copied" toast
- [ ] Double-click word chip in HUD -> new lookup (e.g. "gloom")
- [ ] URL updates to `#/word/melancholy`
- [ ] Direct navigation to `http://localhost:5173/#/word/fire` loads fire
- [ ] "fire" produces a large graph (~80 capped nodes)
- [ ] Unknown word (e.g. "xyzzyplugh") -> error message
- [ ] Escape in search bar clears and blurs

**Step 4: Stop servers**

```bash
pkill -f 'go run ./cmd/metaforge' 2>/dev/null; true
```

**Step 5: Commit (if any fixes were needed)**

```bash
git add -A
git commit -m "fix: integration fixes from manual testing"
```

---

### Task 12: Run all tests, final verification

**Step 1: Run all frontend tests**

Run: `cd web && npx vitest run`
Expected: All tests pass (transform: 8, search-bar: 3, results-panel: 4, strings: 3 = ~18 tests).

**Step 2: Run all Go tests**

Run: `cd api && /usr/local/go/bin/go test ./... -v`
Expected: All 38 tests pass.

**Step 3: Commit any final fixes**

---

## Known Gaps (Deliberate Deferrals)

| Gap | Reason | When |
|-----|--------|------|
| Antonyms | `lexrelations` not imported from sqlunet | Fast-follow |
| Rarity badges | `frequencies` table empty, needs SUBTLEX-UK | Phase 1 stretch |
| Fuzzy search | Exact lemma match only | Future |
| Second theme | Dark Academic only | Phase 3 |
| Node drag | d3/3d-force-graph supports it natively but needs mouse-look disable logic | Polish |
| Mouse-look disable on HUD hover | Needs implementation in mf-force-graph | Polish |
| `prefers-reduced-motion` | Needs graph animation disable | Polish |
| Debounced search | Search fires on Enter only (no live search) | Polish |
| Fluent string usage in components | Components use hardcoded strings; wire to getString() | Polish |

---

## Verification

```bash
# Backend tests
cd api && /usr/local/go/bin/go test ./... -v

# Frontend tests
cd web && npx vitest run

# Integration
cd api && /usr/local/go/bin/go run ./cmd/metaforge --db ../data-pipeline/output/lexicon_v2.db &
cd web && npm run dev
# Open http://localhost:5173
# Type "melancholy" -> graph blooms with gold central node
# Double-click "gloom" -> graph reshuffles
# Right-click any node -> "Copied" toast
# Navigate to /#/word/fire -> large graph loads
# Press / -> search bar focuses
```
