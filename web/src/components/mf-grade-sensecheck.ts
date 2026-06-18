import { LitElement, html, css } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import type { GradingClient } from '../api/grading-client';
import type { SenseCandidate, SenseCheckItem, SenseLabel, SenseVerdict } from '../types/grading';

// Self-contained sense-check session. Owns its own sample, cursor and POSTs —
// like mf-grade-regrade — because its labels go to the SEPARATE sense-labels file,
// never the gold judgements. mf-app only mounts it and hands down the client.
type Phase = 'idle' | 'loading' | 'labelling' | 'done' | 'error';

const BATCH_FLAGGED = 40;
const BATCH_RANDOM = 40;

type SenseCheckClient = Pick<GradingClient, 'getSenseCheckSample' | 'postSenseLabel'>;

@customElement('mf-grade-sensecheck')
export class MfGradeSensecheck extends LitElement {
    static styles = css`
        :host { display: block; }
        .intro { padding: 0.5rem; color: #c8c8c8; font-size: 0.9rem; max-width: 34rem; }
        .intro .muted { color: #8a93a2; font-size: 0.82rem; display: block; margin-top: 0.3rem; }
        button.primary {
            margin: 0.4rem 0.5rem; padding: 0.45rem 0.9rem; cursor: pointer; font-size: 0.88rem;
            background: #181b22; color: #e6e6e6; border: 1px solid #2a3140; border-radius: 4px;
        }
        button.primary:hover { border-color: #6db86d; }
        .bar { display: flex; align-items: center; gap: 0.7rem; flex-wrap: wrap;
            padding: 0.5rem; border-bottom: 1px solid #2a3140; margin-bottom: 0.5rem; }
        .badge { color: #d6a560; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.06em; }
        .pos { font-variant-numeric: tabular-nums; color: #c8c8c8; min-width: 4.5em; }
        .err { color: #e09a9a; padding: 0.5rem; font-size: 0.85rem; }
        .item { margin: 0.5rem; padding: 0.7rem 0.8rem; background: #14171d;
            border: 1px solid #2a3140; border-radius: 6px; max-width: 34rem; }
        .role { font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.05em; color: #8a93a2; }
        .word { font-size: 1.15rem; color: #e6e6e6; margin: 0 0.4rem; }
        .gloss { color: #97a0ae; font-size: 0.9rem; display: block; margin: 0.3rem 0 0.6rem; }
        .verdicts { display: flex; gap: 0.5rem; flex-wrap: wrap; }
        button.verdict { padding: 0.5rem 0.9rem; font-size: 0.9rem; cursor: pointer;
            background: #181b22; color: #e6e6e6; border: 1px solid #2a3140; border-radius: 4px; }
        button.verdict.right { border-color: #6db86d; }
        button.verdict.wrong { border-color: #c47a7a; }
        button.verdict.rare { border-color: #d6a560; }
        button.verdict.pending { box-shadow: inset 0 0 0 2px #4d5566; }
        .candidates { margin: 0.6rem 0; display: flex; flex-direction: column; gap: 0.3rem; }
        button.cand { text-align: left; padding: 0.4rem 0.6rem; cursor: pointer;
            background: #181b22; color: #d6dae2; border: 1px solid #2a3140; border-radius: 4px; font-size: 0.84rem; }
        button.cand:hover { border-color: #6db86d; }
        button.cand .cpos { color: #9ec4ff; margin-right: 0.4rem; }
        button.cand .ctag { color: #8a93a2; margin-left: 0.4rem; font-size: 0.78rem; }
        .ctx-toggle { margin-top: 0.6rem; background: none; border: none; color: #9ec4ff;
            cursor: pointer; font-size: 0.8rem; padding: 0; }
        .ctx { margin-top: 0.4rem; border-top: 1px solid #2a3140; padding-top: 0.4rem; }
        .ctx-chain { font-size: 0.82rem; color: #b8bfca; margin: 0.2rem 0; }
        .ctx-arrow { color: #4d5260; margin: 0 0.25rem; }
        .done { padding: 0.7rem; color: #c8c8c8; }
    `;

