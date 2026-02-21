import { LitElement, html, css } from 'lit'
import { customElement, property } from 'lit/decorators.js'
import type { PropertyValues } from 'lit'
import ForceGraph3D from '3d-force-graph'
import type { ForceGraph3DInstance } from '3d-force-graph'
import SpriteText from 'three-spritetext'
import type { GraphData, GraphLink, GraphNode, Rarity } from '@/graph/types'
import { NODE_COLOURS, RARITY_COLOURS, DEFAULT_NODE_COLOUR } from '@/graph/colours'

const EDGE_COLOUR = 'rgba(232, 224, 212, 0.15)'
const EDGE_COLOUR_DIM = 'rgba(232, 224, 212, 0.08)'
const LABEL_FONT = 'Georgia, "Times New Roman", serif'

// 300ms matches typical OS double-click threshold; balances responsiveness
// with avoiding false double-click detection on slower clickers
const DBLCLICK_THRESHOLD_MS = 300

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
  `

  private graph: ForceGraph3DInstance | null = null
  private container: HTMLDivElement | null = null
  private clickTimer: ReturnType<typeof setTimeout> | null = null
  private resizeObserver: ResizeObserver | null = null
  private previousHoveredNode: GraphNode | null = null

  @property({ type: Object }) graphData: GraphData = { nodes: [], links: [] }
  @property({ type: Object }) hiddenRarities: Set<Rarity> = new Set()

  private isNodeVisible = (n: unknown): boolean => {
    const node = n as GraphNode
    if (node.relationType === 'central') return true
    const rarity = node.rarity ?? 'unusual'
    return !this.hiddenRarities.has(rarity)
  }

  private isLinkVisible = (l: unknown): boolean => {
    const link = l as { source: unknown; target: unknown }
    return this.isNodeVisible(link.source) && this.isNodeVisible(link.target)
  }

  protected firstUpdated(): void {
    this.container = this.renderRoot.querySelector('#graph-container') as HTMLDivElement
    if (!this.container) return

    this.graph = ForceGraph3D({ controlType: 'orbit' })(this.container)
      .backgroundColor('#1a1a2e')
      .nodeColor((n: unknown) => {
        const node = n as GraphNode
        if (node.relationType === 'central') return NODE_COLOURS.central
        return RARITY_COLOURS[node.rarity ?? 'unusual'] ?? DEFAULT_NODE_COLOUR
      })
      .nodeVal((n: unknown) => (n as GraphNode).val)
      .nodeOpacity(0.9)
      .nodeRelSize(0.5)
      .nodeThreeObjectExtend(true)
      .nodeThreeObject((n: unknown) => {
        const node = n as GraphNode
        const colour = node.relationType === 'central'
          ? NODE_COLOURS.central
          : RARITY_COLOURS[node.rarity ?? 'unusual'] ?? DEFAULT_NODE_COLOUR
        const fontSize = node.order === 2 ? 2 : 3
        const sprite = new SpriteText(node.word, fontSize, colour)
        sprite.fontFace = LABEL_FONT
        sprite.backgroundColor = false
        sprite.material.transparent = true
        sprite.material.depthWrite = false
        sprite.padding = [0.5, 2]
        sprite.position.y = 2
        return sprite
      })
      .d3VelocityDecay(0.85)
      .d3AlphaDecay(0.005)
      .cooldownTime(30000)
      .warmupTicks(50)
      .linkColor((l: unknown) => (l as GraphLink).order === 2 ? EDGE_COLOUR_DIM : EDGE_COLOUR)
      .linkWidth((l: unknown) => (l as GraphLink).order === 2 ? 0.5 : 1)
      .linkOpacity(0.6)
      .onNodeClick((n: unknown) => {
        const node = n as GraphNode
        if (node.order === 2) return
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
          this.setNodeHoverBorder(this.previousHoveredNode, false)
        }
        if (node) {
          this.setNodeHoverBorder(node, true)
        }
        this.previousHoveredNode = node
      })

    // Sync renderer dimensions to actual container size (fixes hit-test offset)
    requestAnimationFrame(() => {
      this.syncDimensions()

      if (this.graph) {
        // Pull camera 35% closer than the default starting distance
        const camera = this.graph.camera() as { position: { z: number } }
        camera.position.z *= 0.65

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

    if (this.graphData.nodes.length) {
      this.graph.graphData(this.graphData)
    }
  }

  /** Toggle rounded-rectangle border on the SpriteText label for hover feedback */
  private setNodeHoverBorder(node: GraphNode, hover: boolean): void {
    type SpriteLike = {
      isSprite?: boolean
      borderWidth: number
      borderRadius: number
      borderColor: string
      backgroundColor: string | false
    }
    type ObjLike = { children?: SpriteLike[] }
    const threeObj = (node as unknown as { __threeObj?: ObjLike }).__threeObj
    if (!threeObj) return
    const sprite = threeObj.children?.find(c => c.isSprite)
    if (!sprite) return

    if (hover) {
      const colour = node.relationType === 'central'
        ? NODE_COLOURS.central
        : RARITY_COLOURS[node.rarity ?? 'unusual'] ?? DEFAULT_NODE_COLOUR
      sprite.borderWidth = 0.15
      sprite.borderRadius = 0.3
      sprite.borderColor = colour
      sprite.backgroundColor = 'rgba(0, 0, 0, 0.2)'
    } else if (sprite.borderWidth !== 0) {
      sprite.borderWidth = 0
      sprite.backgroundColor = false
    }
  }

  private syncDimensions() {
    if (!this.container || !this.graph) return
    const { clientWidth, clientHeight } = this.container
    if (clientWidth > 0 && clientHeight > 0) {
      this.graph.width(clientWidth).height(clientHeight)
    }
  }

  updated(changed: PropertyValues<this>): void {
    if (changed.has('graphData') && this.graph) {
      this.graph.graphData(this.graphData)
    }
    if (changed.has('hiddenRarities') && this.graph) {
      this.graph.nodeVisibility(this.isNodeVisible)
      this.graph.linkVisibility(this.isLinkVisible)
    }
  }

  disconnectedCallback(): void {
    super.disconnectedCallback()
    if (this.clickTimer) clearTimeout(this.clickTimer)
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

  render() {
    return html`<div id="graph-container" style="width:100%;height:100%;touch-action:none;"></div>`
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'mf-force-graph': MfForceGraph
  }
}
