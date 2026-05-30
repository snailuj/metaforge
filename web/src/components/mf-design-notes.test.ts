import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import './mf-design-notes';
import { MfDesignNotes } from './mf-design-notes';

describe('mf-design-notes', () => {
    let el: MfDesignNotes;

    beforeEach(async () => {
        el = document.createElement('mf-design-notes') as MfDesignNotes;
        document.body.appendChild(el);
        await el.updateComplete;
    });

    afterEach(() => {
        el.remove();
        vi.restoreAllMocks();
    });

    it('is defined', () => {
        expect(MfDesignNotes).toBeDefined();
    });

    it('renders history content in the history panel when history prop is set', async () => {
        el.history = 'prior note line one\nprior note line two';
        await el.updateComplete;
        const historyEl = el.shadowRoot!.querySelector('.history');
        expect(historyEl).toBeTruthy();
        expect(historyEl!.textContent).toContain('prior note line one');
        expect(historyEl!.textContent).toContain('prior note line two');
    });

    it('save button click emits save-note event with content', async () => {
        let captured: any = null;
        el.addEventListener('save-note', (e: any) => { captured = e.detail; });

        const textarea = el.shadowRoot!.querySelector('textarea') as HTMLTextAreaElement;
        textarea.value = 'a great design note';
        textarea.dispatchEvent(new Event('input'));
        await el.updateComplete;

        const btn = el.shadowRoot!.querySelector('button') as HTMLButtonElement;
        btn.click();

        expect(captured).not.toBeNull();
        expect(captured.content).toBe('a great design note');
    });

    it('textarea clears after save', async () => {
        const textarea = el.shadowRoot!.querySelector('textarea') as HTMLTextAreaElement;
        textarea.value = 'some content to clear';
        textarea.dispatchEvent(new Event('input'));
        await el.updateComplete;

        const btn = el.shadowRoot!.querySelector('button') as HTMLButtonElement;
        btn.click();
        await el.updateComplete;

        const ta2 = el.shadowRoot!.querySelector('textarea') as HTMLTextAreaElement;
        expect(ta2.value).toBe('');
    });

    it('Cmd+S (metaKey) triggers save with content', async () => {
        let captured: any = null;
        el.addEventListener('save-note', (e: any) => { captured = e.detail; });

        const textarea = el.shadowRoot!.querySelector('textarea') as HTMLTextAreaElement;
        textarea.value = 'cmd-s note';
        textarea.dispatchEvent(new Event('input'));
        await el.updateComplete;

        document.dispatchEvent(new KeyboardEvent('keydown', { key: 's', metaKey: true }));
        await new Promise(r => setTimeout(r, 0));

        expect(captured).not.toBeNull();
        expect(captured.content).toBe('cmd-s note');
    });

    it('Ctrl+S (ctrlKey) triggers save with content', async () => {
        let captured: any = null;
        el.addEventListener('save-note', (e: any) => { captured = e.detail; });

        const textarea = el.shadowRoot!.querySelector('textarea') as HTMLTextAreaElement;
        textarea.value = 'ctrl-s note';
        textarea.dispatchEvent(new Event('input'));
        await el.updateComplete;

        document.dispatchEvent(new KeyboardEvent('keydown', { key: 's', ctrlKey: true }));
        await new Promise(r => setTimeout(r, 0));

        expect(captured).not.toBeNull();
        expect(captured.content).toBe('ctrl-s note');
    });

    it('30s idle with non-empty content auto-fires save', async () => {
        vi.useFakeTimers();
        let captured: any = null;
        el.addEventListener('save-note', (e: any) => { captured = e.detail; });

        const textarea = el.shadowRoot!.querySelector('textarea') as HTMLTextAreaElement;
        textarea.value = 'idle auto-save content';
        textarea.dispatchEvent(new Event('input'));
        await el.updateComplete;

        await vi.advanceTimersByTimeAsync(30_000);

        expect(captured).not.toBeNull();
        expect(captured.content).toBe('idle auto-save content');

        vi.useRealTimers();
    });

    it('save is NOT fired when textarea is empty', async () => {
        let saveCount = 0;
        el.addEventListener('save-note', () => { saveCount++; });

        const btn = el.shadowRoot!.querySelector('button') as HTMLButtonElement;
        btn.click();

        document.dispatchEvent(new KeyboardEvent('keydown', { key: 's', metaKey: true }));
        await new Promise(r => setTimeout(r, 0));

        expect(saveCount).toBe(0);
    });

    it('save is NOT fired on idle when textarea is empty', async () => {
        vi.useFakeTimers();
        let saveCount = 0;
        el.addEventListener('save-note', () => { saveCount++; });

        // No input — textarea is empty
        await vi.advanceTimersByTimeAsync(30_000);

        expect(saveCount).toBe(0);

        vi.useRealTimers();
    });
});
