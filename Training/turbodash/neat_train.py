from __future__ import annotations

import argparse
import csv
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import neat

from .manifest import git_snapshot, write_json
from .neat_checkpoint import (
    read_pickle,
    restore_population_exact,
    save_pipeline_checkpoint,
    write_pickle,
)
from .neat_evaluation import GenerationEvaluation, GenerationEvaluator
from .neat_manifest import create_neat_manifest, require_neat_version
from .neat_policy import NeatPolicy
from .paths import DEFAULT_WORKER, RUNS_ROOT, SEED_ROOT, TRAINING_ROOT
from .protocol import ActionSpace, OBSERVATION_SIZE
from .seeds import TrainingSeedScheduler, file_sha256, load_seed_split
from .validation import run_validation
from .worker import close_workers, start_workers

DEFAULT_CONFIG = TRAINING_ROOT / "configs" / "neat_discrete_v1.json"
GENERATION_FIELDS = (
    "generation", "seed_a", "seed_b", "generation_transitions", "cumulative_transitions",
    "population_size", "species_count", "min_fitness", "mean_fitness", "max_fitness",
    "champion_id", "champion_fitness", "validation_performed", "validation_mean_final_score",
    "checkpoint_state",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train neat-python feed-forward genomes against Turbo Dash")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--neat-config", type=Path)
    parser.add_argument("--worker-exe", type=Path, default=DEFAULT_WORKER)
    parser.add_argument("--run-id")
    parser.add_argument("--workers", type=int)
    parser.add_argument("--time-scale", type=float)
    parser.add_argument("--target-transitions", type=int)
    parser.add_argument("--experiment-seed", type=int)
    parser.add_argument("--training-max-duration", type=float)
    parser.add_argument("--population-size", type=int)
    parser.add_argument("--max-generations", type=int)
    parser.add_argument("--resume-state", type=Path)
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument("--purpose", choices=("training", "smoke"), default="training")
    return parser.parse_args()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _apply_overrides(config: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    result = dict(config)
    for key, value in (
        ("workers", args.workers),
        ("time_scale", args.time_scale),
        ("target_transitions", args.target_transitions),
        ("experiment_seed", args.experiment_seed),
        ("training_max_duration", args.training_max_duration),
        ("population_size", args.population_size),
    ):
        if value is not None:
            result[key] = value
    return result


def validate_config(config: dict[str, Any], purpose: str, max_generations: int | None) -> None:
    expected = {
        "algorithm": "NEAT",
        "library": "neat-python",
        "library_version": "2.0.0",
        "action_space": "Discrete",
        "observation_size": OBSERVATION_SIZE,
        "episodes_per_genome": 2,
        "outputs": ["LEFT", "NONE", "RIGHT"],
        "checkpoint_each_generation": True,
    }
    for key, value in expected.items():
        if config.get(key) != value:
            raise ValueError(f"NEAT Discrete configuration requires {key}={value!r}")
    fitness = config.get("fitness", {})
    if float(fitness.get("score_divisor", 0)) != 100 or float(fitness.get("life_loss_penalty", 0)) != 0.5:
        raise ValueError("Fitness must be finalScore / 100 - 0.5 * lifeLossCount")
    for key in ("workers", "population_size", "target_transitions", "validation_interval", "validation_workers"):
        if int(config.get(key, 0)) <= 0:
            raise ValueError(f"{key} must be positive")
    for key in ("time_scale", "training_max_duration", "validation_max_duration"):
        if float(config.get(key, 0)) <= 0:
            raise ValueError(f"{key} must be positive")
    if purpose == "training":
        if int(config["population_size"]) != 64:
            raise ValueError("Full NEAT Discrete training requires population_size=64")
        if not math.isclose(float(config["training_max_duration"]), 300, abs_tol=1e-9):
            raise ValueError("Full NEAT Discrete training requires MaxDuration=300")
        if int(config["workers"]) != 6 or int(config["validation_workers"]) != 6:
            raise ValueError("Full NEAT Discrete training and validation require 6 workers")
        if not math.isclose(float(config["time_scale"]), 20, abs_tol=1e-9):
            raise ValueError("Full NEAT Discrete training requires timeScale=20")
        if int(config["validation_interval"]) != 500_000:
            raise ValueError("NEAT Discrete validation interval must be 500,000 transitions")
        if not math.isclose(float(config["validation_max_duration"]), 300, abs_tol=1e-9):
            raise ValueError("Periodic NEAT Discrete validation requires MaxDuration=300")
        if max_generations is not None:
            raise ValueError("--max-generations is reserved for the bounded smoke test")
    else:
        if int(config["population_size"]) > 8:
            raise ValueError("Smoke population must not exceed 8")
        if int(config["target_transitions"]) > 50_000:
            raise ValueError("Smoke transition ceiling is 50,000")
        if float(config["training_max_duration"]) > 60:
            raise ValueError("Smoke MaxDuration must not exceed 60 seconds")
        if max_generations not in (1, 2):
            raise ValueError("Smoke requires --max-generations 1 or 2")


def validate_neat_config(config: neat.Config, population_size: int) -> None:
    genome = config.genome_config
    exact = {
        "num_inputs": 236,
        "num_outputs": 3,
        "feed_forward": True,
        "initial_connection": "full_direct",
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
    for name, expected in exact.items():
        if getattr(genome, name) != expected:
            raise ValueError(f"Frozen NEAT config requires {name}={expected!r}")
    if config.pop_size != population_size:
        raise ValueError("NEAT config population size differs from pipeline configuration")
    if config.reproduction_config.elitism != 2 or config.reproduction_config.survival_threshold != 0.20:
        raise ValueError("Frozen NEAT reproduction settings differ")
    if config.species_set_config.compatibility_threshold != 3.0:
        raise ValueError("Frozen NEAT compatibility threshold differs")


def _resolve_neat_config(args: argparse.Namespace, config: dict[str, Any]) -> Path:
    if args.neat_config:
        return args.neat_config.resolve()
    configured = Path(str(config["neat_config"]))
    return configured.resolve() if configured.is_absolute() else (TRAINING_ROOT / configured).resolve()


def _append_generation(path: Path, row: dict[str, Any]) -> None:
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=GENERATION_FIELDS, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def _load_resume(args: argparse.Namespace, train_seeds: list[int]):
    state_path = args.resume_state.resolve()
    state = _load_json(state_path)
    if state.get("schema") != 1:
        raise ValueError("Unsupported NEAT pipeline checkpoint schema")
    native_path = Path(state["native_checkpoint"]).resolve()
    if file_sha256(native_path) != state["native_checkpoint_sha256"]:
        raise ValueError("Native NEAT checkpoint hash differs from checkpoint metadata")
    effective_path = Path(state["effective_neat_config"]).resolve()
    if file_sha256(effective_path) != state["effective_neat_config_sha256"]:
        raise ValueError("Effective NEAT configuration hash differs from checkpoint metadata")
    config = _apply_overrides(dict(state["effective_config"]), args)
    run_dir = state_path.parent.parent
    if run_dir.name != state["run_id"] or (args.run_id and args.run_id != state["run_id"]):
        raise ValueError("Resume checkpoint run identity is inconsistent")
    scheduler = TrainingSeedScheduler(train_seeds, int(config["experiment_seed"]))
    scheduler.load_state_dict(state["seed_scheduler"])
    population = restore_population_exact(native_path)
    if population.generation != int(state["population_generation"]):
        raise RuntimeError("Restored NEAT generation differs from pipeline metadata")
    best_genome = None
    if state.get("best_validated_genome"):
        best_path = Path(state["best_validated_genome"]).resolve()
        if file_sha256(best_path) != state["best_validated_genome_sha256"]:
            raise ValueError("Best validated genome hash differs from checkpoint metadata")
        best_genome = read_pickle(best_path)
    return state, config, run_dir, effective_path, scheduler, population, best_genome


def _save_best(run_dir: Path, champion, neat_config: neat.Config, summary: dict[str, Any],
               evaluation: GenerationEvaluation, transitions: int) -> tuple[dict[str, Any], Any]:
    best_dir = run_dir / "best_model"
    genome_path = best_dir / "genome.pkl"
    config_path = best_dir / "config.ini"
    write_pickle(genome_path, champion)
    neat_config.save(str(config_path))
    selection = {
        "schema": 1,
        "criterion": "maximum mean finalScore on all 100 VALIDATION seeds at MaxDuration=300",
        "generation": evaluation.generation,
        "genome_id": evaluation.champion_id,
        "training_fitness": evaluation.champion_fitness,
        "cumulative_training_transitions": transitions,
        "genome_path": str(genome_path.resolve()),
        "genome_sha256": file_sha256(genome_path),
        "config_path": str(config_path.resolve()),
        "config_sha256": file_sha256(config_path),
        "validation_mean_final_score": float(summary["final_score"]["mean"]),
        "summary": summary,
    }
    write_json(best_dir / "selection.json", selection)
    return selection, champion


def main() -> int:
    args = parse_args()
    require_neat_version()
    worker_exe = args.worker_exe.resolve()
    if not worker_exe.is_file():
        raise FileNotFoundError(f"Research Worker build is missing: {worker_exe}")
    train_seeds = load_seed_split(SEED_ROOT / "train.json", "train")
    validation_seeds = load_seed_split(SEED_ROOT / "validation.json", "validation")
    workers = []
    manifest: dict[str, Any] | None = None
    run_dir: Path | None = None
    started = time.perf_counter()
    invocation_initial_transitions = 0
    try:
        if args.resume_state:
            state, config, run_dir, effective_neat_path, scheduler, population, best_genome = _load_resume(
                args, train_seeds
            )
            validate_config(config, args.purpose, args.max_generations)
            git = git_snapshot()
            if git["dirty"] and not args.allow_dirty:
                raise RuntimeError("Working tree is dirty. Commit/stash changes or explicitly pass --allow-dirty.")
            manifest = _load_json(run_dir / "manifest.json")
            manifest.setdefault("resume_events", []).append({
                "utc": datetime.now(timezone.utc).isoformat(),
                "state": str(args.resume_state.resolve()),
                "git": git,
            })
            manifest["status"] = "running"
            config["neat_config"] = str(effective_neat_path)
            manifest["configuration"] = config
            transitions = int(state["cumulative_training_transitions"])
            next_validation = int(state["next_validation_transition"])
            validations_completed = int(state["validations_completed"])
            best_validation = state.get("best_validation")
            invocation_initial_transitions = transitions
        else:
            config = _apply_overrides(_load_json(args.config.resolve()), args)
            validate_config(config, args.purpose, args.max_generations)
            source_neat_path = _resolve_neat_config(args, config)
            if not source_neat_path.is_file():
                raise FileNotFoundError(f"NEAT configuration is missing: {source_neat_path}")
            neat_config = neat.Config(
                neat.DefaultGenome, neat.DefaultReproduction, neat.DefaultSpeciesSet,
                neat.DefaultStagnation, str(source_neat_path),
            )
            neat_config.pop_size = int(config["population_size"])
            neat_config.seed = int(config["experiment_seed"])
            validate_neat_config(neat_config, int(config["population_size"]))
            preflight_git = git_snapshot()
            if preflight_git["dirty"] and not args.allow_dirty:
                raise RuntimeError("Working tree is dirty. Commit/stash changes or explicitly pass --allow-dirty.")
            run_id = args.run_id or datetime.now(timezone.utc).strftime("neat-discrete-%Y%m%d-%H%M%S")
            run_dir = RUNS_ROOT / run_id
            if run_dir.exists():
                raise FileExistsError(f"Run directory already exists: {run_dir}")
            run_dir.mkdir(parents=True)
            effective_neat_path = run_dir / "neat_config.ini"
            neat_config.save(str(effective_neat_path))
            config["neat_config"] = str(effective_neat_path.resolve())
            config["purpose"] = args.purpose
            manifest = create_neat_manifest(
                config, allow_dirty=args.allow_dirty, run_id=run_id, purpose=args.purpose,
                worker_executable=worker_exe,
            )
            scheduler = TrainingSeedScheduler(train_seeds, int(config["experiment_seed"]))
            population = neat.Population(neat_config, seed=int(config["experiment_seed"]))
            transitions = 0
            next_validation = int(config["validation_interval"])
            validations_completed = 0
            best_validation = None
            best_genome = None
        validate_neat_config(population.config, int(config["population_size"]))
        for child in ("checkpoints", "best_model", "validation", "training_sessions"):
            (run_dir / child).mkdir(parents=True, exist_ok=True)
        write_json(run_dir / "config.json", config)
        write_json(run_dir / "manifest.json", manifest)

        completed_this_invocation = 0
        latest_state: Path | None = None
        while transitions < int(config["target_transitions"]):
            if args.max_generations is not None and completed_this_invocation >= args.max_generations:
                break
            if not workers:
                session_id = datetime.now(timezone.utc).strftime("session-%Y%m%d-%H%M%S-%f")
                workers = start_workers(
                    int(config["workers"]), worker_exe, run_dir / "training_sessions" / session_id,
                    time_scale=float(config["time_scale"]),
                    max_duration=float(config["training_max_duration"]),
                    nographics=True,
                    action_space=ActionSpace.DISCRETE,
                )
            generation = int(population.generation) + 1
            seed_pair = (scheduler.next_seed(), scheduler.next_seed())
            evaluator = GenerationEvaluator(workers, run_dir / "training_episodes.csv")
            captured: list[GenerationEvaluation] = []

            def evaluate_generation(genomes, neat_config):
                captured.append(evaluator.evaluate(genomes, neat_config, seed_pair, generation))

            population.run(evaluate_generation, 1)
            if len(captured) != 1:
                raise RuntimeError("NEAT did not produce exactly one completed generation evaluation")
            evaluation = captured[0]
            transitions += evaluation.transitions
            completed_this_invocation += 1
            validation_summary = None
            validation_due = args.purpose == "training" and (
                validations_completed == 0 or transitions >= next_validation
            )
            if validation_due:
                closing = workers
                workers = []
                close_workers(closing)
                validation_dir = run_dir / "validation" / f"generation-{generation:06d}"
                validation_summary = run_validation(
                    NeatPolicy(evaluation.champion, population.config), worker_exe, validation_seeds,
                    validation_dir, workers_count=int(config["validation_workers"]),
                    time_scale=float(config["time_scale"]), action_space=ActionSpace.DISCRETE,
                    max_duration=float(config["validation_max_duration"]), nographics=True,
                )
                validation_summary.update({
                    "algorithm": "NEAT",
                    "generation": generation,
                    "genome_id": evaluation.champion_id,
                    "training_fitness": evaluation.champion_fitness,
                    "cumulative_training_transitions": transitions,
                })
                write_json(validation_dir / "summary.json", validation_summary)
                validations_completed += 1
                while next_validation <= transitions:
                    next_validation += int(config["validation_interval"])
                candidate = float(validation_summary["final_score"]["mean"])
                if best_validation is None or candidate > float(best_validation["validation_mean_final_score"]):
                    best_validation, best_genome = _save_best(
                        run_dir, evaluation.champion, population.config, validation_summary,
                        evaluation, transitions,
                    )
            evaluated_fitnesses = [
                sum(float(row["fitness"]) for row in evaluation.rows if int(row["genome_id"]) == genome_id) / 2.0
                for genome_id in sorted({int(row["genome_id"]) for row in evaluation.rows})
            ]
            generation_row = {
                "generation": generation,
                "seed_a": seed_pair[0],
                "seed_b": seed_pair[1],
                "generation_transitions": evaluation.transitions,
                "cumulative_transitions": transitions,
                "population_size": len(evaluated_fitnesses),
                "species_count": len(population.species.species),
                "min_fitness": min(evaluated_fitnesses),
                "mean_fitness": sum(evaluated_fitnesses) / len(evaluated_fitnesses),
                "max_fitness": max(evaluated_fitnesses),
                "champion_id": evaluation.champion_id,
                "champion_fitness": evaluation.champion_fitness,
                "validation_performed": validation_summary is not None,
                "validation_mean_final_score": (
                    validation_summary["final_score"]["mean"] if validation_summary else ""
                ),
                "checkpoint_state": "pending",
            }
            latest_state = save_pipeline_checkpoint(
                population, run_dir / "checkpoints", scheduler,
                run_id=run_dir.name,
                transitions=transitions,
                next_validation_transition=next_validation,
                validations_completed=validations_completed,
                effective_config=config,
                effective_config_path=effective_neat_path,
                best_validation=best_validation,
                best_genome=best_genome,
            )
            restored_probe = restore_population_exact(Path(_load_json(latest_state)["native_checkpoint"]))
            if restored_probe.generation != population.generation or set(restored_probe.population) != set(population.population):
                raise RuntimeError("Saved native NEAT checkpoint failed immediate load verification")
            generation_row["checkpoint_state"] = str(latest_state.resolve())
            _append_generation(run_dir / "generation_metrics.csv", generation_row)
            print(json.dumps({
                "generation": generation,
                "seed_pair": seed_pair,
                "generation_transitions": evaluation.transitions,
                "cumulative_training_transitions": transitions,
                "champion_fitness": evaluation.champion_fitness,
                "validation_mean_final_score": (
                    validation_summary["final_score"]["mean"] if validation_summary else None
                ),
                "checkpoint_state": str(latest_state.resolve()),
            }))
            manifest["status"] = "running"
            manifest["progress"] = {
                "generation": population.generation,
                "cumulative_training_transitions": transitions,
                "target_transitions": int(config["target_transitions"]),
                "latest_checkpoint_state": str(latest_state.resolve()),
                "validations_completed": validations_completed,
                "best_validation_mean_final_score": (
                    best_validation["validation_mean_final_score"] if best_validation else None
                ),
            }
            write_json(run_dir / "manifest.json", manifest)

        if workers:
            closing = workers
            workers = []
            close_workers(closing)
        if latest_state is None:
            raise ValueError("Target transitions do not exceed the resumed checkpoint state")
        elapsed = time.perf_counter() - started
        reached_budget = transitions >= int(config["target_transitions"])
        manifest.update({
            "status": "complete",
            "finished_utc": datetime.now(timezone.utc).isoformat(),
            "result": {
                "termination_reason": "transition_budget_reached" if reached_budget else "smoke_generation_limit",
                "initial_transitions": invocation_initial_transitions,
                "cumulative_training_transitions": transitions,
                "target_transitions": int(config["target_transitions"]),
                "budget_overshoot_transitions": max(0, transitions - int(config["target_transitions"])),
                "generation": population.generation,
                "generations_this_invocation": completed_this_invocation,
                "wall_seconds_this_invocation": elapsed,
                "training_transitions_per_second": (transitions - invocation_initial_transitions) / elapsed,
                "latest_checkpoint_state": str(latest_state.resolve()),
                "checkpoint_load_verified": True,
                "best_validated_genome": best_validation,
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
