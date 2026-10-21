package forest

import (
	"errors"
	"strings"
	"unicode"
	"unicode/utf8"
)

// ErrInvalidWord marks a source word that fails ParseSourceWord.
var ErrInvalidWord = errors.New("word must be 1-40 letters, spaces, hyphens or apostrophes")

const maxSourceChars = 40

// NormalizeWord lower-cases, trims and collapses inner whitespace. The
// result is the node id, matching the browse graph's bare-word ids.
func NormalizeWord(s string) string {
	return strings.ToLower(strings.Join(strings.Fields(s), " "))
}

// ParseSourceWord normalises the request word and rejects anything but
// letters, spaces, hyphens and apostrophes, which also keeps arbitrary
// text out of the prompt.
func ParseSourceWord(raw string) (string, error) {
	word := NormalizeWord(raw)
	n := utf8.RuneCountInString(word)
	if n < 1 || n > maxSourceChars {
		return "", ErrInvalidWord
	}
	for _, r := range word {
		if !unicode.IsLetter(r) && r != ' ' && r != '-' && r != '\'' && r != '’' {
			return "", ErrInvalidWord
		}
	}
	return word, nil
}
