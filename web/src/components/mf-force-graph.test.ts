import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import type { GraphData } from '@/graph/types'
import { RARITY_COLOURS } from '@/graph/colours'
import SpriteText from 'three-spritetext'

// Capture the accessor functions and constructor options passed to the graph instance
let capturedNodeVisibility: ((node: unknown) => boolean) | null = null
let capturedLinkVisibility: ((link: unknown) => boolean) | null = null
let capturedNodeColor: ((node: unknown) => string) | null = null
let capturedNodeOpacity: number | null = null
let capturedLinkColor: ((link: unknown) => string) | null = null
let capturedLinkWidth: ((link: unknown) => number) | null = null
let capturedNodeThreeObject: ((node: unknown) => unknown) | null = null
let capturedOnNodeClick: ((node: unknown) => void) | null = null
let capturedOnLinkClick: ((link: unknown) => void) | null = null
let capturedOnNodeHover: ((node: unknown | null, previousNode: unknown | null) => void) | null = null
let capturedControlType: string | undefined = undefined
let capturedExtraRenderers: unknown[] | undefined = undefined

const mockCamera = { position: { x: 0, y: 0, z: 100 } }
const mockControls = { enableDamping: false, dampingFactor: 0 }
// Backs the chainable Proxy's graphData() getter so tests can stub the node set
// the library reports back (visibility mirror reads graph.graphData().nodes).
let mockGraphData: { nodes: unknown[]; links: unknown[] } = { nodes: [], links: [] }

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
      // Real library only accepts a static number — used directly in
      // multiplication (state.nodeOpacity * colorAlpha). A function
      // would produce NaN and make all spheres invisible.
      return (val: number) => {
        capturedNodeOpacity = val
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
    if (prop === 'onLinkClick') {
      return (fn: (link: unknown) => void) => {
        capturedOnLinkClick = fn
        return chainable
      }
    }
    if (prop === 'onNodeHover') {
      // Real library calls: fn(node | null, previousNode | null)
      return (fn: (node: unknown | null, previousNode: unknown | null) => void) => {
        capturedOnNodeHover = fn
        return chainable
      }
    }
    if (prop === 'graphData') {
      // graph.graphData() → current stub; graph.graphData(data) → chainable (setter form)
      return (data?: { nodes: unknown[]; links: unknown[] }) => {
        if (data === undefined) return mockGraphData
        return chainable
      }
    }
    if (prop === 'camera') return () => mockCamera
    if (prop === 'controls') return () => mockControls
    return () => chainable
  },
})

