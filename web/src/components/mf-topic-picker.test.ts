import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { MfTopicPicker } from './mf-topic-picker';

describe('mf-topic-picker', () => {
    const topics = [
        { topic: 'anger', topic_synset_id: '1' },
        { topic: 'joy', topic_synset_id: '2' },
        { topic: 'time', topic_synset_id: '3' },
    ];

    let el: MfTopicPicker;

    beforeEach(async () => {
        el = document.createElement('mf-topic-picker') as MfTopicPicker;
        el.topics = topics;
        document.body.appendChild(el);
        await el.updateComplete;
    });

    afterEach(() => {
        document.body.removeChild(el);
    });

    it('is defined as a custom element', () => {
        expect(MfTopicPicker).toBeDefined();
        expect(customElements.get('mf-topic-picker')).toBeDefined();
    });

    it('renders all topics', async () => {
        const options = el.shadowRoot!.querySelectorAll('[data-testid="option"]');
        expect(options.length).toBe(3);
    });

    it('filters topics by typed prefix', async () => {
        const input = el.shadowRoot!.querySelector('input')!;
        input.value = 'an';
        input.dispatchEvent(new Event('input'));
        await el.updateComplete;
        const visible = el.shadowRoot!.querySelectorAll('[data-testid="option"]:not([hidden])');
        expect(visible.length).toBe(1);
        expect(visible[0].textContent).toContain('anger');
    });

    it('filter is case-insensitive', async () => {
        const input = el.shadowRoot!.querySelector('input')!;
        input.value = 'JOY';
        input.dispatchEvent(new Event('input'));
        await el.updateComplete;
        const visible = el.shadowRoot!.querySelectorAll('[data-testid="option"]:not([hidden])');
        expect(visible.length).toBe(1);
    });

    it('emits topic-selected on click', async () => {
        let captured: any = null;
        el.addEventListener('topic-selected', (e: any) => { captured = e.detail; });
        const first = el.shadowRoot!.querySelector('[data-testid="option"]') as HTMLElement;
        first.click();
        expect(captured).toEqual({ topic: 'anger', topic_synset_id: '1' });
    });

    it('emits topic-selected on Enter keydown on focused option', async () => {
        let captured: any = null;
        el.addEventListener('topic-selected', (e: any) => { captured = e.detail; });
        const second = el.shadowRoot!.querySelectorAll('[data-testid="option"]')[1] as HTMLElement;
        second.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }));
        expect(captured?.topic).toBe('joy');
    });
});
