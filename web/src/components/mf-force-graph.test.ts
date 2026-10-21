import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import type { GraphData } from '@/graph/types'
import { RARITY_COLOURS, NODE_COLOURS, FOREST_COLOURS } from '@/graph/colours'
import type { ForestResponse } from '@/types/api'
import { composeForest, forestToGraph } from '@/graph/forest'
import patienceForest from '@/fixtures/forest-patience.json'

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
// Counts graphData(data) SETTER calls (feed events). The "no re-heat" regression
// guard asserts this does not increment when only pathFilter changes.
let graphDataSetCount = 0
// Counts visibility-accessor (re-)applications. The "no re-heat" guard asserts
// these DO increment on pathFilter change while graphData stays flat.
let nodeVisibilitySetCount = 0
let linkVisibilitySetCount = 0

const chainable: Record<string, unknown> = new Proxy({}, {
  get: (_t, prop) => {
    if (prop === 'nodeVisibility') {
      return (fn: (node: unknown) => boolean) => {
        capturedNodeVisibility = fn
        nodeVisibilitySetCount++
        return chainable
      }
    }
    if (prop === 'linkVisibility') {
      return (fn: (link: unknown) => boolean) => {
        capturedLinkVisibility = fn
        linkVisibilitySetCount++
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
        graphDataSetCount++
        return chainable
      }
    }
    if (prop === 'camera') return () => mockCamera
    if (prop === 'controls') return () => mockControls
    // Every other setter: remember its latest arguments and count the calls, so
    // tests can read accessors such as linkDirectionalParticles.
    return (...args: unknown[]) => {
      if (args.length) {
        lastArgs[prop as string] = args
        setCounts[prop as string] = (setCounts[prop as string] ?? 0) + 1
      }
      return chainable
    }
  },
})
let lastArgs: Record<string, unknown[]> = {}
let setCounts: Record<string, number> = {}

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
    lastArgs = {}
    setCounts = {}
    graphDataSetCount = 0
    nodeVisibilitySetCount = 0
    linkVisibilitySetCount = 0
    mockCamera.position.z = 100
    mockControls.enableDamping = false
    mockControls.dampingFactor = 0
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
      // Reset after construction so per-test feed counts start from zero.
      graphDataSetCount = 0
      nodeVisibilitySetCount = 0
      linkVisibilitySetCount = 0
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

    it('grade node label text is the head, not the phrase', async () => {
      const phrasey: import('../types/grading').ChainRecord[] = [{
        ...CHAINS[0],
        chain: [
          { phrase: 'simmering anger', head: 'anger', synset_id: '1' },
          { phrase: 'subterranean heat', head: 'heat', synset_id: '2' },
          { phrase: 'coiled venom', head: 'venom', synset_id: '3' },
        ],
      }]
      gradeEl.mode = 'grade'
      gradeEl.gradeChains = phrasey
      await gradeEl.updateComplete
      const heat = gradeEl.gradeNodes.find((n: any) => n.id === 'syn:2')!
      expect(heat.head).toBe('heat')
      const style = (gradeEl as any).labelStyleFor(heat)
      expect(style.text).toBe('heat')
    })

    it('accumulates deduped backlinks on a shared target node across chains', async () => {
      // 'heat' (syn:2) is reached from two distinct sources via two distinct
      // phrases, so it carries two backlinks. A third inbound edge repeating the
      // first (same source head + phrase) collapses.
      const shared: import('../types/grading').ChainRecord[] = [
        {
          ...CHAINS[0], chain_signature: 'a'.repeat(64),
          chain: [
            { phrase: 'pressure', head: 'pressure', synset_id: '9' },
            { phrase: 'subterranean heat', head: 'heat', synset_id: '2' },
            { phrase: 'venom', head: 'venom', synset_id: '3' },
          ],
        },
        {
          ...CHAINS[1], chain_signature: 'b'.repeat(64),
          chain: [
            { phrase: 'ember', head: 'ember', synset_id: '8' },
            { phrase: 'the warmth below', head: 'heat', synset_id: '2' },
            { phrase: 'fire', head: 'fire', synset_id: '5' },
          ],
        },
        {
          ...CHAINS[0], chain_signature: 'c'.repeat(64),
          chain: [
            { phrase: 'pressure', head: 'pressure', synset_id: '9' },
            { phrase: 'subterranean heat', head: 'heat', synset_id: '2' }, // dup of chain a's inbound edge
            { phrase: 'smoke', head: 'smoke', synset_id: '7' },
          ],
        },
      ]
      gradeEl.mode = 'grade'
      gradeEl.gradeChains = shared
      await gradeEl.updateComplete
      const heat = gradeEl.gradeNodes.find((n: any) => n.id === 'syn:2')!
      expect(heat.backlinks).toEqual([
        { source: 'pressure', phrase: 'subterranean heat' },
        { source: 'ember', phrase: 'the warmth below' },
      ])
    })

    it('keeps space-colliding inbound connections as distinct backlinks', async () => {
      // (prev.head + step.phrase) space-joined collides for these two edges into
      // 'cold fire below', silently dropping the second. A structured dedup key
      // keeps the two genuinely-distinct connections apart.
      const colliding: import('../types/grading').ChainRecord[] = [
        {
          ...CHAINS[0], chain_signature: 'd'.repeat(64),
          chain: [
            { phrase: 'cold fire', head: 'cold fire', synset_id: '11' },
            { phrase: 'below', head: 'target', synset_id: '12' },
            { phrase: 'venom', head: 'venom', synset_id: '3' },
          ],
        },
        {
          ...CHAINS[1], chain_signature: 'e'.repeat(64),
          chain: [
            { phrase: 'cold', head: 'cold', synset_id: '13' },
            { phrase: 'fire below', head: 'target', synset_id: '12' },
            { phrase: 'fire', head: 'fire', synset_id: '5' },
          ],
        },
      ]
      gradeEl.mode = 'grade'
      gradeEl.gradeChains = colliding
      await gradeEl.updateComplete
      const target = gradeEl.gradeNodes.find((n: any) => n.id === 'syn:12')!
      expect(target.backlinks).toEqual([
        { source: 'cold fire', phrase: 'below' },
        { source: 'cold', phrase: 'fire below' },
      ])
    })

    it('topic node has no backlinks; labelStyleFor passes backlinks through', async () => {
      gradeEl.mode = 'grade'
      gradeEl.gradeChains = CHAINS
      await gradeEl.updateComplete
      const anger = gradeEl.gradeNodes.find((n: any) => n.id === 'syn:1')!
      expect(anger.role).toBe('topic')
      expect(anger.backlinks).toEqual([])
      const heat = gradeEl.gradeNodes.find((n: any) => n.id === 'syn:2')!
      const style = (gradeEl as any).labelStyleFor(heat)
      expect(style.backlinks).toEqual(heat.backlinks)
      expect((gradeEl as any).labelStyleFor(anger).backlinks).toEqual([])
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
        schema_version: 'judgement.v2', judged_by: 'julian', round: 1,
        topic: 'anger', topic_synset_id: '1',
        vehicle: 'venom', vehicle_synset_id: '3',
        proposer: 'sonnet_v1',
        chain_signature: 'a'.repeat(64),
        linkage: 'good', metaphor: 'live', tiers: [],
        confidence: 'high', notes: '', supersedes_ts: null,
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

    it('edge colour key: linkage bad → bad_path; good+dead → dead; good+live → live; none → ungraded', async () => {
      gradeEl.mode = 'grade'
      gradeEl.gradeChains = CHAINS
      const sig = 'a'.repeat(64)
      const base = {
        schema_version: 'judgement.v2' as const, judged_by: 'julian', round: 1,
        topic: 'anger', topic_synset_id: '1',
        vehicle: 'venom', vehicle_synset_id: '3',
        proposer: 'sonnet_v1', chain_signature: sig,
        tiers: [], confidence: 'high' as const, notes: '', supersedes_ts: null,
        ts: '2026-05-30T00:00:00Z',
      }
      // linkage:bad dominates — a broken route reads as bad_path regardless of metaphor.
      gradeEl.judgements = [{ ...base, linkage: 'bad', metaphor: 'live' }]
      await gradeEl.updateComplete
      expect(gradeEl.getEdgeColour(sig)).toBe('bad_path')
      // good linkage → colour by metaphor.
      gradeEl.judgements = [{ ...base, linkage: 'good', metaphor: 'dead' }]
      await gradeEl.updateComplete
      expect(gradeEl.getEdgeColour(sig)).toBe('dead')
      gradeEl.judgements = [{ ...base, linkage: 'good', metaphor: 'live' }]
      await gradeEl.updateComplete
      expect(gradeEl.getEdgeColour(sig)).toBe('live')
      gradeEl.judgements = [{ ...base, linkage: 'good', metaphor: 'irrelevant' }]
      await gradeEl.updateComplete
      expect(gradeEl.getEdgeColour(sig)).toBe('irrelevant')
      // No verdict for this signature → null so the renderer applies the ungraded colour.
      expect(gradeEl.getEdgeColour('missing')).toBeNull()
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

    // --- C2 v2: tri-state path filter via visibility (no force-sim re-heat) ---

    // First chain (anger->heat->venom, sig 'aaa...') is graded; second
    // (anger->heat->fire, sig 'bbb...') is ungraded.
    const GRADED_JUDGEMENT = {
      schema_version: 'judgement.v2' as const, judged_by: 'julian', round: 1,
      topic: 'anger', topic_synset_id: '1',
      vehicle: 'venom', vehicle_synset_id: '3',
      proposer: 'sonnet_v1',
      chain_signature: 'a'.repeat(64),
      linkage: 'good' as const, metaphor: 'live' as const, tiers: [],
      confidence: 'high' as const, notes: '', supersedes_ts: null,
      ts: '2026-05-30T00:00:00Z',
    }

    it('buildGradeGraph always builds the FULL graph regardless of pathFilter (stable positions)', async () => {
      gradeEl.mode = 'grade'
      gradeEl.gradeChains = CHAINS
      gradeEl.judgements = [GRADED_JUDGEMENT]
      await gradeEl.updateComplete

      // Default 'both'
      expect(gradeEl.gradeNodes.length).toBe(4)
      expect(gradeEl.gradeLinks.length).toBe(4)

      // Filtering must NOT drop nodes/links from the fed set — only visibility changes.
      gradeEl.pathFilter = 'ungraded'
      await gradeEl.updateComplete
      expect(gradeEl.gradeNodes.length).toBe(4)
      expect(gradeEl.gradeLinks.length).toBe(4)

      gradeEl.pathFilter = 'graded'
      await gradeEl.updateComplete
      expect(gradeEl.gradeNodes.length).toBe(4)
      expect(gradeEl.gradeLinks.length).toBe(4)
    })

    it('changing pathFilter re-applies visibility WITHOUT a graphData re-feed (no bounce)', async () => {
      gradeEl.mode = 'grade'
      gradeEl.gradeChains = CHAINS
      gradeEl.judgements = [GRADED_JUDGEMENT]
      await gradeEl.updateComplete

      // Baseline: the initial grade feed has happened.
      const feedsAfterInitial = graphDataSetCount
      expect(feedsAfterInitial).toBeGreaterThan(0)
      const nodeVisBefore = nodeVisibilitySetCount
      const linkVisBefore = linkVisibilitySetCount

      const gradedLink = { source: 'syn:2', target: 'syn:3', chainSig: 'a'.repeat(64) }
      // Under 'both' the graded link is visible.
      expect(capturedLinkVisibility!(gradedLink)).toBe(true)

      gradeEl.pathFilter = 'ungraded'
      await gradeEl.updateComplete

      // Core regression guard: no new feed (positions stay put)...
      expect(graphDataSetCount).toBe(feedsAfterInitial)
      // ...but the visibility accessors WERE re-applied.
      expect(nodeVisibilitySetCount).toBeGreaterThan(nodeVisBefore)
      expect(linkVisibilitySetCount).toBeGreaterThan(linkVisBefore)
      // And the re-applied predicate reflects the new filter: graded link hidden.
      expect(capturedLinkVisibility).toBeTypeOf('function')
      expect(capturedNodeVisibility).toBeTypeOf('function')
      expect(capturedLinkVisibility!(gradedLink)).toBe(false)
    })

    it('a new verdict re-applies styles + visibility WITHOUT a graphData re-feed (no re-heat)', async () => {
      gradeEl.mode = 'grade'
      gradeEl.gradeChains = CHAINS
      gradeEl.judgements = []
      await gradeEl.updateComplete

      const feedsBefore = graphDataSetCount
      const nodeVisBefore = nodeVisibilitySetCount
      const linkVisBefore = linkVisibilitySetCount

      // A verdict arrives — mf-app refetch reassigns the judgements array.
      gradeEl.judgements = [GRADED_JUDGEMENT]
      await gradeEl.updateComplete

      // No graphData(data) setter call → the d3 force sim is not restarted.
      expect(graphDataSetCount).toBe(feedsBefore)
      // Visibility re-applied in place (so an 'ungraded' filter hides the graded path).
      expect(nodeVisibilitySetCount).toBeGreaterThan(nodeVisBefore)
      expect(linkVisibilitySetCount).toBeGreaterThan(linkVisBefore)
      // The edge colour map reflects the new verdict (read through the getter).
      expect((gradeEl as any).getEdgeColour('a'.repeat(64))).toBe('live')
    })

    it('linkVisibility honours pathFilter (graded/ungraded/both)', async () => {
      gradeEl.mode = 'grade'
      gradeEl.gradeChains = CHAINS
      gradeEl.judgements = [GRADED_JUDGEMENT]
      await gradeEl.updateComplete
      const gradedLink = { source: 'syn:2', target: 'syn:3', chainSig: 'a'.repeat(64) }
      const ungradedLink = { source: 'syn:2', target: 'syn:5', chainSig: 'b'.repeat(64) }

      // both → all links visible
      expect(capturedLinkVisibility!(gradedLink)).toBe(true)
      expect(capturedLinkVisibility!(ungradedLink)).toBe(true)

      // ungraded → hide graded chain, show ungraded
      gradeEl.pathFilter = 'ungraded'
      await gradeEl.updateComplete
      expect(capturedLinkVisibility!(gradedLink)).toBe(false)
      expect(capturedLinkVisibility!(ungradedLink)).toBe(true)

      // graded → the reverse
      gradeEl.pathFilter = 'graded'
      await gradeEl.updateComplete
      expect(capturedLinkVisibility!(gradedLink)).toBe(true)
      expect(capturedLinkVisibility!(ungradedLink)).toBe(false)
    })

    it('nodeVisibility: node unique to a hidden chain hides; node shared with a visible chain stays', async () => {
      gradeEl.mode = 'grade'
      gradeEl.gradeChains = CHAINS
      gradeEl.judgements = [GRADED_JUDGEMENT]
      await gradeEl.updateComplete

      // ungraded → graded chain (venom, syn:3) hidden; shared heat (syn:2) + anger
      // (syn:1) stay because the ungraded chain still touches them; fire (syn:5) stays.
      gradeEl.pathFilter = 'ungraded'
      await gradeEl.updateComplete
      expect(capturedNodeVisibility!({ id: 'syn:3' })).toBe(false) // venom — graded-only
      expect(capturedNodeVisibility!({ id: 'syn:2' })).toBe(true)  // heat — shared
      expect(capturedNodeVisibility!({ id: 'syn:1' })).toBe(true)  // anger — shared
      expect(capturedNodeVisibility!({ id: 'syn:5' })).toBe(true)  // fire — ungraded vehicle

      // graded → ungraded-only fire (syn:5) hidden; venom (syn:3) shown; shared stay.
      gradeEl.pathFilter = 'graded'
      await gradeEl.updateComplete
      expect(capturedNodeVisibility!({ id: 'syn:5' })).toBe(false) // fire — ungraded-only
      expect(capturedNodeVisibility!({ id: 'syn:3' })).toBe(true)  // venom — graded vehicle
      expect(capturedNodeVisibility!({ id: 'syn:2' })).toBe(true)  // heat — shared
    })

    it('syncs grade-node label DOM when pathFilter hides a node (no orphan labels)', async () => {
      gradeEl.mode = 'grade'
      gradeEl.gradeChains = CHAINS
      gradeEl.judgements = [GRADED_JUDGEMENT]
      await gradeEl.updateComplete

      // Stub the node set the library reports back, with mock label children.
      const mkNode = (id: string) => ({ id,
        __threeObj: { children: [{ isCSS2DObject: true, visible: true, element: document.createElement('div') }] } })
      const venom = mkNode('syn:3') // graded-only vehicle
      const heat = mkNode('syn:2')  // shared
      mockGraphData = { nodes: [venom, heat], links: [] }

      gradeEl.pathFilter = 'ungraded'
      await gradeEl.updateComplete

      // venom (graded-only) is now hidden → its label must be hidden too.
      expect(venom.__threeObj.children[0].visible).toBe(false)
      expect(venom.__threeObj.children[0].element.style.display).toBe('none')
      // heat (shared with the ungraded chain) stays visible.
      expect(heat.__threeObj.children[0].visible).toBe(true)
    })

    it('pathFilter defaults to both (all chains visible)', async () => {
      gradeEl.mode = 'grade'
      gradeEl.gradeChains = CHAINS
      gradeEl.judgements = [GRADED_JUDGEMENT]
      await gradeEl.updateComplete
      expect(gradeEl.pathFilter).toBe('both')
      expect(capturedLinkVisibility!({ source: 'syn:2', target: 'syn:3', chainSig: 'a'.repeat(64) })).toBe(true)
      expect(capturedLinkVisibility!({ source: 'syn:2', target: 'syn:5', chainSig: 'b'.repeat(64) })).toBe(true)
    })

    it('latest judgement wins when two exist for same signature', async () => {
      gradeEl.mode = 'grade'
      gradeEl.gradeChains = CHAINS
      gradeEl.judgements = [
        {
          schema_version: 'judgement.v2', judged_by: 'julian', round: 1,
          topic: 'anger', topic_synset_id: '1',
          vehicle: 'venom', vehicle_synset_id: '3',
          proposer: 'sonnet_v1',
          chain_signature: 'a'.repeat(64),
          linkage: 'good', metaphor: 'dead', tiers: [],
          confidence: 'low', notes: '', supersedes_ts: null,
          ts: '2026-05-29T00:00:00Z',
        },
        {
          schema_version: 'judgement.v2', judged_by: 'julian', round: 2,
          topic: 'anger', topic_synset_id: '1',
          vehicle: 'venom', vehicle_synset_id: '3',
          proposer: 'sonnet_v1',
          chain_signature: 'a'.repeat(64),
          linkage: 'good', metaphor: 'live', tiers: [],
          confidence: 'high', notes: '', supersedes_ts: null,
          ts: '2026-05-30T00:00:00Z',
        },
      ]
      await gradeEl.updateComplete
      expect(gradeEl.getEdgeColour('a'.repeat(64))).toBe('live')
    })

    it('reads legacy v1 judgement records (flat label, no axes) via normaliseJudgement', async () => {
      gradeEl.mode = 'grade'
      gradeEl.gradeChains = CHAINS
      const sig = 'a'.repeat(64)
      // Live v1 records carry a flat `label` and NO linkage/metaphor — they reach the
      // v2-typed prop unchanged via gradingClient.getJudgements(). Cast through unknown
      // to model that runtime reality (10 such records exist in the live JSONL).
      const v1 = (label: string) => ({
        schema_version: 'judgement.v1', judged_by: 'julian', round: 1,
        topic: 'anxiety', topic_synset_id: '1',
        vehicle: 'swarm', vehicle_synset_id: '3',
        proposer: 'sonnet_v1', chain_signature: sig,
        label, confidence: 'high', notes: '', supersedes_ts: null,
        ts: '2026-05-30T00:00:00Z',
      }) as unknown as import('../types/grading').JudgementRecord

      gradeEl.judgements = [v1('live')]
      await gradeEl.updateComplete
      expect(gradeEl.getEdgeColour(sig)).toBe('live')

      gradeEl.judgements = [v1('dead')]
      await gradeEl.updateComplete
      expect(gradeEl.getEdgeColour(sig)).toBe('dead')

      // bad_path → linkage:bad dominates (metaphor unknown in v1).
      gradeEl.judgements = [v1('bad_path')]
      await gradeEl.updateComplete
      expect(gradeEl.getEdgeColour(sig)).toBe('bad_path')

      // irrelevant → linkage moot, metaphor:irrelevant keys the colour.
      gradeEl.judgements = [v1('irrelevant')]
      await gradeEl.updateComplete
      expect(gradeEl.getEdgeColour(sig)).toBe('irrelevant')
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
  })
})

describe('MfForceGraph metaphor forest', () => {
  // Thesaurus graph for "patience" that already holds one forest word (escapement).
  const thesaurus = (): GraphData => ({
    nodes: [
      { id: 'patience', word: 'patience', relationType: 'central', val: 8, order: 0, rarity: 'common' },
      { id: 'forbearance', word: 'forbearance', relationType: 'synonym', val: 4, order: 1, rarity: 'rare' },
      { id: 'escapement', word: 'escapement', relationType: 'similar', val: 2, order: 1, rarity: 'rare' },
    ],
    links: [
      { source: 'patience', target: 'forbearance', relationType: 'synonym', order: 1 },
      { source: 'patience', target: 'escapement', relationType: 'similar', order: 1 },
    ],
  })
  const composed = () => composeForest(thesaurus(), forestToGraph(patienceForest as ForestResponse))
  const nodeById = (data: GraphData, id: string) => data.nodes.find(n => n.id === id)!
  const metaphorLink = (data: GraphData, source: string, target: string) =>
    data.links.find(l => l.metaphor && l.source === source && l.target === target)!
  const thesaurusLink = (data: GraphData) => data.links.find(l => !l.metaphor)!
  const alpha = (colour: string) => {
    const m = colour.match(/rgba\([^)]*,\s*([\d.]+)\)/)
    return m ? Number(m[1]) : 1
  }
  const particles = (l: unknown) => (lastArgs.linkDirectionalParticles[0] as (l: unknown) => number)(l)
  const arrows = (l: unknown) => (lastArgs.linkDirectionalArrowLength[0] as (l: unknown) => number)(l)
  const nodeVal = (n: unknown) => (lastArgs.nodeVal[0] as (n: unknown) => number)(n)

  let el: MfForceGraph
  let data: GraphData

  async function mount(opts: { reducedMotion?: boolean } = {}) {
    vi.stubGlobal('matchMedia', (q: string) => ({
      matches: q.includes('prefers-reduced-motion') ? !!opts.reducedMotion : false,
      addEventListener: () => {}, removeEventListener: () => {},
    }))
    const c = composed()
    data = c.data
    el = new MfForceGraph()
    el.graphData = c.data
    el.forest = c.overlay
    document.body.appendChild(el)
    await el.updateComplete
  }

  beforeEach(() => {
    lastArgs = {}
    setCounts = {}
    graphDataSetCount = 0
    mockGraphData = { nodes: [], links: [] }
  })

  afterEach(() => {
    el.remove()
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('draws endpoints larger than hops and thesaurus words, in the endpoint colour; the source keeps the central gold', async () => {
    await mount()
    const endpoint = nodeById(data, 'seed vault')
    const hop = nodeById(data, 'dormant seed')
    expect(capturedNodeColor!(endpoint)).toBe(FOREST_COLOURS.endpoint)
    expect(capturedNodeColor!(hop)).toBe(FOREST_COLOURS.hop)
    expect(capturedNodeColor!(nodeById(data, 'patience'))).toBe(NODE_COLOURS.central)
    expect(nodeVal(endpoint)).toBeGreaterThan(nodeVal(nodeById(data, 'patience')))
    expect(nodeVal(hop)).toBeLessThan(nodeVal(nodeById(data, 'forbearance')))
    // a forest word already in the thesaurus is drawn as the forest sees it
    expect(capturedNodeColor!(nodeById(data, 'escapement'))).toBe(FOREST_COLOURS.endpoint)
  })

  // Rule: thesaurus links dim while a forest is shown, and only then.
  it('dims thesaurus links while a forest is shown and restores them when it is hidden', async () => {
    await mount()
    const link = thesaurusLink(data)
    const withForest = alpha(capturedLinkColor!(link))
    el.forestVisible = false
    await el.updateComplete
    expect(withForest).toBeLessThan(alpha(capturedLinkColor!(link)))
  })

  it('gives metaphor links their own colour and particles; thesaurus links carry none', async () => {
    await mount()
    const ml = metaphorLink(data, 'patience', 'dormant seed')
    expect(capturedLinkColor!(ml)).toContain(hexToRgb(FOREST_COLOURS.branch))
    expect(particles(ml)).toBeGreaterThan(0)
    expect(particles(thesaurusLink(data))).toBe(0)
    expect(arrows(ml)).toBe(0)
  })

  it('under reduced motion swaps the particles for static arrows', async () => {
    await mount({ reducedMotion: true })
    const ml = metaphorLink(data, 'patience', 'dormant seed')
    expect(particles(ml)).toBe(0)
    expect(arrows(ml)).toBeGreaterThan(0)
    expect(arrows(thesaurusLink(data))).toBe(0)
  })

  it('keeps forest nodes visible when their rarity is filtered out, and hides forest-only nodes with the forest', async () => {
    await mount()
    el.hiddenRarities = new Set(['common', 'unusual', 'rare'])
    await el.updateComplete
    expect(capturedNodeVisibility!(nodeById(data, 'escapement'))).toBe(true)  // rare, but an endpoint
    expect(capturedNodeVisibility!(nodeById(data, 'varve'))).toBe(true)       // forest-only, no rarity
    expect(capturedNodeVisibility!(nodeById(data, 'forbearance'))).toBe(false)
    el.forestVisible = false
    await el.updateComplete
    expect(capturedNodeVisibility!(nodeById(data, 'varve'))).toBe(false)
    expect(capturedLinkVisibility!(metaphorLink(data, 'lake sediment', 'varve'))).toBe(false)
  })

  // Rule: lighting paths brightens exactly their nodes and links, dims every
  // other forest and thesaurus mark, and never re-feeds the simulation.
  it('lights the paths in forestLit and dims the rest without calling graphData()', async () => {
    await mount()
    const feedsBefore = graphDataSetCount
    const unlitLink = metaphorLink(data, 'peat bog', 'bog body')
    const normalAlpha = alpha(capturedLinkColor!(unlitLink))
    el.forestLit = new Set(['seed vault'])
    await el.updateComplete

    expect(capturedNodeColor!(nodeById(data, 'seed vault'))).toBe(FOREST_COLOURS.endpoint)
    expect(capturedNodeColor!(nodeById(data, 'dormant seed'))).toBe(FOREST_COLOURS.hop)
    expect(alpha(capturedNodeColor!(nodeById(data, 'bog body')))).toBeLessThan(0.5)
    expect(alpha(capturedNodeColor!(nodeById(data, 'forbearance')))).toBeLessThan(0.5)
    expect(capturedNodeColor!(nodeById(data, 'patience'))).toBe(NODE_COLOURS.central)

    expect(capturedLinkColor!(metaphorLink(data, 'dormant seed', 'seed vault'))).toBe(FOREST_COLOURS.spark)
    expect(alpha(capturedLinkColor!(unlitLink))).toBeLessThan(normalAlpha)
    expect(particles(metaphorLink(data, 'dormant seed', 'seed vault'))).toBeGreaterThan(particles(unlitLink))
    expect(graphDataSetCount).toBe(feedsBefore)
  })

  it('draws lit branches wider than the rest of the forest', async () => {
    await mount()
    const lit = metaphorLink(data, 'dormant seed', 'seed vault')
    const other = metaphorLink(data, 'peat bog', 'bog body')
    const before = capturedLinkWidth!(lit)
    el.forestLit = new Set(['seed vault'])
    await el.updateComplete
    expect(capturedLinkWidth!(lit)).toBeGreaterThan(before)
    expect(capturedLinkWidth!(other)).toBeLessThanOrEqual(before)
  })

  it('marks the labels on a lit path so its hops stand out, and gives the source a root label', async () => {
    await mount()
    const label = (n: unknown) => (capturedNodeThreeObject!(n) as { element: HTMLElement }).element
    expect(label(nodeById(data, 'patience')).dataset.role).toBe('forest-source')
    el.forestLit = new Set(['seed vault'])
    await el.updateComplete
    expect(label(nodeById(data, 'dormant seed')).hasAttribute('data-lit')).toBe(true)
    expect(label(nodeById(data, 'seed vault')).hasAttribute('data-lit')).toBe(true)
    expect(label(nodeById(data, 'peat bog')).hasAttribute('data-lit')).toBe(false)
  })

  // Rule: a selection looks different from a hover, so toggling it under the
  // pointer always shows a change.
  it('rings the selected forest node label, whatever else is lit', async () => {
    await mount()
    const labelEl = document.createElement('div')
    const otherEl = document.createElement('div')
    mockGraphData = {
      nodes: [
        { ...nodeById(data, 'keloid'), __threeObj: { children: [{ isCSS2DObject: true, element: labelEl }] } },
        { ...nodeById(data, 'varve'), __threeObj: { children: [{ isCSS2DObject: true, element: otherEl }] } },
      ],
      links: [],
    }
    el.forestSelectedId = 'keloid'
    el.forestLit = new Set(['varve'])
    await el.updateComplete
    expect(labelEl.hasAttribute('data-selected')).toBe(true)
    expect(otherEl.hasAttribute('data-selected')).toBe(false)
    const born = (capturedNodeThreeObject!(nodeById(data, 'keloid')) as { element: HTMLElement }).element
    expect(born.hasAttribute('data-selected')).toBe(true)
    el.forestSelectedId = null
    await el.updateComplete
    expect(labelEl.hasAttribute('data-selected')).toBe(false)
  })

  it('marks lit grounds and lit labels on the label DOM, and clears them when nothing is lit', async () => {
    await mount()
    const groundEl = document.createElement('div')
    const labelEl = document.createElement('div')
    const dimLabelEl = document.createElement('div')
    const lit = { ...metaphorLink(data, 'dormant seed', 'seed vault'), __lineObj: { children: [{}, { isCSS2DObject: true, element: groundEl }] } }
    mockGraphData = {
      nodes: [
        { ...nodeById(data, 'seed vault'), __threeObj: { children: [{ isCSS2DObject: true, element: labelEl }] } },
        { ...nodeById(data, 'bog body'), __threeObj: { children: [{ isCSS2DObject: true, element: dimLabelEl }] } },
      ],
      links: [lit],
    }
    el.forestLit = new Set(['seed vault'])
    await el.updateComplete
    expect(groundEl.hasAttribute('data-lit')).toBe(true)
    expect(labelEl.hasAttribute('data-dim')).toBe(false)
    expect(dimLabelEl.hasAttribute('data-dim')).toBe(true)

    el.forestLit = null
    await el.updateComplete
    expect(groundEl.hasAttribute('data-lit')).toBe(false)
    expect(dimLabelEl.hasAttribute('data-dim')).toBe(false)
  })

  it('keeps each ground label on its link, a little nearer the parent word', async () => {
    await mount()
    const update = lastArgs.linkPositionUpdate[0] as (obj: unknown, ends: unknown, link: unknown) => boolean
    const label = { isCSS2DObject: true, position: { x: 0, y: 0, z: 0, set(x: number, y: number, z: number) { Object.assign(this, { x, y, z }) } } }
    update(label, { start: { x: 0, y: 0, z: 0 }, end: { x: 100, y: 50, z: 10 } }, {})
    expect(label.position.x).toBeGreaterThan(30)
    expect(label.position.x).toBeLessThan(50)
    expect(label.position.y / label.position.x).toBeCloseTo(0.5)
    expect(() => update(undefined, { start: { x: 0, y: 0, z: 0 }, end: { x: 1, y: 1, z: 1 } }, {})).not.toThrow()
  })

  it('builds a ground label on metaphor links only, from the edge grounds, as text', async () => {
    await mount()
    const makeLinkObj = lastArgs.linkThreeObject[0] as (l: unknown) => { element: HTMLElement } | null
    expect(makeLinkObj(thesaurusLink(data))).toBeNull()
    const hostile = { ...metaphorLink(data, 'patience', 'dormant seed') }
    hostile.metaphor = { ...hostile.metaphor!, grounds: ['<img src=x onerror=alert(1)>'] }
    const obj = makeLinkObj(hostile)!
    expect(obj.element.querySelector('img')).toBeNull()
    expect(obj.element.textContent).toBe('<img src=x onerror=alert(1)>')
  })

  it('labels endpoints with a live mark and forest role, and renders a hostile word as text', async () => {
    await mount()
    const label = (n: unknown) => (capturedNodeThreeObject!(n) as { element: HTMLElement }).element
    const live = label(nodeById(data, 'seed vault'))
    expect(live.dataset.role).toBe('forest-endpoint')
    expect(live.querySelector('.mf-graph-label__mark')?.textContent).toBe('✦')
    expect(label(nodeById(data, 'solera')).querySelector('.mf-graph-label__mark')).toBeNull()
    expect(label(nodeById(data, 'dormant seed')).dataset.role).toBe('forest-hop')

    const hostile = { ...nodeById(data, 'varve'), word: '<img src=x onerror=alert(1)>' }
    expect(label(hostile).querySelector('img')).toBeNull()
    expect(label(hostile).textContent).toContain('<img src=x onerror=alert(1)>')
  })

  it('rebuilds node labels when the forest changes, so a thesaurus word picks up its forest role', async () => {
    await mount()
    // the library recreates every node object when this accessor is re-set
    const before = capturedNodeThreeObject
    el.forest = null
    el.graphData = thesaurus()
    await el.updateComplete
    expect(capturedNodeThreeObject).not.toBe(before)
    const escapement = thesaurus().nodes[2]
    expect((capturedNodeThreeObject!(escapement) as { element: HTMLElement }).element.dataset.role).toBe('rare')
  })

  // Rule: on a forest node, a single click selects and never expands; double-click navigates.
  it('single click on a forest node selects it and never fires mf-node-select', async () => {
    await mount()
    vi.useFakeTimers()
    const select = vi.fn(), expand = vi.fn()
    el.addEventListener('mf-forest-select', select)
    el.addEventListener('mf-node-select', expand)
    capturedOnNodeClick!(nodeById(data, 'escapement'))
    vi.advanceTimersByTime(400)
    expect(expand).not.toHaveBeenCalled()
    expect(select).toHaveBeenCalledOnce()
    expect(select.mock.calls[0][0].detail).toEqual({ target: { kind: 'node', id: 'escapement' } })
  })

  it('double-click on a forest node navigates', async () => {
    await mount()
    vi.useFakeTimers()
    const nav = vi.fn(), select = vi.fn()
    el.addEventListener('mf-node-navigate', nav)
    el.addEventListener('mf-forest-select', select)
    capturedOnNodeClick!(nodeById(data, 'varve'))
    capturedOnNodeClick!(nodeById(data, 'varve'))
    vi.advanceTimersByTime(400)
    expect(nav).toHaveBeenCalledOnce()
    expect(select).not.toHaveBeenCalled()
  })

  it('single click on a thesaurus node still expands it while a forest is shown', async () => {
    await mount()
    vi.useFakeTimers()
    const expand = vi.fn()
    el.addEventListener('mf-node-select', expand)
    capturedOnNodeClick!(nodeById(data, 'forbearance'))
    vi.advanceTimersByTime(400)
    expect(expand).toHaveBeenCalledOnce()
  })

  it('click on a metaphor link selects it; a background click clears the selection', async () => {
    await mount()
    const select = vi.fn()
    el.addEventListener('mf-forest-select', select)
    capturedOnLinkClick!(metaphorLink(data, 'scar tissue', 'hypertrophic scar'))
    ;(lastArgs.onBackgroundClick[0] as () => void)()
    expect(select.mock.calls.map(c => c[0].detail)).toEqual([
      { target: { kind: 'link', source: 'scar tissue', target: 'hypertrophic scar' } },
      { target: null },
    ])
  })

  it('hover on a forest node or metaphor link emits mf-forest-hover, and leaving emits null', async () => {
    await mount()
    const hover = vi.fn()
    el.addEventListener('mf-forest-hover', hover)
    capturedOnNodeHover!(nodeById(data, 'dormant seed'), null)
    capturedOnNodeHover!(null, nodeById(data, 'dormant seed'))
    ;(lastArgs.onLinkHover[0] as (l: unknown) => void)(metaphorLink(data, 'peat bog', 'bog body'))
    ;(lastArgs.onLinkHover[0] as (l: unknown) => void)(null)
    capturedOnNodeHover!(nodeById(data, 'forbearance'), null) // thesaurus: no forest hover
    expect(hover.mock.calls.map(c => c[0].detail.target)).toEqual([
      { kind: 'node', id: 'dormant seed' },
      null,
      { kind: 'link', source: 'peat bog', target: 'bog body' },
      null,
    ])
  })

  it('never sets a forest hover from touch input (no sticky hover after a tap)', async () => {
    await mount()
    const hover = vi.fn()
    el.addEventListener('mf-forest-hover', hover)
    const container = el.shadowRoot!.querySelector('#graph-container')!
    container.dispatchEvent(Object.assign(new Event('pointerdown', { bubbles: true }), { pointerType: 'touch' }))
    capturedOnNodeHover!(nodeById(data, 'dormant seed'), null)
    expect(hover).not.toHaveBeenCalled()
    container.dispatchEvent(Object.assign(new Event('pointermove', { bubbles: true }), { pointerType: 'mouse' }))
    capturedOnNodeHover!(nodeById(data, 'dormant seed'), null)
    expect(hover).toHaveBeenCalledOnce()
  })

  it('frames the camera when a new forest arrives, and not when paths are lit', async () => {
    vi.useFakeTimers()
    await mount()
    const framesAfterMount = setCounts.zoomToFit ?? 0
    vi.advanceTimersByTime(5000)
    const framed = setCounts.zoomToFit ?? 0
    expect(framed).toBeGreaterThan(framesAfterMount)
    el.forestLit = new Set(['varve'])
    await el.updateComplete
    vi.advanceTimersByTime(5000)
    expect(setCounts.zoomToFit ?? 0).toBe(framed)
  })

  it('fades thesaurus labels while a forest is shown, and restores them when it is hidden', async () => {
    await mount()
    const label = (n: unknown) => (capturedNodeThreeObject!(n) as { element: HTMLElement }).element
    expect(label(nodeById(data, 'forbearance')).hasAttribute('data-recede')).toBe(true)
    expect(label(nodeById(data, 'seed vault')).hasAttribute('data-recede')).toBe(false)
    expect(label(nodeById(data, 'patience')).hasAttribute('data-recede')).toBe(false)
    el.forestVisible = false
    await el.updateComplete
    expect(label(nodeById(data, 'forbearance')).hasAttribute('data-recede')).toBe(false)
  })

  it('installs the depth force so the forest grows outward from the source', async () => {
    await mount()
    const call = (lastArgs.d3Force ?? []) as unknown[]
    expect(call[0]).toBe('forestDepth')
    expect(typeof call[1]).toBe('function')
  })

  it('emits no forest events and draws no forest styling in grade mode', async () => {
    await mount()
    el.mode = 'grade'
    await el.updateComplete
    const select = vi.fn()
    el.addEventListener('mf-forest-select', select)
    ;(lastArgs.onBackgroundClick[0] as () => void)()
    expect(select).not.toHaveBeenCalled()
  })
})

function hexToRgb(hex: string): string {
  const n = parseInt(hex.slice(1), 16)
  return `${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}`
}
