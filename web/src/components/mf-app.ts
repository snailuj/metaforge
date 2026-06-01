import { LitElement, html, css, type PropertyValues } from 'lit'
import { customElement, state } from 'lit/decorators.js'
import { lookupWord, ApiError } from '@/api/client'
import { transformLookupToGraph, mergeSecondOrderGraph, stripSecondOrderNodes } from '@/graph/transform'
import { computeCrossLinks } from '@/graph/cross-links'
import { initStrings, getString } from '@/lib/strings'
import { GradingClient } from '@/api/grading-client'
import type { LookupResult } from '@/types/api'
import type { GraphData, GraphNode, Rarity } from '@/graph/types'
import type {
  ChainRecord,
  JudgementRecord,
  TopicSummary,
  VerdictSubmitDetail,
  Linkage,
  MetaphorVerdict,
  Tier,
} from '@/types/grading'
import { normaliseJudgement } from '@/types/grading'
import type { MfToast } from './mf-toast'

// Import components so they register
import './mf-search-bar'
import './mf-force-graph'
import './mf-results-panel'
import './mf-toast'
import './mf-error-banner'
import './mf-topic-picker'
import './mf-grade-panel'
import './mf-design-notes'
import './mf-mobile-notes-overlay'

type AppMode = 'browse' | 'grade'

type AppState = 'idle' | 'loading' | 'ready' | 'error'

