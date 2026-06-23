"""Additively add the SQLUNET SemCor/domains/BNC/provenance tables to an EXISTING
lexicon_v2.db — no destructive rebuild.

Why this exists: the canonical clean rebuild (import_raw.sh) is currently blocked
by a pre-existing import_familiarity.py <-> xlsx drift, and would in any case
regenerate `frequencies` from a *newer* GPT-familiarity source than production
was tuned on. This migration preserves the exact production frequencies/
enrichment and only adds the new, independently-validated tables (reusing the
committed importer functions). Idempotent / re-runnable. Use it on already-built
DBs (incl. deploy worktrees). When import_familiarity is fixed, prefer the clean
rebuild. See docs/inbox/2026-06-05-sqlunet-data-strategy-review.md.
"""
import sqlite3

from utils import SQLUNET_DB, LEXICON_V2
import import_domains
import import_semcor
import import_bnc
import import_provenance

# Mirrors the new section added to SCHEMA.sql (IF NOT EXISTS for idempotency).
NEW_DDL = """
CREATE TABLE IF NOT EXISTS domains (
    domainid   INTEGER PRIMARY KEY,
    domain     TEXT NOT NULL,
    domainname TEXT NOT NULL,
    posid      TEXT NOT NULL CHECK (posid IN ('n','v','a','r','s'))
);
CREATE TABLE IF NOT EXISTS sense_attributes (
    sensekey  TEXT PRIMARY KEY,
    lemma     TEXT NOT NULL,
    synset_id TEXT NOT NULL,
    sensenum  INTEGER,
    tagcount  INTEGER,
    FOREIGN KEY (synset_id) REFERENCES synsets(synset_id)
);
CREATE INDEX IF NOT EXISTS idx_sense_attributes_lemma ON sense_attributes(lemma);
CREATE INDEX IF NOT EXISTS idx_sense_attributes_synset ON sense_attributes(synset_id);
CREATE INDEX IF NOT EXISTS idx_sense_attributes_lemma_tagcount ON sense_attributes(lemma, tagcount);
CREATE TABLE IF NOT EXISTS bnc_frequencies (
    lemma TEXT NOT NULL,
    pos   TEXT NOT NULL CHECK (pos IN ('n','v','a','r','s')),
    freq  INTEGER NOT NULL,
    PRIMARY KEY (lemma, pos)
);
CREATE INDEX IF NOT EXISTS idx_bnc_frequencies_lemma ON bnc_frequencies(lemma);
CREATE TABLE IF NOT EXISTS seed_sources (
    idsource  INTEGER PRIMARY KEY,
    name TEXT NOT NULL, version TEXT, wnversion TEXT, url TEXT, provider TEXT, reference TEXT
);
CREATE TABLE IF NOT EXISTS seed_meta (created TEXT, dbsize INTEGER, build TEXT);
"""


def ensure_schema(dst: sqlite3.Connection):
    """Add synsets.domainid (guarded) + the new tables/indexes, idempotently."""
    cols = [r[1] for r in dst.execute("PRAGMA table_info(synsets)")]
    if "domainid" not in cols:
        dst.execute("ALTER TABLE synsets ADD COLUMN domainid INTEGER")
    dst.executescript(NEW_DDL)


def backfill_domainid(src: sqlite3.Connection, dst: sqlite3.Connection):
    """Set synsets.domainid from source — the existing synsets pre-date the
    column, and the importers' INSERT OR IGNORE never touches existing rows."""
    rows = src.execute("SELECT CAST(synsetid AS TEXT), domainid FROM synsets").fetchall()
    dst.executemany(
        "UPDATE synsets SET domainid = ? WHERE synset_id = ? AND domainid IS NULL",
        [(domainid, synset_id) for synset_id, domainid in rows],
    )


def migrate(src: sqlite3.Connection, dst: sqlite3.Connection):
    """Apply the additive schema + populate the new tables. Idempotent."""
    ensure_schema(dst)
    import_domains.import_domains(src, dst)
    import_semcor.import_sense_attributes(src, dst)
    import_bnc.import_bnc(src, dst)
    import_provenance.import_sources(src, dst)
    import_provenance.import_meta(src, dst)
    backfill_domainid(src, dst)


def main():
    if not SQLUNET_DB.exists():
        raise FileNotFoundError(f"Source DB not found: {SQLUNET_DB}")
    if not LEXICON_V2.exists():
        raise FileNotFoundError(f"Target DB not found: {LEXICON_V2}")

    src = sqlite3.connect(f"file:{SQLUNET_DB}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(LEXICON_V2)
        try:
            migrate(src, dst)
            dst.commit()
        finally:
            dst.close()
    finally:
        src.close()
    print("Additive SQLUNET migration complete!")


if __name__ == "__main__":
    main()
