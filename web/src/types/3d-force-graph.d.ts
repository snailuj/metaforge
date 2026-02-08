declare module '3d-force-graph' {
  export interface ForceGraph3DInstance {
    backgroundColor(colour: string): ForceGraph3DInstance
    nodeLabel(fn: (node: unknown) => string): ForceGraph3DInstance
    nodeColor(fn: (node: unknown) => string): ForceGraph3DInstance
    nodeVal(fn: (node: unknown) => number): ForceGraph3DInstance
    nodeOpacity(opacity: number): ForceGraph3DInstance
    linkColor(fn: () => string): ForceGraph3DInstance
    linkWidth(width: number): ForceGraph3DInstance
    linkOpacity(opacity: number): ForceGraph3DInstance
    onNodeClick(fn: (node: unknown, event: MouseEvent) => void): ForceGraph3DInstance
    onNodeRightClick(fn: (node: unknown, event: MouseEvent) => void): ForceGraph3DInstance
    onNodeHover(fn: (node: unknown | null) => void): ForceGraph3DInstance
    graphData(data?: { nodes: unknown[]; links: unknown[] }): ForceGraph3DInstance
    pauseAnimation(): ForceGraph3DInstance
    resumeAnimation(): ForceGraph3DInstance
    renderer(): { dispose(): void } | undefined
    scene(): unknown
    camera(): unknown
    controls(): unknown
  }

  function ForceGraph3D(
    options?: { controlType?: string },
  ): (container: HTMLElement) => ForceGraph3DInstance

  export default ForceGraph3D
}
