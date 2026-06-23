/* Grading Mode — GradingPanel
   The right-hand HUD. Frosted glass, gold hairline, all-serif. Shows the
   metaphor chain under review, an optional Re-grading banner, then the
   grading axes: METAPHOR · LINKAGE · TIER · CONFIDENCE · issue tags · note.
   Presentational: parent owns the working grade + keyboard, passes setters. */

const Kbd = ({ children, dark }) => <span style={dark ? gradePanelStyles.kbdDark : gradePanelStyles.kbd}>{children}</span>;

// option colour tokens
const METAPHOR_COL = {
  live: 'var(--colour-forge-interesting)',
  dead: 'var(--colour-chip-antonym)',
  irrelevant: 'var(--colour-text-muted)',
};
const LINKAGE_COL = {
  good: 'var(--colour-accent-gold)',
  bad: 'var(--colour-chip-antonym)',
};
const TIER_COL = {
  strong: 'var(--colour-forge-strong)',
  ironic: 'var(--colour-forge-ironic)',
  surprising: 'var(--colour-forge-complex)',
};
const tintP = (v, pct) => `color-mix(in srgb, ${v} ${pct}%, transparent)`;

function fmtWhen(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) +
      ' · ' + d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  } catch (e) { return iso; }
}

// A segmented option button
function Seg({ label, kbd, active, colour, onClick, grow }) {
  const c = colour || 'var(--colour-accent-gold)';
  return (
    <button
      onClick={onClick}
      style={{
        ...gradePanelStyles.seg,
        flex: grow ? 1 : '0 0 auto',
        color: active ? c : 'var(--colour-text-secondary)',
        background: active ? tintP(c, 16) : 'transparent',
        borderColor: active ? tintP(c, 55) : 'var(--hairline-soft)',
      }}
    >
      <span>{label}</span>
      {kbd && <Kbd>{kbd}</Kbd>}
    </button>
  );
}

// A small pill (tier / linkage / tag)
function Pill({ label, active, colour, onClick }) {
  const c = colour || 'var(--colour-accent-gold)';
  return (
    <button
      onClick={onClick}
      style={{
        ...gradePanelStyles.pill,
        color: active ? c : 'var(--colour-text-muted)',
        background: active ? tintP(c, 18) : 'transparent',
        borderColor: active ? tintP(c, 50) : 'var(--hairline-soft)',
      }}
    >{label}</button>
  );
}

function Row({ label, children }) {
  return (
    <div style={gradePanelStyles.row}>
      <div style={gradePanelStyles.rowLabel}>{label}</div>
      <div style={gradePanelStyles.rowBody}>{children}</div>
    </div>
  );
}

