/* Grading Mode — GraphForge
   A faithful 2D stand-in for the product's 3D force graph, tuned to match
   the live Browse look: glossy gem nodes, soft volumetric grey edges, serif
   rarity-tinted labels, a gold central node, slate-blue rings on metaphor
   targets. In Grade mode the metaphor under review lights its path; every
   other already-graded metaphor leaves a faint coloured trail (sage = good/
   live, rose = dead, muted = irrelevant), exactly as the real tool does. */

const { useState: useGState, useEffect: useGEffect, useRef: useGRef, useMemo: useGMemo } = React;

const RARITY_TOKEN = {
  common: 'var(--colour-rarity-common)',
  unusual: 'var(--colour-rarity-unusual)',
  rare: 'var(--colour-rarity-rare)',
};
const VERDICT_EDGE = {
  live: 'var(--colour-forge-interesting)',  // forest green — a good, living link
  good: 'var(--colour-forge-interesting)',
  dead: 'var(--colour-chip-antonym)',       // dusty rose
  broken: 'var(--colour-chip-antonym)',
  irrelevant: 'var(--colour-text-muted)',
  active: 'var(--colour-rarity-unusual)',   // copper — the chain under review
};
const TARGET_RING = 'var(--colour-chip-collocation)'; // slate-blue ring on targets
const pairKey = (a, b) => (a < b ? a + '|' + b : b + '|' + a);

// ---- tiny deterministic force layout ----------------------------------
function forceLayout(nodes, links, central, W, H) {
  const idx = {}; nodes.forEach((n, i) => (idx[n.id] = i));
  const P = nodes.map((n, i) => {
    const a = i * 2.39996323, r = 30 + i * 13;
    return { x: Math.cos(a) * r, y: Math.sin(a) * r, vx: 0, vy: 0 };
  });
  const ci = idx[central];
  P[ci].x = 0; P[ci].y = 0;
  const REST = 96, K_SPRING = 0.045, K_REPEL = 5200, DAMP = 0.86;
  for (let it = 0; it < 320; it++) {
    for (let i = 0; i < P.length; i++) {
      for (let j = i + 1; j < P.length; j++) {
        let dx = P[i].x - P[j].x, dy = P[i].y - P[j].y;
        let d2 = dx * dx + dy * dy || 0.01;
        const f = K_REPEL / d2;
        const d = Math.sqrt(d2);
        const ux = dx / d, uy = dy / d;
        P[i].vx += ux * f; P[i].vy += uy * f;
        P[j].vx -= ux * f; P[j].vy -= uy * f;
      }
    }
    for (const l of links) {
      const a = P[idx[l.source]], b = P[idx[l.target]];
      if (!a || !b) continue;
      let dx = b.x - a.x, dy = b.y - a.y;
      const d = Math.sqrt(dx * dx + dy * dy) || 0.01;
      const f = (d - REST) * K_SPRING;
      const ux = dx / d, uy = dy / d;
      a.vx += ux * f; a.vy += uy * f;
      b.vx -= ux * f; b.vy -= uy * f;
    }
    for (let i = 0; i < P.length; i++) {
      if (i === ci) { P[i].x = 0; P[i].y = 0; P[i].vx = 0; P[i].vy = 0; continue; }
      P[i].vx *= DAMP; P[i].vy *= DAMP;
      P[i].x += P[i].vx; P[i].y += P[i].vy;
    }
  }
  // fit into a centred box
  let minX = 1e9, maxX = -1e9, minY = 1e9, maxY = -1e9;
  P.forEach((p) => { minX = Math.min(minX, p.x); maxX = Math.max(maxX, p.x); minY = Math.min(minY, p.y); maxY = Math.max(maxY, p.y); });
  const pad = 90;
  const sx = (W - pad * 2) / Math.max(1, maxX - minX);
  const sy = (H - pad * 2) / Math.max(1, maxY - minY);
  const s = Math.min(sx, sy, 1.35);
  const cx = (minX + maxX) / 2, cy = (minY + maxY) / 2;
  const pos = {};
  nodes.forEach((n, i) => { pos[n.id] = { x: W / 2 + (P[i].x - cx) * s, y: H / 2 + (P[i].y - cy) * s }; });
  return pos;
}

