/**
 * Module augmentation for 3d-force-graph.
 *
 * The library's TypeScript definitions lose accessor overloads for several
 * methods because the `3d-force-graph` wrapper uses
 * `Omit<ThreeForceGraphGeneric<...>, ...>` to inherit methods, and
 * TypeScript's `Omit` collapses method overloads so the setter signatures
 * that accept accessor functions are lost.
 *
 * This augmentation adds back the missing setter overloads with our concrete
 * node/link types, eliminating the need for `as unknown` double-casts.
 *
 * NOTE: nodeOpacity is intentionally NOT augmented here. The runtime uses
 * `state.nodeOpacity * colorAlpha` (direct multiplication), so only a
 * static number works — a function would produce NaN.
 */

import type { GraphLink } from '@/graph/types'

declare module '3d-force-graph' {
  interface ForceGraph3DInstance {
    showNavInfo(show: boolean): ForceGraph3DInstance
    linkColor(accessor: (link: GraphLink) => string): ForceGraph3DInstance
    linkWidth(accessor: (link: GraphLink) => number): ForceGraph3DInstance
  }
}
