// Package forestcache keeps finished metaphor forests in a writable SQLite
// file, a pool of up to poolSize per (pipeline version, word, max_hops).
package forestcache

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"time"

	_ "github.com/mattn/go-sqlite3"

	"github.com/snailuj/metaforge/internal/forest"
)

// Rows from other versions stay in the file as a corpus of past forests;
// only the store's own version is served or evicted.
const schema = `
CREATE TABLE IF NOT EXISTS forests (
	id         INTEGER PRIMARY KEY AUTOINCREMENT,
	version    TEXT    NOT NULL,
	word       TEXT    NOT NULL,
	max_hops   INTEGER NOT NULL,
	body       TEXT    NOT NULL,
	created_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_forests_pool ON forests(version, word, max_hops, id);
`

// Store is safe for concurrent use.
type Store struct {
	db       *sql.DB
	version  string
	poolSize int
}

// Open creates the file and schema if needed. version is the pipeline
// fingerprint (forest.Fingerprint) the store serves.
func Open(path, version string, poolSize int) (*Store, error) {
	if poolSize < 1 {
		return nil, fmt.Errorf("forest cache pool size must be at least 1, got %d", poolSize)
	}
	db, err := sql.Open("sqlite3", path+"?_journal_mode=WAL&_busy_timeout=5000")
	if err != nil {
		return nil, fmt.Errorf("open forest cache %s: %w", path, err)
	}
	// One connection serialises writers, so concurrent Adds never see
	// SQLITE_BUSY; every statement here is a small indexed lookup.
	db.SetMaxOpenConns(1)
	if _, err := db.Exec(schema); err != nil {
		db.Close()
		return nil, fmt.Errorf("create forest cache schema in %s: %w", path, err)
	}
	s := &Store{db: db, version: version, poolSize: poolSize}

	var current, total int
	if err := db.QueryRow(`SELECT COUNT(*) FILTER (WHERE version = ?), COUNT(*) FROM forests`, version).Scan(&current, &total); err != nil {
		db.Close()
		return nil, fmt.Errorf("count forest cache rows in %s: %w", path, err)
	}
	slog.Info("forest cache opened", "path", path, "version", version, "pool_size", poolSize,
		"forests_this_version", current, "forests_all_versions", total)
	return s, nil
}

func (s *Store) Close() error { return s.db.Close() }

// Random returns one forest from the pool, chosen uniformly, and false when
// the pool is empty.
func (s *Store) Random(ctx context.Context, word string, maxHops int) (forest.Forest, bool, error) {
	var body string
	err := s.db.QueryRowContext(ctx,
		`SELECT body FROM forests WHERE version = ? AND word = ? AND max_hops = ? ORDER BY random() LIMIT 1`,
		s.version, word, maxHops).Scan(&body)
	if errors.Is(err, sql.ErrNoRows) {
		return forest.Forest{}, false, nil
	}
	if err != nil {
		return forest.Forest{}, false, fmt.Errorf("read forest cache: %w", err)
	}
	var f forest.Forest
	if err := json.Unmarshal([]byte(body), &f); err != nil {
		return forest.Forest{}, false, fmt.Errorf("decode cached forest for %q: %w", word, err)
	}
	return f, true, nil
}

// Add stores f and drops the pool's oldest forests beyond poolSize, in one
// transaction.
func (s *Store) Add(ctx context.Context, word string, maxHops int, f forest.Forest) error {
	body, err := json.Marshal(f)
	if err != nil {
		return fmt.Errorf("encode forest for %q: %w", word, err)
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("begin forest cache write: %w", err)
	}
	defer tx.Rollback() // no-op after Commit

	if _, err := tx.ExecContext(ctx,
		`INSERT INTO forests (version, word, max_hops, body, created_at) VALUES (?, ?, ?, ?, ?)`,
		s.version, word, maxHops, string(body), time.Now().UTC().Format(time.RFC3339)); err != nil {
		return fmt.Errorf("insert cached forest for %q: %w", word, err)
	}
	if _, err := tx.ExecContext(ctx,
		`DELETE FROM forests WHERE version = ? AND word = ? AND max_hops = ? AND id NOT IN (
			SELECT id FROM forests WHERE version = ? AND word = ? AND max_hops = ? ORDER BY id DESC LIMIT ?)`,
		s.version, word, maxHops, s.version, word, maxHops, s.poolSize); err != nil {
		return fmt.Errorf("evict cached forests for %q: %w", word, err)
	}
	if err := tx.Commit(); err != nil {
		return fmt.Errorf("commit cached forest for %q: %w", word, err)
	}
	return nil
}
