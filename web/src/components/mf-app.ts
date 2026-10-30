import { LitElement, html, css, type PropertyValues } from 'lit'
import { customElement, state } from 'lit/decorators.js'
import { lookupWord, ApiError, streamForest, ForestError } from '@/api/client'
import { transformLookupToGraph, mergeExpansion, recentreGraph, mergeGlimpse, solidify, relationReach, resolveEndpoint } from '@/graph/transform'
import {
  composeForest, fadeMarks, forestToGraph, litPaths, nextFadeEnd, streamMarks, FOREST_FADE_MS,
  type ForestGraph, type ForestNodePool, type ForestOverlay, type ForestTarget, type StreamMarks,
} from '@/graph/forest'
import { initialForestState, inFlight, reduceForest, litTarget, sameTarget, type ForestEvent, type ForestState, type StreamPath } from '@/forest/state'
import { initialProgress, isBusy, reduceProgress, type ProgressEvent, type ProgressState } from '@/progress/model'
import { startTimer } from '@/lib/timing'
import { rememberedOpen } from './mf-progress-panel'
import { computeCrossLinks } from '@/graph/cross-links'
import { arrivalBatch, ARRIVAL_WINDOW_MS } from '@/graph/batch'
import { initStrings, getString } from '@/lib/strings'
import { GradingClient } from '@/api/grading-client'
import type { LookupResult } from '@/types/api'
import type { GraphData, GraphNode, Rarity, RelationType } from '@/graph/types'
import type {
  ChainRecord,
  JudgementRecord,
  TopicSummary,
  VerdictSubmitDetail,
  WalkEntry,
  GuidedEntry,
  Linkage,
  MetaphorVerdict,
  Tier,
  Tag,
  Confidence,
  GlossMap,
  SenseInventoryMap,
} from '@/types/grading'
import { normaliseJudgement, senseInventoryKey } from '@/types/grading'
import type { MfToast } from './mf-toast'
import type { MfUndoToast } from './mf-undo-toast'
import type { MfForceGraph } from './mf-force-graph'

// Import components so they register
import './mf-search-bar'
import './mf-force-graph'
import './mf-results-panel'
import './mf-forest-panel'
import './mf-progress-panel'
import './mf-toast'
import './mf-undo-toast'
import './mf-error-banner'
import './mf-topic-picker'
import './mf-grade-panel'
import './mf-grade-walk'
import './mf-grade-regrade'
import './mf-grade-sensecheck'
import './mf-signal-report'
import './mf-design-notes'
import './mf-mobile-notes-overlay'

type AppMode = 'browse' | 'grade'

type AppState = 'idle' | 'loading' | 'ready' | 'error'

/** Everything Back or Forward needs to put a browse view back on screen. */
interface ViewSnapshot {
  word: string
  result: LookupResult
  graph: GraphData
  expanded: ReadonlyMap<string, LookupResult>
  lastClickedId: string | null
  forestWord: string
  glimpsed: ReadonlyMap<string, LookupResult>
  fillTargets: ReadonlySet<string>
}

// Views kept for Back/Forward; older entries fall back to a fresh lookup.
const MAX_VIEWS = 50
const UNDO_TOAST_MS = 6000
// Second-level glimpses are one lookup each; a few at a time keeps the API and
// the layout calm while they stream in.
const MAX_GLIMPSE_LOOKUPS = 4
// The phone layout (forest bottom sheet) applies at this width and below.
const PHONE_MAX_WIDTH = 768
const SOURCE_URL = 'https://github.com/snailuj/metaforge'
// GitHub's own mark (Primer Octicons mark-github, MIT), path unmodified.
const GITHUB_MARK = 'M8 0c4.42 0 8 3.58 8 8a8.013 8.013 0 0 1-5.45 7.59c-.4.08-.55-.17-.55-.38 0-.27.01-1.13.01-2.2 0-.75-.25-1.23-.54-1.48 1.78-.2 3.65-.88 3.65-3.95 0-.88-.31-1.59-.82-2.15.08-.2.36-1.02-.08-2.12 0 0-.67-.22-2.2.82-.64-.18-1.32-.27-2-.27-.68 0-1.36.09-2 .27-1.53-1.03-2.2-.82-2.2-.82-.44 1.1-.16 1.92-.08 2.12-.51.56-.82 1.28-.82 2.15 0 3.06 1.86 3.75 3.64 3.95-.23.2-.44.55-.51 1.07-.46.21-1.61.55-2.33-.66-.15-.24-.6-.83-1.23-.82-.67.01-.27.38.01.53.34.19.73.9.82 1.13.16.45.68 1.31 2.69.94 0 .67.01 1.3.01 1.49 0 .21-.15.45-.55.38A7.995 7.995 0 0 1 0 8c0-4.42 3.58-8 8-8Z'
// Synonyms always show; these join them only when ticked on the results panel.
const DEFAULT_HIDDEN_RELATIONS: ReadonlySet<RelationType> = new Set(['hyponym', 'hypernym', 'similar'])

/** The paths a streaming request has drawn, or null when nothing streams. */
function streamPaths(s: ForestState): Readonly<Record<string, StreamPath>> | null {
  return s.request.kind === 'streaming' ? s.request.paths : null
}

