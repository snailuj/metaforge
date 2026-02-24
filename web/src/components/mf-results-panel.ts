import { LitElement, html, css, nothing } from 'lit'
import { customElement, property } from 'lit/decorators.js'
import type { LookupResult, Sense, RelatedWord } from '@/types/api'
import { getString } from '@/lib/strings'

@customElement('mf-results-panel')
export class MfResultsPanel extends LitElement {
  static styles = css`
    :host {
      display: block;
      position: absolute;
      top: calc(var(--space-md, 1rem) + 3.5rem);
      left: var(--space-md, 1rem);
      bottom: var(--space-xl, 2rem);
      width: var(--hud-width, 320px);
      z-index: 10;
      overflow: visible;
      pointer-events: none;
    }

    .panel-track {
      height: 100%;
      overflow-y: auto;
      scrollbar-width: thin;
      scrollbar-color: var(--colour-accent-gold-dim) transparent;
      transition: transform 200ms cubic-bezier(0, 0, 0.08, 1);
      pointer-events: auto;
    }

    :host([collapsed]) .panel-track {
      transform: translateX(calc(-100% - var(--space-md, 1rem)));
      pointer-events: none;
    }

    .panel {
      background: var(--colour-bg-hud, rgba(22, 33, 62, 0.6));
      border: var(--hud-border, 1px solid rgba(212, 175, 55, 0.2));
      border-radius: var(--hud-radius, 4px);
      backdrop-filter: blur(8px);
      padding: var(--space-md, 1rem);
    }

    .toggle-btn {
      display: none;
      position: absolute;
      background: var(--colour-bg-hud, rgba(22, 33, 62, 0.6));
      border: var(--hud-border, 1px solid rgba(212, 175, 55, 0.2));
      border-radius: var(--hud-radius, 4px);
      color: var(--colour-accent-gold, #d4af37);
      font-size: 0.8rem;
      padding: 4px 8px;
      cursor: pointer;
      z-index: 1;
      pointer-events: auto;
    }

    :host(:not([collapsed])) .toggle-btn {
      left: auto;
      right: 0;
      top: 0.25rem;
    }

    :host([collapsed]) .toggle-btn {
      left: 0;
      top: 0;
    }

    @media (max-width: 768px) {
      .toggle-btn {
        display: block;
      }
    }

    h2 {
      font-family: var(--font-heading, serif);
      color: var(--colour-accent-gold, #d4af37);
      font-size: 1.5rem;
      margin-bottom: var(--space-sm, 0.5rem);
    }

    .sense {
      margin-bottom: var(--space-md, 1rem);
      padding-bottom: var(--space-md, 1rem);
      border-bottom: 1px solid rgba(212, 175, 55, 0.1);
    }

    .sense:last-child {
      border-bottom: none;
      margin-bottom: 0;
      padding-bottom: 0;
    }

    .pos-badge {
      display: inline-block;
      font-size: 0.75rem;
      color: var(--colour-text-secondary, #a89f94);
      font-style: italic;
      margin-bottom: var(--space-xs, 0.25rem);
    }

    .definition {
      font-size: 0.95rem;
      line-height: 1.5;
      margin-bottom: var(--space-sm, 0.5rem);
    }

    .section-label {
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--colour-text-muted, #6b6560);
      margin-bottom: var(--space-xs, 0.25rem);
      margin-top: var(--space-sm, 0.5rem);
    }

    .word-list {
      display: flex;
      flex-wrap: wrap;
      gap: var(--space-xs, 0.25rem);
    }

    .word-chip {
      font-size: 0.9rem;
      color: var(--colour-text-primary, #e8e0d4);
      cursor: pointer;
      padding: 2px 6px;
      border-radius: 3px;
      transition: background 0.15s;
    }

    .word-chip:hover {
      background: rgba(212, 175, 55, 0.15);
    }

    .word-chip.synonym { color: #c4956a; }
    .word-chip.hypernym { color: #8b6f47; }
    .word-chip.hyponym { color: #6a8b6f; }
    .word-chip.similar { color: #7a6a8b; }
    .word-chip.collocation { color: #8ba4b8; }
    .word-chip.antonym { color: #b88b8b; }

    .usage-example {
      font-style: italic;
      font-size: 0.9rem;
      line-height: 1.5;
      color: var(--colour-text-secondary, #a89f94);
      margin-bottom: var(--space-sm, 0.5rem);
      padding-left: var(--space-sm, 0.5rem);
      border-left: 2px solid rgba(212, 175, 55, 0.3);
    }

    .meta-badges {
      display: flex;
      gap: var(--space-xs, 0.25rem);
      margin-bottom: var(--space-xs, 0.25rem);
    }

    .meta-badge {
      display: inline-block;
      font-size: 0.65rem;
      padding: 1px 6px;
      border-radius: 8px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }

    .meta-badge.register {
      background: rgba(139, 164, 184, 0.2);
      color: #8ba4b8;
    }

    .meta-badge.connotation-positive {
      background: rgba(106, 139, 111, 0.2);
      color: #8bb89a;
    }

    .meta-badge.connotation-neutral {
      background: rgba(168, 159, 148, 0.2);
      color: #a89f94;
    }

    .meta-badge.connotation-negative {
      background: rgba(184, 139, 139, 0.2);
      color: #b88b8b;
    }

    .word-chip:focus {
      outline: 1px solid var(--colour-accent-gold, #d4af37);
      outline-offset: 1px;
    }

    .rarity-badge {
      display: inline-block;
      font-size: 0.65rem;
      padding: 1px 6px;
      border-radius: 8px;
      margin-left: var(--space-xs, 0.25rem);
      text-transform: uppercase;
      letter-spacing: 0.04em;
      vertical-align: middle;
    }

    .rarity-badge.common {
      background: rgba(106, 139, 111, 0.2);
      color: #8bb89a;
    }

    .rarity-badge.unusual {
      background: rgba(196, 149, 106, 0.2);
      color: #c4956a;
    }

    .rarity-badge.rare {
      background: rgba(122, 106, 139, 0.2);
      color: #a88bc4;
    }
  `

