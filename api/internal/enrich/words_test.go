package enrich

import (
	"database/sql"
	"os"
	"path/filepath"
	"reflect"
	"testing"
)

func TestReadWordFile(t *testing.T) {
	path := filepath.Join(t.TempDir(), "words.txt")
	os.WriteFile(path, []byte("# emotions\nLonging\n\ndread\nlonging\n<script>\n  quiet   hope \n"), 0o644)
	got, err := ReadWordFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if want := []string{"longing", "dread", "quiet hope"}; !reflect.DeepEqual(got, want) {
		t.Fatalf("got %v, want %v", got, want)
	}
}

func TestLexiconWordsCommonNounsAndAdjectivesFirst(t *testing.T) {
	path := filepath.Join(t.TempDir(), "lexicon.db")
	db, err := sql.Open("sqlite3", path)
	if err != nil {
		t.Fatal(err)
	}
	for _, q := range []string{
		`CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, pos TEXT, definition TEXT)`,
		`CREATE TABLE lemmas (lemma TEXT, synset_id TEXT)`,
		`CREATE TABLE frequencies (lemma TEXT PRIMARY KEY, zipf REAL)`,
		`INSERT INTO synsets VALUES ('1','n','a home'),('2','v','to run'),('3','a','bright'),('4','n','an aardvark')`,
		`INSERT INTO lemmas VALUES ('house','1'),('run','2'),('bright','3'),('aardvark','4')`,
		`INSERT INTO frequencies VALUES ('the',7.5),('house',5.8),('run',5.9),('bright',4.9),('aardvark',2.1)`,
	} {
		if _, err := db.Exec(q); err != nil {
			t.Fatal(err)
		}
	}
	db.Close()

	got, err := LexiconWords(path, 2)
	if err != nil {
		t.Fatal(err)
	}
	if want := []string{"house", "bright"}; !reflect.DeepEqual(got, want) {
		t.Fatalf("got %v, want %v", got, want)
	}
}