function GradingPanel({ item, grade, regrading, onSet, onToggleTag, onNote, onCommit, onSkip }) {
  if (!item) return null;
  const g = grade || {};
  const isTarget = (i) => i === item.chain.length - 1;

  return (
    <div style={gradePanelStyles.host}>
      <div style={gradePanelStyles.panel}>

        {regrading && (
          <div style={gradePanelStyles.regrade}>
            Re-grading — your previous verdict was{' '}
            <strong style={{ color: LINKAGE_COL[regrading.linkage] || 'var(--colour-accent-gold)' }}>{regrading.linkage} linkage</strong>
            {' / '}
            <strong style={{ color: METAPHOR_COL[regrading.metaphor] || 'var(--colour-accent-gold)' }}>{regrading.metaphor} metaphor</strong>
            {' '}at {fmtWhen(regrading.at)}.
          </div>
        )}

        {/* the metaphor chain under review */}
        <div style={gradePanelStyles.chain}>
          {item.chain.map((step, i) => (
            <span key={i} style={gradePanelStyles.stepWrap}>
              {i > 0 && <span style={gradePanelStyles.arrow}>→ </span>}
              <span style={{
                color: i === 0 ? 'var(--colour-accent-gold)'
                  : isTarget(i) ? 'var(--colour-chip-collocation)'
                  : 'var(--colour-text-secondary)',
                fontStyle: i === 0 || isTarget(i) ? 'normal' : 'italic',
                fontWeight: i === 0 || isTarget(i) ? 600 : 400,
              }}>{step}</span>
            </span>
          ))}
        </div>

        <Row label="Metaphor">
          <div style={gradePanelStyles.segGroup}>
            <Seg grow label="Live" kbd="L" colour={METAPHOR_COL.live} active={g.metaphor === 'live'} onClick={() => onSet('metaphor', 'live')} />
            <Seg grow label="Dead" kbd="D" colour={METAPHOR_COL.dead} active={g.metaphor === 'dead'} onClick={() => onSet('metaphor', 'dead')} />
            <Seg grow label="Irrelevant" kbd="I" colour={METAPHOR_COL.irrelevant} active={g.metaphor === 'irrelevant'} onClick={() => onSet('metaphor', 'irrelevant')} />
          </div>
        </Row>

        <Row label="Linkage">
          <div style={gradePanelStyles.segGroup}>
            <Seg grow label="Good (default)" colour={LINKAGE_COL.good} active={(g.linkage || 'good') === 'good'} onClick={() => onSet('linkage', 'good')} />
            <Seg grow label="Bad" kbd="B" colour={LINKAGE_COL.bad} active={g.linkage === 'bad'} onClick={() => onSet('linkage', g.linkage === 'bad' ? 'good' : 'bad')} />
          </div>
        </Row>

        <Row label="Tier">
          <div style={gradePanelStyles.pillWrap}>
            {['strong', 'ironic', 'surprising'].map((t) => (
              <Pill key={t} label={t} colour={TIER_COL[t]} active={g.tier === t} onClick={() => onSet('tier', g.tier === t ? null : t)} />
            ))}
          </div>
        </Row>

        <Row label="Confidence">
          <div style={gradePanelStyles.segGroup}>
            <Seg grow label="High" kbd="1" active={g.confidence === 'high'} onClick={() => onSet('confidence', 'high')} />
            <Seg grow label="Med" kbd="2" active={g.confidence === 'med'} onClick={() => onSet('confidence', 'med')} />
            <Seg grow label="Low" kbd="3" active={g.confidence === 'low'} onClick={() => onSet('confidence', 'low')} />
          </div>
        </Row>

        <div style={gradePanelStyles.tagWrap}>
          {['merge', 'padding', 'leap', 'other'].map((tag) => (
            <Pill key={tag} label={tag} active={(g.tags || []).includes(tag)} onClick={() => onToggleTag(tag)} />
          ))}
        </div>

        <textarea
          style={gradePanelStyles.note}
          placeholder="optional note — public repo, no secrets"
          value={g.note || ''}
          onChange={(e) => onNote(e.target.value)}
        />

        <div style={gradePanelStyles.footer}>
          <button style={gradePanelStyles.skip} onClick={onSkip}>Skip <Kbd>S</Kbd></button>
          <button
            style={{ ...gradePanelStyles.commit, opacity: g.metaphor ? 1 : 0.45, cursor: g.metaphor ? 'pointer' : 'not-allowed' }}
            disabled={!g.metaphor}
            onClick={onCommit}
          >Save &amp; next <Kbd dark>↵</Kbd></button>
        </div>
      </div>
    </div>
  );
}

