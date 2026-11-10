// Command forestcache inspects and clears the metaphor forest cache.
//
//	go run ./cmd/forestcache -db PATH stats
//	go run ./cmd/forestcache -db PATH clear [-word W] [-before YYYY-MM-DD] [-all]
//
// PATH is the file the API units read from METAFORGE_FOREST_CACHE, for
// example <worktree>/data-pipeline/output/forest_cache.db. The server can keep
// running: the file is in WAL mode, and a cleared pool simply refills.
// clear needs at least one of -word, -before or -all; filters combine with
// AND, and -before clears rows created before that date (UTC).
package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"

	"github.com/snailuj/metaforge/internal/forestcache"
)

func main() {
	if err := run(os.Args[1:], os.Stdout); err != nil {
		fmt.Fprintln(os.Stderr, "forestcache:", err)
		os.Exit(1)
	}
}

func run(args []string, out io.Writer) error {
	global := flag.NewFlagSet("forestcache", flag.ContinueOnError)
	global.SetOutput(io.Discard)
	dbPath := global.String("db", "", "forest cache SQLite file")
	if err := global.Parse(args); err != nil {
		return err
	}
	if *dbPath == "" {
		return errors.New("-db PATH is required")
	}
	rest := global.Args()
	if len(rest) == 0 {
		return errors.New("a subcommand is required: stats or clear")
	}
	cmd, cmdArgs := rest[0], rest[1:]
	if cmd != "stats" && cmd != "clear" {
		return fmt.Errorf("unknown subcommand %q: want stats or clear", cmd)
	}

	// Open would create a missing file; a mistyped path should fail instead.
	if _, err := os.Stat(*dbPath); err != nil {
		return fmt.Errorf("forest cache file: %w", err)
	}
	store, err := forestcache.Open(*dbPath, "", 1)
	if err != nil {
		return err
	}
	defer store.Close()

	ctx := context.Background()
	if cmd == "stats" {
		return printStats(ctx, store, out)
	}

	fs := flag.NewFlagSet("clear", flag.ContinueOnError)
	fs.SetOutput(io.Discard)
	var filter forestcache.ClearFilter
	fs.StringVar(&filter.Word, "word", "", "clear only this word")
	fs.StringVar(&filter.Before, "before", "", "clear rows created before this date, YYYY-MM-DD (UTC)")
	fs.BoolVar(&filter.All, "all", false, "clear every row")
	if err := fs.Parse(cmdArgs); err != nil {
		return err
	}
	n, err := store.Clear(ctx, filter)
	if err != nil {
		return err
	}
	_, err = fmt.Fprintf(out, "deleted %d forests\n", n)
	return err
}

func printStats(ctx context.Context, store *forestcache.Store, out io.Writer) error {
	stats, err := store.Stats(ctx)
	if err != nil {
		return err
	}
	if len(stats) == 0 {
		_, err := fmt.Fprintln(out, "forest cache is empty")
		return err
	}
	fmt.Fprintf(out, "%-16s %6s  %-20s  %s\n", "version", "rows", "oldest", "newest")
	for _, v := range stats {
		fmt.Fprintf(out, "%-16s %6d  %-20s  %s\n", v.Version, v.Rows, v.Oldest, v.Newest)
	}
	return nil
}