function GraphForge({ graph, filters, targets, pathEdges, trailEdges, onNavigate, onCopy, dimmed }) {
  const ref = useGRef(null);
  const [dims, setDims] = useGState({ w: 1100, h: 760 });
  const [hover, setHover] = useGState(null);
  const [view, setView] = useGState({ x: 0, y: 0, k: 1 });
  const drag = useGRef(null);

  useGEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(() => {
      const el = ref.current; if (el) setDims({ w: el.clientWidth, h: el.clientHeight });
    });
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);

  const pos = useGMemo(
    () => forceLayout(graph.nodes, graph.links, graph.central, dims.w, dims.h),
    [graph, dims.w, dims.h]
  );
  const nodeById = useGMemo(() => { const m = {}; graph.nodes.forEach((n) => (m[n.id] = n)); return m; }, [graph]);
  const visible = (n) => n.id === graph.central || !filters || filters[n.rarity];

  // pan / zoom
  function onWheel(e) {
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.12 : 0.89;
    setView((v) => ({ ...v, k: Math.min(3, Math.max(0.4, v.k * factor)) }));
  }
  function onDown(e) { drag.current = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y }; }
  function onMove(e) {
    if (!drag.current) return;
    setView((v) => ({ ...v, x: drag.current.vx + (e.clientX - drag.current.x), y: drag.current.vy + (e.clientY - drag.current.y) }));
  }
  function onUp() { drag.current = null; }

  const edgeColour = (l) => {
    const k = pairKey(l.source, l.target);
    if (pathEdges && pathEdges[k]) return { c: VERDICT_EDGE[pathEdges[k]] || VERDICT_EDGE.active, w: 5.5, o: 0.92, glow: true };
    if (trailEdges && trailEdges[k]) return { c: VERDICT_EDGE[trailEdges[k]] || 'var(--colour-edge-default)', w: 3, o: 0.4, glow: false };
    return { c: 'var(--colour-edge-default)', w: 3.2, o: dimmed ? 0.5 : 1, glow: false };
  };

  return (
    <div
      ref={ref}
      style={{ ...graphForgeStyles.host, cursor: drag.current ? 'grabbing' : 'grab', opacity: dimmed ? 0.6 : 1 }}
      onWheel={onWheel} onMouseDown={onDown} onMouseMove={onMove} onMouseUp={onUp} onMouseLeave={onUp}
    >
      <svg width={dims.w} height={dims.h} style={{ display: 'block' }}>
        <defs>
          <filter id="edgeSoft" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="2.2" />
          </filter>
          <radialGradient id="gemGold" cx="38%" cy="32%" r="75%">
            <stop offset="0%" stopColor="#f4e3a0" /><stop offset="42%" stopColor="#d4af37" /><stop offset="100%" stopColor="#7d6518" />
          </radialGradient>
          <radialGradient id="gemCommon" cx="38%" cy="32%" r="75%">
            <stop offset="0%" stopColor="#cfe6d4" /><stop offset="45%" stopColor="#8bb89a" /><stop offset="100%" stopColor="#4f6b58" />
          </radialGradient>
          <radialGradient id="gemUnusual" cx="38%" cy="32%" r="75%">
            <stop offset="0%" stopColor="#e6c8a6" /><stop offset="45%" stopColor="#c4956a" /><stop offset="100%" stopColor="#7a5635" />
          </radialGradient>
          <radialGradient id="gemRare" cx="38%" cy="32%" r="75%">
            <stop offset="0%" stopColor="#d8c6e6" /><stop offset="45%" stopColor="#a88bc4" /><stop offset="100%" stopColor="#5f4a78" />
          </radialGradient>
        </defs>

        <g transform={`translate(${view.x},${view.y}) scale(${view.k})`}>
          {/* edges */}
          {graph.links.map((l, i) => {
            const a = pos[l.source], b = pos[l.target];
            const na = nodeById[l.source], nb = nodeById[l.target];
            if (!a || !b || !visible(na) || !visible(nb)) return null;
            const ec = edgeColour(l);
            const hot = hover && (hover === l.source || hover === l.target);
            return (
              <g key={i}>
                <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={ec.c} strokeWidth={ec.w + (ec.glow ? 4 : 2)}
                  strokeLinecap="round" opacity={ec.o * 0.5} filter="url(#edgeSoft)" />
                <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={ec.c} strokeWidth={hot ? ec.w + 1 : ec.w}
                  strokeLinecap="round" opacity={Math.min(1, ec.o + (hot ? 0.2 : 0))} />
              </g>
            );
          })}

          {/* nodes */}
          {graph.nodes.map((n) => {
            if (!visible(n)) return null;
            const p = pos[n.id]; if (!p) return null;
            const isCentral = n.id === graph.central;
            const isHover = hover === n.id;
            const isTarget = targets && targets.has(n.id);
            const grad = isCentral ? 'url(#gemGold)'
              : n.rarity === 'common' ? 'url(#gemCommon)'
              : n.rarity === 'unusual' ? 'url(#gemUnusual)' : 'url(#gemRare)';
            const rad = isCentral ? 11 : 6.5;
            const labelCol = isCentral ? 'var(--colour-accent-gold)' : RARITY_TOKEN[n.rarity];
            const fs = isCentral ? 18 : 13.5;
            return (
              <g key={n.id} style={{ cursor: 'pointer' }}
                onClick={(e) => { e.stopPropagation(); if (!isCentral && onNavigate) onNavigate(n.id); }}
                onContextMenu={(e) => { e.preventDefault(); onCopy && onCopy(n.id); }}
                onMouseEnter={() => setHover(n.id)}
                onMouseLeave={() => setHover((h) => (h === n.id ? null : h))}
              >
                {/* contact shadow */}
                <ellipse cx={p.x} cy={p.y + rad * 0.62} rx={rad * 0.95} ry={rad * 0.4} fill="rgba(0,0,0,0.35)" />
                {isTarget && <circle cx={p.x} cy={p.y} r={rad + 4.5} fill="none" stroke={TARGET_RING} strokeWidth="1.4" opacity="0.85" />}
                {isCentral && <circle cx={p.x} cy={p.y} r={rad + 6} fill="none" stroke="color-mix(in srgb, var(--colour-accent-gold) 30%, transparent)" strokeWidth="1" />}
                <circle cx={p.x} cy={p.y} r={rad} fill={grad} />
                {/* glossy top highlight */}
                <ellipse cx={p.x - rad * 0.28} cy={p.y - rad * 0.34} rx={rad * 0.42} ry={rad * 0.28} fill="rgba(255,255,255,0.5)" />
                {isHover && (
                  <rect x={p.x - (n.id.length * fs * 0.30) - 7} y={p.y - rad - fs - 13}
                    width={n.id.length * fs * 0.60 + 14} height={fs + 8} rx="3"
                    fill="color-mix(in srgb, var(--colour-bg-primary) 55%, transparent)" stroke={labelCol} strokeWidth="0.7" opacity="0.9" />
                )}
                <text x={p.x} y={p.y - rad - 7} textAnchor="middle"
                  fontFamily="'Playfair Display', Georgia, serif" fontSize={fs}
                  fontWeight={isCentral ? 700 : 500} fill={labelCol} style={{ userSelect: 'none' }}>
                  {n.id}
                  {!isCentral && <tspan dx="3" fontSize={fs * 0.7} opacity="0.55"> ›</tspan>}
                </text>
              </g>
            );
          })}
        </g>
      </svg>
      <div style={graphForgeStyles.hint}>Drag to pan · scroll to zoom · left-click a node to look up · right-click to copy</div>
    </div>
  );
}

const graphForgeStyles = {
  host: { position: 'absolute', inset: 0, width: '100%', height: '100%', overflow: 'hidden', zIndex: 1 },
  hint: { position: 'absolute', bottom: 8, left: '50%', transform: 'translateX(-50%)', color: 'var(--colour-text-muted)', opacity: 0.7, fontSize: '0.7rem', fontFamily: "'Crimson Text', serif", letterSpacing: '0.02em', pointerEvents: 'none' },
};

window.GraphForge = GraphForge;