@customElement('mf-app')
export class MfApp extends LitElement {
  static styles = css`
    :host {
      display: block;
      width: 100vw;
      height: 100vh;
      position: relative;
      overflow: hidden;
      background: var(--colour-bg-primary, #1a1a2e);
    }

    .search-container {
      position: absolute;
      top: var(--space-md, 1rem);
      left: 50%;
      transform: translateX(-50%);
      width: min(480px, calc(100% - 2rem));
      z-index: 30;
    }

    mf-force-graph {
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      z-index: 1;
    }

    mf-results-panel {
      z-index: 20;
    }

    .status-message {
      position: absolute;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      color: var(--colour-text-muted, #6b6560);
      font-family: var(--font-body, serif);
      font-size: 1.1rem;
      text-align: center;
      z-index: 5;
    }

    .error-message {
      color: #c47a7a;
    }

    .loading-ring {
      width: 40px;
      height: 40px;
      border: 3px solid var(--colour-accent-gold-dim, rgba(212, 175, 55, 0.3));
      border-top-color: var(--colour-accent-gold, #d4af37);
      border-radius: 50%;
      animation: spin 1s linear infinite;
      margin: 0 auto var(--space-md, 1rem);
    }

    @keyframes spin {
      to { transform: rotate(360deg); }
    }

    .rarity-filters {
      position: absolute;
      top: calc(var(--space-md, 1rem) + 48px);
      left: 50%;
      transform: translateX(-50%);
      display: flex;
      gap: var(--space-sm, 0.5rem);
      z-index: 15;
    }

    .rarity-toggle {
      display: flex;
      align-items: center;
      gap: 4px;
      font-size: 0.75rem;
      color: var(--colour-text-secondary, #a89f94);
      cursor: pointer;
    }

    .rarity-toggle.common { color: #8bb89a; }
    .rarity-toggle.common input { accent-color: #8bb89a; }
    .rarity-toggle.unusual { color: #c4956a; }
    .rarity-toggle.unusual input { accent-color: #c4956a; }
    .rarity-toggle.rare { color: #a88bc4; }
    .rarity-toggle.rare input { accent-color: #a88bc4; }

    .mode-toggle-bar {
      position: absolute;
      top: var(--space-md, 1rem);
      right: var(--space-md, 1rem);
      z-index: 30;
    }

    .grade-toggle {
      background: var(--colour-accent-gold-dim, rgba(212, 175, 55, 0.2));
      border: 1px solid var(--colour-accent-gold, #d4af37);
      color: var(--colour-accent-gold, #d4af37);
      border-radius: 4px;
      padding: 0.4rem 0.8rem;
      font-size: 0.8rem;
      cursor: pointer;
    }

    .grade-toggle:hover {
      background: var(--colour-accent-gold-dim, rgba(212, 175, 55, 0.35));
    }

    .banner-container {
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      z-index: 40;
    }

    /* ── Grade mode layout ─────────────────────────────────── */
    .grade-layout {
      display: flex;
      flex-direction: column;
      height: 100%;
      overflow: hidden;
      position: relative; /* anchor for the right-side notes overlay */
    }

    .grade-top {
      padding: var(--space-md, 1rem);
      padding-right: 9rem; /* leave room for mode-toggle-bar */
      flex-shrink: 0;
    }

    .grade-filters {
      display: flex;
      align-items: center;
      gap: var(--space-sm, 0.5rem);
      margin-top: var(--space-sm, 0.5rem);
    }

    /* Tri-state path filter — segmented control. */
    .path-filter {
      display: inline-flex;
      border: 1px solid var(--colour-border, #3a3550);
      border-radius: 4px;
      overflow: hidden;
    }

    .path-filter button {
      appearance: none;
      border: none;
      background: transparent;
      color: var(--colour-text-secondary, #a89f94);
      font-size: 0.8rem;
      padding: 4px 10px;
      cursor: pointer;
      border-right: 1px solid var(--colour-border, #3a3550);
    }

    .path-filter button:last-child {
      border-right: none;
    }

    .path-filter button[aria-pressed='true'] {
      background: var(--colour-accent-gold, #d4af37);
      color: #1a1a2e;
    }

    .grade-main {
      display: flex;
      flex: 1;
      overflow: hidden;
      gap: var(--space-md, 1rem);
      padding: 0 var(--space-md, 1rem);
    }

    /* Desktop: graph takes the remaining space, panel is fixed width */
    .grade-graph-pane {
      flex: 1;
      position: relative;
      min-height: 0;
    }

    .grade-graph-pane mf-force-graph {
      position: absolute;
      inset: 0;
    }

    .grade-panel-pane {
      width: 320px;
      flex-shrink: 0;
      overflow-y: auto;
    }

    /* Right-side collapsible notes overlay (desktop). The toggle tab is always
       visible; the panel floats over the right portion without resizing the
       graph or verdict panel. */
    .notes-overlay-toggle {
      position: absolute;
      top: 50%;
      right: 0;
      transform: translateY(-50%) rotate(180deg);
      writing-mode: vertical-rl;
      z-index: 45;
      background: var(--colour-accent-gold-dim, rgba(212, 175, 55, 0.2));
      border: 1px solid var(--colour-accent-gold, #d4af37);
      border-right: none;
      color: var(--colour-accent-gold, #d4af37);
      border-radius: 4px 0 0 4px;
      padding: 0.8rem 0.4rem;
      font-size: 0.8rem;
      letter-spacing: 0.05em;
      cursor: pointer;
    }

    .notes-overlay-toggle:hover {
      background: var(--colour-accent-gold-dim, rgba(212, 175, 55, 0.35));
    }

    .notes-overlay-panel {
      position: absolute;
      top: 0;
      right: 0;
      bottom: 0;
      width: min(420px, 90%);
      z-index: 46;
      background: #0f1115;
      border-left: 1px solid #2a3140;
      box-shadow: -4px 0 16px rgba(0, 0, 0, 0.4);
      display: flex;
      flex-direction: column;
      overflow-y: auto;
    }

    .notes-overlay-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 0.5rem 1rem;
      border-bottom: 1px solid #2a3140;
    }

    .notes-overlay-header h2 {
      margin: 0;
      font-size: 1rem;
      color: var(--colour-text-primary, #e6e6e6);
    }

    .notes-overlay-close {
      background: none;
      border: none;
      color: var(--colour-text-secondary, #c8c8c8);
      font-size: 1.2rem;
      line-height: 1;
      cursor: pointer;
      padding: 0.2rem 0.5rem;
    }

    .notes-overlay-close:hover {
      color: #fff;
    }

    /* Mobile flat-text chain list */
    .chain-list {
      flex: 1;
      overflow-y: auto;
      padding: var(--space-md, 1rem);
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
    }

    .chain-card {
      background: #181b22;
      border: 1px solid #2a3140;
      border-radius: 4px;
      padding: 0.6rem 0.8rem;
      cursor: pointer;
      font-size: 0.9rem;
      color: #c8c8c8;
      line-height: 1.5;
    }

    .chain-card:hover {
      background: #1e2330;
      border-color: #3a4150;
    }

    .chain-card.selected {
      border-color: var(--colour-accent-gold, #d4af37);
      background: #1e2330;
    }

    .grade-mobile-panel {
      flex-shrink: 0;
      padding: var(--space-md, 1rem);
      border-top: 1px solid #2a3140;
    }

    .grade-mobile-notes-btn {
      position: fixed;
      bottom: 1rem;
      right: 1rem;
      z-index: 50;
      background: var(--colour-accent-gold-dim, rgba(212, 175, 55, 0.2));
      border: 1px solid var(--colour-accent-gold, #d4af37);
      color: var(--colour-accent-gold, #d4af37);
      border-radius: 4px;
      padding: 0.5rem 1rem;
      font-size: 0.9rem;
      cursor: pointer;
    }

    .grade-empty {
      color: var(--colour-text-muted, #6b6560);
      font-size: 0.95rem;
      padding: 2rem;
      text-align: center;
    }
  `

