from __future__ import annotations

import gzip
import pickle
import random
from pathlib import Path
from typing import Any

import neat

from .manifest import write_json
from .seeds import TrainingSeedScheduler, file_sha256


def write_pickle(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as stream:
        pickle.dump(value, stream, protocol=pickle.HIGHEST_PROTOCOL)
    temporary.replace(path)


def read_pickle(path: Path) -> Any:
    with path.open("rb") as stream:
        return pickle.load(stream)


def restore_population_exact(path: Path) -> neat.Population:
    """Restore a native checkpoint and reinstate the RNG state stored inside it."""
    checkpoint = path.resolve()
    population = neat.Checkpointer.restore_checkpoint(str(checkpoint))
    with gzip.open(checkpoint, "rb") as stream:
        _, _, _, _, random_state = pickle.load(stream)
    random.setstate(random_state)
    return population


def save_pipeline_checkpoint(
    population: neat.Population,
    checkpoint_dir: Path,
    scheduler: TrainingSeedScheduler,
    *,
    run_id: str,
    transitions: int,
    next_validation_transition: int,
    validations_completed: int,
    effective_config: dict[str, Any],
    effective_config_path: Path,
    best_validation: dict[str, Any] | None,
    best_genome: Any | None,
) -> Path:
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    prefix = checkpoint_dir / "neat-checkpoint-"
    neat.Checkpointer(generation_interval=1, filename_prefix=str(prefix)).save_checkpoint(
        population.config, population.population, population.species, population.generation
    )
    native_path = Path(f"{prefix}{population.generation}").resolve()
    if not native_path.is_file():
        raise RuntimeError("neat-python did not create the expected native checkpoint")
    best_snapshot_path = None
    if best_genome is not None:
        best_snapshot_path = native_path.with_name(native_path.name + ".best.pkl")
        write_pickle(best_snapshot_path, best_genome)
    state_path = native_path.with_name(native_path.name + ".state.json")
    state = {
        "schema": 1,
        "run_id": run_id,
        "native_checkpoint": str(native_path),
        "native_checkpoint_sha256": file_sha256(native_path),
        "population_generation": int(population.generation),
        "cumulative_training_transitions": int(transitions),
        "next_validation_transition": int(next_validation_transition),
        "validations_completed": int(validations_completed),
        "seed_scheduler": scheduler.state_dict(),
        "effective_config": effective_config,
        "effective_neat_config": str(effective_config_path.resolve()),
        "effective_neat_config_sha256": file_sha256(effective_config_path),
        "best_validation": best_validation,
        "best_validated_genome": str(best_snapshot_path.resolve()) if best_snapshot_path else None,
        "best_validated_genome_sha256": file_sha256(best_snapshot_path) if best_snapshot_path else None,
        "test_status": "UNUSED FOR TRAINING/TUNING/EVALUATION",
    }
    write_json(state_path, state)
    write_json(checkpoint_dir / "latest.json", {
        "schema": 1,
        "state": str(state_path),
        "native_checkpoint": str(native_path),
    })
    return state_path
