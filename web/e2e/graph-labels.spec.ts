import { test, expect } from '@playwright/test'

// Real-browser geometry/contrast assertions for the DOM label layer. These are
// the anti-self-confirmation tests: label *position* is checked by comparing two
// fully independent code paths — the library's projector (graph2ScreenCoords) and
// the browser's own layout of the real CSS transform (getBoundingClientRect). We
// never hand-roll the fov/tan projection here (that was the original self-
// confirming bug). They share only the camera object, so any wiring fault
// (wrong matrixWorld, stale camera, wrong centre, mis-parented label) surfaces as
// a mismatch beyond the 2px tolerance.

const TOL = 2 // px tolerance — sub-pixel layout + projector rounding
// Must match LABEL_CENTER exported from src/graph/label-layer.ts. The CSS2DObject
// centre is the fraction of the element's box that sits on the node's projected
// point: x=0.5 (horizontally centred), y=1.1 (floated 110% above).
const CENTER = { x: 0.5, y: 1.1 }

test.beforeEach(async ({ page }) => {
  await page.goto('/e2e/fixture.html')
  await page.waitForFunction(() => (window as any).mfReady === true)
})

test('every visible label sits on its node projected position (independent code paths)', async ({ page }) => {
  const mismatches = await page.evaluate((cfg) => {
    const el: any = document.querySelector('mf-force-graph')
    const graph = el.__test_graph
    // Freeze a deterministic frame SYNCHRONOUSLY before measuring: grade mode
    // fires a 700ms-delayed zoomToFit(400ms tween) that pauseAnimation doesn't
    // cancel, so the fixture's resting camera may still be moving. Re-pin the
    // current camera with duration 0 (kills any in-flight tween) then render one
    // CSS2D frame — both code paths below now read the same frozen camera. (The
    // node positions, not the camera path, are what we're validating.)
    const cam = graph.camera()
    graph.cameraPosition({ x: cam.position.x, y: cam.position.y, z: cam.position.z }, { x: 0, y: 0, z: 0 }, 0)
    el.__test_pauseAndRenderFrame()
    // graph2ScreenCoords reports coordinates in the renderer/overlay frame — its
    // origin is the CSS2DRenderer overlay's top-left, NOT the <canvas> box (which
    // an inline-layout line-box shifts down by ~18px). Use the overlay's page
    // rect as the shared reference frame; the two code paths stay independent.
    const overlay = el.__test_labelEls()[0]?.parentElement as HTMLElement
    const frame = overlay.getBoundingClientRect()
    const out: any[] = []
    for (const n of graph.graphData().nodes) {
      const label = n.__threeObj?.children?.find((c: any) => c.isCSS2DObject)
      if (!label || label.element.style.display === 'none') continue
      // Library projector (overlay-frame-relative).
      const lib = graph.graph2ScreenCoords(n.x, n.y, n.z)
      // Browser layout (viewport-relative) → subtract overlay page offset to
      // bring it into the same frame, then apply the centre.
      const r = label.element.getBoundingClientRect()
      const anchorX = r.left + r.width * cfg.center.x - frame.left
      const anchorY = r.top + r.height * cfg.center.y - frame.top
      if (Math.abs(anchorX - lib.x) > cfg.tol || Math.abs(anchorY - lib.y) > cfg.tol) {
        out.push({ id: n.id, anchorX, anchorY, lib, rect: { l: r.left, t: r.top, w: r.width, h: r.height } })
      }
    }
    return out
  }, { center: CENTER, tol: TOL })
  expect(mismatches).toEqual([])
})

