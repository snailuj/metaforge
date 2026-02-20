import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import type { GraphData } from '@/graph/types'
import { RARITY_COLOURS } from '@/graph/colours'
import SpriteText from 'three-spritetext'

// Capture the accessor functions and constructor options passed to the graph instance
let capturedNodeVisibility: ((node: unknown) => boolean) | null = null
let capturedLinkVisibility: ((link: unknown) => boolean) | null = null
let capturedNodeColor: ((node: unknown) => string) | null = null
let capturedNodeOpacity: ((node: unknown) => number) | null = null
let capturedLinkColor: ((link: unknown) => string) | null = null
let capturedLinkWidth: ((link: unknown) => number) | null = null
let capturedNodeThreeObject: ((node: unknown) => unknown) | null = null
let capturedOnNodeClick: ((node: unknown) => void) | null = null
let capturedOnNodeHover: ((node: unknown | null) => void) | null = null
let capturedControlType: string | undefined = undefined

const mockCamera = { position: { x: 0, y: 0, z: 100 } }
const mockControls = { enableDamping: false, dampingFactor: 0 }

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
    if (prop === 'nodeOpacity') {
      return (fn: ((node: unknown) => number) | number) => {
        if (typeof fn === 'function') capturedNodeOpacity = fn
        return chainable
      }
    }
    if (prop === 'linkColor') {
      return (fn: ((link: unknown) => string) | string) => {
        if (typeof fn === 'function') capturedLinkColor = fn
        return chainable
      }
    }
    if (prop === 'linkWidth') {
      return (fn: ((link: unknown) => number) | number) => {
        if (typeof fn === 'function') capturedLinkWidth = fn
        return chainable
      }
    }
    if (prop === 'nodeThreeObject') {
      return (fn: (node: unknown) => unknown) => {
        capturedNodeThreeObject = fn
        return chainable
      }
    }
    if (prop === 'onNodeClick') {
      return (fn: (node: unknown) => void) => {
        capturedOnNodeClick = fn
        return chainable
      }
    }
    if (prop === 'onNodeHover') {
      return (fn: (node: unknown | null) => void) => {
        capturedOnNodeHover = fn
        return chainable
      }
    }
    if (prop === 'camera') return () => mockCamera
    if (prop === 'controls') return () => mockControls
    return () => chainable
  },
})

vi.mock('3d-force-graph', () => ({
  default: (opts?: { controlType?: string }) => {
    capturedControlType = opts?.controlType
    return () => chainable
  },
}))
vi.mock('three-spritetext', () => ({
  default: vi.fn().mockImplementation(() => ({
    fontFace: '',
    backgroundColor: '',
    position: { y: 0 },
  })),
}))

import { MfForceGraph } from './mf-force-graph'

const testData: GraphData = {
  nodes: [
    { id: 'fire', word: 'fire', relationType: 'central', val: 8, order: 0 },
    { id: 'blaze', word: 'blaze', relationType: 'synonym', val: 4, rarity: 'common', order: 1 },
    { id: 'conflagration', word: 'conflagration', relationType: 'synonym', val: 4, rarity: 'rare', order: 1 },
    { id: 'flame', word: 'flame', relationType: 'synonym', val: 4, order: 1 }, // no rarity → defaults to 'unusual'
    { id: 'ember', word: 'ember', relationType: 'synonym', val: 1, rarity: 'common', order: 2 },
  ],
  links: [
    { source: 'fire', target: 'blaze', relationType: 'synonym', order: 1 },
    { source: 'fire', target: 'conflagration', relationType: 'synonym', order: 1 },
    { source: 'fire', target: 'flame', relationType: 'synonym', order: 1 },
    { source: 'fire', target: 'ember', relationType: 'synonym', order: 2 },
  ],
}

