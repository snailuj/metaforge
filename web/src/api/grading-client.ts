import type { ChainRecord, GlossMap, JudgementRecord, RegradeAgreement, SenseCheckSample, SenseLabel, SignalReport, TopicSummary, WalkResponse } from '../types/grading';

const BASE = '/api/grading';
const RETRY_DELAYS_MS = [1000, 3000, 9000];

export class GradingClient {
    async probe(): Promise<boolean> {
        try {
            const r = await fetch(`${BASE}/healthz`);
            // 200 OR 401 both mean "grading is available here"
            return r.ok || r.status === 401;
        } catch {
            return false;
        }
    }

    async getTopics(): Promise<{ topics: TopicSummary[] }> {
        const r = await fetch(`${BASE}/topics`);
        if (!r.ok) throw new Error(`getTopics: ${r.status}`);
        return r.json();
    }

    async getChains(topic?: string): Promise<{ count: number; records: ChainRecord[] }> {
        const url = topic ? `${BASE}/chains?topic=${encodeURIComponent(topic)}` : `${BASE}/chains`;
        const r = await fetch(url);
        if (!r.ok) throw new Error(`getChains: ${r.status}`);
        return r.json();
    }

    async getWalk(): Promise<WalkResponse> {
        const r = await fetch(`${BASE}/walk`);
        if (!r.ok) throw new Error(`getWalk: ${r.status}`);
        return r.json();
    }

    async getGlosses(): Promise<{ glosses: GlossMap }> {
        const r = await fetch(`${BASE}/glosses`);
        if (!r.ok) throw new Error(`getGlosses: ${r.status}`);
        return r.json();
    }

    async getSignalReport(): Promise<SignalReport> {
        const r = await fetch(`${BASE}/signal`);
        if (!r.ok) throw new Error(`getSignalReport: ${r.status}`);
        return r.json();
    }

    async getJudgements(topic?: string): Promise<{ count: number; records: JudgementRecord[] }> {
        const url = topic ? `${BASE}/judgements?topic=${encodeURIComponent(topic)}` : `${BASE}/judgements`;
        const r = await fetch(url);
        if (!r.ok) throw new Error(`getJudgements: ${r.status}`);
        return r.json();
    }

    async postJudgement(j: JudgementRecord): Promise<JudgementRecord> {
        return this._postWithRetry(`${BASE}/judgements`, j, 'postJudgement');
    }

    /** Blind re-grade verdict → the SEPARATE regrades file (never the gold
     *  judgements). Same retry policy as postJudgement. */
    async postRegrade(j: JudgementRecord): Promise<JudgementRecord> {
        return this._postWithRetry(`${BASE}/regrade`, j, 'postRegrade');
    }

    /** POST JSON with the shared retry policy: 3x on 5xx/network (exponential
     *  backoff), never on 4xx (a 4xx is a contract error — retrying is pointless).
     *  `label` only shapes the thrown message so callers can distinguish endpoints. */
    private async _postWithRetry(url: string, body: unknown, label: string): Promise<any> {
        let lastError: Error | null = null;
        for (let attempt = 0; attempt <= RETRY_DELAYS_MS.length; attempt++) {
            try {
                const r = await fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                if (r.ok) return r.json();
                if (r.status >= 400 && r.status < 500) {
                    throw new Error(`${label}: ${r.status} (no retry)`);
                }
                lastError = new Error(`${label}: ${r.status}`);
            } catch (e) {
                if (e instanceof Error && e.message.includes('no retry')) throw e;
                lastError = e as Error;
            }
            if (attempt < RETRY_DELAYS_MS.length) {
                await new Promise(res => setTimeout(res, RETRY_DELAYS_MS[attempt]));
            }
        }
        throw lastError!;
    }

    /** Draw a blind, class-stratified re-grade batch (chains only, no verdicts). */
    async getRegradeSample(opts: { n: number; minAgeDays: number; seed: number }): Promise<{ count: number; records: ChainRecord[] }> {
        const q = `n=${opts.n}&min_age_days=${opts.minAgeDays}&seed=${opts.seed}`;
        const r = await fetch(`${BASE}/regrade/sample?${q}`);
        if (!r.ok) throw new Error(`getRegradeSample: ${r.status}`);
        return r.json();
    }

    /** Draw a stratified sense-check sample (endpoints + candidates + context). */
    async getSenseCheckSample(opts: { nFlagged: number; nRandom: number; seed: number }): Promise<SenseCheckSample> {
        const q = `n_flagged=${opts.nFlagged}&n_random=${opts.nRandom}&seed=${opts.seed}`;
        const r = await fetch(`${BASE}/sense-check/sample?${q}`);
        if (!r.ok) throw new Error(`getSenseCheckSample: ${r.status}`);
        return r.json();
    }

    /** Sense label → the SEPARATE sense-labels file (never the gold judgements). */
    async postSenseLabel(l: SenseLabel): Promise<SenseLabel> {
        return this._postWithRetry(`${BASE}/sense-check`, l, 'postSenseLabel');
    }

    /** Intra-rater self-agreement of gold vs blind re-grades (per-axis κ + agreement). */
    async getRegradeAgreement(): Promise<RegradeAgreement> {
        const r = await fetch(`${BASE}/regrade/agreement`);
        if (!r.ok) throw new Error(`getRegradeAgreement: ${r.status}`);
        return r.json();
    }

    async getDesignNotes(): Promise<{ content: string }> {
        const r = await fetch(`${BASE}/design-notes`);
        if (!r.ok) throw new Error(`getDesignNotes: ${r.status}`);
        return r.json();
    }

    async postDesignNote(content: string): Promise<{ ts: string }> {
        const r = await fetch(`${BASE}/design-notes`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content }),
        });
        if (!r.ok) throw new Error(`postDesignNote: ${r.status}`);
        return r.json();
    }
}