    @property({ attribute: false }) client!: SenseCheckClient;

    @state() private phase: Phase = 'idle';
    @state() private sample: SenseCheckItem[] = [];
    @state() private index = 0;
    @state() private pendingVerdict: SenseVerdict | null = null;
    @state() private showContext = false;
    @state() private error: string | null = null;

    // Not @state — must not trigger a render; the guard is only for re-entrancy.
    private _posting = false;

    private get current(): SenseCheckItem | null {
        return this.sample[this.index] ?? null;
    }

    private _seed(): number {
        return Math.floor(Math.random() * 1_000_000);
    }

    private async _start(): Promise<void> {
        this.phase = 'loading';
        this.error = null;
        try {
            const res = await this.client.getSenseCheckSample(
                { nFlagged: BATCH_FLAGGED, nRandom: BATCH_RANDOM, seed: this._seed() });
            this.sample = res.items;
            this.index = 0;
            this.pendingVerdict = null;
            this.showContext = false;
            this.phase = this.sample.length ? 'labelling' : 'done';
        } catch (e) {
            this.error = e instanceof Error ? e.message : 'failed to draw a sense-check batch';
            this.phase = 'error';
        }
    }

    // right / unsure POST immediately (no intended sense). wrong / rare_ok reveal the
    // candidate picker; the chosen candidate's synset_id rides as intended_synset_id.
    private _onVerdict(verdict: SenseVerdict): void {
        if (verdict === 'wrong' || verdict === 'rare_ok') {
            this.pendingVerdict = verdict;
            return;
        }
        void this._post(verdict, null);
    }

    private _onCandidate(c: SenseCandidate): void {
        if (!this.pendingVerdict) return;
        void this._post(this.pendingVerdict, c.synset_id);
    }

    private _skip(): void {
        // Advance without recording a verdict; the item may resurface in a later sample.
        if (this._posting) return;
        this.index += 1;
        this.pendingVerdict = null;
        this.showContext = false;
        if (this.index >= this.sample.length) this.phase = 'done';
    }

    private _back(): void {
        // Return to the previous item without recording a verdict. Re-grading a
        // returned-to item simply POSTs a fresh label — latest-wins server-side.
        if (this.index === 0 || this._posting) return;
        this.index -= 1;
        this.pendingVerdict = null;
        this.showContext = false;
        this.phase = 'labelling';
    }

    private async _post(verdict: SenseVerdict, intended: string | null): Promise<void> {
        const it = this.current;
        // Guard is set synchronously before the first await, so two rapid clicks post only once.
        if (!it || this._posting) return;
        this._posting = true;
        const label: SenseLabel = {
            schema_version: 'sense_label.v1',
            role: it.role,
            word: it.word,
            snapped_synset_id: it.snapped_synset_id,
            verdict,
            intended_synset_id: intended,
            chain_signature: it.chain_signature,
        };
        try {
            await this.client.postSenseLabel(label);
            this.error = null;
            this.index += 1;
            this.pendingVerdict = null;
            this.showContext = false;
            if (this.index >= this.sample.length) this.phase = 'done';
        } catch (err) {
            // Keep the item so the operator can retry — no lost label.
            this.error = err instanceof Error ? err.message : 'failed to record sense label';
        } finally {
            this._posting = false;
        }
    }

    render() {
        if (this.phase === 'idle') return this._renderIntro();
        if (this.phase === 'error') return html`
            <div class="err" data-testid="sensecheck-error">error: ${this.error}</div>
            <button class="primary" data-testid="sensecheck-start" @click=${this._start}>Try again</button>`;
        if (this.phase === 'loading') return html`<div class="intro">drawing a sense-check batch…</div>`;
        if (this.phase === 'labelling') return this._renderItem();
        return html`
            <div class="done" data-testid="sensecheck-done">Batch complete — your sense labels are saved.</div>
            <button class="primary" data-testid="sensecheck-start" @click=${this._start}>Label another batch</button>`;
    }

