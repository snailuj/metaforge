import { LitElement, html, css } from 'lit'
import { customElement, property, state } from 'lit/decorators.js'

@customElement('mf-search-bar')
export class MfSearchBar extends LitElement {
  static styles = css`
    :host {
      display: block;
      position: relative;
      z-index: 10;
    }

    .search-wrapper {
      display: flex;
      align-items: center;
      gap: var(--space-sm, 0.5rem);
      padding: var(--space-sm, 0.5rem) var(--space-md, 1rem);
      background: var(--colour-bg-hud, rgba(22, 33, 62, 0.6));
      border: var(--hud-border, 1px solid rgba(212, 175, 55, 0.2));
      border-radius: var(--hud-radius, 4px);
      backdrop-filter: blur(8px);
    }

    input {
      flex: 1;
      background: transparent;
      border: none;
      outline: none;
      color: var(--colour-text-primary, #e8e0d4);
      font-family: var(--font-body, serif);
      font-size: 1.1rem;
    }

    input::placeholder {
      color: var(--colour-text-muted, #6b6560);
    }

    .shortcut-hint {
      color: var(--colour-text-muted, #6b6560);
      font-size: 0.75rem;
      font-family: var(--font-mono, monospace);
    }
  `

  @property() placeholder = 'Search for a word...'
  @property() searchLabel = 'Search for a word'

  @state() private value = ''

  connectedCallback(): void {
    super.connectedCallback()
    document.addEventListener('keydown', this.handleGlobalKeydown)
  }

  disconnectedCallback(): void {
    super.disconnectedCallback()
    document.removeEventListener('keydown', this.handleGlobalKeydown)
  }

  private handleGlobalKeydown = (e: KeyboardEvent) => {
    if (e.key !== '/') return
    const active = document.activeElement
    // Don't steal focus from any text input
    if (
      active instanceof HTMLInputElement ||
      active instanceof HTMLTextAreaElement ||
      active?.getAttribute('contenteditable') === 'true'
    ) return
    // Also check if our own shadow input is focused
    if (active === this && this.shadowRoot?.activeElement === this.inputEl) return
    e.preventDefault()
    this.inputEl?.focus()
  }

  private get inputEl(): HTMLInputElement | null {
    return this.shadowRoot?.querySelector('input') ?? null
  }

  private handleInput(e: Event) {
    this.value = (e.target as HTMLInputElement).value
  }

  private handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter') {
      this.submit()
    }
    if (e.key === 'Escape') {
      this.value = ''
      if (this.inputEl) this.inputEl.value = ''
      this.inputEl?.blur()
    }
  }

  private submit() {
    const word = this.value.trim().toLowerCase()
    if (!word) return

    this.dispatchEvent(
      new CustomEvent('mf-search', {
        detail: { word },
        bubbles: true,
        composed: true,
      }),
    )
  }

  render() {
    return html`
      <div class="search-wrapper">
        <input
          type="text"
          placeholder=${this.placeholder}
          .value=${this.value}
          @input=${this.handleInput}
          @keydown=${this.handleKeydown}
          aria-label=${this.searchLabel}
          role="searchbox"
        />
        <span class="shortcut-hint">/</span>
      </div>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'mf-search-bar': MfSearchBar
  }
}
