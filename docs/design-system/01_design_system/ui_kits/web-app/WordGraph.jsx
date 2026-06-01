/* Metaforge UI Kit — WordGraph
   A 2D recreation of the product's 3D force-directed graph: rarity-coloured
   serif word labels radiating from the central gold word, joined by thin
   springy edges. Click a node to navigate; hover to highlight. Rarity
   filters hide/show nodes. (The shipped product renders this in Three.js /
   3d-force-graph; this is a faithful 2D stand-in for the kit.) */

const { useState: useGState, useEffect: useGEffect, useRef: useGRef, useMemo } = React;

const GRAPH_RARITY = {
  common: 'var(--colour-rarity-common)',
  unusual: 'var(--colour-rarity-unusual)',
  rare: 'var(--colour-rarity-rare)',
};
const GRAPH_CENTRAL = 'var(--colour-accent-gold)';

// deterministic hash → 0..1
function hash01(str, salt) {
  let h = 2166136261 ^ salt;
  for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619); }
  return ((h >>> 0) % 10000) / 10000;
}

// Build a flat node/link list from a lookup result (mirrors transform.ts priority)
function buildGraph(result, max = 18) {
  if (!result) return { nodes: [], links: [] };
  const nodes = [{ id: result.word, word: result.word, relationType: 'central', rarity: result.rarity }];
  const seen = new Set([result.word]);
  const tiers = [['synonyms', 'synonym'], ['hyponyms', 'hyponym'], ['hypernyms', 'hypernym'], ['similar', 'similar']];
  const links = [];
  let remaining = max - 1;
  for (const sense of result.senses) {
    for (const [key, type] of tiers) {
      const list = key === 'synonyms' ? sense.synonyms : sense.relations[key];
      if (!list) continue;
      for (const rw of list) {
        if (remaining <= 0) break;
        if (seen.has(rw.word)) continue;
        seen.add(rw.word);
        nodes.push({ id: rw.word, word: rw.word, relationType: type, rarity: rw.rarity });
        links.push({ source: result.word, target: rw.word });
        remaining--;
      }
    }
  }
  // a few cross-links between adjacent same-rarity satellites (visual richness)
  for (let i = 1; i < nodes.length - 1; i++) {
    if (nodes[i].rarity === nodes[i + 1].rarity && hash01(nodes[i].word, 7) > 0.55) {
      links.push({ source: nodes[i].id, target: nodes[i + 1].id, cross: true });
    }
  }
  return { nodes, links };
}

function layout(nodes, W, H) {
  // Keep the graph in the open area to the RIGHT of the results panel,
  // and spread satellites evenly (sunflower / Vogel spiral) so labels
  // don't collide or fall off-screen.
  const panelRight = Math.min(360, W * 0.46);
  const padL = panelRight + 36, padR = 56, padT = 132, padB = 66;
  const cx = (padL + (W - padR)) / 2;
  const cy = (padT + (H - padB)) / 2;
  const rx = Math.max(120, ((W - padR) - padL) / 2);
  const ry = Math.max(110, ((H - padB) - padT) / 2);

  const pos = {};
  pos[nodes[0].id] = { x: cx, y: cy };
  const sat = nodes.slice(1);
  const n = sat.length;
  sat.forEach((node, idx) => {
    const i = idx + 1;
    const t = Math.sqrt(i / (n + 0.6));            // even radial fill 0..1
    const ang = i * 2.39996323 + (hash01(node.word, 3) - 0.5) * 0.45;
    const jr = 0.92 + hash01(node.word, 11) * 0.16; // gentle radius jitter
    pos[node.id] = {
      x: cx + Math.cos(ang) * rx * t * jr,
      y: cy + Math.sin(ang) * ry * t * jr,
    };
  });
  return pos;
}

