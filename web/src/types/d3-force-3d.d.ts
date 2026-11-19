// d3-force-3d ships no type declarations. This covers only what the speed
// test's physics wrapper (src/perf/physics.ts) and the growth tests call.
declare module 'd3-force-3d' {
  export interface SimulationNode {
    index?: number
    x?: number
    y?: number
    z?: number
    vx?: number
    vy?: number
    vz?: number
  }

  export interface Force {
    (alpha: number): void
  }

  export interface Simulation<N extends SimulationNode> {
    force(name: string, force: Force | null): this
    velocityDecay(decay: number): this
    alphaDecay(decay: number): this
    alpha(alpha: number): this
    stop(): this
    tick(iterations?: number): this
    nodes(): N[]
  }

  export interface LinkForce extends Force {
    id<D>(fn: (node: D) => string | number): this
    distance(distance: number): this
  }

  export function forceSimulation<N extends SimulationNode>(nodes?: N[], numDimensions?: 1 | 2 | 3): Simulation<N>
  export function forceLink<L extends { source: unknown; target: unknown }>(links?: L[]): LinkForce
  export function forceManyBody(): Force
  export function forceCenter(): Force
}
