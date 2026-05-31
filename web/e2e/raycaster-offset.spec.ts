import { test } from '@playwright/test'
import { writeFileSync } from 'node:fs'

// Task 11 — DIAGNOSTIC, not a pass/fail gate. Measures the long-reported
// raycaster hit-test offset (browse mode: the report is that you must point
// roughly one item-height *away* from a node for the hover to register).
//
// Research hypothesis (medium confidence): a devicePixelRatio mismatch in
// three-render-objects' pointer→NDC mapping — the WebGL canvas does
// setPixelRatio(min(2, dPR)) (drawing-buffer px) but the pointer position is
// divided by state.width, which is CSS px (set via graph.width(clientWidth)).
// If those two used different units the hit point would drift, and the drift
// would SCALE with dPR.
//
// We measure two ways, at deviceScaleFactor 1 AND 2, and write both to
// /tmp/raycaster-dpr{N}.json:
//
//   (A) AUTHORITATIVE — fine manual raycast silhouette centre.
//       We project the node with the library's projector (graph2ScreenCoords),
//       then sweep a Raycaster vertically through the node's hit-sphere in 0.5px
//       steps using three-render-objects' EXACT pointer→NDC formula
//       (sx/width*2-1, -(sy/height)*2+1). The centre of the symmetric silhouette
//       band, minus the projected Y, is the offset. This is deterministic (no
//       throttle, no event plumbing) and isolates the NDC math the hypothesis
//       is about.
//
//   (B) CROSS-CHECK — real Playwright mouse hover band.
//       page.mouse.move drives genuine pointer events through the production
//       listener; we read the .label-hovered class the component toggles in
//       onNodeHover. Coarser (2px + 50ms raycaster throttle) but exercises the
//       full live path end to end.
//
// If the offset is ~0 at both dPRs and does not grow with dPR, the hypothesis is
// refuted. The fixture keeps the render loop live and enlarges the hit-sphere so
// the band spans many px; enlarging a sphere cannot move its centre, so it
// cannot fabricate an offset.

const STEP_MOUSE = 2     // px granularity of the real-mouse sweep
const STEP_RAY = 0.5     // px granularity of the manual raycast sweep
const RANGE = 40         // sweep ±RANGE px around the projected Y
const SETTLE_MS = 70     // > three-render-objects pointerRaycasterThrottleMs (50)