function WordGraph({ result, filters, onNavigate, onCopy }) {
  const ref = useGRef(null);
  const [dims, setDims] = useGState({ w: 1000, h: 700 });
  const [hover, setHover] = useGState(null);

  useGEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(() => {
      const el = ref.current;
      if (el) setDims({ w: el.clientWidth, h: el.clientHeight });
    });
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);

  const { nodes, links } = useMemo(() => buildGraph(result), [result]);
  const pos = useMemo(() => (nodes.length ? layout(nodes, dims.w, dims.h) : {}), [nodes, dims]);

  const visible = (n) => n.relationType === 'central' || filters[n.rarity];

  function colourOf(n) {
    return n.relationType === 'central' ? GRAPH_CENTRAL : GRAPH_RARITY[n.rarity] || 'var(--colour-text-primary)';
  }

  return (
    <div ref={ref} style={wordGraphStyles.host}>
      <svg width={dims.w} height={dims.h} style={{ display: 'block' }}>
        {/* edges */}
        {links.map((l, i) => {
          const a = pos[l.source]; const b = pos[l.target];
          const na = nodes.find((n) => n.id === l.source); const nb = nodes.find((n) => n.id === l.target);
          if (!a || !b || !visible(na) || !visible(nb)) return null;
          const hot = hover && (hover === l.source || hover === l.target);
          return (
            <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y}
              style={{ stroke: hot ? 'var(--colour-edge-highlight)' : (l.cross ? 'var(--colour-edge-dim)' : 'var(--colour-edge-default)') }}
              strokeWidth={hot ? 1.4 : (l.cross ? 0.6 : 1)} />
          );
        })}
        {/* nodes */}
        {nodes.map((n) => {
          if (!visible(n)) return null;
          const p = pos[n.id]; if (!p) return null;
          const isCentral = n.relationType === 'central';
          const isHover = hover === n.id;
          const col = colourOf(n);
          const fontSize = isCentral ? 19 : 14.5;
          const dotR = isCentral ? 6 : 3.5;
          return (
            <g key={n.id} style={{ cursor: 'pointer' }}
              onClick={() => !isCentral && onNavigate(n.word)}
              onContextMenu={(e) => { e.preventDefault(); onCopy(n.word); }}
              onMouseEnter={() => setHover(n.id)}
              onMouseLeave={() => setHover((h) => (h === n.id ? null : h))}
            >
              {isCentral && <circle cx={p.x} cy={p.y} r={13} fill="none" style={{ stroke: 'color-mix(in srgb, var(--colour-accent-gold) 25%, transparent)' }} strokeWidth="1" />}
              <circle cx={p.x} cy={p.y} r={dotR} style={{ fill: col }} opacity={0.92} />
              {isHover && (
                <rect x={p.x - (n.word.length * fontSize * 0.30) - 6} y={p.y - fontSize - 17}
                  width={n.word.length * fontSize * 0.60 + 12} height={fontSize + 9}
                  rx={3} style={{ fill: 'color-mix(in srgb, var(--colour-bg-primary) 40%, transparent)', stroke: col }} strokeWidth="0.8" />
              )}
              <text x={p.x} y={p.y - 11} textAnchor="middle"
                fontFamily="'Playfair Display', Georgia, serif"
                fontSize={fontSize} fontWeight={isCentral ? 700 : 400}
                style={{ fill: col, userSelect: 'none' }}>{n.word}</text>
            </g>
          );
        })}
      </svg>
      <div style={wordGraphStyles.hint}>Left-click: look up · Right-click: copy · Drag/scroll to explore</div>
    </div>
  );
}

const wordGraphStyles = {
  host: { position: 'absolute', inset: 0, width: '100%', height: '100%', overflow: 'hidden', zIndex: 1, cursor: 'grab' },
  hint: { position: 'absolute', bottom: 8, left: '50%', transform: 'translateX(-50%)', color: 'var(--colour-text-muted)', opacity: 0.7, fontSize: '0.7rem', fontFamily: "'Crimson Text', serif", letterSpacing: '0.02em' },
};

window.WordGraph = WordGraph;