test('labels stay glued under rotate, pan, and zoom', async ({ page }) => {
  const cameras = [
    { pos: { x: 0, y: 0, z: 120 }, look: { x: 0, y: 0, z: 0 } },    // zoom in
    { pos: { x: 0, y: 0, z: 900 }, look: { x: 0, y: 0, z: 0 } },    // zoom out
    { pos: { x: 300, y: 80, z: 300 }, look: { x: 0, y: 0, z: 0 } }, // orbit
    { pos: { x: 60, y: 0, z: 400 }, look: { x: 60, y: 0, z: 0 } },  // pan
  ]
  for (const cam of cameras) {
    const result = await page.evaluate((args) => {
      const el: any = document.querySelector('mf-force-graph')
      // cameraPosition with duration 0 = synchronous, no tween — deterministic.
      el.__test_graph.cameraPosition(args.cam.pos, args.cam.look, 0)
      el.__test_pauseAndRenderFrame()
      // Same shared frame as the position test: the CSS2D overlay's page rect.
      const overlay = el.__test_labelEls()[0]?.parentElement as HTMLElement
      const frame = overlay.getBoundingClientRect()
      const bad: any[] = []
      for (const n of el.__test_graph.graphData().nodes) {
        const label = n.__threeObj?.children?.find((c: any) => c.isCSS2DObject)
        if (!label || label.element.style.display === 'none') continue
        const lib = el.__test_graph.graph2ScreenCoords(n.x, n.y, n.z)
        const r = label.element.getBoundingClientRect()
        const ax = r.left + r.width * args.center.x - frame.left
        const ay = r.top + r.height * args.center.y - frame.top
        if (Math.abs(ax - lib.x) > args.tol || Math.abs(ay - lib.y) > args.tol) {
          bad.push({ id: n.id, ax, ay, lib })
        }
      }
      return bad
    }, { cam, center: CENTER, tol: TOL })
    expect(result, `camera ${JSON.stringify(cam.pos)}`).toEqual([])
  }
})

test('grade label text is the node head, not the phrase', async ({ page }) => {
  const texts = await page.evaluate(() => {
    const el: any = document.querySelector('mf-force-graph')
    el.__test_pauseAndRenderFrame() // ensure CSS2DRenderer has attached label DOM
    return el.__test_labelEls().map((d: HTMLElement) =>
      d.querySelector('.mf-graph-label__text')!.textContent)
  })
  // Heads from the fixture; the phrases ("raw grief", "the leaden weight", …) are
  // never used as label text — they live only in the tooltip.
  expect(texts).toContain('grief')
  expect(texts).toContain('weight')
  expect(texts).not.toContain('raw grief')
  expect(texts).not.toContain('the leaden weight')
})

test('arrow affordance is present on an inbound node and absent on the topic', async ({ page }) => {
  const flags = await page.evaluate(() => {
    const el: any = document.querySelector('mf-force-graph')
    el.__test_pauseAndRenderFrame() // ensure CSS2DRenderer has attached label DOM
    const labelFor = (head: string) => el.__test_labelEls().find((d: HTMLElement) =>
      d.querySelector('.mf-graph-label__text')!.textContent === head)
    const weight = labelFor('weight')   // shared intermediate — has inbound edges
    const grief = labelFor('grief')     // topic — no inbound edges
    return {
      weightHasArrow: !!weight?.querySelector('.mf-graph-label__arrow'),
      griefHasArrow: !!grief?.querySelector('.mf-graph-label__arrow'),
    }
  })
  expect(flags.weightHasArrow).toBe(true)
  expect(flags.griefHasArrow).toBe(false)
})

test('hovering the arrow reveals the tooltip with deduped backlink rows', async ({ page }) => {
  // Tag the shared `weight` node's arrow + tooltip so Playwright can drive a real
  // pointer hover (the CSS :hover reveal is not exercisable in happy-dom).
  await page.evaluate(() => {
    const el: any = document.querySelector('mf-force-graph')
    el.__test_pauseAndRenderFrame() // ensure CSS2DRenderer has attached label DOM
    const weight = el.__test_labelEls().find((d: HTMLElement) =>
      d.querySelector('.mf-graph-label__text')!.textContent === 'weight')
    weight.querySelector('.mf-graph-label__arrow').setAttribute('data-testid', 'weight-arrow')
    weight.querySelector('.mf-graph-label__tooltip').setAttribute('data-testid', 'weight-tooltip')
  })
  const tooltip = page.locator('[data-testid="weight-tooltip"]')
  // Default-hidden via the stylesheet rule (not inline), so it must not show yet.
  await expect(tooltip).toBeHidden()

  await page.locator('[data-testid="weight-arrow"]').hover()
  await expect(tooltip).toBeVisible()

  const rows = await page.evaluate(() => {
    const el: any = document.querySelector('mf-force-graph')
    const weight = el.__test_labelEls().find((d: HTMLElement) =>
      d.querySelector('.mf-graph-label__text')!.textContent === 'weight')
    return Array.from(weight.querySelectorAll('.mf-graph-label__backlink'))
      .map((r: any) => r.textContent)
  })
  // Two distinct inbound connections (grief→"the leaden weight", sorrow→"a pressing
  // heaviness"); the duplicate inbound edge across chains would collapse.
  expect(rows.length).toBe(2)
  expect(rows).toContain('← grief · "the leaden weight"')
  expect(rows).toContain('← sorrow · "a pressing heaviness"')
})

