from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import neat

from .manifest import git_snapshot, write_json
from .neat_checkpoint import read_pickle, restore_population_exact, save_pipeline_checkpoint, write_pickle
from .neat_evaluation import GenerationEvaluation, GenerationEvaluator
from .neat_manifest import create_neat_manifest, require_neat_version
from .neat_policy import NeatPolicy
from .neat_topology import genome_topology
from .neat_v2_selection import (
    materialize_budget_models,
    resolve_wallclock_match_seconds,
    select_budget_records,
)
from .paths import DEFAULT_WORKER, RUNS_ROOT, SEED_ROOT, TRAINING_ROOT
from .protocol import ActionSpace, OBSERVATION_SIZE
from .seeds import TrainingSeedScheduler, file_sha256, load_seed_split
from .validation import run_validation
from .worker import close_workers, start_workers

DEFAULT_CONFIG = TRAINING_ROOT / "configs" / "neat_discrete_v2.json"
GENERATION_FIELDS = (
    "generation", "seed_a", "seed_b", "generation_transitions", "cumulative_transitions",
    "elapsed_total_wall_seconds", "elapsed_training_wall_seconds", "species_before",
    "species_count", "genome_count", "fitness_min", "fitness_mean", "fitness_max",
    "best_training_fitness_so_far", "champion_id", "champion_species_id",
    "champion_enabled_connections", "champion_disabled_connections", "champion_hidden_nodes",
    "validation_performed", "validation_mean_final_score", "checkpoint_state", "milestone",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the generation-bounded NEAT Discrete v2 pipeline")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--worker-exe", type=Path, default=DEFAULT_WORKER)
    parser.add_argument("--run-id")
    parser.add_argument("--experiment-seed", type=int)
    parser.add_argument("--target-generations", type=int)
    parser.add_argument("--workers", type=int)
    parser.add_argument("--time-scale", type=float)
    parser.add_argument("--training-max-duration", type=float)
    parser.add_argument("--compute-match-seconds", type=float)
    parser.add_argument("--resume-state", type=Path)
    parser.add_argument("--purpose", choices=("training", "smoke"), default="training")
    parser.add_argument("--allow-dirty", action="store_true")
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def apply_overrides(config: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    result = dict(config)
    for key, value in (
        ("experiment_seed", args.experiment_seed),
        ("target_generations", args.target_generations),
        ("workers", args.workers),
        ("time_scale", args.time_scale),
        ("training_max_duration", args.training_max_duration),
    ):
        if value is not None:
            result[key] = value
    result["purpose"] = args.purpose
    return result


def validate_pipeline_config(config: dict[str, Any], purpose: str) -> None:
    exact = {
        "algorithm": "NEAT",
        "pipeline_version": 2,
        "library": "neat-python",
        "library_version": "2.0.0",
        "action_space": "Discrete",
        "observation_size": OBSERVATION_SIZE,
        "outputs": ["LEFT", "NONE", "RIGHT"],
        "episodes_per_genome": 2,
        "population_size": 64,
        "workers": 6,
        "time_scale": 20,
        "validation_interval": 500_000,
        "validation_workers": 6,
        "validation_max_duration": 300,
        "validation_after_first_generation": True,
        "milestone_generations": [50, 100, 150, 200],
        "checkpoint_each_generation": True,
    }
    for key, expected in exact.items():
        if config.get(key) != expected:
            raise ValueError(f"NEAT v2 requires {key}={expected!r}")
    fitness = config.get("fitness", {})
    if fitness.get("score_divisor") != 100 or fitness.get("life_loss_penalty") != 0.5:
        raise ValueError("NEAT v2 fitness formula differs from Research Protocol v1")
    if int(config.get("interaction_match_transitions", 0)) != 5_000_000:
        raise ValueError("Interaction-matched budget must be 5,000,000 TRAIN transitions")
    if purpose == "training":
        if int(config.get("target_generations", 0)) != 200:
            raise ValueError("Full NEAT v2 run must end at generation 200")
        if not math.isclose(float(config.get("training_max_duration", 0)), 300, abs_tol=1e-9):
            raise ValueError("Full NEAT v2 run requires MaxDuration=300")
    else:
        if int(config.get("target_generations", 0)) not in (1, 2):
            raise ValueError("NEAT v2 smoke must use 1 or 2 target generations")
        if float(config.get("training_max_duration", 0)) <= 0 or float(config["training_max_duration"]) > 60:
            raise ValueError("NEAT v2 smoke MaxDuration must be in (0, 60]")


def validate_neat_config(config: neat.Config) -> None:
    genome = config.genome_config
    expected = {
        "num_inputs": 236,
        "num_outputs": 3,
        "feed_forward": True,
        "initial_connection": "partial_direct",
        "connection_fraction": 0.10,
        "activation_default": "tanh",
        "aggregation_default": "sum",
        "node_add_prob": 0.05,
        "node_delete_prob": 0.02,
        "conn_add_prob": 0.20,
        "conn_delete_prob": 0.10,
        "weight_mutate_power": 0.5,
        "weight_mutate_rate": 0.5,
        "weight_replace_rate": 0.05,
    }
    for key, value in expected.items():
        if getattr(genome, key) != value:
            raise ValueError(f"Frozen NEAT v2 config requires {key}={value!r}")
    if config.pop_size != 64:
        raise ValueError("Frozen NEAT v2 config requires population 64")
    if config.species_set_config.compatibility_threshold != 2.5:
        raise ValueError("Frozen NEAT v2 config requires compatibility_threshold=2.5")
    if config.reproduction_config.elitism != 2 or config.reproduction_config.survival_threshold != 0.20:
        raise ValueError("Frozen NEAT v2 reproduction parameters differ")


def elapsed_total(base_seconds: float, invocation_started: float) -> float:
    return base_seconds + (time.perf_counter() - invocation_started)


def append_generation(path: Path, row: dict[str, Any]) -> None:
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=GENERATION_FIELDS, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def archive_validation(run_dir: Path, evaluation: GenerationEvaluation, neat_config: neat.Config,
                       summary: dict[str, Any], topology: dict[str, Any], transitions: int,
                       total_seconds: float, training_seconds: float) -> dict[str, Any]:
    directory = run_dir / "validation_archive" / f"generation-{evaluation.generation:06d}"
    directory.mkdir(parents=True, exist_ok=True)
    genome_path = directory / "genome.pkl"
    config_path = directory / "config.ini"
    summary_path = directory / "summary.json"
    write_pickle(genome_path, evaluation.champion)
    neat_config.save(str(config_path))
    write_json(summary_path, summary)
    record = {
        "schema": 1,
        "generation": evaluation.generation,
        "genome_id": evaluation.champion_id,
        "species_id": topology["species_id"],
        "training_fitness": evaluation.champion_fitness,
        "cumulative_training_transitions": transitions,
        "elapsed_total_wall_seconds": total_seconds,
        "elapsed_training_wall_seconds": training_seconds,
        "validation_mean_final_score": float(summary["final_score"]["mean"]),
        "genome_path": str(genome_path.resolve()),
        "genome_sha256": file_sha256(genome_path),
        "config_path": str(config_path.resolve()),
        "config_sha256": file_sha256(config_path),
        "summary_path": str(summary_path.resolve()),
        "summary_sha256": file_sha256(summary_path),
        "topology": topology,
        "test_status": "UNUSED FOR TRAINING/TUNING/EVALUATION",
    }
    write_json(directory / "record.json", record)
    return record


def update_best_model(run_dir: Path, record: dict[str, Any]) -> None:
    best_dir = run_dir / "best_model"
    best_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(record["genome_path"], best_dir / "genome.pkl")
    shutil.copy2(record["config_path"], best_dir / "config.ini")
    write_json(best_dir / "selection.json", record)


def verify_validation_records(records: list[dict[str, Any]]) -> None:
    for record in records:
        for path_key, hash_key in (
            ("genome_path", "genome_sha256"),
            ("config_path", "config_sha256"),
            ("summary_path", "summary_sha256"),
        ):
            path = Path(record[path_key]).resolve()
            if file_sha256(path) != record[hash_key]:
                raise ValueError(f"Validation archive hash mismatch: {path}")


def load_resume(args: argparse.Namespace, train_seeds: list[int]):
    state_path = args.resume_state.resolve()
    state = read_json(state_path)
    extra = state.get("extra_state", {})
    if state.get("schema") != 1 or extra.get("pipeline_version") != 2:
        raise ValueError("Checkpoint is not a NEAT Discrete v2 state")
    native = Path(state["native_checkpoint"]).resolve()
    if file_sha256(native) != state["native_checkpoint_sha256"]:
        raise ValueError("Native checkpoint hash mismatch")
    effective_neat = Path(state["effective_neat_config"]).resolve()
    if file_sha256(effective_neat) != state["effective_neat_config_sha256"]:
        raise ValueError("Effective NEAT v2 config hash mismatch")
    config = apply_overrides(dict(state["effective_config"]), args)
    run_dir = state_path.parent.parent
    if state["run_id"] != run_dir.name or (args.run_id and args.run_id != run_dir.name):
        raise ValueError("Resume run identity mismatch")
    scheduler = TrainingSeedScheduler(train_seeds, int(config["experiment_seed"]))
    scheduler.load_state_dict(state["seed_scheduler"])
    population = restore_population_exact(native)
    if population.generation != int(state["population_generation"]):
        raise RuntimeError("Restored generation mismatch")
    best_genome = None
    if state.get("best_validated_genome"):
        best_path = Path(state["best_validated_genome"]).resolve()
        if file_sha256(best_path) != state["best_validated_genome_sha256"]:
            raise ValueError("Best validated genome snapshot hash mismatch")
        best_genome = read_pickle(best_path)
    records = list(extra.get("validation_records", []))
    verify_validation_records(records)
    return state_path, state, extra, config, run_dir, effective_neat, scheduler, population, best_genome, records


def main() -> int:
    args = parse_args()
    require_neat_version()
    worker_exe = args.worker_exe.resolve()
    if not worker_exe.is_file():
        raise FileNotFoundError(f"Research Worker build is missing: {worker_exe}")
    train_seeds = load_seed_split(SEED_ROOT / "train.json", "train")
    validation_seeds = load_seed_split(SEED_ROOT / "validation.json", "validation")
    invocation_started = time.perf_counter()
    workers = []
    run_dir = None
    manifest = None
    try:
        if args.resume_state:
            (latest_state, state, extra, config, run_dir, effective_neat, scheduler, population,
             best_genome, validation_records) = load_resume(args, train_seeds)
            validate_pipeline_config(config, args.purpose)
            validate_neat_config(population.config)
            git = git_snapshot()
            if git["dirty"] and not args.allow_dirty:
                raise RuntimeError("Working tree is dirty; explicitly pass --allow-dirty")
            manifest = read_json(run_dir / "manifest.json")
            manifest.setdefault("resume_events", []).append({
                "utc": datetime.now(timezone.utc).isoformat(),
                "state": str(latest_state),
                "git": git,
            })
            manifest["status"] = "running"
            manifest["configuration"] = config
            transitions = int(state["cumulative_training_transitions"])
            next_validation = int(state["next_validation_transition"])
            validations_completed = int(state["validations_completed"])
            best_validation = state.get("best_validation")
            base_total_seconds = float(extra["elapsed_total_wall_seconds"])
            training_seconds = float(extra["elapsed_training_wall_seconds"])
            best_training_fitness = float(extra["best_training_fitness"])
            wallclock_match = extra["wallclock_match"]
        else:
            config = apply_overrides(read_json(args.config.resolve()), args)
            validate_pipeline_config(config, args.purpose)
            configured_path = Path(config["neat_config"])
            source_neat = configured_path if configured_path.is_absolute() else TRAINING_ROOT / configured_path
            neat_config = neat.Config(
                neat.DefaultGenome, neat.DefaultReproduction, neat.DefaultSpeciesSet,
                neat.DefaultStagnation, str(source_neat.resolve()),
            )
            neat_config.seed = int(config["experiment_seed"])
            validate_neat_config(neat_config)
            git = git_snapshot()
            if git["dirty"] and not args.allow_dirty:
                raise RuntimeError("Working tree is dirty; explicitly pass --allow-dirty")
            run_id = args.run_id or datetime.now(timezone.utc).strftime("neat-discrete-v2-%Y%m%d-%H%M%S")
            run_dir = RUNS_ROOT / run_id
            if run_dir.exists():
                raise FileExistsError(f"Run directory already exists: {run_dir}")
            run_dir.mkdir(parents=True)
            effective_neat = run_dir / "neat_config.ini"
            neat_config.save(str(effective_neat))
            config["neat_config"] = str(effective_neat.resolve())
            wallclock_match = resolve_wallclock_match_seconds(args.compute_match_seconds)
            manifest = create_neat_manifest(
                config, allow_dirty=args.allow_dirty, run_id=run_id, purpose=args.purpose,
                worker_executable=worker_exe,
            )
            manifest.update({
                "algorithm": "NEAT Discrete v2",
                "pipeline_version": 2,
                "wallclock_match": wallclock_match,
            })
            scheduler = TrainingSeedScheduler(train_seeds, int(config["experiment_seed"]))
            population = neat.Population(neat_config, seed=int(config["experiment_seed"]))
            transitions = 0
            next_validation = int(config["validation_interval"])
            validations_completed = 0
            validation_records = []
            best_validation = None
            best_genome = None
            best_training_fitness = float("-inf")
            base_total_seconds = 0.0
            training_seconds = 0.0
            latest_state = None
        for child in (
            "checkpoints", "milestones", "best_model", "selected_models",
            "validation", "validation_archive", "training_sessions",
        ):
            (run_dir / child).mkdir(parents=True, exist_ok=True)
        write_json(run_dir / "config.json", config)
        write_json(run_dir / "manifest.json", manifest)
        target_generations = int(config["target_generations"])
        while population.generation < target_generations:
            if not workers:
                session = datetime.now(timezone.utc).strftime("session-%Y%m%d-%H%M%S-%f")
                workers = start_workers(
                    6, worker_exe, run_dir / "training_sessions" / session,
                    time_scale=20, max_duration=float(config["training_max_duration"]),
                    nographics=True, action_space=ActionSpace.DISCRETE,
                )
            generation = int(population.generation) + 1
            species_before = len(population.species.species)
            evaluated_species = {
                int(genome_id): int(species_id)
                for species_id, species in population.species.species.items()
                for genome_id in species.members
            }
            seed_pair = (scheduler.next_seed(), scheduler.next_seed())
            evaluator = GenerationEvaluator(workers, run_dir / "training_episodes.csv")
            captured: list[GenerationEvaluation] = []
            training_started = time.perf_counter()
            population.run(
                lambda genomes, neat_config: captured.append(
                    evaluator.evaluate(genomes, neat_config, seed_pair, generation)
                ),
                1,
            )
            training_seconds += time.perf_counter() - training_started
            evaluation = captured[0]
            transitions += evaluation.transitions
            best_training_fitness = max(best_training_fitness, evaluation.champion_fitness)
            champion_topology = genome_topology(
                evaluation.champion, population.config,
                species_id=evaluated_species.get(evaluation.champion_id),
            )
            validation_summary = None
            validation_due = args.purpose == "training" and (
                validations_completed == 0 or transitions >= next_validation
            )
            if validation_due:
                closing = workers
                workers = []
                close_workers(closing)
                output = run_dir / "validation" / f"generation-{generation:06d}"
                validation_summary = run_validation(
                    NeatPolicy(evaluation.champion, population.config), worker_exe, validation_seeds,
                    output, workers_count=6, time_scale=20, action_space=ActionSpace.DISCRETE,
                    max_duration=300, nographics=True,
                )
                validation_summary.update({
                    "algorithm": "NEAT",
                    "pipeline_version": 2,
                    "generation": generation,
                    "genome_id": evaluation.champion_id,
                    "training_fitness": evaluation.champion_fitness,
                    "cumulative_training_transitions": transitions,
                })
                write_json(output / "summary.json", validation_summary)
                validations_completed += 1
                while next_validation <= transitions:
                    next_validation += int(config["validation_interval"])
                record = archive_validation(
                    run_dir, evaluation, population.config, validation_summary, champion_topology,
                    transitions, elapsed_total(base_total_seconds, invocation_started), training_seconds,
                )
                validation_records.append(record)
                write_json(run_dir / "validation_history.json", {
                    "schema": 1,
                    "records": validation_records,
                    "test_status": "UNUSED FOR TRAINING/TUNING/EVALUATION",
                })
                if best_validation is None or record["validation_mean_final_score"] > best_validation["validation_mean_final_score"]:
                    best_validation = record
                    best_genome = evaluation.champion
                    update_best_model(run_dir, record)
            fitnesses = [
                sum(float(row["fitness"]) for row in evaluation.rows if int(row["genome_id"]) == genome_id) / 2.0
                for genome_id in sorted({int(row["genome_id"]) for row in evaluation.rows})
            ]
            total_seconds = elapsed_total(base_total_seconds, invocation_started)
            metadata = {
                "schema": 1,
                "generation": generation,
                "cumulative_training_transitions": transitions,
                "elapsed_total_wall_seconds": total_seconds,
                "elapsed_training_wall_seconds": training_seconds,
                "species_count": len(population.species.species),
                "genome_count": len(population.population),
                "generation_best_training_fitness": evaluation.champion_fitness,
                "best_training_fitness_so_far": best_training_fitness,
                "current_champion_genome_id": evaluation.champion_id,
                "current_champion_topology": champion_topology,
                "milestone": generation in config["milestone_generations"],
                "test_status": "UNUSED FOR TRAINING/TUNING/EVALUATION",
            }
            extra_state = {
                "pipeline_version": 2,
                "elapsed_total_wall_seconds": total_seconds,
                "elapsed_training_wall_seconds": training_seconds,
                "best_training_fitness": best_training_fitness,
                "validation_records": validation_records,
                "wallclock_match": wallclock_match,
            }
            latest_state = save_pipeline_checkpoint(
                population, run_dir / "checkpoints", scheduler,
                run_id=run_dir.name, transitions=transitions,
                next_validation_transition=next_validation,
                validations_completed=validations_completed,
                effective_config=config, effective_config_path=effective_neat,
                best_validation=best_validation, best_genome=best_genome,
                checkpoint_metadata=metadata, extra_state=extra_state,
            )
            saved_state = read_json(latest_state)
            restored = restore_population_exact(Path(saved_state["native_checkpoint"]))
            if restored.generation != population.generation or set(restored.population) != set(population.population):
                raise RuntimeError("Immediate NEAT v2 checkpoint load verification failed")
            total_seconds = elapsed_total(base_total_seconds, invocation_started)
            metadata["elapsed_total_wall_seconds"] = total_seconds
            extra_state["elapsed_total_wall_seconds"] = total_seconds
            saved_state["checkpoint_metadata"] = metadata
            saved_state["extra_state"] = extra_state
            write_json(latest_state, saved_state)
            write_json(
                Path(saved_state["native_checkpoint"] + ".metadata.json"),
                metadata,
            )
            if metadata["milestone"]:
                write_json(run_dir / "milestones" / f"generation-{generation:03d}.json", {
                    **metadata,
                    "checkpoint_state": str(latest_state.resolve()),
                    "checkpoint_state_sha256": file_sha256(latest_state),
                })
            row = {
                "generation": generation,
                "seed_a": seed_pair[0],
                "seed_b": seed_pair[1],
                "generation_transitions": evaluation.transitions,
                "cumulative_transitions": transitions,
                "elapsed_total_wall_seconds": total_seconds,
                "elapsed_training_wall_seconds": training_seconds,
                "species_before": species_before,
                "species_count": len(population.species.species),
                "genome_count": len(population.population),
                "fitness_min": min(fitnesses),
                "fitness_mean": statistics.fmean(fitnesses),
                "fitness_max": max(fitnesses),
                "best_training_fitness_so_far": best_training_fitness,
                "champion_id": evaluation.champion_id,
                "champion_species_id": champion_topology["species_id"],
                "champion_enabled_connections": champion_topology["enabled_connection_count"],
                "champion_disabled_connections": champion_topology["disabled_connection_count"],
                "champion_hidden_nodes": champion_topology["hidden_node_count"],
                "validation_performed": validation_summary is not None,
                "validation_mean_final_score": (
                    validation_summary["final_score"]["mean"] if validation_summary else ""
                ),
                "checkpoint_state": str(latest_state.resolve()),
                "milestone": metadata["milestone"],
            }
            append_generation(run_dir / "generation_metrics.csv", row)
            manifest["progress"] = {
                "generation": generation,
                "cumulative_training_transitions": transitions,
                "elapsed_total_wall_seconds": total_seconds,
                "elapsed_training_wall_seconds": training_seconds,
                "species_count": len(population.species.species),
                "latest_checkpoint_state": str(latest_state.resolve()),
                "validations_completed": validations_completed,
                "best_validation": best_validation,
            }
            write_json(run_dir / "manifest.json", manifest)
            print(json.dumps({
                "generation": generation,
                "transitions": transitions,
                "species_count": len(population.species.species),
                "validation_mean_final_score": (
                    validation_summary["final_score"]["mean"] if validation_summary else None
                ),
            }))
        if workers:
            closing = workers
            workers = []
            close_workers(closing)
        selections = None
        if args.purpose == "training":
            selections = select_budget_records(
                validation_records,
                interaction_transitions=int(config["interaction_match_transitions"]),
                wallclock_seconds=float(wallclock_match["seconds"]),
            )
            selections = materialize_budget_models(run_dir, selections)
        final_total = elapsed_total(base_total_seconds, invocation_started)
        manifest.update({
            "status": "complete",
            "finished_utc": datetime.now(timezone.utc).isoformat(),
            "result": {
                "termination_reason": "generation_limit_reached",
                "generations_completed": population.generation,
                "cumulative_training_transitions": transitions,
                "elapsed_total_wall_seconds": final_total,
                "elapsed_training_wall_seconds": training_seconds,
                "validations_completed": validations_completed,
                "latest_checkpoint_state": str(latest_state.resolve()),
                "best_training_fitness": best_training_fitness,
                "best_validated_genome": best_validation,
                "budget_selections": selections,
                "checkpoint_load_verified": True,
                "test_status": "UNUSED FOR TRAINING/TUNING/EVALUATION",
            },
        })
        write_json(run_dir / "manifest.json", manifest)
        print(json.dumps(manifest["result"], indent=2))
        return 0
    except Exception as exc:
        if manifest is not None and run_dir is not None:
            manifest["status"] = "failed"
            manifest["finished_utc"] = datetime.now(timezone.utc).isoformat()
            manifest["error"] = f"{type(exc).__name__}: {exc}"
            write_json(run_dir / "manifest.json", manifest)
        raise
    finally:
        for worker in workers:
            worker.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