    private _renderIntro() {
        return html`
            <div class="intro">
                Sense-check — confirm whether each endpoint's snapped sense is the one the metaphor intends.
                Anchors the auto-flags and the planned re-snapper to your judgement.
                <span class="muted">Labels go to a separate file; your grades are never touched.</span>
            </div>
            <button class="primary" data-testid="sensecheck-start" @click=${this._start}>Start sense-check</button>`;
    }

    private _renderItem() {
        const it = this.current!;
        return html`
            <div class="bar" role="toolbar" aria-label="Sense-check">
                <span class="badge">sense-check</span>
                <span class="pos" data-testid="sensecheck-progress" aria-live="polite">${this.index + 1} / ${this.sample.length}</span>
                <button class="primary" data-testid="sensecheck-back"
                        ?disabled=${this.index === 0}
                        @click=${this._back}>Back</button>
            </div>
            ${this.error ? html`<div class="err" data-testid="sensecheck-error">error: ${this.error}</div>` : ''}
            <div class="item" data-testid="sensecheck-item">
                <span class="role">${it.role}</span><span class="word">${it.word}</span>
                ${it.pos ? html`<span class="role">${it.pos}</span>` : ''}
                <span class="gloss">${it.snapped_gloss ?? '(no gloss available)'}</span>
                <div class="verdicts">
                    <button class="verdict right" data-testid="verdict-right" @click=${() => this._onVerdict('right')}>Right</button>
                    <button class="verdict wrong ${this.pendingVerdict === 'wrong' ? 'pending' : ''}" data-testid="verdict-wrong" @click=${() => this._onVerdict('wrong')}>Wrong</button>
                    <button class="verdict rare ${this.pendingVerdict === 'rare_ok' ? 'pending' : ''}" data-testid="verdict-rare" @click=${() => this._onVerdict('rare_ok')}>Rare-but-better</button>
                    <button class="verdict" data-testid="verdict-unsure" @click=${() => this._onVerdict('unsure')}>Unsure</button>
                    <button class="verdict" data-testid="verdict-skip" @click=${() => this._skip()}>Skip</button>
                </div>
                ${this.pendingVerdict ? this._renderCandidates(it) : ''}
                ${this._renderContext(it)}
            </div>`;
    }

    private _renderCandidates(it: SenseCheckItem) {
        if (!it.candidates.length) return html`<div class="err">no candidate senses available — pick "Unsure" or fix the precompute</div>`;
        return html`
            <div class="candidates" data-testid="sensecheck-candidates">
                <span class="role">intended sense?</span>
                ${it.candidates.map(c => html`
                    <button class="cand" data-testid="cand-${c.synset_id}" @click=${() => this._onCandidate(c)}>
                        ${c.pos ? html`<span class="cpos">${c.pos}</span>` : ''}${c.gloss}
                        ${c.tagcount != null ? html`<span class="ctag">tagcount ${c.tagcount}</span>` : ''}
                    </button>`)}
            </div>`;
    }

    private _renderContext(it: SenseCheckItem) {
        return html`
            <button class="ctx-toggle" data-testid="ctx-toggle"
                    @click=${() => { this.showContext = !this.showContext; }}>
                ${this.showContext ? 'hide context' : `show context (${it.context.chains.length} chain${it.context.chains.length === 1 ? '' : 's'})`}
            </button>
            ${this.showContext ? html`
                <div class="ctx" data-testid="sensecheck-context">
                    ${it.context.chains.map(c => html`
                        <div class="ctx-chain">
                            ${c.topic_pos || c.topic_gloss ? html`
                                <span class="role">${c.topic_pos ?? ''}</span>
                                ${c.topic_gloss ? html`<span class="gloss">${c.topic_gloss}</span>` : ''}
                            ` : ''}
                            ${c.chain.map((s, i) => html`${s.head}${i < c.chain.length - 1 ? html`<span class="ctx-arrow">→</span>` : ''}`)}
                        </div>`)}
                </div>` : ''}`;
    }
}

declare global {
    interface HTMLElementTagNameMap {
        'mf-grade-sensecheck': MfGradeSensecheck;
    }
}
