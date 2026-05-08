# GSD Final Snapshot

_Archived 2026-05-03 during GSD decommission. This is the last `.gsd/last-snapshot.md` produced before the GSD machinery was removed. Preserved verbatim for historical reference; do not treat as live state._

# GSD context snapshot (2026-05-02T10:41:09.284Z)

## Active context
Active: M001-yywgwj / S01 / T01 — Import V2 enrichment JSON into database

## Top project memories
- [MEM008] (gotcha) Lit @state() on non-rendered properties causes unnecessary re-renders. Use plain private fields for internal state that doesn't affect the template.
- [MEM009] (gotcha) Shadow DOM means document.activeElement returns the host element, not inner elements. Use this.shadowRoot.activeElement for focus tracking inside Lit components.
- [MEM010] (gotcha) 3d-force-graph ships inaccurate .d.ts files. The project uses a local module declaration override in web/src/types/3d-force-graph.d.ts.
- [MEM011] (gotcha) Three.js WebGPU crashes in happy-dom test environment. Mock 3d-force-graph and three-spritetext with a Proxy chainable: const c = new Proxy({}, { get: () => () => c }).
- [MEM012] (gotcha) Python sqlite3.connect() with `with` statement does NOT close the connection — only commits/rollbacks. Use try/finally for cleanup to avoid locked database files.
- [MEM013] (environment) Go binary at /usr/local/go/bin/go — needs `export PATH="/usr/local/go/bin:$PATH"` before any go commands. Not on default PATH.
