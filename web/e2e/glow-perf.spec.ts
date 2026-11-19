import { test, expect } from '@playwright/test'

// Smoke test for the glow speed test page. Quick mode shortens every run, so
// this checks that the whole sequence completes and fills the results table,
// not that any speed is good: the real numbers come from a phone.

test('quick run fills four run rows, three scaling rows and a verdict, with no console errors', async ({ page }) => {
  const errors: string[] = []
  page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()) })
  page.on('pageerror', err => errors.push(String(err)))

  await page.goto('/perf/glow.html?quick=1')
  await page.getByRole('button', { name: 'Run', exact: true }).click()

  await expect(page.locator('#results')).toBeVisible({ timeout: 30000 })
  await expect(page.locator('#run-rows tr')).toHaveCount(4)
  await expect(page.locator('#scaling-rows tr')).toHaveCount(3)
  await expect(page.locator('#verdict')).not.toBeEmpty()
  await expect(page.getByRole('button', { name: 'Copy results' })).toBeVisible()

  expect(errors).toEqual([])
})
