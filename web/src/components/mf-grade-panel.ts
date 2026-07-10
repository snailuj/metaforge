import { LitElement, html, css, type PropertyValues } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import type { ChainRecord, ChainStep, GlossMap, Linkage, MetaphorVerdict, Tier, Tag, Confidence, VerdictSubmitDetail, SenseInventoryItem, SenseInventoryMap } from '../types/grading';
import { TAGS } from '../types/grading';

// WordNet POS code → grader-readable label. 's' is an adjective satellite.
const POS_LABEL: Record<string, string> = { n: 'noun', v: 'verb', a: 'adj', s: 'adj', r: 'adv' };

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

// Structural tags that imply a broken topic→vehicle bridge (bad linkage). Julian
// treats these as implying bad linkage and skips the redundant linkage tap (esp.
// on mobile), so selecting one sets linkage=bad at source. 'padding' is excluded —
// a padded path can still bridge a good pairing; 'other' is unspecified. Mirrors
// LINKAGE_FORCING_TAGS in the Python sidecar (grading_sidecar/models.py).
const LINKAGE_FORCING_TAGS: readonly Tag[] = ['bad_head', 'leap', 'merge'];

@customElement('mf-grade-panel')
export class MfGradePanel extends LitElement {
    static styles = css`
        :host { display: block; padding: 0.5rem; }
        .chain { font-size: 1rem; line-height: 1.6; margin: 0.5rem 0; }
        .arrow { color: #4d5260; margin: 0 0.3rem; }
        /* Each node is tappable/hoverable to read its snapped-sense gloss. The dotted
           underline signals the affordance; active node is boxed. */
        button.step-node {
            font: inherit; color: #e6e6e6; background: transparent;
            border: none; border-bottom: 1px dotted #4d5260;
            padding: 0 0.15rem; cursor: pointer; border-radius: 2px;
        }
        button.step-node:hover { color: #fff; border-bottom-color: #9ec4ff; }
        button.step-node.active { background: #222836; border-bottom-color: #9ec4ff; }
        .link-gloss { margin: 0.1rem 0 0.5rem; font-size: 0.82rem; color: #b8bfca; line-height: 1.4; }
        .link-gloss .pos {
            font-size: 0.7rem; color: #9ec4ff; border: 1px solid #2f3a4d; border-radius: 3px;
            padding: 0 0.3rem; margin: 0 0.35rem; vertical-align: middle;
        }
        .link-gloss .gloss { color: #97a0ae; }
        .link-gloss .gloss.muted { font-style: italic; color: #6f7684; }
        /* Original prose phrase, shown muted beside its snapped head only when
           the two differ — so a mis-snapped head (bad_head) is judgeable. */
        .phrase-sub { color: #7a8190; font-size: 0.8em; font-style: italic; margin-left: 0.3rem; }
        .senses { margin: 0.3rem 0 0.5rem; display: flex; flex-direction: column; gap: 0.25rem; }
        .sense { font-size: 0.82rem; color: #b8bfca; line-height: 1.4; }
        .sense-label { font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.05em; color: #8a93a2; margin-right: 0.35rem; }
        .sense .pos {
            font-size: 0.7rem; color: #9ec4ff; border: 1px solid #2f3a4d; border-radius: 3px;
            padding: 0 0.3rem; margin: 0 0.35rem; vertical-align: middle;
        }
        .sense .gloss { color: #97a0ae; }
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
        /* Sense fan — per-step noun-inventory displayed inside the link-gloss popover.
           Each option is tappable; the intended sense is pre-lit; operator ticks gain
           a distinct border. vec: nodes show a static affordance instead of options. */
        .sense-fan { margin: 0.3rem 0 0; display: flex; flex-direction: column; gap: 0.2rem; }
        .vec-node-label { font-size: 0.8rem; color: #6f7684; font-style: italic; }
        button.sense-option {
            text-align: left; font: inherit; font-size: 0.8rem; cursor: pointer;
            background: transparent; color: #b8bfca;
            border: 1px solid #2a3140; border-radius: 3px;
            padding: 0.15rem 0.4rem;
        }
        button.sense-option:hover { border-color: #9ec4ff; color: #e6e6e6; }
        /* Intended sense is always pre-lit — the model's snap target for this occurrence. */
        button.sense-option.intended { border-color: #4a6da7; color: #9ec4ff; background: #1a2535; }
        /* Operator tick: a co-apt sense confirmed by the grader at this position. */
        button.sense-option.ticked { border-color: #6db86d; color: #a8dba8; background: #1a2f1a; }
        button.sense-option.intended.ticked { border-color: #6db86d; background: #1a2f1a; }
        .sense-sensenum { font-size: 0.7rem; color: #8a93a2; margin-left: 0.35rem; }
        .sense-tagcount { font-size: 0.68rem; color: #6a7280; margin-left: 0.25rem; }
    `;

