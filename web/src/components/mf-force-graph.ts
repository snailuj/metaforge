import { LitElement, html, css } from 'lit'
import { customElement, property } from 'lit/decorators.js'
import type { PropertyValues } from 'lit'
import ForceGraph3D from '3d-force-graph'
import type { ForceGraph3DInstance } from '3d-force-graph'
import type { GraphData, GraphLink, GraphNode, Rarity } from '@/graph/types'
import { NODE_COLOURS, RARITY_COLOURS, DEFAULT_NODE_COLOUR } from '@/graph/colours'
import { makeLabelRenderer, makeLabelObject, syncLabelVisibility, DEFAULT_LABEL_SIZE, type LabelSizeConfig, type LabelStyle, type BacklinkRow } from '@/graph/label-layer'
import type { ChainRecord, JudgementRecord } from '../types/grading'
import { normaliseJudgement } from '../types/grading'

const EDGE_COLOUR = 'rgba(232, 224, 212, 0.15)'
const EDGE_COLOUR_DIM = 'rgba(232, 224, 212, 0.08)'

// 300ms matches typical OS double-click threshold; balances responsiveness
// with avoiding false double-click detection on slower clickers
const DBLCLICK_THRESHOLD_MS = 300

// Grade-mode node/edge styling (spec "Force-graph node visuals"). Browse mode
// uses rarity colours; grade nodes carry a `role` instead, so they need their
// own palette + sizes, and edges colour by verdict.
const GRADE_NODE_COLOURS: Record<'topic' | 'vehicle' | 'step', string> = {
  topic: '#e2b07d',   // orange
  vehicle: '#6fb8e0', // blue
  step: '#c8c8c8',    // grey
}
const GRADE_NODE_VAL: Record<'topic' | 'vehicle' | 'step', number> = {
  topic: 10,
  vehicle: 7,
  step: 4,
}
const GRADE_EDGE_COLOURS: Record<string, string> = {
  live: '#6db86d',
  dead: '#c47a7a',
  bad_path: '#d6a560',
  irrelevant: '#5a5f6a',
  ungraded: '#e8e8e8',
}

// Grade-mode graph node — keyed by synset_id or head to ensure dedup across chains.
// The label shows the `head` (stable snapped concept). A deduped node is reached by
// many chains, each with its own phrase, so per-connection phrases live in
// `backlinks` (surfaced in the label's hover tooltip), not as a single phrase.
interface GradeNode {
  id: string
  head: string
  role: 'topic' | 'vehicle' | 'step'
  backlinks: BacklinkRow[]
}

