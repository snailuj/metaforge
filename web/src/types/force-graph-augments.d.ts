/**
 * Module augmentation for 3d-force-graph.
 *
 * The library's TypeScript definitions are missing or lose accessor overloads
 * for several methods:
 *
 * - nodeOpacity: `three-forcegraph` only declares `number`, but the runtime
 *   accepts `(node) => number` like every other node accessor.
 *
 * - linkColor, linkWidth: `three-forcegraph` correctly types these with
 *   `LinkAccessor<T, N, L>` (value or function), but the `3d-force-graph`
 *   wrapper uses `Omit<ThreeForceGraphGeneric<...>, ...>` to inherit methods.
 *   TypeScript's `Omit` collapses method overloads, so the setter signatures
 *   that accept accessor functions are lost.
 *
 * This augmentation adds back the missing setter overloads with our concrete
 * node/link types, eliminating the need for `as unknown` double-casts.
 */

import type { GraphNode } from '@/graph/types'
import type { GraphLink } from '@/graph/types'

declare module '3d-force-graph' {
  interface ForceGraph3DInstance {
    nodeOpacity(accessor: (node: GraphNode) => number): ForceGraph3DInstance
    linkColor(accessor: (link: GraphLink) => string): ForceGraph3DInstance
    linkWidth(accessor: (link: GraphLink) => number): ForceGraph3DInstance
  }
}
