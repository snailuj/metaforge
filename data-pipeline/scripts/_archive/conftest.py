"""Skip pytest collection inside the archive subdirectory.

Archived scripts (and their tests) reference module names that no
longer resolve from the archive's deeper directory layout. We keep
them frozen as historical artefacts — re-running them isn't supported
and adding sys.path shims would pretend otherwise.
"""
collect_ignore_glob = ["*.py"]
