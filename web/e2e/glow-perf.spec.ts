import { test, expect } from '@playwright/test'

// Smoke test for the glow speed test page. Quick mode shortens every run, so
// this checks that the whole sequence completes and fills the results table,
// not that any speed is good: the real numbers come from a phone. It needs
// the Rust module, so run `npm run build:wasm` first.

test('quick run fills five run rows, three scaling rows, the speed-up line and a verdict, with no console errors', async ({ page }) => {
  const errors: string[] = []
  page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()) })
  page.on('pageerror', err => errors.push(String(err)))

  await page.goto('/perf/glow.html?quick=1')
  await page.getByRole('button', { name: 'Run', exact: true }).click()

  await expect(page.locator('#results')).toBeVisible({ timeout: 30000 })
  await expect(page.locator('#run-rows tr')).toHaveCount(5)
  await expect(page.locator('#scaling-rows tr')).toHaveCount(3)
  await expect(page.locator('#verdict')).not.toBeEmpty()
  await expect(page.locator('#speedup')).toContainText('Rust physics speed-up at 100 / 300 / 1000 nodes:')
  await expect(page.getByRole('button', { name: 'Copy results' })).toBeVisible()

  expect(errors).toEqual([])
})
