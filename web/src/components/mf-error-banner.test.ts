import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { MfErrorBanner } from './mf-error-banner';

describe('mf-error-banner', () => {
    let el: MfErrorBanner;

    beforeEach(async () => {
        el = new MfErrorBanner();
        document.body.appendChild(el);
        await el.updateComplete;
    });

    afterEach(() => {
        document.body.removeChild(el);
    });

    it('renders nothing when message empty', async () => {
        expect(el.shadowRoot!.querySelector('.banner')).toBeNull();
    });

    it('renders message when set', async () => {
        el.message = 'oh no';
        await el.updateComplete;
        const banner = el.shadowRoot!.querySelector('.banner');
        expect(banner?.textContent).toContain('oh no');
    });

    it('applies warn class when level=warn', async () => {
        el.message = 'careful';
        el.level = 'warn';
        await el.updateComplete;
        expect(el.shadowRoot!.querySelector('.banner.warn')).toBeTruthy();
    });
});
