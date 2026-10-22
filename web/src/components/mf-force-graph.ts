import { LitElement, html, css } from 'lit'
import { customElement, property } from 'lit/decorators.js'
import type { PropertyValues } from 'lit'
import ForceGraph3D from '3d-force-graph'
import type { ForceGraph3DInstance } from '3d-force-graph'
import type { GraphData, GraphLink, GraphNode, Rarity } from '@/graph/types'
import { NODE_COLOURS, RARITY_COLOURS, DEFAULT_NODE_COLOUR, FOREST_COLOURS, withAlpha } from '@/graph/colours'
import { makeLabelRenderer, makeLabelObject, makeGroundLabel, syncLabelVisibility, DEFAULT_LABEL_SIZE, type LabelSizeConfig, type LabelStyle, type BacklinkRow } from '@/graph/label-layer'
import { forestDepthForce, FOREST_FADE_MS, type ForestNodeInfo, type ForestOverlay, type ForestTarget } from '@/graph/forest'
import type { ChainRecord, JudgementRecord } from '../types/grading'
import { normaliseJudgement } from '../types/grading'

const EDGE_COLOUR = 'rgba(232, 224, 212, 0.15)'
const EDGE_COLOUR_DIM = 'rgba(232, 224, 212, 0.08)'

// Metaphor forest emphasis. Thesaurus marks recede while a forest is shown so
// the forest reads as the figure; anything off a lit path recedes further.
const FOREST_EDGE_THESAURUS = 'rgba(232, 224, 212, 0.05)'
const FOREST_EDGE_THESAURUS_DIM = 'rgba(232, 224, 212, 0.03)'
const FOREST_NODE_VAL = { endpoint: 18, hop: 1.5 } as const
// Ring 1 sits at offset + spacing from the source, clear of the thesaurus
// cloud (link distance 30); later rings follow at the link distance.
const FOREST_RING = { spacing: 52, offset: 22, strength: 0.08, flatten: 0.6 }
const FOREST_LINK_DISTANCE = FOREST_RING.spacing
// Framing after a new forest lands: once the warm-up has spread it, then
// again as it settles. Padding keeps the burst clear of the side panels.
const FOREST_FRAME_AT_MS = [900, 3200]
const FOREST_FRAME_PADDING = { wide: 110, narrow: 30 }
const LIVE_MARK = '\u2726'
const GROUND_LABEL_AT = 0.36 // along the link, from its source
// Streamed forest: unjudged links flicker like lightning. Each one holds a
// random brightness for a random short spell and sometimes throws a spark.
const STREAM_TICK_MS = 90
const FLICKER_HOLD_MS = { min: 60, max: 260 }
const FLICKER_ALPHA = { min: 0.08, max: 1 }
const FLICKER_SPARK_CHANCE = 0.35
// Reduced motion: a pending link is a still, dotted line (particles that never move).
const STILL_DOTS = 6
const PARTICLE_SPEED = 0.0045
type Emphasis = 'lit' | 'dim' | 'normal'

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
// The label shows the `phrase` (the model's original wording, phrase-first — so
// bad_head display-loss dissolves), falling back to `head` when they coincide.
// `head` is retained as the dedup key and backlink source. A deduped node is
// reached by many chains, each with its own phrase; the originating chain's phrase
// labels the node, and every per-connection phrase still lives in `backlinks`
// (surfaced in the label's hover tooltip).
interface GradeNode {
  id: string
  head: string
  phrase: string
  role: 'topic' | 'vehicle' | 'step'
  backlinks: BacklinkRow[]
}

