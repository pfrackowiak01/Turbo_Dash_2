from __future__ import annotations

import argparse
import json
from pathlib import Path

import neat

from .manifest import write_json
from .neat_checkpoint import read_pickle
from .neat_manifest import require_neat_version
from .neat_policy import NeatPolicy
from .neat_v2_selection import BUDGET_NAMES
from .neat_v2_summary import RUN_SPECS, build_summary, write_csv
from .paths import DEFAULT_WORKER, RUNS_ROOT, SEED_ROOT
from .protocol import ActionSpace
from .seeds import file_sha256, load_seed_split
from .validation import run_validation


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def valid_existing(summary_path: Path, genome_hash: str, config_hash: str) -> bool:
    if not summary_path.is_file():
        return False
    summary = read_json(summary_path)
    return (
        int(summary.get("episodes", 0)) == 100
        and summary.get("algorithm") == "NEAT"
        and summary.get("action_space") == "Discrete"
        and float(summary.get("max_duration", 0)) == 500
        and summary.get("genome_sha256") == genome_hash
        and summary.get("config_sha256") == config_hash
        and summary.get("test_status") == "UNUSED FOR TRAINING/TUNING/EVALUATION"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Deduplicated 500 s validation and summary for NEAT v2")
    parser.add_argument("--worker-exe", type=Path, default=DEFAULT_WORKER)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--time-scale", type=float, default=20)
    parser.add_argument("--skip-existing", action="store_true")
    args = parser.parse_args()
    require_neat_version()
    if args.workers != 6 or args.time_scale != 20:
        raise ValueError("NEAT v2 final validation requires 6 workers and timeScale=20")
    seeds = load_seed_split(SEED_ROOT / "validation.json", "validation")
    validation_root = RUNS_ROOT / "neat-discrete-v2-extended-validation-500"
    validation_root.mkdir(parents=True, exist_ok=True)
    selections = {}
    completed: dict[str, Path] = {}
    for run_id, _ in RUN_SPECS:
        selected = read_json(RUNS_ROOT / run_id / "selected_models" / "selections.json")["selections"]
        for budget_name in BUDGET_NAMES:
            selection = selected[budget_name]
            genome_hash = selection["genome_sha256"]
            config_hash = selection["config_sha256"]
            deduplication_key = f"{genome_hash}:{config_hash}"
            reused = deduplication_key in completed
            if reused:
                summary_path = completed[deduplication_key]
            else:
                output = validation_root / f"{genome_hash[:16]}-{config_hash[:12]}"
                summary_path = output / "summary.json"
                if not (args.skip_existing and valid_existing(summary_path, genome_hash, config_hash)):
                    if output.exists():
                        raise FileExistsError(f"Incomplete validation output already exists: {output}")
                    genome_path = Path(selection["genome_path"]).resolve()
                    config_path = Path(selection["config_path"]).resolve()
                    if file_sha256(genome_path) != genome_hash or file_sha256(config_path) != config_hash:
                        raise ValueError("Selected NEAT v2 model hash mismatch")
                    neat_config = neat.Config(
                        neat.DefaultGenome, neat.DefaultReproduction, neat.DefaultSpeciesSet,
                        neat.DefaultStagnation, str(config_path),
                    )
                    summary = run_validation(
                        NeatPolicy(read_pickle(genome_path), neat_config), args.worker_exe.resolve(), seeds,
                        output, workers_count=6, time_scale=20, action_space=ActionSpace.DISCRETE,
                        max_duration=500, nographics=True,
                    )
                    summary.update({
                        "algorithm": "NEAT",
                        "pipeline_version": 2,
                        "genome_sha256": genome_hash,
                        "config_sha256": config_hash,
                    })
                    write_json(summary_path, summary)
                completed[deduplication_key] = summary_path
            selections[f"{run_id}:{budget_name}"] = {
                "run_id": run_id,
                "budget": budget_name,
                "deduplication_key": deduplication_key,
                "reused": reused,
                "summary_path": str(summary_path.resolve()),
            }
    validation_map = {
        "schema": 1,
        "unique_validations": len(completed),
        "requested_selections": len(selections),
        "selections": selections,
        "test_status": "UNUSED FOR TRAINING/TUNING/EVALUATION",
    }
    map_path = validation_root / "validation-map.json"
    write_json(map_path, validation_map)
    summary = build_summary(RUNS_ROOT, map_path)
    json_path = RUNS_ROOT / "neat-discrete-v2-experiment-summary.json"
    csv_path = RUNS_ROOT / "neat-discrete-v2-experiment-summary.csv"
    write_json(json_path, summary)
    write_csv(csv_path, summary)
    print(json.dumps({
        "unique_500_second_validations": len(completed),
        "requested_budget_models": len(selections),
        "summary_json": str(json_path.resolve()),
        "summary_csv": str(csv_path.resolve()),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
