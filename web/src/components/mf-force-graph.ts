import { LitElement, html, css } from 'lit'
import { customElement, property } from 'lit/decorators.js'
import type { PropertyValues } from 'lit'
import ForceGraph3D from '3d-force-graph'
import type { ForceGraph3DInstance } from '3d-force-graph'
import SpriteText from 'three-spritetext'
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
const LABEL_FONT = 'Georgia, "Times New Roman", serif'

const DBLCLICK_THRESHOLD_MS = 200

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

  private graph: ForceGraph3DInstance | null = null
  private container: HTMLDivElement | null = null
  private clickTimer: ReturnType<typeof setTimeout> | null = null
  private resizeObserver: ResizeObserver | null = null

  @property({ type: Object }) graphData: GraphData = { nodes: [], links: [] }

  protected firstUpdated(): void {
    this.container = this.renderRoot.querySelector('#graph-container') as HTMLDivElement
    if (!this.container) return

    this.graph = ForceGraph3D({ controlType: 'fly' })(this.container)
      .backgroundColor('#1a1a2e')
      .nodeColor((n: unknown) => NODE_COLOURS[(n as GraphNode).relationType] || '#e8e0d4')
      .nodeVal((n: unknown) => (n as GraphNode).val)
      .nodeOpacity(0.9)
      .nodeRelSize(0.5)
      .nodeThreeObjectExtend(true)
      .nodeThreeObject((n: unknown) => {
        const node = n as GraphNode
        const colour = NODE_COLOURS[node.relationType] || '#e8e0d4'
        const sprite = new SpriteText(node.word, 3, colour)
        sprite.fontFace = LABEL_FONT
        sprite.backgroundColor = false as unknown as string
        sprite.position.y = 3
        return sprite
      })
      .d3VelocityDecay(0.85)
      .d3AlphaDecay(0.005)
      .cooldownTime(30000)
      .warmupTicks(50)
      .linkColor(() => EDGE_COLOUR)
      .linkWidth(1)
      .linkOpacity(0.6)
      .onNodeClick((n: unknown) => {
        const node = n as GraphNode
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
      })

    // Sync renderer dimensions to actual container size (fixes hit-test offset)
    requestAnimationFrame(() => this.syncDimensions())

    this.resizeObserver = new ResizeObserver(() => this.syncDimensions())
    this.resizeObserver.observe(this.container)

    if (this.graphData.nodes.length) {
      this.graph.graphData(this.graphData)
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
    if (changed.has('graphData') && this.graph && this.graphData.nodes.length) {
      this.graph.graphData(this.graphData)
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
    return html`<div id="graph-container" style="width:100%;height:100%;"></div>`
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'mf-force-graph': MfForceGraph
  }
}
