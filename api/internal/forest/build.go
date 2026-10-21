package forest

import (
	"encoding/json"
	"errors"
	"fmt"
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

// Hop is one step of a generated path.
type Hop struct {
	Word   string `json:"word"`
	Ground string `json:"ground"`
}

// Branch continues a facet with further hops towards an endpoint.
type Branch struct {
	Hops []Hop  `json:"hops"`
	Line string `json:"line"`
}

// Facet is the first hop of a branch family: one side of the source.
type Facet struct {
	Word     string   `json:"word"`
	Ground   string   `json:"ground"`
	Line     string   `json:"line"`
	Branches []Branch `json:"branches"`
}

// Generated is the generator's structured output.
type Generated struct {
	Facets []Facet `json:"facets"`
}

// ParseGenerated decodes the generator's JSON text.
func ParseGenerated(raw string) (Generated, error) {
	var g Generated
	if err := json.Unmarshal([]byte(raw), &g); err != nil {
		return Generated{}, fmt.Errorf("decode generator output: %w", err)
	}
	return g, nil
}

// Path walks from the source to an endpoint. Words and Grounds are
// normalised and equal in length: Grounds[i] joins the word before
// Words[i] (the source when i is 0) to Words[i].
type Path struct {
	Words   []string
	Grounds []string
	Line    string
}

// Flatten turns the facet tree into one Path per endpoint candidate. A
// facet with a non-empty line is itself an endpoint; each branch is an
// endpoint reached through its facet.
func Flatten(g Generated) []Path {
	var paths []Path
	for _, f := range g.Facets {
		head := Path{
			Words:   []string{NormalizeWord(f.Word)},
			Grounds: []string{strings.TrimSpace(f.Ground)},
		}
		if line := strings.TrimSpace(f.Line); line != "" {
			paths = append(paths, withLine(head, line))
		}
		for _, b := range f.Branches {
			p := withLine(head, strings.TrimSpace(b.Line))
			for _, h := range b.Hops {
				p.Words = append(p.Words, NormalizeWord(h.Word))
				p.Grounds = append(p.Grounds, strings.TrimSpace(h.Ground))
			}
			paths = append(paths, p)
		}
	}
	return paths
}

// withLine copies p so sibling paths never share a backing array.
func withLine(p Path, line string) Path {
	return Path{
		Words:   append([]string(nil), p.Words...),
		Grounds: append([]string(nil), p.Grounds...),
		Line:    line,
	}
}

const (
	maxHopWords = 4
	maxHopChars = 60
)

// ValidatePath reports the first rule the path breaks. source must already
// be normalised.
func ValidatePath(source string, maxHops int, p Path) error {
	n := len(p.Words)
	switch {
	case n == 0:
		return errors.New("path has no hops")
	case n > maxHops:
		return fmt.Errorf("path has %d hops, max is %d", n, maxHops)
	case len(p.Grounds) != n:
		return fmt.Errorf("path has %d words but %d grounds", n, len(p.Grounds))
	case p.Line == "":
		return errors.New("path end has an empty line")
	}
	seen := map[string]bool{source: true}
	for i, w := range p.Words {
		switch {
		case w == "":
			return fmt.Errorf("hop %d is empty", i+1)
		case len(strings.Fields(w)) > maxHopWords:
			return fmt.Errorf("hop %q is longer than %d words", w, maxHopWords)
		case utf8.RuneCountInString(w) > maxHopChars:
			return fmt.Errorf("hop %q is longer than %d characters", w, maxHopChars)
		case p.Grounds[i] == "":
			return fmt.Errorf("hop %q has an empty ground", w)
		case seen[w]:
			return fmt.Errorf("path revisits %q", w)
		}
		seen[w] = true
	}
	return nil
}

// Screen keeps the paths that pass ValidatePath, in order, and counts the
// rest.
func Screen(source string, maxHops int, paths []Path) (valid []Path, invalid int) {
	for _, p := range paths {
		if ValidatePath(source, maxHops, p) == nil {
			valid = append(valid, p)
		} else {
			invalid++
		}
	}
	return valid, invalid
}
