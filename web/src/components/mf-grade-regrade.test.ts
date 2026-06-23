import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import './mf-grade-regrade';
import { MfGradeRegrade } from './mf-grade-regrade';
import type { ChainRecord } from '../types/grading';

const tick = () => new Promise(r => setTimeout(r, 0));

function chain(sig: string, topic = 'anxiety', vehicle = 'swarm'): ChainRecord {
    return {
        schema_version: 'chain.v1', topic, topic_synset_id: '72810', vehicle,
        vehicle_synset_id: '9', proposer: 'sonnet', round: 1, chain_signature: sig,
        chain: [
            { phrase: topic, head: topic, synset_id: '72810' },
            { phrase: vehicle, head: vehicle, synset_id: '9' },
        ],
        generated_at: '2026-06-01T00:00:00+00:00',
    };
}

describe('mf-grade-regrade', () => {
    let el: MfGradeRegrade;
    let getRegradeSample: ReturnType<typeof vi.fn>;
    let postRegrade: ReturnType<typeof vi.fn>;
    let getRegradeAgreement: ReturnType<typeof vi.fn>;

    beforeEach(async () => {
        getRegradeSample = vi.fn().mockResolvedValue({ count: 2, records: [chain('a'), chain('b')] });
        postRegrade = vi.fn().mockResolvedValue({});
        getRegradeAgreement = vi.fn().mockResolvedValue({
            n_pairs: 2, metaphor: { agreement: 0.5, kappa: 0.0 }, linkage: { agreement: 1.0, kappa: null },
        });
        el = document.createElement('mf-grade-regrade') as MfGradeRegrade;
        el.client = { getRegradeSample, postRegrade, getRegradeAgreement } as any;
        document.body.appendChild(el);
        await el.updateComplete;
    });

    afterEach(() => el.remove());

    const start = async () => {
        (el.shadowRoot!.querySelector('[data-testid="regrade-start"]') as HTMLElement).click();
        await el.updateComplete; await tick(); await el.updateComplete;
    };

    const submit = async (verdict: 'live' | 'dead' | 'irrelevant') => {
        const panel = el.shadowRoot!.querySelector('mf-grade-panel')!;
        (panel.shadowRoot!.querySelector(`[data-testid="metaphor-${verdict}"]`) as HTMLElement).click();
        await el.updateComplete; await tick(); await el.updateComplete; await tick(); await el.updateComplete;
    };

    it('shows only a start button before a batch is drawn', () => {
        expect(el.shadowRoot!.querySelector('[data-testid="regrade-start"]')).toBeTruthy();
        expect(el.shadowRoot!.querySelector('mf-grade-panel')).toBeNull();
    });

    it('draws a blind batch and renders the first chain WITHOUT a prior verdict', async () => {
        await start();
        expect(getRegradeSample).toHaveBeenCalledOnce();
        const panel = el.shadowRoot!.querySelector('mf-grade-panel') as any;
        expect(panel).toBeTruthy();
        // The blind invariant: no prior verdict reaches the panel, so no "last saved" echo.
        expect(panel.priorVerdict).toBeNull();
        expect(panel.shadowRoot!.querySelector('[data-testid="last-saved"]')).toBeNull();
        // Progress readout.
        expect(el.shadowRoot!.querySelector('[data-testid="regrade-progress"]')!.textContent).toContain('1 / 2');
    });

    it('posts each verdict to the regrade endpoint and advances', async () => {
        await start();
        await submit('live');
        expect(postRegrade).toHaveBeenCalledOnce();
        const posted = postRegrade.mock.calls[0][0];
        expect(posted.chain_signature).toBe('a');
        expect(posted.metaphor).toBe('live');
        expect(posted.schema_version).toBe('judgement.v2');
        expect(el.shadowRoot!.querySelector('[data-testid="regrade-progress"]')!.textContent).toContain('2 / 2');
    });

    it('fetches and renders the agreement floor after the last verdict', async () => {
        await start();
        await submit('live');
        await submit('dead');
        expect(getRegradeAgreement).toHaveBeenCalledOnce();
        const body = el.shadowRoot!.querySelector('[data-testid="regrade-agreement"]')!.textContent!;
        expect(body).toContain('2');       // n_pairs
        expect(body).toContain('0.5');     // metaphor agreement
        expect(el.shadowRoot!.querySelector('mf-grade-panel')).toBeNull();   // batch over
    });

    it('surfaces an error when the sample fetch fails', async () => {
        getRegradeSample.mockRejectedValue(new Error('getRegradeSample: 500'));
        await start();
        const text = (el.shadowRoot!.textContent || '').toLowerCase();
        expect(text).toContain('error');
        expect(el.shadowRoot!.querySelector('mf-grade-panel')).toBeNull();
    });

    it('does not advance when a verdict POST fails (no lost pairing)', async () => {
        await start();
        postRegrade.mockRejectedValue(new Error('postRegrade: 500'));
        await submit('live');
        // Still on the first chain so the operator can retry.
        expect(el.shadowRoot!.querySelector('[data-testid="regrade-progress"]')!.textContent).toContain('1 / 2');
        expect((el.shadowRoot!.textContent || '').toLowerCase()).toContain('error');
    });
});
