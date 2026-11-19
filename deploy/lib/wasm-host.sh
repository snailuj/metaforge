#!/usr/bin/env bash
# Rust toolchain check for the deploy scripts that build the physics engine. Source, do not
# execute. It only reads: nothing is installed from here, so the script a person runs as
# the deploy user is the one place the toolchain gets changed, by hand, once.

WASM_TARGET="wasm32-unknown-unknown"

# <physics-wasm dir> <what is missing>
_wasm_install_hint() {
    cat >&2 <<HINT
ERROR: $2
The physics engine is built from source on this host with the toolchain pinned in
${1}/rust-toolchain.toml. Run these once, as the user that runs deploy.sh:

  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal --default-toolchain none
  . "\$HOME/.cargo/env"
  cd ${1} && rustup show

then check, from the same directory, that this lists ${WASM_TARGET}:  rustup target list --installed
HINT
}

# check_wasm_toolchain <physics-wasm dir>
# Puts $HOME/.cargo/bin on PATH (rustup's own install location, absent from a
# non-interactive shell), then fails with the missing piece and the install commands unless
# rustup and cargo are found and the pinned toolchain has the wasm target. Reads the pin
# from the toolchain file and asks rustup about that toolchain by name, so it never starts
# an install that rustup would run on its own from inside the directory.
check_wasm_toolchain() {
    local dir="$1" channel
    [ -d "${HOME}/.cargo/bin" ] && PATH="${HOME}/.cargo/bin:${PATH}"
    export PATH
    if ! command -v rustup >/dev/null 2>&1; then
        _wasm_install_hint "$dir" "rustup is not on PATH (looked in PATH and ${HOME}/.cargo/bin)"; return 1
    fi
    if ! command -v cargo >/dev/null 2>&1; then
        _wasm_install_hint "$dir" "cargo is not on PATH (looked in PATH and ${HOME}/.cargo/bin)"; return 1
    fi
    channel="$(sed -n 's/^channel *= *"\(.*\)"/\1/p' "${dir}/rust-toolchain.toml" 2>/dev/null | head -n1)"
    if [ -z "$channel" ]; then
        echo "ERROR: no channel in ${dir}/rust-toolchain.toml" >&2; return 1
    fi
    if ! rustup toolchain list 2>/dev/null | grep -q "^${channel}-"; then
        _wasm_install_hint "$dir" "toolchain ${channel} is not installed"; return 1
    fi
    if ! rustup target list --toolchain "$channel" --installed 2>/dev/null | grep -qx "$WASM_TARGET"; then
        _wasm_install_hint "$dir" "target ${WASM_TARGET} is not installed for ${channel}"; return 1
    fi
    echo "Rust ${channel} with ${WASM_TARGET} found"
}
