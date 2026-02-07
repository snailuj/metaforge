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
