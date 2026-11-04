"""Runs INSIDE the transient sandbox started by deploy/grading/check-sandbox.sh.

Prints one line per probe, "can:<name>" or "cannot:<name>"; the caller asserts which
of those the sandbox should allow. Reads GRADING_DATA_DIR / GRADING_DATA_GIT_ROOT as
the unit would, plus PROBE_CODE_DIR and PROBE_MAIN_GIT (set by the checker).
"""
import os
import subprocess
import sys
import traceback
from pathlib import Path


def writable(path: str) -> bool:
    try:
        with open(path, "w") as f:
            f.write("probe")
        os.unlink(path)
        return True
    except OSError:
        return False


def say(ok: bool, name: str) -> None:
    print(f"{'can' if ok else 'cannot'}:{name}", flush=True)


def commit_count(root: str) -> int:
    out = subprocess.run(["git", "-C", root, "rev-list", "--count", "HEAD"],
                         check=True, capture_output=True, text=True).stdout
    return int(out)


def main() -> int:
    code = os.environ["PROBE_CODE_DIR"]
    git_root = os.environ["GRADING_DATA_GIT_ROOT"]
    data_dir = Path(os.environ["GRADING_DATA_DIR"])

    try:
        from grading_sidecar.app import create_app
        from grading_sidecar.autocommit import autocommit_once
        create_app()
        say(True, "create-app")
    except Exception:
        traceback.print_exc()
        say(False, "create-app")
        return 0

    say(writable(f"{code}/deploy/.mf-probe"), "write-code")
    say(writable(f"{os.environ['PROBE_MAIN_GIT']}/.mf-probe"), "write-main-git")
    say(os.path.exists("/home/agent/.ssh"), "see-ssh")

    before = commit_count(git_root)
    with open(data_dir / "sandbox_probe_provisional.jsonl", "a", encoding="utf-8") as f:
        f.write('{"probe": true}\n')
    say(True, "write-data")
    autocommit_once(git_root, "data-pipeline/grading/")
    say(commit_count(git_root) == before + 1, "autocommit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
