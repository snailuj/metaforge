export type Label = 'live' | 'dead' | 'bad_path' | 'irrelevant';
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
    schema_version: 'judgement.v1';
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
    label: Label;
    confidence: Confidence;
    notes: string;
    supersedes_ts: string | null;
}

export interface TopicSummary {
    topic: string;
    topic_synset_id: string;
}
