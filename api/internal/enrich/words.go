package enrich

import (
	"bufio"
	"database/sql"
	"fmt"
	"log/slog"
	"os"
	"strings"

	_ "github.com/mattn/go-sqlite3"

	"github.com/snailuj/metaforge/internal/forest"
)

// ReadWordFile reads one word per line. Blank lines and # comments are
// skipped; words the forest route would refuse are dropped with a warning;
// repeats keep their first place.
func ReadWordFile(path string) ([]string, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("open word list: %w", err)
	}
	defer f.Close()
	var raw []string
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		raw = append(raw, line)
	}
	if err := sc.Err(); err != nil {
		return nil, fmt.Errorf("read word list: %w", err)
	}
	return clean(raw), nil
}

// LexiconWords returns up to limit words, most frequent first, that have a
// noun or adjective sense in the lexicon: the words people look up, without
// function words like "the".
func LexiconWords(dbPath string, limit int) ([]string, error) {
	db, err := sql.Open("sqlite3", "file:"+dbPath+"?mode=ro")
	if err != nil {
		return nil, fmt.Errorf("open lexicon: %w", err)
	}
	defer db.Close()
	rows, err := db.Query(`
		SELECT f.lemma FROM frequencies f
		WHERE f.zipf IS NOT NULL AND EXISTS (
			SELECT 1 FROM lemmas l JOIN synsets s ON s.synset_id = l.synset_id
			WHERE l.lemma = f.lemma AND s.pos IN ('n', 'a', 's'))
		ORDER BY f.zipf DESC, f.lemma
		LIMIT ?`, limit)
	if err != nil {
		return nil, fmt.Errorf("query lexicon words: %w", err)
	}
	defer rows.Close()
	var raw []string
	for rows.Next() {
		var w string
		if err := rows.Scan(&w); err != nil {
			return nil, fmt.Errorf("read lexicon word: %w", err)
		}
		raw = append(raw, w)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("read lexicon words: %w", err)
	}
	return clean(raw), nil
}

func clean(raw []string) []string {
	seen := map[string]bool{}
	var out []string
	for _, w := range raw {
		n, err := forest.ParseSourceWord(w)
		if err != nil {
			slog.Warn("enrich: word skipped", "word", w, "err", err)
			continue
		}
		if !seen[n] {
			seen[n] = true
			out = append(out, n)
		}
	}
	return out
}
