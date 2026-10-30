import { LitElement, html, css, nothing, type PropertyValues } from 'lit'
import { customElement, property } from 'lit/decorators.js'
import { getString } from '@/lib/strings'
import type { ForestEndpoint, ForestResponse } from '@/types/api'
import { LIVE_SCORE, pathKey, pathTarget, type ForestTarget } from '@/graph/forest'
import { MAX_HOPS, MIN_HOPS, inFlight, initialForestState, sameTarget, type ForestEvent, type ForestState } from '@/forest/state'

const HOP_OPTIONS = Array.from({ length: MAX_HOPS - MIN_HOPS + 1 }, (_, i) => MIN_HOPS + i)

/**
 * The metaphor forest panel: the accessible surface for the forest. Every graph
 * gesture has an equivalent here (hover or focus an item to light its path,
 * Highlight path to keep it lit, Look up to navigate), and it works with no
 * graph at all. Presentational: it renders a ForestState and emits the
 * reducer's UI events as `mf-forest-event`; mf-app owns the state.
 */
@customElement('mf-forest-panel')
export class MfForestPanel extends LitElement {
  static styles = css`
    :host {
      position: absolute;
      top: calc(var(--space-md, 1rem) + 3.5rem);
      inset-inline-end: var(--space-md, 1rem);
      width: min(23rem, calc(100% - 2 * var(--space-md, 1rem)));
      /* --progress-reserve: room mf-app keeps clear for the activity panel below. */
      max-height: calc(100% - 3.5rem - 3 * var(--space-md, 1rem) - var(--progress-reserve, 0px));
      z-index: 25;
      display: flex;
      background: var(--colour-panel-deep);
      border: 1px solid var(--colour-forest-branch-faint);
      border-block-start: 2px solid var(--colour-forest-branch-dim);
      border-radius: var(--hud-radius, 4px);
      backdrop-filter: blur(10px);
      color: var(--colour-text-primary);
      font-family: var(--font-body);
      font-size: 0.9rem;
      line-height: 1.45;
    }

    section {
      flex: 1;
      min-height: 0;
      display: flex;
      flex-direction: column;
    }

    .head {
      padding: var(--space-md, 1rem) var(--space-md, 1rem) 0;
    }

    .title-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: var(--space-sm, 0.5rem);
    }

    h2 {
      margin: 0;
      font-family: var(--font-heading);
      font-size: 1.25rem;
      font-weight: 400;
      color: var(--colour-accent-gold);
    }

    h2:focus { outline: none; }
    h2:focus-visible { outline: 2px solid var(--colour-forest-branch); outline-offset: 2px; }

    .controls {
      display: flex;
      flex-wrap: wrap;
      align-items: flex-end;
      gap: var(--space-sm, 0.5rem);
      margin-block-start: var(--space-sm, 0.5rem);
    }

    .steps {
      display: flex;
      flex-direction: column;
      gap: var(--space-xs, 0.25rem);
    }

    .steps label, .on-graph {
      font-size: 0.8rem;
      color: var(--colour-text-secondary);
    }

    select, button {
      font: inherit;
      min-height: 2.75rem;
      border-radius: var(--hud-radius, 4px);
      cursor: pointer;
    }

    select {
      min-width: 6.5rem;
      padding-inline: var(--space-sm, 0.5rem);
      background: var(--colour-bg-secondary);
      color: var(--colour-text-primary);
      border: 1px solid var(--colour-forest-branch-dim);
    }

    .primary {
      min-width: 7.5rem;
      padding-inline: var(--space-lg, 1.5rem);
      background: var(--colour-accent-gold);
      color: var(--colour-bg-primary);
      border: 1px solid var(--colour-accent-gold);
      font-family: var(--font-heading);
      font-size: 1.05rem;
      letter-spacing: 0.02em;
    }

    .primary[aria-disabled='true'] {
      cursor: progress;
      background: transparent;
      color: var(--colour-accent-gold);
    }

    .secondary {
      padding-inline: var(--space-md, 1rem);
      background: transparent;
      color: var(--colour-text-primary);
      border: 1px solid var(--colour-forest-branch-dim);
    }

    .secondary:hover, select:hover { border-color: var(--colour-forest-branch); }

    .on-graph {
      display: inline-flex;
      align-items: center;
      gap: var(--space-sm, 0.5rem);
      min-height: 2.75rem;
      cursor: pointer;
    }

    .on-graph input {
      inline-size: 1.1rem;
      block-size: 1.1rem;
      accent-color: var(--colour-forest-branch);
      margin: 0;
    }

    :focus-visible {
      outline: 2px solid var(--colour-forest-branch);
      outline-offset: 2px;
    }

    .status, .alert {
      margin-block-start: var(--space-sm, 0.5rem);
    }

    .status:empty, .alert:empty { display: none; }

    .status {
      display: flex;
      gap: var(--space-sm, 0.5rem);
      align-items: baseline;
      color: var(--colour-text-secondary);
    }

    .alert {
      padding: var(--space-sm, 0.5rem) var(--space-md, 1rem);
      border-inline-start: 2px solid var(--colour-alert-text);
      background: var(--colour-alert-bg);
      color: var(--colour-alert-text);
    }

    .ring {
      flex: none;
      inline-size: 0.8rem;
      block-size: 0.8rem;
      border-radius: 50%;
      border: 2px solid var(--colour-forest-branch-dim);
      border-block-start-color: var(--colour-forest-branch);
    }

    @media (prefers-reduced-motion: no-preference) {
      .ring { animation: spin 1s linear infinite; }
      .item { transition: background-color 140ms ease, border-color 140ms ease; }
    }

    @keyframes spin { to { transform: rotate(360deg); } }

    .intro {
      margin-block-start: var(--space-sm, 0.5rem);
      color: var(--colour-text-secondary);
    }

    .sheet-toggle { display: none; }

    .body {
      flex: 1;
      min-height: 0;
      overflow-y: auto;
      padding: var(--space-sm, 0.5rem) var(--space-md, 1rem) var(--space-md, 1rem);
      scrollbar-width: thin;
      scrollbar-color: var(--colour-forest-branch-dim) transparent;
    }

    .legend {
      margin: 0 0 var(--space-sm, 0.5rem);
      font-size: 0.8rem;
      color: var(--colour-text-secondary);
    }

    .legend-mark, .live-mark { color: var(--colour-forest-live); }

    .list {
      list-style: none;
      margin: 0;
      padding: 0;
    }

    .item {
      padding: var(--space-sm, 0.5rem) var(--space-sm, 0.5rem) var(--space-sm, 0.5rem) var(--space-md, 1rem);
      border-inline-start: 2px solid transparent;
      border-block-end: 1px solid var(--colour-forest-branch-faint);
    }

    .item:last-child { border-block-end: none; }

    .item[data-lit] {
      border-inline-start-color: var(--colour-forest-branch);
      background: var(--colour-forest-branch-faint);
    }

    .item-head {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: var(--space-sm, 0.5rem);
    }

    h3 {
      margin: 0;
      font-family: var(--font-heading);
      font-size: 1.05rem;
      font-weight: 400;
      color: var(--colour-forest-endpoint);
    }

    .score {
      flex: none;
      font-size: 0.8rem;
      color: var(--colour-text-secondary);
      font-variant-numeric: tabular-nums;
    }

    .live {
      color: var(--colour-forest-live);
      margin-inline-end: var(--space-xs, 0.25rem);
    }

    .line {
      margin: var(--space-xs, 0.25rem) 0 var(--space-sm, 0.5rem);
      font-size: 1.05rem;
      font-style: italic;
      line-height: 1.4;
    }

    /* The path as a branch: a cyan rail through the words, each ground set
       between the two words it joins. Mirrors the graph. */
    .path {
      list-style: none;
      margin: 0;
      padding: 0;
      font-size: 0.8rem;
    }

    .path > li {
      position: relative;
      padding-inline-start: 1.1rem;
    }

    .path > li::before {
      content: '';
      position: absolute;
      inset-inline-start: 0.2rem;
      inset-block-start: 0.45em;
      inline-size: 0.45rem;
      block-size: 0.45rem;
      border-radius: 50%;
      border: 1px solid var(--colour-forest-hop);
      background: var(--colour-panel-deep);
    }

    .path > li:first-child::before {
      background: var(--colour-accent-gold);
      border-color: var(--colour-accent-gold);
    }

    .path > li:last-child::before {
      background: var(--colour-forest-endpoint);
      border-color: var(--colour-forest-endpoint);
      box-shadow: 0 0 6px var(--colour-forest-branch);
    }

    .path > li:not(:last-child)::after {
      content: '';
      position: absolute;
      inset-inline-start: calc(0.2rem + 0.225rem - 0.5px);
      inset-block: calc(0.45em + 0.5rem) -0.45em;
      inline-size: 1px;
      background: var(--colour-forest-branch-dim);
    }

    .word { color: var(--colour-text-primary); }

    .ground {
      display: block;
      padding-block: 0.1rem 0.2rem;
      font-style: italic;
      color: var(--colour-forest-ground);
    }

    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: var(--space-sm, 0.5rem);
      margin-block-start: var(--space-sm, 0.5rem);
    }

    .actions button {
      padding-inline: var(--space-md, 1rem);
      background: transparent;
      color: var(--colour-text-secondary);
      border: 1px solid var(--colour-forest-branch-faint);
      font-size: 0.8rem;
    }

    .actions button:hover {
      color: var(--colour-text-primary);
      border-color: var(--colour-forest-branch-dim);
    }

    .actions button[aria-pressed='true'] {
      color: var(--colour-bg-primary);
      background: var(--colour-forest-branch);
      border-color: var(--colour-forest-branch);
    }

    .vh {
      position: absolute;
      inline-size: 1px;
      block-size: 1px;
      overflow: hidden;
      clip-path: inset(50%);
      white-space: nowrap;
    }

    /* Phone: a bottom sheet. The bar (heading, controls, status) is always
       there, so Forge is one tap away; the list opens on demand. */
    @media (max-width: 768px) {
      :host {
        position: fixed;
        top: auto;
        inset-inline: 0;
        inset-block-end: 0;
        width: auto;
        max-height: 75dvh;
        border-radius: 10px 10px 0 0;
        border-inline: none;
        border-block-end: none;
        padding-block-end: env(safe-area-inset-bottom, 0);
      }

      .head { padding-block-start: var(--space-sm, 0.5rem); }

      .sheet-toggle {
        display: inline-block;
        padding-inline: var(--space-md, 1rem);
        background: transparent;
        color: var(--colour-forest-branch);
        border: 1px solid var(--colour-forest-branch-dim);
        font-size: 0.8rem;
      }

      :host(:not([sheet-open])) .body[data-has-list] { display: none; }
    }
  `