  @property({ type: Object }) result: LookupResult | null = null
  @property({ type: Boolean, reflect: true }) collapsed = false

  private mediaQuery: MediaQueryList | null = null

  connectedCallback(): void {
    super.connectedCallback()
    this.mediaQuery = window.matchMedia('(max-width: 768px)')
    if (this.mediaQuery.matches) this.collapsed = true
    this.mediaQuery.addEventListener('change', this.handleMediaChange)
  }

  disconnectedCallback(): void {
    super.disconnectedCallback()
    this.mediaQuery?.removeEventListener('change', this.handleMediaChange)
  }

  private handleMediaChange = (e: MediaQueryListEvent) => {
    this.collapsed = e.matches
  }

  private toggleCollapsed() {
    this.collapsed = !this.collapsed
  }

  private renderRarityBadge(rarity?: string) {
    if (!rarity) return nothing
    return html`<span class="rarity-badge ${rarity}">${getString(`rarity-${rarity}`)}</span>`
  }

  private handleWordClick(word: string) {
    this.dispatchEvent(
      new CustomEvent('mf-word-navigate', {
        detail: { word },
        bubbles: true,
        composed: true,
      }),
    )
  }

  private handleWordRightClick(e: MouseEvent, word: string) {
    e.preventDefault()
    navigator.clipboard.writeText(word).catch(() => { /* clipboard unavailable */ })
    this.dispatchEvent(
      new CustomEvent('mf-word-copy', {
        detail: { word },
        bubbles: true,
        composed: true,
      }),
    )
  }

  private handleWordKeydown(e: KeyboardEvent, word: string) {
    if (e.key === 'Enter') {
      this.handleWordClick(word)
    }
  }

