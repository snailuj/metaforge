import { LitElement, html, css, nothing, type PropertyValues } from 'lit'
import { customElement, property, state } from 'lit/decorators.js'
import { getString } from '@/lib/strings'
import { initialProgress, nearbyProgress, type ProgressState } from '@/progress/model'
import { lineText, summaryText } from '@/progress/text'

/** Nearby work that ends sooner than this never shows the card, so a fast
 *  (cached) batch does not flash it. */
export const SHOW_DELAY_MS = 250
const DOCK_MS = 700
const FADE_MS = 300
const PAGES = 4

type Phase = 'hidden' | 'waiting' | 'shown' | 'docking'

/**
 * The card over a locked graph while nearby words load: a book leafing through
 * its pages, what is still coming (the activity panel's summary) and how far the
 * nearby words have got. When the work ends it flies into the activity button,
 * so the user learns where the log lives, then emits `mf-lookup-docked`.
 * Presentational: mf-app owns the state, says when nearby work is active, locks
 * the graph, and supplies the button's rect.
 */
@customElement('mf-lookup-overlay')
export class MfLookupOverlay extends LitElement {
  static styles = css`
    :host {
      position: absolute;
      inset: 0;
      z-index: 23;
      display: grid;
      place-items: center;
      pointer-events: none;
      color: var(--colour-text-primary);
      font-family: var(--font-body);
      font-size: 0.9rem;
      line-height: 1.45;
    }

    .card {
      box-sizing: border-box;
      inline-size: min(22rem, calc(100% - 2 * var(--space-md, 1rem)));
      padding: var(--space-lg, 1.5rem) var(--space-lg, 1.5rem) var(--space-md, 1rem);
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: var(--space-sm, 0.5rem);
      text-align: center;
      background: var(--colour-panel-deep);
      border: 1px solid var(--colour-forest-branch-faint);
      border-radius: var(--hud-radius, 4px);
      box-shadow: 0 0 2.5rem var(--colour-forest-root-glow);
      backdrop-filter: blur(10px);
      transform-origin: center;
    }

    h2 {
      margin: var(--space-sm, 0.5rem) 0 0;
      font-family: var(--font-heading);
      font-size: 1.05rem;
      font-weight: 400;
      color: var(--colour-accent-gold);
    }

    p { margin: 0; }

    .summary { color: var(--colour-text-secondary); }

    .count {
      font-family: var(--font-mono);
      font-size: 0.75rem;
      color: var(--colour-text-muted);
    }

    .bar {
      inline-size: 100%;
      block-size: 3px;
      margin-block-start: var(--space-xs, 0.25rem);
      background: var(--colour-forest-branch-faint);
      border-radius: 2px;
      overflow: hidden;
    }

    .bar > span {
      display: block;
      block-size: 100%;
      background: linear-gradient(90deg, var(--colour-accent-gold-dim), var(--colour-accent-gold));
      transition: inline-size 300ms ease-out;
    }

    /* An open book seen from slightly above; pages lift off the right-hand
       side and settle on the left, one after another. */
    .book {
      position: relative;
      inline-size: 6.5rem;
      block-size: 4.25rem;
      perspective: 30rem;
      transform: rotateX(18deg);
      transform-style: preserve-3d;
    }

    .book::before {
      /* The cover, a little wider than the pages. */
      content: '';
      position: absolute;
      inset: -0.25rem -0.35rem;
      border-radius: 4px;
      background: linear-gradient(90deg, #4a3520, #6b4c2c 48%, #3a2914 50%, #6b4c2c 52%, #4a3520);
      border: 1px solid var(--colour-accent-gold-dim);
    }

    .leaf, .page {
      position: absolute;
      inset-block: 0;
      inline-size: 50%;
      box-sizing: border-box;
      /* Paper with faint ruled lines standing in for text. */
      background:
        repeating-linear-gradient(180deg, transparent 0 0.42rem, rgba(107, 101, 96, 0.35) 0.42rem 0.48rem) content-box,
        linear-gradient(90deg, #d9cfbf, #ece4d6);
      padding: 0.55rem 0.5rem;
    }

    .leaf.left { inset-inline-start: 0; border-radius: 2px 0 0 2px; }
    .leaf.right { inset-inline-start: 50%; border-radius: 0 2px 2px 0; }

    .page {
      inset-inline-start: 50%;
      transform-origin: left center;
      border-radius: 0 2px 2px 0;
    }

    @media (prefers-reduced-motion: no-preference) {
      .page {
        animation: leaf 2.4s cubic-bezier(0.45, 0, 0.3, 1) infinite;
        animation-delay: calc(var(--i) * 0.6s);
      }
    }

    @keyframes leaf {
      0% { transform: rotateY(0deg); filter: brightness(1); }
      12% { transform: rotateY(-25deg); filter: brightness(1.05); }
      40% { transform: rotateY(-178deg); filter: brightness(0.85); }
      85% { transform: rotateY(-178deg); filter: brightness(0.85); opacity: 1; }
      100% { transform: rotateY(-178deg); filter: brightness(0.85); opacity: 0; }
    }

    .vh {
      position: absolute;
      inline-size: 1px;
      block-size: 1px;
      overflow: hidden;
      clip-path: inset(50%);
      white-space: nowrap;
    }
  `

