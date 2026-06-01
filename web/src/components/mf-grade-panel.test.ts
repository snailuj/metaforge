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

    const PRIOR = {
        linkage: 'bad' as const, metaphor: 'dead' as const,
        tiers: ['strong', 'surprising'], tags: ['leap', 'bad_head'],
        confidence: 'med' as const, notes: 'cliché', ts: '2026-05-31T14:22:00Z',
    };
    const setPrior = async (over: Record<string, unknown> = {}) => {
        el.priorVerdict = { ...PRIOR, tiers: [...PRIOR.tiers], tags: [...PRIOR.tags], ...over } as any;
        await el.updateComplete;
    };

    it('prefills all editable fields from the prior verdict', async () => {
        await setPrior();
        expect((el.shadowRoot!.querySelector('[data-testid="linkage-toggle"]') as HTMLElement).classList.contains('bad')).toBe(true);
        expect(tierSelected('strong')).toBe(true);
        expect(tierSelected('surprising')).toBe(true);
        expect(tagSelected('leap')).toBe(true);
        expect(tagSelected('bad_head')).toBe(true);
        const medBtn = [...el.shadowRoot!.querySelectorAll('button.conf')].find(b => b.textContent!.includes('Med'))!;
        expect(medBtn.classList.contains('active')).toBe(true);
        expect((el.shadowRoot!.querySelector('textarea') as HTMLTextAreaElement).value).toBe('cliché');
    });

    it('shows a muted last-saved line with summary + timestamp', async () => {
        await setPrior();
        const line = el.shadowRoot!.querySelector('[data-testid="last-saved"]')!.textContent!;
        expect(line).toContain('bad');
        expect(line).toContain('dead');
        expect(line).toContain('strong');
        expect(line).toContain('leap');
        expect(line).toContain('2026-05-31 14:22');
    });

    it('marks the previously-chosen metaphor button as was-prior', async () => {
        await setPrior();
        expect((el.shadowRoot!.querySelector('[data-testid="metaphor-dead"]') as HTMLElement).classList.contains('was-prior')).toBe(true);
        expect((el.shadowRoot!.querySelector('[data-testid="metaphor-live"]') as HTMLElement).classList.contains('was-prior')).toBe(false);
    });

    it('a re-grade submit retains the prefilled tiers/tags/notes/linkage/confidence', async () => {
        let d: any = null;
        el.addEventListener('verdict-submit', (e: any) => d = e.detail);
        await setPrior({ metaphor: 'live', tiers: ['strong'], tags: ['bad_head'] });
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'l' })); await tick();
        expect(d.tiers).toEqual(['strong']);
        expect(d.tags).toEqual(['bad_head']);
        expect(d.notes).toBe('cliché');
        expect(d.linkage).toBe('bad');
        expect(d.confidence).toBe('med');
    });

    it('does not clobber in-progress edits when priorVerdict identity changes but ts is unchanged', async () => {
        await setPrior({ notes: 'original' });
        const ta = el.shadowRoot!.querySelector('textarea') as HTMLTextAreaElement;
        ta.value = 'my edit'; ta.dispatchEvent(new Event('input'));
        await el.updateComplete;
        await setPrior({ notes: 'original' }); // new object, same ts
        expect((el.shadowRoot!.querySelector('textarea') as HTMLTextAreaElement).value).toBe('my edit');
    });

    it('clears the form when switching to an ungraded chain (priorVerdict null)', async () => {
        await setPrior();
        el.priorVerdict = null;
        await el.updateComplete;
        expect(tierSelected('strong')).toBe(false);
        expect(tagSelected('leap')).toBe(false);
        expect((el.shadowRoot!.querySelector('textarea') as HTMLTextAreaElement).value).toBe('');
    });

    const clickTag = async (tag: string) => {
        (el.shadowRoot!.querySelector(`[data-testid="chip-${tag}"]`) as HTMLElement).click();
        await el.updateComplete;
    };
    const tagSelected = (tag: string) =>
        (el.shadowRoot!.querySelector(`[data-testid="chip-${tag}"]`) as HTMLElement)
            .classList.contains('selected');

    it('exposes bad_head as a tag chip', () => {
        expect(el.shadowRoot!.querySelector('[data-testid="chip-bad_head"]')).toBeTruthy();
    });

    it('clicking tag chips multi-selects (toggle on/off)', async () => {
        await clickTag('padding');
        await clickTag('bad_head');
        expect(tagSelected('padding')).toBe(true);
        expect(tagSelected('bad_head')).toBe(true);
        expect(tagSelected('merge')).toBe(false);
        await clickTag('padding'); // toggle off
        expect(tagSelected('padding')).toBe(false);
        expect(tagSelected('bad_head')).toBe(true);
    });

    it('a submit carries the selected tags as an array', async () => {
        let d: any = null;
        el.addEventListener('verdict-submit', (e: any) => d = e.detail);
        await clickTag('leap');
        await clickTag('bad_head');
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'd' })); await tick();
        expect(d.tags).toEqual(['leap', 'bad_head']);
    });

    it('selected tags reset after a submit', async () => {
        const captures: any[] = [];
        el.addEventListener('verdict-submit', (e: any) => captures.push(e.detail));
        await clickTag('merge');
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'l' })); await tick();
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'l' })); await tick();
        expect(captures.map(c => c.tags)).toEqual([['merge'], []]);
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
