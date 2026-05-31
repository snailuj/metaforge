import { LitElement, html, css } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import type { ChainRecord, Linkage, MetaphorVerdict, Tier, Confidence } from '../types/grading';

// Prior verdict shown in the re-grade banner — the latest v2 judgement for this bridge.
interface PriorVerdict {
    linkage: Linkage;
    metaphor: MetaphorVerdict;
    tier: Tier | null;
    ts: string;
    notes: string;
}

// Metaphor keys SUBMIT (carrying the current pending linkage + tier + confidence).
const METAPHOR_KEYS: Record<string, MetaphorVerdict> = {
    l: 'live', d: 'dead', i: 'irrelevant',
};

// Maps keyboard key → confidence level; default is 'high' (key '1')
const CONFIDENCE_KEYS: Record<string, Confidence> = {
    '1': 'high', '2': 'med', '3': 'low',
};

const TIERS: readonly Tier[] = [
    'legendary', 'complex', 'interesting', 'ironic', 'strong', 'obvious', 'unlikely',
] as const;

const TAG_CHIPS = ['merge', 'padding', 'leap', 'other'] as const;

@customElement('mf-grade-panel')
export class MfGradePanel extends LitElement {
    static styles = css`
        :host { display: block; padding: 0.5rem; }
        .chain { font-size: 1rem; line-height: 1.6; margin: 0.5rem 0; }
        .arrow { color: #4d5260; margin: 0 0.3rem; }
        .group-label { font-size: 0.75rem; color: #8a93a2; text-transform: uppercase; letter-spacing: 0.05em; }
        .verdict-row { display: flex; gap: 0.5rem; margin: 0.4rem 0; align-items: center; }
        button.verdict {
            padding: 0.5rem 0.9rem; font-size: 0.9rem; cursor: pointer;
            background: #181b22; color: #e6e6e6; border: 1px solid #2a3140;
            border-radius: 4px;
        }
        button.verdict.live { border-color: #6db86d; }
        button.verdict.dead { border-color: #c47a7a; }
        button.verdict.irrelevant { border-color: #6a6f7a; }
        button.linkage {
            padding: 0.4rem 0.8rem; font-size: 0.85rem; cursor: pointer;
            background: #181b22; color: #c8c8c8; border: 1px solid #2a3140;
            border-radius: 4px;
        }
        button.linkage.bad { border-color: #d6a560; background: #4a3b2a; color: #f0d29a; }
        .conf-row { display: flex; gap: 0.4rem; margin: 0.4rem 0; align-items: center; }
        button.conf {
            padding: 0.3rem 0.6rem; cursor: pointer;
            background: #181b22; color: #c8c8c8; border: 1px solid #2a3140;
            border-radius: 3px;
        }
        button.conf.active { background: #2a3140; color: #fff; }
        .tiers { display: flex; gap: 0.3rem; margin: 0.4rem 0; flex-wrap: wrap; align-items: center; }
        button.tier {
            font-size: 0.8rem; padding: 0.2rem 0.55rem;
            background: #181b22; color: #9aa3b2; border: 1px solid #2a3140;
            border-radius: 12px; cursor: pointer;
        }
        button.tier.selected { background: #2a3140; color: #fff; border-color: #6db86d; }
        .chips { display: flex; gap: 0.3rem; margin: 0.4rem 0; flex-wrap: wrap; }
        button.chip {
            font-size: 0.8rem; padding: 0.2rem 0.5rem;
            background: #181b22; color: #9aa3b2; border: 1px solid #2a3140;
            border-radius: 12px; cursor: pointer;
        }
        textarea {
            width: 100%; min-height: 3rem; box-sizing: border-box; padding: 0.4rem;
            background: #181b22; color: #e6e6e6; border: 1px solid #2a3140; border-radius: 3px;
            font-family: inherit; font-size: 0.9rem;
        }
        .banner {
            background: #4a3b2a; color: #f0d29a; padding: 0.4rem 0.6rem;
            border-radius: 3px; font-size: 0.85rem; margin-bottom: 0.6rem;
        }
        .banner .prior-notes {
            margin-top: 0.3rem; font-style: italic; color: #d8c08a;
            white-space: pre-wrap; word-break: break-word;
        }
        kbd {
            background: #2a3140; color: #c8c8c8; padding: 0.05rem 0.3rem;
            border-radius: 3px; font-size: 0.75rem; margin-left: 0.3rem;
        }
    `;

    @property({ attribute: false }) chain: ChainRecord | null = null;
    @property({ attribute: false }) priorVerdict: PriorVerdict | null = null;

    @state() private confidence: Confidence = 'high';
    @state() private notes = '';
    // Pending linkage: 'good' is the fast-path default; B toggles to 'bad' before a metaphor submit.
    @state() private pendingLinkage: Linkage = 'good';
    // Single-select tier; only sent (and only meaningful) for a live metaphor.
    @state() private selectedTier: Tier | null = null;

    private boundKeyHandler = (e: KeyboardEvent) => this._onKeydown(e);

    connectedCallback() {
        super.connectedCallback();
        document.addEventListener('keydown', this.boundKeyHandler);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        document.removeEventListener('keydown', this.boundKeyHandler);
    }

