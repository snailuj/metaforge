import { LitElement, html, css, nothing, type PropertyValues } from 'lit'
import { customElement, property, state } from 'lit/decorators.js'
import { getString } from '@/lib/strings'
import { initialProgress, isBusy, pendingOf, type ProgressLine, type ProgressState } from '@/progress/model'

/** How long each collapsed label shows while work is pending. */
export const LABEL_CYCLE_MS = 1500
const STORAGE_KEY = 'mf-progress-open'
const FAILURES: ReadonlySet<ProgressLine['kind']> = new Set(['lookup-failed', 'nearby-failed', 'expand-failed', 'forest-failed'])

/** The collapsed label; cycles on a timer, not with the stage (the log carries the stage). */
function label(i: number): string {
  switch (i % 4) {
    case 0: return getString('progress-label-foraging')
    case 1: return getString('progress-label-forging')
    case 2: return getString('progress-label-fording')
    default: return getString('progress-label-foresting')
  }
}

function lineText(l: ProgressLine): string {
  switch (l.kind) {
    case 'lookup': return getString('progress-line-lookup', { word: l.word, senses: l.senses, words: l.words })
    case 'lookup-failed': return getString('progress-line-lookup-failed', { word: l.word })
    case 'nearby': return getString('progress-line-nearby', { done: l.done, total: l.total })
    case 'nearby-failed': return getString('progress-line-nearby-failed', { n: l.n })
    case 'expanded': return getString('progress-line-expanded', { word: l.word, words: l.words })
    case 'expand-failed': return getString('progress-line-expand-failed', { word: l.word })
    case 'forging': return getString('progress-line-forging', { drafted: l.drafted, kept: l.kept, dropped: l.dropped })
    case 'retrying': return getString('progress-line-retrying')
    case 'judging': return getString('progress-line-judging', { word: l.word })
    case 'forest-ready': return getString('progress-line-forest-ready', { n: l.n })
    case 'forest-failed': return getString('progress-line-forest-failed')
    case 'forest-cancelled': return getString('progress-line-forest-cancelled')
    case 'all-loaded': return getString('progress-line-all-loaded')
  }
}

function readOpen(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === '1'
  } catch (err) {
    console.warn('[progress] could not read the remembered panel state; starting closed', err)
    return false
  }
}

function writeOpen(open: boolean): void {
  try {
    localStorage.setItem(STORAGE_KEY, open ? '1' : '0')
  } catch (err) {
    console.warn('[progress] could not remember the panel state', err)
  }
}

/**
 * The activity panel: what is still loading and a log of what has. Collapsed it
 * is one button (a throbber and a cycling label while work is pending, "Activity"
 * when idle); expanded it adds a summary and the log above the button. New log
 * lines are announced politely, failures as alerts; the label never is.
 * Presentational: mf-app owns the ProgressState. It emits `mf-progress-toggle`
 * so the forest panel can make room.
 */
@customElement('mf-progress-panel')
export class MfProgressPanel extends LitElement {
  static styles = css`
    :host {
      position: absolute;
      inset-inline-end: var(--space-md, 1rem);
      inset-block-end: var(--space-md, 1rem);
      z-index: 24;
      display: flex;
      flex-direction: column;
      align-items: flex-end;
      gap: var(--space-sm, 0.5rem);
      max-inline-size: calc(100% - 2 * var(--space-md, 1rem));
      color: var(--colour-text-primary);
      font-family: var(--font-body);
      font-size: 0.85rem;
      line-height: 1.45;
    }

    [hidden] { display: none !important; }

    .panel {
      box-sizing: border-box;
      inline-size: min(23rem, 100%);
      max-block-size: var(--progress-panel-max, 16rem);
      overflow-y: auto;
      padding: var(--space-sm, 0.5rem) var(--space-md, 1rem) var(--space-md, 1rem);
      background: var(--colour-panel-deep);
      border: 1px solid var(--colour-forest-branch-faint);
      border-radius: var(--hud-radius, 4px);
      backdrop-filter: blur(10px);
      scrollbar-width: thin;
      scrollbar-color: var(--colour-forest-branch-dim) transparent;
    }

    h2 {
      margin: 0 0 var(--space-xs, 0.25rem);
      font-family: var(--font-heading);
      font-size: 1rem;
      font-weight: 400;
      color: var(--colour-accent-gold);
    }

    .summary {
      margin: 0 0 var(--space-sm, 0.5rem);
      color: var(--colour-text-secondary);
    }

    .log {
      margin: 0;
      padding-inline-start: 1.1rem;
    }

    .log li + li { margin-block-start: var(--space-xs, 0.25rem); }

    .log li[data-failure] { color: var(--colour-alert-text); }

    .toggle {
      display: inline-flex;
      align-items: center;
      gap: var(--space-sm, 0.5rem);
      min-block-size: 2.75rem;
      min-inline-size: 2.75rem;
      padding-inline: var(--space-md, 1rem);
      background: var(--colour-panel-deep);
      color: var(--colour-text-primary);
      border: 1px solid var(--colour-forest-branch-dim);
      border-radius: 999px;
      font: inherit;
      cursor: pointer;
    }

    .toggle:hover { border-color: var(--colour-forest-branch); }

    :focus-visible {
      outline: 2px solid var(--colour-forest-branch);
      outline-offset: 2px;
    }

    .panel:focus { outline: none; }

    .throbber {
      flex: none;
      inline-size: 0.8rem;
      block-size: 0.8rem;
      border-radius: 50%;
      border: 2px solid var(--colour-forest-branch-dim);
      border-block-start-color: var(--colour-forest-branch);
    }

    @media (prefers-reduced-motion: no-preference) {
      .throbber { animation: spin 1s linear infinite; }
    }

    @keyframes spin { to { transform: rotate(360deg); } }

    .vh {
      position: absolute;
      inline-size: 1px;
      block-size: 1px;
      overflow: hidden;
      clip-path: inset(50%);
      white-space: nowrap;
    }

    /* Phone: the collapsed control sits above the forest sheet; expanded, the
       panel is a sheet across the bottom, over the forest sheet. */
    @media (max-width: 768px) {
      :host {
        inset-inline-end: var(--space-sm, 0.5rem);
        inset-block-end: calc(var(--forest-sheet-height, 0px) + var(--space-sm, 0.5rem));
      }

      :host([open]) {
        position: fixed;
        inset-inline: 0;
        inset-block-end: 0;
        z-index: 27;
        max-inline-size: none;
        align-items: stretch;
        gap: 0;
        padding-block-end: env(safe-area-inset-bottom, 0);
        background: var(--colour-panel-deep);
        border-block-start: 1px solid var(--colour-forest-branch-dim);
        border-radius: 10px 10px 0 0;
      }

      :host([open]) .panel {
        inline-size: auto;
        max-block-size: 50dvh;
        border: none;
        background: transparent;
      }

      :host([open]) .toggle {
        margin: var(--space-sm, 0.5rem);
        align-self: flex-end;
      }
    }
  `

