import { LitElement, html, css } from 'lit'
import { customElement, property } from 'lit/decorators.js'
import type { PropertyValues } from 'lit'
import ForceGraph3D from '3d-force-graph'
import type { ForceGraph3DInstance } from '3d-force-graph'
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

  @property({ type: Object }) graphData: GraphData = { nodes: [], links: [] }

  protected firstUpdated(): void {
    this.container = this.renderRoot.querySelector('#graph-container') as HTMLDivElement
    if (!this.container) return

    this.graph = ForceGraph3D({ controlType: 'fly' })(this.container)
      .backgroundColor('#1a1a2e')
      .nodeLabel((n: unknown) => (n as GraphNode).word)
      .nodeColor((n: unknown) => NODE_COLOURS[(n as GraphNode).relationType] || '#e8e0d4')
      .nodeVal((n: unknown) => (n as GraphNode).val)
      .nodeOpacity(0.9)
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

    if (this.graphData.nodes.length) {
      this.graph.graphData(this.graphData)
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
