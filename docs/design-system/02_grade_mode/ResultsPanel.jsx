/* Metaforge UI Kit — ResultsPanel
   The signature HUD: word title + rarity badge, then one block per sense
   (POS, meta badges, definition, usage example, colour-coded word chips).
   Chips: click to look up, right-click to copy. */

const CHIP_COLOURS = {
  synonym: 'var(--colour-node-synonym)', hypernym: 'var(--colour-node-hypernym)', hyponym: 'var(--colour-node-hyponym)',
  similar: 'var(--colour-node-similar)', collocation: 'var(--colour-chip-collocation)', antonym: 'var(--colour-chip-antonym)',
};
const tint = (v, pct) => `color-mix(in srgb, ${v} ${pct}%, transparent)`;
const PANEL_RARITY = {
  common: 'var(--colour-rarity-common)', unusual: 'var(--colour-rarity-unusual)', rare: 'var(--colour-rarity-rare)',
};
const CONNOTATION = {
  positive: 'var(--colour-connotation-positive)',
  negative: 'var(--colour-connotation-negative)',
};

function RarityBadge({ rarity }) {
  if (!rarity) return null;
  const c = PANEL_RARITY[rarity];
  return <span style={{ ...resultsPanelStyles.rarityBadge, color: c, background: tint(c, 20) }}>{rarity}</span>;
}

function Chip({ word, type, onNavigate, onCopy }) {
  const [hover, setHover] = React.useState(false);
  return (
    <span
      style={{
        ...resultsPanelStyles.chip,
        color: CHIP_COLOURS[type],
        background: hover ? 'var(--wash-gold)' : 'transparent',
      }}
      tabIndex={0}
      role="button"
      title="Click to look up, right-click to copy"
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      onClick={() => onNavigate(word)}
      onContextMenu={(e) => { e.preventDefault(); onCopy(word); }}
    >{word}</span>
  );
}

function ChipGroup({ label, words, type, onNavigate, onCopy }) {
  if (!words || !words.length) return null;
  return (
    <React.Fragment>
      <div style={resultsPanelStyles.sectionLabel}>{label}</div>
      <div style={resultsPanelStyles.wordList}>
        {words.map((rw, i) => (
          <Chip key={type + i + rw.word} word={rw.word} type={type} onNavigate={onNavigate} onCopy={onCopy} />
        ))}
      </div>
    </React.Fragment>
  );
}

function Sense({ sense, onNavigate, onCopy }) {
  const con = CONNOTATION[sense.connotation];
  return (
    <div style={resultsPanelStyles.sense}>
      <span style={resultsPanelStyles.pos}>{sense.pos}</span>
      {(sense.register !== 'neutral' || con) && (
        <div style={resultsPanelStyles.metaBadges}>
          {sense.register && sense.register !== 'neutral' && (
            <span style={{ ...resultsPanelStyles.metaBadge, color: 'var(--colour-register)', background: tint('var(--colour-register)', 20) }}>{sense.register}</span>
          )}
          {con && (
            <span style={{ ...resultsPanelStyles.metaBadge, color: con, background: tint(con, 20) }}>{sense.connotation}</span>
          )}
        </div>
      )}
      <div style={resultsPanelStyles.definition}>{sense.definition}</div>
      {sense.usage_example && <div style={resultsPanelStyles.usage}>{sense.usage_example}</div>}
      <ChipGroup label="Synonyms" words={sense.synonyms} type="synonym" onNavigate={onNavigate} onCopy={onCopy} />
      <ChipGroup label="Broader terms" words={sense.relations.hypernyms} type="hypernym" onNavigate={onNavigate} onCopy={onCopy} />
      <ChipGroup label="Narrower terms" words={sense.relations.hyponyms} type="hyponym" onNavigate={onNavigate} onCopy={onCopy} />
      <ChipGroup label="Similar" words={sense.relations.similar} type="similar" onNavigate={onNavigate} onCopy={onCopy} />
      <ChipGroup label="Antonyms" words={sense.relations.antonyms} type="antonym" onNavigate={onNavigate} onCopy={onCopy} />
      <ChipGroup label="Results-collocations" words={sense.collocations} type="collocation" onNavigate={onNavigate} onCopy={onCopy} />
    </div>
  );
}

