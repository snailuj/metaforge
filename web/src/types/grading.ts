// Flat v1 verdict — retained only for reading legacy records via normaliseJudgement.
export type Label = 'live' | 'dead' | 'bad_path' | 'irrelevant';
// v2 two-axis verdict: linkage (are the hops accurate?) + metaphor (is the endpoint apt?).
export type Linkage = 'good' | 'bad';
export type MetaphorVerdict = 'live' | 'dead' | 'irrelevant';
// Multi-select reading tiers. `legendary` is derived in a later milestone, not
// human-assigned, so it is not part of the human vocabulary.
export type Tier = 'strong' | 'ironic' | 'surprising';
// Structured issue tags — orthogonal to the verdict axes. `bad_head` flags a
// mis-extracted head concept (a data-prep error), kept distinct from a `bad`
// linkage verdict so head-extraction noise stays out of the metaphor signal.
// `bad_sense` flags a wrong-sense snap (head lemma right, synset wrong): a
// data-quality flag that marks the row sense-suspect, NOT linkage-forcing.
export type Tag = 'merge' | 'padding' | 'leap' | 'bad_head' | 'bad_sense' | 'other';
export const TAGS: readonly Tag[] = ['merge', 'padding', 'leap', 'bad_head', 'bad_sense', 'other'] as const;
export type Confidence = 'high' | 'med' | 'low';

// Per-occurrence sense that has been confirmed as apt at a chain position.
// `intended` = the emit-the-sense gloss-match recorded by the pipeline.
// `operator` = a grading tick applied via the sense fan UI.
export interface AptSense {
    synset_id: string;
    source: 'intended' | 'operator';
}

// Operator-ticked sense at a specific chain step index, carried in the verdict POST body.
// Only OPERATOR ticks are included; the intended sense is already in ChainStep.apt_senses.
export interface StepAptSense {
    step_idx: number;
    synset_id: string;
}

export interface ChainStep {
    phrase: string;
    head: string;
    synset_id: string | null;
    // Phrase-as-Node: explicit graph-node reference. Absent on chain.v1 records;
    // resolved at read-time via resolved_node_ref() logic in the pipeline.
    node_ref?: string | null;
    // Per-occurrence apt sense-set populated by the pipeline / operator.
    apt_senses?: AptSense[];
}

export interface ChainRecord {
    schema_version: 'chain.v1';
    topic: string;
    topic_synset_id: string;
    vehicle: string;
    vehicle_synset_id: string;
    proposer: string;
    round: number;
    chain: ChainStep[];
    chain_signature: string;
    generated_at: string;
}

export interface JudgementRecord {
    schema_version: 'judgement.v2';
    // Omit ts on construction — the server injects a UTC timestamp via default_factory.
    // Existing JSONL records with ts continue to deserialise correctly.
    ts?: string;
    judged_by: string;
    round: number;
    topic: string;
    topic_synset_id: string;
    vehicle: string;
    vehicle_synset_id: string;
    proposer: string;
    chain_signature: string;
    // Two orthogonal axes replace the flat v1 `label`; tiers is a multi-select supplement.
    linkage: Linkage;
    metaphor: MetaphorVerdict;
    tiers: Tier[];
    tags: Tag[];
    confidence: Confidence;
    notes: string;
    supersedes_ts: string | null;
}

// One entry in the precomputed sense inventory fan served by GET /api/grading/senses.
// Ranked by (tagcount DESC, sensenum ASC) in the inventory; intended sense is
// pre-lit in the UI regardless of rank.
export interface SenseInventoryItem {
    synset_id: string;
    sensenum: number;
    tagcount: number | null;
    definition: string | null;
    pos: string | null;
}

// Response shape from GET /api/grading/senses?key=<canonical_phrase>.
export interface SenseInventoryResponse {
    key: string;
    senses: SenseInventoryItem[];
}

// Map from canonical phrase key → ranked sense list (mirrors the JSONL inventory).
// Passed into mf-grade-panel as `senseInventories`; mf-app is responsible for
// pre-loading this map so the panel stays fetch-free and testable without mocks.
export type SenseInventoryMap = Record<string, SenseInventoryItem[]>;

// Emitted by mf-grade-panel on a metaphor submit. Carries both axes, multi-select tiers,
// confidence and notes — mf-app assembles the v2 JudgementRecord from this.
// `step_apt_senses` carries OPERATOR ticks only (the intended sense from each step's
// `synset_id` is excluded — it is already in the ChainStep record).
export interface VerdictSubmitDetail {
    linkage: Linkage;
    metaphor: MetaphorVerdict;
    tiers: Tier[];
    tags: Tag[];
    confidence: Confidence;
    notes: string;
    step_apt_senses: StepAptSense[];
}

export interface TopicSummary {
    topic: string;
    topic_synset_id: string;
}

// synset_id → WordNet gloss + POS, served by GET /api/grading/glosses. Lets the
// grade panel show the topic's sense (noun vs adjective for "antique", etc.).
export interface Gloss {
    pos: string | null;
    definition: string | null;
}
export type GlossMap = Record<string, Gloss>;

// One step of the signal-prioritised grading walk (GET /api/grading/walk). The
// server orders these by acquisition value (per-topic dwell, label-coverage
// steering); the client never re-sorts. `record` is the full chain for rendering.
//
// NOTE: the server also attaches the triage `liveness` score and structural
// flags that DROVE the ordering, but they are deliberately omitted from this
// type — surfacing a predicted score/flag would anchor the grader's fresh
// judgement. The walk consumes only ordering + dwell position, never the priors.
export interface WalkEntry {
    chain_signature: string;
    topic: string;
    vehicle: string;
    dwell_index: number;
    dwell_n: number;
    record: ChainRecord;
}

