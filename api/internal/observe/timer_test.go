package observe

import (
	"bytes"
	"log/slog"
	"strings"
	"testing"
	"time"
)

func TestStart_DisabledReturnsNoOp(t *testing.T) {
	var buf bytes.Buffer
	prev := slog.Default()
	slog.SetDefault(slog.New(slog.NewJSONHandler(&buf, &slog.HandlerOptions{Level: slog.LevelDebug})))
	defer slog.SetDefault(prev)

	Init(false)

	stop := Start("cache_load")
	time.Sleep(2 * time.Millisecond)
	stop()

	if buf.Len() != 0 {
		t.Fatalf("expected no log output when timing disabled, got: %s", buf.String())
	}
}

func TestStart_EnabledEmitsTimingRecord(t *testing.T) {
	var buf bytes.Buffer
	prev := slog.Default()
	slog.SetDefault(slog.New(slog.NewJSONHandler(&buf, &slog.HandlerOptions{Level: slog.LevelInfo})))
	defer slog.SetDefault(prev)

	Init(true)
	defer Init(false)

	stop := Start("cache_load")
	time.Sleep(2 * time.Millisecond)
	stop()

	out := buf.String()
	if !strings.Contains(out, `"label":"cache_load"`) {
		t.Fatalf("expected label in output, got: %s", out)
	}
	if !strings.Contains(out, `"elapsed_ms"`) {
		t.Fatalf("expected elapsed_ms in output, got: %s", out)
	}
}

func TestStart_EnabledIncludesExtraAttrs(t *testing.T) {
	var buf bytes.Buffer
	prev := slog.Default()
	slog.SetDefault(slog.New(slog.NewJSONHandler(&buf, &slog.HandlerOptions{Level: slog.LevelInfo})))
	defer slog.SetDefault(prev)

	Init(true)
	defer Init(false)

	stop := Start("cascade_request")
	stop("word", "anger", "candidates", 23)

	out := buf.String()
	if !strings.Contains(out, `"word":"anger"`) {
		t.Fatalf("expected word attr, got: %s", out)
	}
	if !strings.Contains(out, `"candidates":23`) {
		t.Fatalf("expected candidates attr, got: %s", out)
	}
}
