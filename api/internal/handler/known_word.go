package handler

import (
	"context"

	"github.com/snailuj/metaforge/internal/thesaurus"
)

// KnownWord reports whether word resolves as a lemma in the lexicon, by the
// same rule as /thesaurus/lookup. It satisfies ForestHandler.KnownWord.
func (h *Handler) KnownWord(_ context.Context, word string) (bool, error) {
	return thesaurus.HasLemma(h.database, word)
}