  @property({ attribute: false }) state: ProgressState = initialProgress()
  @property({ type: Boolean, reflect: true }) open = readOpen()
  @state() private labelIndex = 0
  @state() private announcement = ''
  @state() private alertText = ''

  private reducedMotion = false
  private cycleTimer: ReturnType<typeof setInterval> | null = null

  connectedCallback(): void {
    super.connectedCallback()
    this.reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
  }

  disconnectedCallback(): void {
    super.disconnectedCallback()
    this.stopCycle()
  }

  protected willUpdate(changed: PropertyValues<this>): void {
    if (!changed.has('state')) return
    // Announce the lines this state adds; a line updated in place is not news.
    const prev = changed.get('state') as ProgressState | undefined
    const before = new Set((prev?.lines ?? []).map(l => l.key))
    const added = this.state.lines.filter(l => !before.has(l.key))
    const news = added.filter(l => !FAILURES.has(l.kind)).map(lineText).join(' ')
    const failures = added.filter(l => FAILURES.has(l.kind)).map(lineText).join(' ')
    if (news) this.announcement = news
    if (failures) this.alertText = failures
  }

  protected updated(): void {
    const cycle = isBusy(this.state) && !this.reducedMotion
    if (cycle && !this.cycleTimer) {
      this.cycleTimer = setInterval(() => { this.labelIndex++ }, LABEL_CYCLE_MS)
    } else if (!cycle && this.cycleTimer) {
      this.stopCycle()
    }
  }

  private stopCycle(): void {
    if (this.cycleTimer) clearInterval(this.cycleTimer)
    this.cycleTimer = null
    this.labelIndex = 0
  }

  private setOpen(open: boolean): void {
    if (open === this.open) return
    this.open = open
    writeOpen(open)
    this.dispatchEvent(new CustomEvent('mf-progress-toggle', { detail: { open }, bubbles: true, composed: true }))
  }

  private onKeydown(e: KeyboardEvent): void {
    if (e.key !== 'Escape' || !this.open) return
    e.stopPropagation()
    this.setOpen(false)
    this.updateComplete.then(() => this.shadowRoot!.querySelector<HTMLElement>('[data-testid="progress-toggle"]')?.focus())
  }

  private summary(): string {
    const p = pendingOf(this.state)
    const items = [
      p.lookup !== null ? getString('progress-pending-lookup', { word: p.lookup }) : '',
      p.nearby > 0 ? getString('progress-pending-nearby', { n: p.nearby }) : '',
      p.expansions > 0 ? getString('progress-pending-opened', { n: p.expansions }) : '',
      p.forest ? getString('progress-pending-forest') : '',
    ].filter(Boolean)
    if (items.length) return getString('progress-summary', { items: new Intl.ListFormat('en-GB', { type: 'conjunction' }).format(items) })
    return this.state.lines.length ? getString('progress-summary-idle') : getString('progress-empty')
  }

  render() {
    const busy = isBusy(this.state)
    return html`
      <div @keydown=${this.onKeydown} style="display: contents">
        <section
          class="panel"
          id="progress-panel"
          data-testid="progress-panel"
          aria-labelledby="progress-heading"
          tabindex="-1"
          ?hidden=${!this.open}
        >
          <h2 id="progress-heading">${getString('progress-heading')}</h2>
          <p class="summary" data-testid="progress-summary">${this.summary()}</p>
          ${this.state.lines.length
            ? html`<ol class="log" aria-label=${getString('progress-log-label')}>
                ${this.state.lines.map(l => html`<li data-testid="progress-line" ?data-failure=${FAILURES.has(l.kind)}>${lineText(l)}</li>`)}
              </ol>`
            : nothing}
        </section>
        <button
          class="toggle"
          type="button"
          data-testid="progress-toggle"
          aria-expanded=${this.open ? 'true' : 'false'}
          aria-controls="progress-panel"
          aria-label=${busy ? getString('progress-toggle-busy') : nothing}
          @click=${() => this.setOpen(!this.open)}
        >${busy
          ? html`<span class="throbber" aria-hidden="true"></span><span aria-hidden="true">${label(this.labelIndex)}</span>`
          : getString('progress-toggle')}</button>
      </div>
      <div class="vh" role="status" aria-live="polite" aria-atomic="true">${this.announcement}</div>
      <div class="vh" role="alert">${this.alertText}</div>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'mf-progress-panel': MfProgressPanel
  }
}
