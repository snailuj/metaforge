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
});
