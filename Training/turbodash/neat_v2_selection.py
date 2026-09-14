from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .manifest import write_json
from .paths import RUNS_ROOT
from .seeds import file_sha256

PPO_DISCRETE_RUN_IDS = (
    "ppo-discrete-5m-run1",
    "ppo-discrete-5m-run2",
    "ppo-discrete-5m-run3",
)
BUDGET_NAMES = (
    "best_interaction_matched",
    "best_wallclock_matched",
    "best_200_generations",
)


def resolve_wallclock_match_seconds(override: float | None = None) -> dict[str, Any]:
    values = []
    manifests = []
    for run_id in PPO_DISCRETE_RUN_IDS:
        path = RUNS_ROOT / run_id / "manifest.json"
        if not path.is_file():
            values = []
            break
        manifest = json.loads(path.read_text(encoding="utf-8"))
        seconds = manifest.get("result", {}).get("wall_seconds")
        if seconds is None or float(seconds) <= 0:
            values = []
            break
        values.append(float(seconds))
        manifests.append(str(path.resolve()))
    if values:
        return {
            "seconds": sum(values) / len(values),
            "basis": "total_pipeline_wall_clock",
            "source": "mean PPO-D 5M manifest result.wall_seconds",
            "source_run_ids": list(PPO_DISCRETE_RUN_IDS),
            "source_values_seconds": values,
            "source_manifests": manifests,
        }
    if override is None or override <= 0:
        raise FileNotFoundError(
            "Complete PPO-D manifests are unavailable; provide --compute-match-seconds"
        )
    return {
        "seconds": float(override),
        "basis": "total_pipeline_wall_clock",
        "source": "ComputeMatchSeconds override",
        "source_run_ids": [],
        "source_values_seconds": [float(override)],
        "source_manifests": [],
    }


def _best(records: list[dict[str, Any]], predicate, fallback: str) -> tuple[dict[str, Any], str | None]:
    eligible = [record for record in records if predicate(record)]
    note = None
    if not eligible:
        eligible = [min(records, key=lambda record: record[fallback])]
        note = "No validated genome completed within the budget; selected the earliest completed validation."
    return max(eligible, key=lambda record: float(record["validation_mean_final_score"])), note


def select_budget_records(records: list[dict[str, Any]], *, interaction_transitions: int,
                          wallclock_seconds: float) -> dict[str, dict[str, Any]]:
    if not records:
        raise ValueError("At least one completed validation record is required")
    first_completed_boundary = min(
        (
            int(record["cumulative_training_transitions"])
            for record in records
            if int(record["cumulative_training_transitions"]) >= interaction_transitions
        ),
        default=interaction_transitions,
    )
    interaction, interaction_note = _best(
        records,
        lambda record: int(record["cumulative_training_transitions"]) <= first_completed_boundary,
        "cumulative_training_transitions",
    )
    wallclock, wallclock_note = _best(
        records,
        lambda record: float(record["elapsed_total_wall_seconds"]) <= wallclock_seconds,
        "elapsed_total_wall_seconds",
    )
    extended = max(records, key=lambda record: float(record["validation_mean_final_score"]))
    return {
        "best_interaction_matched": {
            **interaction,
            "budget_type": "INTERACTION",
            "budget_limit": interaction_transitions,
            "effective_completed_generation_cutoff": first_completed_boundary,
            "budget_basis": "cumulative TRAIN transitions",
            "fallback_note": interaction_note,
        },
        "best_wallclock_matched": {
            **wallclock,
            "budget_type": "WALLCLOCK",
            "budget_limit": wallclock_seconds,
            "budget_basis": "total pipeline wall-clock seconds",
            "fallback_note": wallclock_note,
        },
        "best_200_generations": {
            **extended,
            "budget_type": "EXTENDED-200G",
            "budget_limit": 200,
            "budget_basis": "completed generations",
            "fallback_note": None,
        },
    }


def materialize_budget_models(run_dir: Path, selections: dict[str, dict[str, Any]]) -> dict[str, Any]:
    selected_root = run_dir / "selected_models"
    selected_root.mkdir(parents=True, exist_ok=True)
    result = {}
    for name in BUDGET_NAMES:
        selection = dict(selections[name])
        source_genome = Path(selection["genome_path"]).resolve()
        source_config = Path(selection["config_path"]).resolve()
        if file_sha256(source_genome) != selection["genome_sha256"]:
            raise ValueError(f"Archived genome hash mismatch for {name}")
        if file_sha256(source_config) != selection["config_sha256"]:
            raise ValueError(f"Archived config hash mismatch for {name}")
        destination = selected_root / name
        destination.mkdir(parents=True, exist_ok=True)
        genome_path = destination / "genome.pkl"
        config_path = destination / "config.ini"
        shutil.copy2(source_genome, genome_path)
        shutil.copy2(source_config, config_path)
        selection.update({
            "selected_model_name": name,
            "source_genome_path": str(source_genome),
            "source_config_path": str(source_config),
            "genome_path": str(genome_path.resolve()),
            "config_path": str(config_path.resolve()),
        })
        if file_sha256(genome_path) != selection["genome_sha256"]:
            raise RuntimeError(f"Materialized genome hash mismatch for {name}")
        write_json(destination / "selection.json", selection)
        result[name] = selection
    write_json(selected_root / "selections.json", {
        "schema": 1,
        "selections": result,
        "deduplication_key": "genome_sha256 + config_sha256",
        "test_status": "UNUSED FOR TRAINING/TUNING/EVALUATION",
    })
    return result
