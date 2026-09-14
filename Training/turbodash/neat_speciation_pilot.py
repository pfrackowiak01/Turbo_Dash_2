from __future__ import annotations

import argparse
import csv
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import neat

from .manifest import git_snapshot, write_json
from .neat_evaluation import GenerationEvaluator
from .neat_manifest import require_neat_version
from .neat_topology import genome_topology
from .paths import DEFAULT_WORKER, RUNS_ROOT, SEED_ROOT, TRAINING_ROOT
from .protocol import ActionSpace
from .seeds import TrainingSeedScheduler, file_sha256, load_seed_split
from .worker import close_workers, start_workers

SOURCE_CONFIG = TRAINING_ROOT / "configs" / "neat_discrete_v1.ini"
PREFLIGHT_THRESHOLDS = (0.25, 0.5, 1.0, 1.5, 2.0, 2.5)
PREFLIGHT_INITIALIZATIONS = (
    ("full_direct", None),
    ("partial_direct", 0.10),
    ("partial_direct", 0.25),
    ("fs_neat_nohidden", None),
)
RUNTIME_VARIANTS = (
    ("full-t1_0", "full_direct", None, 1.0),
    ("full-t1_5", "full_direct", None, 1.5),
    ("partial10-t2_5", "partial_direct", 0.10, 2.5),
    ("partial25-t2_5", "partial_direct", 0.25, 2.5),
    ("fs-neat-t2_5", "fs_neat_nohidden", None, 2.5),
)


def build_config(initial_connection: str, fraction: float | None, threshold: float,
                 experiment_seed: int) -> neat.Config:
    config = neat.Config(
        neat.DefaultGenome, neat.DefaultReproduction, neat.DefaultSpeciesSet,
        neat.DefaultStagnation, str(SOURCE_CONFIG),
    )
    config.pop_size = 64
    config.seed = experiment_seed
    config.species_set_config.compatibility_threshold = float(threshold)
    config.genome_config.initial_connection = initial_connection
    config.genome_config.connection_fraction = fraction
    return config


def structural_preflight(experiment_seed: int) -> list[dict[str, Any]]:
    rows = []
    for initial_connection, fraction in PREFLIGHT_INITIALIZATIONS:
        for threshold in PREFLIGHT_THRESHOLDS:
            config = build_config(initial_connection, fraction, threshold, experiment_seed)
            population = neat.Population(config, seed=experiment_seed)
            connections = [len(genome.connections) for genome in population.population.values()]
            rows.append({
                "initial_connection": initial_connection,
                "connection_fraction": fraction,
                "compatibility_threshold": threshold,
                "initial_species_count": len(population.species.species),
                "initial_connection_count_min": min(connections),
                "initial_connection_count_mean": statistics.fmean(connections),
                "initial_connection_count_max": max(connections),
            })
    return rows


def population_topology(population: dict[int, Any], config: neat.Config) -> dict[str, Any]:
    enabled_counts = []
    hidden_counts = []
    signatures = set()
    for genome in population.values():
        enabled = tuple(sorted(key for key, connection in genome.connections.items() if connection.enabled))
        enabled_counts.append(len(enabled))
        hidden_counts.append(sum(key not in config.genome_config.output_keys for key in genome.nodes))
        signatures.add(enabled)
    return {
        "enabled_connections_min": min(enabled_counts),
        "enabled_connections_mean": statistics.fmean(enabled_counts),
        "enabled_connections_max": max(enabled_counts),
        "hidden_nodes_min": min(hidden_counts),
        "hidden_nodes_mean": statistics.fmean(hidden_counts),
        "hidden_nodes_max": max(hidden_counts),
        "unique_enabled_topologies": len(signatures),
    }


