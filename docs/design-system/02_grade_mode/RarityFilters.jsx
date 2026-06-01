/* Metaforge UI Kit — RarityFilters
   Three tinted checkbox toggles (Common / Unusual / Rare). */

const RARITY_FILTER_COLOURS = {
  common: 'var(--colour-rarity-common)',
  unusual: 'var(--colour-rarity-unusual)',
  rare: 'var(--colour-rarity-rare)',
};

function RarityFilters({ filters, onToggle }) {
  const items = [
    ['common', 'Common'],
    ['unusual', 'Unusual'],
    ['rare', 'Rare'],
  ];
  return (
    <div style={rarityFiltersStyles.row} role="group" aria-label="Filter by word rarity">
      {items.map(([key, label]) => (
        <label key={key} style={{ ...rarityFiltersStyles.toggle, color: RARITY_FILTER_COLOURS[key] }}>
          <input
            type="checkbox"
            checked={filters[key]}
            onChange={() => onToggle(key)}
            style={{ accentColor: RARITY_FILTER_COLOURS[key], width: 15, height: 15, cursor: 'pointer' }}
          />
          {label}
        </label>
      ))}
    </div>
  );
}

const rarityFiltersStyles = {
  row: { display: 'flex', gap: '0.5rem', justifyContent: 'center' },
  toggle: {
    display: 'flex', alignItems: 'center', gap: 4, fontSize: '0.78rem',
    cursor: 'pointer', fontFamily: "'Crimson Text', serif",
    background: 'var(--colour-bg-hud)', border: '1px solid var(--hairline-soft)',
    borderRadius: 'var(--hud-radius)', padding: '4px 10px', backdropFilter: 'var(--hud-blur)',
  },
};

window.RarityFilters = RarityFilters;
