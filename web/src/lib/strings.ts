import { FluentBundle, FluentResource } from '@fluent/bundle'

let bundle: FluentBundle | null = null

/**
 * Fetch and parse the Fluent strings file.
 * Call once at app startup.
 */
export async function initStrings(locale = 'en-GB'): Promise<void> {
  const response = await fetch('/strings/v1/ui.ftl')
  if (!response.ok) {
    console.error('Failed to load strings:', response.status)
    return
  }

  const ftl = await response.text()
  bundle = new FluentBundle(locale)
  const resource = new FluentResource(ftl)
  const errors = bundle.addResource(resource)
  if (errors.length) {
    console.error('Fluent parse errors:', errors)
  }
}

/**
 * Get a translated string by message ID.
 * Returns the ID itself as fallback if not found.
 */
export function getString(
  id: string,
  args?: Record<string, string | number>,
): string {
  if (!bundle) return id

  const message = bundle.getMessage(id)
  if (!message?.value) return id

  return bundle.formatPattern(message.value, args)
}
