import { describe, it, expect, beforeEach, vi } from 'vitest';
import { GradingClient } from './grading-client';

describe('GradingClient', () => {
    let fetchMock: ReturnType<typeof vi.fn>;
    beforeEach(() => {
        fetchMock = vi.fn();
        global.fetch = fetchMock as unknown as typeof fetch;
    });

    it('probe returns true on 200', async () => {
        fetchMock.mockResolvedValue({ ok: true, status: 200 });
        const client = new GradingClient();
        expect(await client.probe()).toBe(true);
    });

    it('probe returns true on 401 (auth required, still available)', async () => {
        fetchMock.mockResolvedValue({ ok: false, status: 401 });
        const client = new GradingClient();
        expect(await client.probe()).toBe(true);
    });

    it('probe returns false on 404', async () => {
        fetchMock.mockResolvedValue({ ok: false, status: 404 });
        const client = new GradingClient();
        expect(await client.probe()).toBe(false);
    });

    it('probe returns false on network error', async () => {
        fetchMock.mockRejectedValue(new Error('network'));
        const client = new GradingClient();
        expect(await client.probe()).toBe(false);
    });

    it('postJudgement retries 3x on 5xx with exponential backoff', async () => {
        vi.useFakeTimers();
        fetchMock
            .mockResolvedValueOnce({ ok: false, status: 500 })
            .mockResolvedValueOnce({ ok: false, status: 500 })
            .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ ts: 'x' }) });
        const client = new GradingClient();
        const promise = client.postJudgement({} as any);
        await vi.runAllTimersAsync();
        const result = await promise;
        expect(result.ts).toBe('x');
        expect(fetchMock).toHaveBeenCalledTimes(3);
        vi.useRealTimers();
    });

    it('postJudgement does not retry on 4xx', async () => {
        fetchMock.mockResolvedValue({ ok: false, status: 422 });
        const client = new GradingClient();
        await expect(client.postJudgement({} as any)).rejects.toThrow();
        expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    it('getWalk fetches the walk endpoint and returns entries', async () => {
        const payload = { count: 1, entries: [{ chain_signature: 's1', topic: 'anger', vehicle: 'venom', dwell_index: 0, dwell_n: 2, record: { chain_signature: 's1' } }] };
        fetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => payload });
        const client = new GradingClient();
        const res = await client.getWalk();
        expect(fetchMock).toHaveBeenCalledWith('/api/grading/walk');
        expect(res.count).toBe(1);
        expect(res.entries[0].record.chain_signature).toBe('s1');
    });

    it('getWalk throws on non-200', async () => {
        fetchMock.mockResolvedValue({ ok: false, status: 500 });
        const client = new GradingClient();
        await expect(client.getWalk()).rejects.toThrow('getWalk: 500');
    });

    it('getSignalReport fetches the signal endpoint and returns the report', async () => {
        const payload = { n: 72, n_live: 44, n_dead: 28, n_topics: 15, n_both_class_topics: 12,
            n_powered_topics: 6, base_rate_live: 0.611, per_topic: [],
            geometry_available: true, geometry_features: [{ name: 'max_hop_cos', within_topic_auc: 0.674, n_pairs: 89 }],
            server_ts: 'x' };
        fetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => payload });
        const client = new GradingClient();
        const res = await client.getSignalReport();
        expect(fetchMock).toHaveBeenCalledWith('/api/grading/signal');
        expect(res.n).toBe(72);
        expect(res.geometry_features[0].within_topic_auc).toBe(0.674);
    });

    it('getSignalReport throws on non-200', async () => {
        fetchMock.mockResolvedValue({ ok: false, status: 500 });
        const client = new GradingClient();
        await expect(client.getSignalReport()).rejects.toThrow('getSignalReport: 500');
    });

    it('getGlosses fetches the glosses endpoint and returns the map', async () => {
        fetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => ({ glosses: { '1': { pos: 'n', definition: 'an antique' } } }) });
        const client = new GradingClient();
        const res = await client.getGlosses();
        expect(fetchMock).toHaveBeenCalledWith('/api/grading/glosses');
        expect(res.glosses['1'].pos).toBe('n');
    });

    it('getGlosses throws on non-200', async () => {
        fetchMock.mockResolvedValue({ ok: false, status: 500 });
        const client = new GradingClient();
        await expect(client.getGlosses()).rejects.toThrow('getGlosses: 500');
    });

    it('getRegradeSample passes n/min_age_days/seed and returns blind chains', async () => {
        const payload = { count: 1, records: [{ chain_signature: 's1', topic: 'anger', chain: [] }] };
        fetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => payload });
        const client = new GradingClient();
        const res = await client.getRegradeSample({ n: 8, minAgeDays: 2, seed: 5 });
        expect(fetchMock).toHaveBeenCalledWith('/api/grading/regrade/sample?n=8&min_age_days=2&seed=5');
        expect(res.records[0].chain_signature).toBe('s1');
    });

    it('getRegradeSample throws on non-200', async () => {
        fetchMock.mockResolvedValue({ ok: false, status: 500 });
        const client = new GradingClient();
        await expect(client.getRegradeSample({ n: 1, minAgeDays: 1, seed: 1 })).rejects.toThrow('getRegradeSample: 500');
    });

    it('postRegrade posts to the regrade endpoint (separate file, never gold)', async () => {
        fetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => ({ metaphor: 'live' }) });
        const client = new GradingClient();
        const res = await client.postRegrade({ metaphor: 'live' } as any);
        const [url, init] = fetchMock.mock.calls[0];
        expect(url).toBe('/api/grading/regrade');
        expect(init.method).toBe('POST');
        expect(res.metaphor).toBe('live');
    });

    it('postRegrade retries 3x on 5xx like postJudgement', async () => {
        vi.useFakeTimers();
        fetchMock
            .mockResolvedValueOnce({ ok: false, status: 500 })
            .mockResolvedValueOnce({ ok: false, status: 500 })
            .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ ts: 'y' }) });
        const client = new GradingClient();
        const promise = client.postRegrade({} as any);
        await vi.runAllTimersAsync();
        expect((await promise).ts).toBe('y');
        expect(fetchMock).toHaveBeenCalledTimes(3);
        vi.useRealTimers();
    });

    it('getRegradeAgreement returns the per-axis agreement report', async () => {
        const payload = { n_pairs: 12, metaphor: { agreement: 0.83, kappa: 0.62 }, linkage: { agreement: 0.75, kappa: 0.4 } };
        fetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => payload });
        const client = new GradingClient();
        const res = await client.getRegradeAgreement();
        expect(fetchMock).toHaveBeenCalledWith('/api/grading/regrade/agreement');
        expect(res.n_pairs).toBe(12);
        expect(res.metaphor.kappa).toBe(0.62);
    });

    it('getRegradeAgreement throws on non-200', async () => {
        fetchMock.mockResolvedValue({ ok: false, status: 500 });
        const client = new GradingClient();
        await expect(client.getRegradeAgreement()).rejects.toThrow('getRegradeAgreement: 500');
    });

    it('getSenseCheckSample requests the stratified sample endpoint', async () => {
        fetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => ({ count: 0, items: [] }) });
        const client = new GradingClient();
        await client.getSenseCheckSample({ nFlagged: 40, nRandom: 40, seed: 3 });
        expect(fetchMock).toHaveBeenCalledWith('/api/grading/sense-check/sample?n_flagged=40&n_random=40&seed=3');
    });

    it('postSenseLabel POSTs to the sense-check endpoint', async () => {
        fetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => ({}) });
        const client = new GradingClient();
        await client.postSenseLabel({
            schema_version: 'sense_label.v1', role: 'topic', word: 'apprehension',
            snapped_synset_id: '1760', verdict: 'wrong', intended_synset_id: '72797',
            chain_signature: 'a',
        });
        expect(fetchMock).toHaveBeenCalledWith('/api/grading/sense-check', expect.objectContaining({ method: 'POST' }));
    });
});