  @property({ attribute: false }) state: ForestState = initialForestState()
  @property({ attribute: false }) lit: ReadonlySet<string> | null = null
  // Phone layout only; ignored by the desktop styles.
  @property({ type: Boolean, reflect: true, attribute: 'sheet-open' }) sheetOpen = false

  private focusPrimaryAfterUpdate = false
  private focusHeadingAfterUpdate = false

  protected willUpdate(changed: PropertyValues<this>): void {
    if (!changed.has('state')) return
    const prev = changed.get('state') as ForestState | undefined
    const response = this.forestResponse(this.state)
    // A stream's later snapshots and its final forest only add to the first,
    // so they never reopen a sheet the user closed.
    const sameStream = prev?.request.kind === 'streaming' && !!prev.request.snapshot && !!this.forestResponse(prev)
    if (response && response !== (prev && this.forestResponse(prev)) && !sameStream) this.sheetOpen = true
    if (!response) this.sheetOpen = false
    // The control that had focus is about to disappear.
    const active = this.shadowRoot?.activeElement
    if (prev && prev.word !== this.state.word && active) this.focusHeadingAfterUpdate = true
    else if (prev && inFlight(prev) && !inFlight(this.state) && active?.matches('[data-testid="forest-cancel"]')) {
      this.focusPrimaryAfterUpdate = true
    }
  }

