from __future__ import annotations

import argparse
import csv
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .manifest import write_json
from .paths import RUNS_ROOT
from .seeds import file_sha256

RUN_SPECS = (
    ("neat-discrete-v2-200g-run1", 20260922),
    ("neat-discrete-v2-200g-run2", 20260923),
    ("neat-discrete-v2-200g-run3", 20260924),
)
BUDGET_NAMES = (
    "best_interaction_matched",
    "best_wallclock_matched",
    "best_200_generations",
)
METRIC_MAP = {
    "finalScore": "final_score",
    "survivalTime": "survival_time",
    "lifeLossCount": "life_loss_count",
    "collisions": "collisions",
    "obstaclesAvoided": "obstacles_avoided",
    "maxLevel": "max_level",
    "Heart": "hearts_collected",
    "Shield": "shields_collected",
    "Boost": "boosts_collected",
    "Gold": "gold_collected",
    "Diamond": "diamonds_collected",
    "turboActivations": "turbo_activations",
}


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Required NEAT v2 artifact is missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def validation_metrics(summary: dict[str, Any], expected_duration: float) -> dict[str, Any]:
    if int(summary.get("episodes", 0)) != 100 or summary.get("action_space") != "Discrete":
        raise ValueError("NEAT v2 summary requires 100-seed Discrete validation")
    if float(summary.get("max_duration", 0)) != expected_duration:
        raise ValueError(f"NEAT v2 validation must use MaxDuration={expected_duration:g}")
    if summary.get("test_status") != "UNUSED FOR TRAINING/TUNING/EVALUATION":
        raise ValueError("NEAT v2 validation does not confirm TEST UNUSED")
    result = {public: summary[source] for public, source in METRIC_MAP.items()}
    result["terminal_distribution"] = summary["terminal_distribution"]
    return result


def build_summary(runs_root: Path, validation_map_path: Path) -> dict[str, Any]:
    validation_map = read_json(validation_map_path)
    mapping = validation_map["selections"]
    runs = []
    for run_id, experiment_seed in RUN_SPECS:
        run_dir = runs_root / run_id
        manifest = read_json(run_dir / "manifest.json")
        if manifest.get("status") != "complete" or manifest.get("algorithm") != "NEAT Discrete v2":
            raise ValueError(f"{run_id} is not a completed NEAT Discrete v2 run")
        if int(manifest["configuration"]["experiment_seed"]) != experiment_seed:
            raise ValueError(f"{run_id} experiment seed mismatch")
        result = manifest["result"]
        if int(result["generations_completed"]) != 200:
            raise ValueError(f"{run_id} did not complete 200 generations")
        with (run_dir / "generation_metrics.csv").open(encoding="utf-8") as stream:
            generation_rows = list(csv.DictReader(stream))
        if len(generation_rows) != 200:
            raise ValueError(f"{run_id} generation_metrics does not contain 200 rows")
        species_history = [int(row["species_count"]) for row in generation_rows]
        latest_state = read_json(Path(result["latest_checkpoint_state"]))
        checkpoint_metadata = latest_state["checkpoint_metadata"]
        milestones = {}
        for generation in (50, 100, 150, 200):
            milestone = read_json(run_dir / "milestones" / f"generation-{generation:03d}.json")
            milestones[str(generation)] = {
                "generation": generation,
                "cumulative_training_transitions": milestone["cumulative_training_transitions"],
                "elapsed_total_wall_seconds": milestone["elapsed_total_wall_seconds"],
                "elapsed_training_wall_seconds": milestone["elapsed_training_wall_seconds"],
                "species_count": milestone["species_count"],
                "genome_count": milestone["genome_count"],
                "best_training_fitness": milestone["generation_best_training_fitness"],
                "current_champion_genome_id": milestone["current_champion_genome_id"],
                "checkpoint_state": milestone["checkpoint_state"],
            }
        budgets = {}
        for budget_name in BUDGET_NAMES:
            selection = result["budget_selections"][budget_name]
            map_key = f"{run_id}:{budget_name}"
            mapped = mapping[map_key]
            summary_300 = read_json(Path(selection["summary_path"]))
            summary_500 = read_json(Path(mapped["summary_path"]))
            if file_sha256(Path(selection["summary_path"])) != selection["summary_sha256"]:
                raise ValueError(f"300 s validation summary hash mismatch for {map_key}")
            if summary_500["genome_sha256"] != selection["genome_sha256"]:
                raise ValueError(f"500 s validation genome mismatch for {map_key}")
            if summary_500["config_sha256"] != selection["config_sha256"]:
                raise ValueError(f"500 s validation config mismatch for {map_key}")
            budgets[budget_name] = {
                "selected_generation": selection["generation"],
                "selected_genome_id": selection["genome_id"],
                "selected_species_id": selection["species_id"],
                "train_transitions_at_selection": selection["cumulative_training_transitions"],
                "elapsed_total_wall_seconds_at_selection": selection["elapsed_total_wall_seconds"],
                "elapsed_training_wall_seconds_at_selection": selection["elapsed_training_wall_seconds"],
                "budget_limit": selection["budget_limit"],
                "budget_basis": selection["budget_basis"],
                "topology": selection["topology"],
                "validation_300": validation_metrics(summary_300, 300),
                "validation_500": validation_metrics(summary_500, 500),
                "validation_500_reused": bool(mapped["reused"]),
                "validation_500_deduplication_key": mapped["deduplication_key"],
                "genome_sha256": selection["genome_sha256"],
                "config_sha256": selection["config_sha256"],
            }
        runs.append({
            "run_id": run_id,
            "experiment_seed": experiment_seed,
            "generations_completed": result["generations_completed"],
            "total_train_transitions": result["cumulative_training_transitions"],
            "total_wall_clock_seconds": result["elapsed_total_wall_seconds"],
            "training_only_wall_clock_seconds": result["elapsed_training_wall_seconds"],
            "species_count_history": species_history,
            "species_count_min": min(species_history),
            "species_count_mean": statistics.fmean(species_history),
            "species_count_max": max(species_history),
            "final_species_count": species_history[-1],
            "final_champion_topology": checkpoint_metadata["current_champion_topology"],
            "best_validated_genome_id": result["best_validated_genome"]["genome_id"],
            "milestone_checkpoints": milestones,
            "budgets": budgets,
        })
    winners = {
        budget: max(
            runs,
            key=lambda run: run["budgets"][budget]["validation_500"]["finalScore"]["mean"],
        )["run_id"]
        for budget in BUDGET_NAMES
    }
    return {
        "schema": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "experiment": "NEAT Discrete v2 — 3 × 200 generations",
        "wallclock_match": read_json(runs_root / RUN_SPECS[0][0] / "manifest.json")["wallclock_match"],
        "runs": runs,
        "best_run_by_budget_mean_finalScore_500": winners,
        "extended_validation": validation_map,
        "test_status": "UNUSED FOR TRAINING/TUNING/EVALUATION",
    }