    private _onKeydown(e: KeyboardEvent) {
        // Don't intercept grading keys when the user is typing in ANY editable
        // field — including ones in other shadow roots (design-notes textarea,
        // topic-picker input). e.target retargets to the shadow host across
        // boundaries, so a plain tagName check on e.target misses them; the
        // composed path includes the real focused element regardless of root.
        const editable = e.composedPath().some(el => {
            const node = el as HTMLElement;
            return node && (node.tagName === 'TEXTAREA' || node.tagName === 'INPUT'
                || node.isContentEditable === true);
        });
        if (editable) return;

        const k = e.key.toLowerCase();
        if (k === 'b') {
            // Visual-only: toggle the pending linkage; does NOT submit.
            e.preventDefault();
            this.pendingLinkage = this.pendingLinkage === 'bad' ? 'good' : 'bad';
        } else if (k in METAPHOR_KEYS) {
            e.preventDefault();
            this._submit(METAPHOR_KEYS[k]);
        } else if (e.key in CONFIDENCE_KEYS) {
            e.preventDefault();
            this.confidence = CONFIDENCE_KEYS[e.key];
        }
    }

    private _submit(metaphor: MetaphorVerdict) {
        // Tier only rides a live metaphor; cleared otherwise so a stale chip never leaks.
        const tier = metaphor === 'live' ? this.selectedTier : null;
        this.dispatchEvent(new CustomEvent('verdict-submit', {
            detail: {
                linkage: this.pendingLinkage,
                metaphor,
                tier,
                confidence: this.confidence,
                notes: this.notes,
            },
            bubbles: true,
            composed: true,
        }));
        // Reset transient state so the next bridge starts from the fast-path default.
        this.pendingLinkage = 'good';
        this.selectedTier = null;
    }

    private _onNotesInput(e: Event) {
        this.notes = (e.target as HTMLTextAreaElement).value;
    }

    private _toggleLinkage() {
        this.pendingLinkage = this.pendingLinkage === 'bad' ? 'good' : 'bad';
    }

    private _selectTier(tier: Tier) {
        // Single-select toggle: clicking the active chip clears it.
        this.selectedTier = this.selectedTier === tier ? null : tier;
    }

    private _addTag(tag: string) {
        // Strip any existing tag prefix, then prepend the new one
        const cleaned = this.notes.replace(/^(merge|padding|leap|other):\s*/i, '');
        this.notes = `${tag}: ${cleaned}`;
        // Sync textarea DOM value to match — Lit's .value binding updates on next render
        // but the test reads textarea.value immediately after updateComplete, so we update
        // the property here; Lit will sync the DOM on the next render cycle.
    }

    render() {
        if (!this.chain) return html`<em>No chain selected</em>`;
        const steps = this.chain.chain;
        return html`
            ${this.priorVerdict ? html`
                <div class="banner" data-testid="re-grade-banner">
                    Re-grading — your previous verdict was
                    <strong>${this.priorVerdict.linkage}</strong> linkage /
                    <strong>${this.priorVerdict.metaphor}</strong> metaphor${this.priorVerdict.tier
                        ? html` (<strong>${this.priorVerdict.tier}</strong>)` : ''}
                    at ${this.priorVerdict.ts}.
                    ${this.priorVerdict.notes ? html`
                        <div class="prior-notes" data-testid="prior-notes">${this.priorVerdict.notes}</div>
                    ` : ''}
                </div>
            ` : ''}
            <div class="chain">
                ${steps.map((s, i) => html`
                    <span>${s.phrase}</span>${i < steps.length - 1 ? html`<span class="arrow">→</span>` : ''}
                `)}
            </div>
            <div class="verdict-row">
                <span class="group-label">Metaphor:</span>
                <button class="verdict live" data-testid="metaphor-live"
                        @click=${() => this._submit('live')}>Live<kbd>L</kbd></button>
                <button class="verdict dead" data-testid="metaphor-dead"
                        @click=${() => this._submit('dead')}>Dead<kbd>D</kbd></button>
                <button class="verdict irrelevant" data-testid="metaphor-irrelevant"
                        @click=${() => this._submit('irrelevant')}>Irrelevant<kbd>I</kbd></button>
            </div>
            <div class="verdict-row">
                <span class="group-label">Linkage:</span>
                <button class="linkage ${this.pendingLinkage === 'bad' ? 'bad' : ''}"
                        data-testid="linkage-toggle"
                        @click=${this._toggleLinkage}>
                    ${this.pendingLinkage === 'bad' ? 'Bad path' : 'Good (default)'}<kbd>B</kbd>
                </button>
            </div>
            <div class="tiers">
                <span class="group-label">Tier:</span>
                ${TIERS.map(tier => html`
                    <button class="tier ${this.selectedTier === tier ? 'selected' : ''}"
                            data-testid="tier-${tier}"
                            @click=${() => this._selectTier(tier)}>${tier}</button>
                `)}
            </div>
            <div class="conf-row">
                <span class="group-label">Confidence:</span>
                <button class="conf ${this.confidence === 'high' ? 'active' : ''}"
                        @click=${() => { this.confidence = 'high'; }}>High<kbd>1</kbd></button>
                <button class="conf ${this.confidence === 'med' ? 'active' : ''}"
                        @click=${() => { this.confidence = 'med'; }}>Med<kbd>2</kbd></button>
                <button class="conf ${this.confidence === 'low' ? 'active' : ''}"
                        @click=${() => { this.confidence = 'low'; }}>Low<kbd>3</kbd></button>
            </div>
            <div class="chips">
                ${TAG_CHIPS.map(tag => html`
                    <button class="chip" data-testid="chip-${tag}" @click=${() => this._addTag(tag)}>${tag}</button>
                `)}
            </div>
            <textarea
                placeholder="optional note — public repo, no secrets"
                .value=${this.notes}
                @input=${this._onNotesInput}
                maxlength="1000"
                rows="3"></textarea>
        `;
    }
}
