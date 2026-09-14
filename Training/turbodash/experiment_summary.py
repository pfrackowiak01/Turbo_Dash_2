from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .manifest import write_json
from .paths import RUNS_ROOT

RUN_SPECS = (
    ("ppo-continuous-5m-run1", 20260916, "ppo-continuous-run1-best-validation-500"),
    ("ppo-continuous-5m-run2", 20260917, "ppo-continuous-run2-best-validation-500"),
    ("ppo-continuous-5m-run3", 20260918, "ppo-continuous-run3-best-validation-500"),
)

REPORTED_METRICS = {
    "lifeLossCount": "life_loss_count",
    "collisions": "collisions",
    "obstaclesAvoided": "obstacles_avoided",
    "maxLevel": "max_level",
    "Hearts": "hearts_collected",
    "Shields": "shields_collected",
    "Boosts": "boosts_collected",
    "Gold": "gold_collected",
    "Diamonds": "diamonds_collected",
    "turboActivations": "turbo_activations",
}
COUNT_METRIC_NAMES = tuple(name for name in REPORTED_METRICS if name != "maxLevel")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Required experiment artifact is missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validate_summary(summary: dict[str, Any], max_duration: float) -> None:
    if int(summary.get("episodes", 0)) != 100:
        raise ValueError("Validation summary must contain exactly 100 episodes")
    if summary.get("action_space") != "Continuous":
        raise ValueError("Validation summary is not PPO Continuous")
    if not math.isclose(float(summary.get("max_duration", -1)), max_duration, rel_tol=0, abs_tol=1e-6):
        raise ValueError(f"Validation summary does not use MaxDuration={max_duration:g}")
    if summary.get("test_status") != "UNUSED FOR TRAINING/TUNING/EVALUATION":
        raise ValueError("Validation summary does not confirm TEST UNUSED")


def build_experiment_summary(runs_root: Path, wall_seconds: float) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for run_id, experiment_seed, validation_run_id in RUN_SPECS:
        run_dir = runs_root / run_id
        manifest = _read_json(run_dir / "manifest.json")
        selection = _read_json(run_dir / "best_model" / "selection.json")
        model_path = run_dir / "best_model" / "model.zip"
        if not model_path.is_file():
            raise FileNotFoundError(f"Best model is missing for {run_id}")
        source_checkpoint = Path(selection.get("source_checkpoint", ""))
        if not source_checkpoint.is_file():
            raise FileNotFoundError(f"Selected source checkpoint is missing for {run_id}")
        config = manifest.get("configuration", {})
        if manifest.get("status") != "complete" or config.get("action_space") != "Continuous":
            raise ValueError(f"{run_id} is not a completed PPO Continuous run")
        if int(config.get("experiment_seed", -1)) != experiment_seed:
            raise ValueError(f"{run_id} has an unexpected experiment seed")
        if int(config.get("total_timesteps", -1)) != 5_000_000:
            raise ValueError(f"{run_id} does not target 5,000,000 transitions")
        summary_300 = selection.get("summary", {})
        summary_500 = _read_json(runs_root / validation_run_id / "validation" / "all-100" / "summary.json")
        _validate_summary(summary_300, 300)
        _validate_summary(summary_500, 500)
        if summary_500.get("model_sha256") != _file_sha256(model_path):
            raise ValueError(f"500 s validation model does not match {run_id} best model")
        terminal_300 = summary_300.get("terminal_distribution", {})
        terminal_500 = summary_500.get("terminal_distribution", {})
        validation_500 = {
            "mean_finalScore": summary_500["final_score"]["mean"],
            "median_finalScore": summary_500["final_score"]["median"],
            "std_finalScore": summary_500["final_score"]["std"],
            "mean_survivalTime": summary_500["survival_time"]["mean"],
            "median_survivalTime": summary_500["survival_time"]["median"],
            "MaxDuration_count": int(terminal_500.get("MaxDuration", 0)),
            "LivesExhausted_count": int(terminal_500.get("LivesExhausted", 0)),
        }
        for public_name, source_name in REPORTED_METRICS.items():
            validation_500[public_name] = summary_500[source_name]
        rows.append({
            "run_id": run_id,
            "experiment_seed": experiment_seed,
            "best_checkpoint_timestep": int(selection["checkpoint_timestep"]),
            "best_checkpoint": str(source_checkpoint),
            "validation_300": {
                "mean_finalScore": summary_300["final_score"]["mean"],
                "median_finalScore": summary_300["final_score"]["median"],
                "mean_survivalTime": summary_300["survival_time"]["mean"],
                "MaxDuration_count": int(terminal_300.get("MaxDuration", 0)),
            },
            "validation_500": validation_500,
        })
    best = max(rows, key=lambda item: item["validation_500"]["mean_finalScore"])
    return {
        "schema": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "experiment": "PPO Continuous 3-run",
        "selection_criterion": "maximum mean finalScore in 500 s validation on 100 VALIDATION seeds",
        "wall_seconds": float(wall_seconds),
        "runs": rows,
        "best_ppo_continuous_run": best["run_id"],
        "best_mean_finalScore_500": best["validation_500"]["mean_finalScore"],
        "test_status": "UNUSED FOR TRAINING/TUNING/EVALUATION",
    }


