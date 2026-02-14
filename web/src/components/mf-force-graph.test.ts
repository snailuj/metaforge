import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import type { GraphData } from '@/graph/types'
import { RARITY_COLOURS } from '@/graph/colours'

// Capture the accessor functions passed to the graph instance
let capturedNodeVisibility: ((node: unknown) => boolean) | null = null
let capturedLinkVisibility: ((link: unknown) => boolean) | null = null
let capturedNodeColor: ((node: unknown) => string) | null = null

const chainable: Record<string, unknown> = new Proxy({}, {
  get: (_t, prop) => {
    if (prop === 'nodeVisibility') {
      return (fn: (node: unknown) => boolean) => {
        capturedNodeVisibility = fn
        return chainable
      }
    }
    if (prop === 'linkVisibility') {
      return (fn: (link: unknown) => boolean) => {
        capturedLinkVisibility = fn
        return chainable
      }
    }
    if (prop === 'nodeColor') {
      return (fn: (node: unknown) => string) => {
        capturedNodeColor = fn
        return chainable
      }
    }
    return () => chainable
  },
})

vi.mock('3d-force-graph', () => ({ default: () => () => chainable }))
vi.mock('three-spritetext', () => ({ default: vi.fn() }))

import { MfForceGraph } from './mf-force-graph'

const testData: GraphData = {
  nodes: [
    { id: 'fire', word: 'fire', relationType: 'central', val: 8 },
    { id: 'blaze', word: 'blaze', relationType: 'synonym', val: 4, rarity: 'common' },
    { id: 'conflagration', word: 'conflagration', relationType: 'synonym', val: 4, rarity: 'rare' },
    { id: 'flame', word: 'flame', relationType: 'synonym', val: 4 }, // no rarity → defaults to 'unusual'
  ],
  links: [
    { source: 'fire', target: 'blaze', relationType: 'synonym' },
    { source: 'fire', target: 'conflagration', relationType: 'synonym' },
    { source: 'fire', target: 'flame', relationType: 'synonym' },
  ],
}

describe('MfForceGraph', () => {
  let el: MfForceGraph

  beforeEach(async () => {
    capturedNodeVisibility = null
    capturedLinkVisibility = null
    capturedNodeColor = null
    el = new MfForceGraph()
    el.graphData = testData
    document.body.appendChild(el)
    await el.updateComplete
  })

  afterEach(() => {
    document.body.removeChild(el)
  })

  it('is defined as a custom element', () => {
    expect(customElements.get('mf-force-graph')).toBeDefined()
  })

  it('sets nodeVisibility accessor on firstUpdated', () => {
    expect(capturedNodeVisibility).toBeTypeOf('function')
  })

  it('sets linkVisibility accessor on firstUpdated', () => {
    expect(capturedLinkVisibility).toBeTypeOf('function')
  })

  it('shows all nodes when hiddenRarities is empty', () => {
    expect(capturedNodeVisibility).not.toBeNull()
    for (const node of testData.nodes) {
      expect(capturedNodeVisibility!(node)).toBe(true)
    }
  })

  it('always shows central node regardless of hiddenRarities', async () => {
    el.hiddenRarities = new Set(['common', 'unusual', 'rare'])
    await el.updateComplete

    const central = testData.nodes.find(n => n.relationType === 'central')!
    expect(capturedNodeVisibility!(central)).toBe(true)
  })

  it('hides nodes whose rarity is in hiddenRarities', async () => {
    el.hiddenRarities = new Set(['rare'])
    await el.updateComplete

    const rare = testData.nodes.find(n => n.id === 'conflagration')!
    expect(capturedNodeVisibility!(rare)).toBe(false)

    const common = testData.nodes.find(n => n.id === 'blaze')!
    expect(capturedNodeVisibility!(common)).toBe(true)
  })

  it('defaults missing rarity to unusual', async () => {
    el.hiddenRarities = new Set(['unusual'])
    await el.updateComplete

    const noRarity = testData.nodes.find(n => n.id === 'flame')!
    expect(capturedNodeVisibility!(noRarity)).toBe(false)
  })

  it('colours central node gold', () => {
    expect(capturedNodeColor).not.toBeNull()
    const central = testData.nodes.find(n => n.relationType === 'central')!
    expect(capturedNodeColor!(central)).toBe('#d4af37')
  })

  it('colours nodes by rarity, not relation type', () => {
    const common = testData.nodes.find(n => n.id === 'blaze')!
    expect(capturedNodeColor!(common)).toBe(RARITY_COLOURS.common)

    const rare = testData.nodes.find(n => n.id === 'conflagration')!
    expect(capturedNodeColor!(rare)).toBe(RARITY_COLOURS.rare)
  })

  it('defaults missing rarity to unusual colour', () => {
    const noRarity = testData.nodes.find(n => n.id === 'flame')!
    expect(capturedNodeColor!(noRarity)).toBe(RARITY_COLOURS.unusual)
  })

  it('sets touch-action none on graph container', () => {
    const container = el.shadowRoot!.querySelector('#graph-container') as HTMLElement
    expect(container.style.touchAction).toBe('none')
  })

  it('hides links when either endpoint is hidden', async () => {
    el.hiddenRarities = new Set(['rare'])
    await el.updateComplete

    expect(capturedLinkVisibility).not.toBeNull()

    // After simulation tick, source/target are full node objects
    const centralNode = testData.nodes.find(n => n.id === 'fire')!
    const rareNode = testData.nodes.find(n => n.id === 'conflagration')!
    const commonNode = testData.nodes.find(n => n.id === 'blaze')!

    // Link to hidden node → hidden
    expect(capturedLinkVisibility!({ source: centralNode, target: rareNode })).toBe(false)
    // Link between visible nodes → visible
    expect(capturedLinkVisibility!({ source: centralNode, target: commonNode })).toBe(true)
  })
})
