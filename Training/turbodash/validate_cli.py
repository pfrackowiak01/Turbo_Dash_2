from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from gymnasium import spaces
from stable_baselines3 import PPO

from .paths import DEFAULT_WORKER, RUNS_ROOT, SEED_ROOT
from .protocol import ActionSpace
from .seeds import load_seed_split
from .validation import run_validation
from .manifest import write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate a PPO checkpoint on all VALIDATION seeds")
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--worker-exe", type=Path, default=DEFAULT_WORKER)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--time-scale", type=float, default=20)
    parser.add_argument("--max-duration", type=float, default=300)
    parser.add_argument("--action-space", choices=("Discrete", "Continuous"), default="Discrete")
    parser.add_argument("--run-id")
    args = parser.parse_args()
    seeds = load_seed_split(SEED_ROOT / "validation.json", "validation")
    run_id = args.run_id or datetime.now(timezone.utc).strftime("validation-%Y%m%d-%H%M%S")
    output = RUNS_ROOT / run_id / "validation" / "all-100"
    model_path = args.model.resolve()
    model = PPO.load(model_path, device="cpu")
    action_space = ActionSpace.from_name(args.action_space)
    if isinstance(model.action_space, spaces.Discrete) and model.action_space.n == 3:
        model_action_space = ActionSpace.DISCRETE
    elif isinstance(model.action_space, spaces.Box) and model.action_space.shape == (1,):
        model_action_space = ActionSpace.CONTINUOUS
    else:
        raise ValueError(f"Unsupported model action space: {model.action_space}")
    if model_action_space != action_space:
        raise ValueError(f"Model uses {model_action_space.name.title()}, requested {action_space.name.title()}")
    summary = run_validation(model, args.worker_exe.resolve(), seeds, output,
                             workers_count=args.workers, time_scale=args.time_scale,
                             action_space=action_space, max_duration=args.max_duration)
    summary["model_path"] = str(model_path)
    summary["model_sha256"] = hashlib.sha256(model_path.read_bytes()).hexdigest()
    write_json(output / "summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
