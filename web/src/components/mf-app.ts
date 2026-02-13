import { LitElement, html, css } from 'lit'
import { customElement, state } from 'lit/decorators.js'
import { lookupWord, ApiError } from '@/api/client'
import { transformLookupToGraph } from '@/graph/transform'
import { initStrings, getString } from '@/lib/strings'
import type { LookupResult } from '@/types/api'
import type { GraphData } from '@/graph/types'
import type { MfToast } from './mf-toast'

// Import components so they register
import './mf-search-bar'
import './mf-force-graph'
import './mf-results-panel'
import './mf-toast'

type AppState = 'idle' | 'loading' | 'ready' | 'error'

@customElement('mf-app')
export class MfApp extends LitElement {
  static styles = css`
    :host {
      display: block;
      width: 100vw;
      height: 100vh;
      position: relative;
      overflow: hidden;
      background: var(--colour-bg-primary, #1a1a2e);
    }

    .search-container {
      position: absolute;
      top: var(--space-md, 1rem);
      left: 50%;
      transform: translateX(-50%);
      width: min(480px, calc(100% - 2rem));
      z-index: 20;
    }

    mf-force-graph {
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      z-index: 1;
    }

    mf-results-panel {
      z-index: 10;
    }

    .status-message {
      position: absolute;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      color: var(--colour-text-muted, #6b6560);
      font-family: var(--font-body, serif);
      font-size: 1.1rem;
      text-align: center;
      z-index: 5;
    }

    .error-message {
      color: #c47a7a;
    }

    .loading-ring {
      width: 40px;
      height: 40px;
      border: 3px solid var(--colour-accent-gold-dim, rgba(212, 175, 55, 0.3));
      border-top-color: var(--colour-accent-gold, #d4af37);
      border-radius: 50%;
      animation: spin 1s linear infinite;
      margin: 0 auto var(--space-md, 1rem);
    }

    @keyframes spin {
      to { transform: rotate(360deg); }
    }

    .rarity-filters {
      position: absolute;
      top: calc(var(--space-md, 1rem) + 48px);
      left: 50%;
      transform: translateX(-50%);
      display: flex;
      gap: var(--space-sm, 0.5rem);
      z-index: 20;
    }

    .rarity-toggle {
      display: flex;
      align-items: center;
      gap: 4px;
      font-size: 0.75rem;
      color: var(--colour-text-secondary, #a89f94);
      cursor: pointer;
    }

    .rarity-toggle input {
      accent-color: var(--colour-accent-gold, #d4af37);
    }

    .rarity-toggle.common { color: #8bb89a; }
    .rarity-toggle.unusual { color: #c4956a; }
    .rarity-toggle.rare { color: #a88bc4; }
  `

  @state() private appState: AppState = 'idle'
  @state() private result: LookupResult | null = null
  @state() private graphData: GraphData = { nodes: [], links: [] }
  @state() private errorMessage = ''
  @state() private showCommon = true
  @state() private showUnusual = true
  @state() private showRare = true

  private get filteredGraphData(): GraphData {
    if (this.showCommon && this.showUnusual && this.showRare) {
      return this.graphData
    }

    const visibleNodes = this.graphData.nodes.filter(node => {
      if (node.relationType === 'central') return true
      const rarity = node.rarity ?? 'unusual'
      if (rarity === 'common' && !this.showCommon) return false
      if (rarity === 'unusual' && !this.showUnusual) return false
      if (rarity === 'rare' && !this.showRare) return false
      return true
    })

    const visibleIds = new Set(visibleNodes.map(n => n.id))
    const visibleLinks = this.graphData.links.filter(
      link => visibleIds.has(link.source as string) && visibleIds.has(link.target as string),
    )

    return { nodes: visibleNodes, links: visibleLinks }
  }

  async connectedCallback(): Promise<void> {
    super.connectedCallback()
    await initStrings()
    this.requestUpdate() // re-render now that strings are loaded

    // Check URL hash for initial word
    const hashWord = this.getWordFromHash()
    if (hashWord) {
      this.doLookup(hashWord)
    }

    window.addEventListener('hashchange', this.handleHashChange)
  }

