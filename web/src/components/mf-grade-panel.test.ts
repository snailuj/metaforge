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

    it('renders chain steps with arrows', async () => {
        const text = el.shadowRoot!.textContent || '';
        expect(text).toContain('anger');
        expect(text).toContain('hostility');
        expect(text).toContain('venom');
        expect(text).toContain('→');
    });

    it('shows the snapped head primary, with the prose phrase only when it differs (bad_head judging)', async () => {
        el.chain = {
            ...CHAIN,
            chain: [
                { phrase: 'anchor', head: 'anchor', synset_id: '1' },
                { phrase: 'resists change', head: 'resistance', synset_id: '2' },
                { phrase: 'habit', head: 'habit', synset_id: '3' },
            ],
        };
        await el.updateComplete;
        const text = el.shadowRoot!.textContent || '';
        expect(text).toContain('resistance');     // snapped head — primary
        expect(text).toContain('resists change');  // original phrase shown because head differs
        // Only the differing step carries a phrase sub-label; equal steps don't duplicate.
        const subs = el.shadowRoot!.querySelectorAll('.phrase-sub');
        expect(subs.length).toBe(1);
        expect(subs[0].textContent).toContain('resists change');
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

    it('clears uncommitted edits when switching between two different UNGRADED chains', async () => {
        // chain A (CHAIN) is set by beforeEach; both chains are ungraded (priorVerdict null).
        // Operator makes uncommitted edits on A:
        (el.shadowRoot!.querySelector('[data-testid="linkage-toggle"]') as HTMLElement).click(); // -> bad
        await clickTag('bad_head');
        const ta = el.shadowRoot!.querySelector('textarea') as HTMLTextAreaElement;
        ta.value = 'draft'; ta.dispatchEvent(new Event('input'));
        await el.updateComplete;
        // Switch to a DIFFERENT ungraded chain B (same panel instance; priorVerdict stays null).
        el.chain = { ...CHAIN, chain_signature: 'b'.repeat(64) };
        await el.updateComplete;
        expect((el.shadowRoot!.querySelector('[data-testid="linkage-toggle"]') as HTMLElement).classList.contains('bad')).toBe(false);
        expect(tagSelected('bad_head')).toBe(false);
        expect((el.shadowRoot!.querySelector('textarea') as HTMLTextAreaElement).value).toBe('');
    });

    const clickTag = async (tag: string) => {
        (el.shadowRoot!.querySelector(`[data-testid="chip-${tag}"]`) as HTMLElement).click();
        await el.updateComplete;
    };
    const tagSelected = (tag: string) =>
        (el.shadowRoot!.querySelector(`[data-testid="chip-${tag}"]`) as HTMLElement)
            .classList.contains('selected');
    const linkageBad = () =>
        (el.shadowRoot!.querySelector('[data-testid="linkage-toggle"]') as HTMLElement)
            .classList.contains('bad');

    it('exposes bad_head as a tag chip', () => {
        expect(el.shadowRoot!.querySelector('[data-testid="chip-bad_head"]')).toBeTruthy();
    });

    it('exposes bad_sense as a tag chip', () => {
        expect(el.shadowRoot!.querySelector('[data-testid="chip-bad_sense"]')).toBeTruthy();
    });

    it('selecting bad_sense does NOT force linkage bad (grader reads the intended sense)', async () => {
        await clickTag('bad_sense');
        expect(tagSelected('bad_sense')).toBe(true);
        expect(linkageBad()).toBe(false);
    });

    it('bad_sense scaffolds a space-normalised "bad sense: " prefix', async () => {
        await clickTag('bad_sense');
        expect(notesValue()).toBe('bad sense: ');
    });

    it('a submit carries the bad_sense tag', async () => {
        let d: any = null;
        el.addEventListener('verdict-submit', (e: any) => d = e.detail);
        await clickTag('bad_sense');
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'l' })); await tick();
        expect(d.tags).toEqual(['bad_sense']);
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

    const notesValue = () => (el.shadowRoot!.querySelector('textarea') as HTMLTextAreaElement).value;

    it('tapping a tag scaffolds the notes with its label prefix and still selects it', async () => {
        await clickTag('leap');
        expect(notesValue()).toBe('leap: ');
        expect(tagSelected('leap')).toBe(true);
    });

    it('bad_head scaffolds a space-normalised "bad head: " prefix', async () => {
        await clickTag('bad_head');
        expect(notesValue()).toBe('bad head: ');
    });

    it('a second tag appends its prefix on a new line', async () => {
        await clickTag('leap');
        await clickTag('padding');
        expect(notesValue()).toBe('leap: \npadding: ');
    });

    it('tapping a tag focuses the textarea with the cursor at the end', async () => {
        await clickTag('merge');
        await tick();
        const ta = el.shadowRoot!.querySelector('textarea') as HTMLTextAreaElement;
        expect(el.shadowRoot!.activeElement).toBe(ta);
        expect(ta.selectionStart).toBe(ta.value.length);
        expect(ta.selectionEnd).toBe(ta.value.length);
    });

    it('deselecting a tag leaves already-typed notes untouched', async () => {
        await clickTag('leap');                 // notes -> 'leap: '
        const ta = el.shadowRoot!.querySelector('textarea') as HTMLTextAreaElement;
        ta.value = 'leap: too abrupt'; ta.dispatchEvent(new Event('input'));
        await el.updateComplete;
        await clickTag('leap');                 // toggle OFF — must not edit notes
        expect(notesValue()).toBe('leap: too abrupt');
        expect(tagSelected('leap')).toBe(false);
    });

    it('scaffolds onto an existing typed note on a fresh line', async () => {
        const ta = el.shadowRoot!.querySelector('textarea') as HTMLTextAreaElement;
        ta.value = 'general thought'; ta.dispatchEvent(new Event('input'));
        await el.updateComplete;
        await clickTag('bad_head');
        expect(notesValue()).toBe('general thought\nbad head: ');
    });

    // A structural tag implies a broken bridge → linkage:bad is set at source, so
    // the grader needn't also tap the linkage button. bad_head/leap/merge force it;
    // padding (bloated-but-valid path) and 'other' do not. Set-only: deselecting a
    // forcing tag never reverts linkage (an explicit bad may stand for other reasons).
    it('selecting bad_head auto-sets linkage to bad', async () => {
        await clickTag('bad_head');
        expect(linkageBad()).toBe(true);
    });

    it('selecting leap auto-sets linkage to bad', async () => {
        await clickTag('leap');
        expect(linkageBad()).toBe(true);
    });

    it('selecting merge auto-sets linkage to bad', async () => {
        await clickTag('merge');
        expect(linkageBad()).toBe(true);
    });

    it('selecting padding alone leaves linkage at the default good', async () => {
        await clickTag('padding');
        expect(linkageBad()).toBe(false);
    });

    it('selecting other does not force linkage bad', async () => {
        await clickTag('other');
        expect(linkageBad()).toBe(false);
    });

    it('deselecting a forcing tag does not revert linkage to good', async () => {
        await clickTag('bad_head');   // -> bad
        await clickTag('bad_head');   // toggle off — must NOT revert
        expect(linkageBad()).toBe(true);
    });

    it('a forcing tag carries linkage:bad into the submit', async () => {
        let d: any = null;
        el.addEventListener('verdict-submit', (e: any) => d = e.detail);
        await clickTag('bad_head');
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'l' })); await tick();
        expect(d.linkage).toBe('bad');
    });

    it('shows topic + vehicle POS and gloss when glosses are provided', async () => {
        el.glosses = {
            '1': { pos: 's', definition: 'belonging to or lasting from times long ago' },  // adjective
            '3': { pos: 'n', definition: 'a poison secreted by some animals' },
        };
        await el.updateComplete;
        const senses = el.shadowRoot!.querySelector('[data-testid="senses"]')!;
        const text = senses.textContent || '';
        expect(text).toContain('anger');        // topic lemma
        expect(text).toContain('venom');         // vehicle lemma
        expect(text).toContain('belonging to'); // topic gloss
        // POS normalised to a readable label (s -> adj)
        expect((el.shadowRoot!.querySelector('[data-testid="pos-topic"]') as HTMLElement).textContent).toContain('adj');
        expect((el.shadowRoot!.querySelector('[data-testid="pos-vehicle"]') as HTMLElement).textContent).toContain('noun');
    });

    it('renders no senses block when no glosses are available', async () => {
        // default: el.glosses is {} (beforeEach sets no glosses)
        expect(el.shadowRoot!.querySelector('[data-testid="senses"]')).toBeNull();
    });

    // --- Per-link glosses: hover or tap any chain node to read its snapped-synset
    // gloss. Lets the grader spot a wrong-sense snap (e.g. livery) at any hop, not
    // just the topic/vehicle endpoints. Reuses the glosses map keyed by synset_id. ---
    const node = (i: number) =>
        el.shadowRoot!.querySelector(`[data-testid="step-node-${i}"]`) as HTMLElement | null;
    const linkGloss = () =>
        el.shadowRoot!.querySelector('[data-testid="link-gloss"]');
    const CHAIN_GLOSSES = {
        '1': { pos: 'n', definition: 'a strong feeling of displeasure' },
        '2': { pos: 'n', definition: 'violent unfriendly feelings' },
        '3': { pos: 'n', definition: 'a poison secreted by some animals' },
    };

    it('renders each chain step as an interactive node', () => {
        expect(node(0)).toBeTruthy();
        expect(node(1)).toBeTruthy();
        expect(node(2)).toBeTruthy();
        expect(node(3)).toBeNull(); // only 3 steps
    });

    it('no link gloss is shown until a node is hovered or tapped', () => {
        el.glosses = CHAIN_GLOSSES;
        expect(linkGloss()).toBeNull();
    });

    it('tapping a chain node reveals its snapped-synset gloss below the chain', async () => {
        el.glosses = CHAIN_GLOSSES;
        await el.updateComplete;
        node(1)!.click();               // hostility, synset '2'
        await el.updateComplete;
        const text = linkGloss()!.textContent || '';
        expect(text).toContain('hostility');                 // node head
        expect(text).toContain('violent unfriendly feelings'); // its gloss
        expect(text).toContain('noun');                       // POS label
    });

    it('tapping the active node again hides its gloss (toggle)', async () => {
        el.glosses = CHAIN_GLOSSES;
        await el.updateComplete;
        node(1)!.click(); await el.updateComplete;
        expect(linkGloss()).toBeTruthy();
        node(1)!.click(); await el.updateComplete;
        expect(linkGloss()).toBeNull();
    });

    it('hovering a chain node reveals its gloss; leaving reverts', async () => {
        el.glosses = CHAIN_GLOSSES;
        await el.updateComplete;
        node(2)!.dispatchEvent(new MouseEvent('mouseenter'));
        await el.updateComplete;
        expect(linkGloss()!.textContent).toContain('a poison secreted');
        node(2)!.dispatchEvent(new MouseEvent('mouseleave'));
        await el.updateComplete;
        expect(linkGloss()).toBeNull();
    });

    it('hover transiently overrides a pinned node, then reverts to the pin on leave', async () => {
        el.glosses = CHAIN_GLOSSES;
        await el.updateComplete;
        node(0)!.click();               // pin step 0 (index 0 — must survive ?? )
        await el.updateComplete;
        node(2)!.dispatchEvent(new MouseEvent('mouseenter'));
        await el.updateComplete;
        expect(linkGloss()!.textContent).toContain('a poison secreted'); // hovered step 2
        node(2)!.dispatchEvent(new MouseEvent('mouseleave'));
        await el.updateComplete;
        expect(linkGloss()!.textContent).toContain('a strong feeling'); // reverts to pinned step 0
    });

    it('degrades gracefully when the node has no gloss (still shows the head)', async () => {
        // default glosses {} — no synset resolves
        node(1)!.click();
        await el.updateComplete;
        const g = linkGloss();
        expect(g).toBeTruthy();
        expect(g!.textContent).toContain('hostility');   // head still shown
        expect(g!.textContent!.toLowerCase()).toContain('no gloss');
    });

    it('switching to a different chain clears the pinned gloss', async () => {
        el.glosses = CHAIN_GLOSSES;
        await el.updateComplete;
        node(1)!.click();
        await el.updateComplete;
        expect(linkGloss()).toBeTruthy();
        el.chain = { ...CHAIN, chain_signature: 'f'.repeat(64) };
        await el.updateComplete;
        expect(linkGloss()).toBeNull();
    });
});