def write_csv(path: Path, summary: dict[str, Any]) -> None:
    fields = [
        "run_id", "experiment_seed", "budget", "generations_completed", "total_train_transitions",
        "total_wall_clock_seconds", "training_only_wall_clock_seconds", "species_count_min",
        "species_count_mean", "species_count_max", "final_species_count", "best_validated_genome_id",
        "selected_generation",
        "selected_genome_id", "selected_species_id", "train_transitions_at_selection",
        "elapsed_total_wall_seconds_at_selection", "elapsed_training_wall_seconds_at_selection",
        "enabled_connection_count", "disabled_connection_count", "total_node_count", "hidden_node_count",
        "input_count", "output_count", "feed_forward_layer_count", "validation_500_reused",
    ]
    for generation in (50, 100, 150, 200):
        fields.extend((
            f"checkpoint_{generation}_transitions",
            f"checkpoint_{generation}_total_wall_seconds",
            f"checkpoint_{generation}_training_wall_seconds",
            f"checkpoint_{generation}_species_count",
            f"checkpoint_{generation}_best_training_fitness",
        ))
    for duration in ("300", "500"):
        for public_name in METRIC_MAP:
            fields.extend((f"validation_{duration}_{public_name}_mean", f"validation_{duration}_{public_name}_median",
                           f"validation_{duration}_{public_name}_std"))
        fields.extend((f"validation_{duration}_MaxDuration_count", f"validation_{duration}_LivesExhausted_count"))
    rows = []
    for run in summary["runs"]:
        for budget_name, budget in run["budgets"].items():
            topology = budget["topology"]
            row = {key: run[key] for key in fields if key in run}
            row.update({
                "budget": budget_name,
                "selected_generation": budget["selected_generation"],
                "selected_genome_id": budget["selected_genome_id"],
                "selected_species_id": budget["selected_species_id"],
                "train_transitions_at_selection": budget["train_transitions_at_selection"],
                "elapsed_total_wall_seconds_at_selection": budget["elapsed_total_wall_seconds_at_selection"],
                "elapsed_training_wall_seconds_at_selection": budget["elapsed_training_wall_seconds_at_selection"],
                "validation_500_reused": budget["validation_500_reused"],
            })
            for key in (
                "enabled_connection_count", "disabled_connection_count", "total_node_count",
                "hidden_node_count", "input_count", "output_count", "feed_forward_layer_count",
            ):
                row[key] = topology[key]
            for generation in (50, 100, 150, 200):
                milestone = run["milestone_checkpoints"][str(generation)]
                row[f"checkpoint_{generation}_transitions"] = milestone["cumulative_training_transitions"]
                row[f"checkpoint_{generation}_total_wall_seconds"] = milestone["elapsed_total_wall_seconds"]
                row[f"checkpoint_{generation}_training_wall_seconds"] = milestone["elapsed_training_wall_seconds"]
                row[f"checkpoint_{generation}_species_count"] = milestone["species_count"]
                row[f"checkpoint_{generation}_best_training_fitness"] = milestone["best_training_fitness"]
            for duration in ("300", "500"):
                validation = budget[f"validation_{duration}"]
                for public_name in METRIC_MAP:
                    metric = validation[public_name]
                    for statistic in ("mean", "median", "std"):
                        row[f"validation_{duration}_{public_name}_{statistic}"] = metric[statistic]
                terminal = validation["terminal_distribution"]
                row[f"validation_{duration}_MaxDuration_count"] = terminal.get("MaxDuration", 0)
                row[f"validation_{duration}_LivesExhausted_count"] = terminal.get("LivesExhausted", 0)
            rows.append(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate NEAT Discrete v2 experiment summary")
    parser.add_argument("--validation-map", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, default=RUNS_ROOT / "neat-discrete-v2-experiment-summary.json")
    parser.add_argument("--output-csv", type=Path, default=RUNS_ROOT / "neat-discrete-v2-experiment-summary.csv")
    args = parser.parse_args()
    summary = build_summary(RUNS_ROOT, args.validation_map.resolve())
    write_json(args.output_json, summary)
    write_csv(args.output_csv, summary)
    print(json.dumps({"json": str(args.output_json.resolve()), "csv": str(args.output_csv.resolve())}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
