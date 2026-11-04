#!/usr/bin/env bash
# Shared helpers for the deploy sandbox checks. Source, do not execute.

# Render a unit template with a real worktree path.
render_unit() { # <template> <worktree> <dest>
    sed "s|__WORKTREE__|$2|g" "$1" > "$3"
}

# Print the [Service] directives that shape the sandbox (one Key=Value per line,
# continuation lines joined), so a transient unit can be started with exactly the
# properties the installed unit would have. Exec*, Environment* and Restart* are
# left out on purpose: the probes run their own command.
sandbox_props() { # <rendered unit>
    awk '
        /^\[/ { in_svc = ($0 == "[Service]"); next }
        !in_svc { next }
        { line = $0
          while (line ~ /\\$/) { sub(/\\$/, "", line); if ((getline nxt) <= 0) break; line = line " " nxt }
          print line }
    ' "$1" | grep -E '^(User|Group|NoNewPrivileges|Protect[A-Za-z]*|BindReadOnlyPaths|BindPaths|ReadWritePaths|ReadOnlyPaths|InaccessiblePaths|StateDirectory|StateDirectoryMode|Private[A-Za-z]*|CapabilityBoundingSet|AmbientCapabilities|Restrict[A-Za-z]*|LockPersonality|SystemCallArchitectures|SystemCallFilter|UMask)=' || true
}

# Re-point /var/lib/metaforge at the scratch state dir so a probe never touches
# live state.
scratch_state() { sed 's|/var/lib/metaforge|/var/lib/mf-sandbox-test|g; /^StateDirectory=/s|metaforge|mf-sandbox-test|g'; }

# Run a shell snippet inside a transient unit that has the given properties.
# Stdout carries the snippet's output; the unit is removed afterwards (--collect).
run_sandboxed() { # <unit-suffix> <props-file> <snippet>
    local name="mf-sandbox-test-$1" args=() line
    while IFS= read -r line; do [ -n "$line" ] && args+=(-p "$line"); done < "$2"
    sudo systemd-run --quiet --wait --pipe --collect -u "$name" "${args[@]}" /bin/sh -c "$3"
}
