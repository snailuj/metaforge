"""Pre-commit secret scan for data-pipeline/grading/.

Scans all files in the grading directory for high-entropy strings and known
secret prefixes (API keys, tokens, PEM keys). Intended to be wired up as a
git pre-commit hook:

    ln -sf $(pwd)/scripts/pre_commit_secret_scan.py .git/hooks/pre-commit

Callable as a library via ``scan_text(text)`` and ``scan_dir(directory)``.

Exit code:
    0 — no secrets found (or directory does not exist)
    1 — possible secrets detected
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Known secret-prefix patterns — regex, ordered longest-match first where
# patterns share a common prefix to avoid partial shadows.
# ---------------------------------------------------------------------------
KNOWN_PREFIXES: list[str] = [
    r"\bsk-[A-Za-z0-9_-]{20,}",            # OpenAI secret key
    r"\bghp_[A-Za-z0-9]{20,}",             # GitHub personal access token
    r"\bgho_[A-Za-z0-9]{20,}",             # GitHub OAuth token
    r"\bxox[bp]-[A-Za-z0-9-]{20,}",        # Slack bot/app token
    r"\bAKIA[A-Z0-9]{16}",                 # AWS access key
    r"-----BEGIN [A-Z ]+PRIVATE KEY-----",  # PEM private keys
]

# Entropy thresholds — tuned per character set.
# Hex alphabet has 16 chars → max entropy = log2(16) = 4.0 bits.
# A lower threshold (3.2) catches near-random hex (git SHAs, HMACs) while
# skipping repetitive patterns like "aaaa..." or "01010101...".
# Base64 alphabet has 64 chars → max entropy = 6.0 bits; 4.5 cuts well above
# structured data and well below truly random tokens.
HEX_ENTROPY_THRESHOLD = 3.2
B64_ENTROPY_THRESHOLD = 4.5

# Minimum token length before we bother computing entropy.  Short tokens have
# naturally lower entropy and would generate excessive false positives.
_ENTROPY_MIN_LEN = 28

# Patterns to identify candidate high-entropy tokens.
_HEX_RE = re.compile(r"\b[a-f0-9]{40,}\b")   # long lowercase hex (e.g. git SHA, HMAC)
_B64_RE = re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b")  # long base64

# JSONL field names whose values are known to be high-entropy but benign
# (e.g. content-addressed hashes used as record identifiers).  Values bound
# to these keys are stripped before entropy scanning so they don't cause
# false positives.
_BENIGN_HEX_FIELDS: frozenset[str] = frozenset({
    "chain_signature",   # SHA-256 of chain content — record identity, not a secret
    "synset_id",         # numeric string, but matches no entropy pattern anyway
})

# Pattern: strip "key": "value" pairs for known-benign fields from the text
# before running entropy checks.  Only targets double-quoted JSON string values.
_BENIGN_FIELD_RE = re.compile(
    r'"(?:' + "|".join(re.escape(f) for f in sorted(_BENIGN_HEX_FIELDS)) + r')"\s*:\s*"[^"]*"'
)


def shannon_entropy(s: str) -> float:
    """Return the Shannon entropy (bits per character) of string *s*."""
    if not s:
        return 0.0
    total = len(s)
    counts = {c: s.count(c) for c in set(s)}
    return -sum((c / total) * math.log2(c / total) for c in counts.values())


def scan_text(text: str) -> list[str]:
    """Scan *text* for secret indicators.

    Returns a list of human-readable finding strings — one per match found.
    An empty list means no secrets were detected.

    Known-benign JSONL field values (e.g. ``chain_signature``) are stripped
    before entropy checks to avoid false positives from content-addressed hashes.
    Known-prefix patterns are applied to the *original* text so that an actual
    secret stored under a benign-looking key name is still caught.
    """
    findings: list[str] = []

    # --- Known-prefix patterns (applied to original text) ---
    for pattern in KNOWN_PREFIXES:
        for m in re.finditer(pattern, text):
            snippet = m.group(0)[:40]
            findings.append(f"known secret prefix: {snippet}…")

    # Strip known-benign hex field values before entropy scanning to suppress
    # false positives from content-addressed identifiers like chain_signature.
    entropy_text = _BENIGN_FIELD_RE.sub("", text)

    # --- High-entropy hex tokens ---
    for m in _HEX_RE.finditer(entropy_text):
        token = m.group(0)
        if len(token) >= _ENTROPY_MIN_LEN and shannon_entropy(token) >= HEX_ENTROPY_THRESHOLD:
            findings.append(f"high-entropy hex: {token[:40]}…")

    # --- High-entropy base64 tokens ---
    for m in _B64_RE.finditer(entropy_text):
        token = m.group(0)
        if len(token) >= _ENTROPY_MIN_LEN and shannon_entropy(token) >= B64_ENTROPY_THRESHOLD:
            findings.append(f"high-entropy base64: {token[:40]}…")

    return findings


def scan_dir(directory: Path) -> dict[str, list[str]]:
    """Recursively scan all files in *directory* for secret indicators.

    Returns a dict mapping file path strings to lists of finding strings.
    Files with no findings are omitted.  Returns an empty dict if the
    directory does not exist.
    """
    out: dict[str, list[str]] = {}

    if not directory.exists():
        return out

    for fpath in directory.rglob("*"):
        if not fpath.is_file():
            continue
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except Exception:
            # Unreadable file — skip silently; we are in a scan, not an audit.
            continue

        file_findings = scan_text(text)
        if file_findings:
            out[str(fpath)] = file_findings

    return out


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    target = repo_root / "data-pipeline" / "grading"
    findings = scan_dir(target)

    if not findings:
        return 0

    print(
        "Pre-commit secret scan FAILED — possible secrets in grading data:",
        file=sys.stderr,
    )
    for path, items in findings.items():
        print(f"  {path}:", file=sys.stderr)
        for item in items:
            print(f"    {item}", file=sys.stderr)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
