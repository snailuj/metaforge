import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { initAnalytics } from './analytics'

const UMAMI_WEBSITE_ID = 'e5752dad-18b8-4c10-a530-76c6b507e4f6'

describe('initAnalytics', () => {
  beforeEach(() => {
    document.head.querySelectorAll('script[data-website-id]').forEach(s => s.remove())
  })

  afterEach(() => {
    document.head.querySelectorAll('script[data-website-id]').forEach(s => s.remove())
  })

  it('injects Umami script when prod is true', () => {
    initAnalytics(true)

    const script = document.head.querySelector('script[data-website-id]') as HTMLScriptElement
    expect(script).not.toBeNull()
    expect(script.src).toContain('cloud.umami.is/script.js')
    expect(script.dataset.websiteId).toBe(UMAMI_WEBSITE_ID)
    expect(script.defer).toBe(true)
  })

  it('does not inject script when prod is false', () => {
    initAnalytics(false)

    const script = document.head.querySelector('script[data-website-id]')
    expect(script).toBeNull()
  })

  it('does not inject duplicate scripts on repeated calls', () => {
    initAnalytics(true)
    initAnalytics(true)

    const scripts = document.head.querySelectorAll('script[data-website-id]')
    expect(scripts.length).toBe(1)
  })
})
