import { test, expect } from '@playwright/test'

// Real-bundle Playwright verification for phrase-as-node grading panel features.
// Tests run in real Chromium at two viewport widths:
//   desktop 1280 — confirms layout and pointer interactions
//   mobile  390  — confirms the panel renders and responds at narrow width
//
// The grade panel is fetch-free: all data is injected via JS properties in
// fixture-grade-panel.html; no sidecar stub is needed.
//
// Assertions cover the four requirements from the implementation plan (Task 9):
//   (a) multi-word step renders phrase-first (phrase is primary, head is subscript)
//   (b) sense fan opens on a step tap and a non-intended tick toggles
//   (c) vec: step shows "vector node — no synset" affordance
//   (d) zero console errors on a fresh page load

for (const [label, width, height] of [
  ['desktop', 1280, 800],
  ['mobile', 390, 844],
] as ['desktop' | 'mobile', number, number][]) {
  test.describe(`phrase-as-node ${label} (${width}×${height})`, () => {
    test.use({ viewport: { width, height } })

    test.beforeEach(async ({ page }) => {
      await page.goto('/e2e/fixture-grade-panel.html')
      await page.waitForFunction(() => (window as any).mfReady === true, undefined, { timeout: 10000 })
    })

    // (a) Multi-word step renders phrase as primary label; head moves to the subscript.
    //     Single-word step (phrase === head) renders no subscript at all.
    test('(a) multi-word step renders phrase-first, head in subscript', async ({ page }) => {
      const result = await page.evaluate(() => {
        const el: any = document.querySelector('mf-grade-panel')
        const root: ShadowRoot | null = el?.shadowRoot ?? null
        if (!root) return null
        const btn1 = root.querySelector('[data-testid="step-node-1"]') as HTMLElement | null
        const btn0 = root.querySelector('[data-testid="step-node-0"]') as HTMLElement | null
        const btn2 = root.querySelector('[data-testid="step-node-2"]') as HTMLElement | null
        const sub1 = btn1?.querySelector('.phrase-sub') as HTMLElement | null
        return {
          btn1Text: btn1?.textContent?.trim() ?? '',
          sub1Text: sub1?.textContent?.trim() ?? null,
          // Only step 1 should carry a phrase-sub (multi-word with differing head).
          phraseSubCount: root.querySelectorAll('.phrase-sub').length,
          btn0HasSub: !!btn0?.querySelector('.phrase-sub'),
          // Vec: step (step 2) primary text is still the phrase.
          btn2Text: btn2?.textContent?.trim() ?? '',
        }
      })

      expect(result).not.toBeNull()
      // Step 1: "buried wound" is the primary button text.
      expect(result!.btn1Text).toContain('buried wound')
      // Subscript carries the snapped head "wound" but not the full phrase.
      expect(result!.sub1Text).toContain('wound')
      expect(result!.sub1Text).not.toContain('buried wound')
      // Multi-word steps (phrase ≠ head) carry exactly one .phrase-sub each; there
      // are two in this fixture (step 1 and the vec: step 2 both differ). The
      // single-word step 0 (grief/grief) must carry none.
      expect(result!.phraseSubCount).toBeGreaterThanOrEqual(1)
      expect(result!.btn0HasSub).toBe(false)
      // Vec: step (step 2) primary text is the phrase "pressed flower".
      expect(result!.btn2Text).toContain('pressed flower')
    })

    // (b) Tapping a step opens the sense fan; the intended sense is pre-lit (.intended);
    //     tapping a non-intended sense toggles the .ticked class on and then off.
    test('(b) sense fan opens on step tap; non-intended tick toggles', async ({ page }) => {
      // Tap step 1 ("buried wound" / intended synset 200).
      await page.evaluate(() => {
        const el: any = document.querySelector('mf-grade-panel')
        ;(el?.shadowRoot?.querySelector('[data-testid="step-node-1"]') as HTMLElement | null)?.click()
      })

      // Wait for Lit to re-render the sense fan inside the link-gloss popover.
      await page.waitForFunction(() => {
        const el: any = document.querySelector('mf-grade-panel')
        return !!el?.shadowRoot?.querySelector('[data-testid="sense-fan"]')
      }, undefined, { timeout: 5000 })

      const initial = await page.evaluate(() => {
        const root = (document.querySelector('mf-grade-panel') as any)?.shadowRoot
        const fan   = root?.querySelector('[data-testid="sense-fan"]')
        const o200  = root?.querySelector('[data-testid="sense-option-200"]')
        const o201  = root?.querySelector('[data-testid="sense-option-201"]')
        return {
          fanText:     fan?.textContent ?? '',
          o200Classes: o200?.className ?? '',
          o201Classes: o201?.className ?? '',
        }
      })

      // Inventory senses appear in the fan.
      expect(initial.fanText).toContain('a brief look')
      expect(initial.fanText).toContain('a deflection')
      // Intended sense (200) is pre-lit.
      expect(initial.o200Classes).toContain('intended')
      expect(initial.o200Classes).not.toContain('ticked')
      // Non-intended sense (201) starts unticked.
      expect(initial.o201Classes).not.toContain('ticked')

      // Tick sense 201.
      await page.evaluate(() => {
        const root = (document.querySelector('mf-grade-panel') as any)?.shadowRoot
        ;(root?.querySelector('[data-testid="sense-option-201"]') as HTMLElement | null)?.click()
      })
      await page.waitForFunction(() => {
        const root = (document.querySelector('mf-grade-panel') as any)?.shadowRoot
        return root?.querySelector('[data-testid="sense-option-201"]')?.classList.contains('ticked') === true
      }, undefined, { timeout: 5000 })

      const afterTick = await page.evaluate(() =>
        (document.querySelector('mf-grade-panel') as any)
          ?.shadowRoot?.querySelector('[data-testid="sense-option-201"]')?.className ?? '')
      expect(afterTick).toContain('ticked')

      // Toggle off.
      await page.evaluate(() => {
        const root = (document.querySelector('mf-grade-panel') as any)?.shadowRoot
        ;(root?.querySelector('[data-testid="sense-option-201"]') as HTMLElement | null)?.click()
      })
      await page.waitForFunction(() => {
        const root = (document.querySelector('mf-grade-panel') as any)?.shadowRoot
        return root?.querySelector('[data-testid="sense-option-201"]')?.classList.contains('ticked') === false
      }, undefined, { timeout: 5000 })

      const afterUntick = await page.evaluate(() =>
        (document.querySelector('mf-grade-panel') as any)
          ?.shadowRoot?.querySelector('[data-testid="sense-option-201"]')?.className ?? '')
      expect(afterUntick).not.toContain('ticked')
    })

    // (c) Vec: step (synset_id null) shows "vector node — no synset" in the sense fan;
    //     no sense-option buttons are rendered (no ticking affordance for a vec: node).
    test('(c) vec: step shows "vector node — no synset" affordance', async ({ page }) => {
      // Tap step 2 ("pressed flower" / synset_id null).
      await page.evaluate(() => {
        const el: any = document.querySelector('mf-grade-panel')
        ;(el?.shadowRoot?.querySelector('[data-testid="step-node-2"]') as HTMLElement | null)?.click()
      })

      // Wait for Lit to render the vec: affordance.
      await page.waitForFunction(() => {
        const el: any = document.querySelector('mf-grade-panel')
        return !!el?.shadowRoot?.querySelector('[data-testid="vec-node-label"]')
      }, undefined, { timeout: 5000 })

      const result = await page.evaluate(() => {
        const root = (document.querySelector('mf-grade-panel') as any)?.shadowRoot
        const fan       = root?.querySelector('[data-testid="sense-fan"]')
        const vecLabel  = root?.querySelector('[data-testid="vec-node-label"]')
        // Vec: nodes must not expose sense-option tick buttons.
        const tickBtns  = root?.querySelectorAll('button.sense-option') ?? []
        return {
          fanPresent:       !!fan,
          vecLabelText:     vecLabel?.textContent?.trim() ?? null,
          senseOptionCount: tickBtns.length,
        }
      })

      expect(result.fanPresent).toBe(true)
      expect(result.vecLabelText).toContain('vector node')
      expect(result.vecLabelText).toContain('no synset')
      // No ticking affordance on a vec: node.
      expect(result.senseOptionCount).toBe(0)
    })

    // (d) Attaching the console listener BEFORE navigating ensures every error emitted
    //     during component boot is captured. The beforeEach already loaded the page, so
    //     we re-navigate here from a fresh state.
    test('(d) zero console errors on a fresh load', async ({ page }) => {
      const errors: string[] = []
      page.on('console', msg => {
        if (msg.type() === 'error') errors.push(msg.text())
      })
      await page.goto('/e2e/fixture-grade-panel.html')
      await page.waitForFunction(() => (window as any).mfReady === true, undefined, { timeout: 10000 })
      expect(errors).toEqual([])
    })
  })
}
