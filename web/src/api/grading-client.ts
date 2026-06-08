import type { ChainRecord, JudgementRecord, SignalReport, TopicSummary, WalkResponse } from '../types/grading';

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
        let lastError: Error | null = null;
        for (let attempt = 0; attempt <= RETRY_DELAYS_MS.length; attempt++) {
            try {
                const r = await fetch(`${BASE}/judgements`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(j),
                });
                if (r.ok) return r.json();
                if (r.status >= 400 && r.status < 500) {
                    throw new Error(`postJudgement: ${r.status} (no retry)`);
                }
                lastError = new Error(`postJudgement: ${r.status}`);
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
