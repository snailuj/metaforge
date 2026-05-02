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
inputs) are recorded as ``status='failed'`` + ``error`` and do NOT
abort the rest of the sweep — preserves partial work for idempotent
re-runs.

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
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
import evaluate_aptness
from utils import get_git_commit

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1


# --- Config loading ----------------------------------------------------------

def load_sweep_config(path: str) -> dict[str, Any]:
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
        data = yaml.safe_load(text)
    elif suffix == ".json":
        data = json.loads(text)
    else:
        raise ValueError(
            f"Unsupported config extension {suffix!r}: use .yaml/.yml/.json"
        )

    if not isinstance(data, dict):
        raise ValueError(
            f"Sweep config {path}: top-level must be a mapping, got {type(data).__name__}"
        )
    if "variations" not in data or not isinstance(data["variations"], list):
        raise ValueError(
            f"Sweep config {path}: missing/invalid 'variations' list"
        )
    return data


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
    data = json.loads(ref_path.read_text())
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
    variation: dict[str, Any],
    db_path: str,
    pairs_file: str,
    controls_file: str,
) -> dict[str, Any]:
    """Run a single variation. Returns a result dict (success or failed).

    On any exception (unknown scoring, DB error, malformed input) the
    failure is captured into the result dict with ``status='failed'``
    and the exception type+message in ``error`` — the sweep continues.
    """
    name = variation.get("name", "<unnamed>")
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
            name, scoring, exc,
        )
        return {
            "name": name,
            "scoring": scoring,
            "threshold_percentile": threshold_percentile,
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
            "duration_ms": duration_ms,
        }

    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    agg = result["aggregate"]
    log.info(
        "variation finish: name=%s scoring=%s separation=%.4f "
        "aptness=%.4f n_apt=%d n_inapt=%d duration_ms=%g",
        name, scoring, result["separation_score"],
        result["aptness_rate"], agg["n_apt"], agg["n_inapt"], duration_ms,
    )
    return {
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
        "status": "ok",
        "error": None,
        "duration_ms": duration_ms,
    }


# --- Sweep orchestrator ------------------------------------------------------

def run_sweep(
    config: dict[str, Any],
    config_path: str,
) -> dict[str, Any]:
    """Execute every variation in ``config`` and return a structured result.

    Validates that referenced inputs (db, pairs, controls) exist before
    running any variation — saves wasted compute on a typo. Per-variation
    failures are caught inside :func:`_run_one_variation` and surfaced
    in the per-variation entry rather than aborting the sweep.
    """
    db_path = config.get("db")
    pairs_file = config.get("pairs")
    controls_file = config.get("controls")
    mrr_ref_path = config.get("mrr_reference")

    for label, value in (("db", db_path), ("pairs", pairs_file), ("controls", controls_file)):
        if not value:
            raise ValueError(f"Sweep config: missing required key {label!r}")
        if not Path(value).is_file():
            raise FileNotFoundError(
                f"Sweep config {label}={value!r}: path does not exist"
            )

    mrr_ref_value = load_mrr_reference(mrr_ref_path)

    variations = config["variations"]
    log.info(
        "sweep start: name=%s db=%s variations=%d mrr_ref=%s",
        config.get("name", "<unnamed>"), db_path, len(variations),
        mrr_ref_path or "n/a",
    )

    sweep_started = time.perf_counter()
    per_var_results: list[dict[str, Any]] = []
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

def _rank_key(row: dict[str, Any]) -> tuple[int, float]:
    """Sort key: ok rows first, then DESC by separation_score.

    Failed rows pin to the bottom (rank 1 > rank 0). Within the ok group,
    higher separation_score floats first — negate the value so an ascending
    sort gives DESC order.
    """
    if row["status"] != "ok":
        return (1, 0.0)
    return (0, -float(row.get("separation_score", 0.0)))


def render_markdown_report(sweep_result: dict[str, Any]) -> str:
    """Render a ranked markdown comparison table from a sweep result."""
    mrr_ref = sweep_result.get("mrr_reference_value")
    mrr_ref_str = f"{mrr_ref:.4f}" if mrr_ref is not None else "n/a"

    header = (
        f"# Sweep Report: {sweep_result.get('name', '<unnamed>')}\n\n"
        f"- **Timestamp:** {sweep_result['timestamp']}\n"
        f"- **Git commit:** {sweep_result['git_commit']}\n"
        f"- **Config:** {sweep_result['config_path']}\n"
        f"- **DB:** {sweep_result['db_path']}\n"
        f"- **MRR reference:** "
        f"{sweep_result.get('mrr_reference_path') or 'n/a'} "
        f"({mrr_ref_str})\n"
        f"- **Variations:** {len(sweep_result['variations'])} "
        f"(duration {sweep_result['duration_ms']:.0f}ms)\n\n"
    )

    cols = [
        "name", "scoring", "threshold", "aptness_rate", "separation_score",
        "mean_apt", "mean_inapt", "n_apt", "n_inapt", "mrr_ref", "status",
    ]
    table = "| " + " | ".join(cols) + " |\n"
    table += "|" + "|".join(["---"] * len(cols)) + "|\n"

    for row in sorted(sweep_result["variations"], key=_rank_key):
        if row["status"] == "ok":
            cells = [
                str(row["name"]),
                str(row["scoring"]),
                f"{row['threshold']:.4f}",
                f"{row['aptness_rate']:.4f}",
                f"{row['separation_score']:.4f}",
                f"{row['mean_apt_score']:.4f}",
                f"{row['mean_inapt_score']:.4f}",
                str(row["n_apt"]),
                str(row["n_inapt"]),
                mrr_ref_str,
                "ok",
            ]
        else:
            err = row.get("error", "?")
            cells = [
                str(row["name"]),
                str(row["scoring"]),
                "—", "—", "—", "—", "—", "—", "—", mrr_ref_str,
                f"failed: {err}",
            ]
        table += "| " + " | ".join(cells) + " |\n"

    return header + table


# --- CLI ---------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parameter sweep harness over evaluate_aptness",
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
    args = parser.parse_args()

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


if __name__ == "__main__":
    main()
