/* Metaforge UI Kit — App shell.
   Wires search → lookup → graph + results panel, with rarity filters,
   loading/idle/error states, and copy toasts. Faithful to mf-app.ts. */
const { useState: useAState, useCallback } = React;

function App() {
  const [state, setState] = useAState('idle'); // idle | loading | ready | error
  const [result, setResult] = useAState(null);
  const [error, setError] = useAState('');
  const [collapsed, setCollapsed] = useAState(false);
  const [filters, setFilters] = useAState({ common: true, unusual: true, rare: true });
  const [theme, setTheme] = useAState('dark');
  const [toast, setToast] = useAState({ message: '', visible: false });
  const toastTimer = React.useRef(null);

  const showToast = useCallback((msg) => {
    setToast({ message: msg, visible: true });
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast((t) => ({ ...t, visible: false })), 1500);
  }, []);

  const doLookup = useCallback((word) => {
    setState('loading');
    setError('');
    // simulate the <100ms API round-trip
    setTimeout(() => {
      const r = window.MF_LEXICON.lookup(word);
      if (!r) {
        setState('error');
        setError(`"${word}" was not found in the thesaurus.`);
        return;
      }
      setResult(r);
      setState('ready');
    }, 260);
  }, []);

  const onCopy = useCallback((word) => {
    if (navigator.clipboard) navigator.clipboard.writeText(word).catch(() => {});
    showToast(`Copied "${word}"`);
  }, [showToast]);

  const toggleFilter = useCallback((key) => {
    setFilters((f) => ({ ...f, [key]: !f[key] }));
  }, []);

  return (
    <div data-theme={theme} style={appStyles.root}>
      {/* theme switcher — top-right (Settings position) */}
      <div style={appStyles.themeToggle}>
        {[['dark', 'Dark'], ['parchment', 'Parchment']].map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTheme(key)}
            style={{
              ...appStyles.themeBtn,
              color: theme === key ? 'var(--colour-bg-primary)' : 'var(--colour-text-secondary)',
              background: theme === key ? 'var(--colour-accent-gold)' : 'transparent',
            }}
          >{label}</button>
        ))}
      </div>

      {/* graph behind everything */}
      {state === 'ready' && (
        <WordGraph result={result} filters={filters} onNavigate={doLookup} onCopy={onCopy} />
      )}

      {/* search */}
      <div style={appStyles.searchContainer}>
        <SearchBar value={result ? result.word : ''} onSearch={doLookup} />
      </div>

      {/* rarity filters */}
      {state === 'ready' && (
        <div style={appStyles.filters}>
          <RarityFilters filters={filters} onToggle={toggleFilter} />
        </div>
      )}

      {/* status messages */}
      {state === 'idle' && (
        <div style={appStyles.status}>
          <div style={appStyles.idleText}>Type a word to explore</div>
          <div style={appStyles.examples}>
            try{' '}
            {window.MF_LEXICON.examples.map((w, i) => (
              <React.Fragment key={w}>
                <span style={appStyles.exampleLink} onClick={() => doLookup(w)}>{w}</span>
                {i < window.MF_LEXICON.examples.length - 1 ? ' · ' : ''}
              </React.Fragment>
            ))}
          </div>
        </div>
      )}
      {state === 'loading' && (
        <div style={appStyles.status}>
          <div style={appStyles.ring} />
          <div style={appStyles.idleText}>Looking up…</div>
        </div>
      )}
      {state === 'error' && (
        <div style={{ ...appStyles.status, color: '#c47a7a' }}>{error}</div>
      )}

      {/* results panel */}
      {state === 'ready' && (
        <ResultsPanel
          result={result}
          collapsed={collapsed}
          onToggle={() => setCollapsed((c) => !c)}
          onNavigate={doLookup}
          onCopy={onCopy}
        />
      )}

      <Toast message={toast.message} visible={toast.visible} />
    </div>
  );
}

const appStyles = {
  root: { position: 'absolute', inset: 0, width: '100%', height: '100%', overflow: 'hidden', background: 'var(--colour-bg-primary)', transition: 'background 0.3s ease' },
  themeToggle: { position: 'absolute', top: '1rem', right: '1rem', zIndex: 35, display: 'flex', gap: 2, padding: 3, background: 'var(--colour-bg-hud)', border: '1px solid var(--hairline)', borderRadius: 'var(--hud-radius)', backdropFilter: 'var(--hud-blur)' },
  themeBtn: { fontFamily: "'Crimson Text', serif", fontSize: '0.8rem', padding: '3px 12px', border: 'none', borderRadius: 3, cursor: 'pointer', transition: 'all 0.15s' },
  searchContainer: { position: 'absolute', top: '1rem', left: '50%', transform: 'translateX(-50%)', width: 'min(480px, calc(100% - 2rem))', zIndex: 30 },
  filters: { position: 'absolute', top: 'calc(1rem + 56px)', left: '50%', transform: 'translateX(-50%)', zIndex: 15 },
  status: { position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%,-50%)', color: 'var(--colour-text-muted)', fontFamily: "'Crimson Text', serif", fontSize: '1.1rem', textAlign: 'center', zIndex: 5 },
  idleText: { color: 'var(--colour-text-muted)', fontSize: '1.1rem' },
  examples: { marginTop: '0.75rem', fontSize: '0.95rem', color: 'var(--colour-text-secondary)' },
  exampleLink: { color: 'var(--colour-rarity-unusual)', cursor: 'pointer', borderBottom: '1px dotted color-mix(in srgb, var(--colour-rarity-unusual) 40%, transparent)' },
  ring: { width: 40, height: 40, border: '3px solid var(--colour-accent-gold-dim)', borderTopColor: 'var(--colour-accent-gold)', borderRadius: '50%', animation: 'mfspin 1s linear infinite', margin: '0 auto 1rem' },
};

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
