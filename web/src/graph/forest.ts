import type { ForestEndpoint, ForestResponse, ForestRole } from '@/types/api'
import type { StreamPath } from '@/forest/state'
import type { GraphData, GraphLink, GraphNode, StreamMarkStatus } from './types'

/** The UI marks an endpoint live at this score or above (spec: quality gate). */
export const LIVE_SCORE = 7

export interface ForestNodeInfo {
  role: ForestRole
  forestId: string
  depth: number           // fewest hops from the source along a kept path
  endpointIds: string[]   // kept paths that pass through or end at this node
  live: boolean           // endpoints only
  stream?: StreamMarkStatus  // set only on streamed marks
  fadeUntil?: number
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
  forest: ForestGraph | null  // same object across recompositions of one response; null while only a stream is drawn
}

/** Forest node objects by forest id, kept for one word, so a node keeps its
 *  object (and so its simulated position) from its first streamed hop through
 *  every snapshot. */
export type ForestNodePool = Map<string, GraphNode>

/** How long a streamed mark that no path uses any more takes to fade out. */
export const FOREST_FADE_MS = 600

export interface StreamNodeMark {
  id: string
  parent: string | null   // the node it grows from, for its first position
  depth: number
  role: ForestRole
  live: boolean
  status: StreamMarkStatus
  fadeUntil?: number
}

export interface StreamLinkMark {
  source: string
  target: string
  grounds: string[]
  status: StreamMarkStatus
  fadeUntil?: number
}

/** The marks a stream draws beyond the latest snapshot; links keyed by [source, target]. */
export interface StreamMarks {
  nodes: Map<string, StreamNodeMark>
  links: Map<string, StreamLinkMark>
}

export function normaliseWord(word: string): string {
  return word.trim().toLowerCase().replace(/\s+/g, ' ')
}

const linkKey = (source: string, target: string) => JSON.stringify([source, target])

export function forestToGraph(response: ForestResponse, pool?: ForestNodePool): ForestGraph {
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
    const fields = { word: n.word, relationType: role === 'source' ? 'central' : 'metaphor', val: 1, order: role === 'source' ? 0 : 1 } as const
    const pooled = pool?.get(n.id)
    const node: GraphNode = pooled ? Object.assign(pooled, fields) : { id: n.id, ...fields }
    pool?.set(n.id, node)
    nodes.push(node)
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
  stream?: { marks: StreamMarks; pool: ForestNodePool },
): { data: GraphData; overlay: ForestOverlay | null } {
  if (!forest && !stream?.marks.nodes.size) return { data: thesaurus, overlay: null }

  const byWord = new Map<string, GraphNode>()
  const byId = new Map<string, GraphNode>()
  for (const n of thesaurus.nodes) {
    byId.set(n.id, n)
    const w = normaliseWord(n.word)
    if (!byWord.has(w)) byWord.set(w, n)
  }

  const overlay: ForestOverlay = { byNodeId: new Map(), nodeIdByForestId: new Map(), forest }
  const added: GraphNode[] = []
  for (const node of forest?.nodes ?? []) {
    const match = byWord.get(normaliseWord(node.word)) ?? byId.get(node.id)
    const graphId = match ? match.id : node.id
    if (!match) added.push(node)
    overlay.nodeIdByForestId.set(node.id, graphId)
    overlay.byNodeId.set(graphId, forest!.info.get(node.id)!)
  }

  const streamNodes: Array<[GraphNode, StreamNodeMark]> = []
  for (const m of [...(stream?.marks.nodes.values() ?? [])].sort((a, b) => a.depth - b.depth)) {
    const match = byWord.get(normaliseWord(m.id)) ?? byId.get(m.id)
    let node = match
    if (!node) {
      node = stream!.pool.get(m.id) ?? { id: m.id, word: m.id, relationType: m.depth === 0 ? 'central' : 'metaphor', val: 1, order: m.depth === 0 ? 0 : 1 }
      stream!.pool.set(m.id, node)
      added.push(node)
      streamNodes.push([node, m])
    }
    overlay.nodeIdByForestId.set(m.id, node.id)
    // A thesaurus word that stops being streamed just goes back to the thesaurus.
    if (match && m.status === 'fading') continue
    overlay.byNodeId.set(node.id, {
      role: m.role, forestId: m.id, depth: m.depth, endpointIds: [], live: m.live, stream: m.status, fadeUntil: m.fadeUntil,
    })
  }
  const addedById = new Map(added.map(n => [n.id, n]))
  seedPositions(streamNodes, id => {
    const graphId = overlay.nodeIdByForestId.get(id)
    return graphId === undefined ? undefined : byId.get(graphId) ?? addedById.get(graphId)
  })

  const links: GraphLink[] = (forest?.links ?? []).map(l => ({
    source: overlay.nodeIdByForestId.get(l.source) ?? l.source,
    target: overlay.nodeIdByForestId.get(l.target) ?? l.target,
    relationType: 'metaphor',
    order: 1,
    metaphor: { grounds: l.grounds, endpointIds: l.endpointIds, forestSource: l.source, forestTarget: l.target },
  }))
  for (const l of stream?.marks.links.values() ?? []) {
    const source = overlay.nodeIdByForestId.get(l.source)
    const target = overlay.nodeIdByForestId.get(l.target)
    if (source === undefined || target === undefined) continue
    links.push({
      source, target, relationType: 'metaphor', order: 1,
      metaphor: { grounds: l.grounds, endpointIds: [], forestSource: l.source, forestTarget: l.target, stream: l.status, fadeUntil: l.fadeUntil },
    })
  }

  return {
    data: { nodes: [...thesaurus.nodes, ...added], links: [...thesaurus.links, ...links] },
    overlay,
  }
}