def write_csv(path: Path, variants: list[dict[str, Any]]) -> None:
    fields = [
        "variant", "initial_connection", "connection_fraction", "compatibility_threshold",
        "generation", "species_before", "species_after", "generation_transitions",
        "cumulative_transitions", "fitness_min", "fitness_mean", "fitness_max",
        "enabled_connections_min", "enabled_connections_mean", "enabled_connections_max",
        "hidden_nodes_min", "hidden_nodes_mean", "hidden_nodes_max", "unique_enabled_topologies",
    ]
    rows = []
    for variant in variants:
        for generation in variant["generations"]:
            rows.append({
                "variant": variant["variant"],
                "initial_connection": variant["initial_connection"],
                "connection_fraction": variant["connection_fraction"],
                "compatibility_threshold": variant["compatibility_threshold"],
                **{key: generation.get(key) for key in fields[4:]},
            })
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounded structural speciation pilot for NEAT Discrete v2")
    parser.add_argument("--worker-exe", type=Path, default=DEFAULT_WORKER)
    parser.add_argument("--run-id", default="neat-discrete-v2-speciation-pilot")
    parser.add_argument("--experiment-seed", type=int, default=20260922)
    parser.add_argument("--generations", type=int, default=3)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--time-scale", type=float, default=20)
    parser.add_argument("--max-duration", type=float, default=30)
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args()
    require_neat_version()
    if args.generations < 2 or args.generations > 5:
        raise ValueError("Pilot must use between 2 and 5 short generations")
    if args.workers != 6 or args.time_scale != 20:
        raise ValueError("Pilot requires 6 workers and timeScale=20")
    if args.max_duration <= 0 or args.max_duration > 60:
        raise ValueError("Pilot MaxDuration must be in (0, 60]")
    git = git_snapshot()
    if git["dirty"] and not args.allow_dirty:
        raise RuntimeError("Working tree is dirty; explicitly pass --allow-dirty for the pilot")
    worker_exe = args.worker_exe.resolve()
    if not worker_exe.is_file():
        raise FileNotFoundError(f"Research Worker build is missing: {worker_exe}")
    train_seeds = load_seed_split(SEED_ROOT / "train.json", "train")
    run_dir = RUNS_ROOT / args.run_id
    if run_dir.exists():
        raise FileExistsError(f"Pilot run directory already exists: {run_dir}")
    run_dir.mkdir(parents=True)
    started = time.perf_counter()
    variants = []
    try:
        for variant_name, initial_connection, fraction, threshold in RUNTIME_VARIANTS:
            variant_dir = run_dir / variant_name
            variant_dir.mkdir(parents=True)
            config = build_config(initial_connection, fraction, threshold, args.experiment_seed)
            config.save(str(variant_dir / "neat_config.ini"))
            population = neat.Population(config, seed=args.experiment_seed)
            scheduler = TrainingSeedScheduler(train_seeds, args.experiment_seed)
            workers = start_workers(
                args.workers, worker_exe, variant_dir, time_scale=args.time_scale,
                max_duration=args.max_duration, nographics=True, action_space=ActionSpace.DISCRETE,
            )
            generation_rows = []
            cumulative = 0
            try:
                for generation in range(1, args.generations + 1):
                    species_before = len(population.species.species)
                    evaluated_species = {
                        int(genome_id): int(species_id)
                        for species_id, species in population.species.species.items()
                        for genome_id in species.members
                    }
                    seed_pair = (scheduler.next_seed(), scheduler.next_seed())
                    evaluator = GenerationEvaluator(workers, variant_dir / "training_episodes.csv")
                    captured = []
                    population.run(
                        lambda genomes, neat_config: captured.append(
                            evaluator.evaluate(genomes, neat_config, seed_pair, generation)
                        ),
                        1,
                    )
                    evaluation = captured[0]
                    cumulative += evaluation.transitions
                    fitnesses = [
                        sum(float(row["fitness"]) for row in evaluation.rows
                            if int(row["genome_id"]) == genome_id) / 2.0
                        for genome_id in sorted({int(row["genome_id"]) for row in evaluation.rows})
                    ]
                    species_id = evaluated_species.get(evaluation.champion_id)
                    generation_rows.append({
                        "generation": generation,
                        "seed_pair": list(seed_pair),
                        "species_before": species_before,
                        "species_after": len(population.species.species),
                        "generation_transitions": evaluation.transitions,
                        "cumulative_transitions": cumulative,
                        "fitness_min": min(fitnesses),
                        "fitness_mean": statistics.fmean(fitnesses),
                        "fitness_max": max(fitnesses),
                        **population_topology(population.population, config),
                        "champion_topology": genome_topology(
                            evaluation.champion, config, species_id=species_id
                        ),
                    })
            finally:
                close_workers(workers)
            species_history = [generation_rows[0]["species_before"]] + [
                row["species_after"] for row in generation_rows
            ]
            variants.append({
                "variant": variant_name,
                "initial_connection": initial_connection,
                "connection_fraction": fraction,
                "compatibility_threshold": threshold,
                "initial_species_count": species_history[0],
                "species_history": species_history,
                "species_min": min(species_history),
                "species_mean": statistics.fmean(species_history),
                "species_max": max(species_history),
                "total_transitions": cumulative,
                "generations": generation_rows,
            })
            print(json.dumps({
                "variant": variant_name,
                "species_history": species_history,
                "transitions": cumulative,
            }))
        report = {
            "schema": 1,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "experiment_seed": args.experiment_seed,
            "population_size": 64,
            "generations_per_runtime_variant": args.generations,
            "workers": args.workers,
            "time_scale": args.time_scale,
            "max_duration": args.max_duration,
            "source_config": str(SOURCE_CONFIG.resolve()),
            "source_config_sha256": file_sha256(SOURCE_CONFIG),
            "preflight": structural_preflight(args.experiment_seed),
            "runtime_variants": variants,
            "wall_seconds": time.perf_counter() - started,
            "selection_note": "Select structurally; validation finalScore was not used.",
            "test_status": "UNUSED FOR TRAINING/TUNING/EVALUATION",
        }
        write_json(run_dir / "speciation-pilot.json", report)
        write_csv(run_dir / "speciation-pilot.csv", variants)
        print(json.dumps({"report": str((run_dir / "speciation-pilot.json").resolve())}, indent=2))
        return 0
    except Exception:
        raise


if __name__ == "__main__":
    raise SystemExit(main())
