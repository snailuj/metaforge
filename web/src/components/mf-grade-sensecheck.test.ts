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
              topic_pos: 'n', topic_gloss: 'fearful expectation or anticipation',
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

    it('Skip advances without POSTing a label', async () => {
        await start();
        expect(el.shadowRoot!.querySelector('[data-testid="sensecheck-progress"]')!.textContent).toContain('1 / 2');
        (el.shadowRoot!.querySelector('[data-testid="verdict-skip"]') as HTMLElement).click();
        await el.updateComplete; await tick(); await el.updateComplete;
        expect(postSenseLabel).not.toHaveBeenCalled();                 // no label recorded
        expect(el.shadowRoot!.querySelector('[data-testid="sensecheck-progress"]')!.textContent).toContain('2 / 2');
    });

    it('context expander reveals the endpoint\'s chains on demand', async () => {
        getSenseCheckSample.mockResolvedValue({
            count: 1, items: [{
                ...item(),
                context: { chains: [
                    { topic: 'apprehension', vehicle: 'avalanche', chain_signature: 'a',
                      topic_pos: 'n', topic_gloss: 'fearful expectation or anticipation',
                      chain: [{ phrase: 'apprehension', head: 'apprehension', synset_id: '1760' },
                              { phrase: 'avalanche', head: 'avalanche', synset_id: '9' }] },
                    { topic: 'apprehension', vehicle: 'trapdoor', chain_signature: 'b',
                      topic_pos: null, topic_gloss: null,
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

    // -----------------------------------------------------------------------
    // Task 3: Back button
    // -----------------------------------------------------------------------

    it('Back button is absent/disabled at item 1', async () => {
        await start();
        // At index 0 (first item) the Back button must not exist or be disabled.
        const btn = el.shadowRoot!.querySelector('[data-testid="sensecheck-back"]') as HTMLButtonElement | null;
        if (btn) {
            expect(btn.disabled).toBe(true);
        }
        // Confirm we're at item 1.
        expect(el.shadowRoot!.querySelector('[data-testid="sensecheck-progress"]')!.textContent).toContain('1 / 2');
    });

    it('Back from item 2 returns to item 1 without POSTing', async () => {
        await start();
        // Advance to item 2 via Skip (no POST).
        await click('[data-testid="verdict-skip"]');
        expect(el.shadowRoot!.querySelector('[data-testid="sensecheck-progress"]')!.textContent).toContain('2 / 2');
        // Now go back.
        await click('[data-testid="sensecheck-back"]');
        expect(postSenseLabel).not.toHaveBeenCalled();
        expect(el.shadowRoot!.querySelector('[data-testid="sensecheck-progress"]')!.textContent).toContain('1 / 2');
    });

    // -----------------------------------------------------------------------
    // Task 3: topic POS/gloss in context panel
    // -----------------------------------------------------------------------

    // -----------------------------------------------------------------------
    // Fix 1: Back button in done phase
    // -----------------------------------------------------------------------

    it('done phase has a Back button that returns to the last item without an extra POST', async () => {
        // Label through both items to reach done phase.
        await start();
        await click('[data-testid="verdict-right"]');  // item 1 → posts, advances to item 2
        await click('[data-testid="verdict-right"]');  // item 2 → posts, advances to done
        expect(el.shadowRoot!.querySelector('[data-testid="sensecheck-done"]')).toBeTruthy();
        const postCountBeforeBack = postSenseLabel.mock.calls.length;
        // Back button must exist in done phase.
        const backBtn = el.shadowRoot!.querySelector('[data-testid="sensecheck-back"]') as HTMLElement | null;
        expect(backBtn).not.toBeNull();
        await click('[data-testid="sensecheck-back"]');
        // Must return to labelling phase at the last item (N / N).
        expect(el.shadowRoot!.querySelector('[data-testid="sensecheck-done"]')).toBeNull();
        expect(el.shadowRoot!.querySelector('[data-testid="sensecheck-progress"]')!.textContent).toContain('2 / 2');
        // No extra POST must have been triggered by Back.
        expect(postSenseLabel.mock.calls.length).toBe(postCountBeforeBack);
    });

    // -----------------------------------------------------------------------
    // Task 2 (ux4): 'split' verdict — multi-select picker + Confirm
    // -----------------------------------------------------------------------

    it('Split reveals the candidate list WITHOUT posting', async () => {
        await start();
        await click('[data-testid="verdict-split"]');
        // Candidate list must appear.
        expect(el.shadowRoot!.querySelector('[data-testid="sensecheck-candidates"]')).toBeTruthy();
        // No POST should have happened.
        expect(postSenseLabel).not.toHaveBeenCalled();
    });

    it('Split reveals Confirm button; clicking two candidates then Confirm posts split with both apt_synset_ids', async () => {
        await start();
        await click('[data-testid="verdict-split"]');
        // Confirm button should be visible.
        expect(el.shadowRoot!.querySelector('[data-testid="confirm-split"]')).toBeTruthy();
        // Tick two candidates.
        await click('[data-testid="cand-1760"]');
        await click('[data-testid="cand-72797"]');
        // Still no POST — waiting for Confirm.
        expect(postSenseLabel).not.toHaveBeenCalled();
        await click('[data-testid="confirm-split"]');
        expect(postSenseLabel).toHaveBeenCalledOnce();
        const posted = postSenseLabel.mock.calls[0][0];
        expect(posted.verdict).toBe('split');
        expect(posted.intended_synset_id).toBeNull();
        // Both synset_ids must appear in apt_synset_ids (order-insensitive).
        expect(posted.apt_synset_ids).toHaveLength(2);
        expect(posted.apt_synset_ids).toContain('1760');
        expect(posted.apt_synset_ids).toContain('72797');
        // Must advance.
        expect(el.shadowRoot!.querySelector('[data-testid="sensecheck-progress"]')!.textContent).toContain('2 / 2');
    });

    it('Clicking a candidate again un-ticks it (removed from the payload)', async () => {
        await start();
        await click('[data-testid="verdict-split"]');
        // Tick then un-tick candidate 1760.
        await click('[data-testid="cand-1760"]');
        await click('[data-testid="cand-1760"]');
        // Tick candidate 72797.
        await click('[data-testid="cand-72797"]');
        await click('[data-testid="confirm-split"]');
        const posted = postSenseLabel.mock.calls[0][0];
        expect(posted.apt_synset_ids).toHaveLength(1);
        expect(posted.apt_synset_ids).toContain('72797');
        expect(posted.apt_synset_ids).not.toContain('1760');
    });

    it('Wrong still single-selects and posts on the first candidate tap (unchanged)', async () => {
        await start();
        await click('[data-testid="verdict-wrong"]');
        // No Confirm button for wrong.
        expect(el.shadowRoot!.querySelector('[data-testid="confirm-split"]')).toBeNull();
        // Candidate tap posts immediately.
        await click('[data-testid="cand-72797"]');
        expect(postSenseLabel).toHaveBeenCalledOnce();
        const posted = postSenseLabel.mock.calls[0][0];
        expect(posted.verdict).toBe('wrong');
        expect(posted.intended_synset_id).toBe('72797');
        // apt_synset_ids must be [] on wrong.
        expect(posted.apt_synset_ids).toEqual([]);
    });

    it('Confirm with nothing ticked posts apt_synset_ids: []', async () => {
        await start();
        await click('[data-testid="verdict-split"]');
        // Do not tick any candidates — just confirm.
        await click('[data-testid="confirm-split"]');
        const posted = postSenseLabel.mock.calls[0][0];
        expect(posted.verdict).toBe('split');
        expect(posted.apt_synset_ids).toEqual([]);
    });

    // -----------------------------------------------------------------------
    // Fix 1 (review): selectedApt must not leak across batches
    // -----------------------------------------------------------------------

    it('selectedApt does not leak: _start() resets it before the next batch renders', async () => {
        // Regression guard: _start() must clear selectedApt alongside pendingVerdict.
        // Without the fix, a stale tick from a previous split survives into the new batch.
        // The leak surface: _post() reads this.selectedApt directly, so any path that
        // calls _post('split') without first calling _onVerdict('split') (which clears it)
        // would carry the stale ids. _start() is one such re-entry point.
        await start();

        // Tap Split and tick one candidate — selectedApt = ['1760'].
        await click('[data-testid="verdict-split"]');
        await click('[data-testid="cand-1760"]');

        // _start() is called (simulates "Label another batch" / "Try again" from done/error).
        // This is the point where the fix must act: selectedApt must be [] after _start().
        getSenseCheckSample.mockResolvedValue({ count: 1, items: [item()] });
        (el as any)._start();
        await el.updateComplete; await tick(); await el.updateComplete;

        // Directly call _post('split') without going through _onVerdict('split')
        // (which would legitimately reset selectedApt). This exposes the stale state.
        (el as any)._post('split', null);
        await el.updateComplete; await tick(); await el.updateComplete;

        // apt_synset_ids must be [] — the stale '1760' from the pre-_start() tick must NOT appear.
        const posted = postSenseLabel.mock.calls[0][0];
        expect(posted.verdict).toBe('split');
        expect(posted.apt_synset_ids).toEqual([]);
    });

    it('context panel shows topic POS when expanded on a chain that has it', async () => {
        getSenseCheckSample.mockResolvedValue({
            count: 1, items: [{
                ...item('drought', 'vehicle'),
                context: { chains: [
                    { topic: 'longing', vehicle: 'drought', chain_signature: 'a',
                      topic_pos: 'n', topic_gloss: 'prolonged unsatisfied desire',
                      chain: [{ phrase: 'longing', head: 'longing', synset_id: '72598' },
                              { phrase: 'drought', head: 'drought', synset_id: '104281' }] },
                ] },
            }],
        });
        await start();
        await click('[data-testid="ctx-toggle"]');
        const ctx = el.shadowRoot!.querySelector('[data-testid="sensecheck-context"]')!.textContent!;
        // Topic POS and gloss should be rendered within the context block.
        expect(ctx).toContain('n');                               // topic_pos
        expect(ctx).toContain('prolonged unsatisfied desire');    // topic_gloss
    });
});
