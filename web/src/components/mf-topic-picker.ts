import { LitElement, html, css } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import type { TopicSummary } from '../types/grading';

@customElement('mf-topic-picker')
export class MfTopicPicker extends LitElement {
    static styles = css`
        :host { display: block; }
        input { width: 100%; padding: 0.4rem; font-size: 1rem; box-sizing: border-box; }
        ul { list-style: none; padding: 0; margin: 0; max-height: 50vh; overflow-y: auto; }
        li { padding: 0.5rem; cursor: pointer; }
        li:hover, li:focus { background: var(--mf-bg-hover, #2a3140); outline: none; }
        li[hidden] { display: none; }
    `;

    @property({ type: Array }) topics: TopicSummary[] = [];
    @state() private filter = '';

    private onInput(e: Event) {
        this.filter = (e.target as HTMLInputElement).value.toLowerCase();
    }

    private select(t: TopicSummary) {
        this.dispatchEvent(new CustomEvent('topic-selected', {
            detail: t, bubbles: true, composed: true,
        }));
    }

    render() {
        return html`
            <input type="text" placeholder="filter topics…" @input=${this.onInput} />
            <ul>
                ${this.topics.map(t => html`
                    <li data-testid="option"
                        ?hidden=${this.filter !== '' && !t.topic.toLowerCase().includes(this.filter)}
                        tabindex="0"
                        @click=${() => this.select(t)}
                        @keydown=${(e: KeyboardEvent) => { if (e.key === 'Enter') this.select(t); }}>
                        ${t.topic}
                    </li>
                `)}
            </ul>
        `;
    }
}