  protected updated(): void {
    // Set after render: a select's value only sticks once its options exist.
    const select = this.shadowRoot!.querySelector<HTMLSelectElement>('#forest-steps')
    if (select) select.value = String(this.state.maxHops)
    if (this.focusPrimaryAfterUpdate) this.shadowRoot!.querySelector<HTMLElement>('[data-testid="forest-primary"]')?.focus()
    if (this.focusHeadingAfterUpdate) this.shadowRoot!.querySelector<HTMLElement>('h2')?.focus()
    this.focusPrimaryAfterUpdate = this.focusHeadingAfterUpdate = false
  }

  private forestResponse(s: ForestState): ForestResponse | null {
    return s.content.kind === 'forest' ? s.content.response : null
  }

  private emit(event: ForestEvent): void {
    this.dispatchEvent(new CustomEvent('mf-forest-event', { detail: event, bubbles: true, composed: true }))
  }

  private onPrimary(): void {
    if (inFlight(this.state)) return
    this.emit({ type: 'forge' })
  }

  private onCancel(): void {
    this.emit({ type: 'cancel' })
    // The prop update that removes Cancel may land after this handler.
    this.focusPrimaryAfterUpdate = true
  }

  private onKeydown(e: KeyboardEvent): void {
    if (e.key !== 'Escape') return
    if (this.state.selection) {
      this.emit({ type: 'select', target: null })
    } else if (this.sheetOpen) {
      this.sheetOpen = false
      this.updateComplete.then(() => this.shadowRoot!.querySelector<HTMLElement>('[data-testid="forest-sheet-toggle"]')?.focus())
    }
  }