  @state() private appState: AppState = 'idle'
  @state() private result: LookupResult | null = null
  @state() private graphData: GraphData = { nodes: [], links: [] }
  @state() private errorMessage = ''
  @state() private showCommon = true
  @state() private showUnusual = true
  @state() private showRare = true
  @state() mode: AppMode = 'browse'
  @state() private gradingAvailable = false

  // Grade-mode state
  @state() private gradeTopics: TopicSummary[] = []
  @state() private gradeChains: ChainRecord[] = []
  @state() private gradeJudgements: JudgementRecord[] = []
  @state() private selectedChain: ChainRecord | null = null
  @state() private notesHistory = ''
  @state() private notesOverlayOpen = false
  // Desktop right-side notes overlay — collapsed by default to preserve vertical space
  @state() private notesPanelCollapsed = true
  @state() private viewportWidth = window.innerWidth
  @state() private pendingQueue: JudgementRecord[] = []
  // Tri-state path filter (grade mode). 'both' shows all chains; 'ungraded' /
  // 'graded' restrict to chains without / with a verdict. Threaded to
  // mf-force-graph, which toggles visibility in place (no force-sim re-heat).
  @state() private pathFilter: 'both' | 'ungraded' | 'graded' = 'both'

  private currentWord = ''
  private lookupId = 0
  private selectId = 0
  private baseGraphData: GraphData = { nodes: [], links: [] }
  private gradingClient = new GradingClient()

  private hiddenRarities: Set<Rarity> = new Set()
  private handleResize = () => { this.viewportWidth = window.innerWidth }

  protected willUpdate(changed: PropertyValues): void {
    if (changed.has('showCommon') || changed.has('showUnusual') || changed.has('showRare')) {
      const hidden = new Set<Rarity>()
      if (!this.showCommon) hidden.add('common')
      if (!this.showUnusual) hidden.add('unusual')
      if (!this.showRare) hidden.add('rare')
      this.hiddenRarities = hidden
    }
  }

