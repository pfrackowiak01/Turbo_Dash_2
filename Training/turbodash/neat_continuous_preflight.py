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
from .neat_continuous_policy import select_continuous_action
from .neat_evaluation import GenerationEvaluator
from .neat_manifest import require_neat_version
from .paths import DEFAULT_WORKER, RUNS_ROOT, SEED_ROOT, TRAINING_ROOT
from .protocol import ActionSpace
from .seeds import TrainingSeedScheduler, file_sha256, load_seed_split
from .worker import close_workers, start_workers

DEFAULT_PIPELINE_CONFIG = TRAINING_ROOT / "configs" / "neat_continuous_v1.json"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def valid_existing(path: Path, config_hash: str, pipeline_hash: str, generations: int,
                   max_duration: float, experiment_seed: int) -> bool:
    if not path.is_file():
        return False
    report = read_json(path)
    return (
        report.get("accepted") is True
        and report.get("source_config_sha256") == config_hash
        and report.get("pipeline_config_sha256") == pipeline_hash
        and int(report.get("generations", 0)) == generations
        and float(report.get("max_duration", 0)) == max_duration
        and int(report.get("experiment_seed", 0)) == experiment_seed
        and report.get("action_space") == "Continuous"
        and report.get("test_status") == "UNUSED FOR TRAINING/TUNING/EVALUATION"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounded NEAT Continuous speciation preflight")
    parser.add_argument("--config", type=Path, default=DEFAULT_PIPELINE_CONFIG)
    parser.add_argument("--worker-exe", type=Path, default=DEFAULT_WORKER)
    parser.add_argument("--run-id", default="neat-continuous-v1-speciation-preflight")
    parser.add_argument("--experiment-seed", type=int, default=20260925)
    parser.add_argument("--generations", type=int, default=3)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--time-scale", type=float, default=20)
    parser.add_argument("--max-duration", type=float, default=30)
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument("--skip-existing", action="store_true")
    args = parser.parse_args()
    require_neat_version()
    if args.generations < 3 or args.generations > 5:
        raise ValueError("Continuous preflight must use 3 to 5 short generations")
    if args.workers != 6 or args.time_scale != 20:
        raise ValueError("Continuous preflight requires 6 workers and timeScale=20")
    if args.max_duration <= 0 or args.max_duration > 30:
        raise ValueError("Continuous preflight MaxDuration must be in (0, 30]")
    pipeline_path = args.config.resolve()
    pipeline = read_json(pipeline_path)
    preflight = pipeline.get("speciation_preflight", {})
    if pipeline.get("action_space") != "Continuous" or pipeline.get("outputs") != ["STEERING"]:
        raise ValueError("Preflight requires the one-output NEAT Continuous config")
    if preflight.get("initial_connection") != "partial_direct" or preflight.get("connection_fraction") != 0.10:
        raise ValueError("Preflight requires partial_direct 0.10")
    if float(preflight.get("compatibility_threshold", 0)) != 2.5:
        raise ValueError("Initial Continuous preflight must evaluate compatibility_threshold=2.5")
    source = Path(pipeline["neat_config"])
    source = source if source.is_absolute() else TRAINING_ROOT / source
    source_hash = file_sha256(source)
    pipeline_hash = file_sha256(pipeline_path)
    run_dir = RUNS_ROOT / args.run_id
    report_path = run_dir / "speciation-preflight.json"
    if args.skip_existing and valid_existing(
        report_path, source_hash, pipeline_hash, args.generations, args.max_duration,
        args.experiment_seed,
    ):
        print(json.dumps({"report": str(report_path.resolve()), "reused": True}, indent=2))
        return 0
    if run_dir.exists():
        raise FileExistsError(f"Preflight run directory already exists: {run_dir}")
    git = git_snapshot()
    if git["dirty"] and not args.allow_dirty:
        raise RuntimeError("Working tree is dirty; explicitly pass --allow-dirty for the preflight")
    worker_exe = args.worker_exe.resolve()
    if not worker_exe.is_file():
        raise FileNotFoundError(f"Research Worker build is missing: {worker_exe}")
    train_seeds = load_seed_split(SEED_ROOT / "train.json", "train")
    config = neat.Config(
        neat.DefaultGenome, neat.DefaultReproduction, neat.DefaultSpeciesSet,
        neat.DefaultStagnation, str(source.resolve()),
    )
    config.seed = args.experiment_seed
    if config.pop_size != 64 or config.genome_config.num_inputs != 236 or config.genome_config.num_outputs != 1:
        raise ValueError("Preflight requires population 64 and a 236-to-1 network")
    if config.species_set_config.compatibility_threshold != 2.5:
        raise ValueError("Effective preflight threshold differs from 2.5")
    run_dir.mkdir(parents=True)
    config.save(str(run_dir / "neat_config.ini"))
    population = neat.Population(config, seed=args.experiment_seed)
    initial_connection_counts = [
        sum(connection.enabled for connection in genome.connections.values())
        for genome in population.population.values()
    ]
    scheduler = TrainingSeedScheduler(train_seeds, args.experiment_seed)
    workers = start_workers(
        args.workers, worker_exe, run_dir / "workers", time_scale=args.time_scale,
        max_duration=args.max_duration, nographics=True, action_space=ActionSpace.CONTINUOUS,
    )
    started = time.perf_counter()
    rows = []
    cumulative = 0
    initial_species = len(population.species.species)
    try:
        for generation in range(1, args.generations + 1):
            species_before = len(population.species.species)
            pair = (scheduler.next_seed(), scheduler.next_seed())
            captured = []
            evaluator = GenerationEvaluator(
                workers, run_dir / "training_episodes.csv",
                action_selector=select_continuous_action,
            )
            population.run(
                lambda genomes, neat_config: captured.append(
                    evaluator.evaluate(genomes, neat_config, pair, generation)
                ),
                1,
            )
            evaluation = captured[0]
            cumulative += evaluation.transitions
            evaluated_genome_ids = sorted({int(row["genome_id"]) for row in evaluation.rows})
            fitnesses = [
                statistics.fmean(
                    float(row["fitness"]) for row in evaluation.rows
                    if int(row["genome_id"]) == genome_id
                )
                for genome_id in evaluated_genome_ids
            ]
            rows.append({
                "generation": generation,
                "seed_a": pair[0],
                "seed_b": pair[1],
                "species_before": species_before,
                "species_after": len(population.species.species),
                "generation_transitions": evaluation.transitions,
                "cumulative_transitions": cumulative,
                "fitness_min": min(fitnesses),
                "fitness_mean": statistics.fmean(fitnesses),
                "fitness_max": max(fitnesses),
            })
    finally:
        close_workers(workers)
    species_history = [initial_species] + [row["species_after"] for row in rows]
    stable_min = int(preflight["required_stable_species_min"])
    stable_max = int(preflight["required_stable_species_max"])
    accepted = all(stable_min <= count <= stable_max for count in species_history)
    report = {
        "schema": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "action_space": "Continuous",
        "outputs": 1,
        "experiment_seed": args.experiment_seed,
        "population_size": 64,
        "generations": args.generations,
        "workers": args.workers,
        "time_scale": args.time_scale,
        "max_duration": args.max_duration,
        "compatibility_threshold": 2.5,
        "initial_connection": "partial_direct 0.10",
        "initial_connection_count": {
            "min": min(initial_connection_counts),
            "mean": statistics.fmean(initial_connection_counts),
            "max": max(initial_connection_counts),
        },
        "species_history": species_history,
        "stable_species_range": [stable_min, stable_max],
        "accepted": accepted,
        "decision": (
            "keep compatibility_threshold=2.5"
            if accepted else "pathological: evaluate only thresholds 2.0 and 3.0 before freezing"
        ),
        "threshold_alternatives_evaluated": [],
        "total_training_transitions": cumulative,
        "wall_seconds": time.perf_counter() - started,
        "generation_metrics": rows,
        "source_config": str(source.resolve()),
        "source_config_sha256": source_hash,
        "pipeline_config": str(pipeline_path),
        "pipeline_config_sha256": pipeline_hash,
        "selection_basis": "species stability only; VALIDATION was not loaded or used",
        "git": git,
        "test_status": "UNUSED FOR TRAINING/TUNING/EVALUATION",
    }
    write_json(report_path, report)
    with (run_dir / "speciation-preflight.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"report": str(report_path.resolve()), "accepted": accepted,
                      "species_history": species_history}, indent=2))
    if not accepted:
        raise RuntimeError("Threshold 2.5 did not keep a stable 2-8 species range")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