    @property({ attribute: false }) chain: ChainRecord | null = null;
    @property({ attribute: false }) priorVerdict: PriorVerdict | null = null;
    // synset_id → {pos, definition}; supplied by mf-app so the grader can see the
    // topic's sense (noun vs adjective). Empty map → no sense block rendered.
    @property({ attribute: false }) glosses: GlossMap = {};
    // canonical_phrase_key → [ranked noun senses]; supplied by mf-app from the
    // precomputed inventory JSONL. Empty map → fan degrades to gloss-only popover.
    @property({ attribute: false }) senseInventories: SenseInventoryMap = {};

    @state() private confidence: Confidence = 'high';
    @state() private notes = '';
    // Pending linkage: 'good' is the fast-path default; B toggles to 'bad' before a metaphor submit.
    @state() private pendingLinkage: Linkage = 'good';
    // Multi-select tiers; only sent (and only meaningful) for a live metaphor.
    @state() private selectedTiers: Tier[] = [];
    // Multi-select issue tags — orthogonal to verdict axes, always available.
    @state() private selectedTags: Tag[] = [];
    // Which chain node's gloss is revealed. Hover (transient) takes precedence over
    // a pinned tap so the mouse can preview any node then fall back to the pin; both
    // null = no gloss shown. Indices, so 0 is valid — read via `hover ?? pin`, never `||`.
    @state() private _hoverStepIdx: number | null = null;
    @state() private _pinnedStepIdx: number | null = null;
    // Operator-ticked co-apt senses per chain step position. Only holds OPERATOR
    // ticks — the intended sense (step.synset_id) is NOT stored here (it is already
    // in the ChainStep record and excluded from the verdict payload to avoid duplication).
    // Map<step_idx, Set<synset_id>>. Reset on chain change (same willUpdate hook that
    // resets _pinnedStepIdx).
    @state() private _stepTicks: Map<number, Set<string>> = new Map();
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
        // A pinned/hovered node index is meaningless on a different chain — clear it.
        // Operator sense ticks are chain-scoped; a different chain starts with a clean slate.
        this._hoverStepIdx = null;
        this._pinnedStepIdx = null;
        this._stepTicks = new Map();
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

    // Topic + vehicle sense rows (head lemma · POS · gloss) so the grader can
    // tell which sense a synset_id pins. Only rows we have a gloss for are shown.
    private _renderSenses(chain: ChainRecord) {
        const rows: Array<['topic' | 'vehicle', string, string]> = [
            ['topic', chain.topic, chain.topic_synset_id],
            ['vehicle', chain.vehicle, chain.vehicle_synset_id],
        ];
        const items = rows
            .map(([label, lemma, sid]) => ({ label, lemma, g: this.glosses[sid] }))
            .filter(x => x.g && (x.g.pos || x.g.definition));
        if (!items.length) return '';
        return html`
            <div class="senses" data-testid="senses">
                ${items.map(x => html`
                    <div class="sense">
                        <span class="sense-label">${x.label}</span><strong>${x.lemma}</strong>
                        ${x.g!.pos ? html`<span class="pos" data-testid="pos-${x.label}">${POS_LABEL[x.g!.pos] ?? x.g!.pos}</span>` : ''}
                        ${x.g!.definition ? html`<span class="gloss">${x.g!.definition}</span>` : ''}
                    </div>
                `)}
            </div>
        `;
    }

    // ISO-8601 → "YYYY-MM-DD HH:MM" by slice (deterministic; no Date/locale).
    private _fmtTs(ts: string): string {
        return ts.slice(0, 16).replace('T', ' ');
    }

    // Node whose gloss to show: a live hover wins over the pinned tap, so the mouse
    // can preview any node and fall back to the pin on leave. `??` (not `||`) keeps
    // index 0 selectable.
    private _activeStepIdx(): number | null {
        return this._hoverStepIdx ?? this._pinnedStepIdx;
    }

    private _toggleStepGloss(i: number) {
        this._pinnedStepIdx = this._pinnedStepIdx === i ? null : i;
    }

    // Canonical lookup key for the sense inventory: NFC-normalised, stripped, lowercased,
    // spaces → underscores. Mirrors vec_ref() in the Python models (one canonicaliser).
    private _canonicalKey(phrase: string): string {
        return phrase.trim().toLowerCase().replace(/ /g, '_');
    }

    // Toggle an operator sense tick at the given step. The intended sense (step.synset_id)
    // cannot be ticked — it is always pre-lit and excluded from the operator payload.
    private _toggleSenseTick(stepIdx: number, synsetId: string, intendedSynsetId: string | null | undefined) {
        if (synsetId === intendedSynsetId) return;  // intended sense is pre-lit, not ticked
        const current = new Set(this._stepTicks.get(stepIdx) ?? []);
        if (current.has(synsetId)) {
            current.delete(synsetId);
        } else {
            current.add(synsetId);
        }
        // Rebuild the Map to trigger Lit's reactive update (Map mutation is not observable).
        const next = new Map(this._stepTicks);
        if (current.size > 0) {
            next.set(stepIdx, current);
        } else {
            next.delete(stepIdx);
        }
        this._stepTicks = next;
    }

