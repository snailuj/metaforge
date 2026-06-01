/* Grading Mode — App shell
   Browse ⇄ Grade, the gold top-right toggle mirroring the live app.
   GRADE: a queue of generated metaphors, filtered Both / Ungraded / Graded,
   graded keyboard-first (L/D/I · B · 1/2/3 · Enter saves & advances). The
   metaphor under review lights its path in the graph; previously graded
   metaphors leave faint coloured trails. BROWSE: the shipped thesaurus,
   same upgraded graph + results HUD, so the two modes share one visual world. */

const { useState: useAState, useEffect: useAEffect, useCallback, useMemo: useAMemo, useRef: useARef } = React;

const pk = (a, b) => (a < b ? a + '|' + b : b + '|' + a);

// colour-key for a metaphor's path edges, from its (working or committed) grade
function edgeKeyFor(grade) {
  if (!grade || !grade.metaphor) return 'active';        // under review → copper
  if (grade.linkage === 'bad') return 'dead';            // bad linkage → rose
  if (grade.metaphor === 'live') return 'live';          // good + live → green
  if (grade.metaphor === 'dead') return 'dead';          // dead figure → rose
  return 'irrelevant';                                   // irrelevant → muted
}
function pathPairs(path) {
  const out = [];
  for (let i = 0; i < path.length - 1; i++) out.push(pk(path[i], path[i + 1]));
  return out;
}

// adapt a lexicon lookup into the GraphForge graph shape (Browse mode)
function buildLexGraph(result, max = 16) {
  if (!result) return { nodes: [], links: [], central: '' };
  const nodes = [{ id: result.word, rarity: result.rarity }];
  const seen = new Set([result.word]);
  const links = [];
  let left = max - 1;
  const tiers = [['synonyms'], ['hyponyms'], ['hypernyms'], ['similar']];
  for (const sense of result.senses) {
    for (const [key] of tiers) {
      const list = key === 'synonyms' ? sense.synonyms : sense.relations[key];
      if (!list) continue;
      for (const rw of list) {
        if (left <= 0) break;
        if (seen.has(rw.word)) continue;
        seen.add(rw.word);
        nodes.push({ id: rw.word, rarity: rw.rarity });
        links.push({ source: result.word, target: rw.word });
        left--;
      }
    }
  }
  return { nodes, links, central: result.word };
}

