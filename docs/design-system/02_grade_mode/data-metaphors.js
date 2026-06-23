/* ============================================================
   Grading Mode — metaphor dataset
   ------------------------------------------------------------
   Grade Mode operates on GENERATED METAPHORS, not the thesaurus.
   A metaphor is a CHAIN: a path from a source word, across a few
   associative "bridge" steps, to a target word.

       anchor → prevents drift → holds everything together → keystone

   We model one source word's generation graph ("anchor") plus a
   queue of candidate metaphors that walk paths through it. Each
   item may already carry a prior grade — that drives the queue
   filters (Both / Ungraded / Graded) and the Re-grading banner.
   Colours are all design-system tokens; nothing invented here.
   ============================================================ */
(function () {
  // ---- the source word's generation graph -------------------
  // rarity tints the node + label (sage common / copper unusual / lilac rare)
  const N = (id, rarity, ring) => ({ id, rarity, ring: ring || null });
  const NODES = [
    N('anchor', 'unusual'),           // the central source word (gold)
    // — holding / tension branch
    N('hold', 'common'),
    N('chain', 'common'),
    N('connector', 'common', 'rare'),
    N('tendon', 'unusual', 'rare'),
    N('vessel', 'common'),
    N('body', 'common'),
    N('line', 'common'),
    N('depth', 'unusual'),
    N('plummet', 'rare', 'rare'),
    // — drift / settling branch
    N('drift', 'common'),
    N('drops', 'common'),
    N('sinks', 'common'),
    N('settles', 'common'),
    N('inertia', 'unusual'),
    N('stone', 'common', 'rare'),
    // — fixity / structure branch
    N('keystone', 'unusual', 'rare'),
    N('root', 'common', 'rare'),
    N('point', 'common'),
    N('position', 'common'),
    // — habit / pattern branch
    N('rest', 'common'),
    N('descends', 'unusual'),
    N('grips', 'common'),
    N('change', 'common'),
    N('pattern', 'common'),
    N('habit', 'common', 'rare'),
  ];

  // structural edges (grey by default; grade state recolours a path)
  const L = (a, b) => ({ source: a, target: b });
  const LINKS = [
    L('anchor', 'hold'), L('anchor', 'drift'), L('anchor', 'drops'),
    L('anchor', 'position'), L('anchor', 'sinks'), L('anchor', 'point'),
    L('anchor', 'rest'), L('anchor', 'descends'), L('anchor', 'grips'),
    L('anchor', 'vessel'), L('anchor', 'body'),
    L('hold', 'keystone'), L('hold', 'root'), L('hold', 'chain'), L('hold', 'drops'),
    L('chain', 'connector'), L('connector', 'tendon'),
    L('body', 'line'), L('line', 'depth'), L('depth', 'plummet'),
    L('vessel', 'point'), L('point', 'position'),
    L('drift', 'hold'),
    L('position', 'change'), L('change', 'pattern'), L('pattern', 'habit'),
    L('sinks', 'settles'), L('settles', 'inertia'), L('inertia', 'stone'),
    L('drops', 'sinks'),
  ];

  // ---- the grading queue ------------------------------------
  // path = node ids whose connecting edges light up for this metaphor.
  // chain = the human-readable rendering (source, bridges…, target).
  // grade = null (ungraded) OR a prior verdict (graded → Re-grading).
  const G = (metaphor, linkage, tier, confidence, tags, note, at) =>
    ({ metaphor, linkage, tier, confidence, tags: tags || [], note: note || '', at });

  const METAPHORS = [
    {
      id: 'm-keystone',
      source: 'anchor', target: 'keystone',
      chain: ['anchor', 'prevents drift', 'holds everything together', 'keystone'],
      path: ['anchor', 'drift', 'hold', 'keystone'],
      grade: null,
    },
    {
      id: 'm-tendon',
      source: 'anchor', target: 'tendon',
      chain: ['anchor', 'chain to vessel', 'holds under tension', 'taut connector', 'tendon'],
      path: ['anchor', 'chain', 'connector', 'tendon'],
      grade: G('live', 'good', 'strong', 'high', [], '', '2026-05-31T09:00:06.864556+00:00'),
    },
    {
      id: 'm-plummet',
      source: 'anchor', target: 'plummet',
      chain: ['anchor', 'a weighted body', 'on a line into the depth', 'plummet'],
      path: ['anchor', 'body', 'line', 'depth', 'plummet'],
      grade: null,
    },
    {
      id: 'm-habit',
      source: 'anchor', target: 'habit',
      chain: ['anchor', 'holds a position', 'against change', 'a settled pattern', 'habit'],
      path: ['anchor', 'position', 'change', 'pattern', 'habit'],
      grade: null,
    },
    {
      id: 'm-stone',
      source: 'anchor', target: 'stone',
      chain: ['anchor', 'sinks', 'settles into inertia', 'stone'],
      path: ['anchor', 'sinks', 'settles', 'inertia', 'stone'],
      grade: G('dead', 'bad', null, 'med', ['leap'], 'reads as a definition, not a figure', '2026-05-30T14:12:41.001000+00:00'),
    },
    {
      id: 'm-root',
      source: 'anchor', target: 'root',
      chain: ['anchor', 'holds fast below', 'takes root'],
      path: ['anchor', 'hold', 'root'],
      grade: null,
    },
    {
      id: 'm-grips',
      source: 'anchor', target: 'grips',
      chain: ['anchor', 'grips the seabed'],
      path: ['anchor', 'grips'],
      grade: G('irrelevant', 'good', null, 'low', ['padding'], '', '2026-05-29T22:41:09.500000+00:00'),
    },
    {
      id: 'm-rest',
      source: 'anchor', target: 'rest',
      chain: ['anchor', 'comes to rest', 'descends'],
      path: ['anchor', 'rest', 'descends'],
      grade: null,
    },
  ];

  window.MF_FORGE = {
    graph: { nodes: NODES, links: LINKS, central: 'anchor' },
    queue: METAPHORS,
  };
})();