export interface WalkResponse {
    count: number;
    entries: WalkEntry[];
}

// Guided walk (GET /api/grading/guided-walk): an exact prefilled candidate order.
// No dwell/triage priors — the server withholds the stored judge_verdict + cohort
// (anchoring guard), so the client only ever sees the chain + its list position.
export interface GuidedEntry {
    chain_signature: string;
    topic: string;
    vehicle: string;
    order: number;
    record: ChainRecord;
}

export interface GuidedWalkResponse {
    count: number;
    batch: string | null;
    entries: GuidedEntry[];
}

// On-demand signal/coverage report (GET /api/grading/signal). Re-read after a
// grading batch: coverage = the binding breadth constraint; geometry = the
// within-topic "one big leap" concordance (max_hop_cos etc.).
export interface SignalTopic {
    topic_synset_id: string;
    topic: string;
    live: number;
    dead: number;
    pairs: number;
}

export interface SignalFeature {
    name: string;
    within_topic_auc: number | null;
    n_pairs: number;
}

export interface SignalReport {
    n: number;
    n_live: number;
    n_dead: number;
    base_rate_live: number;
    n_topics: number;
    n_both_class_topics: number;
    n_powered_topics: number;
    // Rows tagged bad_head (a mis-snapped INTERMEDIATE head — endpoints are pinned,
    // so the pairing stays valid). Kept in the live/dead counts; held out only of the
    // geometry concordance (unreliable synset). Surfaced as a data-quality flag —
    // head-extraction is known broken. Still counts as bad linkage below.
    n_bad_head: number;
    // Linkage axis re-derived from tags: bad if linkage=bad OR any of {bad_head,
    // leap, merge}. Corrects the lazy "didn't tap bad-linkage" default on tagged rows.
    n_linkage_good: number;
    n_linkage_bad: number;
    per_topic: SignalTopic[];
    geometry_available: boolean;
    geometry_features: SignalFeature[];
    server_ts: string;
}

// Blind re-grade self-agreement (GET /api/grading/regrade/agreement). Per verdict
// axis: raw observed agreement + 2-class Cohen's κ. Both null where undefined
// (no overlapping pairs, or every label identical). This is the intra-rater
// reliability FLOOR — the audit's prerequisite before any κ gate is interpretable.
export interface AxisAgreement {
    agreement: number | null;
    kappa: number | null;
}
export interface RegradeAgreement {
    n_pairs: number;
    metaphor: AxisAgreement;
    linkage: AxisAgreement;
}

// Normalised two-axis view of a stored judgement, regardless of v1/v2 source.
// linkage/metaphor may be null where a flat v1 label carried no signal on that axis.
export interface NormalisedJudgement {
    linkage: Linkage | null;
    metaphor: MetaphorVerdict | null;
    tiers: Tier[];
    tags: Tag[];
}

// --- Sense-check (anchors snap-correctness to human gold) ---
// 'split' means the snapper conflated multiple distinct senses for this endpoint —
// flag for per-sense splitting. Carries no intended_synset_id (like 'right'/'unsure').
export type SenseVerdict = 'right' | 'wrong' | 'rare_ok' | 'unsure' | 'split';

export interface SenseCandidate {
    synset_id: string;
    pos: string | null;
    gloss: string | null;
    tagcount: number | null;
}

export interface SenseContextChain {
    topic: string;
    vehicle: string;
    chain: ChainStep[];
    chain_signature: string;
    topic_pos: string | null;
    topic_gloss: string | null;
}

export interface SenseCheckItem {
    role: 'topic' | 'vehicle';
    word: string;
    snapped_synset_id: string;
    stratum: string;
    snapped_gloss: string | null;
    pos: string | null;
    candidates: SenseCandidate[];
    context: { chains: SenseContextChain[] };
    chain_signature: string | null;
}

export interface SenseCheckSample {
    count: number;
    items: SenseCheckItem[];
}

// Posted on each verdict. ts is server-injected (omit on construction).
export interface SenseLabel {
    schema_version: 'sense_label.v1';
    ts?: string;
    role: 'topic' | 'vehicle';
    word: string;
    snapped_synset_id: string;
    verdict: SenseVerdict;
    intended_synset_id: string | null;
    // Multi-select apt senses for 'split' verdict: the synset_ids the operator ticked.
    // Empty array for all other verdicts.
    apt_synset_ids: string[];
    chain_signature: string | null;
}

// v1 `label` → (linkage, metaphor). None where the flat label carried no signal on that
// axis: bad_path only asserted a broken route (metaphor unknown); irrelevant means the
// pairing is unconnected (linkage moot). Mirrors _V1_LABEL_MAP in the Python sidecar.
const V1_LABEL_MAP: Record<Label, [Linkage | null, MetaphorVerdict | null]> = {
    live: ['good', 'live'],
    dead: ['good', 'dead'],
    bad_path: ['bad', null],
    irrelevant: [null, 'irrelevant'],
};

// Read-side mirror of the Python normalise_judgement: maps a stored record (v1 `label`
// or v2 axes) to the uniform two-axis view consumers expect. Non-destructive.
export function normaliseJudgement(
    raw: { linkage?: Linkage; metaphor?: MetaphorVerdict; tiers?: Tier[]; tags?: Tag[]; label?: Label },
): NormalisedJudgement {
    if (raw.linkage !== undefined || raw.metaphor !== undefined) {
        return {
            linkage: raw.linkage ?? null,
            metaphor: raw.metaphor ?? null,
            tiers: raw.tiers ?? [],
            tags: raw.tags ?? [],
        };
    }
    const [linkage, metaphor] = raw.label
        ? V1_LABEL_MAP[raw.label]
        : [null, null];
    return { linkage, metaphor, tiers: [], tags: [] };
}
