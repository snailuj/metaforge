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
export type Tag = 'merge' | 'padding' | 'leap' | 'bad_head' | 'other';
export const TAGS: readonly Tag[] = ['merge', 'padding', 'leap', 'bad_head', 'other'] as const;
export type Confidence = 'high' | 'med' | 'low';

export interface ChainStep {
    phrase: string;
    head: string;
    synset_id: string | null;
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

// Emitted by mf-grade-panel on a metaphor submit. Carries both axes, multi-select tiers,
// confidence and notes — mf-app assembles the v2 JudgementRecord from this.
export interface VerdictSubmitDetail {
    linkage: Linkage;
    metaphor: MetaphorVerdict;
    tiers: Tier[];
    tags: Tag[];
    confidence: Confidence;
    notes: string;
}

export interface TopicSummary {
    topic: string;
    topic_synset_id: string;
}

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

// Normalised two-axis view of a stored judgement, regardless of v1/v2 source.
// linkage/metaphor may be null where a flat v1 label carried no signal on that axis.
export interface NormalisedJudgement {
    linkage: Linkage | null;
    metaphor: MetaphorVerdict | null;
    tiers: Tier[];
    tags: Tag[];
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