  disconnectedCallback(): void {
    super.disconnectedCallback()
    window.removeEventListener('hashchange', this.handleHashChange)
  }

  private handleHashChange = () => {
    const word = this.getWordFromHash()
    if (word) {
      this.doLookup(word)
    }
  }

  private getWordFromHash(): string | null {
    const match = window.location.hash.match(/^#\/word\/(.+)$/)
    return match ? decodeURIComponent(match[1]) : null
  }

  private setWordHash(word: string) {
    const newHash = `#/word/${encodeURIComponent(word)}`
    if (window.location.hash !== newHash) {
      window.location.hash = newHash
    }
  }

  private async handleSearch(e: CustomEvent<{ word: string }>) {
    this.doLookup(e.detail.word)
  }

  private async handleNodeNavigate(e: CustomEvent<{ word: string }>) {
    const node = e.detail
    if (node.word) {
      this.doLookup(node.word)
    }
  }

  private handleWordNavigate(e: CustomEvent<{ word: string }>) {
    this.doLookup(e.detail.word)
  }

  private handleCopy(e: CustomEvent<{ word: string }>) {
    const toast = this.shadowRoot?.querySelector('mf-toast') as MfToast | null
    toast?.show(getString('toast-copied', { word: e.detail.word }))
  }

  private async doLookup(word: string) {
    this.appState = 'loading'
    this.errorMessage = ''

    try {
      const result = await lookupWord(word)
      this.result = result
      this.graphData = transformLookupToGraph(result)
      this.appState = 'ready'
      this.setWordHash(word)
    } catch (err) {
      this.appState = 'error'
      if (err instanceof ApiError && err.status === 404) {
        this.errorMessage = getString('results-word-not-found', { word })
      } else {
        this.errorMessage = getString('error-generic')
      }
    }
  }

  render() {
    return html`
      <div class="search-container">
        <mf-search-bar
          .placeholder=${getString('search-placeholder')}
          .searchLabel=${getString('search-aria-label')}
          @mf-search=${this.handleSearch}
        ></mf-search-bar>
      </div>

      <div role="status" aria-live="polite" aria-atomic="true">
        ${this.appState === 'loading'
          ? html`
              <div class="status-message">
                <div class="loading-ring"></div>
                ${getString('status-loading')}
              </div>
            `
          : ''}

        ${this.appState === 'error'
          ? html`<div class="status-message error-message">${this.errorMessage}</div>`
          : ''}

        ${this.appState === 'idle'
          ? html`<div class="status-message">${getString('status-idle')}</div>`
          : ''}
      </div>

      ${this.appState === 'ready'
        ? html`
            <div class="rarity-filters" role="group" aria-label="${getString('filter-aria-label')}">
              <label class="rarity-toggle common">
                <input type="checkbox" .checked=${this.showCommon}
                  @change=${(e: Event) => { this.showCommon = (e.target as HTMLInputElement).checked }}>
                ${getString('filter-common')}
              </label>
              <label class="rarity-toggle unusual">
                <input type="checkbox" .checked=${this.showUnusual}
                  @change=${(e: Event) => { this.showUnusual = (e.target as HTMLInputElement).checked }}>
                ${getString('filter-unusual')}
              </label>
              <label class="rarity-toggle rare">
                <input type="checkbox" .checked=${this.showRare}
                  @change=${(e: Event) => { this.showRare = (e.target as HTMLInputElement).checked }}>
                ${getString('filter-rare')}
              </label>
            </div>
          `
        : ''}

      <mf-force-graph
        .graphData=${this.filteredGraphData}
        @mf-node-select=${() => {}}
        @mf-node-navigate=${this.handleNodeNavigate}
        @mf-node-copy=${this.handleCopy}
      ></mf-force-graph>

      <mf-results-panel
        .result=${this.result}
        @mf-word-navigate=${this.handleWordNavigate}
        @mf-word-copy=${this.handleCopy}
      ></mf-results-panel>

      <mf-toast></mf-toast>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'mf-app': MfApp
  }
}
