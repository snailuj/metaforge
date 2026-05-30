import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import './mf-grade-panel';
import { MfGradePanel } from './mf-grade-panel';

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

    it('emits verdict-submit on L keydown (live)', async () => {
        let captured: any = null;
        el.addEventListener('verdict-submit', (e: any) => { captured = e.detail; });
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'l' }));
        await new Promise(r => setTimeout(r, 0));
        expect(captured?.label).toBe('live');
    });

    it('emits verdict-submit on D (dead), B (bad_path), I (irrelevant)', async () => {
        const captures: any[] = [];
        el.addEventListener('verdict-submit', (e: any) => captures.push(e.detail));
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'd' })); await new Promise(r => setTimeout(r, 0));
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'b' })); await new Promise(r => setTimeout(r, 0));
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'i' })); await new Promise(r => setTimeout(r, 0));
        expect(captures.map((c: any) => c.label)).toEqual(['dead', 'bad_path', 'irrelevant']);
    });

    it('confidence defaults to high; 2 sets med', async () => {
        let captured: any = null;
        el.addEventListener('verdict-submit', (e: any) => { captured = e.detail; });
        document.dispatchEvent(new KeyboardEvent('keydown', { key: '2' }));
        await new Promise(r => setTimeout(r, 0));
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'l' }));
        await new Promise(r => setTimeout(r, 0));
        expect(captured?.confidence).toBe('med');
    });

    it('shows re-grade banner when priorVerdict prop is set', async () => {
        el.priorVerdict = { label: 'bad_path', ts: '2026-05-30T00:00:00Z' };
        await el.updateComplete;
        const banner = el.shadowRoot!.querySelector('[data-testid="re-grade-banner"]');
        expect(banner).toBeTruthy();
        expect(banner!.textContent).toContain('bad_path');
    });

    it('tag chip prepends tag prefix to notes', async () => {
        const chip = el.shadowRoot!.querySelector('[data-testid="chip-merge"]') as HTMLElement;
        chip.click();
        await el.updateComplete;
        const textarea = el.shadowRoot!.querySelector('textarea') as HTMLTextAreaElement;
        expect(textarea.value.startsWith('merge:')).toBe(true);
    });

    it('verdict event payload includes confidence and notes', async () => {
        let captured: any = null;
        el.addEventListener('verdict-submit', (e: any) => { captured = e.detail; });
        const textarea = el.shadowRoot!.querySelector('textarea') as HTMLTextAreaElement;
        textarea.value = 'test note';
        textarea.dispatchEvent(new Event('input'));
        await el.updateComplete;
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'l' }));
        await new Promise(r => setTimeout(r, 0));
        expect(captured?.notes).toBe('test note');
        expect(captured?.confidence).toBe('high');
        expect(captured?.label).toBe('live');
    });

    it('does NOT fire a verdict when a grading key is pressed inside an editable field', async () => {
        let captured: any = null;
        el.addEventListener('verdict-submit', (e: any) => { captured = e.detail; });
        // A keydown whose composed path includes a TEXTAREA (e.g. the design-notes
        // textarea in another shadow root) must not trigger grading.
        const ta = document.createElement('textarea');
        document.body.appendChild(ta);
        ta.dispatchEvent(new KeyboardEvent('keydown', { key: 'l', bubbles: true, composed: true }));
        await new Promise(r => setTimeout(r, 0));
        expect(captured).toBeNull();
        document.body.removeChild(ta);
    });
});
