package forest

import (
	"encoding/json"
	"errors"
	"fmt"
	"slices"
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
	return strings.ToLower(collapseSpace(s))
}

// collapseSpace trims and joins inner runs of whitespace, newlines included,
// into single spaces.
func collapseSpace(s string) string {
	return strings.Join(strings.Fields(s), " ")
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
			Grounds: []string{collapseSpace(f.Ground)},
		}
		if line := collapseSpace(f.Line); line != "" {
			paths = append(paths, withLine(head, line))
		}
		for _, b := range f.Branches {
			p := withLine(head, collapseSpace(b.Line))
			for _, h := range b.Hops {
				p.Words = append(p.Words, NormalizeWord(h.Word))
				p.Grounds = append(p.Grounds, collapseSpace(h.Ground))
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
	maxHopWords    = 4
	maxHopChars    = 60
	maxGroundChars = 80
	maxLineChars   = 200

	// maxPaths bounds what a model can make the judge read and us hold.
	maxPaths = 24
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
	case utf8.RuneCountInString(p.Line) > maxLineChars:
		return fmt.Errorf("line is longer than %d characters", maxLineChars)
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
		case utf8.RuneCountInString(p.Grounds[i]) > maxGroundChars:
			return fmt.Errorf("ground of hop %q is longer than %d characters", w, maxGroundChars)
		case seen[w]:
			return fmt.Errorf("path revisits %q", w)
		}
		seen[w] = true
	}
	return nil
}

// Screen keeps the paths that pass ValidatePath, in order, and counts the
// rest. Only the first maxPaths are considered; later ones count as invalid.
func Screen(source string, maxHops int, paths []Path) (valid []Path, invalid int) {
	for i, p := range paths {
		if i < maxPaths && ValidatePath(source, maxHops, p) == nil {
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
	Duplicate int `json:"duplicate"`
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
// path, then the earlier one) and the rest count as duplicate.
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
			rej.Duplicate++
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

// Role is a node's part in the forest.
type Role string

const (
	RoleSource   Role = "source"
	RoleHop      Role = "hop"
	RoleEndpoint Role = "endpoint"
)

// Node is a word in the forest; ID is the normalised word.
type Node struct {
	ID   string `json:"id"`
	Word string `json:"word"`
	Role Role   `json:"role"`
}

// Edge runs along a path, source outward, carrying the distinct grounds
// that join its two words across all kept paths.
type Edge struct {
	Source  string   `json:"source"`
	Target  string   `json:"target"`
	Grounds []string `json:"grounds"`
}

// Endpoint is a kept path end. Grounds[i] joins Path[i] to Path[i+1].
type Endpoint struct {
	ID      string   `json:"id"`
	Path    []string `json:"path"`
	Grounds []string `json:"grounds"`
	Line    string   `json:"line"`
	Score   int      `json:"score"`
	Reason  string   `json:"reason"`
}

// Stats accounts for every generated path: Kept plus the Rejected counts
// equal Generated.
type Stats struct {
	Generated int      `json:"generated"`
	Kept      int      `json:"kept"`
	Rejected  Rejected `json:"rejected"`
}

// Forest is the API response body.
type Forest struct {
	Source    string     `json:"source"`
	MaxHops   int        `json:"max_hops"`
	Model     string     `json:"model"`
	Nodes     []Node     `json:"nodes"`
	Edges     []Edge     `json:"edges"`
	Endpoints []Endpoint `json:"endpoints"`
	Stats     Stats      `json:"stats"`
}

// Merge folds kept paths into the node, edge and endpoint lists. Nodes and
// edges appear in order of first use; endpoints sort by score descending,
// then path length ascending, then input order. The slices are never nil.
func Merge(source string, kept []ScoredPath) Forest {
	f := Forest{
		Source:    source,
		Nodes:     []Node{{ID: source, Word: source, Role: RoleSource}},
		Edges:     []Edge{},
		Endpoints: []Endpoint{},
	}

	endpointIDs := make(map[string]bool, len(kept))
	for _, k := range kept {
		endpointIDs[k.Words[len(k.Words)-1]] = true
	}

	nodeSeen := map[string]bool{source: true}
	edgeAt := map[[2]string]int{}
	for _, k := range kept {
		path := append([]string{source}, k.Words...)
		for i := 1; i < len(path); i++ {
			if w := path[i]; !nodeSeen[w] {
				nodeSeen[w] = true
				role := RoleHop
				if endpointIDs[w] {
					role = RoleEndpoint
				}
				f.Nodes = append(f.Nodes, Node{ID: w, Word: w, Role: role})
			}
			key := [2]string{path[i-1], path[i]}
			at, ok := edgeAt[key]
			if !ok {
				at = len(f.Edges)
				edgeAt[key] = at
				f.Edges = append(f.Edges, Edge{Source: key[0], Target: key[1], Grounds: []string{}})
			}
			if g := k.Grounds[i-1]; !slices.Contains(f.Edges[at].Grounds, g) {
				f.Edges[at].Grounds = append(f.Edges[at].Grounds, g)
			}
		}
		f.Endpoints = append(f.Endpoints, Endpoint{
			ID:      k.Words[len(k.Words)-1],
			Path:    path,
			Grounds: append([]string(nil), k.Grounds...),
			Line:    k.Line,
			Score:   k.Score,
			Reason:  k.Reason,
		})
	}

	slices.SortStableFunc(f.Endpoints, func(a, b Endpoint) int {
		if a.Score != b.Score {
			return b.Score - a.Score
		}
		return len(a.Path) - len(b.Path)
	})
	return f
}

// Build judges the screened paths against verdicts and merges the
// survivors. invalid is the count of paths Screen already dropped; it is
// added to Generated and Rejected.Invalid. ignored lists verdict indices
// that matched nothing. Model is left for the caller to set.
func Build(source string, maxHops, minScore int, valid []Path, invalid int, verdicts []Verdict) (f Forest, ignored []int) {
	kept, rej, ignored := ApplyVerdicts(valid, verdicts, minScore)
	rej.Invalid += invalid

	f = Merge(source, kept)
	f.MaxHops = maxHops
	f.Stats = Stats{Generated: len(valid) + invalid, Kept: len(kept), Rejected: rej}
	return f, ignored
}

// GeneratorUserMessage is the generator's user turn.
func GeneratorUserMessage(source string, maxHops int) string {
	return fmt.Sprintf("SOURCE: %s\nMAX_HOPS: %d", source, maxHops)
}

// JudgeUserMessage numbers paths from 1, the numbering ApplyVerdicts
// expects. Each path gets its chain of words, then one row per hop naming
// the two words a ground joins, then its line: a small judge given only an
// inline chain checked later grounds against the source word.
func JudgeUserMessage(source string, paths []Path) string {
	var b strings.Builder
	fmt.Fprintf(&b, "SOURCE: %s", source)
	for i, p := range paths {
		fmt.Fprintf(&b, "\n\n%d. %s", i+1, source)
		for _, w := range p.Words {
			fmt.Fprintf(&b, " -> %s", w)
		}
		prev := source
		for j, w := range p.Words {
			fmt.Fprintf(&b, "\n   %s / %s: %s", prev, w, p.Grounds[j])
			prev = w
		}
		fmt.Fprintf(&b, "\n   line: %s", p.Line)
	}
	return b.String()
}
