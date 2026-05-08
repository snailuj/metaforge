"""Parameter sweep harness for the aptness evaluator.

Runs ``evaluate_aptness.evaluate()`` once per variation in a sweep
config (YAML or JSON) and emits a structured JSON result + ranked
markdown comparison table.

Sweep config shape (YAML preferred for human authoring; JSON also
accepted — picked by file extension):

```yaml
name: baseline_v2
db: data-pipeline/output/lexicon_v2.db
pairs: data-pipeline/fixtures/metaphor_pairs_v2.json
controls: data-pipeline/fixtures/munch_inapt.jsonl
mrr_reference: data-pipeline/output/eval_baseline_v2.json   # optional
variations:
  - name: baseline
    scoring: jaccard_salience
    threshold_percentile: 95
  - name: raw
    scoring: jaccard_raw
    threshold_percentile: 95
```

Per-variation failures (unknown scoring, DB read error, malformed
inputs) are recorded as ``status='failed'`` + ``error_type`` +
``error_message`` and do NOT abort the rest of the sweep — preserves
partial work for idempotent re-runs.

Outputs:
  * ``--output PATH``   structured JSON with provenance + variations[]
  * ``--report PATH``   ranked markdown table (default: <output>.md)

Usage:
    python run_sweep.py \\
        --config data-pipeline/sweeps/baseline.yaml \\
        --output data-pipeline/output/sweep_results.json
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, NotRequired, TypedDict, Union, cast

sys.path.insert(0, str(Path(__file__).parent))
import evaluate_aptness
from utils import get_git_commit

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1


class OkVariationResult(TypedDict):
    """Successful variation row. ``status`` is the discriminator.

    ``false_positive_rate`` is preserved alongside ``aptness_rate`` because
    consumers (sweep-report tooling) compare them as a pair when judging
    a variation; dropping it would silently regress those reports.
    """
    status: Literal["ok"]
    name: str
    scoring: str
    threshold_percentile: float
    threshold: float
    aptness_rate: float
    false_positive_rate: float
    separation_score: float
    mean_apt_score: float
    mean_inapt_score: float
    n_apt: int
    n_inapt: int
    duration_ms: float


class FailedVariationResult(TypedDict):
    """Failed variation row. ``error`` is split into type + message so
    consumers can filter on error_type without re-parsing a string."""
    status: Literal["failed"]
    name: str
    scoring: str
    threshold_percentile: float
    error_type: str
    error_message: str
    duration_ms: float


VariationResult = Union[OkVariationResult, FailedVariationResult]


# --- Sweep config schema -----------------------------------------------------
#
# Required-by-default (total=True); genuinely optional keys are wrapped
# in NotRequired[...]. The runtime validator in load_sweep_config still
# owns the config-path-aware error messages, but the type now matches
# the invariants downstream code (run_sweep, render_markdown_report)
# already relies on — so static checkers can narrow key access.

class VariationSpec(TypedDict):
    name: str
    scoring: NotRequired[str]
    threshold_percentile: NotRequired[float]


ALLOWED_VARIATION_KEYS = frozenset(VariationSpec.__annotations__.keys())


class SweepConfig(TypedDict):
    db: str
    pairs: str
    controls: str
    variations: list[VariationSpec]
    name: NotRequired[str]
    mrr_reference: NotRequired[str]


ALLOWED_SWEEP_KEYS = frozenset(SweepConfig.__annotations__.keys())


# --- Config loading ----------------------------------------------------------

def load_sweep_config(path: str) -> SweepConfig:
    """Load a sweep config from a YAML or JSON file.

    Selects parser by file extension. YAML support is optional — if the
    config is .yaml/.yml and PyYAML isn't installed, raises with a clear
    install hint rather than a cryptic ImportError.
    """
    cfg_path = Path(path)
    if not cfg_path.is_file():
        raise FileNotFoundError(f"--config not found: {path}")

    text = cfg_path.read_text()
    suffix = cfg_path.suffix.lower()
    if suffix in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                f"YAML config requested ({path}) but PyYAML not installed. "
                f"Install with `pip install pyyaml` or use a .json config."
            ) from exc
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ValueError(
                f"sweep config {cfg_path}: invalid YAML ({exc})"
            ) from exc
    elif suffix == ".json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"sweep config {cfg_path}: invalid JSON ({exc})"
            ) from exc
    else:
        raise ValueError(
            f"Unsupported config extension {suffix!r}: use .yaml/.yml/.json"
        )

    if not isinstance(data, dict):
        raise ValueError(
            f"sweep config {path}: top-level must be a mapping, got {type(data).__name__}"
        )
    if "variations" not in data or not isinstance(data["variations"], list):
        raise ValueError(
            f"sweep config {path}: missing/invalid 'variations' list"
        )
    # Empty `variations: []` is a silent no-op: the sweep emits no rows
    # and main() still returns 0, indistinguishable from a successful
    # sweep on CI. Reject at the schema boundary so downstream code can
    # rely on a non-empty invariant.
    if len(data["variations"]) == 0:
        raise ValueError(
            f"sweep config {path}: 'variations' list is empty — at least "
            f"one variation is required. See "
            f"data-pipeline/sweeps/baseline_v2.yaml for the canonical config shape."
        )

    # Strict allow-list at the top level — typos like `scorring` are
    # silent footguns in a sweep harness, where a misspelled key reverts
    # to the default and the user pays the wasted compute.
    unknown_top = set(data) - ALLOWED_SWEEP_KEYS
    if unknown_top:
        raise ValueError(
            f"sweep config {path}: unknown key(s): {sorted(unknown_top)} "
            f"(allowed: {sorted(ALLOWED_SWEEP_KEYS)})"
        )

    # Required-key presence — enforced at the schema boundary so the
    # `cast(SweepConfig, data)` below honestly reflects the runtime
    # invariant and downstream code can rely on direct key access. Wording
    # mirrors the iter-6 path-prefixed lowercase pattern used elsewhere
    # in this validator.
    for required_key in ("db", "pairs", "controls"):
        if required_key not in data:
            raise ValueError(
                f"sweep config {path}: missing required key {required_key!r}"
                f" — see data-pipeline/sweeps/baseline_v2.yaml for the canonical config shape."
            )

    # Per-variation: allow-list, mandatory non-empty name, name uniqueness.
    seen_names: list[str] = []
    duplicates: list[str] = []
    for idx, var in enumerate(data["variations"]):
        if not isinstance(var, dict):
            raise ValueError(
                f"sweep config {path}: variation[{idx}] must be a mapping, "
                f"got {type(var).__name__}"
            )
        unknown_var = set(var) - ALLOWED_VARIATION_KEYS
        if unknown_var:
            raise ValueError(
                f"sweep config {path}: variation[{idx}] unknown key(s): "
                f"{sorted(unknown_var)} "
                f"(allowed: {sorted(ALLOWED_VARIATION_KEYS)})"
            )
        name = var.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(
                f"sweep config {path}: variation[{idx}] missing required "
                f"'name' (must be non-empty string) — see "
                f"data-pipeline/sweeps/baseline_v2.yaml for the canonical config shape."
            )
        if name in seen_names and name not in duplicates:
            duplicates.append(name)
        seen_names.append(name)

        # `scoring`, when set, must name a registered scoring fn. Without
        # this boundary check a typo (e.g. `jaccard_salinece`) only
        # surfaces inside `_run_one_variation` after sweep setup has begun
        # — wasted setup, partial artefacts, confused error attribution.
        # Mirror the rest of the validator: fail fast, name the file, the
        # variation, the bad value, and list the valid options.
        if "scoring" in var:
            scoring_value = var["scoring"]
            if scoring_value not in evaluate_aptness.SCORING_FNS:
                raise ValueError(
                    f"sweep config {path}: variation {name!r}: unknown "
                    f"scoring fn {scoring_value!r}; valid: "
                    f"{sorted(evaluate_aptness.SCORING_FNS)}"
                )

        # threshold_percentile must lie in [0, 100]. Out-of-range values
        # silently clamp to min/max sample inside `_percentile`, which is
        # a true silent fallback (no log, no signal). Reject at the schema
        # boundary so a typo (`-5` for `5`) cannot quietly degrade the run.
        if "threshold_percentile" in var:
            tp = var["threshold_percentile"]
            if not isinstance(tp, (int, float)) or isinstance(tp, bool):
                raise ValueError(
                    f"sweep config {path}: variation[{idx}] "
                    f"'threshold_percentile' must be a number in [0, 100], "
                    f"got {tp!r} ({type(tp).__name__})"
                )
            if not (0 <= tp <= 100):
                raise ValueError(
                    f"sweep config {path}: variation[{idx}] "
                    f"'threshold_percentile' must be a number in [0, 100], "
                    f"got {tp}"
                )
    if duplicates:
        raise ValueError(
            f"sweep config {path}: duplicate variation name(s): {duplicates}"
        )

    # Validator has enforced every required key + shape — narrow the
    # parsed dict to the schema type for downstream consumers.
    #
    # Belt-and-braces: the cast() below is a soft pact, so a future PR
    # adding a SweepConfig key without updating the validator would slip
    # through silently. This assert pins the join-point — any drift
    # between the validator and the TypedDict trips here, before the cast
    # papers over the gap. Should never fire under correct validation.
    required_top_keys = ("db", "pairs", "controls", "variations")
    assert all(k in data for k in required_top_keys), (
        f"validator drift: required keys missing at cast site: "
        f"{[k for k in required_top_keys if k not in data]}"
    )
    return cast(SweepConfig, data)


def load_mrr_reference(path: str | None) -> float | None:
    """Pull the MRR value from a baseline JSON. Returns None if path is None.

    Expected shape (eval_baseline_v2.json): ``{"mrr": {"value": float, ...}}``.
    Tolerates both nested and flat shapes for forward compatibility — flat
    ``{"mrr": 0.123}`` is also accepted in case the reference artifact ever
    flattens. Raises FileNotFoundError if the path is set but missing — a
    typo in the config should fail fast.
    """
    if not path:
        return None
    ref_path = Path(path)
    if not ref_path.is_file():
        raise FileNotFoundError(f"mrr_reference not found: {path}")
    try:
        data = json.loads(ref_path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"mrr_reference {ref_path}: invalid JSON ({exc})"
        ) from exc
    mrr = data.get("mrr")
    if isinstance(mrr, dict):
        value = mrr.get("value")
    else:
        value = mrr
    if value is None:
        raise ValueError(
            f"mrr_reference {path}: no 'mrr.value' or 'mrr' float found"
        )
    return float(value)


# --- Per-variation execution -------------------------------------------------

def _run_one_variation(
    variation: VariationSpec,
    db_path: str,
    pairs_file: str,
    controls_file: str,
) -> VariationResult:
    """Run a single variation. Returns a tagged-union result.

    On any exception (unknown scoring, DB error, malformed input) the
    failure is captured into a :class:`FailedVariationResult` with the
    exception type and message split into separate fields — the sweep
    continues.
    """
    # `name` is validator-enforced (load_sweep_config requires every
    # variation to declare a non-empty string name) — direct key access
    # narrows from Optional[str] to str.
    name = variation["name"]
    scoring = variation.get("scoring", evaluate_aptness.DEFAULT_SCORING)
    threshold_percentile = float(variation.get("threshold_percentile", 95.0))

    log.info(
        "variation start: name=%s scoring=%s threshold_pct=%g",
        name, scoring, threshold_percentile,
    )
    started = time.perf_counter()
    try:
        # Open a fresh connection per variation — keeps failures
        # independent and avoids cross-variation transaction state.
        conn = sqlite3.connect(db_path)
        try:
            result = evaluate_aptness.evaluate(
                conn=conn,
                pairs_file=pairs_file,
                controls_file=controls_file,
                threshold_percentile=threshold_percentile,
                db_path=db_path,
                scoring=scoring,
            )
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 — per-variation isolation is required
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        log.warning(
            "variation failed: name=%s scoring=%s error=%s",
            name, scoring, exc, exc_info=True,
        )
        failed: FailedVariationResult = {
            "status": "failed",
            "name": name,
            "scoring": scoring,
            "threshold_percentile": threshold_percentile,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "duration_ms": duration_ms,
        }
        return failed

    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    agg = result["aggregate"]
    log.info(
        "variation finish: name=%s scoring=%s separation=%.4f "
        "aptness=%.4f n_apt=%d n_inapt=%d duration_ms=%g",
        name, scoring, result["separation_score"],
        result["aptness_rate"], agg["n_apt"], agg["n_inapt"], duration_ms,
    )
    ok: OkVariationResult = {
        "status": "ok",
        "name": name,
        "scoring": scoring,
        "threshold_percentile": threshold_percentile,
        "threshold": result["config"]["threshold"],
        "aptness_rate": result["aptness_rate"],
        "false_positive_rate": result["false_positive_rate"],
        "separation_score": result["separation_score"],
        "mean_apt_score": agg["mean_apt_score"],
        "mean_inapt_score": agg["mean_inapt_score"],
        "n_apt": agg["n_apt"],
        "n_inapt": agg["n_inapt"],
        "duration_ms": duration_ms,
    }
    return ok


# --- Sweep orchestrator ------------------------------------------------------

def run_sweep(
    config: SweepConfig,
    config_path: str,
) -> dict[str, Any]:
    """Execute every variation in ``config`` and return a structured result.

    Validates that referenced inputs (db, pairs, controls) exist before
    running any variation — saves wasted compute on a typo. Per-variation
    failures are caught inside :func:`_run_one_variation` and surfaced
    in the per-variation entry rather than aborting the sweep.
    """
    # `db`, `pairs`, `controls` presence is validator-enforced in
    # load_sweep_config, so direct key access narrows from Optional[str]
    # to str. Only the I/O check (path exists) remains here — that's a
    # filesystem concern, not a schema one.
    db_path = config["db"]
    pairs_file = config["pairs"]
    controls_file = config["controls"]
    mrr_ref_path = config.get("mrr_reference")

    for label, value in (("db", db_path), ("pairs", pairs_file), ("controls", controls_file)):
        if not Path(value).is_file():
            raise FileNotFoundError(
                f"sweep config {label}={value!r}: path does not exist"
            )

    mrr_ref_value = load_mrr_reference(mrr_ref_path)

    variations = config["variations"]
    log.info(
        "sweep start: name=%s db=%s variations=%d mrr_ref=%s",
        config.get("name", "<unnamed>"), db_path, len(variations),
        mrr_ref_path or "n/a",
    )

    sweep_started = time.perf_counter()
    per_var_results: list[VariationResult] = []
    for variation in variations:
        per_var_results.append(_run_one_variation(
            variation=variation,
            db_path=db_path,
            pairs_file=pairs_file,
            controls_file=controls_file,
        ))
    sweep_duration_ms = round((time.perf_counter() - sweep_started) * 1000, 2)

    log.info(
        "sweep finish: variations=%d ok=%d failed=%d duration_ms=%g",
        len(per_var_results),
        sum(1 for r in per_var_results if r["status"] == "ok"),
        sum(1 for r in per_var_results if r["status"] == "failed"),
        sweep_duration_ms,
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "name": config.get("name", "<unnamed>"),
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_commit": get_git_commit(),
        "config_path": config_path,
        "db_path": db_path,
        "pairs_file": pairs_file,
        "controls_file": controls_file,
        "mrr_reference_path": mrr_ref_path,
        "mrr_reference_value": mrr_ref_value,
        "duration_ms": sweep_duration_ms,
        "variations": per_var_results,
    }


# --- Markdown report ---------------------------------------------------------

def _rank_key(row: VariationResult) -> tuple[int, float]:
    """Sort key: ok rows first, then DESC by separation_score.

    Failed rows pin to the bottom (rank 1 > rank 0). Within the ok group,
    higher separation_score floats first — negate the value so an ascending
    sort gives DESC order.
    """
    if row["status"] != "ok":
        return (1, 0.0)
    return (0, -float(row["separation_score"]))


def render_markdown_report(sweep_result: dict[str, Any]) -> str:
    """Render a ranked markdown comparison table from a sweep result.

    Layout:
      1. Header block (timestamp, commit, config, db, mrr reference,
         variation count + total duration).
      2. ``## Summary`` — one line stating ok/failed counts and the
         best-by-separation_score variation (or "all failed" when M==N).
      3. The per-row table, ranked by separation_score DESC, with a
         leading ``rank`` column. Failed rows pin to the bottom with
         em-dashes in numeric cells and a bare ``failed`` token; full
         error detail moves to the Failures appendix below.
      4. ``## Failures`` — appended IFF any variation failed.
    """
    mrr_ref = sweep_result.get("mrr_reference_value")
    mrr_ref_str = f"{mrr_ref:.4f}" if mrr_ref is not None else "n/a"

    variations = sweep_result["variations"]
    ok_rows = [r for r in variations if r["status"] == "ok"]
    failed_rows = [r for r in variations if r["status"] == "failed"]
    total = len(variations)

    header = (
        f"# Sweep Report: {sweep_result.get('name', '<unnamed>')}\n\n"
        f"- **Timestamp:** {sweep_result['timestamp']}\n"
        f"- **Git commit:** {sweep_result['git_commit']}\n"
        f"- **Config:** {sweep_result['config_path']}\n"
        f"- **DB:** {sweep_result['db_path']}\n"
        f"- **MRR reference:** "
        f"{sweep_result.get('mrr_reference_path') or 'n/a'} "
        f"({mrr_ref_str})\n"
        f"- **Variations:** {total} "
        f"(duration {sweep_result['duration_ms']:.0f}ms)\n\n"
    )

    # Summary line — state ok/failed counts and the winner so an
    # operator can read the headline without scanning the table. The
    # validator guarantees `variations` is non-empty, so exactly one
    # of `ok_rows` or `failed_rows` is non-empty here.
    if ok_rows:
        best = max(ok_rows, key=lambda r: r["separation_score"])
        summary_tail = (
            f"Best by separation_score: {best['name']} "
            f"({best['separation_score']:.4f})."
        )
    else:
        summary_tail = "All variations failed — see Failures below."
    summary = (
        f"## Summary\n\n"
        f"**{len(ok_rows)} variation(s) succeeded, "
        f"{len(failed_rows)} failed.** {summary_tail}\n\n"
    )

    # Per-row table. Rank column pins ordering for skim-readability;
    # mrr_ref column is dropped because the global reference already
    # appears once in the header block.
    cols = [
        "rank", "name", "scoring", "threshold", "aptness_rate",
        "separation_score", "mean_apt", "mean_inapt", "n_apt", "n_inapt",
        "status",
    ]
    table = "| " + " | ".join(cols) + " |\n"
    table += "|" + "|".join(["---"] * len(cols)) + "|\n"

    rank_counter = 0
    for row in sorted(variations, key=_rank_key):
        if row["status"] == "ok":
            rank_counter += 1
            cells = [
                str(rank_counter),
                str(row["name"]),
                str(row["scoring"]),
                f"{row['threshold']:.4f}",
                f"{row['aptness_rate']:.4f}",
                f"{row['separation_score']:.4f}",
                f"{row['mean_apt_score']:.4f}",
                f"{row['mean_inapt_score']:.4f}",
                str(row["n_apt"]),
                str(row["n_inapt"]),
                "ok",
            ]
        else:
            cells = [
                "—",
                str(row["name"]),
                str(row["scoring"]),
                "—", "—", "—", "—", "—", "—", "—",
                "failed",
            ]
        table += "| " + " | ".join(cells) + " |\n"

    body = header + summary + table

    if failed_rows:
        failures = ["\n## Failures\n"]
        for row in failed_rows:
            failures.append(
                f"\n### {row['name']} ({row['scoring']})\n"
                f"- error_type: {row['error_type']}\n"
                f"- error_message: {row['error_message']}\n"
            )
        body += "".join(failures)

    return body


# --- CLI ---------------------------------------------------------------------

def _build_arg_parser() -> argparse.ArgumentParser:
    """Construct the run_sweep CLI parser.

    Pulled out as a builder so tests can introspect ``--help`` without
    spawning a subprocess. The available scoring formulas are read from
    ``evaluate_aptness.SCORING_FNS`` at parser-construction time so the
    help text stays in sync with the registry — no manual edit required
    when a new formula is added.
    """
    formulas = ", ".join(sorted(evaluate_aptness.SCORING_FNS.keys()))
    parser = argparse.ArgumentParser(
        description="Parameter sweep harness over evaluate_aptness",
        epilog=f"Available scoring formulas: {formulas}",
    )
    parser.add_argument(
        "--config", required=True,
        help="Sweep config (YAML or JSON, picked by extension)",
    )
    parser.add_argument(
        "--output", "-o", required=True,
        help="Output JSON path for structured results",
    )
    parser.add_argument(
        "--report", default=None,
        help="Markdown report path (default: <output>.md alongside JSON)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable debug logging",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint.

    Returns an integer exit code so CI can distinguish three outcomes:
      * 0 — every variation succeeded
      * 1 — partial failure (some variations failed, some succeeded)
      * 2 — catastrophic failure (every variation failed); a separate code
            from 1 lets a scheduled job bisect "the sweep itself is broken"
            (schema drift, missing fixture, malformed config) from "one
            variation has a bad parameter".

    ``argv`` is accepted for testability — pytest can drive ``main`` without
    ``sys.exit`` killing the process. When ``argv`` is None, argparse falls
    back to ``sys.argv[1:]`` as usual.
    """
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    config = load_sweep_config(args.config)
    sweep_result = run_sweep(config, config_path=args.config)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(sweep_result, indent=2))
    log.info("wrote JSON results to %s", output_path)

    report_path = Path(args.report) if args.report else output_path.with_suffix(".md")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_markdown_report(sweep_result))
    log.info("wrote markdown report to %s", report_path)

    # Escalate failures to the exit code so scheduled/CI invocations can
    # detect a broken sweep — the per-variation status row is not enough
    # because a fully-broken sweep still writes a "successful" artefact.
    variations = sweep_result["variations"]
    total = len(variations)
    failed_count = sum(1 for v in variations if v["status"] == "failed")

    if failed_count == 0:
        return 0
    if failed_count == total:
        log.error("sweep finish: ALL %d variation(s) failed", total)
        return 2
    log.warning(
        "sweep finish: ok=%d failed=%d of %d (partial failure)",
        total - failed_count, failed_count, total,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