@customElement('mf-app')
export class MfApp extends LitElement {
  static styles = css`
    :host {
      display: block;
      width: 100vw;
      /* dvh tracks the visual viewport (shrinks when mobile browser toolbar appears),
         so the app never extends behind the toolbar. Falls back to 100vh on older
         browsers where dvh is unsupported — acceptable static degradation. */
      height: 100dvh;
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

    /* The activity panel sits bottom right, under the forest panel: the forest
       panel keeps clear of its button, and of the whole panel while it is open. */
    :host {
      --progress-panel-max: 16rem;
    }

    mf-forest-panel {
      --progress-reserve: calc(2.75rem + var(--space-md, 1rem));
    }

    mf-forest-panel.progress-open {
      --progress-reserve: calc(var(--progress-panel-max) + 2.75rem + 2 * var(--space-md, 1rem));
    }

    /* Phone: the forest is a bottom sheet (z 25). An opened results panel
       slides over it; closing it uncovers the sheet again. */
    @media (max-width: 768px) {
      mf-results-panel {
        z-index: 26;
      }
    }

    /* Bottom left, under the results panel (z 10) so it never covers a control.
       On a phone it rides above the forest sheet (--forest-sheet-height). */
    /* GitHub's mark as a link to the repository, which its brand rules allow.
       Those rules forbid recolouring or reshaping it: white on the dark UI,
       no words joined to it. Top left on desktop; on phones it rides above the
       forest sheet, bottom left, clear of the search bar. */
    .source-link {
      position: absolute;
      inset-inline-start: var(--space-md, 1rem);
      inset-block-start: var(--space-md, 1rem);
      z-index: 5;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      inline-size: 2.75rem;
      block-size: 2.75rem;
      border-radius: var(--hud-radius, 4px);
      color: #fff;
    }

    .source-link svg { fill: currentColor; }

    .source-link:hover { background: var(--colour-panel-deep); }

    .source-link:focus-visible {
      outline: 2px solid var(--colour-accent-gold);
      outline-offset: 2px;
    }

    @media (max-width: 768px) {
      .source-link {
        inset-block-start: auto;
        inset-inline-start: var(--space-sm, 0.5rem);
        inset-block-end: calc(var(--forest-sheet-height, 0px) + env(safe-area-inset-bottom, 0px));
      }
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

    /* Re-Centre and the Undo toast share one slot under the filters: the toast
       takes it as Re-Centre is used, and gives it back on the next node click. */
    :host {
      --recentre-slot-top: calc(var(--space-md, 1rem) + 84px);
    }

    .recentre,
    mf-undo-toast {
      position: absolute;
      top: var(--recentre-slot-top);
      left: 50%;
      transform: translateX(-50%);
    }

    mf-undo-toast {
      bottom: auto;
    }

    .recentre {
      z-index: 15;
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      max-width: calc(100% - 2rem);
      padding: 0.3rem 0.9rem 0.3rem 0.7rem;
      border: 1px solid var(--colour-accent-gold-dim, rgba(212, 175, 55, 0.5));
      border-radius: 999px;
      background: var(--colour-panel-deep, rgba(14, 22, 42, 0.88));
      box-shadow: 0 0 18px var(--colour-forest-root-glow, rgba(212, 175, 55, 0.25));
      color: var(--colour-accent-gold, #d4af37);
      font-family: var(--font-heading, serif);
      font-size: 0.8rem;
      font-variant: small-caps;
      letter-spacing: 0.06em;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      cursor: pointer;
      transition: color 0.2s ease, text-shadow 0.2s ease, background 0.2s ease;
    }

    .recentre:hover,
    .recentre:focus-visible {
      color: #f3d77a;
      text-shadow: 0 0 10px rgba(212, 175, 55, 0.6);
      background: rgba(26, 22, 10, 0.92);
      outline: none;
    }

    .recentre-glyph {
      font-size: 0.95rem;
      line-height: 1;
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

    /* Mobile walk: a full-width, vertically scrollable region so the whole shell
       (head-chain + verdict controls + notes) is reachable. Unlike .grade-main it
       does not clip — it takes the column's remaining height and scrolls. */
    .grade-walk-scroll {
      flex: 1;
      overflow-y: auto;
      padding: var(--space-md, 1rem);
      /* Safe-area-aware bottom padding so the last row clears the mobile browser
         toolbar. env(safe-area-inset-bottom) covers the notch; the extra 1rem
         ensures breathing room even without notch support. */
      padding-bottom: max(2rem, env(safe-area-inset-bottom, 1rem));
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
  // synset_id → {pos, definition} for chain synsets; fetched once on grade entry,
  // threaded to the panels so the grader sees the topic's sense. Empty on failure.
  @state() private gradeGlosses: GlossMap = {}
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

  // Walk sub-mode (grade mode). 'topic' = today's topic-picker flow; 'walk' steps
  // through the server-ordered acquisition list (GET /api/grading/walk) one chain
  // at a time. walkGradedSigs is a SESSION set — a chain graded this session drops
  // out of the visible walk (so the next ungraded one slides in) without a refetch.
  @state() private gradeView: 'topic' | 'walk' | 'regrade' | 'sensecheck' | 'guided' = 'topic'
  @state() private walkEntries: WalkEntry[] = []
  @state() private walkPos = 0
  @state() private walkSkipGraded = true
  @state() private walkGradedSigs: Set<string> = new Set()
  // The walk spans ALL topics, so it needs the global verdict set (gradeJudgements
  // is topic-scoped) for prior-verdict prefill + context-graph edge colouring.
  @state() private walkJudgements: JudgementRecord[] = []
  // Memoised single-element array fed to the desktop context graph, rebuilt only
  // when the current chain changes so the force-sim doesn't re-frame on every
  // unrelated mf-app re-render.
  private _walkGraphSig = ''
  private _walkGraphChains: ChainRecord[] = []

  // Guided walk sub-mode: an EXACT operator-prefilled candidate order
  // (GET /api/grading/guided-walk). Literal Prev/Next — no skip-graded, no dwell.
  // BLIND: the server withholds the stored judge verdict; agreement is computed
  // off-band after the round, so grading here stays unanchored.
  @state() private guidedEntries: GuidedEntry[] = []
  @state() private guidedPos = 0
  @state() private guidedGradedSigs: Set<string> = new Set()
  @state() private guidedJudgements: JudgementRecord[] = []
  // Guided prefill opt-in (amendment passes over already-graded chains). Blind
  // is the default and resets whenever guided mode re-initialises.
  @state() private guidedPrefill = false
  // canonical phrase key -> ranked noun senses, accumulated per viewed chain.
  // Fetched lazily from /senses (per-key route); the panel's fan is dead without it.
  @state() private senseInventories: SenseInventoryMap = {}
  private _sensesRequested = new Set<string>()
  @state() private guidedBatch: string | null = null
  private _guidedGraphSig = ''
  private _guidedGraphChains: ChainRecord[] = []

  // Metaphor forest. forestState is the whole UI state machine (forest/state.ts);
  // the rest is derived from it or is an effect handle.
  @state() private forestState: ForestState = initialForestState()
  @state() private forestOverlay: ForestOverlay | null = null
  @state() private forestLit: ReadonlySet<string> | null = null
  private forestGraph: ForestGraph | null = null
  private forestAbort: AbortController | null = null
  private forestLitTarget: ForestTarget | null = null
  // Streaming: the marks drawn beyond the latest snapshot (pending, kept or
  // fading), the timer that ends the next fade, and the node objects for the
  // committed word, reused so nodes keep their positions as the forest grows.
  private forestMarks: StreamMarks = { nodes: new Map(), links: new Map() }
  private forestFadeTimer: ReturnType<typeof setTimeout> | null = null
  private forestPool: ForestNodePool = new Map()
  // The activity log (progress/model.ts) and whether its panel is open, which
  // the forest panel makes room for.
  @state() private progress: ProgressState = initialProgress()
  @state() private progressOpen = rememberedOpen()

  private currentWord = ''
  private lookupId = 0
  // Bumped whenever the graph is replaced wholesale, so an expansion that
  // resolves afterwards is dropped instead of merged into the wrong graph.
  private graphGen = 0
  // The thesaurus graph on screen (the lookup plus every expansion the user
  // has clicked open); the forest is overlaid on it to give graphData.
  private thesaurusGraph: GraphData = { nodes: [], links: [] }
  // Node ids whose relations are on the graph, and those still being fetched.
  // Each expanded node's lookup (the source's included) is kept, so a
  // re-click never refetches and Re-Centre can show its results at once.
  private expanded: ReadonlyMap<string, LookupResult> = new Map()
  private expanding = new Set<string>()
  // Two levels per word: every word a search or click adds is owed a glimpse
  // of its own synonyms (fillTargets). glimpsed holds each word's lookup once
  // drawn, reused if the word is clicked. Only visible words are glimpsed.
  private glimpsed: ReadonlyMap<string, LookupResult> = new Map()
  private fillTargets: ReadonlySet<string> = new Set()
  private filling = new Set<string>()
  private fillFailed = new Set<string>()
  // Glimpses merge into thesaurusGraph at once but reach the graph in batches, so
  // a wave of them reheats the layout once. Any other recomposition carries them.
  private glimpseBatch = arrivalBatch(ARRIVAL_WINDOW_MS, () => this.recomposeGraph())
  @state() private hiddenRelations: ReadonlySet<RelationType> = DEFAULT_HIDDEN_RELATIONS
  // The node a Re-Centre would centre on: the last one clicked.
  @state() private lastClickedId: string | null = null
  // Back/Forward: every history entry the app makes carries a view id, and the
  // view on screen is saved under its id whenever the app leaves it.
  private viewId = ''
  // The word in the view's URL. Not currentWord, which a lookup sets as soon
  // as it starts, while the old view is still on screen.
  private viewWord = ''
  private viewSeq = 0
  // Ids outlive a page load in history.state, so they must not repeat across loads.
  private readonly viewPrefix = Date.now().toString(36)
  private views = new Map<string, ViewSnapshot>()
  private gradingClient = new GradingClient()

  private hiddenRarities: Set<Rarity> = new Set()
  // The forest sheet's height on a phone, published as --forest-sheet-height so
  // the bottom-corner controls sit above it.
  private forestSheetObserver: ResizeObserver | null = null
  private observedSheet: Element | null = null
  private handleResize = () => { this.viewportWidth = window.innerWidth }

  protected updated(changed: PropertyValues): void {
    const sheet = this.shadowRoot?.querySelector('mf-forest-panel') ?? null
    if (sheet !== this.observedSheet) {
      this.forestSheetObserver?.disconnect()
      this.forestSheetObserver = null
      this.observedSheet = sheet
      if (sheet && typeof ResizeObserver !== 'undefined') {
        this.forestSheetObserver = new ResizeObserver(this.syncForestSheetHeight)
        this.forestSheetObserver.observe(sheet)
      }
      this.syncForestSheetHeight()
    } else if (changed.has('viewportWidth')) {
      this.syncForestSheetHeight()
    }
  }

  private syncForestSheetHeight = (): void => {
    const sheet = this.observedSheet ?? this.shadowRoot?.querySelector('mf-forest-panel')
    const height = sheet && this.viewportWidth <= PHONE_MAX_WIDTH ? Math.round(sheet.getBoundingClientRect().height) : 0
    this.style.setProperty('--forest-sheet-height', `${height}px`)
  }

  protected willUpdate(changed: PropertyValues): void {
    if (changed.has('showCommon') || changed.has('showUnusual') || changed.has('showRare')) {
      const hidden = new Set<Rarity>()
      if (!this.showCommon) hidden.add('common')
      if (!this.showUnusual) hidden.add('unusual')
      if (!this.showRare) hidden.add('rare')
      this.hiddenRarities = hidden
      this.pumpGlimpses() // words a rarity hid may now be shown
    }
    // Lazily fetch sense inventories for whichever chain the active grade view
    // shows (fire-and-forget; results merge into senseInventories as they land).
    void this.ensureSenseInventories(this.currentGradeChain())
  }

  /** The chain the active grade view is currently showing, if any. */
  private currentGradeChain(): ChainRecord | null {
    if (this.mode !== 'grade') return null
    if (this.gradeView === 'topic') return this.selectedChain
    if (this.gradeView === 'walk') return this.walkCurrent?.record ?? null
    if (this.gradeView === 'guided') return this.guidedCurrent?.record ?? null
    return null
  }

  /** Fetch (once per key) the sense inventory for each step phrase of a chain.
   *  Failures degrade to an empty fan — logged, never thrown into render. */
  private async ensureSenseInventories(chain: ChainRecord | null): Promise<void> {
    if (!chain) return
    // Phrase key + head-lemma key (the fan falls back to the head's senses when a
    // multi-word phrase has no phrase-level inventory).
    const keys = [...new Set((chain.chain ?? []).flatMap(st =>
      [senseInventoryKey(st.phrase), st.head ? senseInventoryKey(st.head) : '']))]
      .filter(k => k && !this._sensesRequested.has(k))
    if (keys.length === 0) return
    keys.forEach(k => this._sensesRequested.add(k))
    const results = await Promise.all(keys.map(async k => {
      try {
        return await this.gradingClient.getSenses(k)
      } catch (err) {
        console.warn('[mf-app] getSenses failed for', k, err)
        return { key: k, senses: [] }
      }
    }))
    const merged = { ...this.senseInventories }
    for (const r of results) merged[r.key] = r.senses
    this.senseInventories = merged
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
      this.doLookup(hashWord, { history: 'replace' })
    }

    window.addEventListener('popstate', this.handlePopState)
    window.addEventListener('hashchange', this.handleHashChange)
    window.addEventListener('resize', this.handleResize)
  }

  disconnectedCallback(): void {
    super.disconnectedCallback()
    this.forestSheetObserver?.disconnect()
    this.forestSheetObserver = null
    this.observedSheet = null
    window.removeEventListener('popstate', this.handlePopState)
    window.removeEventListener('hashchange', this.handleHashChange)
    window.removeEventListener('resize', this.handleResize)
    if (this.forestFadeTimer) clearTimeout(this.forestFadeTimer)
    this.forestFadeTimer = null
    this.glimpseBatch.cancel()
  }

  // The browser already made the entry (a typed URL, or Back to an entry the
  // app holds no view for), so the lookup takes it over rather than pushing.
  private handleHashChange = () => {
    const word = this.getWordFromHash()
    if (word && word !== this.currentWord) {
      this.doLookup(word, { history: 'replace' })
    }
  }

  /** Back/Forward onto an entry whose view is still in memory: put it back as
   *  it was left. Anything else falls through to the hashchange lookup. */
  private handlePopState = () => {
    // history.state is the popped entry's state, the same object as e.state.
    const id = (history.state as { mfView?: unknown } | null)?.mfView
    const snapshot = typeof id === 'string' ? this.views.get(id) : undefined
    if (!snapshot) {
      console.debug('[mf-app] popstate without a held view', { id })
      return
    }
    this.saveView()
    this.restoreView(id as string, snapshot)
  }

  private saveView(): void {
    if (!this.viewId || !this.result) return
    this.views.delete(this.viewId) // re-insert so eviction drops the least recent
    this.views.set(this.viewId, {
      word: this.viewWord,
      result: this.result,
      graph: this.thesaurusGraph,
      expanded: this.expanded,
      lastClickedId: this.lastClickedId,
      forestWord: this.forestState.word,
      glimpsed: this.glimpsed,
      fillTargets: this.fillTargets,
    })
    while (this.views.size > MAX_VIEWS) {
      const oldest = this.views.keys().next().value as string
      this.views.delete(oldest)
      console.debug('[mf-app] evicted view', { id: oldest })
    }
  }

  /** Give the view now on screen its own history entry: a new one, or the
   *  current entry when the browser has already made it. */
  private enterView(word: string, mode: 'push' | 'replace'): void {
    this.viewId = `${this.viewPrefix}-${++this.viewSeq}`
    this.viewWord = word
    const url = `#/word/${encodeURIComponent(word)}`
    if (mode === 'push') history.pushState({ mfView: this.viewId }, '', url)
    else history.replaceState({ mfView: this.viewId }, '', url)
  }

  private restoreView(id: string, v: ViewSnapshot): void {
    ++this.lookupId // a lookup still in flight belonged to the view being left
    ++this.graphGen
    this.viewId = id
    this.viewWord = v.word
    this.currentWord = v.word
    this.result = v.result
    this.thesaurusGraph = v.graph
    this.expanded = v.expanded
    this.expanding = new Set()
    this.glimpsed = v.glimpsed
    this.fillTargets = v.fillTargets
    this.filling = new Set()
    this.fillFailed = new Set()
    this.lastClickedId = v.lastClickedId
    this.appState = 'ready'
    this.errorMessage = ''
    this.undoToast?.hide()
    this.dispatchForest({ type: 'word-committed', word: v.forestWord })
    this.reportProgress({ type: 'view-restored', keepForest: inFlight(this.forestState) })
    this.recomposeGraph()
    console.info('[mf-app] restored view', { id, word: v.word, nodes: v.graph.nodes.length })
    this.pumpGlimpses() // a view left mid-stream picks up where it stopped
    void this.focusSource()
  }

  private get undoToast(): MfUndoToast | null {
    return this.shadowRoot?.querySelector('mf-undo-toast') ?? null
  }

  /** Fly the camera to the source node once the graph has the new data. */
  private async focusSource(): Promise<void> {
    await this.updateComplete
    const source = this.thesaurusGraph.nodes.find(n => n.relationType === 'central')
    const graph = this.shadowRoot?.querySelector('mf-force-graph') as MfForceGraph | null
    if (!source || !graph) return
    await graph.updateComplete // it feeds the library the new nodes in its own update
    graph.focusNode(source.id)
  }

  /** Make the last-clicked node the source. Every node stays where it is; the
   *  camera, search box and results move to it, and Back undoes it. */
  private async recentre(): Promise<void> {
    const node = this.thesaurusGraph.nodes.find(n => n.id === this.lastClickedId)
    if (!node || node.relationType === 'central') return
    const gen = this.graphGen
    let result = this.expanded.get(node.id)
    try {
      result ??= await lookupWord(node.word)
    } catch (err) {
      console.warn('[mf-app] re-centre lookup failed', { nodeId: node.id, word: node.word }, err)
      const toast = this.shadowRoot?.querySelector('mf-toast') as MfToast | null
      toast?.show(getString('recentre-failed', { word: node.word }), 4000)
      return
    }
    if (gen !== this.graphGen) return // the graph was replaced meanwhile

    this.saveView()
    this.thesaurusGraph = recentreGraph(this.thesaurusGraph, node.id)
    this.expanded = new Map(this.expanded).set(node.id, result)
    this.currentWord = node.word
    this.result = result
    this.lastClickedId = null
    this.recomposeGraph()
    this.enterView(node.word, 'push')
    console.info('[mf-app] re-centred', { word: node.word, nodes: this.thesaurusGraph.nodes.length })
    this.undoToast?.show(getString('undo-recentred', { word: node.word }), UNDO_TOAST_MS)
    await this.focusSource()
  }

  private handleUndo(): void {
    history.back()
  }

  private getWordFromHash(): string | null {
    const match = window.location.hash.match(/^#\/word\/(.+)$/)
    return match ? decodeURIComponent(match[1]) : null
  }

  private async handleSearch(e: CustomEvent<{ word: string }>) {
    this.doLookup(e.detail.word)
  }

  /** Double-click: start afresh at the node's word, with Undo on offer. */
  private async handleNodeNavigate(e: CustomEvent<{ id?: string; word: string }>) {
    const node = e.detail
    if (node.word) {
      // Forest words are often phrases the thesaurus lacks; look them up softly.
      const fromForest = !!node.id && !!this.forestOverlay?.byNodeId.has(node.id)
      if (await this.doLookup(node.word, { soft: fromForest })) {
        this.undoToast?.show(getString('undo-started-over', { word: node.word }), UNDO_TOAST_MS)
      }
    }
  }

  /** Single click: open the node's own relations onto the graph, keeping the
   *  source and every earlier expansion where they are. */
  private async handleNodeSelect(e: CustomEvent<GraphNode>) {
    const node = e.detail
    this.lastClickedId = node.relationType === 'central' ? null : node.id
    if (node.relationType === 'central') return
    this.undoToast?.hide() // Re-Centre is back in the slot the toast shares
    if (this.expanded.has(node.id) || this.expanding.has(node.id)) {
      console.debug('[mf-app] node already expanded', { nodeId: node.id })
      return
    }

    const gen = this.graphGen
    this.expanding.add(node.id)
    this.reportProgress({ type: 'expansion-started', word: node.word })
    try {
      const result = this.glimpsed.get(node.id) ?? await lookupWord(node.word)
      if (gen !== this.graphGen) return // stale — the graph was replaced meanwhile
      const merged = mergeExpansion(this.thesaurusGraph, node.id, result)
      // Everything the node now leads to is a word this click added: it turns
      // solid, and each is owed its own glimpse.
      const children = merged.links.filter(l => resolveEndpoint(l.source) === node.id).map(l => resolveEndpoint(l.target))
      this.thesaurusGraph = solidify(merged, [node.id, ...children])
      this.expanded = new Map(this.expanded).set(node.id, result)
      this.fillTargets = new Set([...this.fillTargets, ...children])
      console.debug('[mf-app] expanded node', { nodeId: node.id, nodes: this.thesaurusGraph.nodes.length })
      this.reportProgress({ type: 'expansion-done', word: node.word, words: children.length })
      this.recomposeGraph()
      this.pumpGlimpses()
    } catch (err) {
      console.warn('[mf-app] second-order expansion failed', { nodeId: node.id, word: node.word }, err)
      if (gen === this.graphGen) this.reportProgress({ type: 'expansion-failed', word: node.word })
    } finally {
      this.expanding.delete(node.id)
    }
  }

  /** Start glimpses for owed words the graph shows, up to the lookup limit, and
   *  tell the activity log how many more are waiting for a slot. */
  private pumpGlimpses(): void {
    if (this.fillTargets.size === 0) {
      this.reportProgress({ type: 'glimpses-waiting', n: 0 })
      return
    }
    const reach = relationReach(this.thesaurusGraph, this.hiddenRelations)
    const byId = new Map(this.thesaurusGraph.nodes.map(n => [n.id, n]))
    let waiting = 0
    for (const id of this.fillTargets) {
      if (this.glimpsed.has(id) || this.expanded.has(id) || this.filling.has(id) || this.fillFailed.has(id)) continue
      if (reach && !reach.has(id)) continue // hidden: glimpsed if a toggle reveals it
      const node = byId.get(id)
      if (!node || this.hiddenRarities.has(node.rarity ?? 'unusual')) continue
      if (this.filling.size < MAX_GLIMPSE_LOOKUPS) void this.glimpse(node)
      else waiting++
    }
    this.reportProgress({ type: 'glimpses-waiting', n: waiting })
  }

  private async glimpse(node: GraphNode): Promise<void> {
    const gen = this.graphGen
    let merged = false
    this.filling.add(node.id)
    this.reportProgress({ type: 'glimpse-started' })
    const stopTimer = startTimer('glimpse')
    try {
      const result = await lookupWord(node.word)
      stopTimer({ word: node.word, stale: gen !== this.graphGen })
      if (gen !== this.graphGen) return // stale — the graph was replaced meanwhile
      // A click may have expanded it meanwhile; its lookup is still worth keeping.
      if (!this.expanded.has(node.id)) this.thesaurusGraph = mergeGlimpse(this.thesaurusGraph, node.id, result)
      this.glimpsed = new Map(this.glimpsed).set(node.id, result)
      const targets = new Set(this.fillTargets)
      targets.delete(node.id)
      this.fillTargets = targets
      merged = true
      this.reportProgress({ type: 'glimpse-done' })
    } catch (err) {
      console.warn('[mf-app] glimpse failed', { nodeId: node.id, word: node.word }, err)
      if (gen === this.graphGen) {
        this.fillFailed.add(node.id)
        this.reportProgress({ type: 'glimpse-failed' })
      }
    } finally {
      if (gen === this.graphGen) {
        this.filling.delete(node.id)
        this.pumpGlimpses()
        if (merged) this.glimpseBatch.arrive(this.filling.size > 0)
      }
    }
  }

  private handleRelationsChange(e: CustomEvent<{ hidden: ReadonlySet<RelationType> }>): void {
    this.hiddenRelations = e.detail.hidden
    console.debug('[mf-app] hidden relations', { hidden: [...this.hiddenRelations] })
    this.pumpGlimpses()
  }

  private handleWordNavigate(e: CustomEvent<{ word: string }>) {
    this.doLookup(e.detail.word)
  }

  // --- Metaphor forest ---

  /** Feed one event to the forest state machine, then run what the change
   *  implies: abort a superseded request, start a new one, recompose the graph
   *  when the forest changes, and recompute the lit paths. */
  private dispatchForest(event: ForestEvent): void {
    const prev = this.forestState
    const next = reduceForest(prev, event)
    if (next === prev) return
    this.forestState = next

    // Any seq move ends the request in flight: Cancel, or a new word.
    if (next.seq !== prev.seq && inFlight(prev)) this.reportProgress({ type: 'forest-ended', outcome: 'cancelled' })
    if (next.seq !== prev.seq && this.forestAbort) {
      console.debug('[forest] aborting superseded request', { word: prev.word, seq: prev.seq })
      this.forestAbort.abort()
      this.forestAbort = null
    }
    if (next.request.kind === 'loading' && next.seq !== prev.seq) void this.runForest(next)

    if (next.word !== prev.word) {
      // The forest belongs to its word: nothing of the old one fades or is reused.
      this.forestPool = new Map()
      this.forestMarks = { nodes: new Map(), links: new Map() }
    }
    const prevResponse = prev.content.kind === 'forest' ? prev.content.response : null
    const nextResponse = next.content.kind === 'forest' ? next.content.response : null
    const forestChanged = prevResponse !== nextResponse
    const streamChanged = streamPaths(prev) !== streamPaths(next)
    if (forestChanged) this.forestGraph = nextResponse ? forestToGraph(nextResponse, this.forestPool) : null
    if (forestChanged || streamChanged) this.updateStreamMarks()
    const target = litTarget(next)
    if (forestChanged || !sameTarget(target, this.forestLitTarget)) {
      this.forestLitTarget = target
      const lit = this.forestGraph ? litPaths(this.forestGraph, target) : null
      this.forestLit = lit && lit.size > 0 ? lit : null
    }
  }

  private async runForest(s: ForestState): Promise<void> {
    const { seq, word, maxHops } = s
    // A forest already on show means New forest: ask for one the server has
    // not served before rather than a cached one.
    const fresh = s.content.kind === 'forest'
    const controller = new AbortController()
    this.forestAbort = controller
    const started = performance.now()
    console.info('[forest] request', { word, maxHops, seq, fresh })
    this.reportProgress({ type: 'forest-started' })
    try {
      await streamForest(word, maxHops, event => {
        if (seq === this.forestState.seq) this.reportProgress({ type: 'forest-stream', event })
        const ms = Math.round(performance.now() - started)
        if (event.type === 'done') {
          console.info('[forest] response', { word, seq, endpoints: event.forest.endpoints.length, generated: event.forest.stats.generated, ms })
        } else if (event.type === 'error') {
          console.warn('[forest] stream failed', { word, seq, kind: event.kind, ms })
        } else {
          console.debug('[forest] stream event', { seq, type: event.type, path: 'pathId' in event ? event.pathId : undefined, ms })
        }
        this.dispatchForest({ type: 'stream', seq, event })
      }, controller.signal, fresh)
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        console.debug('[forest] request aborted', { word, seq })
      } else if (err instanceof ForestError) {
        console.warn('[forest] request failed', { word, seq, kind: err.kind, status: err.status })
        if (seq === this.forestState.seq) this.reportProgress({ type: 'forest-ended', outcome: 'failed' })
        this.dispatchForest({ type: 'failed', seq, error: err.kind, retryAfterSeconds: err.retryAfterSeconds })
      } else {
        console.error('[forest] unexpected failure', { word, seq }, err)
        if (seq === this.forestState.seq) this.reportProgress({ type: 'forest-ended', outcome: 'failed' })
        this.dispatchForest({ type: 'failed', seq, error: 'failed', retryAfterSeconds: null })
      }
    } finally {
      if (this.forestAbort === controller) this.forestAbort = null
    }
  }

  /** Recompute the streamed marks from the current paths and snapshot, carry
   *  dropped ones as fading (at once gone under reduced motion), and redraw. */
  private updateStreamMarks(): void {
    const live = streamMarks(streamPaths(this.forestState) ?? {}, this.forestGraph)
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
    const now = performance.now()
    this.forestMarks = fadeMarks(this.forestMarks, live, this.forestGraph, now, reduce ? 0 : FOREST_FADE_MS)
    if (this.forestFadeTimer) clearTimeout(this.forestFadeTimer)
    this.forestFadeTimer = null
    const end = nextFadeEnd(this.forestMarks)
    if (end !== null) {
      this.forestFadeTimer = setTimeout(() => {
        this.forestFadeTimer = null
        this.updateStreamMarks()
      }, Math.max(0, end - now) + 1)
    }
    this.recomposeGraph()
  }

  private reportProgress(event: ProgressEvent): void {
    this.progress = reduceProgress(this.progress, event)
  }

  private recomposeGraph(): void {
    this.glimpseBatch.cancel() // this composition carries any glimpses waiting for the batch
    const { data, overlay } = composeForest(this.thesaurusGraph, this.forestGraph, { marks: this.forestMarks, pool: this.forestPool })
    this.graphData = data
    this.forestOverlay = overlay
  }

  /** The forest node that carries the selection ring on the graph. */
  private get forestSelectedId(): string | null {
    const s = this.forestState.selection
    if (!s) return null
    return s.kind === 'node' ? s.id : s.kind === 'path' ? s.endpointId : s.target
  }

  private handleForestEvent(e: CustomEvent<ForestEvent>): void {
    this.dispatchForest(e.detail)
  }

  private handleForestTarget(type: 'hover' | 'select', e: CustomEvent<{ target: ForestTarget | null }>): void {
    this.dispatchForest({ type, target: e.detail.target })
  }

  private handleForestLookup(e: CustomEvent<{ word: string }>): void {
    this.doLookup(e.detail.word, { soft: true })
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
      // The browse surfaces unmount, so nothing can end a hover or focus.
      this.dispatchForest({ type: 'hover', target: null })
      this.dispatchForest({ type: 'focus', target: null })
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
    const storedView = localStorage.getItem('mf-grade-view')
    if (storedView === 'walk' || storedView === 'topic' || storedView === 'regrade' || storedView === 'sensecheck' || storedView === 'guided') this.gradeView = storedView
    try {
      const [topicsRes, notesRes, glossesRes] = await Promise.all([
        this.gradingClient.getTopics(),
        this.gradingClient.getDesignNotes(),
        this.gradingClient.getGlosses().catch(() => ({ glosses: {} })),
      ])
      this.gradeTopics = topicsRes.topics
      this.notesHistory = notesRes.content
      this.gradeGlosses = glossesRes.glosses
    } catch (err) {
      console.warn('[mf-app] initGradeMode failed', err)
      this.errorMessage = 'Failed to load grading data'
    }
    if (this.gradeView === 'walk') void this.initWalk()
    if (this.gradeView === 'guided') void this.initGuidedWalk()
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

  // --- Walk sub-mode ---

  /** Switch grade view (topic ↔ walk). Persisted so a reload returns the operator
   *  to where they were; entering the walk (re)fetches the acquisition order. */
  private setGradeView(view: 'topic' | 'walk' | 'regrade' | 'sensecheck' | 'guided'): void {
    this.gradeView = view
    localStorage.setItem('mf-grade-view', view)
    // Start each view clean; the walk repopulates selectedChain from its own list.
    // Re-grade is self-contained (owns its own sample + cursor + POSTs).
    this.selectedChain = null
    if (view === 'walk') void this.initWalk()
    if (view === 'guided') void this.initGuidedWalk()
  }

  /** Fetch the server-ordered walk and land on the first ungraded chain. Also load
   *  the GLOBAL verdict set so prior-verdict prefill + context-graph colouring work
   *  across topics (the walk is cross-topic; gradeJudgements is topic-scoped). */
  private async initWalk(): Promise<void> {
    try {
      const [walkRes, judgementsRes] = await Promise.all([
        this.gradingClient.getWalk(),
        this.gradingClient.getJudgements(),
      ])
      this.walkEntries = walkRes.entries
      this.walkJudgements = judgementsRes.records
      this.walkGradedSigs = new Set()
      this.walkPos = 0
      this.syncWalkSelection()
    } catch (err) {
      console.warn('[mf-app] initWalk failed', err)
      this.errorMessage = 'Failed to load walk'
    }
  }

  /** Verdicts the current grade view should resolve against: the global set while
   *  walking (cross-topic), the topic-scoped set in topic view. */
  private get activeJudgements(): JudgementRecord[] {
    if (this.gradeView === 'walk') return this.walkJudgements
    if (this.gradeView === 'guided') return this.guidedJudgements
    return this.gradeJudgements
  }

  /** The walk addresses the FULL ordered list (walkPos), not a filtered view. A
   *  graded chain stays in place so Prev can return to it; only forward motion
   *  (Next / auto-advance) skips graded chains. */
  private get walkCurrent(): WalkEntry | null {
    return this.walkEntries[this.walkPos] ?? null
  }

  private isWalkGraded(e: WalkEntry | null): boolean {
    return !!e && this.walkGradedSigs.has(e.chain_signature)
  }

  /** Next ungraded position strictly after `from` (or any next position when
   *  skip-graded is off); -1 if none ahead. */
  private nextUngradedPos(from: number): number {
    for (let i = from + 1; i < this.walkEntries.length; i++) {
      if (!this.walkSkipGraded || !this.isWalkGraded(this.walkEntries[i])) return i
    }
    return -1
  }

  private get canWalkPrev(): boolean {
    return this.walkPos > 0
  }

  private get canWalkNext(): boolean {
    return this.nextUngradedPos(this.walkPos) >= 0
  }

  /** Ungraded chains remaining in the whole walk (queue-progress readout). */
  private get walkUngradedRemaining(): number {
    return this.walkEntries.reduce((n, e) => n + (this.isWalkGraded(e) ? 0 : 1), 0)
  }

  /** Clamp walkPos into the full list and project the current entry onto
   *  selectedChain (which the panel + handleVerdictSubmit key off). */
  private syncWalkSelection(): void {
    if (this.walkEntries.length === 0) {
      this.walkPos = 0
      this.selectedChain = null
      return
    }
    this.walkPos = Math.max(0, Math.min(this.walkPos, this.walkEntries.length - 1))
    this.selectedChain = this.walkCurrent?.record ?? null
  }

  /** Forward to the next ungraded chain (fresh work) — disabled when none remain. */
  private walkNext(): void {
    const n = this.nextUngradedPos(this.walkPos)
    if (n >= 0) {
      this.walkPos = n
      this.syncWalkSelection()
    }
  }

  /** Literal step back — lands on the previous chain whether or not it is graded,
   *  so the operator can revisit what they just graded (verdict pre-fills). */
  private walkPrev(): void {
    if (this.walkPos > 0) {
      this.walkPos -= 1
      this.syncWalkSelection()
    }
  }

  private toggleWalkSkipGraded(): void {
    this.walkSkipGraded = !this.walkSkipGraded
  }

  /** Submit a verdict from the walk, then advance to the next ungraded chain.
   *  Reuses handleVerdictSubmit verbatim (POST + refetch); the graded chain stays
   *  in the list (Prev can revisit it) — only the forward cursor moves past it. */
  private async handleWalkVerdictSubmit(e: CustomEvent<VerdictSubmitDetail>): Promise<void> {
    const graded = this.selectedChain
    const recorded = await this.handleVerdictSubmit(e)
    // Auth expired (or no chain) — do not record or advance.
    if (!recorded || !graded) {
      this.syncWalkSelection()
      return
    }
    this.walkGradedSigs = new Set([...this.walkGradedSigs, graded.chain_signature])
    // Refresh the GLOBAL verdict set (handleVerdictSubmit only refetched the topic
    // scope into gradeJudgements) so prior-verdict echo + graph stay correct in walk.
    try {
      const jr = await this.gradingClient.getJudgements()
      this.walkJudgements = jr.records
    } catch (err) {
      console.warn('[mf-app] walk judgement refresh failed', err)
    }
    const n = this.nextUngradedPos(this.walkPos)
    if (n >= 0) this.walkPos = n   // else stay on the just-graded chain (all done — still reviewable)
    this.syncWalkSelection()
  }

  /** Stable single-element array for the desktop context graph — rebuilt only when
   *  the current chain's signature changes, so the graph re-frames on navigation
   *  but not on incidental re-renders. */
  private walkGraphChainsFor(record: ChainRecord | null): ChainRecord[] {
    const sig = record?.chain_signature ?? ''
    if (sig !== this._walkGraphSig) {
      this._walkGraphSig = sig
      this._walkGraphChains = record ? [record] : []
    }
    return this._walkGraphChains
  }

  // --- Guided walk (prefilled blind candidate list) ---------------------------
  // Mirrors the signal walk but with LITERAL Prev/Next (the order is fixed by the
  // prefill, not by triage) and no skip-graded — the operator walks every
  // candidate in the batch, in order.

  private async initGuidedWalk(): Promise<void> {
    try {
      const [guidedRes, judgementsRes] = await Promise.all([
        this.gradingClient.getGuidedWalk(),
        this.gradingClient.getJudgements(),
      ])
      this.guidedEntries = guidedRes.entries
      this.guidedBatch = guidedRes.batch
      this.guidedJudgements = judgementsRes.records
      this.guidedGradedSigs = new Set()
      this.guidedPos = 0
      this.syncGuidedSelection()
    } catch (err) {
      console.warn('[mf-app] initGuidedWalk failed', err)
      this.errorMessage = 'Failed to load guided walk'
    }
  }

  private get guidedCurrent(): GuidedEntry | null {
    return this.guidedEntries[this.guidedPos] ?? null
  }

  private isGuidedGraded(e: GuidedEntry | null): boolean {
    return !!e && this.guidedGradedSigs.has(e.chain_signature)
  }

  private get canGuidedPrev(): boolean {
    return this.guidedPos > 0
  }

  private get canGuidedNext(): boolean {
    return this.guidedPos < this.guidedEntries.length - 1
  }

  private get guidedUngradedRemaining(): number {
    return this.guidedEntries.reduce((n, e) => n + (this.isGuidedGraded(e) ? 0 : 1), 0)
  }

  private syncGuidedSelection(): void {
    if (this.guidedEntries.length === 0) {
      this.guidedPos = 0
      this.selectedChain = null
      return
    }
    this.guidedPos = Math.max(0, Math.min(this.guidedPos, this.guidedEntries.length - 1))
    this.selectedChain = this.guidedCurrent?.record ?? null
  }

  /** Literal forward step through the fixed candidate order (does NOT skip graded —
   *  the operator reviews every candidate in the batch). */
  private guidedNext(): void {
    if (this.guidedPos < this.guidedEntries.length - 1) {
      this.guidedPos += 1
      this.syncGuidedSelection()
    }
  }

  private guidedPrev(): void {
    if (this.guidedPos > 0) {
      this.guidedPos -= 1
      this.syncGuidedSelection()
    }
  }

  private async handleGuidedVerdictSubmit(e: CustomEvent<VerdictSubmitDetail>): Promise<void> {
    const graded = this.selectedChain
    const recorded = await this.handleVerdictSubmit(e)
    if (!recorded || !graded) {
      this.syncGuidedSelection()
      return
    }
    this.guidedGradedSigs = new Set([...this.guidedGradedSigs, graded.chain_signature])
    try {
      const jr = await this.gradingClient.getJudgements()
      this.guidedJudgements = jr.records
    } catch (err) {
      console.warn('[mf-app] guided judgement refresh failed', err)
    }
    // Literal advance — move to the next candidate in the fixed order (if any).
    if (this.guidedPos < this.guidedEntries.length - 1) this.guidedPos += 1
    this.syncGuidedSelection()
  }

  private guidedGraphChainsFor(record: ChainRecord | null): ChainRecord[] {
    const sig = record?.chain_signature ?? ''
    if (sig !== this._guidedGraphSig) {
      this._guidedGraphSig = sig
      this._guidedGraphChains = record ? [record] : []
    }
    return this._guidedGraphChains
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

  /** Topic ↔ Walk view toggle + on-demand signal report, shown in every grade view's top row. */
  private renderGradeViewToggle() {
    const opt = (view: 'topic' | 'walk' | 'regrade' | 'sensecheck' | 'guided', label: string) => html`
      <button
        data-testid="grade-view-${view}"
        aria-pressed=${this.gradeView === view}
        @click=${() => this.setGradeView(view)}
      >${label}</button>
    `
    return html`
      <div class="grade-view-toggle" role="group" aria-label="Grade view" data-testid="grade-view-toggle">
        ${opt('topic', 'By topic')}
        ${opt('walk', 'Walk')}
        ${opt('guided', 'Guided')}
        ${opt('regrade', 'Blind re-grade')}
        ${opt('sensecheck', 'Sense-check')}
      </div>
      <mf-signal-report .client=${this.gradingClient}></mf-signal-report>
    `
  }

  /** Returns true if the verdict was persisted OR queued for retry (i.e. recorded),
   *  false only when auth expired (caller should not advance). */
  private async handleVerdictSubmit(e: CustomEvent<VerdictSubmitDetail>): Promise<boolean> {
    if (!this.selectedChain) return false
    const chain = this.selectedChain
    const prior = this.priorVerdict(chain)
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
      tags: e.detail.tags,
      confidence: e.detail.confidence,
      notes: e.detail.notes,
      // Operator per-hop co-aptness ticks — dropping these here silently
      // destroys careful grading work (it did, once: batch 4, 2026-07-13).
      step_apt_senses: e.detail.step_apt_senses ?? [],
      supersedes_ts: prior?.ts ?? null,
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
      return true
    } catch (err: unknown) {
      const status = (err as { status?: number }).status ?? (err instanceof Error && err.message.includes('401') ? 401 : 0)
      if (status === 401 || (err instanceof Error && err.message.includes('401'))) {
        this.handleAuthExpired()
        return false
      }
      console.warn('[mf-app] handleVerdictSubmit failed', err)
      // Push to queue so the judgement is not lost; advance past this chain
      this.pendingQueue = [...this.pendingQueue, judgement]
      this.savePendingQueue()
      this.selectedChain = null
      this.errorMessage = `${this.pendingQueue.length} verdict${this.pendingQueue.length === 1 ? '' : 's'} pending — will retry on next save`
      return true
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
  ): { linkage: Linkage; metaphor: MetaphorVerdict; tiers: Tier[]; tags: Tag[]; confidence: Confidence; ts: string; notes: string } | null {
    let latest: JudgementRecord | null = null
    for (const j of this.activeJudgements) {
      if (j.chain_signature === chain.chain_signature) latest = j
    }
    if (!latest) return null
    const { linkage, metaphor, tiers, tags } = normaliseJudgement(latest)
    return {
      linkage: linkage ?? 'bad',
      metaphor: metaphor ?? 'irrelevant',
      tiers,
      tags,
      confidence: latest.confidence ?? 'high',
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

  /** Render the flat-text chain label for mobile cards. Shows the original
   *  phrases (phrase-as-node) so the grader sees the model's exact output, not
   *  just the snapped lemma — consistent with the grade-panel phrase-first rule. */
  private chainLabel(chain: ChainRecord): string {
    return chain.chain.map(s => s.phrase).join(' → ')
  }

  /** `soft` (lookups started from the forest): the search box changes only on
   *  success, and a 404 leaves the page as it was with a toast, because forest
   *  words are often phrases the thesaurus does not have.
   *  `history`: 'push' gives the new view its own entry, so Back returns to the
   *  one it replaces; 'replace' takes over an entry the browser already made.
   *  Resolves true when the new view is on screen. */
  private async doLookup(
    word: string,
    { soft = false, history: entry = 'push' }: { soft?: boolean; history?: 'push' | 'replace' } = {},
  ): Promise<boolean> {
    const id = ++this.lookupId
    if (!soft) this.currentWord = word
    this.appState = 'loading'
    this.errorMessage = ''
    this.reportProgress({ type: 'lookup-started', word })
    const stopTimer = startTimer('lookup')

    try {
      const result = await lookupWord(word)
      stopTimer({ word, stale: id !== this.lookupId })
      if (id !== this.lookupId) return false // stale — a newer lookup superseded this one
      this.saveView()
      this.undoToast?.hide() // its offer was about the view being replaced
      this.currentWord = word
      this.result = result
      const graph = transformLookupToGraph(result)
      const nodeIds = new Set(graph.nodes.map(n => n.id))
      const crossLinks = computeCrossLinks(result, nodeIds)
      ++this.graphGen // invalidate any in-flight expansion
      this.thesaurusGraph = { nodes: graph.nodes, links: [...graph.links, ...crossLinks] }
      this.expanded = new Map([[result.word, result]])
      this.expanding = new Set()
      this.glimpsed = new Map()
      this.fillTargets = new Set(graph.nodes.filter(n => n.relationType !== 'central').map(n => n.id))
      this.filling = new Set()
      this.fillFailed = new Set()
      this.lastClickedId = null
      this.dispatchForest({ type: 'word-committed', word: result.word })
      this.reportProgress({
        type: 'lookup-done', word: result.word, senses: result.senses.length,
        words: graph.nodes.length - 1, keepForest: inFlight(this.forestState),
      })
      this.recomposeGraph()
      this.appState = 'ready'
      this.enterView(word, entry)
      this.pumpGlimpses()
      void this.focusSource() // a Re-Centre may have aimed the camera elsewhere
      return true
    } catch (err) {
      stopTimer({ word, failed: true })
      if (id !== this.lookupId) return false // stale
      this.reportProgress({ type: 'lookup-failed', word })
      if (soft && this.result && err instanceof ApiError && err.status === 404) {
        console.info('[forest] forest word not in the thesaurus', { word })
        this.appState = 'ready'
        const toast = this.shadowRoot?.querySelector('mf-toast') as MfToast | null
        toast?.show(getString('forest-lookup-missing', { word }), 5000)
        return false
      }
      this.appState = 'error'
      if (err instanceof ApiError && err.status === 404) {
        this.errorMessage = getString('results-word-not-found', { word })
      } else {
        this.errorMessage = getString('error-generic')
      }
      return false
    }
  }

  private renderRecentre() {
    const node = this.lastClickedId ? this.thesaurusGraph.nodes.find(n => n.id === this.lastClickedId) : undefined
    if (!node || node.relationType === 'central') return ''
    return html`
      <button class="recentre" type="button" @click=${() => void this.recentre()}>
        <span class="recentre-glyph" aria-hidden="true">◎</span>${getString('recentre-button', { word: node.word })}
      </button>
    `
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

      ${this.appState === 'ready' ? this.renderRecentre() : ''}

      <mf-force-graph
        .graphData=${this.graphData}
        .hiddenRarities=${this.hiddenRarities}
        .hiddenRelations=${this.hiddenRelations}
        .forest=${this.forestOverlay}
        .forestVisible=${this.forestState.onGraph}
        .forestLit=${this.forestLit}
        .forestSelectedId=${this.forestSelectedId}
        .loading=${isBusy(this.progress)}
        @mf-node-select=${this.handleNodeSelect}
        @mf-node-navigate=${this.handleNodeNavigate}
        @mf-node-copy=${this.handleCopy}
        @mf-forest-hover=${(e: CustomEvent<{ target: ForestTarget | null }>) => this.handleForestTarget('hover', e)}
        @mf-forest-select=${(e: CustomEvent<{ target: ForestTarget | null }>) => this.handleForestTarget('select', e)}
      ></mf-force-graph>

      <mf-results-panel
        .result=${this.result}
        .hiddenRelations=${this.hiddenRelations}
        @mf-relations-change=${this.handleRelationsChange}
        @mf-word-navigate=${this.handleWordNavigate}
        @mf-word-copy=${this.handleCopy}
      ></mf-results-panel>

      ${this.result
        ? html`<mf-forest-panel
            class=${this.progressOpen ? 'progress-open' : ''}
            .state=${this.forestState}
            .lit=${this.forestLit}
            @mf-forest-event=${this.handleForestEvent}
            @mf-forest-lookup=${this.handleForestLookup}
          ></mf-forest-panel>`
        : ''}

      <mf-progress-panel
        .state=${this.progress}
        @mf-progress-toggle=${(e: CustomEvent<{ open: boolean }>) => { this.progressOpen = e.detail.open }}
      ></mf-progress-panel>

      <a class="source-link" href=${SOURCE_URL} target="_blank" rel="noopener noreferrer"
        aria-label="${getString('source-link')} ${getString('source-link-new-tab')}"
        title=${getString('source-link')}
        ><svg aria-hidden="true" viewBox="0 0 16 16" width="24" height="24"><path d=${GITHUB_MARK} /></svg></a>
    `
  }

  private renderGradeModeDesktop() {
    return html`
      <div class="grade-layout" data-testid="grade-layout">
        <div class="grade-top">
          ${this.renderGradeViewToggle()}
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
                  .glosses=${this.gradeGlosses}
                  .senseInventories=${this.senseInventories}
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
          ${this.renderGradeViewToggle()}
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
                .glosses=${this.gradeGlosses}
                .senseInventories=${this.senseInventories}
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

  /** Signal-prioritised walk: step through the server-ordered acquisition list.
   *  Desktop renders the current chain in graph context (single-chain context is
   *  the accepted v1 scope — the topic constellation is deferred); mobile shows the
   *  bare chain (the panel's own step render) with no force-graph element. */
  private renderGradeWalk() {
    const entry = this.walkCurrent
    const isDesktop = this.viewportWidth >= 900
    // The walk shell needs proper sizing or the head-chain clips: desktop → the
    // fixed-width, internally-scrolling .grade-panel-pane beside the graph; mobile →
    // a full-width scroll region (.grade-walk-scroll) directly under .grade-layout —
    // NOT .grade-main, whose row-flex + overflow:hidden (built for the desktop graph)
    // squeezes the width and clips the panel with no way to scroll.
    const shell = html`
      <mf-grade-walk
        data-testid="grade-walk"
        .chain=${entry?.record ?? null}
        .priorVerdict=${entry ? this.priorVerdict(entry.record) : null}
        .glosses=${this.gradeGlosses}
        .senseInventories=${this.senseInventories}
        .topic=${entry?.topic ?? ''}
        .index=${this.walkPos}
        .total=${this.walkEntries.length}
        .dwellIndex=${entry?.dwell_index ?? 0}
        .dwellN=${entry?.dwell_n ?? 0}
        .skipGraded=${this.walkSkipGraded}
        .canPrev=${this.canWalkPrev}
        .canNext=${this.canWalkNext}
        .graded=${this.isWalkGraded(entry)}
        .ungradedLeft=${this.walkUngradedRemaining}
        @walk-prev=${this.walkPrev}
        @walk-next=${this.walkNext}
        @walk-skip-toggle=${this.toggleWalkSkipGraded}
        @verdict-submit=${this.handleWalkVerdictSubmit}
      ></mf-grade-walk>`
    return html`
      <div class="grade-layout" data-testid="grade-walk-layout">
        <div class="grade-top">
          ${this.renderGradeViewToggle()}
        </div>

        ${entry === null
          ? html`<div class="grade-empty" data-testid="walk-empty">No chains in the walk — switch to By topic.</div>`
          : isDesktop
            ? html`
              <div class="grade-main">
                <div class="grade-graph-pane">
                  <mf-force-graph
                    .graphData=${this.graphData}
                    .mode=${'grade'}
                    .gradeChains=${this.walkGraphChainsFor(entry.record)}
                    .judgements=${this.walkJudgements}
                    .viewportWidth=${this.viewportWidth}
                  ></mf-force-graph>
                </div>
                <div class="grade-panel-pane">${shell}</div>
              </div>`
            : html`<div class="grade-walk-scroll">${shell}</div>`}
      </div>
    `
  }

  /** Guided walk view — the same shell as the signal walk (guided flag hides the
   *  dwell + skip affordances), driven by the prefilled candidate list with literal
   *  Prev/Next. Desktop shows the chain in graph context; mobile scrolls the panel. */
  private renderGradeGuidedWalk() {
    const entry = this.guidedCurrent
    const isDesktop = this.viewportWidth >= 900
    const shell = html`
      <mf-grade-walk
        data-testid="grade-guided"
        .guided=${true}
        .chain=${entry?.record ?? null}
        .priorVerdict=${this.guidedPrefill && entry ? this.priorVerdict(entry.record) : null
          /* BLIND by default: the server-side anchoring guard withholds
             judge_verdict/cohort — leaking the operator's own prior verdict
             re-anchors re-grade batches and inflates consistency. The prefill
             toggle is an explicit opt-in for amendment passes (e.g. re-ticking
             senses over already-graded chains). */}
        .prefillOn=${this.guidedPrefill}
        .glosses=${this.gradeGlosses}
        .senseInventories=${this.senseInventories}
        .topic=${entry?.topic ?? ''}
        .index=${this.guidedPos}
        .total=${this.guidedEntries.length}
        .canPrev=${this.canGuidedPrev}
        .canNext=${this.canGuidedNext}
        .graded=${this.isGuidedGraded(entry)}
        .ungradedLeft=${this.guidedUngradedRemaining}
        @walk-prev=${this.guidedPrev}
        @walk-next=${this.guidedNext}
        @walk-prefill-toggle=${() => { this.guidedPrefill = !this.guidedPrefill }}
        @verdict-submit=${this.handleGuidedVerdictSubmit}
      ></mf-grade-walk>`
    return html`
      <div class="grade-layout" data-testid="grade-guided-layout">
        <div class="grade-top">
          ${this.renderGradeViewToggle()}
          ${this.guidedBatch
            ? html`<span class="guided-batch" data-testid="guided-batch" title="active guided batch">batch: ${this.guidedBatch}</span>`
            : ''}
        </div>

        ${entry === null
          ? html`<div class="grade-empty" data-testid="guided-empty">No guided batch queued — tee one up server-side.</div>`
          : isDesktop
            ? html`
              <div class="grade-main">
                <div class="grade-graph-pane">
                  <mf-force-graph
                    .graphData=${this.graphData}
                    .mode=${'grade'}
                    .gradeChains=${this.guidedGraphChainsFor(entry.record)}
                    .judgements=${this.guidedJudgements}
                    .viewportWidth=${this.viewportWidth}
                  ></mf-force-graph>
                </div>
                <div class="grade-panel-pane">${shell}</div>
              </div>`
            : html`<div class="grade-walk-scroll">${shell}</div>`}
      </div>
    `
  }

  /** Blind re-grade view — its own top toggle row + the self-contained re-grade
   *  shell (owns sample/cursor/POSTs to the separate regrades file). */
  private renderGradeRegrade() {
    return html`
      <div class="grade-layout" data-testid="grade-regrade-layout">
        <div class="grade-top">
          ${this.renderGradeViewToggle()}
        </div>
        <div class="grade-walk-scroll">
          <mf-grade-regrade
            data-testid="grade-regrade"
            .client=${this.gradingClient}
            .glosses=${this.gradeGlosses}
          ></mf-grade-regrade>
        </div>
      </div>
    `
  }

  /** Sense-check view — its own toggle row + the self-contained sense-check shell
   *  (owns sample/cursor/POSTs to the separate sense-labels file). */
  private renderGradeSenseCheck() {
    return html`
      <div class="grade-layout" data-testid="grade-sensecheck-layout">
        <div class="grade-top">
          ${this.renderGradeViewToggle()}
        </div>
        <div class="grade-walk-scroll">
          <mf-grade-sensecheck
            data-testid="grade-sensecheck"
            .client=${this.gradingClient}
          ></mf-grade-sensecheck>
        </div>
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
        ? (this.gradeView === 'walk'
            ? this.renderGradeWalk()
            : this.gradeView === 'guided'
              ? this.renderGradeGuidedWalk()
              : this.gradeView === 'regrade'
                ? this.renderGradeRegrade()
                : this.gradeView === 'sensecheck'
                  ? this.renderGradeSenseCheck()
                  : (this.viewportWidth >= 900 ? this.renderGradeModeDesktop() : this.renderGradeModeMobile()))
        : this.renderBrowseMode()}

      <mf-toast></mf-toast>
      <mf-undo-toast .actionLabel=${getString('undo-action')} @mf-undo=${this.handleUndo}></mf-undo-toast>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'mf-app': MfApp
  }
}