  private renderWordChip(rw: RelatedWord, type: string) {
    return html`
      <span
        class="word-chip ${type}"
        data-word=${rw.word}
        data-rarity=${rw.rarity ?? ''}
        tabindex="0"
        role="button"
        @click=${() => this.handleWordClick(rw.word)}
        @contextmenu=${(e: MouseEvent) => this.handleWordRightClick(e, rw.word)}
        @keydown=${(e: KeyboardEvent) => this.handleWordKeydown(e, rw.word)}
        title="${getString('word-chip-title')}"
      >${rw.word}</span>
    `
  }

  private renderMetaBadges(sense: Sense) {
    const badges = []
    if (sense.register && sense.register !== 'neutral') {
      badges.push(html`<span class="meta-badge register">${getString(`register-${sense.register}`)}</span>`)
    }
    if (sense.connotation && sense.connotation !== 'neutral') {
      badges.push(html`<span class="meta-badge connotation-${sense.connotation}">${getString(`connotation-${sense.connotation}`)}</span>`)
    }
    return badges.length ? html`<div class="meta-badges">${badges}</div>` : nothing
  }

  private renderSense(sense: Sense) {
    return html`
      <div class="sense">
        <span class="pos-badge">${sense.pos}</span>
        ${this.renderMetaBadges(sense)}
        <div class="definition">${sense.definition}</div>

        ${sense.usage_example
          ? html`<div class="usage-example">${sense.usage_example}</div>`
          : nothing}

        ${sense.synonyms.length
          ? html`
              <div class="section-label">${getString('results-synonyms')}</div>
              <div class="word-list">
                ${sense.synonyms.map(s => this.renderWordChip(s, 'synonym'))}
              </div>
            `
          : nothing}

        ${sense.relations.hypernyms.length
          ? html`
              <div class="section-label">${getString('results-broader')}</div>
              <div class="word-list">
                ${sense.relations.hypernyms.map(h => this.renderWordChip(h, 'hypernym'))}
              </div>
            `
          : nothing}

        ${sense.relations.hyponyms.length
          ? html`
              <div class="section-label">${getString('results-narrower')}</div>
              <div class="word-list">
                ${sense.relations.hyponyms.map(h => this.renderWordChip(h, 'hyponym'))}
              </div>
            `
          : nothing}

        ${sense.relations.similar.length
          ? html`
              <div class="section-label">${getString('results-similar')}</div>
              <div class="word-list">
                ${sense.relations.similar.map(s => this.renderWordChip(s, 'similar'))}
              </div>
            `
          : nothing}

        ${sense.relations.antonyms.length
          ? html`
              <div class="section-label">${getString('results-antonyms')}</div>
              <div class="word-list">
                ${sense.relations.antonyms.map(a => this.renderWordChip(a, 'antonym'))}
              </div>
            `
          : nothing}

        ${sense.collocations?.length
          ? html`
              <div class="section-label">${getString('results-collocations')}</div>
              <div class="word-list">
                ${sense.collocations.map(c => this.renderWordChip(c, 'collocation'))}
              </div>
            `
          : nothing}
      </div>
    `
  }

  render() {
    if (!this.result) {
      return nothing
    }

    return html`
      <button
        class="toggle-btn"
        aria-expanded=${this.collapsed ? 'false' : 'true'}
        aria-label=${getString('panel-collapse-label')}
        @click=${this.toggleCollapsed}
      >${this.collapsed ? getString('panel-expand') : '\u00AB'}</button>
      <div class="panel-track">
        <div class="panel" role="region" aria-label="${getString('results-aria-label')}" aria-live="polite">
          <h2>${this.result.word} ${this.renderRarityBadge(this.result.rarity)}</h2>
          ${this.result.senses.map(s => this.renderSense(s))}
        </div>
      </div>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'mf-results-panel': MfResultsPanel
  }
}
