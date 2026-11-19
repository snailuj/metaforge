#!/usr/bin/env bash
# Tests for deploy/lib/wasm-host.sh with fake rustup and cargo on a scratch PATH and HOME,
# so nothing is installed and the real toolchain is never touched:
#   deploy/lib/test-wasm-host.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
# shellcheck source=wasm-host.sh
. "${HERE}/wasm-host.sh"

FAILS=0
ok()   { echo "  PASS: $1"; }
fail() { echo "  FAIL: $1"; FAILS=$((FAILS + 1)); }

# A physics-wasm dir with a pinned toolchain file.
DIR="${T}/physics-wasm"; mkdir -p "$DIR"
printf '[toolchain]\nchannel = "1.97.0"\ntargets = ["wasm32-unknown-unknown"]\n' > "${DIR}/rust-toolchain.toml"

# New scratch home with a fake rustup. TOOLCHAINS and TARGETS say what it reports.
fake_home() { # <toolchains> <targets> [no-cargo] [no-rustup]
    local h; h="$(mktemp -d -p "$T")"; mkdir -p "${h}/.cargo/bin"
    if [ -z "${4:-}" ]; then
        cat > "${h}/.cargo/bin/rustup" <<SH
#!/bin/sh
case "\$1" in
  toolchain) printf '%s\n' $1 ;;
  target)    printf '%s\n' $2 ;;
esac
echo "\$*" >> "${h}/rustup.calls"
SH
        chmod +x "${h}/.cargo/bin/rustup"
    fi
    [ -n "${3:-}" ] || { printf '#!/bin/sh\nexit 0\n' > "${h}/.cargo/bin/cargo"; chmod +x "${h}/.cargo/bin/cargo"; }
    echo "$h"
}
# Runs the check in a subshell with only the fake home's bin dir and the system tools on PATH.
run_check() { # <home> -> sets OUT and RC
    OUT="$(HOME="$1" PATH="/usr/bin:/bin" bash -c ". '${HERE}/wasm-host.sh'; check_wasm_toolchain '${DIR}'; rc=\$?; echo \"cargo=\$(command -v cargo)\"; exit \$rc" 2>&1)"
    RC=$?
}

echo "== check_wasm_toolchain"
H="$(fake_home "1.97.0-x86_64-unknown-linux-gnu" "wasm32-unknown-unknown x86_64-unknown-linux-gnu")"
run_check "$H"
[ "$RC" = 0 ] && ok "passes when the pinned toolchain and target are installed" || fail "rc=$RC: $OUT"
case "$OUT" in *"cargo=${H}/.cargo/bin/cargo"*) ok "puts \$HOME/.cargo/bin on PATH for the build";; *) fail "cargo not on PATH: $OUT";; esac

H="$(fake_home "1.97.0-x86_64-unknown-linux-gnu" "wasm32-unknown-unknown" no-cargo)"
run_check "$H"
[ "$RC" != 0 ] && ok "fails without cargo" || fail "passed without cargo"
case "$OUT" in *"cargo is not on PATH"*"sh.rustup.rs"*"rustup show"*) ok "names cargo and prints the install commands";; *) fail "message: $OUT";; esac

H="$(fake_home "" "" "" no-rustup)"
run_check "$H"
[ "$RC" != 0 ] && ok "fails without rustup" || fail "passed without rustup"
case "$OUT" in *"rustup is not on PATH"*"--default-toolchain none"*) ok "names rustup and prints the install commands";; *) fail "message: $OUT";; esac

H="$(fake_home "stable-x86_64-unknown-linux-gnu" "wasm32-unknown-unknown")"
run_check "$H"
[ "$RC" != 0 ] && ok "fails when the pinned toolchain is not installed" || fail "passed with the wrong toolchain"
case "$OUT" in *"toolchain 1.97.0 is not installed"*"rustup show"*) ok "names the pinned toolchain";; *) fail "message: $OUT";; esac

H="$(fake_home "1.97.0-x86_64-unknown-linux-gnu" "x86_64-unknown-linux-gnu")"
run_check "$H"
[ "$RC" != 0 ] && ok "fails when the wasm target is not installed" || fail "passed without the target"
case "$OUT" in *"wasm32-unknown-unknown is not installed for 1.97.0"*"rustup show"*) ok "names the target";; *) fail "message: $OUT";; esac

echo "== idempotent"
H="$(fake_home "1.97.0-x86_64-unknown-linux-gnu" "wasm32-unknown-unknown")"
run_check "$H"; first="$RC"; run_check "$H"
[ "$first" = 0 ] && [ "$RC" = 0 ] && ok "a second run changes nothing and passes again" || fail "second run rc=$RC"
[ -s "${H}/rustup.calls" ] || fail "the check never asked rustup anything"
grep -qE "^(toolchain install|target add|component add|update|default|self)" "${H}/rustup.calls" && fail "the check installed something" || ok "never calls an installing rustup subcommand"

echo ""
[ "$FAILS" = 0 ] && echo "All passed" || { echo "${FAILS} failed"; exit 1; }
