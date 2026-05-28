-- Metaforge lexicon_v2 schema
--
-- Canonical DDL for all tables and indexes. Used by import_raw.sh to create
-- an empty database before importing raw sources.
--
-- Keep this file in sync with any migrations. If you add, remove, or alter
-- a table, update this file and commit alongside the migration.

-- ============================================================
-- OEWN Core
-- ============================================================

CREATE TABLE synsets (
    synset_id TEXT PRIMARY KEY,
    pos TEXT NOT NULL CHECK (pos IN ('n', 'v', 'a', 'r', 's')),
    definition TEXT NOT NULL
);

CREATE TABLE lemmas (
    lemma TEXT NOT NULL,
    synset_id TEXT NOT NULL,
    FOREIGN KEY (synset_id) REFERENCES synsets(synset_id),
    PRIMARY KEY (lemma, synset_id)
);

CREATE TABLE relations (
    source_synset TEXT NOT NULL,
    target_synset TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    FOREIGN KEY (source_synset) REFERENCES synsets(synset_id),
    FOREIGN KEY (target_synset) REFERENCES synsets(synset_id)
);

CREATE INDEX idx_lemmas_lemma ON lemmas(lemma);
-- idx_lemmas_synset_id covers the reverse lookup ("which lemmas does
-- this synset have?") used by the cascade forge query's correlated
-- subquery `SELECT lemma FROM lemmas WHERE synset_id = ?`. Without it,
-- SQLite scans the entire lemmas table (~185k rows) per result row,
-- making broad-lemma /forge/suggest requests 3-4s instead of ~350ms.
-- The PRIMARY KEY (lemma, synset_id) is leftmost-prefix only and
-- cannot serve queries on synset_id alone.
CREATE INDEX idx_lemmas_synset_id ON lemmas(synset_id);
CREATE INDEX idx_relations_source ON relations(source_synset);
CREATE INDEX idx_relations_type ON relations(relation_type);

CREATE TABLE frequencies (
    lemma TEXT PRIMARY KEY,
    familiarity REAL,
    familiarity_dominant INTEGER,
    zipf REAL,
    frequency INTEGER,
    rarity TEXT NOT NULL DEFAULT 'unusual'
        CHECK (rarity IN ('common', 'unusual', 'rare')),
    source TEXT
);

CREATE INDEX idx_frequencies_lemma ON frequencies(lemma);
CREATE INDEX idx_frequencies_zipf ON frequencies(zipf);
CREATE INDEX idx_frequencies_rarity ON frequencies(rarity);
CREATE INDEX idx_frequencies_familiarity ON frequencies(familiarity);

-- ============================================================
-- VerbNet (classes, roles, examples, members)
-- ============================================================

CREATE TABLE vn_classes (
    class_id INTEGER PRIMARY KEY,
    class_name TEXT NOT NULL UNIQUE,
    class_definition TEXT
);

CREATE TABLE vn_class_members (
    wordid INTEGER NOT NULL,
    synsetid TEXT NOT NULL,
    classid INTEGER NOT NULL,
    vnwordid INTEGER NOT NULL,
    FOREIGN KEY (synsetid) REFERENCES synsets(synset_id),
    FOREIGN KEY (classid) REFERENCES vn_classes(class_id),
    PRIMARY KEY (wordid, synsetid, classid)
);

CREATE TABLE vn_roles (
    role_id INTEGER PRIMARY KEY,
    class_id INTEGER NOT NULL,
    theta_role TEXT NOT NULL,
    FOREIGN KEY (class_id) REFERENCES vn_classes(class_id)
);

CREATE TABLE vn_examples (
    example_id INTEGER PRIMARY KEY,
    class_id INTEGER NOT NULL,
    example_text TEXT NOT NULL,
    FOREIGN KEY (class_id) REFERENCES vn_classes(class_id)
);

CREATE INDEX idx_vn_class_members_synset ON vn_class_members(synsetid);
CREATE INDEX idx_vn_class_members_class ON vn_class_members(classid);

-- ============================================================
-- SyntagNet (collocation pairs)
-- ============================================================

CREATE TABLE syntagms (
    syntagm_id INTEGER PRIMARY KEY,
    synset1id TEXT NOT NULL,
    synset2id TEXT NOT NULL,
    sensekey1 TEXT NOT NULL,
    sensekey2 TEXT NOT NULL,
    word1id INTEGER NOT NULL,
    word2id INTEGER NOT NULL,
    FOREIGN KEY (synset1id) REFERENCES synsets(synset_id),
    FOREIGN KEY (synset2id) REFERENCES synsets(synset_id)
);

CREATE INDEX idx_syntagms_synset1 ON syntagms(synset1id);
CREATE INDEX idx_syntagms_synset2 ON syntagms(synset2id);

-- ============================================================
-- FrameNet frames (metadata for semantic constraints)
-- ============================================================

CREATE TABLE fn_frames (
    frame_id INTEGER PRIMARY KEY,
    frame_name TEXT NOT NULL UNIQUE,
    frame_definition TEXT NOT NULL
);

CREATE TABLE fn_frame_synsets (
    frame_id INTEGER NOT NULL,
    synset_id TEXT NOT NULL,
    FOREIGN KEY (frame_id) REFERENCES fn_frames(frame_id),
    FOREIGN KEY (synset_id) REFERENCES synsets(synset_id),
    PRIMARY KEY (frame_id, synset_id)
);

CREATE INDEX idx_fn_frame_synsets_synset ON fn_frame_synsets(synset_id);
CREATE INDEX idx_fn_frame_synsets_frame ON fn_frame_synsets(frame_id);

-- ============================================================
-- Property dimensions (optional, for UI filtering)
-- ============================================================

CREATE TABLE property_dimensions (
    dimension_id INTEGER PRIMARY KEY,
    dimension_name TEXT NOT NULL UNIQUE,
    dimension_category TEXT NOT NULL
);

CREATE TABLE property_dimension_map (
    property_id INTEGER NOT NULL,
    dimension_id INTEGER NOT NULL,
    FOREIGN KEY (property_id) REFERENCES property_vocabulary(property_id),
    FOREIGN KEY (dimension_id) REFERENCES property_dimensions(dimension_id),
    PRIMARY KEY (property_id, dimension_id)
);

CREATE TABLE frame_dimensions (
    frame_id INTEGER NOT NULL,
    dimension_id INTEGER NOT NULL,
    FOREIGN KEY (frame_id) REFERENCES fn_frames(frame_id),
    FOREIGN KEY (dimension_id) REFERENCES property_dimensions(dimension_id),
    PRIMARY KEY (frame_id, dimension_id)
);

-- ============================================================
-- Enrichment tables (empty at creation, populated by pipeline)
-- ============================================================

CREATE TABLE enrichment (
    synset_id TEXT PRIMARY KEY,
    connotation TEXT CHECK (connotation IN ('positive', 'neutral', 'negative')),
    register TEXT CHECK (register IN ('formal', 'neutral', 'informal', 'slang')),
    usage_example TEXT,
    model_used TEXT,
    extracted_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (synset_id) REFERENCES synsets(synset_id)
);

CREATE TABLE property_vocabulary (
    property_id INTEGER PRIMARY KEY,
    text TEXT NOT NULL UNIQUE,
    embedding BLOB,
    is_oov INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'pilot'
);

CREATE INDEX idx_property_vocabulary_text ON property_vocabulary(text);
CREATE INDEX idx_property_vocabulary_oov ON property_vocabulary(is_oov);

CREATE TABLE synset_properties (
    synset_id TEXT NOT NULL,
    property_id INTEGER NOT NULL,
    -- salience is an LLM-emitted weight in [0.0, 1.0]; bound the column so a
    -- prompt regression or schema drift cannot persist negative or >1 weights
    -- silently. Mirrors the synset_concreteness.score precedent set in M01.
    salience REAL NOT NULL DEFAULT 1.0 CHECK (salience >= 0.0 AND salience <= 1.0),
    property_type TEXT,
    relation TEXT,
    FOREIGN KEY (synset_id) REFERENCES enrichment(synset_id),
    FOREIGN KEY (property_id) REFERENCES property_vocabulary(property_id),
    PRIMARY KEY (synset_id, property_id)
);

CREATE INDEX idx_sp_synset ON synset_properties(synset_id);
CREATE INDEX idx_sp_property ON synset_properties(property_id);

CREATE TABLE synset_metonyms (
    synset_id TEXT NOT NULL,
    metonym_syntagm_id INTEGER NOT NULL,
    metonym_rank INTEGER NOT NULL,
    FOREIGN KEY (synset_id) REFERENCES enrichment(synset_id),
    FOREIGN KEY (metonym_syntagm_id) REFERENCES syntagms(syntagm_id),
    PRIMARY KEY (synset_id, metonym_syntagm_id)
);

CREATE INDEX idx_synset_metonyms_synset ON synset_metonyms(synset_id);

CREATE TABLE lemma_metadata (
    lemma       TEXT NOT NULL,
    synset_id   TEXT NOT NULL,
    register    TEXT CHECK (register IN ('formal', 'neutral', 'informal', 'slang')),
    connotation TEXT CHECK (connotation IN ('positive', 'neutral', 'negative')),
    PRIMARY KEY (lemma, synset_id)
);

-- ============================================================
-- Curated vocabulary (populated by build_vocab.py + build_antonyms.py)
-- ============================================================

CREATE TABLE IF NOT EXISTS property_vocab_curated (
    vocab_id    INTEGER PRIMARY KEY,
    synset_id   TEXT NOT NULL,
    lemma       TEXT NOT NULL,
    pos         TEXT NOT NULL,
    polysemy    INTEGER NOT NULL,
    UNIQUE(synset_id)
);

CREATE INDEX IF NOT EXISTS idx_vocab_curated_lemma ON property_vocab_curated(lemma);

CREATE TABLE IF NOT EXISTS lemma_embeddings (
    lemma     TEXT PRIMARY KEY,
    embedding BLOB NOT NULL
);

CREATE TABLE IF NOT EXISTS vocab_clusters (
    vocab_id         INTEGER PRIMARY KEY,
    cluster_id       INTEGER NOT NULL,
    is_representative INTEGER NOT NULL DEFAULT 0,
    is_singleton     INTEGER NOT NULL DEFAULT 0,
    dominant_type    TEXT CHECK (dominant_type IS NULL OR dominant_type IN
        ('sensorimotor', 'behaviour', 'functional', 'effect',
         'emotional', 'social', 'other'))
                           -- M05: dominant property type for this cluster, populated by snap_properties.py
                           -- after all snapping completes. One of: sensorimotor, behaviour, functional,
                           -- effect, emotional, social, other. NULL until first snap-with-types run.
);

CREATE INDEX IF NOT EXISTS idx_vocab_clusters_cluster ON vocab_clusters(cluster_id);

CREATE TABLE IF NOT EXISTS synset_properties_curated (
    synset_id    TEXT NOT NULL,
    vocab_id     INTEGER NOT NULL,
    cluster_id   INTEGER NOT NULL,
    -- snap_method is a closed enum written by snap_properties.py; constrain it
    -- so an unexpected snap path (or a typo) cannot be persisted silently.
    -- Mirrors the existing enum CHECKs on enrichment.connotation/register.
    snap_method  TEXT NOT NULL CHECK (snap_method IN ('exact', 'morphological', 'embedding')),
    -- snap_score is a cosine similarity (only set for the embedding path).
    -- Clamped to [-1.0, 1.0] at write time by snap_properties.py (commit
    -- 7a334528). A strict [-1.0, 1.0] CHECK is deferred — D6 in
    -- docs/superpowers/review-logs/2026-05-08-review-m01-and-snap-memopt-review.md:
    -- the live DB has one float32-drift outlier (1.00000011920929) the
    -- CHECK would reject until renormalised on the next snap rebuild,
    -- after which the CHECK lands without preconditions.
    snap_score   REAL,
    -- salience_sum is a non-negative accumulator over multiple LLM properties
    -- snapping into the same cluster; bound it so a sign/NaN regression in
    -- snap_properties.py cannot persist silently.
    salience_sum REAL NOT NULL DEFAULT 1.0 CHECK (salience_sum >= 0.0),
    PRIMARY KEY (synset_id, cluster_id)
);

CREATE INDEX IF NOT EXISTS idx_spc_synset ON synset_properties_curated(synset_id);
CREATE INDEX IF NOT EXISTS idx_spc_cluster ON synset_properties_curated(cluster_id);
CREATE INDEX IF NOT EXISTS idx_spc_vocab ON synset_properties_curated(vocab_id);

CREATE TABLE IF NOT EXISTS property_antonyms (
    vocab_id_a  INTEGER NOT NULL,
    vocab_id_b  INTEGER NOT NULL,
    FOREIGN KEY (vocab_id_a) REFERENCES property_vocab_curated(vocab_id),
    FOREIGN KEY (vocab_id_b) REFERENCES property_vocab_curated(vocab_id),
    PRIMARY KEY (vocab_id_a, vocab_id_b)
);

CREATE TABLE IF NOT EXISTS cluster_antonyms (
    cluster_id_a INTEGER NOT NULL,
    cluster_id_b INTEGER NOT NULL,
    PRIMARY KEY (cluster_id_a, cluster_id_b)
);

-- ============================================================
-- Concreteness (Brysbaert ground truth)
-- ============================================================
-- Populated by import_concreteness.py from Brysbaert et al. (2014).
-- Used as training data by predict_concreteness.py to fill gaps via k-NN
-- regression over FastText embeddings during enrich.sh Step 4.

CREATE TABLE IF NOT EXISTS synset_concreteness (
    synset_id TEXT PRIMARY KEY,
    -- Brysbaert concreteness lives on a 1.0-5.0 Likert scale; bound the
    -- column so a regression bug (NaN, extrapolation) cannot persist
    -- silently corrupt scores.
    score REAL NOT NULL CHECK (score >= 1.0 AND score <= 5.0),
    source TEXT NOT NULL,
    FOREIGN KEY (synset_id) REFERENCES synsets(synset_id)
);

-- ============================================================
-- Metaphor graph (2026-05-28)
-- ============================================================
-- Bridge-centric layer: a proposal is (topic, vehicle, path) where the
-- path is an ordered list of intermediate synsets. Cascade and LLM
-- proposers share one pool. Judgments attach per (bridge, judge).
-- Spec: docs/superpowers/specs/2026-05-28-metaphor-graph-schema-design.md

CREATE TABLE IF NOT EXISTS metaphor_bridges (
    bridge_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_synset_id    TEXT NOT NULL REFERENCES synsets(synset_id),
    vehicle_synset_id  TEXT NOT NULL REFERENCES synsets(synset_id),
    proposer           TEXT NOT NULL,
    proposed_at        TEXT NOT NULL,
    path_hash          TEXT NOT NULL CHECK (length(path_hash) = 64
                                            AND NOT path_hash GLOB '*[^0-9a-f]*'),
    rationale          TEXT,
    cosine_distance    REAL,
    ortony_score       REAL,
    cascade_score      REAL,
    signed_delta       REAL,
    CHECK (topic_synset_id != vehicle_synset_id),
    CHECK (length(proposer) > 0),
    CHECK (length(proposed_at) > 0),
    UNIQUE (topic_synset_id, vehicle_synset_id, proposer, path_hash)
);

CREATE INDEX IF NOT EXISTS idx_metaphor_bridges_topic
    ON metaphor_bridges(topic_synset_id);
CREATE INDEX IF NOT EXISTS idx_metaphor_bridges_vehicle
    ON metaphor_bridges(vehicle_synset_id);
CREATE INDEX IF NOT EXISTS idx_metaphor_bridges_proposer
    ON metaphor_bridges(proposer);

CREATE TABLE IF NOT EXISTS metaphor_bridge_steps (
    bridge_id          INTEGER NOT NULL REFERENCES metaphor_bridges(bridge_id) ON DELETE CASCADE,
    step_index         INTEGER NOT NULL,
    via_synset_id      TEXT NOT NULL REFERENCES synsets(synset_id),
    PRIMARY KEY (bridge_id, step_index)
);

CREATE INDEX IF NOT EXISTS idx_metaphor_bridge_steps_via
    ON metaphor_bridge_steps(via_synset_id);

CREATE TABLE IF NOT EXISTS metaphor_judgments (
    judgment_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    bridge_id          INTEGER NOT NULL REFERENCES metaphor_bridges(bridge_id) ON DELETE CASCADE,
    label              TEXT NOT NULL CHECK (label IN
                         ('live','dead_synonym','dead_lakoff','irrelevant','edge_case')),
    judged_by          TEXT NOT NULL,
    judged_at          TEXT NOT NULL,
    confidence         REAL,
    notes              TEXT,
    CHECK (confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)),
    CHECK (length(judged_by) > 0),
    CHECK (length(judged_at) > 0),
    UNIQUE (bridge_id, judged_by)
);

