import { LitElement, html, css } from 'lit'
import { customElement, state } from 'lit/decorators.js'

@customElement('mf-toast')
export class MfToast extends LitElement {
  static styles = css`
    :host {
      position: fixed;
      bottom: var(--space-xl, 2rem);
      left: 50%;
      transform: translateX(-50%);
      z-index: 100;
      pointer-events: none;
    }

    .toast {
      background: var(--colour-accent-gold, #d4af37);
      color: var(--colour-bg-primary, #1a1a2e);
      padding: var(--space-xs, 0.25rem) var(--space-md, 1rem);
      border-radius: var(--hud-radius, 4px);
      font-family: var(--font-body, serif);
      font-size: 0.9rem;
      opacity: 0;
      transition: opacity 0.2s ease;
    }

    .toast.visible {
      opacity: 1;
    }
  `

  @state() private message = ''
  @state() private visible = false
  private hideTimer: ReturnType<typeof setTimeout> | null = null

  show(message: string, duration = 1500) {
    this.message = message
    this.visible = true

    if (this.hideTimer) clearTimeout(this.hideTimer)
    this.hideTimer = setTimeout(() => {
      this.visible = false
    }, duration)
  }

  disconnectedCallback(): void {
    super.disconnectedCallback()
    if (this.hideTimer) clearTimeout(this.hideTimer)
  }

  render() {
    return html`
      <div class="toast ${this.visible ? 'visible' : ''}" role="status" aria-live="polite">${this.message}</div>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'mf-toast': MfToast
  }
}
