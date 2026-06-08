import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import './mf-signal-report';
import { MfSignalReport } from './mf-signal-report';
import type { SignalReport } from '../types/grading';

const tick = () => new Promise(r => setTimeout(r, 0));

const REPORT: SignalReport = {
    n: 72, n_live: 44, n_dead: 28, base_rate_live: 0.611,
    n_topics: 15, n_both_class_topics: 12, n_powered_topics: 6,
    per_topic: [{ topic_synset_id: 'T', topic: 'adornment', live: 5, dead: 5, pairs: 25 }],
    geometry_available: true,
    geometry_features: [
        { name: 'max_hop_cos', within_topic_auc: 0.674, n_pairs: 89 },
        { name: 'std_hop_cos', within_topic_auc: 0.657, n_pairs: 70 },
    ],
    server_ts: '2026-06-08T00:00:00Z',
};

describe('mf-signal-report', () => {
    let el: MfSignalReport;
    let getSignalReport: ReturnType<typeof vi.fn>;

    beforeEach(async () => {
        getSignalReport = vi.fn().mockResolvedValue(REPORT);
        el = document.createElement('mf-signal-report') as MfSignalReport;
        el.client = { getSignalReport } as any;
        document.body.appendChild(el);
        await el.updateComplete;
    });

    afterEach(() => el.remove());

    const load = async () => {
        (el.shadowRoot!.querySelector('[data-testid="signal-load"]') as HTMLElement).click();
        await el.updateComplete; await tick(); await el.updateComplete;
    };

    it('shows only a trigger button before loading', () => {
        expect(el.shadowRoot!.querySelector('[data-testid="signal-load"]')).toBeTruthy();
        expect(el.shadowRoot!.querySelector('[data-testid="signal-body"]')).toBeNull();
    });

    it('fetches and renders coverage on click', async () => {
        await load();
        expect(getSignalReport).toHaveBeenCalledOnce();
        const text = el.shadowRoot!.textContent || '';
        expect(text).toContain('44');   // live
        expect(text).toContain('28');   // dead
        expect(text).toContain('15');   // topics
        expect(text).toContain('12');   // both-class
        expect(text).toContain('6');    // powered
    });

    it('renders the within-topic geometry concordance', async () => {
        await load();
        const text = el.shadowRoot!.textContent || '';
        expect(text).toContain('max_hop_cos');
        expect(text).toContain('0.67');   // AUC formatted
        expect(text).toContain('89');     // n_pairs
    });

    it('notes when geometry is unavailable', async () => {
        getSignalReport.mockResolvedValue({ ...REPORT, geometry_available: false, geometry_features: [] });
        await load();
        const text = (el.shadowRoot!.textContent || '').toLowerCase();
        expect(text).toContain('geometry');
    });

    it('surfaces an error when the fetch fails', async () => {
        getSignalReport.mockRejectedValue(new Error('getSignalReport: 500'));
        await load();
        const text = (el.shadowRoot!.textContent || '').toLowerCase();
        expect(text).toContain('error');
    });
});
