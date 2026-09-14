from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .manifest import write_json
from .paths import RUNS_ROOT
from .seeds import file_sha256

RUN_SPECS = (
    ("neat-discrete-5m-run1", 20260919, "neat-discrete-run1-best-validation-500"),
    ("neat-discrete-5m-run2", 20260920, "neat-discrete-run2-best-validation-500"),
    ("neat-discrete-5m-run3", 20260921, "neat-discrete-run3-best-validation-500"),
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


def _read(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Required NEAT experiment artifact is missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_summary(summary: dict[str, Any], max_duration: float) -> None:
    if int(summary.get("episodes", 0)) != 100:
        raise ValueError("NEAT validation must contain exactly 100 episodes")
    if summary.get("algorithm") != "NEAT" or summary.get("action_space") != "Discrete":
        raise ValueError("Validation is not NEAT Discrete")
    if not math.isclose(float(summary.get("max_duration", -1)), max_duration, abs_tol=1e-6):
        raise ValueError(f"Validation does not use MaxDuration={max_duration:g}")
    if summary.get("test_status") != "UNUSED FOR TRAINING/TUNING/EVALUATION":
        raise ValueError("Validation does not confirm TEST UNUSED")


def build_experiment_summary(runs_root: Path, wall_seconds: float) -> dict[str, Any]:
    rows = []
    for run_id, experiment_seed, validation_id in RUN_SPECS:
        run_dir = runs_root / run_id
        manifest = _read(run_dir / "manifest.json")
        selection = _read(run_dir / "best_model" / "selection.json")
        genome_path = run_dir / "best_model" / "genome.pkl"
        config_path = run_dir / "best_model" / "config.ini"
        config = manifest.get("configuration", {})
        result = manifest.get("result", {})
        if manifest.get("status") != "complete" or manifest.get("algorithm") != "NEAT Discrete":
            raise ValueError(f"{run_id} is not a completed NEAT Discrete run")
        if config.get("action_space") != "Discrete" or int(config.get("experiment_seed", -1)) != experiment_seed:
            raise ValueError(f"{run_id} has an unexpected action space or experiment seed")
        if int(config.get("target_transitions", -1)) != 5_000_000:
            raise ValueError(f"{run_id} does not target 5,000,000 training transitions")
        if int(result.get("cumulative_training_transitions", 0)) < 5_000_000:
            raise ValueError(f"{run_id} stopped before its transition budget")
        if selection.get("genome_sha256") != file_sha256(genome_path):
            raise ValueError(f"Best genome hash mismatch for {run_id}")
        if selection.get("config_sha256") != file_sha256(config_path):
            raise ValueError(f"Best config hash mismatch for {run_id}")
        summary_300 = selection.get("summary", {})
        summary_500 = _read(runs_root / validation_id / "validation" / "all-100" / "summary.json")
        _validate_summary(summary_300, 300)
        _validate_summary(summary_500, 500)
        if summary_500.get("genome_sha256") != file_sha256(genome_path):
            raise ValueError(f"500 s validation genome does not match {run_id}")
        if summary_500.get("config_sha256") != file_sha256(config_path):
            raise ValueError(f"500 s validation config does not match {run_id}")
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
            "training_transitions": int(result["cumulative_training_transitions"]),
            "best_generation": int(selection["generation"]),
            "best_genome": str(genome_path.resolve()),
            "validation_300": {
                "mean_finalScore": summary_300["final_score"]["mean"],
                "median_finalScore": summary_300["final_score"]["median"],
                "mean_survivalTime": summary_300["survival_time"]["mean"],
                "MaxDuration_count": int(terminal_300.get("MaxDuration", 0)),
            },
            "validation_500": validation_500,
        })
    best = max(rows, key=lambda row: row["validation_500"]["mean_finalScore"])
    return {
        "schema": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "experiment": "NEAT Discrete 3-run",
        "selection_criterion": "maximum mean finalScore in 500 s validation on 100 VALIDATION seeds",
        "wall_seconds": float(wall_seconds),
        "runs": rows,
        "best_neat_discrete_run": best["run_id"],
        "best_mean_finalScore_500": best["validation_500"]["mean_finalScore"],
        "test_status": "UNUSED FOR TRAINING/TUNING/EVALUATION",
    }


def write_csv(path: Path, summary: dict[str, Any]) -> None:
    fields = [
        "run_id", "experiment_seed", "training_transitions", "best_generation",
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
        flat = {key: row[key] for key in ("run_id", "experiment_seed", "training_transitions", "best_generation")}
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
    parser = argparse.ArgumentParser(description="Build the final NEAT Discrete experiment summary")
    parser.add_argument("--wall-seconds", type=float, required=True)
    parser.add_argument("--output-json", type=Path, default=RUNS_ROOT / "neat-discrete-experiment-summary.json")
    parser.add_argument("--output-csv", type=Path, default=RUNS_ROOT / "neat-discrete-experiment-summary.csv")
    args = parser.parse_args()
    summary = build_experiment_summary(RUNS_ROOT, args.wall_seconds)
    write_json(args.output_json, summary)
    write_csv(args.output_csv, summary)
    print(json.dumps({
        "best_neat_discrete_run": summary["best_neat_discrete_run"],
        "best_mean_finalScore_500": summary["best_mean_finalScore_500"],
        "json": str(args.output_json.resolve()),
        "csv": str(args.output_csv.resolve()),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