function App() {
  const [mode, setMode] = useAState('grade');         // grade | browse
  const [theme, setTheme] = useAState('dark');
  const [filters, setFilters] = useAState({ common: true, unusual: true, rare: true });
  const [toast, setToast] = useAState({ message: '', visible: false });
  const toastTimer = useARef(null);

  // ---- GRADE state ----
  const queue = window.MF_FORGE.queue;
  const graph = window.MF_FORGE.graph;
  const targets = useAMemo(() => new Set(queue.map((m) => m.target)), [queue]);
  const [grades, setGrades] = useAState(() => {
    const g = {}; queue.forEach((m) => (g[m.id] = m.grade ? { ...m.grade } : null)); return g;
  });
  const [qfilter, setQfilter] = useAState('both');    // both | ungraded | graded
  const [idx, setIdx] = useAState(0);
  const [draft, setDraft] = useAState({});

  const filtered = useAMemo(() => queue.filter((m) => {
    if (qfilter === 'ungraded') return !grades[m.id];
    if (qfilter === 'graded') return !!grades[m.id];
    return true;
  }), [queue, grades, qfilter]);

  const current = filtered[Math.min(idx, Math.max(0, filtered.length - 1))] || null;

  // seed the draft whenever the current item changes
  useAEffect(() => {
    if (!current) { setDraft({}); return; }
    const committed = grades[current.id];
    setDraft(committed ? { ...committed, tags: [...(committed.tags || [])] } : { tags: [] });
  }, [current && current.id]);

  const showToast = useCallback((msg) => {
    setToast({ message: msg, visible: true });
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast((t) => ({ ...t, visible: false })), 1500);
  }, []);

  const setAxis = useCallback((axis, val) => setDraft((d) => ({ ...d, [axis]: val })), []);
  const toggleTag = useCallback((tag) => setDraft((d) => {
    const tags = d.tags || [];
    return { ...d, tags: tags.includes(tag) ? tags.filter((t) => t !== tag) : [...tags, tag] };
  }), []);
  const setNote = useCallback((v) => setDraft((d) => ({ ...d, note: v })), []);

  const advance = useCallback(() => {
    setIdx((i) => {
      // prefer next still-ungraded item in the filtered list; else next; else clamp
      for (let step = 1; step <= filtered.length; step++) {
        const j = (i + step) % filtered.length;
        if (qfilter !== 'graded' && !grades[filtered[j].id]) return j;
      }
      return Math.min(i + 1, filtered.length - 1);
    });
  }, [filtered, grades, qfilter]);

  const commit = useCallback(() => {
    if (!current || !draft.metaphor) return;
    const stamped = { ...draft, linkage: draft.linkage || 'good', at: new Date().toISOString() };
    setGrades((g) => ({ ...g, [current.id]: stamped }));
    showToast(`Graded "${current.source} → ${current.target}"`);
    advance();
  }, [current, draft, advance, showToast]);

  const skip = useCallback(() => { showToast('Skipped'); advance(); }, [advance, showToast]);
  const go = useCallback((delta) => setIdx((i) => Math.max(0, Math.min(filtered.length - 1, i + delta))), [filtered.length]);

  useAEffect(() => { setIdx(0); }, [qfilter]);

  // ---- keyboard (grade mode) ----
  useAEffect(() => {
    if (mode !== 'grade') return;
    const onKey = (e) => {
      const a = document.activeElement;
      if (a && (a.tagName === 'TEXTAREA' || a.tagName === 'INPUT')) {
        if (e.key === 'Escape') a.blur();
        return;
      }
      const k = e.key.toLowerCase();
      if (k === 'l') { setAxis('metaphor', 'live'); }
      else if (k === 'd') { setAxis('metaphor', 'dead'); }
      else if (k === 'i') { setAxis('metaphor', 'irrelevant'); }
      else if (k === 'b') { setDraft((dr) => ({ ...dr, linkage: dr.linkage === 'bad' ? 'good' : 'bad' })); }
      else if (k === '1') { setAxis('confidence', 'high'); }
      else if (k === '2') { setAxis('confidence', 'med'); }
      else if (k === '3') { setAxis('confidence', 'low'); }
      else if (k === 's') { skip(); }
      else if (e.key === 'Enter') { e.preventDefault(); commit(); }
      else if (e.key === 'ArrowRight' || k === 'k') { go(1); }
      else if (e.key === 'ArrowLeft' || k === 'j') { go(-1); }
      else return;
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [mode, setAxis, skip, commit, go]);

  // edge tints for the graph
  const { pathEdges, trailEdges } = useAMemo(() => {
    const pe = {}, te = {};
    queue.forEach((m) => {
      const committed = grades[m.id];
      const isCurrent = current && m.id === current.id;
      if (isCurrent) {
        const key = edgeKeyFor(draft && draft.metaphor ? draft : (committed || {}));
        pathPairs(m.path).forEach((p) => (pe[p] = key));
      } else if (committed) {
        const key = edgeKeyFor(committed);
        pathPairs(m.path).forEach((p) => { if (!(p in te)) te[p] = key; });
      }
    });
    return { pathEdges: pe, trailEdges: te };
  }, [queue, grades, current && current.id, draft, mode]);

  const gradedCount = useAMemo(() => queue.filter((m) => grades[m.id]).length, [queue, grades]);

  // ---- BROWSE state ----
  const [bResult, setBResult] = useAState(() => window.MF_LEXICON.lookup('hungriness'));
  const [collapsed, setCollapsed] = useAState(false);
  const onCopy = useCallback((word) => {
    if (navigator.clipboard) navigator.clipboard.writeText(word).catch(() => {});
    showToast(`Copied "${word}"`);
  }, [showToast]);
  const doLookup = useCallback((word) => {
    const r = window.MF_LEXICON.lookup(word);
    if (r) setBResult(r); else showToast(`"${word}" was not found`);
  }, [showToast]);
  const bGraph = useAMemo(() => buildLexGraph(bResult), [bResult]);

  const toggleFilter = useCallback((key) => setFilters((f) => ({ ...f, [key]: !f[key] })), []);

  return (
    <div data-theme={theme} style={appStyles.themeWrap}>
     <div style={appStyles.root}>
      {/* mode toggle — top-right, mirrors the live app */}
      <div style={appStyles.topRight}>
        <div style={appStyles.themeToggle}>
          {[['dark', 'Dark'], ['parchment', 'Parchment']].map(([key, label]) => (
            <button key={key} onClick={() => setTheme(key)} style={{ ...appStyles.themeBtn,
              color: theme === key ? 'var(--colour-bg-primary)' : 'var(--colour-text-secondary)',
              background: theme === key ? 'var(--colour-accent-gold)' : 'transparent' }}>{label}</button>
          ))}
        </div>
        <button style={appStyles.modeBtn} onClick={() => setMode((m) => (m === 'grade' ? 'browse' : 'grade'))}>
          {mode === 'grade' ? 'Browse mode' : 'Grade mode'}
        </button>
      </div>

      {/* graph behind everything */}
      {mode === 'grade'
        ? <GraphForge graph={graph} filters={filters} targets={targets} pathEdges={pathEdges} trailEdges={trailEdges} onNavigate={(w) => onCopy(w)} onCopy={onCopy} />
        : <GraphForge graph={bGraph} filters={filters} targets={new Set()} onNavigate={doLookup} onCopy={onCopy} dimmed={false} />}

      {/* search (browse only) */}
      {mode === 'browse' && (
        <div style={appStyles.searchContainer}>
          <SearchBar value={bResult ? bResult.word : ''} onSearch={doLookup} />
        </div>
      )}

      {/* rarity filters — shared */}
      <div style={mode === 'browse' ? appStyles.filtersBrowse : appStyles.filtersGrade}>
        <RarityFilters filters={filters} onToggle={toggleFilter} />
      </div>

      {/* GRADE chrome */}
      {mode === 'grade' && (
        <React.Fragment>
          <div style={appStyles.queueBar}>
            <div style={appStyles.segFilter}>
              {[['both', 'Both'], ['ungraded', 'Ungraded'], ['graded', 'Graded']].map(([key, label]) => (
                <button key={key} onClick={() => setQfilter(key)} style={{ ...appStyles.filterBtn,
                  color: qfilter === key ? 'var(--colour-bg-primary)' : 'var(--colour-text-secondary)',
                  background: qfilter === key ? 'var(--colour-accent-gold)' : 'transparent' }}>{label}</button>
              ))}
            </div>
            <div style={appStyles.progress}>
              <span style={{ color: 'var(--colour-accent-gold)' }}>{gradedCount}</span>
              <span> / {queue.length} graded</span>
            </div>
          </div>

          {current ? (
            <GradingPanel
              item={current}
              grade={draft}
              regrading={grades[current.id] || null}
              onSet={setAxis}
              onToggleTag={toggleTag}
              onNote={setNote}
              onCommit={commit}
              onSkip={skip}
            />
          ) : (
            <div style={appStyles.emptyPanel}>Nothing here — every metaphor in this filter is done.</div>
          )}
        </React.Fragment>
      )}

      {/* BROWSE chrome */}
      {mode === 'browse' && bResult && (
        <ResultsPanel result={bResult} collapsed={collapsed} onToggle={() => setCollapsed((c) => !c)} onNavigate={doLookup} onCopy={onCopy} />
      )}

      <Toast message={toast.message} visible={toast.visible} />
     </div>
    </div>
  );
}

const appStyles = {
  themeWrap: { position: 'absolute', inset: 0, overflow: 'hidden' },
  root: { position: 'absolute', inset: 0, width: '100%', height: '100%', overflow: 'hidden', background: 'var(--colour-bg-primary)' },
  topRight: { position: 'absolute', top: '1rem', right: '1rem', zIndex: 35, display: 'flex', alignItems: 'center', gap: '0.5rem' },
  themeToggle: { display: 'flex', gap: 2, padding: 3, background: 'var(--colour-bg-hud)', border: '1px solid var(--hairline)', borderRadius: 'var(--hud-radius)', backdropFilter: 'var(--hud-blur)' },
  themeBtn: { fontFamily: "'Crimson Text', serif", fontSize: '0.78rem', padding: '3px 11px', border: 'none', borderRadius: 3, cursor: 'pointer', transition: 'all 0.15s' },
  modeBtn: { fontFamily: "'Crimson Text', serif", fontSize: '0.85rem', whiteSpace: 'nowrap', padding: '0.42rem 0.9rem', borderRadius: 'var(--hud-radius)', border: '1px solid var(--colour-accent-gold)', background: 'var(--wash-gold)', color: 'var(--colour-accent-gold)', cursor: 'pointer', backdropFilter: 'var(--hud-blur)' },
  searchContainer: { position: 'absolute', top: '1rem', left: '50%', transform: 'translateX(-50%)', width: 'min(480px, calc(100% - 2rem))', zIndex: 30 },
  filtersBrowse: { position: 'absolute', top: 'calc(1rem + 56px)', left: '50%', transform: 'translateX(-50%)', zIndex: 15 },
  filtersGrade: { position: 'absolute', bottom: '2rem', left: '1rem', zIndex: 15 },
  queueBar: { position: 'absolute', top: '1rem', left: '1rem', zIndex: 30, display: 'flex', flexDirection: 'column', gap: '0.5rem' },
  segFilter: { display: 'flex', gap: 2, padding: 3, background: 'var(--colour-bg-hud)', border: '1px solid var(--hairline)', borderRadius: 'var(--hud-radius)', backdropFilter: 'var(--hud-blur)', width: 'fit-content' },
  filterBtn: { fontFamily: "'Crimson Text', serif", fontSize: '0.82rem', padding: '4px 13px', border: 'none', borderRadius: 3, cursor: 'pointer', transition: 'all 0.15s' },
  progress: { fontFamily: "'Crimson Text', serif", fontSize: '0.85rem', color: 'var(--colour-text-secondary)', paddingLeft: '0.3rem' },
  emptyPanel: { position: 'absolute', top: 'calc(1rem + 3.5rem)', right: '1rem', width: '23rem', zIndex: 20, padding: '1rem', background: 'var(--colour-bg-hud)', border: '1px solid var(--hairline)', borderRadius: 'var(--hud-radius)', backdropFilter: 'var(--hud-blur)', fontFamily: "'Crimson Text', serif", color: 'var(--colour-text-secondary)', fontSize: '0.95rem' },
};

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