const gradePanelStyles = {
  host: { position: 'absolute', top: 'calc(1rem + 3.5rem)', right: '1rem', bottom: '2rem', width: '23rem', zIndex: 20, overflowY: 'auto', scrollbarWidth: 'thin', scrollbarColor: 'var(--colour-accent-gold-dim) transparent' },
  panel: { background: 'var(--colour-bg-hud)', border: '1px solid var(--hairline)', borderRadius: 'var(--hud-radius)', backdropFilter: 'var(--hud-blur)', WebkitBackdropFilter: 'var(--hud-blur)', padding: '0.9rem 1rem 1rem' },
  regrade: { border: '1px solid color-mix(in srgb, var(--colour-accent-gold) 45%, transparent)', background: 'var(--wash-gold-soft)', borderRadius: 'var(--hud-radius)', padding: '0.5rem 0.6rem', fontFamily: "'Crimson Text', serif", fontSize: '0.82rem', lineHeight: 1.45, color: 'var(--colour-text-secondary)', marginBottom: '0.75rem' },
  chain: { fontFamily: "'Crimson Text', serif", fontSize: '1.02rem', lineHeight: 1.5, paddingBottom: '0.8rem', marginBottom: '0.4rem', borderBottom: '1px solid var(--hairline-soft)' },
  stepWrap: { whiteSpace: 'normal', marginRight: '0.15rem' },
  arrow: { color: 'var(--colour-accent-gold-dim)', fontSize: '0.85rem' },
  row: { display: 'flex', alignItems: 'flex-start', gap: '0.6rem', marginTop: '0.7rem' },
  rowLabel: { flex: '0 0 4.6rem', fontFamily: "'Crimson Text', serif", fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--colour-text-muted)', paddingTop: '0.42rem' },
  rowBody: { flex: 1, minWidth: 0 },
  segGroup: { display: 'flex', gap: '0.35rem' },
  seg: { display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '0.35rem', padding: '0.34rem 0.6rem', borderRadius: 'var(--hud-radius)', border: '1px solid var(--hairline-soft)', fontFamily: "'Crimson Text', serif", fontSize: '0.92rem', cursor: 'pointer', transition: 'all 0.13s', whiteSpace: 'nowrap', background: 'transparent' },
  pillWrap: { display: 'flex', flexWrap: 'wrap', gap: '0.35rem' },
  pill: { padding: '0.26rem 0.7rem', borderRadius: '999px', border: '1px solid var(--hairline-soft)', fontFamily: "'Crimson Text', serif", fontSize: '0.86rem', cursor: 'pointer', transition: 'all 0.13s', textTransform: 'lowercase' },
  tagWrap: { display: 'flex', flexWrap: 'wrap', gap: '0.35rem', marginTop: '0.85rem' },
  note: { width: '100%', marginTop: '0.7rem', minHeight: '4.5rem', resize: 'vertical', background: 'color-mix(in srgb, var(--colour-bg-primary) 35%, transparent)', border: '1px solid var(--hairline-soft)', borderRadius: 'var(--hud-radius)', padding: '0.5rem 0.6rem', color: 'var(--colour-text-primary)', fontFamily: "'Crimson Text', serif", fontSize: '0.9rem', outline: 'none' },
  footer: { display: 'flex', gap: '0.5rem', marginTop: '0.85rem' },
  skip: { flex: '0 0 auto', display: 'inline-flex', alignItems: 'center', gap: '0.35rem', whiteSpace: 'nowrap', padding: '0.45rem 0.8rem', borderRadius: 'var(--hud-radius)', border: '1px solid var(--hairline-soft)', background: 'transparent', color: 'var(--colour-text-secondary)', fontFamily: "'Crimson Text', serif", fontSize: '0.9rem', cursor: 'pointer' },
  commit: { flex: 1, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '0.4rem', whiteSpace: 'nowrap', padding: '0.45rem 0.8rem', borderRadius: 'var(--hud-radius)', border: '1px solid var(--colour-accent-gold)', background: 'var(--colour-accent-gold)', color: 'var(--colour-bg-primary)', fontFamily: "'Crimson Text', serif", fontSize: '0.95rem', fontWeight: 600, transition: 'opacity 0.13s' },
  kbd: { fontFamily: "'JetBrains Mono', monospace", fontSize: '0.62rem', lineHeight: 1, padding: '2px 4px', borderRadius: 3, background: 'var(--wash-gold-soft)', border: '1px solid var(--hairline-soft)', color: 'var(--colour-text-secondary)' },
  kbdDark: { fontFamily: "'JetBrains Mono', monospace", fontSize: '0.62rem', lineHeight: 1, padding: '2px 4px', borderRadius: 3, background: 'color-mix(in srgb, var(--colour-bg-primary) 28%, transparent)', border: '1px solid color-mix(in srgb, var(--colour-bg-primary) 30%, transparent)', color: 'var(--colour-bg-primary)' },
};

window.GradingPanel = GradingPanel;
