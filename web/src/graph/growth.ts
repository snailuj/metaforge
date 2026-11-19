// Steady graph growth: words that arrive while the graph is on screen grow out of
// their parent while the words already there hold still, so each arrival no longer
// moves the whole layout. Pure decisions over the node objects d3 simulates; the
// functions that place or pin write to those objects, because d3 reads them there.

import type { GraphLink, GraphNode } from './types'
import { resolveEndpoint } from './transform'

/** A node as d3-force leaves it: position, velocity and the fixed position it honours. */
export interface SimNode extends GraphNode {
  vx?: number; vy?: number; vz?: number
  fx?: number; fy?: number; fz?: number
  // Set by the library's drag controls while a node is held by the pointer.
  __initialFixedPos?: { fx?: number; fy?: number; fz?: number }
}

/** Below this speed (units per tick) a node counts as settled. */
export const SETTLED_SPEED = 0.05

/** Width of the cube a newcomer's seed offset falls in: each axis is within half of it. */
export const SEED_SPREAD = 4

const defaultJitter = () => (Math.random() - 0.5) * SEED_SPREAD

/** Nodes this feed adds: an id not fed before, or a node object with no position
 *  yet (a fresh lookup reuses ids with new objects). */
export function arrivals(nodes: readonly SimNode[], fedIds: ReadonlySet<string>): SimNode[] {
  return nodes.filter(n => !fedIds.has(n.id) || n.x === undefined)
}

/**
 * Which placed neighbour each unplaced newcomer grows out of (its parent: the
 * neighbour of lowest order, the first listed on a tie), in the order to seed
 * them: shallowest first, so a chain seeds in one pass. Reads ids, orders and
 * links only; `isPlaced` says where a position exists, so a layout that stores
 * positions in plain arrays can use the same rule. O(nodes + links).
 */
export function seedParents<T extends { id: string; order: number }>(
  newcomers: readonly T[],
  links: readonly GraphLink[],
  nodes: readonly T[],
  isPlaced: (node: T) => boolean,
): Array<{ child: T; parent: T }> {
  const unplaced = new Set(newcomers.filter(n => !isPlaced(n)).map(n => n.id))
  if (unplaced.size === 0) return []
  const byId = new Map(nodes.map(n => [n.id, n]))
  const neighbours = new Map<string, T[]>()
  for (const l of links) {
    const s = resolveEndpoint(l.source)
    const t = resolveEndpoint(l.target)
    for (const [a, b] of [[s, t], [t, s]]) {
      if (!unplaced.has(a)) continue
      const other = byId.get(b)
      if (!other) continue
      const list = neighbours.get(a)
      if (list) list.push(other)
      else neighbours.set(a, [other])
    }
  }
  const seeded = new Set<string>()
  const pairs: Array<{ child: T; parent: T }> = []
  for (const n of [...newcomers].sort((a, b) => a.order - b.order)) {
    if (!unplaced.has(n.id)) continue
    let parent: T | undefined
    for (const m of neighbours.get(n.id) ?? []) {
      if ((isPlaced(m) || seeded.has(m.id)) && (!parent || m.order < parent.order)) parent = m
    }
    if (!parent) continue
    seeded.add(n.id)
    pairs.push({ child: n, parent })
  }
  return pairs
}

/**
 * Start each unplaced newcomer beside its placed neighbour of lowest order (its
 * parent), plus a small offset, so it grows out of it instead of flying in from
 * the origin. Newcomers go shallowest first, so a chain seeds in one pass.
 * O(nodes + links).
 */
export function seedArrivals(
  newcomers: readonly SimNode[],
  links: readonly GraphLink[],
  nodes: readonly SimNode[],
  jitter: () => number = defaultJitter,
): void {
  for (const { child, parent } of seedParents(newcomers, links, nodes, n => n.x !== undefined)) {
    child.x = parent.x! + jitter()
    child.y = (parent.y ?? 0) + jitter()
    child.z = (parent.z ?? 0) + jitter()
  }
}

/** The nodes to hold still while newcomers settle: every one that is not a
 *  newcomer and that `canHold` allows. */
export function settledToHold<T extends { id: string }>(
  nodes: Iterable<T>,
  newcomerIds: ReadonlySet<string>,
  canHold: (node: T) => boolean,
): T[] {
  const out: T[] = []
  for (const n of nodes) if (!newcomerIds.has(n.id) && canHold(n)) out.push(n)
  return out
}

/** Pin every placed node that is not a newcomer and that nothing else has fixed
 *  (a drag, say), at its current position. Returns the ids it pinned. */
export function holdSettled(nodes: readonly SimNode[], newcomerIds: ReadonlySet<string>): Set<string> {
  const free = (n: SimNode) => n.x !== undefined && n.fx === undefined && n.fy === undefined && n.fz === undefined
  const held = new Set<string>()
  for (const n of settledToHold(nodes, newcomerIds, free)) {
    n.fx = n.x
    n.fy = n.y
    n.fz = n.z
    held.add(n.id)
  }
  return held
}

/**
 * Free the nodes `held` names. They had no fixed position before the hold, so
 * they end free even if a drag moved them meanwhile. A node still under the
 * pointer is left to the drag, told to free it at dragend.
 */
export function releaseHeld(nodes: readonly SimNode[], held: ReadonlySet<string>): void {
  for (const n of nodes) {
    if (!held.has(n.id)) continue
    if (n.__initialFixedPos) {
      n.__initialFixedPos.fx = n.__initialFixedPos.fy = n.__initialFixedPos.fz = undefined
      continue
    }
    delete n.fx
    delete n.fy
    delete n.fz
  }
}

/** Release once arrivals have been quiet for `quietMs` and every newcomer has
 *  settled, or after `maxQuietMs` of quiet whatever the newcomers do. */
export function shouldRelease({ now, lastArrivalAt, newcomers, quietMs, maxQuietMs }: {
  now: number
  lastArrivalAt: number
  newcomers: readonly Pick<SimNode, 'vx' | 'vy' | 'vz'>[]
  quietMs: number
  maxQuietMs: number
}): boolean {
  const quiet = now - lastArrivalAt
  if (quiet >= maxQuietMs) return true
  if (quiet < quietMs) return false
  return newcomers.every(n => Math.hypot(n.vx ?? 0, n.vy ?? 0, n.vz ?? 0) < SETTLED_SPEED)
}
