// Package observe provides feature-flagged timing instrumentation for
// long-running or product-critical routines (e.g. the cascade hot path).
//
// Per the project Observability standard: timer functions must devolve
// to NO-OP when the feature flag is disabled and in all production
// deployments. Enable in non-production by setting METAFORGE_CASCADE_TIMING=1
// (wired through main.go → observe.Init).
package observe

import (
	"log/slog"
	"sync/atomic"
	"time"
)

// enabled is read on every Start call. atomic.Bool keeps the read cheap
// (one MOV) so the NO-OP path stays cheap even on hot routines.
var enabled atomic.Bool

// Init toggles timing collection. Call once at process start from main.
// Safe to call multiple times for tests.
func Init(on bool) {
	enabled.Store(on)
}

// Enabled reports whether timing collection is on. Useful for callers that
// want to skip allocating attrs for the disabled path.
func Enabled() bool {
	return enabled.Load()
}

// Start returns a stop function. When timing is enabled, calling stop
// emits a slog Info record tagged "timing" with the supplied label,
// elapsed milliseconds, and any extra attrs passed to stop. When timing
// is disabled, Start returns a NO-OP stop and does no allocation beyond
// the closure itself.
//
// Pattern:
//
//	defer observe.Start("cascade_request")("word", word, "candidates", n)
//
// Extra attrs are appended to the timing record so callers can include
// per-call context (input size, output count, etc).
func Start(label string) func(extra ...any) {
	if !enabled.Load() {
		return func(...any) {}
	}
	start := time.Now()
	return func(extra ...any) {
		elapsedMs := time.Since(start).Milliseconds()
		attrs := make([]any, 0, 4+len(extra))
		attrs = append(attrs, "label", label, "elapsed_ms", elapsedMs)
		attrs = append(attrs, extra...)
		slog.Info("timing", attrs...)
	}
}
