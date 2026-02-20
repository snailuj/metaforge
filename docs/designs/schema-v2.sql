-- Schema v2: OEWN + VerbNet (selective) + SyntagNet + FrameNet frames + Property vocabulary
--
-- Migration from sch.v1:
--   RETAIN: synsets, lemmas, relations, frequencies (OEWN core)
--   RETAIN: embeddings.bin (FastText 300d, external file)
--   ADD: VerbNet selective tables
--   ADD: SyntagNet collocation pairs
--   ADD: FrameNet frame metadata
--   ADD: Property vocabulary with embeddings
--   MODIFY: enrichment table (property_ids instead of JSON array)

-- ============================================================
-- OEWN Core (retained from sch.v1, unchanged)
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
-- VerbNet Selective Integration (classes, roles, examples only)
-- ============================================================

CREATE TABLE vn_classes (
    class_id INTEGER PRIMARY KEY,
    class_name TEXT NOT NULL UNIQUE,  -- e.g., "51.2", "45.4"
    class_definition TEXT
);

CREATE TABLE vn_class_members (
    wordid INTEGER NOT NULL,          -- VerbNet internal word ID
    synsetid TEXT NOT NULL,           -- Link to OEWN synsets
    classid INTEGER NOT NULL,
    vnwordid INTEGER NOT NULL,        -- VerbNet member ID
    FOREIGN KEY (synsetid) REFERENCES synsets(synset_id),
    FOREIGN KEY (classid) REFERENCES vn_classes(class_id),
    PRIMARY KEY (wordid, synsetid, classid)
);