  @property({ attribute: false }) state: ProgressState = initialProgress()
  /** True while nearby words are owed and the graph is locked. */
  @property({ attribute: false }) active = false
  /** Where the card docks when the work ends: the activity button's rect. */
  @property({ attribute: false }) dockTarget: (() => DOMRect | null) | null = null
  @state() private phase: Phase = 'hidden'
  // The count to show while docking, once the state no longer has one.
  @state() private last: { done: number; total: number } = { done: 0, total: 0 }

  private reducedMotion = false
  private showTimer: ReturnType<typeof setTimeout> | null = null
  private dock: Animation | null = null

  connectedCallback(): void {
    super.connectedCallback()
    this.reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
  }

  disconnectedCallback(): void {
    super.disconnectedCallback()
    this.clearShowTimer()
    this.dock?.cancel()
  }

  protected willUpdate(changed: PropertyValues<this>): void {
    const nearby = nearbyProgress(this.state)
    if (nearby) this.last = nearby
    if (!changed.has('active')) return
    if (this.active) this.start()
    else this.end()
  }

  protected updated(changed: PropertyValues): void {
    if (changed.has('phase') && this.phase === 'docking') this.runDock()
  }

  private start(): void {
    if (this.phase === 'docking') {
      console.debug('[lookup-overlay] nearby work restarted mid-dock; staying')
      this.dock?.cancel()
      this.dock = null
      this.phase = 'shown'
      return
    }
    if (this.phase !== 'hidden') return
    this.phase = 'waiting'
    this.showTimer = setTimeout(() => {
      this.showTimer = null
      this.phase = 'shown'
      console.debug('[lookup-overlay] shown', this.last)
    }, SHOW_DELAY_MS)
  }

  private end(): void {
    if (this.phase === 'waiting') {
      this.clearShowTimer()
      this.phase = 'hidden'
      console.debug('[lookup-overlay] nearby work ended before the show delay')
    } else if (this.phase === 'shown') {
      this.phase = 'docking'
    }
  }

  private clearShowTimer(): void {
    if (this.showTimer) clearTimeout(this.showTimer)
    this.showTimer = null
  }

  /** Fly the card into the dock target (fade only under reduced motion). */
  private runDock(): void {
    const card = this.shadowRoot?.querySelector<HTMLElement>('.card')
    const to = this.dockTarget?.() ?? null
    if (!card || !to || typeof card.animate !== 'function') {
      console.debug('[lookup-overlay] nothing to dock into; going at once', { card: !!card, target: !!to })
      this.docked()
      return
    }
    let frames: Keyframe[]
    if (this.reducedMotion) {
      frames = [{ opacity: 1 }, { opacity: 0 }]
    } else {
      const from = card.getBoundingClientRect()
      const dx = to.left + to.width / 2 - (from.left + from.width / 2)
      const dy = to.top + to.height / 2 - (from.top + from.height / 2)
      const scale = from.width > 0 ? Math.max(0.05, to.width / from.width) : 0.1
      frames = [
        { transform: 'translate(0, 0) scale(1)', opacity: 1 },
        { transform: `translate(${dx * 0.15}px, ${dy * 0.15}px) scale(0.92)`, opacity: 1, offset: 0.25 },
        { transform: `translate(${dx}px, ${dy}px) scale(${scale})`, opacity: 0.15 },
      ]
    }
    const dock = card.animate(frames, {
      duration: this.reducedMotion ? FADE_MS : DOCK_MS,
      easing: 'cubic-bezier(0.55, 0, 0.75, 0.2)',
      fill: 'forwards',
    })
    this.dock = dock
    dock.finished.then(
      () => { if (this.dock === dock) this.docked() },
      () => console.debug('[lookup-overlay] dock cancelled'),
    )
  }

  private docked(): void {
    this.dock = null
    this.phase = 'hidden'
    console.debug('[lookup-overlay] docked into activity')
    this.dispatchEvent(new CustomEvent('mf-lookup-docked', { bubbles: true, composed: true }))
  }

  render() {
    const visible = this.phase === 'shown' || this.phase === 'docking'
    if (!visible) return html`<div class="vh" role="status"></div>`
    const { done, total } = this.phase === 'docking' ? { done: this.last.total, total: this.last.total } : this.last
    const pct = total > 0 ? Math.round((done / total) * 100) : 0
    return html`
      <section class="card" data-testid="lookup-overlay" aria-labelledby="lookup-heading">
        <div class="book" aria-hidden="true">
          <div class="leaf left"></div>
          <div class="leaf right"></div>
          ${Array.from({ length: PAGES }, (_, i) => html`<div class="page" style="--i: ${i}"></div>`)}
        </div>
        <h2 id="lookup-heading">${getString('lookup-overlay-heading')}</h2>
        <p class="summary" data-testid="lookup-summary">${summaryText(this.state)}</p>
        <div
          class="bar"
          role="progressbar"
          aria-label=${getString('lookup-overlay-progress-label')}
          aria-valuemin="0"
          aria-valuemax=${total}
          aria-valuenow=${done}
        ><span style="inline-size: ${pct}%"></span></div>
        <p class="count" data-testid="lookup-count">${lineText({ key: 'nearby', kind: 'nearby', done, total })}</p>
      </section>
      <div class="vh" role="status">${this.phase === 'shown' ? getString('lookup-overlay-paused') : nothing}</div>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'mf-lookup-overlay': MfLookupOverlay
  }
}