interface Vec3 { x: number; y: number; z: number }

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
    @media (prefers-reduced-motion: no-preference) {
      .mf-graph-label {
        transition: background 120ms ease;
      }
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
    /* Metaphor forest labels. Colours mirror FOREST_COLOURS; the canvas cannot
       read CSS custom properties, so the tokens live in both places. */
    .mf-graph-label[data-role='forest-endpoint'] {
      background: var(--colour-forest-label-bg) !important;
      border: 1px solid var(--colour-forest-branch-dim);
      border-radius: 999px;
      padding: 1px 8px 2px;
    }
    .mf-graph-label[data-role='forest-endpoint'] .mf-graph-label__text {
      font-size: 14px !important;
      letter-spacing: 0.01em;
    }
    .mf-graph-label__mark {
      color: var(--colour-forest-live, #d4af37);
      margin-inline-end: 4px;
      font-size: 11px;
      vertical-align: 1px;
    }
    /* !important: buildLabelEl sets an inline contrast background. Hops get a
       quieter backing than endpoints (square, faint rule) so links crossing
       them never cut the word; upright, unlike the italic grounds. */
    .mf-graph-label[data-role='forest-hop'] {
      background: var(--colour-forest-label-bg) !important;
      border: 1px solid var(--colour-forest-branch-faint);
      border-radius: 3px;
      padding: 0 5px 1px;
    }
    .mf-graph-label[data-role='forest-hop'] .mf-graph-label__text {
      font-size: 11.5px !important;
      letter-spacing: 0.01em;
    }
    /* The root of the forest: the looked-up word, larger, in a gold ring. */
    .mf-graph-label[data-role='forest-source'] {
      background: var(--colour-forest-root-bg) !important;
      border: 1px solid var(--colour-accent-gold-dim);
      border-radius: 999px;
      padding: 2px 10px 3px;
      box-shadow: 0 0 14px var(--colour-forest-root-glow);
    }
    .mf-graph-label[data-role='forest-source'] .mf-graph-label__text {
      font-size: 17px !important;
    }
    /* CSS2DRenderer re-stacks labels by depth every frame (inline z-index);
       words on a lit path and the root stay above the ground labels. */
    .mf-graph-label[data-lit], .mf-graph-label[data-role='forest-source'] {
      z-index: 100000 !important;
    }
    .mf-graph-label[data-role='forest-endpoint'][data-lit] {
      border-color: var(--colour-forest-spark);
      box-shadow: 0 0 12px var(--colour-forest-glow);
    }
    .mf-graph-label[data-role='forest-hop'][data-lit] {
      background: var(--colour-forest-label-bg-strong) !important;
      border-radius: 3px;
    }
    .mf-graph-label[data-role='forest-hop'][data-lit] .mf-graph-label__text {
      color: var(--colour-forest-endpoint) !important;
      font-size: 12px !important;
    }
    /* A selection is a gold ring a hover never draws, so a click that selects
       or clears it always shows a change. */
    .mf-graph-label[data-selected] {
      outline: 2px solid var(--colour-forest-live);
      outline-offset: 2px;
      border-radius: 999px;
    }
    .mf-graph-label[data-recede] {
      opacity: 0.45;
    }
    .mf-graph-label[data-dim] {
      opacity: 0.18;
    }
    .mf-ground-label {
      visibility: hidden;
      display: flex;
      flex-direction: column;
      align-items: center;
      max-width: 7.5rem;
      padding: 2px 7px 3px;
      border-radius: 3px;
      background: var(--colour-forest-label-bg-strong);
      border-inline-start: 2px solid var(--colour-forest-branch);
      color: var(--colour-forest-ground);
      font-family: var(--font-body, Georgia, serif);
      font-style: italic;
      font-size: 11px;
      line-height: 1.25;
      text-align: center;
      white-space: normal;
    }
    .mf-ground-label[data-lit] {
      visibility: visible;
    }
    /* Streamed words: unjudged ones sit back a little; dropped ones fade out
       (reduced motion removes them at once, so the fade never runs there). */
    .mf-graph-label[data-pending] {
      opacity: 0.75;
    }
    @media (prefers-reduced-motion: no-preference) {
      .mf-graph-label[data-role^='forest'] {
        transition: opacity 160ms ease;
      }
      .mf-graph-label[data-fading] {
        animation: mf-forest-fade 600ms ease-out forwards;
      }
      @keyframes mf-forest-fade {
        from { opacity: 1; }
        to { opacity: 0; }
      }
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
  private reducedMotion = false
  // pointerType of the latest pointer on the canvas; a touch never sets hover.
  private lastPointerType = 'mouse'
  private forestHoverActive = false
  private forestFrameTimers: ReturnType<typeof setTimeout>[] = []
  private streamTimer: ReturnType<typeof setTimeout> | null = null
  // Current flicker brightness of each pending link, keyed by its forest ends.
  private flicker = new Map<string, { alpha: number; until: number }>()

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
  // Metaphor forest overlay (browse mode). graphData already holds the forest
  // nodes and links; this says which nodes play which role.
  @property({ attribute: false }) forest: ForestOverlay | null = null
  // Show on graph. Hiding uses visibility, not a re-feed, so the layout holds.
  @property({ attribute: false }) forestVisible = true
  // Endpoint ids of the paths to light; null lights nothing.
  @property({ attribute: false }) forestLit: ReadonlySet<string> | null = null
  // Forest id of the node whose label carries the selection ring.
  @property({ attribute: false }) forestSelectedId: string | null = null

  // Whether the 3D library should be loaded. Derived from mode + viewportWidth —
  // kept as a getter so Lit never schedules a secondary update cycle from updated().
  // Rendered by the template (controls flat fallback), so changes propagate via
  // the reactive props it depends on (mode, viewportWidth) — no @state needed.
  get threeDLoaded(): boolean {
    return this.mode === 'browse' || this.viewportWidth >= 900
  }

  // --- Metaphor forest ---

  /** The overlay in force: none in grade mode or while hidden. */
  private get activeForest(): ForestOverlay | null {
    return this.mode === 'browse' && this.forestVisible ? this.forest : null
  }

  private forestInfo(n: unknown): ForestNodeInfo | undefined {
    return this.activeForest?.byNodeId.get((n as GraphNode).id)
  }

  private emphasis(pathKeys: string[]): Emphasis {
    if (!this.forestLit || this.forestLit.size === 0) return 'normal'
    return pathKeys.some(id => this.forestLit!.has(id)) ? 'lit' : 'dim'
  }

  /** Share of a fading mark's fade still to run: 1 when it starts, 0 when gone. */
  private fadeLeft(fadeUntil: number | undefined): number {
    return Math.min(1, Math.max(0, ((fadeUntil ?? 0) - performance.now()) / FOREST_FADE_MS))
  }

  private flickerKey(l: GraphLink): string {
    return JSON.stringify([l.metaphor!.forestSource, l.metaphor!.forestTarget])
  }

  private nodeColorFn = (n: unknown): string => {
    if (this.mode === 'grade') return GRADE_NODE_COLOURS[(n as GradeNode).role]
    const node = n as GraphNode
    const base = node.relationType === 'central'
      ? NODE_COLOURS.central
      : RARITY_COLOURS[node.rarity ?? 'unusual'] ?? DEFAULT_NODE_COLOUR
    if (!this.activeForest) return base
    const info = this.forestInfo(node)
    if (!info) return withAlpha(base, this.forestLit ? 0.18 : 0.55)
    if (info.role === 'source') return NODE_COLOURS.central
    const colour = info.role === 'endpoint' ? FOREST_COLOURS.endpoint : FOREST_COLOURS.hop
    if (info.stream === 'fading') return withAlpha(colour, Math.round(this.fadeLeft(info.fadeUntil) * 100) / 100)
    if (info.stream === 'pending') return withAlpha(colour, 0.7)
    return this.emphasis(info.pathKeys) === 'dim' ? withAlpha(colour, 0.22) : colour
  }

  private linkColorFn = (l: unknown): string => {
    if (this.mode === 'grade') {
      const sig = (l as GradeLink).chainSig
      const verdict = this.getEdgeColour(sig)
      const base = GRADE_EDGE_COLOURS[verdict ?? 'ungraded']
      // Whole-path highlight: links sharing the hovered chain glow white.
      return sig === this.hoveredChainSig ? '#ffffff' : base
    }
    const link = l as GraphLink
    if (this.activeForest) {
      if (link.metaphor?.stream === 'pending') {
        return this.reducedMotion
          ? withAlpha(FOREST_COLOURS.branch, 0.45)
          : withAlpha(FOREST_COLOURS.spark, this.flicker.get(this.flickerKey(link))?.alpha ?? FLICKER_ALPHA.max)
      }
      if (link.metaphor?.stream === 'fading') {
        return withAlpha(FOREST_COLOURS.branch, Math.round(0.85 * this.fadeLeft(link.metaphor.fadeUntil) * 100) / 100)
      }
      if (link.metaphor) {
        const e = this.emphasis(link.metaphor.pathKeys)
        return e === 'lit' ? FOREST_COLOURS.spark : withAlpha(FOREST_COLOURS.branch, e === 'dim' ? 0.16 : 0.85)
      }
      return link.order === 2 || this.forestLit ? FOREST_EDGE_THESAURUS_DIM : FOREST_EDGE_THESAURUS
    }
    return link.order === 2 ? EDGE_COLOUR_DIM : EDGE_COLOUR
  }

  private particleCountFn = (l: unknown): number => {
    const link = l as GraphLink
    if (!this.activeForest || !link.metaphor) return 0
    if (link.metaphor.stream === 'pending') return this.reducedMotion ? STILL_DOTS : 0
    if (this.reducedMotion || link.metaphor.stream === 'fading') return 0
    const e = this.emphasis(link.metaphor.pathKeys)
    return e === 'lit' ? 4 : e === 'dim' ? 0 : 2
  }

  private particleSpeedFn = (l: unknown): number =>
    this.reducedMotion && (l as GraphLink).metaphor?.stream === 'pending' ? 0 : PARTICLE_SPEED

  private linkWidthFn = (l: unknown): number => {
    if (this.mode === 'grade') return (l as GradeLink).chainSig === this.hoveredChainSig ? 3 : 1.5
    const link = l as GraphLink
    if (!link.metaphor) return link.order === 2 ? 0.5 : 1
    return this.activeForest && this.emphasis(link.metaphor.pathKeys) === 'lit' ? 2.4 : 1.1
  }

  private arrowLengthFn = (l: unknown): number =>
    this.reducedMotion && this.activeForest && (l as GraphLink).metaphor ? 3.5 : 0

  private groundLabelFn = (l: unknown) => {
    const link = l as GraphLink
    if (this.mode !== 'browse' || !link.metaphor) return null
    const obj = makeGroundLabel(link.metaphor.grounds)
    if (this.activeForest && this.emphasis(link.metaphor.pathKeys) === 'lit') obj.element.setAttribute('data-lit', '')
    return obj
  }

  private nodeLabelFn = (n: unknown) => {
    const obj = makeLabelObject(this.labelStyleFor(n), () => this.effectiveLabelSize, () => this.labelRefDist)
    this.applyLabelFade(obj.element, n)
    return obj
  }

  /** Thesaurus labels recede while a forest is shown; labels on a lit path
   *  light up and everything else dims. */
  private labelFade(n: unknown): 'recede' | 'dim' | 'lit' | null {
    if (!this.activeForest) return null
    const info = this.forestInfo(n)
    if (!info) return (n as GraphNode).relationType === 'central' ? null : this.forestLit ? 'dim' : 'recede'
    if (info.role === 'source') return null
    const e = this.emphasis(info.pathKeys)
    return e === 'normal' ? null : e
  }

  private applyLabelFade(el: HTMLElement, n: unknown): void {
    const fade = this.labelFade(n)
    el.toggleAttribute('data-recede', fade === 'recede')
    el.toggleAttribute('data-dim', fade === 'dim')
    el.toggleAttribute('data-lit', fade === 'lit')
    const info = this.activeForest && this.forestSelectedId ? this.forestInfo(n) : undefined
    el.toggleAttribute('data-selected', !!info && info.forestId === this.forestSelectedId)
    const stream = this.forestInfo(n)?.stream
    el.toggleAttribute('data-pending', stream === 'pending')
    el.toggleAttribute('data-fading', stream === 'fading')
    // A label rebuilt mid-fade picks the fade up where it was.
    el.style.animationDelay = stream === 'fading'
      ? `${-Math.round((1 - this.fadeLeft(this.forestInfo(n)?.fadeUntil)) * FOREST_FADE_MS)}ms`
      : ''
  }

  /** Run the stream animation while any streamed link is pending or fading,
   *  and stop it when none is. Reduced motion never animates. */
  private syncStreamAnimation(): void {
    const animate = !!this.graph && !this.reducedMotion && !!this.activeForest &&
      this.graphData.links.some(l => l.metaphor?.stream === 'pending' || l.metaphor?.stream === 'fading')
    if (animate && !this.streamTimer) this.streamTimer = setTimeout(this.tickStream, STREAM_TICK_MS)
    if (!animate && this.streamTimer) {
      clearTimeout(this.streamTimer)
      this.streamTimer = null
    }
  }

  /** One animation step: new flicker spells and sparks for pending links, and
   *  the next fade step. Colour accessors only, so the simulation is untouched. */
  private tickStream = (): void => {
    this.streamTimer = null
    if (!this.graph || !this.activeForest) return
    const now = performance.now()
    const flicker = new Map<string, { alpha: number; until: number }>()
    let more = false
    for (const l of this.graphData.links) {
      const m = l.metaphor
      if (m?.stream === 'pending') {
        more = true
        const key = this.flickerKey(l)
        let spell = this.flicker.get(key)
        if (!spell || now >= spell.until) {
          spell = {
            alpha: Math.round((FLICKER_ALPHA.min + Math.random() * (FLICKER_ALPHA.max - FLICKER_ALPHA.min)) * 100) / 100,
            until: now + FLICKER_HOLD_MS.min + Math.random() * (FLICKER_HOLD_MS.max - FLICKER_HOLD_MS.min),
          }
          if (Math.random() < FLICKER_SPARK_CHANCE) this.graph.emitParticle(l)
        }
        flicker.set(key, spell)
      } else if (m?.stream === 'fading' && (m.fadeUntil ?? 0) > now) {
        more = true
      }
    }
    this.flicker = flicker
    this.graph.linkColor(this.linkColorFn).nodeColor(this.nodeColorFn)
    if (more) this.streamTimer = setTimeout(this.tickStream, STREAM_TICK_MS)
  }

  /** Frame the whole graph a moment after a new forest lands, so the burst
   *  is on screen however far it grew. */
  private scheduleForestFraming(): void {
    this.forestFrameTimers.forEach(clearTimeout)
    const padding = this.viewportWidth > 768 ? FOREST_FRAME_PADDING.wide : FOREST_FRAME_PADDING.narrow
    this.forestFrameTimers = FOREST_FRAME_AT_MS.map(ms => setTimeout(() => {
      this.graph?.zoomToFit(this.reducedMotion ? 0 : 800, padding)
    }, ms))
  }

  private emitForest(name: 'mf-forest-hover' | 'mf-forest-select', target: ForestTarget | null): void {
    this.dispatchEvent(new CustomEvent(name, { detail: { target }, bubbles: true, composed: true }))
  }

  private forestTargetForLink(l: unknown): ForestTarget | null {
    const m = (l as GraphLink | null)?.metaphor
    return m ? { kind: 'link', source: m.forestSource, target: m.forestTarget } : null
  }

  private setForestHover(target: ForestTarget | null): void {
    if (target && this.lastPointerType === 'touch') return
    if (!target && !this.forestHoverActive) return
    this.forestHoverActive = !!target
    this.emitForest('mf-forest-hover', target)
  }

  /** Re-evaluate forest styling in place: colours, particles and label DOM.
   *  Never graphData(), so the simulation does not re-heat. */
  private refreshForestStyles(): void {
    if (!this.graph) return
    this.graph
      .nodeColor(this.nodeColorFn)
      .linkColor(this.linkColorFn)
      // Re-setting the width rebuilds link objects, ground labels included;
      // they are born with the current lit state.
      .linkWidth(this.linkWidthFn)
      .linkDirectionalParticles(this.particleCountFn)
      .linkDirectionalArrowLength(this.arrowLengthFn)
    this.syncForestLabels()
  }

  /** Mirror the lit set onto label DOM: grounds show on lit links, labels off
   *  every lit path dim. Objects created later read the same rules at birth. */
  private syncForestLabels(): void {
    if (!this.graph) return
    const data = this.graph.graphData() as unknown as {
      nodes?: Array<{ __threeObj?: { children?: Array<{ isCSS2DObject?: boolean; element: HTMLElement }> } }>
      links?: Array<GraphLink & { __lineObj?: { children?: Array<{ isCSS2DObject?: boolean; element: HTMLElement }> } }>
    }
    // graphData() is library-owned and may be unpopulated; same guard as reapplyVisibility.
    for (const n of Array.isArray(data.nodes) ? data.nodes : []) {
      const label = n.__threeObj?.children?.find(c => c.isCSS2DObject)
      if (label) this.applyLabelFade(label.element, n)
    }
    for (const l of Array.isArray(data.links) ? data.links : []) {
      const ground = l.metaphor && l.__lineObj?.children?.find(c => c?.isCSS2DObject)
      if (ground) ground.element.toggleAttribute('data-lit', !!this.activeForest && this.emphasis(l.metaphor!.pathKeys) === 'lit')
    }
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
          nodes.set(id, { id, head: step.head, phrase: step.phrase, role, backlinks: [] })
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
    // Forest-only words hide with the forest; forest words skip the rarity filter.
    if (node.relationType === 'metaphor') return !!this.activeForest
    if (node.relationType === 'central' || this.forestInfo(node)) return true
    const rarity = node.rarity ?? 'unusual'
    return !this.hiddenRarities.has(rarity)
  }

  private isLinkVisible = (l: unknown): boolean => {
    if (this.mode === 'grade') {
      return this.pathFilterPasses((l as GradeLink).chainSig)
    }
    const link = l as { source: unknown; target: unknown; metaphor?: unknown }
    if (link.metaphor && !this.activeForest) return false
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
      return { text: gn.phrase || gn.head, colour: GRADE_NODE_COLOURS[gn.role], role: gn.role, backlinks: gn.backlinks }
    }
    const node = n as GraphNode
    const info = this.forestInfo(node)
    if (info?.role === 'source') return { text: node.word, colour: NODE_COLOURS.central, role: 'forest-source' }
    if (info) {
      return info.role === 'endpoint'
        ? { text: node.word, colour: FOREST_COLOURS.endpoint, role: 'forest-endpoint', mark: info.live ? LIVE_MARK : undefined }
        : { text: node.word, colour: FOREST_COLOURS.hopLabel, role: 'forest-hop' }
    }
    const colour = node.relationType === 'central'
      ? NODE_COLOURS.central
      : RARITY_COLOURS[node.rarity ?? 'unusual'] ?? DEFAULT_NODE_COLOUR
    return { text: node.word, colour, role: node.relationType === 'central' ? 'central' : (node.rarity ?? 'unusual') }
  }

  protected firstUpdated(): void {
    this.container = this.renderRoot.querySelector('#graph-container') as HTMLDivElement
    if (!this.container) return

    this.reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
    // Remember the input type so a tap (which three reports as a hover) never
    // leaves a path lit after the finger lifts.
    const notePointer = (e: Event) => { this.lastPointerType = (e as PointerEvent).pointerType || 'mouse' }
    this.container.addEventListener('pointerdown', notePointer, { capture: true })
    this.container.addEventListener('pointermove', notePointer, { capture: true })

    this.labelRenderer = makeLabelRenderer(this.container.clientWidth, this.container.clientHeight)
    this.graph = ForceGraph3D({ controlType: 'orbit', extraRenderers: [this.labelRenderer] })(this.container)
      .backgroundColor('#1a1a2e')
      // The library's hover tooltips render HTML. Forest words are model text,
      // so they stay off: the default reads a `name` field, which must never become markup.
      .nodeLabel(() => '')
      .linkLabel(() => '')
      .nodeColor(this.nodeColorFn)
      .nodeVal((n: unknown) => {
        if (this.mode === 'grade') return GRADE_NODE_VAL[(n as GradeNode).role]
        const role = this.forestInfo(n)?.role
        return role === 'endpoint' || role === 'hop' ? FOREST_NODE_VAL[role] : (n as GraphNode).val
      })
      .nodeOpacity(0.9)
      .nodeRelSize(0.5)
      .nodeThreeObjectExtend(true)
      .nodeThreeObject(this.nodeLabelFn)
      .d3VelocityDecay(0.85)
      .d3AlphaDecay(0.005)
      .cooldownTime(30000)
      .warmupTicks(50)
      .linkColor(this.linkColorFn)
      .linkWidth(this.linkWidthFn)
      .linkOpacity(0.6)
      // Metaphor forest: sparks flow source to target, which the transform
      // orients from the source word outward along each path.
      .linkDirectionalParticles(this.particleCountFn)
      .linkDirectionalParticleSpeed(this.particleSpeedFn)
      .linkDirectionalParticleWidth(2.2)
      .linkDirectionalParticleColor(() => FOREST_COLOURS.spark)
      .linkDirectionalArrowLength(this.arrowLengthFn)
      .linkDirectionalArrowRelPos(0.92)
      .linkDirectionalArrowColor(() => FOREST_COLOURS.branch)
      .linkThreeObjectExtend(true)
      .linkThreeObject(this.groundLabelFn)
      .linkPositionUpdate((obj: unknown, ends: { start: Vec3; end: Vec3 }) => {
        const label = obj as { isCSS2DObject?: boolean; position: { set(x: number, y: number, z: number): void } } | undefined
        if (label?.isCSS2DObject) {
          // Nearer the parent: the child's own label sits just above the child.
          const { start, end } = ends
          const t = GROUND_LABEL_AT
          label.position.set(start.x + (end.x - start.x) * t, start.y + (end.y - start.y) * t, start.z + (end.z - start.z) * t)
        }
        return false
      })
      .onBackgroundClick(() => {
        if (this.activeForest) this.emitForest('mf-forest-select', null)
      })
      .onLinkHover((l: unknown) => {
        if (this.mode !== 'grade') {
          if (this.activeForest) this.setForestHover(this.forestTargetForLink(l))
          return
        }
        const sig = l ? (l as GradeLink).chainSig : null
        if (sig !== this.hoveredChainSig) {
          this.hoveredChainSig = sig
          this.refreshLinkStyles()
        }
        if (this.container) this.container.style.cursor = l ? 'pointer' : 'default'
      })
      .onLinkClick((l: unknown) => {
        if (this.mode !== 'grade') {
          const target = this.activeForest && this.forestTargetForLink(l)
          if (target) this.emitForest('mf-forest-select', target)
          return
        }
        if (!l) return
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
        const node = n as GraphNode
        const info = this.forestInfo(node)
        // A forest word is drawn as part of the forest, so it behaves as one:
        // single click selects its paths, double-click navigates, never expands.
        if (info) {
          if (this.clickTimer) {
            clearTimeout(this.clickTimer)
            this.clickTimer = null
            this.dispatchEvent(new CustomEvent('mf-node-navigate', { detail: node, bubbles: true, composed: true }))
          } else {
            this.clickTimer = setTimeout(() => {
              this.clickTimer = null
              this.emitForest('mf-forest-select', { kind: 'node', id: info.forestId })
            }, DBLCLICK_THRESHOLD_MS)
          }
          return
        }
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
        if (this.activeForest) {
          const info = node ? this.forestInfo(node) : undefined
          this.setForestHover(info ? { kind: 'node', id: info.forestId } : null)
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

    // Browse mode: metaphor links are a little longer than thesaurus links, and
    // the depth force rings the forest around the source.
    if (this.mode === 'browse' && this.graph) {
      const isMetaphor = (l: unknown) => !!(l as GraphLink).metaphor
      this.graph.d3Force('link')?.distance?.((l: unknown) => (isMetaphor(l) ? FOREST_LINK_DISTANCE : 30))
      this.graph.d3Force('forestDepth', forestDepthForce(
        (node: object) => this.forestInfo(node)?.depth,
        FOREST_RING,
      ))
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
    this.graph.linkColor(this.linkColorFn).linkWidth(this.linkWidthFn)
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
    // A new or hidden forest changes node roles: rebuild labels (node objects
    // are reused across feeds, so their labels would keep the old role) and
    // re-evaluate styling and visibility in place.
    const forestChanged = changed.has('forest') || changed.has('forestVisible')
    const previous = changed.get('forest') as ForestOverlay | null | undefined
    // A stream with no snapshot yet has no forest to frame; the first snapshot frames it.
    if (this.graph && changed.has('forest') && this.forest?.forest && this.forest.forest !== previous?.forest) {
      this.scheduleForestFraming()
    }
    if (this.graph && forestChanged) {
      this.graph.nodeThreeObject((n: unknown) => this.nodeLabelFn(n))
      this.refreshForestStyles()
      this.reapplyVisibility()
    } else if (this.graph && changed.has('forestLit')) {
      this.refreshForestStyles()
    } else if (this.graph && changed.has('forestSelectedId')) {
      this.syncForestLabels()
    }
    // Topology-affecting changes need a full re-feed (which restarts the sim):
    // the browse graph, the mode, or the grade chains.
    const topologyChanged =
      changed.has('graphData') || changed.has('mode') || changed.has('gradeChains')
    if (this.graph && topologyChanged) {
      this.feedGraph()
    } else if (this.graph && changed.has('judgements')) {
      // A verdict changed but the node/link set did not. Edge colour rides the
      // linkColor accessor (getEdgeColour reads the latestVerdicts getter) and
      // the path filter reads the same getter — so re-evaluating styles +
      // visibility in place reflects the new verdict WITHOUT graphData(), and the
      // force sim never re-heats. Under 'ungraded' this also hides the graded path.
      this.refreshLinkStyles()
      this.reapplyVisibility()
    }
    // Both visibility filters toggle ALREADY-FED objects in place — they never
    // re-feed, so the force sim does not re-heat and the layout stays put.
    // grade-mode 'pathFilter' and browse-mode 'hiddenRarities' share this path.
    if ((changed.has('pathFilter') || changed.has('hiddenRarities')) && this.graph) {
      this.reapplyVisibility()
    }
    if (forestChanged || topologyChanged) this.syncStreamAnimation()
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
    this.forestFrameTimers.forEach(clearTimeout)
    if (this.streamTimer) clearTimeout(this.streamTimer)
    this.streamTimer = null
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
