import { LitElement, html, css } from 'lit'
import { customElement, property, state } from 'lit/decorators.js'
import { keyed } from 'lit/directives/keyed.js'

const DEFAULT_DURATION_MS = 6000

/**
 * A small brass-rimmed plaque offering to undo the last navigation. A gold
 * fuse burns along its foot for as long as the offer stands; pointing at it or
 * focusing it holds the fuse, so nobody loses the offer while reaching for it.
 * Pressing Undo fires `mf-undo`; the host decides what undoing means.
 */
@customElement('mf-undo-toast')
export class MfUndoToast extends LitElement {
  static styles = css`
    :host {
      position: fixed;
      left: 50%;
      bottom: calc(var(--space-xl, 2rem) + env(safe-area-inset-bottom, 0px));
      transform: translateX(-50%);
      z-index: 110;
      pointer-events: none;
      max-width: calc(100vw - 2rem);
    }

    .plaque {
      position: relative;
      display: flex;
      align-items: center;
      gap: var(--space-sm, 0.5rem);
      padding: 0.45rem 0.45rem 0.5rem 0.95rem;
      overflow: hidden;
      border: 1px solid var(--colour-accent-gold-dim, rgba(212, 175, 55, 0.5));
      border-radius: 999px;
      background:
        radial-gradient(120% 140% at 50% -40%, rgba(212, 175, 55, 0.16), transparent 60%),
        var(--colour-panel-deep, rgba(14, 22, 42, 0.88));
      box-shadow:
        inset 0 1px 0 rgba(232, 224, 212, 0.06),
        0 10px 30px rgba(0, 0, 0, 0.45),
        0 0 28px var(--colour-forest-root-glow, rgba(212, 175, 55, 0.25));
      backdrop-filter: blur(6px);
      color: var(--colour-text-primary, #e8e0d4);
      font-family: var(--font-body, serif);
      font-size: 0.95rem;
      opacity: 0;
      transform: translateY(14px) scale(0.97);
      transition: opacity 0.25s ease, transform 0.35s cubic-bezier(0.2, 0.9, 0.3, 1.2);
    }

    .plaque.visible {
      opacity: 1;
      transform: none;
      pointer-events: auto;
    }

    .star {
      color: var(--colour-accent-gold, #d4af37);
      font-size: 0.7rem;
      text-shadow: 0 0 8px var(--colour-accent-gold, #d4af37);
    }

    .message {
      font-style: italic;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .undo {
      display: inline-flex;
      align-items: center;
      gap: 0.3rem;
      margin-inline-start: var(--space-xs, 0.25rem);
      padding: 0.3rem 0.8rem 0.3rem 0.7rem;
      border: 1px solid transparent;
      border-inline-start-color: rgba(212, 175, 55, 0.25);
      border-radius: 0 999px 999px 0;
      background: transparent;
      color: var(--colour-accent-gold, #d4af37);
      font-family: var(--font-heading, serif);
      font-size: 0.8rem;
      font-variant: small-caps;
      letter-spacing: 0.08em;
      cursor: pointer;
      transition: color 0.2s ease, text-shadow 0.2s ease, background 0.2s ease;
    }

    .undo:hover,
    .undo:focus-visible {
      color: #f3d77a;
      text-shadow: 0 0 10px rgba(212, 175, 55, 0.6);
      background: rgba(212, 175, 55, 0.08);
      outline: none;
    }

    .undo:focus-visible {
      border-color: var(--colour-accent-gold-dim, rgba(212, 175, 55, 0.5));
    }

    .glyph {
      font-size: 1rem;
      line-height: 1;
    }

    /* The fuse: a gold thread with a glowing tip, burning from right to left. */
    .fuse {
      position: absolute;
      left: 1.1rem;
      bottom: 3px;
      height: 1px;
      width: calc(100% - 2.2rem);
      background: linear-gradient(90deg, rgba(212, 175, 55, 0.15), var(--colour-accent-gold, #d4af37));
      transform-origin: left center;
      animation: burn var(--fuse-ms, 6000ms) linear forwards;
    }

    .fuse::after {
      content: '';
      position: absolute;
      right: -2px;
      top: -1.5px;
      width: 4px;
      height: 4px;
      border-radius: 50%;
      background: #fff6d6;
      box-shadow: 0 0 6px 2px rgba(243, 215, 122, 0.8);
    }

    .held .fuse {
      animation-play-state: paused;
    }

    @keyframes burn {
      from { width: calc(100% - 2.2rem); }
      to { width: 0; }
    }

    @media (prefers-reduced-motion: reduce) {
      .plaque { transform: none; transition: opacity 0.2s ease; }
      .fuse { animation: none; opacity: 0.5; }
      .fuse::after { display: none; }
    }
  `

  @property() actionLabel = 'Undo'

  @state() private message = ''
  @state() private visible = false
  @state() private held = false
  // Restarts the fuse animation on every show.
  @state() private showCount = 0
  private duration = DEFAULT_DURATION_MS
  private hideTimer: ReturnType<typeof setTimeout> | null = null
  private deadline = 0
  private remaining = 0

  show(message: string, duration = DEFAULT_DURATION_MS): void {
    this.message = message
    this.duration = duration
    this.visible = true
    this.held = this.pointerOver || this.focusWithin
    this.showCount++
    if (this.held) this.remaining = duration
    else this.arm(duration)
  }

  hide(): void {
    this.clearTimer()
    this.visible = false
    this.held = false
    // A hidden plaque takes no pointer events, so no pointerleave will come.
    this.pointerOver = false
    this.focusWithin = false
  }

  disconnectedCallback(): void {
    super.disconnectedCallback()
    this.clearTimer()
  }

  private arm(ms: number): void {
    this.clearTimer()
    this.deadline = Date.now() + ms
    this.hideTimer = setTimeout(() => this.hide(), ms)
  }

  private clearTimer(): void {
    if (this.hideTimer) clearTimeout(this.hideTimer)
    this.hideTimer = null
  }

  // The offer holds while either is true.
  private pointerOver = false
  private focusWithin = false

  private setHold(pointerOver: boolean, focusWithin: boolean): void {
    this.pointerOver = pointerOver
    this.focusWithin = focusWithin
    if (!this.visible) return
    const held = pointerOver || focusWithin
    if (held === this.held) return
    this.held = held
    if (held) {
      this.remaining = Math.max(0, this.deadline - Date.now())
      this.clearTimer()
    } else {
      this.arm(this.remaining)
    }
  }

  private handleUndo(): void {
    this.hide()
    this.dispatchEvent(new CustomEvent('mf-undo', { bubbles: true, composed: true }))
  }

  render() {
    return html`
      <div
        class="plaque ${this.visible ? 'visible' : ''} ${this.held ? 'held' : ''}"
        style="--fuse-ms: ${this.duration}ms"
        @pointerenter=${() => this.setHold(true, this.focusWithin)}
        @pointerleave=${() => this.setHold(false, this.focusWithin)}
        @focusin=${() => this.setHold(this.pointerOver, true)}
        @focusout=${() => this.setHold(this.pointerOver, false)}
      >
        <span class="star" aria-hidden="true">✦</span>
        <span class="message" role="status" aria-live="polite">${this.visible ? this.message : ''}</span>
        <button class="undo" type="button" tabindex=${this.visible ? 0 : -1} @click=${this.handleUndo}>
          <span class="glyph" aria-hidden="true">↶</span>${this.actionLabel}
        </button>
        ${this.visible ? keyed(this.showCount, html`<span class="fuse" aria-hidden="true"></span>`) : ''}
      </div>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'mf-undo-toast': MfUndoToast
  }
}
