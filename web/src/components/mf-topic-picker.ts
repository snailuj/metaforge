import { LitElement, html, css } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import type { TopicSummary } from '../types/grading';

@customElement('mf-topic-picker')
export class MfTopicPicker extends LitElement {
    static styles = css`
        :host { display: block; position: relative; }
        input { width: 100%; padding: 0.4rem; font-size: 1rem; box-sizing: border-box; }
        /* The option list OVERLAYS (position:absolute) rather than participating
           in flow — otherwise a 20-item list pushes the layout and squeezes the
           graph pane to nothing. Shown only while open (focused/typing). */
        ul {
            list-style: none;
            margin: 0;
            padding: 0;
            position: absolute;
            top: 100%;
            left: 0;
            right: 0;
            z-index: 60;
            max-height: 50vh;
            overflow-y: auto;
            background: var(--colour-bg-elevated, #181b22);
            border: 1px solid #2a3140;
            border-top: none;
            display: none;
        }
        ul.open { display: block; }
        li { padding: 0.5rem; cursor: pointer; }
        li:hover, li:focus { background: var(--mf-bg-hover, #2a3140); outline: none; }
        li[hidden] { display: none; }
    `;

    @property({ type: Array }) topics: TopicSummary[] = [];
    @state() private filter = '';
    @state() private open = false;
    @state() private value = '';
    private blurTimer: ReturnType<typeof setTimeout> | null = null;

    private onInput(e: Event) {
        this.value = (e.target as HTMLInputElement).value;
        this.filter = this.value.toLowerCase();
        this.open = true;
    }

    private onFocus() {
        if (this.blurTimer) { clearTimeout(this.blurTimer); this.blurTimer = null; }
        this.open = true;
    }

    private onBlur() {
        // Delay so an option click (which blurs the input first) still registers.
        this.blurTimer = setTimeout(() => { this.open = false; }, 150);
    }

    private select(t: TopicSummary) {
        this.value = t.topic;
        this.filter = '';
        this.open = false;
        this.dispatchEvent(new CustomEvent('topic-selected', {
            detail: t, bubbles: true, composed: true,
        }));
    }

    disconnectedCallback(): void {
        super.disconnectedCallback();
        if (this.blurTimer) clearTimeout(this.blurTimer);
    }

    render() {
        return html`
            <input
                type="text"
                placeholder="filter topics…"
                .value=${this.value}
                @input=${this.onInput}
                @focus=${this.onFocus}
                @blur=${this.onBlur}
            />
            <ul class=${this.open ? 'open' : ''}>
                ${this.topics.map(t => html`
                    <li data-testid="option"
                        ?hidden=${this.filter !== '' && !t.topic.toLowerCase().includes(this.filter)}
                        tabindex="0"
                        @mousedown=${(e: MouseEvent) => e.preventDefault()}
                        @click=${() => this.select(t)}
                        @keydown=${(e: KeyboardEvent) => { if (e.key === 'Enter') this.select(t); }}>
                        ${t.topic}
                    </li>
                `)}
            </ul>
        `;
    }
}