  async connectedCallback(): Promise<void> {
    super.connectedCallback()
    await initStrings()
    this.requestUpdate() // re-render now that strings are loaded

    // Probe grading availability and resolve initial mode
    this.gradingClient.probe().then(available => {
      this.gradingAvailable = available
      if (available) {
        const stored = localStorage.getItem('mf-mode')
        if (stored === 'grade' || stored === 'browse') {
          this.mode = stored
        } else {
          // Default to grade on the staging/next host, browse everywhere else
          this.mode = window.location.host === 'metaforge-next.julianit.me' ? 'grade' : 'browse'
        }
        if (this.mode === 'grade') {
          void this.initGradeMode()
        }
      } else {
        // Grading unavailable — force browse and hide toggle
        this.mode = 'browse'
      }
    }).catch(err => {
      console.warn('[mf-app] grading probe failed', err)
      this.gradingAvailable = false
      this.mode = 'browse'
    })

    // Check URL hash for initial word
    const hashWord = this.getWordFromHash()
    if (hashWord) {
      this.doLookup(hashWord)
    }

    window.addEventListener('hashchange', this.handleHashChange)
    window.addEventListener('resize', this.handleResize)
  }

  disconnectedCallback(): void {
    super.disconnectedCallback()
    window.removeEventListener('hashchange', this.handleHashChange)
    window.removeEventListener('resize', this.handleResize)
  }

  private handleHashChange = () => {
    const word = this.getWordFromHash()
    if (word && word !== this.currentWord) {
      this.doLookup(word)
    }
  }

