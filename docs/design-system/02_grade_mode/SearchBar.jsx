/* Metaforge UI Kit — SearchBar
   Frosted input, "/" shortcut hint, autocomplete dropdown. */
const { useState, useRef, useEffect } = React;

const RARITY_VAR = {
  common: 'var(--colour-rarity-common)',
  unusual: 'var(--colour-rarity-unusual)',
  rare: 'var(--colour-rarity-rare)',
};
const rarityWash = (k) => `color-mix(in srgb, ${RARITY_VAR[k]} 18%, transparent)`;

function SearchBar({ value, onSearch }) {
  const [text, setText] = useState(value || '');
  const [suggestions, setSuggestions] = useState([]);
  const [sel, setSel] = useState(-1);
  const [focused, setFocused] = useState(false);
  const inputRef = useRef(null);

  useEffect(() => { setText(value || ''); }, [value]);

  // global "/" focuses the input
  useEffect(() => {
    const onKey = (e) => {
      if (e.key !== '/') return;
      const a = document.activeElement;
      if (a && (a.tagName === 'INPUT' || a.tagName === 'TEXTAREA')) return;
      e.preventDefault();
      inputRef.current && inputRef.current.focus();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, []);

  function handleInput(e) {
    const v = e.target.value;
    setText(v);
    const next = v.trim().length >= 1 ? window.MF_LEXICON.suggest(v) : [];
    setSuggestions(next);
    setSel(-1);
  }

  function choose(word) {
    setSuggestions([]);
    setSel(-1);
    setText(word);
    onSearch(word);
    inputRef.current && inputRef.current.blur();
  }

  function handleKeyDown(e) {
    if (e.key === 'ArrowDown' && suggestions.length) {
      e.preventDefault();
      setSel((s) => (s + 1) % suggestions.length);
    } else if (e.key === 'ArrowUp' && suggestions.length) {
      e.preventDefault();
      setSel((s) => (s <= 0 ? suggestions.length - 1 : s - 1));
    } else if (e.key === 'Enter') {
      if (sel >= 0 && suggestions[sel]) choose(suggestions[sel].word);
      else if (text.trim()) choose(text.trim().toLowerCase());
    } else if (e.key === 'Escape') {
      setSuggestions([]); setSel(-1); setText(''); inputRef.current.blur();
    }
  }

  const open = focused && suggestions.length > 0;

  return (
    <div style={searchBarStyles.wrap}>
      <div style={{ ...searchBarStyles.bar, borderRadius: open ? 'var(--hud-radius) var(--hud-radius) 0 0' : 'var(--hud-radius)' }}>
        <input
          ref={inputRef}
          style={searchBarStyles.input}
          placeholder="Search for a word…"
          value={text}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          onFocus={() => setFocused(true)}
          onBlur={() => setTimeout(() => setFocused(false), 150)}
          aria-label="Search the thesaurus"
        />
        <span style={searchBarStyles.hint}>/</span>
      </div>
      {open && (
        <ul style={searchBarStyles.list}>
          {suggestions.map((s, i) => (
            <li
              key={s.word}
              style={{ ...searchBarStyles.item, background: i === sel ? 'var(--wash-gold)' : 'transparent' }}
              onMouseEnter={() => setSel(i)}
              onMouseDown={(e) => { e.preventDefault(); choose(s.word); }}
            >
              <div style={searchBarStyles.itemTop}>
                <span style={searchBarStyles.word}>{s.word}</span>
                {s.sense_count > 1 && <span style={searchBarStyles.senseBadge}>{s.sense_count} senses</span>}
                <span style={{ ...searchBarStyles.rarityBadge, color: RARITY_VAR[s.rarity], background: rarityWash(s.rarity) }}>{s.rarity}</span>
              </div>
              <div style={searchBarStyles.def}>{s.definition}</div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

const searchBarStyles = {
  wrap: { position: 'relative', width: '100%' },
  bar: {
    display: 'flex', alignItems: 'center', gap: 8, padding: '10px 16px',
    background: 'var(--colour-bg-hud)', border: '1px solid var(--hairline)',
    backdropFilter: 'var(--hud-blur)', WebkitBackdropFilter: 'var(--hud-blur)',
  },
  input: {
    flex: 1, background: 'transparent', border: 'none', outline: 'none',
    color: 'var(--colour-text-primary)', fontFamily: "'Crimson Text', serif", fontSize: '1.1rem',
  },
  hint: { color: 'var(--colour-text-muted)', fontSize: '0.75rem', fontFamily: "'JetBrains Mono', monospace" },
  list: {
    position: 'absolute', top: '100%', left: 0, right: 0, margin: 0, padding: 0,
    listStyle: 'none', background: 'var(--colour-bg-hud-solid)', border: '1px solid var(--hairline)',
    borderTop: 'none', borderRadius: '0 0 var(--hud-radius) var(--hud-radius)', backdropFilter: 'var(--hud-blur)',
    maxHeight: '20rem', overflowY: 'auto', zIndex: 40,
  },
  item: { display: 'flex', flexDirection: 'column', gap: '0.15rem', padding: '0.5rem 1rem', cursor: 'pointer', borderBottom: '1px solid var(--hairline-soft)' },
  itemTop: { display: 'flex', alignItems: 'center', gap: '0.5rem' },
  word: { color: 'var(--colour-text-primary)', fontWeight: 600, fontSize: '1rem', fontFamily: "'Crimson Text', serif" },
  senseBadge: { color: 'var(--colour-text-muted)', fontSize: '0.7rem', background: 'var(--wash-gold-soft)', padding: '0.05rem 0.35rem', borderRadius: 3 },
  rarityBadge: { fontSize: '0.65rem', padding: '0.05rem 0.35rem', borderRadius: 3, textTransform: 'uppercase', letterSpacing: '0.03em' },
  def: { color: 'var(--colour-text-muted)', fontSize: '0.8rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', fontFamily: "'Crimson Text', serif" },
};

window.SearchBar = SearchBar;
