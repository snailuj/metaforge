import { LitElement, html, css } from 'lit'
import { customElement, property } from 'lit/decorators.js'
import type { ChainRecord, GlossMap, Linkage, MetaphorVerdict, Tier, Tag, Confidence } from '../types/grading'
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
        .left { color: #8a93a2; font-size: 0.78rem; font-variant-numeric: tabular-nums; }
        .graded { color: #6db86d; font-size: 0.78rem; font-weight: 600; }
        button.skip { margin-left: auto; }
        button.skip.on { background: #2a3140; color: #fff; border-color: #6db86d; }
    `

    @property({ attribute: false }) chain: ChainRecord | null = null
    @property({ attribute: false }) priorVerdict: PriorVerdict | null = null
    @property({ attribute: false }) glosses: GlossMap = {}
    @property() topic = ''
    @property({ type: Number }) index = 0
    @property({ type: Number }) total = 0
    @property({ type: Number }) dwellIndex = 0
    @property({ type: Number }) dwellN = 0
    @property({ type: Boolean }) skipGraded = true
    // Nav availability is computed by mf-app over the full ordered list: Next is the
    // next UNGRADED chain (forward work), Prev is a literal step back (review what
    // you just graded). `graded` flags that the current chain already has a verdict.
    @property({ type: Boolean }) canPrev = true
    @property({ type: Boolean }) canNext = true
    @property({ type: Boolean }) graded = false
    // Ungraded chains still remaining in the whole walk — queue-progress readout.
    @property({ type: Number }) ungradedLeft = 0
    // Guided mode: the list is an exact prefilled candidate order (not signal-ranked),
    // so the dwell sub-indicator and skip-graded toggle — both signal-walk affordances —
    // are hidden. Navigation, position, and the graded badge stay.
    @property({ type: Boolean }) guided = false

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
            <div class="walk-bar" role="toolbar" aria-label="Walk navigation">
                <button data-testid="walk-prev" ?disabled=${!this.canPrev}
                        @click=${() => this.emit('walk-prev')}>‹ Prev</button>
                <span class="pos" data-testid="walk-pos" aria-live="polite">${pos}</span>
                <span class="left" data-testid="walk-left">${this.ungradedLeft} left</span>
                <button data-testid="walk-next" ?disabled=${!this.canNext}
                        @click=${() => this.emit('walk-next')}>Next ›</button>
                ${this.graded ? html`<span class="graded" data-testid="walk-graded" title="already graded — your verdict is pre-filled">✓ graded</span>` : ''}
                ${this.guided
                    ? html`<span class="dwell" data-testid="walk-topic">${this.topic}</span>`
                    : html`
                        <span class="dwell" data-testid="walk-dwell">${this.topic} · ${this.dwellIndex + 1}/${this.dwellN}</span>
                        <button class="skip ${this.skipGraded ? 'on' : ''}" data-testid="walk-skip"
                                aria-pressed=${this.skipGraded}
                                @click=${() => this.emit('walk-skip-toggle')}>Skip graded</button>`}
            </div>
            <mf-grade-panel
                .chain=${this.chain}
                .priorVerdict=${this.priorVerdict}
                .glosses=${this.glosses}
            ></mf-grade-panel>
        `
    }
}

declare global {
    interface HTMLElementTagNameMap {
        'mf-grade-walk': MfGradeWalk
    }
}
