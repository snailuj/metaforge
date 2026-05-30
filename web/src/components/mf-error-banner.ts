import { LitElement, html, css } from 'lit';
import { customElement, property } from 'lit/decorators.js';

@customElement('mf-error-banner')
export class MfErrorBanner extends LitElement {
    static styles = css`
        :host { display: block; }
        .banner {
            background: #c47a7a;
            color: white;
            padding: 0.5rem 1rem;
            font-size: 0.9rem;
        }
        .banner.warn { background: #d6a560; }
    `;

    @property() message = '';
    @property() level: 'error' | 'warn' = 'error';

    render() {
        if (!this.message) return html``;
        return html`<div class="banner ${this.level}">${this.message}</div>`;
    }
}

declare global {
    interface HTMLElementTagNameMap {
        'mf-error-banner': MfErrorBanner;
    }
}
