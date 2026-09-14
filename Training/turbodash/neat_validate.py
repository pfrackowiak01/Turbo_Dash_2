from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import neat

from .manifest import write_json
from .neat_checkpoint import read_pickle
from .neat_manifest import require_neat_version
from .neat_policy import NeatPolicy
from .paths import DEFAULT_WORKER, RUNS_ROOT, SEED_ROOT
from .protocol import ActionSpace
from .seeds import file_sha256, load_seed_split
from .validation import run_validation


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate a NEAT Discrete genome on VALIDATION seeds")
    parser.add_argument("--genome", type=Path, required=True)
    parser.add_argument("--neat-config", type=Path)
    parser.add_argument("--worker-exe", type=Path, default=DEFAULT_WORKER)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--time-scale", type=float, default=20)
    parser.add_argument("--max-duration", type=float, default=300)
    parser.add_argument("--run-id")
    args = parser.parse_args()
    version = require_neat_version()
    genome_path = args.genome.resolve()
    config_path = args.neat_config.resolve() if args.neat_config else genome_path.with_name("config.ini")
    if not genome_path.is_file() or not config_path.is_file():
        raise FileNotFoundError("NEAT genome or its config.ini is missing")
    if args.max_duration <= 0 or args.workers <= 0:
        raise ValueError("workers and MaxDuration must be positive")
    neat_config = neat.Config(
        neat.DefaultGenome, neat.DefaultReproduction, neat.DefaultSpeciesSet,
        neat.DefaultStagnation, str(config_path),
    )
    genome = read_pickle(genome_path)
    seeds = load_seed_split(SEED_ROOT / "validation.json", "validation")
    run_id = args.run_id or datetime.now(timezone.utc).strftime("neat-validation-%Y%m%d-%H%M%S")
    output = RUNS_ROOT / run_id / "validation" / "all-100"
    if output.exists():
        raise FileExistsError(f"Validation output already exists: {output}")
    summary = run_validation(
        NeatPolicy(genome, neat_config), args.worker_exe.resolve(), seeds, output,
        workers_count=args.workers, time_scale=args.time_scale,
        action_space=ActionSpace.DISCRETE, max_duration=args.max_duration,
    )
    summary.update({
        "algorithm": "NEAT",
        "neat_python_version": version,
        "genome_path": str(genome_path),
        "genome_sha256": file_sha256(genome_path),
        "config_path": str(config_path),
        "config_sha256": file_sha256(config_path),
    })
    write_json(output / "summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
