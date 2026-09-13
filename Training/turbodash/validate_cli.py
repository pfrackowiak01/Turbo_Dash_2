from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from stable_baselines3 import PPO

from .paths import DEFAULT_WORKER, RUNS_ROOT, SEED_ROOT
from .seeds import load_seed_split
from .validation import run_validation


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate a PPO checkpoint on all VALIDATION seeds")
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--worker-exe", type=Path, default=DEFAULT_WORKER)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--time-scale", type=float, default=20)
    parser.add_argument("--run-id")
    args = parser.parse_args()
    seeds = load_seed_split(SEED_ROOT / "validation.json", "validation")
    run_id = args.run_id or datetime.now(timezone.utc).strftime("validation-%Y%m%d-%H%M%S")
    output = RUNS_ROOT / run_id / "validation" / "all-100"
    model = PPO.load(args.model.resolve(), device="cpu")
    summary = run_validation(model, args.worker_exe.resolve(), seeds, output,
                             workers_count=args.workers, time_scale=args.time_scale)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