function ResultsPanel({ result, collapsed, onToggle, onNavigate, onCopy }) {
  if (!result) return null;
  return (
    <div style={resultsPanelStyles.host}>
      <button style={resultsPanelStyles.toggleBtn} onClick={onToggle} aria-label="Collapse results panel">
        {collapsed ? 'Explore »' : '«'}
      </button>
      <div style={{ ...resultsPanelStyles.track, transform: collapsed ? 'translateX(calc(-100% - 1rem))' : 'none' }}>
        <div style={resultsPanelStyles.panel} role="region" aria-label="Thesaurus results">
          <h2 style={resultsPanelStyles.h2}>
            {result.word}
            <RarityBadge rarity={result.rarity} />
          </h2>
          {result.senses.map((s, i) => (
            <Sense key={i} sense={s} onNavigate={onNavigate} onCopy={onCopy} />
          ))}
        </div>
      </div>
    </div>
  );
}

const resultsPanelStyles = {
  host: { position: 'absolute', top: 'calc(1rem + 3.5rem)', left: '1rem', bottom: '2rem', width: '20rem', zIndex: 20, pointerEvents: 'none' },
  track: { height: '100%', overflowY: 'auto', transition: 'transform 200ms cubic-bezier(0,0,0.08,1)', pointerEvents: 'auto', scrollbarWidth: 'thin', scrollbarColor: 'var(--colour-accent-gold-dim) transparent' },
  panel: { background: 'var(--colour-bg-hud)', border: '1px solid var(--hairline)', borderRadius: 'var(--hud-radius)', backdropFilter: 'var(--hud-blur)', WebkitBackdropFilter: 'var(--hud-blur)', padding: '1rem' },
  toggleBtn: { position: 'absolute', top: '0.25rem', right: 0, background: 'var(--colour-bg-hud)', border: '1px solid var(--hairline)', borderRadius: 'var(--hud-radius)', color: 'var(--colour-accent-gold)', fontSize: '0.8rem', padding: '4px 8px', cursor: 'pointer', zIndex: 1, pointerEvents: 'auto', fontFamily: "'Crimson Text', serif" },
  h2: { fontFamily: "'Playfair Display', serif", color: 'var(--colour-accent-gold)', fontSize: '1.5rem', fontWeight: 700, marginBottom: '0.5rem' },
  rarityBadge: { display: 'inline-block', fontSize: '0.65rem', padding: '1px 6px', borderRadius: 8, marginLeft: '0.25rem', textTransform: 'uppercase', letterSpacing: '0.04em', verticalAlign: 'middle' },
  sense: { marginBottom: '1rem', paddingBottom: '1rem', borderBottom: '1px solid var(--hairline-soft)' },
  pos: { display: 'inline-block', fontSize: '0.75rem', color: 'var(--colour-text-secondary)', fontStyle: 'italic', marginBottom: '0.25rem' },
  metaBadges: { display: 'flex', gap: '0.25rem', marginBottom: '0.25rem' },
  metaBadge: { display: 'inline-block', fontSize: '0.65rem', padding: '1px 6px', borderRadius: 8, textTransform: 'uppercase', letterSpacing: '0.04em' },
  definition: { fontSize: '0.95rem', lineHeight: 1.5, marginBottom: '0.5rem', color: 'var(--colour-text-primary)', fontFamily: "'Crimson Text', serif" },
  usage: { fontStyle: 'italic', fontSize: '0.9rem', lineHeight: 1.5, color: 'var(--colour-text-secondary)', marginBottom: '0.5rem', paddingLeft: '0.5rem', borderLeft: '2px solid color-mix(in srgb, var(--colour-accent-gold) 30%, transparent)', fontFamily: "'Crimson Text', serif" },
  sectionLabel: { fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--colour-text-muted)', marginBottom: '0.25rem', marginTop: '0.5rem', fontFamily: "'Crimson Text', serif" },
  wordList: { display: 'flex', flexWrap: 'wrap', gap: '0.25rem' },
  chip: { fontSize: '0.9rem', cursor: 'pointer', padding: '2px 6px', borderRadius: 3, transition: 'background 0.15s', fontFamily: "'Crimson Text', serif" },
};

window.ResultsPanel = ResultsPanel;
