import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import './mf-grade-sensecheck';
import { MfGradeSensecheck } from './mf-grade-sensecheck';
import type { SenseCheckItem } from '../types/grading';

const tick = () => new Promise(r => setTimeout(r, 0));

function item(word = 'apprehension', role: 'topic' | 'vehicle' = 'topic'): SenseCheckItem {
    return {
        role, word, snapped_synset_id: '1760', stratum: 'flagged',
        snapped_gloss: 'the act of arresting a criminal', pos: 'n',
        candidates: [
            { synset_id: '1760', pos: 'n', gloss: 'the act of arresting a criminal', tagcount: 2 },
            { synset_id: '72797', pos: 'n', gloss: 'fearful expectation', tagcount: null },
        ],
        context: { chains: [
            { topic: 'apprehension', vehicle: 'avalanche', chain_signature: 'a',
              chain: [{ phrase: 'apprehension', head: 'apprehension', synset_id: '1760' },
                      { phrase: 'avalanche', head: 'avalanche', synset_id: '9' }] },
        ] },
        chain_signature: 'a',
    };
}

describe('mf-grade-sensecheck', () => {
    let el: MfGradeSensecheck;
    let getSenseCheckSample: ReturnType<typeof vi.fn>;
    let postSenseLabel: ReturnType<typeof vi.fn>;

    beforeEach(async () => {
        getSenseCheckSample = vi.fn().mockResolvedValue({ count: 2, items: [item(), item('river', 'vehicle')] });
        postSenseLabel = vi.fn().mockResolvedValue({});
        el = document.createElement('mf-grade-sensecheck') as MfGradeSensecheck;
        el.client = { getSenseCheckSample, postSenseLabel } as any;
        document.body.appendChild(el);
        await el.updateComplete;
    });
    afterEach(() => el.remove());

    const start = async () => {
        (el.shadowRoot!.querySelector('[data-testid="sensecheck-start"]') as HTMLElement).click();
        await el.updateComplete; await tick(); await el.updateComplete;
    };
    const click = async (sel: string) => {
        (el.shadowRoot!.querySelector(sel) as HTMLElement).click();
        await el.updateComplete; await tick(); await el.updateComplete;
    };

    it('shows only a start button before a batch is drawn', () => {
        expect(el.shadowRoot!.querySelector('[data-testid="sensecheck-start"]')).toBeTruthy();
        expect(el.shadowRoot!.querySelector('[data-testid="sensecheck-item"]')).toBeNull();
    });

    it('draws a sample and renders the first item word/role/gloss', async () => {
        await start();
        expect(getSenseCheckSample).toHaveBeenCalledOnce();
        const txt = el.shadowRoot!.querySelector('[data-testid="sensecheck-item"]')!.textContent!;
        expect(txt).toContain('apprehension');
        expect(txt).toContain('topic');
        expect(txt).toContain('the act of arresting a criminal');
        expect(el.shadowRoot!.querySelector('[data-testid="sensecheck-progress"]')!.textContent).toContain('1 / 2');
    });

    it('posts a "right" verdict (no intended) and advances', async () => {
        await start();
        await click('[data-testid="verdict-right"]');
        expect(postSenseLabel).toHaveBeenCalledOnce();
        const posted = postSenseLabel.mock.calls[0][0];
        expect(posted.verdict).toBe('right');
        expect(posted.intended_synset_id).toBeNull();
        expect(posted.snapped_synset_id).toBe('1760');
        expect(el.shadowRoot!.querySelector('[data-testid="sensecheck-progress"]')!.textContent).toContain('2 / 2');
    });

    it('does not advance when a POST fails (no lost label)', async () => {
        await start();
        postSenseLabel.mockRejectedValue(new Error('postSenseLabel: 500'));
        await click('[data-testid="verdict-right"]');
        expect(el.shadowRoot!.querySelector('[data-testid="sensecheck-progress"]')!.textContent).toContain('1 / 2');
        expect((el.shadowRoot!.textContent || '').toLowerCase()).toContain('error');
    });

    it('Wrong reveals candidates; picking one posts that intended_synset_id', async () => {
        await start();
        // No candidate list until a Wrong/Rare verdict.
        expect(el.shadowRoot!.querySelector('[data-testid="sensecheck-candidates"]')).toBeNull();
        await click('[data-testid="verdict-wrong"]');
        expect(el.shadowRoot!.querySelector('[data-testid="sensecheck-candidates"]')).toBeTruthy();
        // No POST yet — we still need the intended sense.
        expect(postSenseLabel).not.toHaveBeenCalled();
        await click('[data-testid="cand-72797"]');
        const posted = postSenseLabel.mock.calls[0][0];
        expect(posted.verdict).toBe('wrong');
        expect(posted.intended_synset_id).toBe('72797');
        expect(el.shadowRoot!.querySelector('[data-testid="sensecheck-progress"]')!.textContent).toContain('2 / 2');
    });

    it('ignores a rapid double-click (no double POST / double advance)', async () => {
        await start();
        const btn = el.shadowRoot!.querySelector('[data-testid="verdict-right"]') as HTMLElement;
        btn.click(); btn.click();              // two synchronous clicks, no await between
        await el.updateComplete; await tick(); await el.updateComplete;
        expect(postSenseLabel).toHaveBeenCalledOnce();
        expect(el.shadowRoot!.querySelector('[data-testid="sensecheck-progress"]')!.textContent).toContain('2 / 2');
    });

    it('Rare-but-better reveals candidates; picking one posts rare_ok with intended_synset_id', async () => {
        await start();
        // No candidate list until a Wrong/Rare verdict.
        expect(el.shadowRoot!.querySelector('[data-testid="sensecheck-candidates"]')).toBeNull();
        await click('[data-testid="verdict-rare"]');
        expect(el.shadowRoot!.querySelector('[data-testid="sensecheck-candidates"]')).toBeTruthy();
        // No POST yet — we still need the intended sense.
        expect(postSenseLabel).not.toHaveBeenCalled();
        await click('[data-testid="cand-72797"]');
        const posted = postSenseLabel.mock.calls[0][0];
        expect(posted.verdict).toBe('rare_ok');
        expect(posted.intended_synset_id).toBe('72797');
        expect(el.shadowRoot!.querySelector('[data-testid="sensecheck-progress"]')!.textContent).toContain('2 / 2');
    });

    it('context expander reveals the endpoint\'s chains on demand', async () => {
        getSenseCheckSample.mockResolvedValue({
            count: 1, items: [{
                ...item(),
                context: { chains: [
                    { topic: 'apprehension', vehicle: 'avalanche', chain_signature: 'a',
                      chain: [{ phrase: 'apprehension', head: 'apprehension', synset_id: '1760' },
                              { phrase: 'avalanche', head: 'avalanche', synset_id: '9' }] },
                    { topic: 'apprehension', vehicle: 'trapdoor', chain_signature: 'b',
                      chain: [{ phrase: 'apprehension', head: 'apprehension', synset_id: '1760' },
                              { phrase: 'trapdoor', head: 'trapdoor', synset_id: '8' }] },
                ] },
            }],
        });
        await start();
        // Collapsed by default.
        expect(el.shadowRoot!.querySelector('[data-testid="sensecheck-context"]')).toBeNull();
        expect(el.shadowRoot!.querySelector('[data-testid="ctx-toggle"]')!.textContent).toContain('2 chains');
        await click('[data-testid="ctx-toggle"]');
        const ctx = el.shadowRoot!.querySelector('[data-testid="sensecheck-context"]')!.textContent!;
        expect(ctx).toContain('avalanche');   // both chains shown
        expect(ctx).toContain('trapdoor');
    });
});
