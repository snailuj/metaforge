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

// Start returns a stop function. When timing is enabled, calling stop
// emits a slog Info record tagged "timing" with the supplied label,
// elapsed milliseconds, and any extra attrs passed to stop. When timing
// is disabled, the returned stop function does no slog work and does
// not call time.Now — but two per-call costs remain regardless of the
// feature flag:
//
//  1. The closure literal `func(...any) {}` returned on the disabled
//     path is a fresh function value per call (escape analysis on a
//     func returning a func usually pushes it to the heap).
//  2. The variadic arg slice at the call site (e.g. `"word", w,
//     "candidates", n`) is constructed by the caller before the
//     no-op closure runs.
//
// So "NO-OP" here means "no I/O, no timing arithmetic", not "zero
// per-call allocation". Callers on hot paths that pass many extras
// should keep this in mind; for the cascade hot path (≤6 stages per
// request) the cost is negligible vs the slog and json-encode work
// the request is already paying for.
//
// Two usage patterns are supported:
//
//  1. Manual stop at known exit points (what the cascade handler uses
//     so it can tag each `outcome=` enum branch separately):
//         stopTotal := observe.Start("cascade_request_total")
//         ...
//         stopTotal("word", word, "outcome", "scored")
//
//  2. Deferred stop for single-exit functions:
//         defer observe.Start("cascade_request")("word", word, "candidates", n)
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