for (const dsf of [1, 2]) {
  test.describe(`dpr=${dsf}`, () => {
    test.use({ deviceScaleFactor: dsf, viewport: { width: 1000, height: 800 } })

    test(`measure vertical hover offset`, async ({ page }) => {
      await page.goto('/e2e/fixture-browse.html')
      await page.waitForFunction(() => (window as any).mfReady === true, undefined, { timeout: 20000 })

      // Pick the target (node nearest viewport centre) and isolate it: hide every
      // other node's mesh so the raycaster has a single candidate. Then run the
      // AUTHORITATIVE manual-raycast silhouette sweep in-page.
      const measureA = await page.evaluate(async (args) => {
        const THREE: any = await import('/node_modules/three/build/three.module.js')
        const el: any = document.querySelector('mf-force-graph')
        const graph = el.__test_graph
        const scene = graph.scene()
        const camera = graph.camera()
        const W = graph.width(), H = graph.height()
        const container: HTMLElement = el.renderRoot.querySelector('#graph-container')
        const rect = container.getBoundingClientRect()

        const nodes = graph.graphData().nodes
        const cx = rect.width / 2
        const cy = rect.height / 2
        const projected = nodes.map((n: any) => ({
          n, id: n.id, p: graph.graph2ScreenCoords(n.x, n.y, n.z),
        }))
        const target = [...projected].sort(
          (a, b) =>
            Math.hypot(a.p.x - cx, a.p.y - cy) - Math.hypot(b.p.x - cx, b.p.y - cy),
        )[0]

        // Isolate: hide all non-target meshes (three skips invisible objects).
        for (const { n } of projected) {
          if (n.id === target.id) continue
          n.__threeObj?.traverse?.((o: any) => { if (o.isMesh) o.visible = false })
        }
        const obj3d = target.n.__threeObj

        // three-render-objects' exact pointer→NDC mapping.
        const ndc = (sx: number, sy: number) =>
          new THREE.Vector2((sx / W) * 2 - 1, -(sy / H) * 2 + 1)

        const sweep = (axis: 'x' | 'y', step: number, range: number) => {
          const hit: number[] = []
          for (let d = -range; d <= range; d += step) {
            const sx = axis === 'x' ? target.p.x + d : target.p.x
            const sy = axis === 'y' ? target.p.y + d : target.p.y
            const rc = new THREE.Raycaster()
            rc.setFromCamera(ndc(sx, sy), camera)
            const hs = rc.intersectObject(obj3d, true).filter((h: any) => h.object.visible)
            if (hs.length) hit.push(d)
          }
          return hit
        }
        const vBand = sweep('y', args.stepRay, args.range)
        const hBand = sweep('x', args.stepRay, args.range)
        const centre = (b: number[]) => (b.length ? (Math.min(...b) + Math.max(...b)) / 2 : null)

        // Frame offsets — the structural evidence. renderObjects keys its pointer
        // listener off state.container (#graph-container); three.js DragControls
        // keys its raycaster off renderer.domElement (the <canvas>). If the canvas
        // box is vertically offset from the container, the two raycasters disagree
        // by that many CSS px — and it is dPR-INDEPENDENT (a layout line-box, not
        // a pixel-ratio effect).
        const canvas: HTMLCanvasElement = container.querySelector('canvas') as HTMLCanvasElement
        const overlay = el.__test_labelEls()[0]?.parentElement as HTMLElement | undefined
        const canvasTopMinusContainerTop =
          canvas.getBoundingClientRect().top - rect.top
        const overlayTopMinusContainerTop =
          overlay ? overlay.getBoundingClientRect().top - rect.top : null

        return {
          targetId: target.id,
          projected: target.p,
          rect: { left: rect.left, top: rect.top, width: rect.width, height: rect.height },
          dpr: window.devicePixelRatio,
          // Offset = silhouette centre minus 0 (the projected point) in CSS px.
          vBandMin: vBand.length ? Math.min(...vBand) : null,
          vBandMax: vBand.length ? Math.max(...vBand) : null,
          vOffsetPx: centre(vBand),
          hOffsetPx: centre(hBand),
          canvasTopMinusContainerTop,
          overlayTopMinusContainerTop,
          canvasDrawingBufferH: canvas.height,
          canvasCssH: canvas.getBoundingClientRect().height,
        }
      }, { stepRay: STEP_RAY, range: RANGE })

      // (B) Real-mouse cross-check on the same isolated target. Sweep vertically;
      // read .label-hovered (production hover path). The render loop stays live.
      const hitsDy: number[] = []
      const trace: Array<{ dy: number; hovered: boolean }> = []
      for (let dy = -RANGE; dy <= RANGE; dy += STEP_MOUSE) {
        await page.mouse.move(
          measureA.rect.left + measureA.projected.x,
          measureA.rect.top + measureA.projected.y + dy,
        )
        await page.waitForTimeout(SETTLE_MS)
        const hovered = await page.evaluate((targetId) => {
          const el: any = document.querySelector('mf-force-graph')
          const graph = el.__test_graph
          const node = graph.graphData().nodes.find((n: any) => n.id === targetId)
          const label = node?.__threeObj?.children?.find((c: any) => c.isCSS2DObject)
          return !!label && label.element.classList.contains('label-hovered')
        }, measureA.targetId)
        trace.push({ dy, hovered })
        if (hovered) hitsDy.push(dy)
      }
      const mouseCentre =
        hitsDy.length > 0 ? (Math.min(...hitsDy) + Math.max(...hitsDy)) / 2 : null

      const result = {
        dpr: measureA.dpr,
        deviceScaleFactor: dsf,
        targetId: measureA.targetId,
        projectedX: measureA.projected.x,
        projectedY: measureA.projected.y,
        // (A) authoritative manual-raycast silhouette
        manualRaycast: {
          vBandMin: measureA.vBandMin,
          vBandMax: measureA.vBandMax,
          vOffsetPx: measureA.vOffsetPx,
          hOffsetPx: measureA.hOffsetPx,
        },
        // structural evidence: the canvas frame offset that splits the two
        // raycasters' reference frames (dPR-independent).
        frames: {
          canvasTopMinusContainerTop: measureA.canvasTopMinusContainerTop,
          overlayTopMinusContainerTop: measureA.overlayTopMinusContainerTop,
          canvasDrawingBufferH: measureA.canvasDrawingBufferH,
          canvasCssH: measureA.canvasCssH,
        },
        // (B) real-mouse hover-band cross-check
        realMouse: {
          hitsDy,
          hitBandMin: hitsDy.length ? Math.min(...hitsDy) : null,
          hitBandMax: hitsDy.length ? Math.max(...hitsDy) : null,
          offsetPx: mouseCentre,
        },
        trace,
      }

      writeFileSync(`/tmp/raycaster-dpr${dsf}.json`, JSON.stringify(result, null, 2))
      console.log(`dpr=${dsf}`, JSON.stringify(result))
    })
  })
}
