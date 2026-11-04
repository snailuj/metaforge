// Command enrich grows the metaphor forest cache through the Metaforge
// API, night and day, paced under the server's weekly model budget.
//
//	enrich -api http://127.0.0.1:8080 -lexicon lexicon_v2.db -top 5000 -state enrich_state.json
//
// It asks for one fresh forest at a time, spacing them so enrichment spends
// at most (weekly cap - reserve) a week, and stops while the week's total
// spend, live users included, sits above that line. Progress is saved after
// every forest, so it can be stopped and restarted at any time.
package main

import (
	"context"
	"errors"
	"flag"
	"log/slog"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/snailuj/metaforge/internal/enrich"
)

func main() {
	api := flag.String("api", "http://127.0.0.1:8080", "Metaforge API base URL")
	wordsFile := flag.String("words", "", "word list, one per line (overrides -lexicon)")
	lexicon := flag.String("lexicon", "", "lexicon database to draw common nouns and adjectives from")
	top := flag.Int("top", 5000, "with -lexicon, how many words, most frequent first")
	statePath := flag.String("state", "enrich_state.json", "progress file")
	hops := flag.Int("hops", 3, "max_hops for each forest (1-5)")
	passes := flag.Int("passes", 10, "passes over the word list, one forest per word each; 0 runs forever")
	reserve := flag.Float64("reserve", 5, "USD of the weekly cap left for live users")
	initialCost := flag.Float64("initial-cost", 0.005, "USD per forest assumed until real costs come in")
	minInterval := flag.Duration("min-interval", 10*time.Second, "shortest gap between forests")
	flag.Parse()

	if err := run(*api, *wordsFile, *lexicon, *top, *statePath, *hops, *passes, *reserve, *initialCost, *minInterval); err != nil {
		slog.Error("enrich stopped", "err", err)
		os.Exit(1)
	}
}

func run(api, wordsFile, lexicon string, top int, statePath string, hops, passes int, reserve, initialCost float64, minInterval time.Duration) error {
	var words []string
	var err error
	switch {
	case wordsFile != "":
		words, err = enrich.ReadWordFile(wordsFile)
	case lexicon != "":
		words, err = enrich.LexiconWords(lexicon, top)
	default:
		return errors.New("give -words or -lexicon")
	}
	if err != nil {
		return err
	}
	if hops < 1 || hops > 5 {
		return errors.New("-hops must be 1 to 5")
	}
	if reserve < 0 || initialCost <= 0 {
		return errors.New("-reserve must be at least 0 and -initial-cost above 0")
	}

	e, err := enrich.New(enrich.NewClient(api, 100*time.Second), enrich.Config{
		Words: words, MaxHops: hops, Passes: passes, ReserveUSD: reserve, InitialCostUSD: initialCost,
		MinInterval: minInterval, IdleWait: 15 * time.Minute, ErrorWait: time.Minute, StatePath: statePath,
	}, time.Now)
	if err != nil {
		return err
	}
	slog.Info("enrich starting", "api", api, "words", len(words), "hops", hops, "passes", passes,
		"reserve_usd", reserve, "state", statePath)

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	err = e.Run(ctx)
	st := e.State()
	slog.Info("enrich finished", "forests", st.Forests, "failed", st.Failed, "spent_usd", st.SpentUSD, "pass", st.Pass)
	switch {
	case errors.Is(err, enrich.ErrDone), errors.Is(err, context.Canceled):
		return nil
	default:
		return err
	}
}