  private pathTarget(e: ForestEndpoint): ForestTarget {
    return pathTarget(e)
  }

  private statusText(): string {
    const { request, content, notice, word } = this.state
    const kept = content.kind === 'forest'
    if (request.kind === 'streaming') return getString('forest-streaming', { n: request.snapshot?.endpoints.length ?? 0 })
    if (request.kind === 'loading') return kept ? getString('forest-loading-kept', { word }) : getString('forest-loading', { word })
    if (notice === 'found' && kept) {
      const endpoints = content.response.endpoints
      return getString('forest-found', { n: endpoints.length, live: endpoints.filter(e => e.score >= LIVE_SCORE).length, word })
    }
    if (notice === 'empty-kept') return getString('forest-empty-kept')
    if (notice === 'cancelled') return kept ? getString('forest-cancelled-kept') : getString('forest-cancelled')
    if (content.kind === 'empty') return getString('forest-empty', { word, generated: content.response.stats.generated })
    return ''
  }

  private alertText(): string {
    const { request, content, word } = this.state
    if (request.kind !== 'failed') return ''
    const message = request.error === 'busy'
      ? request.retryAfterSeconds
        ? getString('forest-error-busy', { seconds: request.retryAfterSeconds })
        : getString('forest-error-busy-soon')
      : getString(`forest-error-${request.error}`, { word })
    return content.kind === 'forest' ? `${message} ${getString('forest-error-kept')}` : message
  }

  private renderItem(e: ForestEndpoint) {
    const target = this.pathTarget(e)
    const pressed = sameTarget(this.state.selection, target)
    const live = e.score >= LIVE_SCORE
    return html`
      <li
        class="item"
        data-testid="forest-item"
        ?data-lit=${this.lit?.has(pathKey(e)) ?? false}
        @pointerenter=${(ev: PointerEvent) => { if (ev.pointerType !== 'touch') this.emit({ type: 'hover', target }) }}
        @pointerleave=${(ev: PointerEvent) => { if (ev.pointerType !== 'touch') this.emit({ type: 'hover', target: null }) }}
        @focusin=${() => this.emit({ type: 'focus', target })}
        @focusout=${(ev: FocusEvent) => {
          // Moving between this item's own buttons keeps its path lit.
          if (!(ev.currentTarget as HTMLElement).contains(ev.relatedTarget as Node | null)) this.emit({ type: 'focus', target: null })
        }}
      >
        <div class="item-head">
          <h3>${e.id}</h3>
          <span class="score">
            ${live ? html`<span class="live"><span class="live-mark" aria-hidden="true">✦ </span>${getString('forest-live')}</span>` : nothing}
            <span aria-hidden="true">${e.score}/10</span>
            <span class="vh">${getString('forest-score', { score: e.score })}</span>
          </span>
        </div>
        <p class="line">${e.line}</p>
        <ol class="path" aria-label=${getString('forest-path-label', { source: e.path[0], endpoint: e.id })}>
          ${e.path.map((word, i) => html`
            <li>
              <span class="word">${word}</span>
              ${i < e.grounds.length
                ? html`<span class="ground"><span class="vh">${getString('forest-joined-by')} </span><span class="ground-text">${e.grounds[i]}</span></span>`
                : nothing}
            </li>`)}
        </ol>
        <div class="actions">
          <button
            data-testid="forest-highlight"
            aria-pressed=${pressed ? 'true' : 'false'}
            aria-label=${getString('forest-highlight-name', { endpoint: e.id })}
            @click=${() => this.emit({ type: 'select', target })}
          >${getString('forest-highlight')}</button>
          <button
            data-testid="forest-lookup"
            aria-label=${getString('forest-lookup-name', { endpoint: e.id })}
            @click=${() => this.dispatchEvent(new CustomEvent('mf-forest-lookup', { detail: { word: e.id }, bubbles: true, composed: true }))}
          >${getString('forest-lookup')}</button>
        </div>
      </li>`
  }

