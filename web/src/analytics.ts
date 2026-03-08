const UMAMI_SRC = 'https://cloud.umami.is/script.js'
const UMAMI_WEBSITE_ID = 'e5752dad-18b8-4c10-a530-76c6b507e4f6'

export function initAnalytics(prod: boolean): void {
  if (!prod) return
  if (document.head.querySelector('script[data-website-id]')) return

  const script = document.createElement('script')
  script.defer = true
  script.src = UMAMI_SRC
  script.dataset.websiteId = UMAMI_WEBSITE_ID
  document.head.appendChild(script)
}