describe('MfForceGraph', () => {
  let el: MfForceGraph

  beforeEach(async () => {
    capturedNodeVisibility = null
    capturedLinkVisibility = null
    capturedNodeColor = null
    capturedNodeOpacity = null
    capturedLinkColor = null
    capturedLinkWidth = null
    capturedNodeThreeObject = null
    capturedOnNodeClick = null
    capturedOnNodeHover = null
    capturedControlType = undefined
    mockCamera.position.z = 100
    mockControls.enableDamping = false
    mockControls.dampingFactor = 0
    vi.mocked(SpriteText).mockClear()
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

  it('uses orbit controls', () => {
    expect(capturedControlType).toBe('orbit')
  })

  it('does not dispatch mf-node-select for order-2 nodes', () => {
    vi.useFakeTimers()
    const order2Node = { id: 'spark', word: 'spark', relationType: 'synonym', val: 2, order: 2 }
    const spy = vi.fn()
    el.addEventListener('mf-node-select', spy)

    capturedOnNodeClick!(order2Node)
    vi.advanceTimersByTime(400)

    expect(spy).not.toHaveBeenCalled()

    el.removeEventListener('mf-node-select', spy)
    vi.useRealTimers()
  })

  it('dispatches mf-node-select for order-1 nodes', () => {
    vi.useFakeTimers()
    const order1Node = { id: 'blaze', word: 'blaze', relationType: 'synonym', val: 4, order: 1 }
    const spy = vi.fn()
    el.addEventListener('mf-node-select', spy)

    capturedOnNodeClick!(order1Node)
    vi.advanceTimersByTime(400)

    expect(spy).toHaveBeenCalledOnce()

    el.removeEventListener('mf-node-select', spy)
    vi.useRealTimers()
  })

  it('scales default camera zoom 35% closer on init', async () => {
    await new Promise<void>(r => requestAnimationFrame(r))
    expect(mockCamera.position.z).toBeCloseTo(65, 0)
  })

  it('enables damping on orbit controls after init', async () => {
    await new Promise<void>(r => requestAnimationFrame(r))
    expect(mockControls.enableDamping).toBe(true)
    expect(mockControls.dampingFactor).toBeCloseTo(0.25)
  })

  it('highlights mesh on hover: wireframe, bright colour, scaled up', () => {
    const color = { _origHex: 0, getHex: vi.fn().mockReturnValue(0xaabbcc), setHex: vi.fn() }
    const meshMaterial = { wireframe: false, opacity: 0.9, color }
    const scale = { set: vi.fn() }
    const node = {
      id: 'blaze', word: 'blaze', relationType: 'synonym', val: 4, order: 1,
      __threeObj: { children: [{ isMesh: true, material: meshMaterial, scale }, { isMesh: false }] },
    }
    capturedOnNodeHover!(node)
    expect(meshMaterial.wireframe).toBe(true)
    expect(meshMaterial.opacity).toBe(1.0)
    expect(scale.set).toHaveBeenCalledWith(5, 5, 5)
    expect(color.setHex).toHaveBeenCalledWith(0x00ff88)
  })

  it('restores mesh on hover-out: original colour, opacity, normal scale', () => {
    const color = { _origHex: 0, getHex: vi.fn().mockReturnValue(0xaabbcc), setHex: vi.fn() }
    const meshMaterial = { wireframe: false, opacity: 0.9, color }
    const scale = { set: vi.fn() }
    const node = {
      id: 'blaze', word: 'blaze', relationType: 'synonym', val: 4, order: 1,
      __threeObj: { children: [{ isMesh: true, material: meshMaterial, scale }, { isMesh: false }] },
    }
    capturedOnNodeHover!(node) // hover in
    capturedOnNodeHover!(null) // hover out
    expect(meshMaterial.wireframe).toBe(false)
    expect(meshMaterial.opacity).toBe(0.9)
    expect(scale.set).toHaveBeenLastCalledWith(1, 1, 1)
    expect(color.setHex).toHaveBeenLastCalledWith(0xaabbcc)
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

  describe('order-2 visual differentiation', () => {
    it('sets nodeOpacity accessor as a function', () => {
      expect(capturedNodeOpacity).toBeTypeOf('function')
    })

    it('returns 0.9 opacity for order-1 nodes', () => {
      const node = testData.nodes.find(n => n.id === 'blaze')!
      expect(capturedNodeOpacity!(node)).toBe(0.9)
    })

    it('returns 0.45 opacity for order-2 nodes', () => {
      const node = testData.nodes.find(n => n.id === 'ember')!
      expect(capturedNodeOpacity!(node)).toBe(0.45)
    })

    it('sets linkColor accessor as a function', () => {
      expect(capturedLinkColor).toBeTypeOf('function')
    })

    it('returns standard alpha for order-1 links', () => {
      const link = testData.links.find(l => l.target === 'blaze')!
      expect(capturedLinkColor!(link)).toBe('rgba(232, 224, 212, 0.15)')
    })

    it('returns dimmer alpha for order-2 links', () => {
      const link = testData.links.find(l => l.target === 'ember')!
      expect(capturedLinkColor!(link)).toBe('rgba(232, 224, 212, 0.08)')
    })

    it('sets linkWidth accessor as a function', () => {
      expect(capturedLinkWidth).toBeTypeOf('function')
    })

    it('returns 1 width for order-1 links', () => {
      const link = testData.links.find(l => l.target === 'blaze')!
      expect(capturedLinkWidth!(link)).toBe(1)
    })

    it('returns 0.5 width for order-2 links', () => {
      const link = testData.links.find(l => l.target === 'ember')!
      expect(capturedLinkWidth!(link)).toBe(0.5)
    })

    it('hides order-2 nodes when their rarity is hidden', async () => {
      el.hiddenRarities = new Set(['common'])
      await el.updateComplete

      const ember = testData.nodes.find(n => n.id === 'ember')!
      expect(capturedNodeVisibility!(ember)).toBe(false)
    })

    it('uses smaller label sprite for order-2 nodes', () => {
      expect(capturedNodeThreeObject).toBeTypeOf('function')
      vi.mocked(SpriteText).mockClear()
      const ember = testData.nodes.find(n => n.id === 'ember')!
      capturedNodeThreeObject!(ember)
      const calls = vi.mocked(SpriteText).mock.calls
      expect(calls[0][1]).toBe(2)
    })

    it('uses standard label sprite for order-1 nodes', () => {
      expect(capturedNodeThreeObject).toBeTypeOf('function')
      vi.mocked(SpriteText).mockClear()
      const blaze = testData.nodes.find(n => n.id === 'blaze')!
      capturedNodeThreeObject!(blaze)
      const calls = vi.mocked(SpriteText).mock.calls
      expect(calls[0][1]).toBe(3)
    })
  })
})
