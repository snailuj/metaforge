import { LitElement, html, css, nothing } from 'lit'
import { customElement, property, state } from 'lit/decorators.js'
import { autocompleteWord, type AutocompleteSuggestion } from '@/api/client'
import { SUGGEST_MODE } from '@/config'

const DEBOUNCE_MS = 200
const MIN_SUGGEST_LENGTH = 3

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

    .suggestions {
      position: absolute;
      top: 100%;
      left: 0;
      right: 0;
      margin: 0;
      padding: 0;
      list-style: none;
      background: var(--colour-bg-hud, rgba(22, 33, 62, 0.95));
      border: var(--hud-border, 1px solid rgba(212, 175, 55, 0.2));
      border-top: none;
      border-radius: 0 0 var(--hud-radius, 4px) var(--hud-radius, 4px);
      backdrop-filter: blur(8px);
      max-height: 20rem;
      overflow-y: auto;
      scrollbar-width: thin;
      scrollbar-color: var(--colour-accent-gold-dim, rgba(212, 175, 55, 0.3)) transparent;
    }

    .suggestion-item {
      display: flex;
      flex-direction: column;
      gap: 0.15rem;
      padding: 0.5rem 1rem;
      cursor: pointer;
      border-bottom: 1px solid rgba(212, 175, 55, 0.08);
    }

    .suggestion-item:last-child {
      border-bottom: none;
    }

    .suggestion-item:hover,
    .suggestion-item.selected {
      background: rgba(212, 175, 55, 0.12);
    }

    .suggestion-top {
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }

    .suggestion-word {
      color: var(--colour-text-primary, #e8e0d4);
      font-weight: 600;
      font-size: 1rem;
    }

    .sense-badge {
      color: var(--colour-text-muted, #6b6560);
      font-size: 0.7rem;
      background: rgba(212, 175, 55, 0.1);
      padding: 0.05rem 0.35rem;
      border-radius: 3px;
    }

    .rarity-badge {
      font-size: 0.65rem;
      padding: 0.05rem 0.35rem;
      border-radius: 3px;
      text-transform: uppercase;
      letter-spacing: 0.03em;
    }

    .rarity-badge[data-rarity="common"] {
      color: #7ec97e;
      background: rgba(126, 201, 126, 0.15);
    }

    .rarity-badge[data-rarity="unusual"] {
      color: #d4af37;
      background: rgba(212, 175, 55, 0.15);
    }

    .rarity-badge[data-rarity="rare"] {
      color: #c97e7e;
      background: rgba(201, 126, 126, 0.15);
    }

    .suggestion-definition {
      color: var(--colour-text-muted, #6b6560);
      font-size: 0.8rem;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
  `

  @property() placeholder = 'Search for a word...'
  @property() searchLabel = 'Search for a word'

  @state() private value = ''
  @state() private suggestions: AutocompleteSuggestion[] = []
  @state() private selectedIndex = -1

  private debounceTimer: ReturnType<typeof setTimeout> | null = null

  connectedCallback(): void {
    super.connectedCallback()
    document.addEventListener('keydown', this.handleGlobalKeydown)
  }

  disconnectedCallback(): void {
    super.disconnectedCallback()
    document.removeEventListener('keydown', this.handleGlobalKeydown)
    if (this.debounceTimer) clearTimeout(this.debounceTimer)
  }

  // NOTE: document.activeElement in shadow DOM returns the host element,
  // not the inner input. We check our own shadow root explicitly (line 76).
  // Other shadow-rooted inputs would need similar guards if added in future.
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
    const word = this.value.trim().toLowerCase()

    // Clear suggestions if input drops below threshold
    if (word.length < MIN_SUGGEST_LENGTH) {
      this.suggestions = []
      this.selectedIndex = -1
    }

    this.scheduleDebounce()
  }

  private scheduleDebounce() {
    if (this.debounceTimer) clearTimeout(this.debounceTimer)

    const word = this.value.trim().toLowerCase()
    if (word.length < MIN_SUGGEST_LENGTH) return

    this.debounceTimer = setTimeout(() => {
      this.debounceTimer = null
      this.fetchSuggestions(word)
    }, DEBOUNCE_MS)
  }

  private async fetchSuggestions(prefix: string) {
    if (SUGGEST_MODE === 'dropdown') {
      try {
        this.suggestions = await autocompleteWord(prefix)
        this.selectedIndex = -1
      } catch {
        // Autocomplete errors are non-fatal — don't disrupt UX
        this.suggestions = []
      }
    } else if (SUGGEST_MODE === 'auto-load') {
      try {
        const suggestions = await autocompleteWord(prefix)
        if (suggestions.length > 0) {
          this.emitSearch(suggestions[0].word)
        }
      } catch {
        // Silent failure
      }
    }
    // 'inline' mode: TODO — ghost text completion
  }

  private handleFocusOut = () => {
    // Delay closing so that click events on suggestions fire first
    requestAnimationFrame(() => {
      const active = this.shadowRoot?.activeElement
      if (!active) {
        this.closeSuggestions()
      }
    })
  }

  private closeSuggestions() {
    this.suggestions = []
    this.selectedIndex = -1
  }

  private handleKeydown(e: KeyboardEvent) {
    // Stop all key events from propagating to FlyControls on window
    e.stopPropagation()

    if (e.key === 'ArrowDown' && this.suggestions.length > 0) {
      e.preventDefault()
      this.selectedIndex = (this.selectedIndex + 1) % this.suggestions.length
      return
    }
    if (e.key === 'ArrowUp' && this.suggestions.length > 0) {
      e.preventDefault()
      this.selectedIndex = this.selectedIndex <= 0
        ? this.suggestions.length - 1
        : this.selectedIndex - 1
      return
    }

    if (e.key === 'Enter') {
      if (this.debounceTimer) {
        clearTimeout(this.debounceTimer)
        this.debounceTimer = null
      }
      if (this.selectedIndex >= 0 && this.selectedIndex < this.suggestions.length) {
        // Submit the selected suggestion
        const word = this.suggestions[this.selectedIndex].word
        this.closeSuggestions()
        this.emitSearch(word)
      } else {
        this.closeSuggestions()
        this.submit()
      }
      return
    }

    if (e.key === 'Escape') {
      if (this.debounceTimer) {
        clearTimeout(this.debounceTimer)
        this.debounceTimer = null
      }
      this.closeSuggestions()
      this.value = ''
      if (this.inputEl) this.inputEl.value = ''
      this.inputEl?.blur()
    }
  }

  private handleKeyup(e: KeyboardEvent) {
    e.stopPropagation()
  }

  private handleSuggestionClick(word: string) {
    this.closeSuggestions()
    this.emitSearch(word)
  }

  private submit() {
    const word = this.value.trim().toLowerCase()
    if (!word) return
    this.emitSearch(word)
  }

  private emitSearch(word: string) {
    this.dispatchEvent(
      new CustomEvent('mf-search', {
        detail: { word },
        bubbles: true,
        composed: true,
      }),
    )
  }

  private renderSuggestions() {
    if (this.suggestions.length === 0) return nothing

    return html`
      <ul class="suggestions" role="listbox">
        ${this.suggestions.map((s, i) => html`
          <li
            id="suggestion-${i}"
            class="suggestion-item ${i === this.selectedIndex ? 'selected' : ''}"
            role="option"
            aria-selected=${i === this.selectedIndex}
            @click=${() => this.handleSuggestionClick(s.word)}
          >
            <div class="suggestion-top">
              <span class="suggestion-word">${s.word}</span>
              ${s.sense_count > 1 ? html`<span class="sense-badge">${s.sense_count} senses</span>` : nothing}
              ${s.rarity ? html`<span class="rarity-badge" data-rarity=${s.rarity}>${s.rarity}</span>` : nothing}
            </div>
            <div class="suggestion-definition">${s.definition}</div>
          </li>
        `)}
      </ul>
    `
  }

  render() {
    return html`
      <div class="search-wrapper" role="search" @focusout=${this.handleFocusOut}>
        <input
          type="text"
          placeholder=${this.placeholder}
          .value=${this.value}
          @input=${this.handleInput}
          @keydown=${this.handleKeydown}
          @keyup=${this.handleKeyup}
          aria-label=${this.searchLabel}
          aria-expanded=${this.suggestions.length > 0}
          aria-autocomplete="list"
          aria-activedescendant=${this.selectedIndex >= 0 ? `suggestion-${this.selectedIndex}` : ''}
        />
        <span class="shortcut-hint">/</span>
      </div>
      ${this.renderSuggestions()}
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'mf-search-bar': MfSearchBar
  }
}