test('arrow tracks the node projected position after a rotate (independent code paths)', async ({ page }) => {
  const mismatches = await page.evaluate((cfg) => {
    const el: any = document.querySelector('mf-force-graph')
    const graph = el.__test_graph
    // Rotate the camera, then freeze a deterministic frame (kills any in-flight
    // tween) — both code paths below read the same frozen camera afterwards.
    graph.cameraPosition({ x: 300, y: 80, z: 300 }, { x: 0, y: 0, z: 0 }, 0)
    el.__test_pauseAndRenderFrame()
    const overlay = el.__test_labelEls()[0]?.parentElement as HTMLElement
    const frame = overlay.getBoundingClientRect()
    const out: any[] = []
    for (const n of graph.graphData().nodes) {
      const label = n.__threeObj?.children?.find((c: any) => c.isCSS2DObject)
      if (!label || label.element.style.display === 'none') continue
      const arrow = label.element.querySelector('.mf-graph-label__arrow')
      if (!arrow) continue // only nodes with inbound edges carry the affordance
      // Library projector (overlay-frame-relative) for the node's data coord.
      const lib = graph.graph2ScreenCoords(n.x, n.y, n.z)
      // The label element rides on the node via CSS2DRenderer; its anchor (centre)
      // must sit on the projected point. The arrow is a child of that element, so
      // if the label tracks, the arrow tracks — assert the label anchor matches.
      const r = label.element.getBoundingClientRect()
      const anchorX = r.left + r.width * cfg.center.x - frame.left
      const anchorY = r.top + r.height * cfg.center.y - frame.top
      if (Math.abs(anchorX - lib.x) > cfg.tol || Math.abs(anchorY - lib.y) > cfg.tol) {
        out.push({ id: n.id, anchorX, anchorY, lib })
      }
      // The arrow must lie inside the label's box (right-hand end) — proves it
      // rides with the label rather than detaching to a stale position.
      const ar = arrow.getBoundingClientRect()
      const inside = ar.left >= r.left - cfg.tol && ar.right <= r.right + cfg.tol &&
        ar.top >= r.top - cfg.tol && ar.bottom <= r.bottom + cfg.tol
      if (!inside) out.push({ id: n.id, arrowDetached: { ar, r } })
    }
    return out
  }, { center: CENTER, tol: TOL })
  expect(mismatches).toEqual([])
})

test('labels meet the min-px floor and carry contrast styles', async ({ page }) => {
  const report = await page.evaluate(() => {
    const el: any = document.querySelector('mf-force-graph')
    const labels: HTMLElement[] = el.__test_labelEls()
    return labels.map((d) => {
      const span = d.querySelector('span') as HTMLElement
      const boxCs = getComputedStyle(d)
      const spanCs = getComputedStyle(span)
      // Parse the background-colour alpha out of the computed rgba()/rgb().
      const m = boxCs.backgroundColor.match(/rgba?\(([^)]+)\)/)
      const parts = m ? m[1].split(',').map((s) => parseFloat(s.trim())) : []
      const alpha = parts.length === 4 ? parts[3] : (parts.length === 3 ? 1 : 0)
      return {
        h: d.getBoundingClientRect().height,
        bgAlpha: alpha,
        bg: boxCs.backgroundColor,
        shadow: spanCs.textShadow,
      }
    })
  })
  expect(report.length).toBeGreaterThan(0)
  for (const r of report) {
    expect(r.h).toBeGreaterThanOrEqual(10)   // min-px floor (10/11px) honoured
    expect(r.bgAlpha).toBeGreaterThan(0)      // contrast box present
    expect(r.shadow).not.toBe('none')         // text outline present
  }
})
