// Package forestcache keeps finished metaphor forests in a writable SQLite
// file, a pool of up to poolSize per (word, max_hops). A row records the
// pipeline version it was written under, but the version never decides
// whether it is served. Every forest is also kept permanently in the
// model-call log, so the cache is disposable: clear it by hand with
// cmd/forestcache.
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

// The version column is a label only: pools, serving and eviction ignore it,
// so a prompt edit does not empty the cache.
const schema = `
CREATE TABLE IF NOT EXISTS forests (
	id         INTEGER PRIMARY KEY AUTOINCREMENT,
	version    TEXT    NOT NULL,
	word       TEXT    NOT NULL,
	max_hops   INTEGER NOT NULL,
	body       TEXT    NOT NULL,
	created_at TEXT    NOT NULL
);
DROP INDEX IF EXISTS idx_forests_pool;
CREATE INDEX IF NOT EXISTS idx_forests_word_hops ON forests(word, max_hops, id);
`

// Store is safe for concurrent use.
type Store struct {
	db       *sql.DB
	version  string
	poolSize int
}

// Open creates the file and schema if needed. version is the pipeline
// fingerprint (forest.Fingerprint) written on each new row. An empty version
// gives a read/admin-only store: Add refuses to write.
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
		`SELECT body FROM forests WHERE word = ? AND max_hops = ? ORDER BY random() LIMIT 1`,
		word, maxHops).Scan(&body)
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

// List returns the pool, newest first. It reads at most poolSize rows, so a
// response stays bounded however the file was written.
func (s *Store) List(ctx context.Context, word string, maxHops int) ([]forest.Forest, error) {
	rows, err := s.db.QueryContext(ctx,
		`SELECT body FROM forests WHERE word = ? AND max_hops = ? ORDER BY id DESC LIMIT ?`,
		word, maxHops, s.poolSize)
	if err != nil {
		return nil, fmt.Errorf("list cached forests for %q: %w", word, err)
	}
	defer rows.Close()
	forests := []forest.Forest{}
	for rows.Next() {
		var body string
		if err := rows.Scan(&body); err != nil {
			return nil, fmt.Errorf("read cached forest for %q: %w", word, err)
		}
		var f forest.Forest
		if err := json.Unmarshal([]byte(body), &f); err != nil {
			return nil, fmt.Errorf("decode cached forest for %q: %w", word, err)
		}
		forests = append(forests, f)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("list cached forests for %q: %w", word, err)
	}
	return forests, nil
}

// Full reports whether the pool already holds poolSize forests, so another
// would only evict one.
func (s *Store) Full(ctx context.Context, word string, maxHops int) (bool, error) {
	var n int
	if err := s.db.QueryRowContext(ctx,
		`SELECT COUNT(*) FROM forests WHERE word = ? AND max_hops = ?`,
		word, maxHops).Scan(&n); err != nil {
		return false, fmt.Errorf("count cached forests for %q: %w", word, err)
	}
	return n >= s.poolSize, nil
}

// Add stores f and drops the pool's oldest forests beyond poolSize, in one
// transaction.
func (s *Store) Add(ctx context.Context, word string, maxHops int, f forest.Forest) error {
	if s.version == "" {
		return errors.New("forest cache opened without a version cannot add forests")
	}
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
		`DELETE FROM forests WHERE word = ? AND max_hops = ? AND id NOT IN (
			SELECT id FROM forests WHERE word = ? AND max_hops = ? ORDER BY id DESC LIMIT ?)`,
		word, maxHops, word, maxHops, s.poolSize); err != nil {
		return fmt.Errorf("evict cached forests for %q: %w", word, err)
	}
	if err := tx.Commit(); err != nil {
		return fmt.Errorf("commit cached forest for %q: %w", word, err)
	}
	return nil
}

// VersionStats summarises the rows written under one pipeline version.
// Oldest and Newest are created_at strings (RFC3339, UTC).
type VersionStats struct {
	Version string
	Rows    int
	Oldest  string
	Newest  string
}

// Stats lists each version in the cache, oldest first.
func (s *Store) Stats(ctx context.Context) ([]VersionStats, error) {
	rows, err := s.db.QueryContext(ctx,
		`SELECT version, COUNT(*), MIN(created_at), MAX(created_at) FROM forests
		 GROUP BY version ORDER BY MIN(created_at), version`)
	if err != nil {
		return nil, fmt.Errorf("read forest cache stats: %w", err)
	}
	defer rows.Close()
	stats := []VersionStats{}
	for rows.Next() {
		var v VersionStats
		if err := rows.Scan(&v.Version, &v.Rows, &v.Oldest, &v.Newest); err != nil {
			return nil, fmt.Errorf("read forest cache stats row: %w", err)
		}
		stats = append(stats, v)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("read forest cache stats: %w", err)
	}
	return stats, nil
}

// ClearFilter selects the rows Clear deletes. Set fields combine with AND.
type ClearFilter struct {
	Word   string
	Before string // YYYY-MM-DD: rows created before this date (UTC)
	All    bool
}

const clearDateLayout = "2006-01-02"

// Clear deletes the rows matching f in one statement and returns how many.
// It refuses an empty filter, so a mistyped command cannot empty the cache.
func (s *Store) Clear(ctx context.Context, f ClearFilter) (int64, error) {
	if f.Word == "" && f.Before == "" && !f.All {
		return 0, errors.New("clear needs a word, a before date or all")
	}
	query, args := `DELETE FROM forests WHERE 1 = 1`, []any{}
	if f.Word != "" {
		query += ` AND word = ?`
		args = append(args, f.Word)
	}
	if f.Before != "" {
		if _, err := time.Parse(clearDateLayout, f.Before); err != nil {
			return 0, fmt.Errorf("before %q must be a date like 2026-10-22: %w", f.Before, err)
		}
		// created_at is RFC3339 UTC, so text order is time order and a bare
		// date sorts before every timestamp on that day.
		query += ` AND created_at < ?`
		args = append(args, f.Before)
	}
	res, err := s.db.ExecContext(ctx, query, args...)
	if err != nil {
		return 0, fmt.Errorf("clear forest cache: %w", err)
	}
	n, err := res.RowsAffected()
	if err != nil {
		return 0, fmt.Errorf("count cleared forests: %w", err)
	}
	slog.Info("forest cache cleared", "word", f.Word, "before", f.Before, "all", f.All, "rows_deleted", n)
	return n, nil
}
