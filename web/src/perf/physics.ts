import { forceSimulation, forceLink, forceManyBody, forceCenter, type SimulationNode } from 'd3-force-3d'
import type { Scene } from './scene'

// The app's layout settings (3 dimensions, velocity decay 0.85, link distance
// 30, default charge and centre) with alpha held at 0.3, so every tick costs
// what a busy moment in the real graph costs.

export const HELD_ALPHA = 0.3

export interface Physics {
  tick(): void
  /** Same work as `count` calls to `tick`; lets a caller time a batch. */
  tickMany(count: number): void
  /** Writes x, y, z per node into `out`. */
  writePositions(out: Float32Array): void
}

export function createPhysics(scene: Scene): Physics {
  const nodes: SimulationNode[] = Array.from({ length: scene.nodeCount }, (_, i) => ({
    x: scene.positions[3 * i],
    y: scene.positions[3 * i + 1],
    z: scene.positions[3 * i + 2],
  }))
  const links = Array.from({ length: scene.edges.length / 2 }, (_, e) => ({
    source: scene.edges[2 * e],
    target: scene.edges[2 * e + 1],
  }))
  const sim = forceSimulation(nodes, 3)
    .force('link', forceLink(links).distance(30))
    .force('charge', forceManyBody())
    .force('center', forceCenter())
    .velocityDecay(0.85)
    .alphaDecay(0)
    .alpha(HELD_ALPHA)
    .stop()

  return {
    tick() {
      sim.tick()
    },
    tickMany(count) {
      for (let i = 0; i < count; i++) sim.tick()
    },
    writePositions(out) {
      for (let i = 0; i < nodes.length; i++) {
        out[3 * i] = nodes[i].x ?? 0
        out[3 * i + 1] = nodes[i].y ?? 0
        out[3 * i + 2] = nodes[i].z ?? 0
      }
    },
  }
}
