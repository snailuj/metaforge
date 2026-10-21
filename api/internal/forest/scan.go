package forest

import (
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
)

// ScanEvent is one JSON value that has finished arriving. Path holds the
// object keys and array indices from the root down to it; the root's Path
// is empty.
type ScanEvent struct {
	Path []string
	Raw  []byte
}

// PathString joins Path with "/", e.g. "facets/0/branches/1/hops/0".
func (e ScanEvent) PathString() string { return strings.Join(e.Path, "/") }

type scanState uint8

const (
	expectValue scanState = iota
	expectValueOrEnd
	expectKeyOrEnd
	expectKey
	expectColon
	expectCommaOrEnd
	scanDone
)

type scanFrame struct {
	kind  byte // '{', '[' or 0 for the root
	start int
	seg   string
	state scanState
	key   string
	index int
}

// Scanner reads one JSON document in chunks, as a streamed model response
// arrives, and reports every value the moment its last byte is in. It keeps
// the whole document in memory; generator output is capped at
// callMaxTokens, so that stays small.
type Scanner struct {
	buf   []byte
	pos   int
	stack []scanFrame

	inString, stringIsKey, escape bool
	inScalar                      bool
	tokenStart                    int
}

// Feed adds a chunk and returns the values it completed, innermost first.
// An error means the stream is not valid JSON; the Scanner is then unusable.
func (s *Scanner) Feed(chunk string) ([]ScanEvent, error) {
	if s.stack == nil {
		s.stack = []scanFrame{{}}
	}
	s.buf = append(s.buf, chunk...)
	var out []ScanEvent
	for ; s.pos < len(s.buf); s.pos++ {
		i, c := s.pos, s.buf[s.pos]
		if s.inString {
			switch {
			case s.escape:
				s.escape = false
			case c == '\\':
				s.escape = true
			case c == '"':
				s.inString = false
				if s.stringIsKey {
					top := s.top()
					if err := json.Unmarshal(s.buf[s.tokenStart:i+1], &top.key); err != nil {
						return out, fmt.Errorf("scan: bad key at %d: %w", s.tokenStart, err)
					}
					top.state = expectColon
				} else {
					out = append(out, s.complete(s.tokenStart, i+1))
				}
			}
			continue
		}
		if s.inScalar {
			if !isDelimiter(c) {
				continue
			}
			s.inScalar = false
			if !json.Valid(s.buf[s.tokenStart:i]) {
				return out, fmt.Errorf("scan: bad literal %q at %d", s.buf[s.tokenStart:i], s.tokenStart)
			}
			out = append(out, s.complete(s.tokenStart, i))
		}
		if isSpace(c) {
			continue
		}
		ev, err := s.step(i, c)
		if err != nil {
			return out, err
		}
		if ev != nil {
			out = append(out, *ev)
		}
	}
	return out, nil
}

func (s *Scanner) step(i int, c byte) (*ScanEvent, error) {
	top := s.top()
	switch top.state {
	case expectValue, expectValueOrEnd:
		switch {
		case c == ']' && top.state == expectValueOrEnd:
			return s.close(i), nil
		case c == '{' || c == '[':
			seg := s.childSeg()
			st := expectKeyOrEnd
			if c == '[' {
				st = expectValueOrEnd
			}
			s.stack = append(s.stack, scanFrame{kind: c, start: i, seg: seg, state: st})
		case c == '"':
			s.inString, s.stringIsKey, s.tokenStart = true, false, i
		case c == '-' || (c >= '0' && c <= '9') || c == 't' || c == 'f' || c == 'n':
			s.inScalar, s.tokenStart = true, i
		default:
			return nil, s.unexpected(i, c)
		}
	case expectKeyOrEnd, expectKey:
		switch {
		case c == '}' && top.state == expectKeyOrEnd:
			return s.close(i), nil
		case c == '"':
			s.inString, s.stringIsKey, s.tokenStart = true, true, i
		default:
			return nil, s.unexpected(i, c)
		}
	case expectColon:
		if c != ':' {
			return nil, s.unexpected(i, c)
		}
		top.state = expectValue
	case expectCommaOrEnd:
		switch {
		case c == ',' && top.kind == '{':
			top.state = expectKey
		case c == ',' && top.kind == '[':
			top.index++
			top.state = expectValue
		case (c == '}' && top.kind == '{') || (c == ']' && top.kind == '['):
			return s.close(i), nil
		default:
			return nil, s.unexpected(i, c)
		}
	default:
		return nil, s.unexpected(i, c)
	}
	return nil, nil
}

func (s *Scanner) top() *scanFrame { return &s.stack[len(s.stack)-1] }

func (s *Scanner) childSeg() string {
	switch top := s.top(); top.kind {
	case '{':
		return top.key
	case '[':
		return strconv.Itoa(top.index)
	}
	return ""
}

// close pops the container ending at i and reports it.
func (s *Scanner) close(i int) *ScanEvent {
	f := s.stack[len(s.stack)-1]
	s.stack = s.stack[:len(s.stack)-1]
	ev := s.complete(f.start, i+1)
	return &ev
}

// complete reports the value at buf[start:end] as a child of the top frame.
func (s *Scanner) complete(start, end int) ScanEvent {
	path := make([]string, 0, len(s.stack))
	// stack[0] is the root slot and stack[1] the root value: neither has a segment.
	for i := 2; i < len(s.stack); i++ {
		path = append(path, s.stack[i].seg)
	}
	if len(s.stack) > 1 {
		path = append(path, s.childSeg())
	}
	ev := ScanEvent{Path: path, Raw: append([]byte(nil), s.buf[start:end]...)}
	if top := s.top(); top.kind == 0 {
		top.state = scanDone
	} else {
		top.state = expectCommaOrEnd
	}
	return ev
}

func (s *Scanner) unexpected(i int, c byte) error {
	return fmt.Errorf("scan: unexpected %q at %d", c, i)
}

func isSpace(c byte) bool { return c == ' ' || c == '\n' || c == '\r' || c == '\t' }

func isDelimiter(c byte) bool { return isSpace(c) || c == ',' || c == '}' || c == ']' }
