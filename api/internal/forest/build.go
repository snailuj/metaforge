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

// Verdict is the judge's assessment of one numbered path.
type Verdict struct {
	Index     int    `json:"index"`
	Score     int    `json:"score"`
	BrokenHop bool   `json:"broken_hop"`
	Drift     bool   `json:"drift"`
	Literal   bool   `json:"literal"`
	Cliche    bool   `json:"cliche"`
	Reason    string `json:"reason"`
}

// ParseVerdicts decodes the judge's JSON text.
func ParseVerdicts(raw string) ([]Verdict, error) {
	var out struct {
		Verdicts []Verdict `json:"verdicts"`
	}
	if err := json.Unmarshal([]byte(raw), &out); err != nil {
		return nil, fmt.Errorf("decode judge output: %w", err)
	}
	return out.Verdicts, nil
}

// Rejected counts rejected paths by reason. Every field is always
// serialised, so the client sees zeros rather than missing keys.
type Rejected struct {
	Invalid   int `json:"invalid"`
	LowScore  int `json:"low_score"`
	BrokenHop int `json:"broken_hop"`
	Drift     int `json:"drift"`
	Cliche    int `json:"cliche"`
	Literal   int `json:"literal"`
}

// ScoredPath is a path that survived judging.
type ScoredPath struct {
	Path
	Score  int
	Reason string
}

const (
	minVerdictScore = 0
	maxVerdictScore = 10
)

// ApplyVerdicts judges paths against verdicts, whose indices are 1-based
// positions in paths. Kept paths keep their input order. ignored lists the
// verdict indices that matched no path, or repeated one, for logging.
//
// A path is rejected for the first of: no verdict (invalid), then the flags
// broken_hop, drift, literal, cliche, then a score below minScore. Of kept
// paths sharing an endpoint, the highest score survives (then the shorter
// path, then the earlier one) and the rest count as invalid.
func ApplyVerdicts(paths []Path, verdicts []Verdict, minScore int) (kept []ScoredPath, rej Rejected, ignored []int) {
	byIndex := make(map[int]Verdict, len(verdicts))
	for _, v := range verdicts {
		_, dup := byIndex[v.Index]
		if v.Index < 1 || v.Index > len(paths) || dup {
			ignored = append(ignored, v.Index)
			continue
		}
		v.Score = min(max(v.Score, minVerdictScore), maxVerdictScore)
		byIndex[v.Index] = v
	}

	var passed []ScoredPath
	for i, p := range paths {
		v, ok := byIndex[i+1]
		switch {
		case !ok:
			rej.Invalid++
		case v.BrokenHop:
			rej.BrokenHop++
		case v.Drift:
			rej.Drift++
		case v.Literal:
			rej.Literal++
		case v.Cliche:
			rej.Cliche++
		case v.Score < minScore:
			rej.LowScore++
		default:
			passed = append(passed, ScoredPath{Path: p, Score: v.Score, Reason: v.Reason})
		}
	}

	winner := make(map[string]int, len(passed))
	for i, sp := range passed {
		end := sp.Words[len(sp.Words)-1]
		w, seen := winner[end]
		if !seen || beats(sp, passed[w]) {
			winner[end] = i
		}
	}
	for i, sp := range passed {
		if winner[sp.Words[len(sp.Words)-1]] == i {
			kept = append(kept, sp)
		} else {
			rej.Invalid++
		}
	}
	return kept, rej, ignored
}

// beats orders candidates for one endpoint: higher score, then shorter.
func beats(a, b ScoredPath) bool {
	if a.Score != b.Score {
		return a.Score > b.Score
	}
	return len(a.Words) < len(b.Words)
}
