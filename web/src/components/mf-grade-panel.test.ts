import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import './mf-grade-panel';
import { MfGradePanel } from './mf-grade-panel';

const tick = () => new Promise(r => setTimeout(r, 0));

const CHAIN = {
    schema_version: 'chain.v1' as const,
    topic: 'anger', vehicle: 'venom',
    topic_synset_id: '1', vehicle_synset_id: '3',
    chain_signature: 'a'.repeat(64),
    chain: [
        { phrase: 'anger', head: 'anger', synset_id: '1' },
        { phrase: 'hostility', head: 'hostility', synset_id: '2' },
        { phrase: 'venom', head: 'venom', synset_id: '3' },
    ],
    proposer: 'sonnet_v1', round: 1, generated_at: 'x',
};

describe('mf-grade-panel', () => {
    let el: MfGradePanel;

    beforeEach(async () => {
        el = document.createElement('mf-grade-panel') as MfGradePanel;
        el.chain = CHAIN;
        document.body.appendChild(el);
        await el.updateComplete;
    });

    afterEach(() => {
        el.remove();
    });

    it('is defined', () => {
        expect(MfGradePanel).toBeDefined();
    });

    it('renders chain phrases with arrows', async () => {
        const text = el.shadowRoot!.textContent || '';
        expect(text).toContain('anger');
        expect(text).toContain('hostility');
        expect(text).toContain('venom');
        expect(text).toContain('→');
    });

    it('L submits linkage:good + metaphor:live by default', async () => {
        let d: any = null;
        el.addEventListener('verdict-submit', (e: any) => d = e.detail);
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'l' }));
        await tick();
        expect(d).toMatchObject({ linkage: 'good', metaphor: 'live' });
    });

    it('B then D submits linkage:bad + metaphor:dead', async () => {
        let d: any = null;
        el.addEventListener('verdict-submit', (e: any) => d = e.detail);
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'b' })); await tick();
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'd' })); await tick();
        expect(d).toMatchObject({ linkage: 'bad', metaphor: 'dead' });
    });

    it('I submits metaphor:irrelevant', async () => {
        let d: any = null;
        el.addEventListener('verdict-submit', (e: any) => d = e.detail);
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'i' }));
        await tick();
        expect(d).toMatchObject({ linkage: 'good', metaphor: 'irrelevant' });
    });

    const clickTier = async (tier: string) => {
        (el.shadowRoot!.querySelector(`[data-testid="tier-${tier}"]`) as HTMLElement).click();
        await el.updateComplete;
    };
    const tierSelected = (tier: string) =>
        (el.shadowRoot!.querySelector(`[data-testid="tier-${tier}"]`) as HTMLElement)
            .classList.contains('selected');

    it('clicking two tier chips selects both', async () => {
        await clickTier('strong');
        await clickTier('surprising');
        expect(tierSelected('strong')).toBe(true);
        expect(tierSelected('surprising')).toBe(true);
        expect(tierSelected('ironic')).toBe(false);
    });

    it('clicking a selected chip deselects only it', async () => {
        await clickTier('strong');
        await clickTier('surprising');
        await clickTier('strong'); // toggle off
        expect(tierSelected('strong')).toBe(false);
        expect(tierSelected('surprising')).toBe(true);
    });

    it('a live submit carries the selected tiers as an array', async () => {
        let d: any = null;
        el.addEventListener('verdict-submit', (e: any) => d = e.detail);
        await clickTier('strong');
        await clickTier('surprising');
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'l' })); await tick();
        expect(d).toMatchObject({ metaphor: 'live' });
        expect(d.tiers).toEqual(['strong', 'surprising']);
    });

    it('tiers are gated to live — a dead submit emits empty tiers', async () => {
        let d: any = null;
        el.addEventListener('verdict-submit', (e: any) => d = e.detail);
        await clickTier('strong');
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'd' })); await tick();
        expect(d.metaphor).toBe('dead');
        expect(d.tiers).toEqual([]);
    });

    it('selected tiers reset after a submit', async () => {
        const captures: any[] = [];
        el.addEventListener('verdict-submit', (e: any) => captures.push(e.detail));
        await clickTier('strong');
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'l' })); await tick();
        // Next submit (no chip) carries no tiers.
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'l' })); await tick();
        expect(captures.map(c => c.tiers)).toEqual([['strong'], []]);
    });

    it('pending linkage:bad resets after a submit', async () => {
        const captures: any[] = [];
        el.addEventListener('verdict-submit', (e: any) => captures.push(e.detail));
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'b' })); await tick();
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'd' })); await tick();
        // Next submit (no B) reverts to the default good linkage.
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'l' })); await tick();
        expect(captures.map(c => c.linkage)).toEqual(['bad', 'good']);
    });

    it('confidence defaults to high; 2 sets med', async () => {
        let d: any = null;
        el.addEventListener('verdict-submit', (e: any) => d = e.detail);
        document.dispatchEvent(new KeyboardEvent('keydown', { key: '2' })); await tick();
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'l' })); await tick();
        expect(d?.confidence).toBe('med');
    });

    it('re-grade banner shows prior linkage, metaphor, multiple tiers and notes', async () => {
        el.priorVerdict = { linkage: 'good', metaphor: 'live', tiers: ['strong', 'surprising'], notes: 'cliché', ts: '2026-05-31T00:00:00Z' };
        await el.updateComplete;
        const b = el.shadowRoot!.querySelector('[data-testid="re-grade-banner"]')!.textContent!;
        expect(b).toContain('live');
        expect(b).toContain('strong');
        expect(b).toContain('surprising');
        expect(b).toContain('cliché');
    });

    it('renders no prior-notes line when priorVerdict has empty notes', async () => {
        el.priorVerdict = { linkage: 'good', metaphor: 'live', tiers: [], notes: '', ts: '2026-05-31T00:00:00Z' };
        await el.updateComplete;
        const banner = el.shadowRoot!.querySelector('[data-testid="re-grade-banner"]');
        expect(banner).toBeTruthy();
        expect(el.shadowRoot!.querySelector('[data-testid="prior-notes"]')).toBeNull();
    });

    it('tag chip prepends tag prefix to notes', async () => {
        const chip = el.shadowRoot!.querySelector('[data-testid="chip-merge"]') as HTMLElement;
        chip.click();
        await el.updateComplete;
        const textarea = el.shadowRoot!.querySelector('textarea') as HTMLTextAreaElement;
        expect(textarea.value.startsWith('merge:')).toBe(true);
    });

    it('verdict event payload includes confidence and notes', async () => {
        let d: any = null;
        el.addEventListener('verdict-submit', (e: any) => d = e.detail);
        const textarea = el.shadowRoot!.querySelector('textarea') as HTMLTextAreaElement;
        textarea.value = 'test note';
        textarea.dispatchEvent(new Event('input'));
        await el.updateComplete;
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'l' }));
        await tick();
        expect(d?.notes).toBe('test note');
        expect(d?.confidence).toBe('high');
        expect(d?.metaphor).toBe('live');
    });

    it('does not fire while typing in an editable field (composedPath trap retained)', async () => {
        let d: any = null;
        el.addEventListener('verdict-submit', (e: any) => d = e.detail);
        const ta = document.createElement('textarea');
        document.body.appendChild(ta);
        ta.dispatchEvent(new KeyboardEvent('keydown', { key: 'l', bubbles: true, composed: true }));
        await tick();
        expect(d).toBeNull();
        ta.remove();
    });

    it('a submit carries a tags array (empty by default)', async () => {
        let d: any = null;
        el.addEventListener('verdict-submit', (e: any) => d = e.detail);
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'l' })); await tick();
        expect(d.tags).toEqual([]);
    });
});
