import { LitElement, html, css, type PropertyValues } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import type { ChainRecord, Linkage, MetaphorVerdict, Tier, Tag, Confidence, VerdictSubmitDetail } from '../types/grading';
import { TAGS } from '../types/grading';

// Prior verdict shown in the muted last-saved line — the latest v2 judgement for this bridge.
interface PriorVerdict {
    linkage: Linkage;
    metaphor: MetaphorVerdict;
    tiers: Tier[];
    tags: Tag[];
    confidence: Confidence;
    ts: string;
    notes: string;
}

// Metaphor keys SUBMIT (carrying the current pending linkage + tiers + confidence).
const METAPHOR_KEYS: Record<string, MetaphorVerdict> = {
    l: 'live', d: 'dead', i: 'irrelevant',
};

// Maps keyboard key → confidence level; default is 'high' (key '1')
const CONFIDENCE_KEYS: Record<string, Confidence> = {
    '1': 'high', '2': 'med', '3': 'low',
};

const TIERS: readonly Tier[] = ['strong', 'ironic', 'surprising'] as const;

@customElement('mf-grade-panel')
export class MfGradePanel extends LitElement {
    static styles = css`
        :host { display: block; padding: 0.5rem; }
        .chain { font-size: 1rem; line-height: 1.6; margin: 0.5rem 0; }
        .arrow { color: #4d5260; margin: 0 0.3rem; }
        /* Original prose phrase, shown muted beside its snapped head only when
           the two differ — so a mis-snapped head (bad_head) is judgeable. */
        .phrase-sub { color: #7a8190; font-size: 0.8em; font-style: italic; margin-left: 0.3rem; }
        .group-label { font-size: 0.75rem; color: #8a93a2; text-transform: uppercase; letter-spacing: 0.05em; }
        .verdict-row { display: flex; flex-wrap: wrap; gap: 0.5rem; margin: 0.4rem 0; align-items: center; }
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
        .conf-row { display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 0.4rem 0; align-items: center; }
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
        button.chip.selected { background: #2a3140; color: #fff; border-color: #6db86d; }
        textarea {
            width: 100%; min-height: 3rem; box-sizing: border-box; padding: 0.4rem;
            background: #181b22; color: #e6e6e6; border: 1px solid #2a3140; border-radius: 3px;
            font-family: inherit; font-size: 0.9rem;
        }
        .last-saved { color: #8a93a2; font-size: 0.78rem; margin-bottom: 0.5rem; }
        .last-saved strong { color: #b8bfca; font-weight: 600; }
        button.verdict.was-prior { box-shadow: inset 0 0 0 2px #4d5566; }
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
    // Multi-select tiers; only sent (and only meaningful) for a live metaphor.
    @state() private selectedTiers: Tier[] = [];
    // Multi-select issue tags — orthogonal to verdict axes, always available.
    @state() private selectedTags: Tag[] = [];
    // Stable identity of what we last prefilled for: the selected chain's
    // signature plus the prior record's ts. Keying on the chain too means a
    // switch to a different chain — even another ungraded one (same null prior)
    // — re-syncs, while an mf-app re-render handing us a fresh-but-equal
    // priorVerdict object keeps the same key and never clobbers in-progress edits.
    private _prefilledForKey: string | null = null;

    private boundKeyHandler = (e: KeyboardEvent) => this._onKeydown(e);

    connectedCallback() {
        super.connectedCallback();
        document.addEventListener('keydown', this.boundKeyHandler);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        document.removeEventListener('keydown', this.boundKeyHandler);
    }

    protected willUpdate(changed: PropertyValues<this>): void {
        // Prefill/reset the form when the SELECTED CHAIN or its prior verdict
        // changes. Keyed on chain signature + the prior record's ts: switching to
        // a different chain (incl. another ungraded one → same null prior) or
        // re-grading the same chain (new ts) changes the key and re-syncs; an
        // equal re-render keeps the key, so in-progress edits are never clobbered.
        if (!changed.has('priorVerdict') && !changed.has('chain')) return;
        const pv = this.priorVerdict;
        const key = `${this.chain?.chain_signature ?? ''}|${pv?.ts ?? ''}`;
        if (key === this._prefilledForKey) return;
        this._prefilledForKey = key;
        if (pv) {
            this.pendingLinkage = pv.linkage;
            this.confidence = pv.confidence;
            this.selectedTiers = [...pv.tiers];
            this.selectedTags = [...pv.tags];
            this.notes = pv.notes;
        } else {
            this.pendingLinkage = 'good';
            this.confidence = 'high';
            this.selectedTiers = [];
            this.selectedTags = [];
            this.notes = '';
        }
    }

    // ISO-8601 → "YYYY-MM-DD HH:MM" by slice (deterministic; no Date/locale).
    private _fmtTs(ts: string): string {
        return ts.slice(0, 16).replace('T', ' ');
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
        // Tiers only ride a live metaphor; cleared otherwise so stale chips never leak.
        const tiers = metaphor === 'live' ? this.selectedTiers : [];
        const detail: VerdictSubmitDetail = {
            linkage: this.pendingLinkage,
            metaphor,
            tiers,
            tags: this.selectedTags,
            confidence: this.confidence,
            notes: this.notes,
        };
        this.dispatchEvent(new CustomEvent<VerdictSubmitDetail>('verdict-submit', {
            detail,
            bubbles: true,
            composed: true,
        }));
        // Reset transient state so the next bridge starts from the fast-path default.
        this.pendingLinkage = 'good';
        this.selectedTiers = [];
        this.selectedTags = [];
    }

    private _onNotesInput(e: Event) {
        this.notes = (e.target as HTMLTextAreaElement).value;
    }

    private _toggleLinkage() {
        this.pendingLinkage = this.pendingLinkage === 'bad' ? 'good' : 'bad';
    }

    private _selectTier(tier: Tier) {
        // Multi-select toggle: clicking a selected chip removes only it.
        this.selectedTiers = this.selectedTiers.includes(tier)
            ? this.selectedTiers.filter(t => t !== tier)
            : [...this.selectedTiers, tier];
    }

    private _toggleTag(tag: Tag) {
        // Multi-select toggle: clicking a selected chip removes only it.
        const willSelect = !this.selectedTags.includes(tag);
        this.selectedTags = willSelect
            ? [...this.selectedTags, tag]
            : this.selectedTags.filter(t => t !== tag);
        // Selecting a tag scaffolds a matching note line and drops the cursor
        // straight after it, so the operator can elaborate or hit another tag
        // without reaching for the textarea. Deselecting never touches the note
        // (it may already carry typed elaboration).
        if (willSelect) this._scaffoldNote(tag);
    }

    private _scaffoldNote(tag: Tag) {
        const label = `${tag.replace(/_/g, ' ')}: `;
        // Each tag gets its own line; no leading blank line on an empty note.
        this.notes = this.notes.length === 0
            ? label
            : `${this.notes.replace(/\n*$/, '')}\n${label}`;
        // Focus + caret-to-end after the value re-renders.
        this.updateComplete.then(() => {
            const ta = this.renderRoot.querySelector('textarea') as HTMLTextAreaElement | null;
            if (!ta) return;
            ta.focus();
            const end = ta.value.length;
            ta.setSelectionRange(end, end);
        });
    }

    render() {
        if (!this.chain) return html`<em>No chain selected</em>`;
        const steps = this.chain.chain;
        return html`
            ${this.priorVerdict ? html`
                <div class="last-saved" data-testid="last-saved">
                    last saved:
                    <strong>${this.priorVerdict.linkage}</strong>/<strong>${this.priorVerdict.metaphor}</strong>${this.priorVerdict.tiers.length
                        ? html` · ${this.priorVerdict.tiers.join(', ')}` : ''}${this.priorVerdict.tags.length
                        ? html` · ${this.priorVerdict.tags.join(', ')}` : ''}
                    ${this.priorVerdict.ts ? html` · ${this._fmtTs(this.priorVerdict.ts)}` : ''}
                </div>
            ` : ''}
            <div class="chain">
                ${steps.map((s, i) => html`
                    <span class="step">${s.head}${s.phrase !== s.head
                        ? html`<span class="phrase-sub">${s.phrase}</span>` : ''}</span>${i < steps.length - 1 ? html`<span class="arrow">→</span>` : ''}
                `)}
            </div>
            <div class="verdict-row">
                <span class="group-label">Metaphor:</span>
                <button class="verdict live ${this.priorVerdict?.metaphor === 'live' ? 'was-prior' : ''}" data-testid="metaphor-live"
                        @click=${() => this._submit('live')}>Live<kbd>L</kbd></button>
                <button class="verdict dead ${this.priorVerdict?.metaphor === 'dead' ? 'was-prior' : ''}" data-testid="metaphor-dead"
                        @click=${() => this._submit('dead')}>Dead<kbd>D</kbd></button>
                <button class="verdict irrelevant ${this.priorVerdict?.metaphor === 'irrelevant' ? 'was-prior' : ''}" data-testid="metaphor-irrelevant"
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
                    <button class="tier ${this.selectedTiers.includes(tier) ? 'selected' : ''}"
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
                <span class="group-label">Tags:</span>
                ${TAGS.map(tag => html`
                    <button class="chip ${this.selectedTags.includes(tag) ? 'selected' : ''}"
                            data-testid="chip-${tag}"
                            @click=${() => this._toggleTag(tag)}>${tag}</button>
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