/** A new streamed node starts beside the node it grows from, so the forest
 *  grows outward instead of flying in from the origin. Parents come first
 *  (sorted by depth), so a chain of new nodes seeds in one pass. */
function seedPositions(nodes: Array<[GraphNode, StreamNodeMark]>, nodeOf: (forestId: string) => GraphNode | undefined): void {
  const jitter = () => (Math.random() - 0.5) * 4
  for (const [node, mark] of nodes) {
    if (node.x !== undefined || mark.parent === null) continue
    const parent = nodeOf(mark.parent)
    if (parent?.x === undefined) continue
    node.x = parent.x + jitter()
    node.y = (parent.y ?? 0) + jitter()
    node.z = (parent.z ?? 0) + jitter()
  }
}

const BRANCH_ID = /^(f\d+)b\d+$/

/**
 * The marks a stream adds to the latest snapshot. A node or link is drawn while
 * any pending or kept path uses it; a branch also uses its facet's head hop,
 * which the server sends under the facet's own id. Anything the snapshot
 * already draws is left out, so it is never drawn twice.
 */
export function streamMarks(paths: Readonly<Record<string, StreamPath>>, forest: ForestGraph | null): StreamMarks {
  const nodes = new Map<string, StreamNodeMark>()
  const links = new Map<string, StreamLinkMark>()
  const inSnapshot = new Set(forest?.links.map(l => linkKey(l.source, l.target)) ?? [])

  const markNode = (id: string, parent: string | null, depth: number, status: StreamMarkStatus, endpointScore?: number) => {
    if (forest?.info.has(id)) return
    const prev = nodes.get(id)
    const shallowest = Math.min(prev?.depth ?? depth, depth)
    nodes.set(id, {
      id,
      parent: prev && prev.depth <= depth ? prev.parent : parent,
      depth: shallowest,
      role: shallowest === 0 ? 'source' : endpointScore !== undefined || prev?.role === 'endpoint' ? 'endpoint' : 'hop',
      live: !!prev?.live || (endpointScore ?? 0) >= LIVE_SCORE,
      status: prev?.status === 'kept' ? 'kept' : status,
    })
  }

  for (const p of Object.values(paths)) {
    if (p.status === 'rejected') continue
    const head = BRANCH_ID.exec(p.id)?.[1]
    const hops = [...(head ? paths[head]?.hops ?? [] : []), ...p.hops]
    const status: StreamMarkStatus = p.status === 'kept' ? 'kept' : 'pending'
    const endpoint = p.status === 'kept' ? p.endpoint ?? hops[hops.length - 1]?.to : undefined
    hops.forEach((h, i) => {
      const key = linkKey(h.from, h.to)
      if (!inSnapshot.has(key)) {
        const prev = links.get(key)
        links.set(key, {
          source: h.from,
          target: h.to,
          grounds: prev ? [...new Set([...prev.grounds, h.ground])] : [h.ground],
          status: prev?.status === 'kept' ? 'kept' : status,
        })
      }
      markNode(h.from, i === 0 ? null : hops[i - 1].from, i, status)
      markNode(h.to, h.from, i + 1, status, h.to === endpoint ? p.score ?? 0 : undefined)
    })
  }
  return { nodes, links }
}

/**
 * Carry dropped marks into the next set as fading: a mark that `prev` drew and
 * neither `next` nor the snapshot does fades for `fadeMs` from `now`, then goes.
 * A mark already fading keeps its deadline; `fadeMs` 0 drops marks at once.
 */
export function fadeMarks(prev: StreamMarks, next: StreamMarks, forest: ForestGraph | null, now: number, fadeMs: number): StreamMarks {
  const inSnapshot = new Set(forest?.links.map(l => linkKey(l.source, l.target)) ?? [])
  const carry = <M extends { status: StreamMarkStatus; fadeUntil?: number }>(from: Map<string, M>, into: Map<string, M>, held: (key: string) => boolean) => {
    if (fadeMs <= 0) return
    for (const [key, mark] of from) {
      if (into.has(key) || held(key)) continue
      if (mark.status !== 'fading') into.set(key, { ...mark, status: 'fading', fadeUntil: now + fadeMs })
      else if ((mark.fadeUntil ?? 0) > now) into.set(key, mark)
    }
  }
  const out: StreamMarks = { nodes: new Map(next.nodes), links: new Map(next.links) }
  carry(prev.nodes, out.nodes, id => !!forest?.info.has(id))
  carry(prev.links, out.links, key => inSnapshot.has(key))
  return out
}

/** When the next fading mark is due to go, or null when none is fading. */
export function nextFadeEnd(marks: StreamMarks): number | null {
  let end: number | null = null
  for (const m of [...marks.nodes.values(), ...marks.links.values()]) {
    if (m.status === 'fading' && m.fadeUntil !== undefined && (end === null || m.fadeUntil < end)) end = m.fadeUntil
  }
  return end
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
