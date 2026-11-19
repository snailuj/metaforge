# Staging deploy

`deploy.sh` redeploys staging from this worktree (`.worktrees/next`, tracking `main`). Run it as `agent`, the user that owns the worktree and runs the frontend build.

## One-time Rust setup

Staging builds the physics engine (`web/physics-wasm`) from source with the toolchain pinned in `web/physics-wasm/rust-toolchain.toml`. `deploy.sh` checks for it before doing any work and stops with these steps if something is missing. It installs nothing itself.

Run as `agent`, from the worktree root:

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal --default-toolchain none
. "$HOME/.cargo/env"
cd web/physics-wasm && rustup show
```

`--default-toolchain none` installs rustup only. `rustup show` inside `web/physics-wasm` reads the toolchain file and installs the pinned toolchain and the `wasm32-unknown-unknown` target.

Check, in the same directory:

```bash
rustup target list --installed
```

The output must include `wasm32-unknown-unknown`.

Changing the pin in `rust-toolchain.toml` needs `rustup show` again in that directory; the next deploy stops at its toolchain check until then.

The check is tested by `deploy/lib/test-wasm-host.sh`.
