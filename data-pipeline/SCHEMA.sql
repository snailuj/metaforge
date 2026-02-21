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
    source TEXT NOT NULL DEFAULT 'pilot',
    idf REAL
);

CREATE INDEX idx_property_vocabulary_text ON property_vocabulary(text);
CREATE INDEX idx_property_vocabulary_oov ON property_vocabulary(is_oov);

CREATE TABLE synset_properties (
    synset_id TEXT NOT NULL,
    property_id INTEGER NOT NULL,
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

-- ============================================================
-- Computed tables (populated by pipeline, empty at creation)
-- ============================================================

CREATE TABLE IF NOT EXISTS property_similarity (
    property_id_a INTEGER NOT NULL,
    property_id_b INTEGER NOT NULL,
    similarity REAL NOT NULL,
    PRIMARY KEY (property_id_a, property_id_b)
);

CREATE INDEX IF NOT EXISTS idx_property_similarity_a ON property_similarity(property_id_a);
CREATE INDEX IF NOT EXISTS idx_property_similarity_b ON property_similarity(property_id_b);
CREATE INDEX IF NOT EXISTS idx_property_similarity_score ON property_similarity(similarity);

CREATE TABLE IF NOT EXISTS synset_centroids (
    synset_id TEXT PRIMARY KEY,
    centroid BLOB NOT NULL,
    property_count INTEGER NOT NULL
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

CREATE TABLE IF NOT EXISTS property_antonyms (
    vocab_id_a  INTEGER NOT NULL,
    vocab_id_b  INTEGER NOT NULL,
    FOREIGN KEY (vocab_id_a) REFERENCES property_vocab_curated(vocab_id),
    FOREIGN KEY (vocab_id_b) REFERENCES property_vocab_curated(vocab_id),
    PRIMARY KEY (vocab_id_a, vocab_id_b)
);