// Grade-mode graph link — retains originating chain signature for colouring
interface GradeLink {
  source: string
  target: string
  chainSig: string
}

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
      touch-action: none;
    }
    /* three-render-objects injects its .scene-nav-info style into document.head,
       which cannot cross our shadow boundary — so inside the shadow root the hint
       is unstyled and renders as an in-flow ~18px text block that pushes the
       <canvas> (and the whole WebGL scene) down 18px. That desynchronises the
       canvas frame from the CSS2D label overlay (labels float ~18px above their
       nodes) and from three's DragControls raycaster (hover registers ~18px low —
       the long-standing "aim below the node" bug). Re-declaring the rule here
       takes the hint out of flow and restores top:0 alignment for all three.
       Guarded by web/e2e/raycaster-offset.spec.ts (canvasTopMinusContainerTop). */
    .scene-nav-info {
      position: absolute;
      bottom: 5px;
      width: 100%;
      text-align: center;
      color: slategrey;
      opacity: 0.7;
      font-size: 10px;
      pointer-events: none;
      user-select: none;
    }
    /* Labels live in this shadow root (CSS2DRenderer overlay), so the hover
       highlight rule applies here. */
    .mf-graph-label {
      transition: background 120ms ease;
    }
    .mf-graph-label.label-hovered {
      background: rgba(255, 255, 255, 0.18);
      outline: 1px solid rgba(255, 255, 255, 0.5);
    }
    /* Backlink tooltip: default-hidden HERE (stylesheet, not inline) so the
       sibling :hover rule can reveal it — an inline display:none would
       out-specify it and never show. Reveal is pure CSS off the arrow's
       hover, so there are zero per-label listeners (matters at fog-of-war scale). */
    .mf-graph-label__tooltip {
      display: none;
      background: rgba(20, 20, 40, 0.92);
      color: #e8e0d4;
      padding: 4px 8px;
      border-radius: 4px;
      font-size: 12px;
      font-family: Georgia, "Times New Roman", serif;
      white-space: nowrap;
      max-width: 320px;
      z-index: 10;
    }
    .mf-graph-label__arrow:hover ~ .mf-graph-label__tooltip {
      display: block;
    }
    .mf-graph-label__tooltip-head {
      font-weight: bold;
      margin-bottom: 2px;
    }
    .mf-graph-label__backlink {
      opacity: 0.85;
    }
  `

  private graph: ForceGraph3DInstance | null = null
  private labelRenderer: ReturnType<typeof makeLabelRenderer> | null = null
  private container: HTMLDivElement | null = null
  private clickTimer: ReturnType<typeof setTimeout> | null = null
  private resizeObserver: ResizeObserver | null = null
  private previousHoveredNode: GraphNode | null = null
  private gradeFrameTimer: ReturnType<typeof setTimeout> | null = null
  // Distance at which distance-floor labels render at full basePx (captured from
  // the framing camera in Task 6; the sensible default here keeps the getter pure).
  private labelRefDist = 200
  // Chain signature of the path currently hovered (grade mode) — whole-path highlight.
  private hoveredChainSig: string | null = null

  @property({ type: Object }) graphData: GraphData = { nodes: [], links: [] }
  @property({ type: Object }) hiddenRarities: Set<Rarity> = new Set()
  @property({ attribute: false }) mode: 'browse' | 'grade' = 'browse'
  @property({ attribute: false }) gradeChains: ChainRecord[] = []
  @property({ attribute: false }) judgements: JudgementRecord[] = []
  // Tri-state path filter (grade mode). The FULL grade graph is always fed so
  // node positions stay stable; this only toggles visibility of existing
  // objects — no force-sim re-heat / "bounce". 'both' shows everything,
  // 'graded'/'ungraded' show only chains with/without a latest verdict.
  @property({ attribute: false }) pathFilter: 'both' | 'ungraded' | 'graded' = 'both'
  @property({ attribute: false }) labelSize: LabelSizeConfig | null = null
  @property({ type: Number }) viewportWidth = typeof window !== 'undefined' ? window.innerWidth : 1024

  // Whether the 3D library should be loaded. Derived from mode + viewportWidth —
  // kept as a getter so Lit never schedules a secondary update cycle from updated().
  // Rendered by the template (controls flat fallback), so changes propagate via
  // the reactive props it depends on (mode, viewportWidth) — no @state needed.
  get threeDLoaded(): boolean {
    return this.mode === 'browse' || this.viewportWidth >= 900
  }

  // --- Grade-mode derived accessors ---

  /** Deduplicated node list for grade mode. Keyed by synset_id (preferred) or head. */
  get gradeNodes(): GradeNode[] {
    if (this.mode !== 'grade') return []
    return this.buildGradeGraph().nodes
  }

  /** Edge list for grade mode, one link per consecutive chain step pair. */
  get gradeLinks(): GradeLink[] {
    if (this.mode !== 'grade') return []
    return this.buildGradeGraph().links
  }

  private buildGradeGraph(): { nodes: GradeNode[]; links: GradeLink[] } {
    const nodes = new Map<string, GradeNode>()
    const links: GradeLink[] = []
    // Per-node set of seen `${source} ${phrase}` keys, so identical inbound
    // connections (same previous head + same phrase) collapse to one backlink.
    const backlinkKeys = new Map<string, Set<string>>()
    // Always build the FULL grade graph (all chains). The path filter is applied
    // at render time via nodeVisibility/linkVisibility so node positions stay
    // fixed across filter changes — feeding a filtered set would re-heat the
    // force sim and bounce the layout.
    for (const chain of this.gradeChains) {
      const stepIds: string[] = []
      for (let i = 0; i < chain.chain.length; i++) {
        const step = chain.chain[i]
        const id = step.synset_id ? `syn:${step.synset_id}` : `head:${step.head}`
        const role: GradeNode['role'] =
          i === 0 ? 'topic' : (i === chain.chain.length - 1 ? 'vehicle' : 'step')
        if (!nodes.has(id)) {
          nodes.set(id, { id, head: step.head, role, backlinks: [] })
          backlinkKeys.set(id, new Set())
        }
        // Accumulate the inbound connection on the TARGET node: source = the
        // previous step's head, phrase = this step's phrase. Deduped per node.
        if (i > 0) {
          const prev = chain.chain[i - 1]
          const key = JSON.stringify([prev.head, step.phrase]) // structured: free-text fields, a space-join could collide
          const seen = backlinkKeys.get(id)!
          if (!seen.has(key)) {
            seen.add(key)
            nodes.get(id)!.backlinks.push({ source: prev.head, phrase: step.phrase })
          }
        }
        stepIds.push(id)
      }
      for (let i = 0; i < stepIds.length - 1; i++) {
        links.push({ source: stepIds[i], target: stepIds[i + 1], chainSig: chain.chain_signature })
      }
    }
    return { nodes: [...nodes.values()], links }
  }

  /**
   * Called when a node is clicked in grade mode. Emits `chain-selected` with
   * the matching ChainRecord if the clicked node is a vehicle endpoint.
   * Non-vehicle clicks are silently ignored — callers should set `isVehicle`
   * based on node role in the grade graph.
   */
  handleNodeClick(node: { id: string; isVehicle?: boolean }): void {
    if (this.mode !== 'grade' || !node.isVehicle) return
    const matches = this.gradeChains.filter(c => {
      const last = c.chain[c.chain.length - 1]
      const lastId = last.synset_id ? `syn:${last.synset_id}` : `head:${last.head}`
      return lastId === node.id
    })
    if (matches.length === 0) return
    // v1: emit first match; multi-match disambiguation is a v1.1 affordance
    this.dispatchEvent(new CustomEvent('chain-selected', {
      detail: matches[0],
      bubbles: true,
      composed: true,
    }))
  }

  /**
   * Latest-per-signature verdict derived from the judgements prop.
   * Newer ts string wins; undefined ts sorts last (treated as empty string).
   */
  private get latestVerdicts(): Map<string, JudgementRecord> {
    const m = new Map<string, JudgementRecord>()
    for (const j of this.judgements) {
      const existing = m.get(j.chain_signature)
      if (!existing || (j.ts ?? '') > (existing.ts ?? '')) {
        m.set(j.chain_signature, j)
      }
    }
    return m
  }

  /**
   * Returns the GRADE_EDGE_COLOURS key for a chain signature, or null if unjudged
   * (so the renderer applies the `ungraded` colour). Derived from the two verdict
   * axes: a broken route (linkage:bad) dominates as `bad_path`; otherwise the
   * endpoint's metaphor verdict (live/dead/irrelevant) keys the colour.
   *
   * Stored records may be v1 (flat `label`) or v2 (two axes) — `getJudgements()`
   * feeds both through the v2-typed prop unchanged. `normaliseJudgement` maps either
   * to the uniform two-axis view, matching the sibling consumer `mf-app.priorVerdict`
   * so a graded legacy record still keys a colour rather than reading as ungraded.
   */
  getEdgeColour(chainSig: string): string | null {
    const record = this.latestVerdicts.get(chainSig)
    if (!record) return null
    const { linkage, metaphor } = normaliseJudgement(record)
    if (linkage === 'bad') return 'bad_path'
    return metaphor
  }

  // --- Grade-mode path filter ---

  /** Does a chain (by signature) pass the current tri-state path filter?
   *  both → always; graded → has a latest verdict; ungraded → has none. */
  private pathFilterPasses(chainSig: string): boolean {
    if (this.pathFilter === 'both') return true
    const hasVerdict = this.latestVerdicts.has(chainSig)
    return this.pathFilter === 'graded' ? hasVerdict : !hasVerdict
  }

  /** Ids of grade nodes touched by at least one VISIBLE link. A node shared
   *  between a visible and a hidden chain stays visible. Recomputed each
   *  visibility pass — cheap relative to the force sim it replaces. */
  private visibleGradeNodeIds(): Set<string> {
    const ids = new Set<string>()
    for (const link of this.gradeLinks) {
      if (!this.pathFilterPasses(link.chainSig)) continue
      ids.add(link.source)
      ids.add(link.target)
    }
    return ids
  }

  // --- Visibility predicates (browse rarity filter + grade path filter) ---

  private isNodeVisible = (n: unknown): boolean => {
    if (this.mode === 'grade') {
      // Visible iff touched by a visible link under the current path filter.
      return this.visibleGradeNodeIds().has((n as { id: string }).id)
    }
    const node = n as GraphNode
    if (node.relationType === 'central') return true
    const rarity = node.rarity ?? 'unusual'
    return !this.hiddenRarities.has(rarity)
  }

  private isLinkVisible = (l: unknown): boolean => {
    if (this.mode === 'grade') {
      return this.pathFilterPasses((l as GradeLink).chainSig)
    }
    const link = l as { source: unknown; target: unknown }
    return this.isNodeVisible(link.source) && this.isNodeVisible(link.target)
  }

  /** Resolved label sizing: explicit prop overrides the per-mode default. */
  get effectiveLabelSize(): LabelSizeConfig {
    return this.labelSize ?? DEFAULT_LABEL_SIZE[this.mode]
  }

  /** Style descriptor for a node's DOM label — reuses the sprite-era colour logic
   *  so grade and browse palettes flow through one label code path. */
  private labelStyleFor(n: unknown): LabelStyle {
    if (this.mode === 'grade') {
      const gn = n as GradeNode
      return { text: gn.head, colour: GRADE_NODE_COLOURS[gn.role], role: gn.role, backlinks: gn.backlinks }
    }
    const node = n as GraphNode
    const colour = node.relationType === 'central'
      ? NODE_COLOURS.central
      : RARITY_COLOURS[node.rarity ?? 'unusual'] ?? DEFAULT_NODE_COLOUR
    return { text: node.word, colour, role: node.relationType === 'central' ? 'central' : (node.rarity ?? 'unusual') }
  }

  protected firstUpdated(): void {
    this.container = this.renderRoot.querySelector('#graph-container') as HTMLDivElement
    if (!this.container) return

    this.labelRenderer = makeLabelRenderer(this.container.clientWidth, this.container.clientHeight)
    this.graph = ForceGraph3D({ controlType: 'orbit', extraRenderers: [this.labelRenderer] })(this.container)
      .backgroundColor('#1a1a2e')
      .nodeColor((n: unknown) => {
        if (this.mode === 'grade') return GRADE_NODE_COLOURS[(n as GradeNode).role]
        const node = n as GraphNode
        if (node.relationType === 'central') return NODE_COLOURS.central
        return RARITY_COLOURS[node.rarity ?? 'unusual'] ?? DEFAULT_NODE_COLOUR
      })
      .nodeVal((n: unknown) => (
        this.mode === 'grade' ? GRADE_NODE_VAL[(n as GradeNode).role] : (n as GraphNode).val
      ))
      .nodeOpacity(0.9)
      .nodeRelSize(0.5)
      .nodeThreeObjectExtend(true)
      .nodeThreeObject((n: unknown) => makeLabelObject(
        this.labelStyleFor(n),
        () => this.effectiveLabelSize,
        () => this.labelRefDist,
      ))
      .d3VelocityDecay(0.85)
      .d3AlphaDecay(0.005)
      .cooldownTime(30000)
      .warmupTicks(50)
      .linkColor((l: unknown) => {
        if (this.mode === 'grade') {
          const sig = (l as GradeLink).chainSig
          const verdict = this.getEdgeColour(sig)
          const base = GRADE_EDGE_COLOURS[verdict ?? 'ungraded']
          // Whole-path highlight: links sharing the hovered chain glow white.
          return sig === this.hoveredChainSig ? '#ffffff' : base
        }
        return (l as GraphLink).order === 2 ? EDGE_COLOUR_DIM : EDGE_COLOUR
      })
      .linkWidth((l: unknown) => {
        if (this.mode === 'grade') {
          return (l as GradeLink).chainSig === this.hoveredChainSig ? 3 : 1.5
        }
        return (l as GraphLink).order === 2 ? 0.5 : 1
      })
      .linkOpacity(0.6)
      .onLinkHover((l: unknown) => {
        if (this.mode !== 'grade') return
        const sig = l ? (l as GradeLink).chainSig : null
        if (sig !== this.hoveredChainSig) {
          this.hoveredChainSig = sig
          this.refreshLinkStyles()
        }
        if (this.container) this.container.style.cursor = l ? 'pointer' : 'default'
      })
      .onLinkClick((l: unknown) => {
        if (this.mode !== 'grade' || !l) return
        // Click anywhere on a path selects it — same as clicking the vehicle.
        const sig = (l as GradeLink).chainSig
        const chain = this.gradeChains.find(c => c.chain_signature === sig)
        if (chain) {
          this.dispatchEvent(new CustomEvent('chain-selected', {
            detail: chain, bubbles: true, composed: true,
          }))
        }
      })
      .onNodeClick((n: unknown) => {
        // In grade mode, node clicks route to handleNodeClick for chain-selected emission.
        // The grade graph uses `id` keys of the form `syn:<id>` or `head:<name>`.
        if (this.mode === 'grade') {
          const gn = this.gradeNodes.find(node => node.id === (n as { id?: string }).id)
          if (gn && gn.role === 'vehicle') {
            this.handleNodeClick({ id: gn.id, isVehicle: true })
          }
          return
        }
        // Browse-mode behaviour — unchanged.
        const node = n as GraphNode
        if (node.order === 2) {
          if (this.clickTimer) {
            clearTimeout(this.clickTimer)
            this.clickTimer = null
          }
          return
        }
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
          }, DBLCLICK_THRESHOLD_MS)
        }
      })
      .onNodeRightClick((n: unknown, event: MouseEvent) => {
        const node = n as GraphNode
        event.preventDefault()
        navigator.clipboard.writeText(node.word).catch(() => { /* clipboard unavailable */ })
        this.dispatchEvent(
          new CustomEvent('mf-node-copy', {
            detail: { word: node.word },
            bubbles: true,
            composed: true,
          }),
        )
      })
      .onNodeHover((n: unknown) => {
        const node = n as GraphNode | null
        if (this.container) {
          this.container.style.cursor = node ? 'pointer' : 'default'
        }

        if (this.previousHoveredNode) {
          this.setLabelHover(this.previousHoveredNode, false)
        }
        if (node) {
          this.setLabelHover(node, true)
        }
        this.previousHoveredNode = node
      })

    // Grade mode: tighter constellation + bigger hit-spheres so nodes are
    // closer together and easier to click. (Browse mode keeps its defaults —
    // this is a separate element instance from the browse graph.)
    if (this.mode === 'grade' && this.graph) {
      this.graph.nodeRelSize(2)
      this.graph.d3Force('charge')?.strength?.(-22)
      this.graph.d3Force('link')?.distance?.(18)
    }

    // Sync renderer dimensions to actual container size (fixes hit-test offset)
    requestAnimationFrame(() => {
      this.syncDimensions()

      if (this.graph) {
        // Pull camera 35% closer than the default starting distance
        const camera = this.graph.camera() as { position: { x: number; y: number; z: number } }
        camera.position.z *= 0.65
        // Distance at which distance-floor labels render at full basePx.
        this.labelRefDist = Math.hypot(camera.position.x, camera.position.y, camera.position.z) || 200

        // Enable smooth zoom/orbit damping (3d-force-graph already calls
        // controls.update() each frame, so this works out of the box)
        const controls = this.graph.controls() as {
          enableDamping: boolean
          dampingFactor: number
        }
        controls.enableDamping = true
        controls.dampingFactor = 0.05
      }
    })

    this.resizeObserver = new ResizeObserver(() => this.syncDimensions())
    this.resizeObserver.observe(this.container)

    this.graph.nodeVisibility(this.isNodeVisible)
    this.graph.linkVisibility(this.isLinkVisible)

    this.feedGraph()
  }

  /**
   * The node/link set actually handed to the 3D renderer: the grade graph in
   * grade mode, the browse graph otherwise. This is the decision that was
   * missing — grade nodes/links were computed but never fed to the library,
   * so grade mode rendered an empty graph.
   */
  activeGraphData(): { nodes: unknown[]; links: unknown[] } {
    if (this.mode === 'grade') {
      return { nodes: this.gradeNodes, links: this.gradeLinks }
    }
    return this.graphData
  }

  /** Re-apply link accessors so the library re-evaluates colour/width
   *  (used for whole-path hover highlight). */
  private refreshLinkStyles(): void {
    if (!this.graph) return
    this.graph.linkColor(this.graph.linkColor()).linkWidth(this.graph.linkWidth())
  }

  /** Feed the active graph to the library, and (grade mode) frame it. */
  private feedGraph(): void {
    if (!this.graph) return
    const data = this.activeGraphData()
    if (this.mode === 'grade') {
      this.graph.graphData(data as GraphData)
      this.frameGradeGraph()
    } else if (data.nodes.length) {
      this.graph.graphData(data as GraphData)
    }
  }

  /**
   * Frame the grade constellation after the force sim has had a moment to
   * spread nodes out from the origin. Without this the camera can sit
   * zoomed-out / panned away from the cluster (the reported "nothing on
   * screen" symptom once data is flowing).
   */
  private frameGradeGraph(): void {
    if (this.gradeFrameTimer) clearTimeout(this.gradeFrameTimer)
    this.gradeFrameTimer = setTimeout(() => {
      this.graph?.zoomToFit(400, 30)
    }, 700)
  }

  /** Toggle the hover highlight class on a node's DOM label. */
  private setLabelHover(node: GraphNode, hover: boolean): void {
    const threeObj = (node as unknown as { __threeObj?: { children?: Array<{ isCSS2DObject?: boolean; element: HTMLElement }> } }).__threeObj
    const label = threeObj?.children?.find(c => c.isCSS2DObject)
    if (label) label.element.classList.toggle('label-hovered', hover)
  }

  private syncDimensions() {
    if (!this.container || !this.graph) return
    const { clientWidth, clientHeight } = this.container
    if (clientWidth > 0 && clientHeight > 0) {
      this.graph.width(clientWidth).height(clientHeight)
    }
  }

  updated(changed: PropertyValues<this>): void {
    // Re-feed the renderer when the browse graph, the mode, the grade chains,
    // or the judgements (edge colours) change. Grade-mode data flows here —
    // gradeChains arrives via prop after a topic is selected.
    if (this.graph && (
      changed.has('graphData') || changed.has('mode') ||
      changed.has('gradeChains') || changed.has('judgements')
    )) {
      this.feedGraph()
    }
    // Both visibility filters toggle ALREADY-FED objects in place — they never
    // re-feed, so the force sim does not re-heat and the layout stays put.
    // grade-mode 'pathFilter' and browse-mode 'hiddenRarities' share this path.
    if ((changed.has('pathFilter') || changed.has('hiddenRarities')) && this.graph) {
      this.reapplyVisibility()
    }
  }

  /** Re-apply the visibility predicates and mirror them onto the label DOM.
   *  nodeVisibility removes a hidden node's group from the scene, so
   *  CSS2DRenderer never re-traverses its label and would otherwise leave it
   *  stuck visible at its last position — hence the explicit label sync. */
  private reapplyVisibility(): void {
    if (!this.graph) return
    this.graph.nodeVisibility(this.isNodeVisible).linkVisibility(this.isLinkVisible)
    const data = this.graph.graphData() as unknown as { nodes?: Parameters<typeof syncLabelVisibility>[0] }
    // graphData() is library-owned; guard against an unpopulated graph (e.g.
    // a filter toggled before any data was fed) where nodes is absent.
    if (Array.isArray(data.nodes)) syncLabelVisibility(data.nodes, this.isNodeVisible)
  }

  disconnectedCallback(): void {
    super.disconnectedCallback()
    if (this.clickTimer) clearTimeout(this.clickTimer)
    if (this.gradeFrameTimer) clearTimeout(this.gradeFrameTimer)
    if (this.resizeObserver) {
      this.resizeObserver.disconnect()
      this.resizeObserver = null
    }
    if (this.graph) {
      this.graph.pauseAnimation()
      const renderer = this.graph.renderer()
      if (renderer) renderer.dispose()
      this.graph = null
    }
  }

  /** Test hook: freeze the sim and render exactly one label frame against the
   *  current camera, so DOM-label geometry can be measured deterministically.
   *  Also cancels the pending grade-mode zoomToFit (which would resume animation
   *  mid-measurement) and disables orbit damping (which lerps the camera over
   *  frames) — without these two, the projector read and the layout read can see
   *  cameras one frame apart and disagree. */
  __test_pauseAndRenderFrame(): void {
    if (!this.graph || !this.labelRenderer) return
    if (this.gradeFrameTimer) {
      clearTimeout(this.gradeFrameTimer)
      this.gradeFrameTimer = null
    }
    const controls = this.graph.controls() as { enableDamping?: boolean } | undefined
    if (controls) controls.enableDamping = false
    this.graph.pauseAnimation()
    this.labelRenderer.render(this.graph.scene() as never, this.graph.camera() as never)
  }

  /** Test hook: the live label `<div>`s in the overlay. */
  __test_labelEls(): HTMLElement[] {
    if (!this.labelRenderer) return []
    return Array.from(this.labelRenderer.domElement.querySelectorAll('.mf-graph-label'))
  }

  /** Test hook: the underlying ForceGraph3D instance, so e2e can call the
   *  library's own projector (`graph2ScreenCoords`) and camera driver
   *  (`cameraPosition`) — the independent code path the position assertion
   *  checks the DOM layout against. */
  get __test_graph(): ForceGraph3DInstance | null {
    return this.graph
  }

  render() {
    return html`<div id="graph-container" style="width:100%;height:100%;touch-action:none;"></div>`
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'mf-force-graph': MfForceGraph
  }
}