  private getWordFromHash(): string | null {
    const match = window.location.hash.match(/^#\/word\/(.+)$/)
    return match ? decodeURIComponent(match[1]) : null
  }

  private setWordHash(word: string) {
    const newHash = `#/word/${encodeURIComponent(word)}`
    if (window.location.hash !== newHash) {
      window.location.hash = newHash
    }
  }

  private async handleSearch(e: CustomEvent<{ word: string }>) {
    this.doLookup(e.detail.word)
  }

  private async handleNodeNavigate(e: CustomEvent<{ word: string }>) {
    const node = e.detail
    if (node.word) {
      this.doLookup(node.word)
    }
  }

  private async handleNodeSelect(e: CustomEvent<GraphNode>) {
    const node = e.detail
    if (node.relationType === 'central') return

    const id = ++this.selectId
    try {
      const result = await lookupWord(node.word)
      if (id !== this.selectId) return // stale — a newer select superseded this one
      const stripped = stripSecondOrderNodes(this.baseGraphData)
      this.graphData = mergeSecondOrderGraph(stripped, node.id, result)
    } catch (err) {
      console.warn('[mf-app] second-order expansion failed', { nodeId: node.id, word: node.word }, err)
    }
  }

  private handleWordNavigate(e: CustomEvent<{ word: string }>) {
    this.doLookup(e.detail.word)
  }

  private handleCopy(e: CustomEvent<{ word: string }>) {
    const toast = this.shadowRoot?.querySelector('mf-toast') as MfToast | null
    toast?.show(getString('toast-copied', { word: e.detail.word }))
  }

  handleAuthExpired(): void {
    this.mode = 'browse'
    this.errorMessage = 'Auth expired — refresh to re-authenticate'
  }

  private toggleMode(): void {
    const next: AppMode = this.mode === 'browse' ? 'grade' : 'browse'
    this.mode = next
    localStorage.setItem('mf-mode', next)
    if (next === 'grade') {
      void this.initGradeMode()
    }
  }

  // --- Pending-queue helpers ---

  private static readonly PENDING_KEY = 'pending_judgements'

  private loadPendingQueue(): void {
    try {
      const raw = localStorage.getItem(MfApp.PENDING_KEY)
      this.pendingQueue = raw ? (JSON.parse(raw) as JudgementRecord[]) : []
    } catch {
      this.pendingQueue = []
    }
  }

  private savePendingQueue(): void {
    localStorage.setItem(MfApp.PENDING_KEY, JSON.stringify(this.pendingQueue))
  }

  private async flushPendingQueue(): Promise<void> {
    if (this.pendingQueue.length === 0) return
    const queue = [...this.pendingQueue]
    const remaining: JudgementRecord[] = []
    for (const j of queue) {
      try {
        await this.gradingClient.postJudgement(j)
      } catch {
        remaining.push(j)
      }
    }
    this.pendingQueue = remaining
    this.savePendingQueue()
  }

  /** Fetch topics and design-notes history when entering grade mode. */
  private async initGradeMode(): Promise<void> {
    this.loadPendingQueue()
    try {
      const [topicsRes, notesRes] = await Promise.all([
        this.gradingClient.getTopics(),
        this.gradingClient.getDesignNotes(),
      ])
      this.gradeTopics = topicsRes.topics
      this.notesHistory = notesRes.content
    } catch (err) {
      console.warn('[mf-app] initGradeMode failed', err)
      this.errorMessage = 'Failed to load grading data'
    }
  }

  private async handleTopicSelected(e: CustomEvent<TopicSummary>): Promise<void> {
    const topic = e.detail.topic
    this.selectedChain = null
    this.gradeChains = []
    this.gradeJudgements = []
    try {
      const [chainsRes, judgementsRes] = await Promise.all([
        this.gradingClient.getChains(topic),
        this.gradingClient.getJudgements(topic),
      ])
      this.gradeChains = chainsRes.records
      this.gradeJudgements = judgementsRes.records
    } catch (err) {
      console.warn('[mf-app] handleTopicSelected failed', { topic }, err)
      this.errorMessage = 'Failed to load chains for topic'
    }
  }

  private handleChainSelected(e: CustomEvent<ChainRecord>): void {
    this.selectedChain = e.detail
  }

  private toggleNotesPanel(): void {
    this.notesPanelCollapsed = !this.notesPanelCollapsed
  }

  /** Always-visible grade-mode filter row. Reused by desktop + mobile layouts.
   *  The tri-state path filter toggles which chains the graph shows; the graph
   *  applies it via visibility (no re-layout). */
  private renderGradeFilters() {
    const opt = (value: 'both' | 'ungraded' | 'graded', label: string) => html`
      <button
        data-testid="path-filter-${value}"
        aria-pressed=${this.pathFilter === value}
        @click=${() => { this.pathFilter = value }}
      >${label}</button>
    `
    return html`
      <div class="grade-filters">
        <div class="path-filter" role="group" aria-label="Path filter" data-testid="path-filter">
          ${opt('both', 'Both')}
          ${opt('ungraded', 'Ungraded')}
          ${opt('graded', 'Graded')}
        </div>
      </div>
    `
  }

  private async handleVerdictSubmit(e: CustomEvent<VerdictSubmitDetail>): Promise<void> {
    if (!this.selectedChain) return
    const chain = this.selectedChain
    const judgement: JudgementRecord = {
      schema_version: 'judgement.v2',
      judged_by: 'julian',
      round: chain.round,
      topic: chain.topic,
      topic_synset_id: chain.topic_synset_id,
      vehicle: chain.vehicle,
      vehicle_synset_id: chain.vehicle_synset_id,
      proposer: chain.proposer,
      chain_signature: chain.chain_signature,
      linkage: e.detail.linkage,
      metaphor: e.detail.metaphor,
      tiers: e.detail.tiers,
      confidence: e.detail.confidence,
      notes: e.detail.notes,
      supersedes_ts: null,
    }
    try {
      await this.gradingClient.postJudgement(judgement)
      // Refetch judgements for the current topic so the UI reflects the new verdict
      const judgementsRes = await this.gradingClient.getJudgements(chain.topic)
      this.gradeJudgements = judgementsRes.records
      this.selectedChain = null
      // Flush any verdicts that failed during a previous session
      await this.flushPendingQueue()
      if (this.pendingQueue.length > 0) {
        this.errorMessage = `${this.pendingQueue.length} verdict${this.pendingQueue.length === 1 ? '' : 's'} pending — will retry on next save`
      } else {
        // Clear a stale pending-banner if the queue is now empty
        if (this.errorMessage.includes('pending')) {
          this.errorMessage = ''
        }
      }
    } catch (err: unknown) {
      const status = (err as { status?: number }).status ?? (err instanceof Error && err.message.includes('401') ? 401 : 0)
      if (status === 401 || (err instanceof Error && err.message.includes('401'))) {
        this.handleAuthExpired()
      } else {
        console.warn('[mf-app] handleVerdictSubmit failed', err)
        // Push to queue so the judgement is not lost; advance past this chain
        this.pendingQueue = [...this.pendingQueue, judgement]
        this.savePendingQueue()
        this.selectedChain = null
        this.errorMessage = `${this.pendingQueue.length} verdict${this.pendingQueue.length === 1 ? '' : 's'} pending — will retry on next save`
      }
    }
  }

  private async handleSaveNote(e: CustomEvent<{ content: string }>): Promise<void> {
    try {
      await this.gradingClient.postDesignNote(e.detail.content)
      const notesRes = await this.gradingClient.getDesignNotes()
      this.notesHistory = notesRes.content
    } catch (err) {
      console.warn('[mf-app] handleSaveNote failed', err)
      this.errorMessage = 'Failed to save design note'
    }
  }

  /**
   * Look up whether a chain has already been judged by the current user.
   * Judgements arrive as an append-log, so the latest verdict for a signature
   * is the last matching record — re-grades supersede earlier passes. We surface
   * both axes, the multi-select tiers and the notes so the re-grade banner can echo
   * the grader's prior verdict and reasoning.
   *
   * Stored records may be v1 (flat `label`) or v2 (two axes); `normaliseJudgement`
   * maps either to the uniform two-axis view the panel expects. The handful of v1
   * labels that carry no signal on an axis (`bad_path` → metaphor unknown,
   * `irrelevant` → linkage moot) are coalesced to their closest concrete value for
   * display — these ≈5 legacy records are slated for an operator re-grade under v2.
   */
  private priorVerdict(
    chain: ChainRecord,
  ): { linkage: Linkage; metaphor: MetaphorVerdict; tiers: Tier[]; ts: string; notes: string } | null {
    let latest: JudgementRecord | null = null
    for (const j of this.gradeJudgements) {
      if (j.chain_signature === chain.chain_signature) latest = j
    }
    if (!latest) return null
    const { linkage, metaphor, tiers } = normaliseJudgement(latest)
    return {
      linkage: linkage ?? 'bad',
      metaphor: metaphor ?? 'irrelevant',
      tiers,
      ts: latest.ts ?? '',
      notes: latest.notes ?? '',
    }
  }

  /** Signatures that carry at least one verdict — the graded/ungraded predicate. */
  private get verdictedSignatures(): Set<string> {
    return new Set(this.gradeJudgements.map(j => j.chain_signature))
  }

  /** Chains shown in the mobile flat list, honouring the tri-state path filter.
   *  Mirrors the graph's predicate so desktop and mobile agree on what "graded"
   *  means. */
  private get visibleGradeChains(): ChainRecord[] {
    if (this.pathFilter === 'both') return this.gradeChains
    const verdicted = this.verdictedSignatures
    return this.gradeChains.filter(c =>
      this.pathFilter === 'graded'
        ? verdicted.has(c.chain_signature)
        : !verdicted.has(c.chain_signature),
    )
  }

  /** Render the flat-text chain label for mobile cards. */
  private chainLabel(chain: ChainRecord): string {
    return chain.chain.map(s => s.phrase).join(' → ')
  }

  private async doLookup(word: string) {
    const id = ++this.lookupId
    ++this.selectId // invalidate any in-flight second-order select
    this.currentWord = word
    this.appState = 'loading'
    this.errorMessage = ''

    try {
      const result = await lookupWord(word)
      if (id !== this.lookupId) return // stale — a newer lookup superseded this one
      this.result = result
      const graph = transformLookupToGraph(result)
      const nodeIds = new Set(graph.nodes.map(n => n.id))
      const crossLinks = computeCrossLinks(result, nodeIds)
      this.baseGraphData = { nodes: graph.nodes, links: [...graph.links, ...crossLinks] }
      this.graphData = this.baseGraphData
      this.appState = 'ready'
      this.setWordHash(word)
    } catch (err) {
      if (id !== this.lookupId) return // stale
      this.appState = 'error'
      if (err instanceof ApiError && err.status === 404) {
        this.errorMessage = getString('results-word-not-found', { word })
      } else {
        this.errorMessage = getString('error-generic')
      }
    }
  }

  private renderBrowseMode() {
    return html`
      <div class="search-container">
        <mf-search-bar
          .placeholder=${getString('search-placeholder')}
          .searchLabel=${getString('search-aria-label')}
          .value=${this.currentWord}
          @mf-search=${this.handleSearch}
        ></mf-search-bar>
      </div>

      <div role="status" aria-live="polite" aria-atomic="true">
        ${this.appState === 'loading'
          ? html`
              <div class="status-message">
                <div class="loading-ring"></div>
                ${getString('status-loading')}
              </div>
            `
          : ''}

        ${this.appState === 'error'
          ? html`<div class="status-message error-message">${this.errorMessage}</div>`
          : ''}

        ${this.appState === 'idle'
          ? html`<div class="status-message">${getString('status-idle')}</div>`
          : ''}
      </div>

      ${this.appState === 'ready'
        ? html`
            <div class="rarity-filters" role="group" aria-label="${getString('filter-aria-label')}">
              <label class="rarity-toggle common">
                <input type="checkbox" .checked=${this.showCommon}
                  @change=${(e: Event) => { this.showCommon = (e.target as HTMLInputElement).checked }}>
                ${getString('filter-common')}
              </label>
              <label class="rarity-toggle unusual">
                <input type="checkbox" .checked=${this.showUnusual}
                  @change=${(e: Event) => { this.showUnusual = (e.target as HTMLInputElement).checked }}>
                ${getString('filter-unusual')}
              </label>
              <label class="rarity-toggle rare">
                <input type="checkbox" .checked=${this.showRare}
                  @change=${(e: Event) => { this.showRare = (e.target as HTMLInputElement).checked }}>
                ${getString('filter-rare')}
              </label>
            </div>
          `
        : ''}

      <mf-force-graph
        .graphData=${this.graphData}
        .hiddenRarities=${this.hiddenRarities}
        @mf-node-select=${this.handleNodeSelect}
        @mf-node-navigate=${this.handleNodeNavigate}
        @mf-node-copy=${this.handleCopy}
      ></mf-force-graph>

      <mf-results-panel
        .result=${this.result}
        @mf-word-navigate=${this.handleWordNavigate}
        @mf-word-copy=${this.handleCopy}
      ></mf-results-panel>
    `
  }

  private renderGradeModeDesktop() {
    return html`
      <div class="grade-layout" data-testid="grade-layout">
        <div class="grade-top">
          <mf-topic-picker
            .topics=${this.gradeTopics}
            @topic-selected=${this.handleTopicSelected}
          ></mf-topic-picker>
          ${this.renderGradeFilters()}
        </div>

        <div class="grade-main">
          <div class="grade-graph-pane">
            <mf-force-graph
              .graphData=${this.graphData}
              .mode=${'grade'}
              .gradeChains=${this.gradeChains}
              .judgements=${this.gradeJudgements}
              .pathFilter=${this.pathFilter}
              .viewportWidth=${this.viewportWidth}
              @mf-node-select=${this.handleNodeSelect}
              @mf-node-navigate=${this.handleNodeNavigate}
              @mf-node-copy=${this.handleCopy}
              @chain-selected=${this.handleChainSelected}
            ></mf-force-graph>
          </div>

          ${this.selectedChain
            ? html`
              <div class="grade-panel-pane">
                <mf-grade-panel
                  .chain=${this.selectedChain}
                  .priorVerdict=${this.priorVerdict(this.selectedChain)}
                  @verdict-submit=${this.handleVerdictSubmit}
                ></mf-grade-panel>
              </div>`
            : ''}
        </div>

        <button
          class="notes-overlay-toggle"
          data-testid="notes-overlay-toggle"
          aria-expanded=${!this.notesPanelCollapsed}
          @click=${this.toggleNotesPanel}
        >Notes</button>

        ${this.notesPanelCollapsed
          ? ''
          : html`
            <div class="notes-overlay-panel" data-testid="notes-overlay-panel">
              <div class="notes-overlay-header">
                <h2>Design notes</h2>
                <button
                  class="notes-overlay-close"
                  aria-label="Collapse design notes"
                  @click=${this.toggleNotesPanel}
                >×</button>
              </div>
              <mf-design-notes
                .history=${this.notesHistory}
                @save-note=${this.handleSaveNote}
              ></mf-design-notes>
            </div>`}
      </div>
    `
  }

  private renderGradeModeMobile() {
    return html`
      <div class="grade-layout" data-testid="grade-layout-mobile">
        <div class="grade-top">
          <mf-topic-picker
            .topics=${this.gradeTopics}
            @topic-selected=${this.handleTopicSelected}
          ></mf-topic-picker>
          ${this.renderGradeFilters()}
        </div>

        <div class="chain-list" data-testid="chain-list">
          ${this.visibleGradeChains.length === 0
            ? html`<div class="grade-empty">Select a topic to load chains.</div>`
            : this.visibleGradeChains.map(chain => html`
                <div
                  class="chain-card ${this.selectedChain?.chain_signature === chain.chain_signature ? 'selected' : ''}"
                  data-testid="chain-card"
                  @click=${() => { this.selectedChain = chain }}
                >${this.chainLabel(chain)}</div>
              `)}
        </div>

        ${this.selectedChain
          ? html`
            <div class="grade-mobile-panel">
              <mf-grade-panel
                .chain=${this.selectedChain}
                .priorVerdict=${this.priorVerdict(this.selectedChain)}
                @verdict-submit=${this.handleVerdictSubmit}
              ></mf-grade-panel>
            </div>`
          : ''}

        <button
          class="grade-mobile-notes-btn"
          data-testid="notes-btn"
          @click=${() => { this.notesOverlayOpen = true }}
        >Notes</button>

        <mf-mobile-notes-overlay
          .open=${this.notesOverlayOpen}
          .history=${this.notesHistory}
          @close=${() => { this.notesOverlayOpen = false }}
          @save-note=${this.handleSaveNote}
        ></mf-mobile-notes-overlay>
      </div>
    `
  }

  render() {
    return html`
      ${this.errorMessage
        ? html`<div class="banner-container"><mf-error-banner .message=${this.errorMessage}></mf-error-banner></div>`
        : ''}

      ${this.gradingAvailable
        ? html`
          <div class="mode-toggle-bar">
            <button
              class="grade-toggle"
              data-testid="grade-toggle"
              @click=${this.toggleMode}
            >${this.mode === 'grade' ? 'Browse mode' : 'Grade mode'}</button>
          </div>`
        : ''}

      ${this.mode === 'grade'
        ? (this.viewportWidth >= 900 ? this.renderGradeModeDesktop() : this.renderGradeModeMobile())
        : this.renderBrowseMode()}

      <mf-toast></mf-toast>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'mf-app': MfApp
  }
}
