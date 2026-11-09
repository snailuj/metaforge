// Stands in for `three/webgpu`. three-render-objects imports WebGPURenderer for
// an opt-in `useWebGPU` mode that Metaforge never enables; the real module
// pulls three.js's whole WebGPU build (~500 KB minified) into the bundle.
// If anything ever does construct it, fail loudly rather than render nothing.
export class WebGPURenderer {
  constructor() {
    throw new Error('[metaforge] WebGPURenderer is stubbed out of the bundle; see vite.config.ts')
  }
}
