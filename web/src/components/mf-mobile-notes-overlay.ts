import { LitElement, html, css } from 'lit';
import { customElement, property } from 'lit/decorators.js';
import './mf-design-notes';

/**
 * Bottom-sheet drawer that slides up over the bottom 60% of the viewport.
 * Embeds mf-design-notes and forwards its save-note events upward.
 * Emits a `close` CustomEvent when the close button or backdrop is clicked.
 */
@customElement('mf-mobile-notes-overlay')
export class MfMobileNotesOverlay extends LitElement {
    static styles = css`
        :host { display: contents; }

        .backdrop {
            position: fixed;
            inset: 0;
            background: rgba(0, 0, 0, 0.5);
            z-index: 999;
        }

        .sheet {
            position: fixed;
            left: 0;
            right: 0;
            bottom: 0;
            height: 60vh;
            background: #0f1115;
            border-top: 1px solid #2a3140;
            border-radius: 12px 12px 0 0;
            z-index: 1000;
            display: flex;
            flex-direction: column;
        }

        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.5rem 1rem;
            border-bottom: 1px solid #2a3140;
        }

        header h2 {
            margin: 0;
            font-size: 1rem;
            color: #e6e6e6;
        }

        button.close {
            background: none;
            border: none;
            color: #c8c8c8;
            font-size: 1.2rem;
            cursor: pointer;
            padding: 0.2rem 0.5rem;
            line-height: 1;
        }

        button.close:hover {
            color: #fff;
        }

        mf-design-notes {
            flex: 1;
            overflow-y: auto;
        }
    `;

    /** Whether the overlay is visible. */
    @property({ type: Boolean }) open = false;

    /** History text passed through to mf-design-notes. */
    @property() history = '';

    private close() {
        this.dispatchEvent(new CustomEvent('close', { bubbles: true, composed: true }));
    }

    render() {
        if (!this.open) return html``;
        return html`
            <div data-testid="overlay">
                <div class="backdrop" @click=${this.close}></div>
                <div class="sheet">
                    <header>
                        <h2>Design notes</h2>
                        <button
                            data-testid="close-btn"
                            class="close"
                            aria-label="Close design notes"
                            @click=${this.close}
                        >×</button>
                    </header>
                    <mf-design-notes .history=${this.history}></mf-design-notes>
                </div>
            </div>
        `;
    }
}

declare global {
    interface HTMLElementTagNameMap {
        'mf-mobile-notes-overlay': MfMobileNotesOverlay;
    }
}