CREATE INDEX IF NOT EXISTS idx_metaphor_judgments_label
    ON metaphor_judgments(label);
CREATE INDEX IF NOT EXISTS idx_metaphor_judgments_judged_by
    ON metaphor_judgments(judged_by);

-- Unified graph view: existing relation tables + judged-live metaphor links
DROP VIEW IF EXISTS graph_edges;

-- Row-multiplicity note: this view does NOT deduplicate. UNION arms can emit
-- multiple rows for the same logical edge:
--   has_property:  one row per curated property-cluster shared (1:1 in practice
--                  given the snap pipeline's idempotency, but not enforced here)
--   metonym_of:    one row per (synset_id, metonym_syntagm_id); distinct
--                  syntagms can link the same (src, dst) synset pair
--   antonym_of:    property_antonyms stores both (a,b) and (b,a) — bidirectional
--                  fan-out is preserved here, NOT collapsed
--   metaphor_link: one row per (bridge_id, judge); with multiple judges (e.g.
--                  julian + llm_judge_v1) the same live bridge emits N rows
-- Consumers wanting unique (src, dst[, bridge_id]) edges must apply DISTINCT
-- or aggregate. This preserves raw signal at the view layer; aggregation
-- belongs in the consumer.
CREATE VIEW graph_edges AS
SELECT
    spc.synset_id     AS src_synset_id,
    pvc.synset_id     AS dst_synset_id,
    'has_property'    AS relation,
    spc.salience_sum  AS weight,
    NULL              AS bridge_id
FROM synset_properties_curated spc
JOIN property_vocab_curated pvc ON pvc.vocab_id = spc.vocab_id
UNION ALL
-- metonym_of: directional, src=sm.synset_id, dst=the OTHER endpoint of the
-- syntagm. WHERE clause drops (a) rows whose sm.synset_id doesn't match
-- either endpoint (phantom-edge fix, round 1) and (b) self-syntagms where
-- synset1id == synset2id (self-loop fix, round 2). Upstream
-- synset_metonyms direction convention is "synset_id IS a metonym of the
-- other endpoint" — see import_syntagnet.py for the import semantics.
SELECT
    sm.synset_id                                                            AS src_synset_id,
    CASE WHEN s.synset1id = sm.synset_id THEN s.synset2id ELSE s.synset1id END AS dst_synset_id,
    'metonym_of'                                                            AS relation,
    NULL                                                                    AS weight,
    NULL                                                                    AS bridge_id
FROM synset_metonyms sm
JOIN syntagms s ON s.syntagm_id = sm.metonym_syntagm_id
WHERE sm.synset_id IN (s.synset1id, s.synset2id)
  AND s.synset1id != s.synset2id
UNION ALL
SELECT
    pa.synset_id   AS src_synset_id,
    pb.synset_id   AS dst_synset_id,
    'antonym_of'   AS relation,
    NULL           AS weight,
    NULL           AS bridge_id
FROM property_antonyms pant
JOIN property_vocab_curated pa ON pa.vocab_id = pant.vocab_id_a
JOIN property_vocab_curated pb ON pb.vocab_id = pant.vocab_id_b
UNION ALL
SELECT
    mb.topic_synset_id   AS src_synset_id,
    mb.vehicle_synset_id AS dst_synset_id,
    'metaphor_link'      AS relation,
    mj.confidence        AS weight,
    mb.bridge_id         AS bridge_id
FROM metaphor_bridges mb
JOIN metaphor_judgments mj ON mj.bridge_id = mb.bridge_id
WHERE mj.label = 'live';