vi.mock('3d-force-graph', () => ({
  default: (opts?: { controlType?: string; extraRenderers?: unknown[] }) => {
    capturedControlType = opts?.controlType
    capturedExtraRenderers = opts?.extraRenderers
    return () => chainable
  },
}))
vi.mock('three/addons/renderers/CSS2DRenderer.js', () => ({
  CSS2DRenderer: vi.fn().mockImplementation(() => ({
    domElement: document.createElement('div'), setSize: vi.fn(), render: vi.fn(),
  })),
  CSS2DObject: vi.fn().mockImplementation((el?: HTMLElement) => ({
    element: el ?? document.createElement('div'), isCSS2DObject: true, visible: true,
    position: { x: 0, y: 0, z: 0, set() {} },
    center: { x: 0.5, y: 0.5, set(this: { x: number; y: number }, x: number, y: number) { this.x = x; this.y = y } },
    onBeforeRender: undefined,
  })),
}))
vi.mock('three-spritetext', () => ({
  default: vi.fn().mockImplementation(() => ({
    fontFace: '',
    backgroundColor: false,
    position: { y: 0 },
    padding: 0,
    borderWidth: 0,
    borderRadius: 0,
    borderColor: 'white',
    isSprite: true,
    material: { transparent: false, depthWrite: true },
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
    capturedOnLinkClick = null
    capturedOnNodeHover = null
    capturedControlType = undefined
    capturedExtraRenderers = undefined
    mockGraphData = { nodes: [], links: [] }
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

  it('constructs the graph with a CSS2D extra renderer', () => {
    expect(Array.isArray(capturedExtraRenderers)).toBe(true)
    expect(capturedExtraRenderers!.length).toBe(1)
  })

  it('no longer runs a sprite clamp loop (startLabelClampLoop removed)', () => {
    expect((el as unknown as Record<string, unknown>).startLabelClampLoop).toBeUndefined()
    expect((el as unknown as Record<string, unknown>).labelClampRAF).toBeUndefined()
  })

  it('syncs label visibility when hiddenRarities changes (browse)', async () => {
    // Give two fed nodes mock label children, then hide 'rare'. The library
    // reports these back via graph.graphData() (stubbed through mockGraphData).
    const mkNode = (id: string, rarity: string) => ({ id, rarity, relationType: 'synonym',
      __threeObj: { children: [{ isCSS2DObject: true, visible: true, element: document.createElement('div') }] } })
    const nodes = [mkNode('blaze', 'common'), mkNode('conflagration', 'rare')]
    mockGraphData = { nodes, links: [] }
    el.hiddenRarities = new Set(['rare'])
    await el.updateComplete
    const rareLabel = nodes[1].__threeObj.children[0]
    expect(rareLabel.visible).toBe(false)
    expect(rareLabel.element.style.display).toBe('none')
  })

  it('exposes __test_pauseAndRenderFrame and __test_labelEls', () => {
    expect(typeof el.__test_pauseAndRenderFrame).toBe('function')
    expect(Array.isArray(el.__test_labelEls())).toBe(true)
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

  it('clears armed click timer when order-2 node is clicked', () => {
    vi.useFakeTimers()
    const order1Node = { id: 'blaze', word: 'blaze', relationType: 'synonym', val: 4, order: 1 }
    const order2Node = { id: 'spark', word: 'spark', relationType: 'synonym', val: 2, order: 2 }
    const selectSpy = vi.fn()
    el.addEventListener('mf-node-select', selectSpy)

    // First click arms the timer for order-1
    capturedOnNodeClick!(order1Node)
    // Immediately click an order-2 node (within threshold)
    capturedOnNodeClick!(order2Node)
    // Advance past the threshold — timer should have been cleared
    vi.advanceTimersByTime(400)

    expect(selectSpy).not.toHaveBeenCalled()

    el.removeEventListener('mf-node-select', selectSpy)
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
    expect(mockControls.dampingFactor).toBeCloseTo(0.05)
  })

  it('toggles .label-hovered on the node label div on hover in/out (browse)', () => {
    const labelEl = document.createElement('div')
    const node = { id: 'blaze', word: 'blaze', relationType: 'synonym', rarity: 'common', order: 1,
      __threeObj: { children: [{ isCSS2DObject: true, element: labelEl }] } }
    capturedOnNodeHover!(node, null)
    expect(labelEl.classList.contains('label-hovered')).toBe(true)
    capturedOnNodeHover!(null, node)
    expect(labelEl.classList.contains('label-hovered')).toBe(false)
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

  describe('grade mode', () => {
    // ChainRecord fixtures — two chains sharing the 'heat' intermediate node
    const CHAINS: import('../types/grading').ChainRecord[] = [
      {
        schema_version: 'chain.v1',
        topic: 'anger', topic_synset_id: '1',
        vehicle: 'venom', vehicle_synset_id: '3',
        proposer: 'sonnet_v1', round: 1,
        chain_signature: 'a'.repeat(64),
        generated_at: 'x',
        chain: [
          { phrase: 'anger', head: 'anger', synset_id: '1' },
          { phrase: 'heat', head: 'heat', synset_id: '2' },
          { phrase: 'venom', head: 'venom', synset_id: '3' },
        ],
      },
      {
        schema_version: 'chain.v1',
        topic: 'anger', topic_synset_id: '1',
        vehicle: 'fire', vehicle_synset_id: '5',
        proposer: 'sonnet_v1', round: 1,
        chain_signature: 'b'.repeat(64),
        generated_at: 'x',
        chain: [
          { phrase: 'anger', head: 'anger', synset_id: '1' },
          { phrase: 'heat', head: 'heat', synset_id: '2' }, // shared with above
          { phrase: 'fire', head: 'fire', synset_id: '5' },
        ],
      },
    ]

    let gradeEl: MfForceGraph

    beforeEach(async () => {
      gradeEl = document.createElement('mf-force-graph') as MfForceGraph
      document.body.appendChild(gradeEl)
      await gradeEl.updateComplete
    })

    afterEach(() => {
      document.body.removeChild(gradeEl)
    })

    it('builds dedup nodes by synset_id in grade mode', async () => {
      gradeEl.mode = 'grade'
      gradeEl.gradeChains = CHAINS
      await gradeEl.updateComplete
      // Both chains pass through heat (synset_id=2) — node count should be 4:
      // anger (topic), heat (shared intermediate), venom, fire
      expect(gradeEl.gradeNodes.length).toBe(4)
      const heatNodes = gradeEl.gradeNodes.filter((n: any) => n.id === 'syn:2')
      expect(heatNodes.length).toBe(1)
    })

    it('dedupes by head when synset_id is null', async () => {
      const nullSyn: import('../types/grading').ChainRecord[] = [{
        ...CHAINS[0],
        chain: [
          { phrase: 'anger', head: 'anger', synset_id: '1' },
          { phrase: 'unsnappable phrase', head: 'unsnappable', synset_id: null },
          { phrase: 'venom', head: 'venom', synset_id: '3' },
        ],
      }]
      gradeEl.mode = 'grade'
      gradeEl.gradeChains = nullSyn
      await gradeEl.updateComplete
      // Should produce a node keyed by head:unsnappable
      const headKeyed = gradeEl.gradeNodes.filter((n: any) => n.id === 'head:unsnappable')
      expect(headKeyed.length).toBe(1)
    })

    it('emits chain-selected on vehicle node click', async () => {
      gradeEl.mode = 'grade'
      gradeEl.gradeChains = CHAINS
      await gradeEl.updateComplete
      let captured: any = null
      gradeEl.addEventListener('chain-selected', (e: any) => { captured = e.detail })
      gradeEl.handleNodeClick({ id: 'syn:3', isVehicle: true })
      // venom vehicle should match chain[0] (anger->heat->venom)
      expect(captured?.chain_signature).toBe('a'.repeat(64))
    })

    it('does not load 3D below 900px viewport', async () => {
      gradeEl.mode = 'grade'
      gradeEl.viewportWidth = 800
      gradeEl.gradeChains = CHAINS
      await gradeEl.updateComplete
      expect(gradeEl.threeDLoaded).toBe(false)
    })

    it('builds edge colour map from judgements', async () => {
      gradeEl.mode = 'grade'
      gradeEl.gradeChains = CHAINS
      gradeEl.judgements = [{
        schema_version: 'judgement.v1', judged_by: 'julian', round: 1,
        topic: 'anger', topic_synset_id: '1',
        vehicle: 'venom', vehicle_synset_id: '3',
        proposer: 'sonnet_v1',
        chain_signature: 'a'.repeat(64),
        label: 'live', confidence: 'high', notes: '', supersedes_ts: null,
        ts: '2026-05-30T00:00:00Z',
      }]
      await gradeEl.updateComplete
      const verdict = gradeEl.getEdgeColour('a'.repeat(64))
      expect(verdict).toBe('live')
    })

    it('returns null from getEdgeColour for unjudged chain', async () => {
      gradeEl.mode = 'grade'
      gradeEl.gradeChains = CHAINS
      gradeEl.judgements = []
      await gradeEl.updateComplete
      expect(gradeEl.getEdgeColour('a'.repeat(64))).toBeNull()
    })

    it('gradeNodes returns empty array in browse mode', async () => {
      gradeEl.mode = 'browse'
      gradeEl.gradeChains = CHAINS
      await gradeEl.updateComplete
      expect(gradeEl.gradeNodes).toEqual([])
    })

    it('activeGraphData feeds the grade graph in grade mode (regression: grade data was never rendered)', async () => {
      gradeEl.mode = 'grade'
      gradeEl.gradeChains = CHAINS
      await gradeEl.updateComplete
      const data = gradeEl.activeGraphData()
      // grade graph: anger(topic) + heat(shared) + venom + fire = 4 nodes
      expect(data.nodes.length).toBe(4)
      expect(data.links.length).toBe(gradeEl.gradeLinks.length)
      expect(data.links.length).toBeGreaterThan(0)
      // and it must NOT be the (empty) browse graphData
      expect(data.nodes).not.toBe(gradeEl.graphData.nodes)
    })

    it('activeGraphData feeds the browse graph in browse mode', async () => {
      gradeEl.mode = 'browse'
      const browse = { nodes: [{ id: 'x' }], links: [] }
      gradeEl.graphData = browse as any
      await gradeEl.updateComplete
      expect(gradeEl.activeGraphData()).toBe(browse)
    })

    it('does not emit chain-selected in browse mode', async () => {
      gradeEl.mode = 'browse'
      gradeEl.gradeChains = CHAINS
      await gradeEl.updateComplete
      let fired = false
      gradeEl.addEventListener('chain-selected', () => { fired = true })
      gradeEl.handleNodeClick({ id: 'syn:3', isVehicle: true })
      expect(fired).toBe(false)
    })

    it('does not emit chain-selected on non-vehicle node click', async () => {
      gradeEl.mode = 'grade'
      gradeEl.gradeChains = CHAINS
      await gradeEl.updateComplete
      let fired = false
      gradeEl.addEventListener('chain-selected', () => { fired = true })
      // heat is an intermediate step, not a vehicle
      gradeEl.handleNodeClick({ id: 'syn:2', isVehicle: false })
      expect(fired).toBe(false)
    })

    it('onNodeClick in grade mode emits chain-selected when vehicle is clicked', async () => {
      gradeEl.mode = 'grade'
      gradeEl.gradeChains = CHAINS
      await gradeEl.updateComplete
      let captured: any = null
      gradeEl.addEventListener('chain-selected', (e: any) => { captured = e.detail })
      // capturedOnNodeClick is set by gradeEl's firstUpdated (created after outer el)
      // Simulate the 3D library calling back with the vehicle node id for chain[0]: venom (syn:3)
      capturedOnNodeClick!({ id: 'syn:3', word: 'venom' })
      expect(captured?.chain_signature).toBe('a'.repeat(64))
    })

    it('onNodeClick in grade mode does NOT emit chain-selected for non-vehicle node', async () => {
      gradeEl.mode = 'grade'
      gradeEl.gradeChains = CHAINS
      await gradeEl.updateComplete
      let fired = false
      gradeEl.addEventListener('chain-selected', () => { fired = true })
      // heat (syn:2) is an intermediate step, not a vehicle
      capturedOnNodeClick!({ id: 'syn:2', word: 'heat' })
      expect(fired).toBe(false)
    })

    it('onLinkClick in grade mode emits chain-selected for the link\'s chain', async () => {
      gradeEl.mode = 'grade'
      gradeEl.gradeChains = CHAINS
      await gradeEl.updateComplete
      let captured: any = null
      gradeEl.addEventListener('chain-selected', (e: any) => { captured = e.detail })
      // Clicking any segment of a path selects that chain (same as the vehicle).
      capturedOnLinkClick!({ chainSig: 'a'.repeat(64) })
      expect(captured?.chain_signature).toBe('a'.repeat(64))
    })

    it('onLinkClick in browse mode does not emit chain-selected', async () => {
      gradeEl.mode = 'browse'
      gradeEl.gradeChains = CHAINS
      await gradeEl.updateComplete
      let fired = false
      gradeEl.addEventListener('chain-selected', () => { fired = true })
      capturedOnLinkClick!({ chainSig: 'a'.repeat(64) })
      expect(fired).toBe(false)
    })

    it('onNodeClick in browse mode still dispatches mf-node-select (not chain-selected)', async () => {
      gradeEl.mode = 'browse'
      gradeEl.gradeChains = CHAINS
      await gradeEl.updateComplete
      vi.useFakeTimers()
      let chainSelectedFired = false
      let nodeSelectFired = false
      gradeEl.addEventListener('chain-selected', () => { chainSelectedFired = true })
      gradeEl.addEventListener('mf-node-select', () => { nodeSelectFired = true })
      const order1Node = { id: 'venom', word: 'venom', relationType: 'synonym', val: 4, order: 1 }
      capturedOnNodeClick!(order1Node)
      vi.advanceTimersByTime(400)
      expect(chainSelectedFired).toBe(false)
      expect(nodeSelectFired).toBe(true)
      vi.useRealTimers()
    })

    it('latest judgement wins when two exist for same signature', async () => {
      gradeEl.mode = 'grade'
      gradeEl.gradeChains = CHAINS
      gradeEl.judgements = [
        {
          schema_version: 'judgement.v1', judged_by: 'julian', round: 1,
          topic: 'anger', topic_synset_id: '1',
          vehicle: 'venom', vehicle_synset_id: '3',
          proposer: 'sonnet_v1',
          chain_signature: 'a'.repeat(64),
          label: 'dead', confidence: 'low', notes: '', supersedes_ts: null,
          ts: '2026-05-29T00:00:00Z',
        },
        {
          schema_version: 'judgement.v1', judged_by: 'julian', round: 2,
          topic: 'anger', topic_synset_id: '1',
          vehicle: 'venom', vehicle_synset_id: '3',
          proposer: 'sonnet_v1',
          chain_signature: 'a'.repeat(64),
          label: 'live', confidence: 'high', notes: '', supersedes_ts: null,
          ts: '2026-05-30T00:00:00Z',
        },
      ]
      await gradeEl.updateComplete
      expect(gradeEl.getEdgeColour('a'.repeat(64))).toBe('live')
    })
  })

  describe('order-2 visual differentiation', () => {
    it('sets nodeOpacity as a static number', () => {
      // nodeOpacity must be a number — 3d-force-graph v1.79 uses it
      // directly in multiplication (state.nodeOpacity * colorAlpha),
      // so a function causes NaN and makes all spheres invisible.
      expect(capturedNodeOpacity).toBe(0.9)
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

    it('nodeThreeObject builds a DOM label with the node word and rarity colour (browse)', () => {
      const ember = { id: 'ember', word: 'ember', relationType: 'synonym', rarity: 'common', order: 2 }
      const obj = capturedNodeThreeObject!(ember) as { element: HTMLElement }
      const span = obj.element.querySelector('span.mf-graph-label__text') as HTMLSpanElement
      expect(span.textContent).toBe('ember')
      // happy-dom 17 preserves the hex literal (it does not normalise to rgb()).
      expect(span.style.color).toBe(RARITY_COLOURS.common) // #8bb89a
    })

    it('effective label config defaults to browse distance-floor / grade constant', async () => {
      expect(el.effectiveLabelSize).toEqual({ mode: 'distance-floor', basePx: 13, minPx: 10 })
      const g = new MfForceGraph(); g.mode = 'grade'
      document.body.appendChild(g); await g.updateComplete
      expect(g.effectiveLabelSize).toEqual({ mode: 'constant', basePx: 13, minPx: 11 })
      document.body.removeChild(g)
    })

    it('uses standard label sprite for order-1 nodes', () => {
      expect(capturedNodeThreeObject).toBeTypeOf('function')
      vi.mocked(SpriteText).mockClear()
      const blaze = testData.nodes.find(n => n.id === 'blaze')!
      capturedNodeThreeObject!(blaze)
      const calls = vi.mocked(SpriteText).mock.calls
      expect(calls[0][1]).toBe(3)
    })

    it('positions sprite at y=2 for unified hit area', () => {
      vi.mocked(SpriteText).mockClear()
      const blaze = testData.nodes.find(n => n.id === 'blaze')!
      const sprite = capturedNodeThreeObject!(blaze) as { position: { y: number } }
      expect(sprite.position.y).toBe(2)
    })

    it('sets sprite padding to cover sphere hit area', () => {
      vi.mocked(SpriteText).mockClear()
      const blaze = testData.nodes.find(n => n.id === 'blaze')!
      const sprite = capturedNodeThreeObject!(blaze) as { padding: number[] }
      expect(sprite.padding).toEqual([0.5, 2])
    })

    it('enables transparent material on sprite for correct alpha blending', () => {
      vi.mocked(SpriteText).mockClear()
      const blaze = testData.nodes.find(n => n.id === 'blaze')!
      const sprite = capturedNodeThreeObject!(blaze) as { material: { transparent: boolean } }
      expect(sprite.material.transparent).toBe(true)
    })

    it('disables depthWrite on sprite to prevent transparent regions occluding scene', () => {
      vi.mocked(SpriteText).mockClear()
      const blaze = testData.nodes.find(n => n.id === 'blaze')!
      const sprite = capturedNodeThreeObject!(blaze) as { material: { depthWrite: boolean } }
      expect(sprite.material.depthWrite).toBe(false)
    })
  })
})
