import { LitElement, html, css } from 'lit'
import { customElement, property } from 'lit/decorators.js'
import type { ChainRecord, Linkage, MetaphorVerdict, Tier, Tag, Confidence } from '../types/grading'
import './mf-grade-panel'

// Shape of the muted "last saved" prior verdict the panel echoes — mirrors what
// mf-app.priorVerdict() returns. Passed straight through to mf-grade-panel.
interface PriorVerdict {
    linkage: Linkage
    metaphor: MetaphorVerdict
    tiers: Tier[]
    tags: Tag[]
    confidence: Confidence
    ts: string
    notes: string
}

/**
 * Presentational shell for the signal-prioritised grading walk. It owns no data
 * and no index — mf-app drives the position and hands down the current chain. The
 * shell renders the nav bar (prev / position / next / dwell / skip-graded) and
 * embeds the existing mf-grade-panel, which renders the chain steps + verdict
 * controls. The panel's `verdict-submit` is bubbles+composed, so it crosses this
 * boundary to mf-app unaided — we never re-dispatch it (that would double-submit).
 *
 * Arrow keys page the walk; the editable-field guard (composedPath, never
 * activeElement — Shadow DOM retargets the latter to the host) keeps Left/Right
 * from paging while the operator is typing in the notes textarea. The panel owns
 * the L/D/I/B/1/2/3 keys; there is no overlap.
 */
@customElement('mf-grade-walk')
export class MfGradeWalk extends LitElement {
    static styles = css`
        :host { display: block; }
        .walk-bar {
            display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap;
            padding: 0.5rem; border-bottom: 1px solid #2a3140; margin-bottom: 0.5rem;
        }
        button {
            padding: 0.4rem 0.8rem; cursor: pointer; border-radius: 4px;
            background: #181b22; color: #e6e6e6; border: 1px solid #2a3140; font-size: 0.85rem;
        }
        button:disabled { opacity: 0.4; cursor: default; }
        .pos { font-variant-numeric: tabular-nums; color: #c8c8c8; min-width: 4.5em; text-align: center; }
        .dwell { color: #8a93a2; font-size: 0.8rem; }
        button.skip { margin-left: auto; }
        button.skip.on { background: #2a3140; color: #fff; border-color: #6db86d; }
    `

    @property({ attribute: false }) chain: ChainRecord | null = null
    @property({ attribute: false }) priorVerdict: PriorVerdict | null = null
    @property() topic = ''
    @property({ type: Number }) index = 0
    @property({ type: Number }) total = 0
    @property({ type: Number }) dwellIndex = 0
    @property({ type: Number }) dwellN = 0
    @property({ type: Boolean }) skipGraded = true

    private boundKey = (e: KeyboardEvent) => this.onKeydown(e)

    connectedCallback(): void {
        super.connectedCallback()
        document.addEventListener('keydown', this.boundKey)
    }

    disconnectedCallback(): void {
        super.disconnectedCallback()
        document.removeEventListener('keydown', this.boundKey)
    }

    private onKeydown(e: KeyboardEvent): void {
        if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return
        const editable = e.composedPath().some(node => {
            const el = node as HTMLElement
            return el && (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT' || el.isContentEditable === true)
        })
        if (editable) return
        e.preventDefault()
        this.emit(e.key === 'ArrowLeft' ? 'walk-prev' : 'walk-next')
    }

    private emit(name: 'walk-prev' | 'walk-next' | 'walk-skip-toggle'): void {
        this.dispatchEvent(new CustomEvent(name, { bubbles: true, composed: true }))
    }

    render() {
        const pos = this.total === 0 ? '0 / 0' : `${this.index + 1} / ${this.total}`
        return html`
            <div class="walk-bar">
                <button data-testid="walk-prev" ?disabled=${this.index <= 0}
                        @click=${() => this.emit('walk-prev')}>‹ Prev</button>
                <span class="pos" data-testid="walk-pos">${pos}</span>
                <button data-testid="walk-next" ?disabled=${this.index >= this.total - 1}
                        @click=${() => this.emit('walk-next')}>Next ›</button>
                <span class="dwell" data-testid="walk-dwell">${this.topic} · ${this.dwellIndex + 1}/${this.dwellN}</span>
                <button class="skip ${this.skipGraded ? 'on' : ''}" data-testid="walk-skip"
                        aria-pressed=${this.skipGraded}
                        @click=${() => this.emit('walk-skip-toggle')}>Skip graded</button>
            </div>
            <mf-grade-panel
                .chain=${this.chain}
                .priorVerdict=${this.priorVerdict}
            ></mf-grade-panel>
        `
    }
}

declare global {
    interface HTMLElementTagNameMap {
        'mf-grade-walk': MfGradeWalk
    }
}
