// main_test.go — exec-level tests that cover the startup boundary
// (env var parsing → log.Fatalf escalation) which can't be exercised
// from package-internal Go tests because main() owns the process exit.
package main

import (
	"bytes"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

// TestMain_MalformedGamma_FailsLoud verifies that a malformed
// METAFORGE_FORGE_GAMMA env var aborts startup with a non-zero exit
// instead of silently degrading to Gamma=0 (M05 disabled). The
// envFloat helper's Warn-and-default behaviour is fine for low-impact
// env vars (CORS origin); Gamma changes scoring math and a silent
// fall-through defeats the entire point of the NewGamma boundary
// cast. See cascade.go NewGamma docstring.
func TestMain_MalformedGamma_FailsLoud(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping exec test in -short mode")
	}

	tmp := t.TempDir()
	bin := filepath.Join(tmp, "metaforge")

	// Build the binary into the temp dir. We invoke `go build` rather
	// than rely on a pre-built artefact so the test is self-contained
	// and CI-portable.
	build := exec.Command("go", "build", "-o", bin, ".")
	build.Dir = "."
	var buildErr bytes.Buffer
	build.Stderr = &buildErr
	if err := build.Run(); err != nil {
		t.Fatalf("go build: %v\nstderr: %s", err, buildErr.String())
	}

	// Run with a bogus Gamma value. The fatal must fire BEFORE the DB
	// open (otherwise an unrelated DB-not-found error could mask the
	// real signal), so we point --db at a file that does exist (the
	// binary itself) to make sure DB-open isn't what kills the process.
	cmd := exec.Command(bin, "--db", bin, "--port", "0")
	cmd.Env = append(os.Environ(),
		"METAFORGE_FORGE_GAMMA=zzz",
		// Force a CORS origin so unrelated flags don't try to read $HOME
		"METAFORGE_FORGE_CASCADE=0",
	)
	var stderr bytes.Buffer
	cmd.Stderr = &stderr
	err := cmd.Run()

	if err == nil {
		t.Fatalf("expected non-zero exit on malformed METAFORGE_FORGE_GAMMA, got success. stderr:\n%s",
			stderr.String())
	}
	exitErr, ok := err.(*exec.ExitError)
	if !ok {
		t.Fatalf("expected *exec.ExitError, got %T: %v", err, err)
	}
	if exitErr.ExitCode() == 0 {
		t.Fatalf("expected non-zero exit code, got 0")
	}
	// The fatal log must mention the env var so the operator gets a
	// pointer to the actual problem AND must NOT mention DB / handler
	// startup — if those appear, the Gamma fatal didn't fire and the
	// process died from a downstream symptom instead.
	if !strings.Contains(stderr.String(), "METAFORGE_FORGE_GAMMA") {
		t.Errorf("expected fatal log to mention METAFORGE_FORGE_GAMMA, stderr:\n%s",
			stderr.String())
	}
	if strings.Contains(stderr.String(), "Failed to initialise") {
		t.Errorf("Gamma parse fatal must fire BEFORE handler init, but stderr shows handler-init failure:\n%s",
			stderr.String())
	}
}

// TestMain_EmptyGamma_FailsLoud — R3.PR.SFH O4: an explicit-empty
// METAFORGE_FORGE_GAMMA (e.g. `export METAFORGE_FORGE_GAMMA=` to clear
// it in a shell) is operationally indistinguishable from malformed
// input — both should fail loud. The previous gate
// `if envGamma != ""` treated explicit-empty as unset and silently
// degraded to Gamma=0, disabling M05 while the operator believed they
// had simply cleared a stale value. LookupEnv distinguishes "set to
// empty" from "not set"; empty must escalate via ParseFloat error.
func TestMain_EmptyGamma_FailsLoud(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping exec test in -short mode")
	}

	tmp := t.TempDir()
	bin := filepath.Join(tmp, "metaforge")

	build := exec.Command("go", "build", "-o", bin, ".")
	build.Dir = "."
	var buildErr bytes.Buffer
	build.Stderr = &buildErr
	if err := build.Run(); err != nil {
		t.Fatalf("go build: %v\nstderr: %s", err, buildErr.String())
	}

	cmd := exec.Command(bin, "--db", bin, "--port", "0")
	// Explicit empty value — distinct from unset. The fix must treat
	// this as a malformed signal and refuse to start.
	cmd.Env = append(os.Environ(),
		"METAFORGE_FORGE_GAMMA=",
		"METAFORGE_FORGE_CASCADE=0",
	)
	var stderr bytes.Buffer
	cmd.Stderr = &stderr
	err := cmd.Run()

	if err == nil {
		t.Fatalf("expected non-zero exit on explicit-empty METAFORGE_FORGE_GAMMA, got success. stderr:\n%s",
			stderr.String())
	}
	exitErr, ok := err.(*exec.ExitError)
	if !ok {
		t.Fatalf("expected *exec.ExitError, got %T: %v", err, err)
	}
	if exitErr.ExitCode() == 0 {
		t.Fatalf("expected non-zero exit code, got 0")
	}
	if !strings.Contains(stderr.String(), "METAFORGE_FORGE_GAMMA") {
		t.Errorf("expected fatal log to mention METAFORGE_FORGE_GAMMA, stderr:\n%s",
			stderr.String())
	}
	// Must die at the Gamma parse boundary, not later at handler init —
	// otherwise the env-var-empty signal got masked by a downstream
	// symptom.
	if strings.Contains(stderr.String(), "Failed to initialise") {
		t.Errorf("Gamma empty-value fatal must fire BEFORE handler init, but stderr shows handler-init failure:\n%s",
			stderr.String())
	}
}
