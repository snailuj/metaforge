import { LitElement, html, css } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import type { GradingClient } from '../api/grading-client';
import type { ChainRecord, GlossMap, JudgementRecord, RegradeAgreement, VerdictSubmitDetail } from '../types/grading';
import './mf-grade-panel';

// Blind re-grade session — the intra-rater reliability FLOOR. Draws a batch of
// already-graded chains (old enough that re-grading tests stability, not memory),
// shows each with NO prior verdict (the blind invariant), records the fresh pass
// to the SEPARATE regrades file, then reports self-agreement (per-axis κ).
//
// Self-contained: unlike mf-grade-walk (which mf-app drives), this owns its sample,
// cursor and POSTs — because its verdicts go to /api/grading/regrade, never the gold
// judgements. mf-app only mounts it and hands down the client + glosses.
type Phase = 'idle' | 'loading' | 'grading' | 'done' | 'error';

// Batch shape. Random seed per session so successive batches broaden which signatures
// get a blind pass (the agreement endpoint pairs every overlapping sig). min_age_days
// keeps freshly-graded chains out — re-grading those would test memory, not stability.
const BATCH_N = 12;
const MIN_AGE_DAYS = 3;

type RegradeClient = Pick<GradingClient, 'getRegradeSample' | 'postRegrade' | 'getRegradeAgreement'>;

@customElement('mf-grade-regrade')
export class MfGradeRegrade extends LitElement {
    static styles = css`
        :host { display: block; }
        .intro { padding: 0.5rem; color: #c8c8c8; font-size: 0.9rem; max-width: 34rem; }
        .intro .muted { color: #8a93a2; font-size: 0.82rem; display: block; margin-top: 0.3rem; }
        button.primary {
            margin: 0.4rem 0.5rem; padding: 0.45rem 0.9rem; cursor: pointer; font-size: 0.88rem;
            background: #181b22; color: #e6e6e6; border: 1px solid #2a3140; border-radius: 4px;
        }
        button.primary:hover { border-color: #6db86d; }
        button.primary:disabled { opacity: 0.6; cursor: progress; }
        .bar {
            display: flex; align-items: center; gap: 0.7rem; flex-wrap: wrap;
            padding: 0.5rem; border-bottom: 1px solid #2a3140; margin-bottom: 0.5rem;
        }
        .badge { color: #d6a560; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.06em; }
        .pos { font-variant-numeric: tabular-nums; color: #c8c8c8; min-width: 4.5em; }
        .err { color: #e09a9a; padding: 0.5rem; font-size: 0.85rem; }
        .panel {
            margin: 0.5rem; padding: 0.6rem 0.7rem; background: #14171d;
            border: 1px solid #2a3140; border-radius: 6px; font-size: 0.84rem; color: #d6dae2; max-width: 32rem;
        }
        .panel .axis { font-variant-numeric: tabular-nums; margin: 0.2rem 0; }
        .panel .axis strong { color: #9ec4ff; }
        .panel .muted { color: #8a93a2; }
        .caption { color: #8a93a2; font-style: italic; margin-top: 0.4rem; font-size: 0.78rem; }
    `;

    @property({ attribute: false }) client!: RegradeClient;
    @property({ attribute: false }) glosses: GlossMap = {};

    @state() private phase: Phase = 'idle';
    @state() private sample: ChainRecord[] = [];
    @state() private index = 0;
    @state() private agreement: RegradeAgreement | null = null;
    @state() private error: string | null = null;

    private get current(): ChainRecord | null {
        return this.sample[this.index] ?? null;
    }

    private _seed(): number {
        // App-side randomness is fine here (not a workflow script). A fresh seed each
        // session draws a different blind subset, broadening floor coverage over time.
        return Math.floor(Math.random() * 1_000_000);
    }

    private async _start(): Promise<void> {
        this.phase = 'loading';
        this.error = null;
        this.agreement = null;
        try {
            const res = await this.client.getRegradeSample({ n: BATCH_N, minAgeDays: MIN_AGE_DAYS, seed: this._seed() });
            this.sample = res.records;
            this.index = 0;
            this.phase = this.sample.length ? 'grading' : 'done';
            if (!this.sample.length) await this._loadAgreement();
        } catch (e) {
            this.error = e instanceof Error ? e.message : 'failed to draw a re-grade batch';
            this.phase = 'error';
        }
    }