    // Render the sense fan inside the link-gloss popover. Shows the ranked noun-sense
    // inventory for the active step; vec: nodes show a static affordance instead.
    private _renderSenseFan(step: ChainStep, stepIdx: number) {
        const key = this._canonicalKey(step.phrase);
        const senses: SenseInventoryItem[] = this.senseInventories[key] ?? [];
        const intendedId = step.synset_id ?? null;

        // vec: step — no synset, no ticking affordance.
        if (intendedId === null) {
            return html`
                <div class="sense-fan" data-testid="sense-fan">
                    <span class="vec-node-label" data-testid="vec-node-label">vector node — no synset</span>
                </div>
            `;
        }

        // No inventory for this phrase — render nothing (graceful degrade).
        if (senses.length === 0) return '';

        const ticked = this._stepTicks.get(stepIdx) ?? new Set<string>();
        return html`
            <div class="sense-fan" data-testid="sense-fan">
                ${senses.map(s => {
                    const isIntended = s.synset_id === intendedId;
                    const isTicked = ticked.has(s.synset_id);
                    const classes = [
                        'sense-option',
                        isIntended ? 'intended' : '',
                        isTicked ? 'ticked' : '',
                    ].filter(Boolean).join(' ');
                    return html`<button type="button"
                        class="${classes}"
                        data-testid="sense-option-${s.synset_id}"
                        @click=${(e: Event) => {
                            e.stopPropagation();  // don't toggle the gloss pin
                            this._toggleSenseTick(stepIdx, s.synset_id, intendedId);
                        }}>
                        ${s.definition ?? s.synset_id}
                        <span class="sense-sensenum">n·${s.sensenum}</span>
                        ${s.tagcount != null ? html`<span class="sense-tagcount">${s.tagcount}</span>` : ''}
                    </button>`;
                })}
            </div>
        `;
    }

    // The gloss of the currently hovered/tapped node — the WordNet definition of the
    // synset it snapped to. Reveals a wrong-sense snap at ANY hop (e.g. livery),
    // where the sense block only covers the topic/vehicle endpoints. Degrades to a
    // muted note when that synset has no precomputed gloss (unexported / null snap).
    private _renderLinkGloss(steps: ChainStep[]) {
        const i = this._activeStepIdx();
        if (i === null) return '';
        const step = steps[i];
        if (!step) return '';
        const g = step.synset_id ? this.glosses[step.synset_id] : undefined;
        // vec: steps have no synset gloss; the fan renders the vec: affordance instead.
        const isVec = step.synset_id === null || step.synset_id === undefined;
        return html`
            <div class="link-gloss" data-testid="link-gloss">
                <strong>${step.phrase}</strong>
                ${g?.pos ? html`<span class="pos" data-testid="link-gloss-pos">${POS_LABEL[g.pos] ?? g.pos}</span>` : ''}
                ${!isVec && (g?.definition
                    ? html`<span class="gloss">${g.definition}</span>`
                    : html`<span class="gloss muted">no gloss for this sense</span>`)}
                ${this._renderSenseFan(step, i)}
            </div>
        `;
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
        // Serialise operator ticks to the step_apt_senses payload. Only OPERATOR ticks are
        // included (the intended sense is already in ChainStep.synset_id; duplicating it
        // into the verdict would conflate provenance and bloat the record).
        const step_apt_senses = Array.from(this._stepTicks.entries()).flatMap(
            ([step_idx, synsets]) => Array.from(synsets).map(synset_id => ({ step_idx, synset_id }))
        ).sort((a, b) => a.step_idx - b.step_idx || a.synset_id.localeCompare(b.synset_id));
        const detail: VerdictSubmitDetail = {
            linkage: this.pendingLinkage,
            metaphor,
            tiers,
            tags: this.selectedTags,
            confidence: this.confidence,
            notes: this.notes,
            step_apt_senses,
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
        if (willSelect) {
            // A structural tag implies the bridge is broken — record linkage:bad at
            // source so the grader needn't also tap the linkage button. Set-only:
            // deselecting never reverts (an explicit bad may stand for other reasons).
            if (LINKAGE_FORCING_TAGS.includes(tag)) this.pendingLinkage = 'bad';
            // Scaffold a matching note line and drop the cursor straight after it, so
            // the operator can elaborate or hit another tag without reaching for the
            // textarea. Deselecting never touches the note (it may carry typed text).
            this._scaffoldNote(tag);
        }
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
                ${steps.map((s, i) => html`<button type="button"
                        class="step-node ${this._activeStepIdx() === i ? 'active' : ''}"
                        data-testid="step-node-${i}"
                        @click=${() => this._toggleStepGloss(i)}
                        @mouseenter=${() => { this._hoverStepIdx = i; }}
                        @mouseleave=${() => { this._hoverStepIdx = null; }}>${s.phrase}${s.phrase !== s.head
                        ? html`<span class="phrase-sub">${s.head}</span>` : ''}</button>${i < steps.length - 1 ? html`<span class="arrow">→</span>` : ''}`)}
            </div>
            ${this._renderLinkGloss(steps)}
            ${this._renderSenses(this.chain)}
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
