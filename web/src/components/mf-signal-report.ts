import { LitElement, html, css } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import type { GradingClient } from '../api/grading-client';
import type { SignalReport } from '../types/grading';

// On-demand signal dashboard for the grading tool. Click to re-read the curated
// graph's live/dead signal after a grading batch: coverage (the binding breadth
// constraint — topics, both-class topics, powered topics) plus the within-topic
// path-geometry concordance (max_hop_cos = "one big leap"). The heavy compute is
// precomputed offline; this just fetches GET /api/grading/signal.
@customElement('mf-signal-report')
export class MfSignalReport extends LitElement {
    static styles = css`
        :host { display: block; }
        button.trigger {
            padding: 0.35rem 0.7rem; font-size: 0.8rem; cursor: pointer;
            background: #181b22; color: #c8c8c8; border: 1px solid #2a3140; border-radius: 4px;
        }
        button.trigger:hover { border-color: #6db86d; }
        button.trigger:disabled { opacity: 0.6; cursor: progress; }
        .panel {
            margin-top: 0.4rem; padding: 0.6rem 0.7rem; background: #14171d;
            border: 1px solid #2a3140; border-radius: 6px; font-size: 0.82rem; color: #d6dae2;
            max-width: 30rem;
        }
        .row { display: flex; flex-wrap: wrap; gap: 0.5rem 1rem; margin: 0.15rem 0; }
        .stat strong { color: #8fd28f; font-weight: 600; }
        .warn { color: #d6a560; }
        .muted { color: #8a93a2; }
        .geom { margin-top: 0.4rem; border-top: 1px solid #2a3140; padding-top: 0.4rem; }
        .feat { font-variant-numeric: tabular-nums; }
        .feat strong { color: #9ec4ff; }
        .caption { color: #8a93a2; font-style: italic; margin-top: 0.35rem; font-size: 0.78rem; }
        .err { color: #e09a9a; }
        .head { display: flex; align-items: center; gap: 0.5rem; justify-content: space-between; }
        button.refresh {
            font-size: 0.72rem; padding: 0.15rem 0.45rem; cursor: pointer;
            background: #181b22; color: #9aa3b2; border: 1px solid #2a3140; border-radius: 3px;
        }
    `;

    @property({ attribute: false }) client!: Pick<GradingClient, 'getSignalReport'>;

    @state() private report: SignalReport | null = null;
    @state() private loading = false;
    @state() private error: string | null = null;

    private async _load() {
        this.loading = true;
        this.error = null;
        try {
            this.report = await this.client.getSignalReport();
        } catch (e) {
            this.error = e instanceof Error ? e.message : 'failed to load signal report';
            this.report = null;
        } finally {
            this.loading = false;
        }
    }

    private _fmtAuc(auc: number | null): string {
        return auc === null ? '—' : auc.toFixed(2);
    }

    render() {
        return html`
            <button class="trigger" data-testid="signal-load" ?disabled=${this.loading}
                    @click=${this._load}>
                ${this.loading ? 'reading signal…' : 'Signal report'}
            </button>
            ${this.error ? html`<div class="panel err" data-testid="signal-error">error: ${this.error}</div>` : ''}
            ${this.report ? this._renderReport(this.report) : ''}
        `;
    }

    private _renderReport(r: SignalReport) {
        return html`
            <div class="panel" data-testid="signal-body">
                <div class="head">
                    <span><strong>${r.n}</strong> graded
                        <span class="muted">(${r.n_live} live / ${r.n_dead} dead)</span></span>
                    <button class="refresh" data-testid="signal-refresh" @click=${this._load}>refresh</button>
                </div>
                <div class="row">
                    <span class="stat"><strong>${r.n_topics}</strong> topics</span>
                    <span class="stat"><strong>${r.n_both_class_topics}</strong> both-class</span>
                    <span class="stat"><strong>${r.n_powered_topics}</strong> powered <span class="muted">(≥5 pairs)</span></span>
                </div>
                <div class="row">
                    <span class="stat" data-testid="signal-linkage"><strong>${r.n_linkage_bad}</strong> bad-linkage
                        <span class="muted">/ ${r.n_linkage_good} good</span></span>
                    ${r.n_excluded_bad_head > 0
                        ? html`<span class="warn" data-testid="signal-badhead">⚠ ${r.n_excluded_bad_head} bad_head excluded from liveness</span>`
                        : ''}
                </div>
                ${r.geometry_available && r.geometry_features.length
                    ? html`
                        <div class="geom">
                            <div class="muted">within-topic concordance (live = bigger leap):</div>
                            ${r.geometry_features.map(f => html`
                                <div class="feat">${f.name}
                                    <strong>${this._fmtAuc(f.within_topic_auc)}</strong>
                                    <span class="muted">(${f.n_pairs} pairs)</span></div>
                            `)}
                        </div>
                        <div class="caption">breadth is the binding constraint — grow both-class topics to power the cross-topic test.</div>
                    `
                    : html`<div class="geom muted">geometry not precomputed — coverage only.</div>`}
            </div>
        `;
    }
}

declare global {
    interface HTMLElementTagNameMap {
        'mf-signal-report': MfSignalReport;
    }
}