CREATE TABLE vn_roles (
    role_id INTEGER PRIMARY KEY,
    class_id INTEGER NOT NULL,
    theta_role TEXT NOT NULL,         -- Agent, Theme, Patient, Instrument, etc.
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
-- SyntagNet (collocation pairs for contiguity metonyms)
-- ============================================================

CREATE TABLE syntagms (
    syntagm_id INTEGER PRIMARY KEY,
    synset1id TEXT NOT NULL,          -- First word sense
    synset2id TEXT NOT NULL,          -- Second word sense
    sensekey1 TEXT NOT NULL,          -- WordNet sense key
    sensekey2 TEXT NOT NULL,          -- WordNet sense key
    word1id INTEGER NOT NULL,         -- SyntagNet word ID
    word2id INTEGER NOT NULL,         -- SyntagNet word ID
    FOREIGN KEY (synset1id) REFERENCES synsets(synset_id),
    FOREIGN KEY (synset2id) REFERENCES synsets(synset_id)
);

CREATE INDEX idx_syntagms_synset1 ON syntagms(synset1id);
CREATE INDEX idx_syntagms_synset2 ON syntagms(synset2id);

-- ============================================================
-- FrameNet Frames (metadata only for semantic constraints)
-- ============================================================

CREATE TABLE fn_frames (
    frame_id INTEGER PRIMARY KEY,
    frame_name TEXT NOT NULL UNIQUE,  -- e.g., "Communication", "Motion"
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
-- Property Vocabulary with Embeddings
-- ============================================================

-- Property vocabulary: curated properties with FastText embeddings for fuzzy matching
-- Embeddings enable:
--   1. Synonym clustering (reduce/decrease/lower cluster naturally)
--   2. Confidence scoring (distance between properties)
--   3. "Stretch" metaphor discovery (nearby but not identical properties)
CREATE TABLE property_vocabulary (
    property_id INTEGER PRIMARY KEY,
    text TEXT NOT NULL UNIQUE,            -- Normalised property (lemmatised)
    embedding BLOB,                       -- FastText 300d (1200 bytes) or NULL if OOV
    is_oov INTEGER NOT NULL DEFAULT 0,    -- 1 if out-of-vocabulary (flagged for review)
    source TEXT NOT NULL DEFAULT 'spike'  -- Origin: 'spike', 'curation', 'manual'
);

CREATE INDEX idx_property_vocabulary_text ON property_vocabulary(text);
CREATE INDEX idx_property_vocabulary_oov ON property_vocabulary(is_oov);

-- Optional: semantic dimensions for browsing/filtering (not required for matching)
-- Dimensions group properties by category (physical, behavioral, perceptual, etc.)
-- This is for UI organisation, not matching — embeddings handle similarity
CREATE TABLE property_dimensions (
    dimension_id INTEGER PRIMARY KEY,
    dimension_name TEXT NOT NULL UNIQUE,  -- e.g., "luminosity", "audibility", "speed"
    dimension_category TEXT NOT NULL      -- "physical", "behavioral", "perceptual", "social"
);

-- Optional mapping: property → dimension (for UI filtering)
CREATE TABLE property_dimension_map (
    property_id INTEGER NOT NULL,
    dimension_id INTEGER NOT NULL,
    FOREIGN KEY (property_id) REFERENCES property_vocabulary(property_id),
    FOREIGN KEY (dimension_id) REFERENCES property_dimensions(dimension_id),
    PRIMARY KEY (property_id, dimension_id)
);

-- Map frames to relevant property dimensions (constrains LLM selection)
-- NOTE: May be obviated if Task 1 spike shows embeddings provide sufficient consistency
CREATE TABLE frame_dimensions (
    frame_id INTEGER NOT NULL,
    dimension_id INTEGER NOT NULL,
    FOREIGN KEY (frame_id) REFERENCES fn_frames(frame_id),
    FOREIGN KEY (dimension_id) REFERENCES property_dimensions(dimension_id),
    PRIMARY KEY (frame_id, dimension_id)
);

-- ============================================================
-- Enrichment v2 (properties via junction table + contiguity metonyms)
-- ============================================================

CREATE TABLE enrichment (
    synset_id TEXT PRIMARY KEY,
    -- Properties: many-to-many via junction table
    connotation TEXT CHECK (connotation IN ('positive', 'neutral', 'negative')),
    register TEXT CHECK (register IN ('formal', 'neutral', 'informal', 'slang')),
    usage_example TEXT,
    model_used TEXT,
    extracted_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (synset_id) REFERENCES synsets(synset_id)
);

-- Junction table: synset → properties (many-to-many)
CREATE TABLE synset_properties (
    synset_id TEXT NOT NULL,
    property_id INTEGER NOT NULL,
    FOREIGN KEY (synset_id) REFERENCES enrichment(synset_id),
    FOREIGN KEY (property_id) REFERENCES property_vocabulary(property_id),
    PRIMARY KEY (synset_id, property_id)
);

-- Contiguity metonyms (from SyntagNet, stored as references not duplicated)
CREATE TABLE synset_metonyms (
    synset_id TEXT NOT NULL,
    metonym_syntagm_id INTEGER NOT NULL,  -- References syntagms table
    metonym_rank INTEGER NOT NULL,        -- 1, 2, 3 (top 3 collocates)
    FOREIGN KEY (synset_id) REFERENCES enrichment(synset_id),
    FOREIGN KEY (metonym_syntagm_id) REFERENCES syntagms(syntagm_id),
    PRIMARY KEY (synset_id, metonym_syntagm_id)
);

CREATE INDEX idx_synset_properties_synset ON synset_properties(synset_id);
CREATE INDEX idx_synset_properties_property ON synset_properties(property_id);
CREATE INDEX idx_synset_metonyms_synset ON synset_metonyms(synset_id);

-- ============================================================
-- Computed Tables (created by pipeline steps, not initial schema)
-- ============================================================

-- Pairwise property similarity (cosine similarity >= threshold).
-- Both directions stored for query convenience: (a,b) and (b,a).
CREATE TABLE IF NOT EXISTS property_similarity (
    property_id_a INTEGER NOT NULL,
    property_id_b INTEGER NOT NULL,
    similarity REAL NOT NULL,
    PRIMARY KEY (property_id_a, property_id_b),
    FOREIGN KEY (property_id_a) REFERENCES property_vocabulary(property_id),
    FOREIGN KEY (property_id_b) REFERENCES property_vocabulary(property_id)
);

CREATE INDEX IF NOT EXISTS idx_property_similarity_a ON property_similarity(property_id_a);
CREATE INDEX IF NOT EXISTS idx_property_similarity_b ON property_similarity(property_id_b);
CREATE INDEX IF NOT EXISTS idx_property_similarity_score ON property_similarity(similarity);

-- Per-synset centroid: average of its property embeddings (FastText 300d).
-- Precomputed to avoid N+1 queries in the Go API layer.
CREATE TABLE IF NOT EXISTS synset_centroids (
    synset_id TEXT PRIMARY KEY,
    centroid BLOB NOT NULL,
    property_count INTEGER NOT NULL
);

-- ============================================================
-- Curated Property Vocabulary (from build_vocab.py)
-- ============================================================

-- Canonical vocabulary entries: one lemma per synset, least-polysemous chosen
CREATE TABLE IF NOT EXISTS property_vocab_curated (
    vocab_id    INTEGER PRIMARY KEY,
    synset_id   TEXT NOT NULL,
    lemma       TEXT NOT NULL,
    pos         TEXT NOT NULL,
    polysemy    INTEGER NOT NULL,
    UNIQUE(synset_id)
);

CREATE INDEX IF NOT EXISTS idx_vocab_curated_lemma ON property_vocab_curated(lemma);

-- Snapped synset-property links (from snap_properties.py)
CREATE TABLE IF NOT EXISTS synset_properties_curated (
    synset_id   TEXT NOT NULL,
    vocab_id    INTEGER NOT NULL,
    snap_method TEXT NOT NULL,
    snap_score  REAL,
    FOREIGN KEY (vocab_id) REFERENCES property_vocab_curated(vocab_id),
    PRIMARY KEY (synset_id, vocab_id)
);

CREATE INDEX IF NOT EXISTS idx_spc_synset ON synset_properties_curated(synset_id);
CREATE INDEX IF NOT EXISTS idx_spc_vocab ON synset_properties_curated(vocab_id);

-- Antonym pairs via WordNet attribute relations (from build_antonyms.py)
CREATE TABLE IF NOT EXISTS property_antonyms (
    vocab_id_a  INTEGER NOT NULL,
    vocab_id_b  INTEGER NOT NULL,
    FOREIGN KEY (vocab_id_a) REFERENCES property_vocab_curated(vocab_id),
    FOREIGN KEY (vocab_id_b) REFERENCES property_vocab_curated(vocab_id),
    PRIMARY KEY (vocab_id_a, vocab_id_b)
);

-- ============================================================
-- Runtime Query Examples
-- ============================================================

-- Get all properties with embeddings for a synset (for matching)
-- SELECT pv.text, pv.embedding
-- FROM synset_properties sp
-- JOIN property_vocabulary pv ON pv.property_id = sp.property_id
-- WHERE sp.synset_id = ?;

-- Find synsets with similar properties (fuzzy match via embedding distance)
-- Application layer computes cosine similarity between embedding vectors

-- Get OOV properties needing review
-- SELECT text FROM property_vocabulary WHERE is_oov = 1;

-- ============================================================
-- Migration Notes
-- ============================================================

-- From sch.v1:
--   enrichment.properties was JSON array: ["prop1", "prop2", "prop3"]
--   enrichment.metonyms was JSON array: ["metonym1", "metonym2"]
--
-- In sch.v2:
--   synset_properties junction table: normalised many-to-many
--   synset_metonyms references syntagms table (avoid duplication)
--   property_vocabulary has embeddings for fuzzy matching
--
-- Benefits:
--   - Can query "all synsets with property X" efficiently
--   - Property vocabulary is centralised and curated
--   - Embeddings enable fuzzy matching without exact string equality
--   - Metonyms are sense-disambiguated via SyntagNet synset links
--   - OOV properties flagged for manual review
