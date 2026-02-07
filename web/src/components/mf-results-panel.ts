import { LitElement, html, css, nothing } from 'lit'
import { customElement, property } from 'lit/decorators.js'
import type { LookupResult, Sense, RelatedWord } from '@/types/api'

@customElement('mf-results-panel')
export class MfResultsPanel extends LitElement {
  static styles = css`
    :host {
      display: block;
      position: absolute;
      top: var(--space-xl, 2rem);
      left: var(--space-md, 1rem);
      bottom: var(--space-xl, 2rem);
      width: var(--hud-width, 320px);
      z-index: 10;
      overflow-y: auto;
      scrollbar-width: thin;
      scrollbar-color: var(--colour-accent-gold-dim) transparent;
    }

    .panel {
      background: var(--colour-bg-hud, rgba(22, 33, 62, 0.6));
      border: var(--hud-border, 1px solid rgba(212, 175, 55, 0.2));
      border-radius: var(--hud-radius, 4px);
      backdrop-filter: blur(8px);
      padding: var(--space-md, 1rem);
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
  `

  @property({ type: Object }) result: LookupResult | null = null

  private handleWordDblClick(word: string) {
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
    navigator.clipboard.writeText(word)
    this.dispatchEvent(
      new CustomEvent('mf-word-copy', {
        detail: { word },
        bubbles: true,
        composed: true,
      }),
    )
  }

  private renderWordChip(rw: RelatedWord, type: string) {
    return html`
      <span
        class="word-chip ${type}"
        data-word=${rw.word}
        @dblclick=${() => this.handleWordDblClick(rw.word)}
        @contextmenu=${(e: MouseEvent) => this.handleWordRightClick(e, rw.word)}
        title="Double-click to navigate, right-click to copy"
      >${rw.word}</span>
    `
  }

  private renderSense(sense: Sense) {
    return html`
      <div class="sense">
        <span class="pos-badge">${sense.pos}</span>
        <div class="definition">${sense.definition}</div>

        ${sense.synonyms.length
          ? html`
              <div class="section-label">Synonyms</div>
              <div class="word-list">
                ${sense.synonyms.map(s => this.renderWordChip(s, 'synonym'))}
              </div>
            `
          : nothing}

        ${sense.relations.hypernyms.length
          ? html`
              <div class="section-label">Broader terms</div>
              <div class="word-list">
                ${sense.relations.hypernyms.map(h => this.renderWordChip(h, 'hypernym'))}
              </div>
            `
          : nothing}

        ${sense.relations.hyponyms.length
          ? html`
              <div class="section-label">Narrower terms</div>
              <div class="word-list">
                ${sense.relations.hyponyms.map(h => this.renderWordChip(h, 'hyponym'))}
              </div>
            `
          : nothing}

        ${sense.relations.similar.length
          ? html`
              <div class="section-label">Similar</div>
              <div class="word-list">
                ${sense.relations.similar.map(s => this.renderWordChip(s, 'similar'))}
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
      <div class="panel" role="region" aria-label="Thesaurus results">
        <h2>${this.result.word}</h2>
        ${this.result.senses.map(s => this.renderSense(s))}
      </div>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'mf-results-panel': MfResultsPanel
  }
}
