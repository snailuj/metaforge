import markup from './page.html?raw'
import { runAll, FULL_TIMING, QUICK_TIMING, type RunStatus } from './runner'
import { buildReport, type DeviceFacts } from './report'
import { verdict, describeVerdict, FRAME_BUDGET_MS, JITTER_ALLOWANCE_MS, PASS_LIMIT_MS } from './verdict'
import type { Results } from './results'

// The glow speed test page. Nothing in the main app imports this file.

function byId<T extends HTMLElement>(id: string): T {
  const el = document.getElementById(id)
  if (!el) throw new Error(`glow speed test: #${id} is missing from the page`)
  return el as T
}

const ms = (v: number) => v.toFixed(2)

function cell(text: string, className?: string): HTMLTableCellElement {
  const td = document.createElement('td')
  td.textContent = text
  if (className) td.className = className
  return td
}

function row(...cells: HTMLTableCellElement[]): HTMLTableRowElement {
  const tr = document.createElement('tr')
  tr.append(...cells)
  return tr
}

function statusText(s: RunStatus): string {
  const seconds = Math.ceil(s.remainingMs / 1000)
  if (s.phase === 'scaling') return `Step ${s.step} of ${s.steps}: ${s.label}.`
  const what = s.phase === 'warm-up' ? 'warming up' : 'measuring'
  return `Step ${s.step} of ${s.steps}: ${s.label}, ${what}, ${seconds} s left.`
}

function init(): void {
  const root = byId('perf-root')
  // The single-file build writes the markup into the page; the dev page does not.
  if (!root.firstElementChild) root.innerHTML = markup

  const canvas = byId<HTMLCanvasElement>('stage')
  const runButton = byId<HTMLButtonElement>('run')
  const copyButton = byId<HTMLButtonElement>('copy')
  const status = byId('status')
  const resultsEl = byId('results')
  const interruptedEl = byId('interrupted')
  const verdictEl = byId('verdict')
  const passNote = byId('pass-note')
  const runRows = byId('run-rows')
  const scalingRows = byId('scaling-rows')
  const copyStatus = byId('copy-status')
  const fallback = byId<HTMLTextAreaElement>('fallback')

  const quick = new URLSearchParams(location.search).get('quick') === '1'
  const timing = quick ? QUICK_TIMING : FULL_TIMING
  let reportText = ''
  let running = false

  const setStatus = (text: string) => {
    // Only touch the live region when the words change, which is once a second.
    if (status.textContent !== text) status.textContent = text
  }

  function showResults(results: Results, facts: DeviceFacts, interrupted: boolean): void {
    const v = verdict(results.runs)
    interruptedEl.hidden = !interrupted
    verdictEl.textContent = interrupted
      ? 'No verdict: the test was interrupted before every run finished.'
      : `${describeVerdict(v)} Physics takes ${(v.physicsShare * 100).toFixed(1)}% of a ${FRAME_BUDGET_MS} ms frame.`
    passNote.textContent =
      `A run passes when its frame-interval 95th percentile is at most ${PASS_LIMIT_MS.toFixed(1)} ms ` +
      `(${FRAME_BUDGET_MS} ms plus ${JITTER_ALLOWANCE_MS.toFixed(1)} ms for timer jitter).`

    runRows.replaceChildren(...results.runs.map(r => {
      const name = cell(r.label)
      const note = document.createElement('small')
      const judged = r.id !== 'none'
      const passed = r.interval.p95 <= PASS_LIMIT_MS
      note.textContent = judged ? (passed ? 'within the limit' : 'over the limit') : 'reference'
      name.append(note)
      return row(
        name,
        cell(ms(r.interval.median)),
        cell(ms(r.interval.p95), judged && !passed ? 'fail' : undefined),
        cell(`${(r.interval.overBudgetShare * 100).toFixed(1)}%`),
        cell(ms(r.physics.median)),
        cell(ms(r.draw.median)),
      )
    }))
    scalingRows.replaceChildren(...results.scaling.map(s =>
      row(cell(String(s.nodes)), cell(String(s.edges)), cell(ms(s.physics.median)), cell(ms(s.physics.p95)))))

    const report = buildReport(results, facts)
    reportText = interrupted
      ? `INTERRUPTED: the tab was hidden during a run. Results are partial; ignore the verdict line.\n${report}`
      : report
    fallback.hidden = true
    copyStatus.textContent = ''
    resultsEl.hidden = false
    resultsEl.focus()
  }

  async function start(): Promise<void> {
    if (running) return
    running = true
    runButton.disabled = true
    resultsEl.hidden = true
    fallback.hidden = true
    setStatus('Starting.')

    const controller = new AbortController()
    const onVisibility = () => {
      if (!document.hidden) return
      controller.abort()
      setStatus('Interrupted: the tab was hidden.')
    }
    document.addEventListener('visibilitychange', onVisibility)

    let wakeLock: WakeLockSentinel | null = null
    try {
      wakeLock = (await navigator.wakeLock?.request('screen')) ?? null
    } catch (err) {
      console.warn('[glow test] screen wake lock refused; the screen may dim during the runs', err)
    }

    let backingStore = { width: 0, height: 0 }
    try {
      const ctx = canvas.getContext('2d')
      if (!ctx) throw new Error('This browser did not give a 2D canvas context.')
      const outcome = await runAll({
        deps: { now: () => performance.now(), requestFrame: cb => requestAnimationFrame(cb) },
        devicePixelRatio: window.devicePixelRatio || 1,
        signal: controller.signal,
        onStatus: s => setStatus(statusText(s)),
        prepareSurface: pixelRatio => {
          const rect = canvas.getBoundingClientRect()
          canvas.width = Math.round(rect.width * pixelRatio)
          canvas.height = Math.round(rect.height * pixelRatio)
          if (backingStore.width === 0) backingStore = { width: canvas.width, height: canvas.height }
          return { ctx, width: rect.width, height: rect.height, pixelRatio }
        },
      }, timing)
      setStatus(outcome.interrupted ? 'Interrupted. Partial results below.' : 'Done. Results below.')
      showResults(outcome.results, {
        isoDate: new Date().toISOString(),
        pixelRatio: window.devicePixelRatio || 1,
        viewport: { width: window.innerWidth, height: window.innerHeight },
        backingStore,
        userAgent: navigator.userAgent,
      }, outcome.interrupted)
    } catch (err) {
      console.error('[glow test] the run failed', err)
      setStatus(`The test failed: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      document.removeEventListener('visibilitychange', onVisibility)
      wakeLock?.release().catch(err => console.warn('[glow test] wake lock release failed', err))
      runButton.textContent = 'Run again'
      runButton.disabled = false
      running = false
    }
  }

  function showFallback(): void {
    fallback.value = reportText
    fallback.hidden = false
    fallback.focus()
    fallback.select()
    copyStatus.textContent = 'Copying was blocked. The text is selected below; copy it by hand.'
  }

  runButton.addEventListener('click', () => void start())
  // writeText must be called inside the click handler to keep the user gesture.
  copyButton.addEventListener('click', () => {
    let attempt: Promise<void>
    try {
      attempt = navigator.clipboard.writeText(reportText)
    } catch (err) {
      attempt = Promise.reject(err) // no clipboard at all, as on an insecure page
    }
    attempt.then(
      () => { copyStatus.textContent = 'Copied.' },
      err => {
        console.warn('[glow test] clipboard write refused', err)
        showFallback()
      },
    )
  })
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init)
else init()
