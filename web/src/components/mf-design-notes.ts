import { LitElement, html, css } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';

// Time of inactivity in ms before an auto-save fires
const IDLE_MS = 30_000;

@customElement('mf-design-notes')
export class MfDesignNotes extends LitElement {
    static styles = css`
        :host { display: block; padding: 0.5rem; }
        .history {
            background: #181b22; color: #c8c8c8; padding: 0.6rem;
            border: 1px solid #2a3140; border-radius: 4px;
            max-height: 30vh; overflow-y: auto; font-family: ui-monospace, monospace;
            font-size: 0.85rem; white-space: pre-wrap; margin-bottom: 0.5rem;
            min-height: 1.4rem;
        }
        .history:empty::before {
            content: '(no notes yet)'; color: #6a6f7a; font-style: italic;
        }
        textarea {
            width: 100%; min-height: 8rem; box-sizing: border-box; padding: 0.5rem;
            background: #181b22; color: #e6e6e6; border: 1px solid #2a3140; border-radius: 3px;
            font-family: inherit; font-size: 0.9rem;
            resize: vertical;
        }
        .row { display: flex; justify-content: flex-end; margin-top: 0.4rem; }
        button {
            padding: 0.4rem 0.9rem; cursor: pointer;
            background: #181b22; color: #e6e6e6; border: 1px solid #2a3140; border-radius: 3px;
        }
        kbd {
            background: #2a3140; padding: 0.05rem 0.3rem; border-radius: 3px;
            font-size: 0.75rem; margin-left: 0.3rem;
        }
    `;

    /** Accumulated history shown read-only above the live textarea. */
    @property() history = '';

    /** Live textarea content. */
    @state() private content = '';

    private idleTimer: ReturnType<typeof setTimeout> | null = null;

    // Arrow function so we can pass the same reference to add/remove listener
    private onKeydown = (e: KeyboardEvent) => {
        if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 's') {
            e.preventDefault();
            this.save();
        }
    };

    connectedCallback() {
        super.connectedCallback();
        document.addEventListener('keydown', this.onKeydown);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        document.removeEventListener('keydown', this.onKeydown);
        if (this.idleTimer) {
            clearTimeout(this.idleTimer);
            this.idleTimer = null;
        }
    }

    private onInput(e: Event) {
        this.content = (e.target as HTMLTextAreaElement).value;
        this.resetIdle();
    }

    private resetIdle() {
        if (this.idleTimer) clearTimeout(this.idleTimer);
        this.idleTimer = null;

        // Only arm the idle timer when there is something to save
        if (this.content.trim()) {
            this.idleTimer = setTimeout(() => this.save(), IDLE_MS);
        }
    }

    private save() {
        if (!this.content.trim()) return;

        this.dispatchEvent(new CustomEvent('save-note', {
            detail: { content: this.content },
            bubbles: true,
            composed: true,
        }));

        this.content = '';

        // Keep the textarea DOM node in sync immediately — Lit's .value binding
        // updates on the next render cycle, but we also zero the raw DOM value so
        // it reads '' synchronously (important for tests that read ta.value right
        // after save without waiting for updateComplete).
        const ta = this.shadowRoot?.querySelector('textarea') as HTMLTextAreaElement | null;
        if (ta) ta.value = '';

        if (this.idleTimer) {
            clearTimeout(this.idleTimer);
            this.idleTimer = null;
        }
    }

    render() {
        return html`
            <div class="history">${this.history}</div>
            <textarea
                placeholder="public repo — no secrets, names, or personal context"
                .value=${this.content}
                @input=${this.onInput}
                rows="8"></textarea>
            <div class="row">
                <button @click=${this.save}>Save<kbd>⌘S</kbd></button>
            </div>
        `;
    }
}
