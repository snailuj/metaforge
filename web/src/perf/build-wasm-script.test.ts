import { describe, it, expect } from 'vitest'
import { execFileSync } from 'node:child_process'
import { mkdtempSync, writeFileSync, chmodSync, readFileSync, rmSync, realpathSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'

// Rule: `npm run build:wasm` runs cargo from the folder that holds rust-toolchain.toml.
// rustup looks for the toolchain file from the working directory, not from --manifest-path,
// so cargo started anywhere else builds with whatever default toolchain the host has
// (or fails outright on a host installed with --default-toolchain none).
describe('npm run build:wasm', () => {
  it('starts cargo in the folder with the pinned toolchain file', () => {
    const dir = mkdtempSync(join(tmpdir(), 'fake-cargo-'))
    try {
      const log = join(dir, 'cwd.log')
      const fake = join(dir, 'cargo')
      writeFileSync(fake, `#!/bin/sh\npwd -P > "${log}"\nexit 1\n`)
      chmodSync(fake, 0o755)
      try {
        execFileSync('npm', ['run', '--silent', 'build:wasm'], {
          cwd: resolve(__dirname, '../..'),
          env: { ...process.env, PATH: `${dir}:${process.env.PATH}` },
          stdio: 'pipe',
        })
      } catch {
        // The fake cargo fails on purpose; only where it was started matters.
      }
      const cwd = readFileSync(log, 'utf8').trim()
      expect(cwd).toBe(realpathSync(resolve(__dirname, '../../physics-wasm')))
    } finally {
      rmSync(dir, { recursive: true, force: true })
    }
  })
})