  render() {
    const { request, content, word, onGraph } = this.state
    const loadingNow = inFlight(this.state)
    const response = this.forestResponse(this.state)
    const status = this.statusText()

    return html`
      <section aria-labelledby="forest-heading" @keydown=${this.onKeydown}>
      <div class="head">
        <div class="title-row">
          <h2 id="forest-heading" tabindex="-1">${getString('forest-heading')}</h2>
          ${response
            ? html`<button
                class="sheet-toggle"
                data-testid="forest-sheet-toggle"
                aria-expanded=${this.sheetOpen ? 'true' : 'false'}
                aria-controls="forest-body"
                @click=${() => { this.sheetOpen = !this.sheetOpen }}
              >${this.sheetOpen ? getString('forest-sheet-hide') : getString('forest-sheet-show', { n: response.endpoints.length })}</button>`
            : nothing}
        </div>

        <div class="controls">
          <div class="steps">
            <label for="forest-steps">${getString('forest-max-steps')}</label>
            <select
              id="forest-steps"
              @change=${(e: Event) => this.emit({ type: 'set-max-hops', maxHops: Number((e.target as HTMLSelectElement).value) })}
            >
              ${HOP_OPTIONS.map(n => html`<option value=${n}>${getString('forest-steps-option', { n })}</option>`)}
            </select>
          </div>
          <button
            class="primary"
            data-testid="forest-primary"
            aria-disabled=${loadingNow ? 'true' : 'false'}
            @click=${this.onPrimary}
          >${loadingNow ? getString('forest-forging') : content.kind === 'forest' ? getString('forest-forge-new') : getString('forest-forge')}</button>
          ${loadingNow
            ? html`<button class="secondary" data-testid="forest-cancel" @click=${this.onCancel}>${getString('forest-cancel')}</button>`
            : nothing}
        </div>

        ${response
          ? html`<label class="on-graph" for="forest-on-graph">
              <input
                id="forest-on-graph"
                type="checkbox"
                .checked=${onGraph}
                @change=${(e: Event) => this.emit({ type: 'set-on-graph', onGraph: (e.target as HTMLInputElement).checked })}
              >${getString('forest-show-on-graph')}
            </label>`
          : nothing}

        <div class="status" role="status" aria-live="polite" aria-atomic="true">${status
          ? html`${loadingNow ? html`<span class="ring" aria-hidden="true"></span>` : nothing}<span>${status}</span>`
          : nothing}</div>
        <div class="alert" role="alert">${this.alertText()}</div>
      </div>

      <div
        class="body"
        id="forest-body"
        data-testid="forest-body"
        ?data-has-list=${!!response}
      >
        ${response
          ? html`
            <p class="legend"><span class="legend-mark" aria-hidden="true">✦ </span>${getString('forest-legend')}</p>
            <ol class="list" aria-label=${getString('forest-list-label', { word })}>
              ${response.endpoints.map(e => this.renderItem(e))}
            </ol>`
          : content.kind === 'none' && request.kind === 'idle'
            ? html`<p class="intro">${getString('forest-intro', { word })}</p>`
            : nothing}
      </div>
      </section>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'mf-forest-panel': MfForestPanel
  }
}
