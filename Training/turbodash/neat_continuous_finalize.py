from __future__ import annotations

import argparse
from pathlib import Path

from .neat_continuous_policy import NeatContinuousPolicy
from .neat_v2_finalize import finalize_experiment
from .paths import DEFAULT_WORKER
from .protocol import ActionSpace

RUN_SPECS = (
    ("neat-continuous-v1-200g-run1", 20260925),
    ("neat-continuous-v1-200g-run2", 20260926),
    ("neat-continuous-v1-200g-run3", 20260927),
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Finalize the NEAT Continuous v1 experiment")
    parser.add_argument("--worker-exe", type=Path, default=DEFAULT_WORKER)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--time-scale", type=float, default=20)
    parser.add_argument("--skip-existing", action="store_true")
    args = parser.parse_args()
    finalize_experiment(
        worker_exe=args.worker_exe, workers=args.workers, time_scale=args.time_scale,
        skip_existing=args.skip_existing, run_specs=RUN_SPECS, action_space=ActionSpace.CONTINUOUS,
        policy_type=NeatContinuousPolicy,
        validation_root_name="neat-continuous-v1-extended-validation-500",
        summary_stem="neat-continuous-v1-experiment-summary",
        expected_algorithm="NEAT Continuous v1", expected_output_count=1,
        experiment_name="NEAT Continuous v1 — 3 × 200 generations",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
