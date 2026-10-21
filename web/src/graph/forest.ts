import type { ForestEndpoint, ForestResponse, ForestRole } from '@/types/api'
import type { GraphData, GraphLink, GraphNode } from './types'

/** The UI marks an endpoint live at this score or above (spec: quality gate). */
export const LIVE_SCORE = 7

export interface ForestNodeInfo {
  role: ForestRole
  forestId: string
  depth: number           // fewest hops from the source along a kept path
  endpointIds: string[]   // kept paths that pass through or end at this node
  live: boolean           // endpoints only
}

/** What a hover, focus or selection points at; it lights every path through it. */
export type ForestTarget =
  | { kind: 'path'; endpointId: string }
  | { kind: 'node'; id: string }                       // forest id
  | { kind: 'link'; source: string; target: string }   // forest ids

interface ForestLinkSpec {
  source: string
  target: string
  grounds: string[]
  endpointIds: string[]
}

/** A forest response, indexed once on arrival. Its node objects are reused by
 *  every composition, so the simulation keeps their positions. */
export interface ForestGraph {
  source: string
  endpoints: ForestEndpoint[]
  info: Map<string, ForestNodeInfo>
  nodes: GraphNode[]
  links: ForestLinkSpec[]
}

/** The forest as placed on one composed graph, keyed by graph node id. */
export interface ForestOverlay {
  byNodeId: Map<string, ForestNodeInfo>
  nodeIdByForestId: Map<string, string>
  forest: ForestGraph  // same object across recompositions of one response
}

export function normaliseWord(word: string): string {
  return word.trim().toLowerCase().replace(/\s+/g, ' ')
}

const linkKey = (source: string, target: string) => JSON.stringify([source, target])

export function forestToGraph(response: ForestResponse): ForestGraph {
  const throughNode = new Map<string, string[]>()
  const throughLink = new Map<string, string[]>()
  const depth = new Map<string, number>()
  for (const e of response.endpoints) {
    e.path.forEach((id, i) => {
      throughNode.set(id, [...(throughNode.get(id) ?? []), e.id])
      depth.set(id, Math.min(depth.get(id) ?? Infinity, i))
      if (i > 0) {
        const key = linkKey(e.path[i - 1], id)
        throughLink.set(key, [...(throughLink.get(key) ?? []), e.id])
      }
    })
  }
  const scores = new Map(response.endpoints.map(e => [e.id, e.score]))

  const info = new Map<string, ForestNodeInfo>()
  const nodes: GraphNode[] = []
  for (const n of response.nodes) {
    const role = n.id === response.source ? 'source' : n.role
    info.set(n.id, {
      role,
      forestId: n.id,
      depth: depth.get(n.id) ?? (role === 'source' ? 0 : 1),
      endpointIds: [...new Set(throughNode.get(n.id) ?? [])],
      live: (scores.get(n.id) ?? 0) >= LIVE_SCORE,
    })
    nodes.push({
      id: n.id,
      word: n.word,
      relationType: role === 'source' ? 'central' : 'metaphor',
      val: 1,
      order: role === 'source' ? 0 : 1,
    })
  }

  const links = response.edges.map(e => ({
    source: e.source,
    target: e.target,
    grounds: e.grounds,
    endpointIds: [...new Set(throughLink.get(linkKey(e.source, e.target)) ?? [])],
  }))

  return { source: response.source, endpoints: response.endpoints, info, nodes, links }
}

/**
 * Overlay a forest on the thesaurus graph. A forest word already on the graph
 * (same normalised word, or same id) becomes that node, so it is never drawn
 * twice. Metaphor links are fresh objects with string ends on every call:
 * d3 swaps string ends for node objects once fed, and a reused link would
 * then point at a node object from an earlier lookup.
 */
export function composeForest(
  thesaurus: GraphData,
  forest: ForestGraph | null,
): { data: GraphData; overlay: ForestOverlay | null } {
  if (!forest) return { data: thesaurus, overlay: null }

  const byWord = new Map<string, GraphNode>()
  const byId = new Map<string, GraphNode>()
  for (const n of thesaurus.nodes) {
    byId.set(n.id, n)
    const w = normaliseWord(n.word)
    if (!byWord.has(w)) byWord.set(w, n)
  }

  const overlay: ForestOverlay = { byNodeId: new Map(), nodeIdByForestId: new Map(), forest }
  const added: GraphNode[] = []
  for (const node of forest.nodes) {
    const match = byWord.get(normaliseWord(node.word)) ?? byId.get(node.id)
    const graphId = match ? match.id : node.id
    if (!match) added.push(node)
    overlay.nodeIdByForestId.set(node.id, graphId)
    overlay.byNodeId.set(graphId, forest.info.get(node.id)!)
  }

  const links: GraphLink[] = forest.links.map(l => ({
    source: overlay.nodeIdByForestId.get(l.source) ?? l.source,
    target: overlay.nodeIdByForestId.get(l.target) ?? l.target,
    relationType: 'metaphor',
    order: 1,
    metaphor: { grounds: l.grounds, endpointIds: l.endpointIds, forestSource: l.source, forestTarget: l.target },
  }))

  return {
    data: { nodes: [...thesaurus.nodes, ...added], links: [...thesaurus.links, ...links] },
    overlay,
  }
}

/** Endpoint ids of every kept path through the target; null when nothing is targeted. */
export function litEndpoints(forest: ForestGraph, target: ForestTarget | null): Set<string> | null {
  if (!target) return null
  switch (target.kind) {
    case 'path':
      return new Set(forest.endpoints.some(e => e.id === target.endpointId) ? [target.endpointId] : [])
    case 'node':
      return new Set(forest.info.get(target.id)?.endpointIds ?? [])
    case 'link': {
      const link = forest.links.find(l => l.source === target.source && l.target === target.target)
      return new Set(link?.endpointIds ?? [])
    }
  }
}

interface SimNode { x?: number; y?: number; z?: number; vx?: number; vy?: number; vz?: number }

interface DepthForceOptions {
  spacing: number     // distance between rings
  offset?: number     // extra radius for every ring, to clear the thesaurus cloud
  strength?: number
  flatten?: number    // 0..1: pull toward the root's z plane, facing the default camera
}

/**
 * A d3 force that pulls each forest node toward a sphere of radius
 * offset + depth * spacing around the depth-0 node, so the forest grows outward
 * from the source in rings instead of tangling into the thesaurus cloud. With
 * `flatten`, the rings also settle toward the plane facing the default camera,
 * so the burst reads at a glance. Nodes with no depth (the thesaurus) are untouched.
 */
export function forestDepthForce<N extends SimNode>(
  depthOf: (node: N) => number | undefined,
  { spacing, offset = 0, strength = 0.08, flatten = 0 }: DepthForceOptions,
) {
  let nodes: N[] = []
  const force = (alpha: number) => {
    const root = nodes.find(n => depthOf(n) === 0)
    if (!root) return
    const rx = root.x ?? 0, ry = root.y ?? 0, rz = root.z ?? 0
    for (const n of nodes) {
      const d = depthOf(n)
      if (!d) continue
      const dx = (n.x ?? 0) - rx, dy = (n.y ?? 0) - ry, dz = (n.z ?? 0) - rz
      const dist = Math.hypot(dx, dy, dz) || 1e-3
      const k = ((offset + d * spacing - dist) / dist) * strength * alpha
      n.vx = (n.vx ?? 0) + dx * k
      n.vy = (n.vy ?? 0) + dy * k
      n.vz = (n.vz ?? 0) + dz * k - dz * flatten * strength * alpha
    }
  }
  force.initialize = (n: N[]) => { nodes = n }
  return force
}
