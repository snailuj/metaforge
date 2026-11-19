// A fixed synthetic graph for the glow speed test. Seeded, so every device
// draws the same scene and results are comparable across phones.

import { mulberry32 } from '@/lib/random'

export const PILL_COUNT = 12

export interface Scene {
  nodeCount: number
  /** x, y, z per node. */
  positions: Float32Array
  /** Two node indexes per edge. */
  edges: Uint32Array
  labels: string[]
  /** Node indexes drawn as glowing pills. */
  pills: number[]
}

const WORDS = [
  'ember', 'tide', 'lantern', 'harvest', 'anchor', 'whisper', 'thread', 'glacier', 'compass', 'orchard',
  'mirror', 'tempest', 'lull', 'cinder', 'meadow', 'keystone', 'ripple', 'quarry', 'threshold', 'marrow',
  'beacon', 'drift', 'canopy', 'forge', 'hollow', 'sparrow', 'ledger', 'tapestry', 'riddle', 'furrow',
  'zenith', 'bramble', 'current', 'veil', 'sediment', 'kindle', 'horizon', 'pitch', 'garland', 'brink',
  'mosaic', 'tether', 'solstice', 'rift', 'cadence', 'lattice', 'burrow', 'prism', 'dusk', 'weir',
  'flint', 'chorus', 'umbra', 'gossamer', 'plinth', 'fathom', 'wick', 'estuary', 'sinew', 'vestige',
]

const SPREAD = 120

export function buildScene(seed: number, nodeCount: number, edgeCount: number): Scene {
  const rand = mulberry32(seed)
  const positions = new Float32Array(nodeCount * 3)
  for (let i = 0; i < positions.length; i++) positions[i] = (rand() * 2 - 1) * SPREAD

  const edges = new Uint32Array(edgeCount * 2)
  for (let e = 0; e < edgeCount; e++) {
    const a = Math.floor(rand() * nodeCount)
    // Offset by 1..n-1 so an edge never joins a node to itself.
    const b = (a + 1 + Math.floor(rand() * (nodeCount - 1))) % nodeCount
    edges[2 * e] = a
    edges[2 * e + 1] = b
  }

  const labels = Array.from({ length: nodeCount }, (_, i) => WORDS[i % WORDS.length])

  // Partial Fisher-Yates over the indexes picks distinct pills.
  const order = Array.from({ length: nodeCount }, (_, i) => i)
  const pillCount = Math.min(PILL_COUNT, nodeCount)
  for (let i = 0; i < pillCount; i++) {
    const j = i + Math.floor(rand() * (nodeCount - i))
    ;[order[i], order[j]] = [order[j], order[i]]
  }
  return { nodeCount, positions, edges, labels, pills: order.slice(0, pillCount) }
}