def write_csv(path: Path, summary: dict[str, Any]) -> None:
    fields = [
        "run_id", "experiment_seed", "best_checkpoint_timestep",
        "validation_300_mean_finalScore", "validation_300_median_finalScore",
        "validation_300_mean_survivalTime", "validation_300_MaxDuration_count",
        "validation_500_mean_finalScore", "validation_500_median_finalScore",
        "validation_500_std_finalScore", "validation_500_mean_survivalTime",
        "validation_500_median_survivalTime", "validation_500_MaxDuration_count",
        "validation_500_LivesExhausted_count",
    ]
    for name in COUNT_METRIC_NAMES:
        fields.extend((f"validation_500_{name}_mean", f"validation_500_{name}_total"))
    fields.extend(("validation_500_maxLevel_mean", "validation_500_maxLevel_max"))
    flat_rows = []
    for row in summary["runs"]:
        flat = {key: row[key] for key in ("run_id", "experiment_seed", "best_checkpoint_timestep")}
        for duration in ("validation_300", "validation_500"):
            for key, value in row[duration].items():
                if not isinstance(value, dict):
                    flat[f"{duration}_{key}"] = value
        for name in COUNT_METRIC_NAMES:
            metric = row["validation_500"][name]
            flat[f"validation_500_{name}_mean"] = metric["mean"]
            flat[f"validation_500_{name}_total"] = round(float(metric["mean"]) * 100)
        max_level = row["validation_500"]["maxLevel"]
        flat["validation_500_maxLevel_mean"] = max_level["mean"]
        flat["validation_500_maxLevel_max"] = max_level["max"]
        flat_rows.append(flat)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(flat_rows)
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the final PPO Continuous experiment summary")
    parser.add_argument("--wall-seconds", type=float, required=True)
    parser.add_argument("--output-json", type=Path, default=RUNS_ROOT / "ppo-continuous-experiment-summary.json")
    parser.add_argument("--output-csv", type=Path, default=RUNS_ROOT / "ppo-continuous-experiment-summary.csv")
    args = parser.parse_args()
    summary = build_experiment_summary(RUNS_ROOT, args.wall_seconds)
    write_json(args.output_json, summary)
    write_csv(args.output_csv, summary)
    print(json.dumps({
        "best_ppo_continuous_run": summary["best_ppo_continuous_run"],
        "best_mean_finalScore_500": summary["best_mean_finalScore_500"],
        "json": str(args.output_json.resolve()),
        "csv": str(args.output_csv.resolve()),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
