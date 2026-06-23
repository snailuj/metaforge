import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import './mf-mobile-notes-overlay';
import { MfMobileNotesOverlay } from './mf-mobile-notes-overlay';

describe('mf-mobile-notes-overlay', () => {
    let el: MfMobileNotesOverlay;

    beforeEach(async () => {
        el = document.createElement('mf-mobile-notes-overlay') as MfMobileNotesOverlay;
        document.body.appendChild(el);
        await el.updateComplete;
    });

    afterEach(() => {
        el.remove();
    });

    it('is defined', () => {
        expect(MfMobileNotesOverlay).toBeDefined();
    });

    it('renders nothing when open is false', async () => {
        el.open = false;
        await el.updateComplete;
        const overlay = el.shadowRoot!.querySelector('[data-testid="overlay"]');
        expect(overlay).toBeNull();
    });

    it('renders overlay when open is true', async () => {
        el.open = true;
        await el.updateComplete;
        const overlay = el.shadowRoot!.querySelector('[data-testid="overlay"]');
        expect(overlay).not.toBeNull();
    });

    it('close button click emits close event', async () => {
        el.open = true;
        await el.updateComplete;

        let closeFired = false;
        el.addEventListener('close', () => { closeFired = true; });

        const btn = el.shadowRoot!.querySelector('[data-testid="close-btn"]') as HTMLButtonElement;
        expect(btn).not.toBeNull();
        btn.click();

        expect(closeFired).toBe(true);
    });

    it('forwards save-note from inner mf-design-notes', async () => {
        el.open = true;
        await el.updateComplete;

        let capturedDetail: any = null;
        el.addEventListener('save-note', (e: Event) => {
            capturedDetail = (e as CustomEvent).detail;
        });

        const designNotes = el.shadowRoot!.querySelector('mf-design-notes');
        expect(designNotes).not.toBeNull();

        // mf-design-notes dispatches save-note with bubbles:true, composed:true
        // so it will bubble up through the shadow root to the overlay element
        designNotes!.dispatchEvent(new CustomEvent('save-note', {
            detail: { content: 'forwarded note' },
            bubbles: true,
            composed: true,
        }));

        expect(capturedDetail).not.toBeNull();
        expect(capturedDetail.content).toBe('forwarded note');
    });
});