    private async _onVerdict(e: CustomEvent<VerdictSubmitDetail>): Promise<void> {
        const chain = this.current;
        if (!chain) return;
        const record: JudgementRecord = {
            schema_version: 'judgement.v2',
            judged_by: 'julian',
            round: chain.round,
            topic: chain.topic,
            topic_synset_id: chain.topic_synset_id,
            vehicle: chain.vehicle,
            vehicle_synset_id: chain.vehicle_synset_id,
            proposer: chain.proposer,
            chain_signature: chain.chain_signature,
            linkage: e.detail.linkage,
            metaphor: e.detail.metaphor,
            tiers: e.detail.tiers,
            tags: e.detail.tags,
            confidence: e.detail.confidence,
            notes: e.detail.notes,
            // Blind pass is independent of the gold verdict; the regrades file
            // resolves latest-wins on its own, so nothing to supersede here.
            supersedes_ts: null,
        };
        try {
            await this.client.postRegrade(record);
            this.error = null;
            this.index += 1;
            if (this.index >= this.sample.length) {
                this.phase = 'done';
                await this._loadAgreement();
            }
        } catch (err) {
            // Don't advance — keep the chain so the operator can retry, no lost pairing.
            this.error = err instanceof Error ? err.message : 'failed to record re-grade';
        }
    }

    private async _loadAgreement(): Promise<void> {
        try {
            this.agreement = await this.client.getRegradeAgreement();
        } catch (e) {
            this.error = e instanceof Error ? e.message : 'failed to load agreement';
        }
    }

    render() {
        if (this.phase === 'idle') return this._renderIntro();
        if (this.phase === 'error') return html`
            <div class="err" data-testid="regrade-error">error: ${this.error}</div>
            <button class="primary" data-testid="regrade-start" @click=${this._start}>Try again</button>`;
        if (this.phase === 'loading') return html`<div class="intro">drawing a blind batch…</div>`;
        if (this.phase === 'grading') return this._renderGrading();
        return this._renderDone();
    }

    private _renderIntro() {
        return html`
            <div class="intro">
                Blind re-grade — re-judge a sample of your older verdicts with no prior shown.
                Measures how much you agree with yourself (the reliability floor every κ gate depends on).
                <span class="muted">Verdicts go to a separate file; your original grades are never touched.</span>
            </div>
            <button class="primary" data-testid="regrade-start" @click=${this._start}>Start blind re-grade</button>`;
    }

    private _renderGrading() {
        return html`
            <div class="bar" role="toolbar" aria-label="Blind re-grade">
                <span class="badge">blind</span>
                <span class="pos" data-testid="regrade-progress" aria-live="polite">${this.index + 1} / ${this.sample.length}</span>
            </div>
            ${this.error ? html`<div class="err" data-testid="regrade-error">error: ${this.error}</div>` : ''}
            <mf-grade-panel
                .chain=${this.current}
                .priorVerdict=${null}
                .glosses=${this.glosses}
                @verdict-submit=${this._onVerdict}
            ></mf-grade-panel>`;
    }

    private _fmt(v: number | null): string {
        return v === null ? '—' : v.toFixed(2);
    }

    private _renderDone() {
        const a = this.agreement;
        return html`
            <div class="panel" data-testid="regrade-agreement">
                ${a
                    ? html`
                        <div><strong>${a.n_pairs}</strong> chains re-graded blind</div>
                        <div class="axis">metaphor: agreement <strong>${this._fmt(a.metaphor.agreement)}</strong>
                            <span class="muted">· κ ${this._fmt(a.metaphor.kappa)}</span></div>
                        <div class="axis">linkage: agreement <strong>${this._fmt(a.linkage.agreement)}</strong>
                            <span class="muted">· κ ${this._fmt(a.linkage.kappa)}</span></div>
                        <div class="caption">κ below ~0.4 means the verdicts are too noisy to train a judge on — fix the rubric before scaling.</div>`
                    : html`<div class="muted">no overlapping pairs yet — grade a batch to measure the floor.</div>`}
            </div>
            ${this.error ? html`<div class="err" data-testid="regrade-error">error: ${this.error}</div>` : ''}
            <button class="primary" data-testid="regrade-start" @click=${this._start}>Grade another batch</button>`;
    }
}

declare global {
    interface HTMLElementTagNameMap {
        'mf-grade-regrade': MfGradeRegrade;
    }
}
