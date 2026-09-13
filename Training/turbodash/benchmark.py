from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import psutil

from .paths import DEFAULT_WORKER, RUNS_ROOT, SEED_ROOT
from .seeds import TrainingSeedScheduler, load_seed_split
from .vec_env import TurboDashVecEnv
from .worker import start_workers


def benchmark_count(executable: Path, output: Path, count: int, transitions: int, time_scale: float,
                    train_seeds: list[int]) -> dict:
    workers = start_workers(count, executable, output, time_scale=time_scale, nographics=True)
    env = TurboDashVecEnv(workers, TrainingSeedScheduler(train_seeds, 20260913 + count))
    observations = env.reset()
    processes = [psutil.Process(worker.pid) for worker in workers]
    cpu_before = sum(sum(process.cpu_times()[:2]) for process in processes)
    peak_rss = sum(process.memory_info().rss for process in processes)
    completed = 0
    started = time.perf_counter()
    stable = True
    error = ""
    try:
        while completed < transitions:
            actions = np.full(count, 1, dtype=np.int64)
            observations, rewards, dones, infos = env.step(actions)
            completed += count
            if not np.isfinite(observations).all() or not np.isfinite(rewards).all():
                raise FloatingPointError("Non-finite benchmark transition")
            peak_rss = max(peak_rss, sum(process.memory_info().rss for process in processes if process.is_running()))
    except Exception as exc:
        stable = False
        error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        wall = time.perf_counter() - started
        cpu_after = sum(sum(process.cpu_times()[:2]) for process in processes if process.is_running())
        env.close()
    return {
        "workers": count,
        "requested_transitions": transitions,
        "actual_transitions": completed,
        "wall_seconds": wall,
        "transitions_per_second": completed / wall,
        "worker_cpu_percent_total": 100 * (cpu_after - cpu_before) / wall,
        "peak_worker_rss_bytes": peak_rss,
        "peak_worker_rss_mib": peak_rss / (1024 * 1024),
        "stable": stable,
        "error": error,
        "test_status": "UNUSED",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark 1/2/4/6 Unity Research Workers on TRAIN seeds")
    parser.add_argument("--worker-exe", type=Path, default=DEFAULT_WORKER)
    parser.add_argument("--transitions", type=int, default=4000, help="Minimum transitions per worker count")
    parser.add_argument("--time-scale", type=float, default=20)
    parser.add_argument("--counts", nargs="+", type=int, default=[1, 2, 4, 6])
    parser.add_argument("--run-id")
    args = parser.parse_args()
    train_seeds = load_seed_split(SEED_ROOT / "train.json", "train")
    run_id = args.run_id or datetime.now(timezone.utc).strftime("benchmark-%Y%m%d-%H%M%S")
    root = RUNS_ROOT / run_id
    if root.exists():
        raise FileExistsError(root)
    results = []
    for count in args.counts:
        result = benchmark_count(args.worker_exe.resolve(), root / f"workers-{count}", count,
                                 args.transitions, args.time_scale, train_seeds)
        results.append(result)
        print(json.dumps(result, indent=2))
    stable = [result for result in results if result["stable"]]
    practical = max(stable, key=lambda value: value["transitions_per_second"])["workers"]
    # Keep the expected four-worker default unless another count is at least 15% faster.
    four = next((result for result in stable if result["workers"] == 4), None)
    best = max(stable, key=lambda value: value["transitions_per_second"])
    recommended = practical if four is None or best["transitions_per_second"] >= four["transitions_per_second"] * 1.15 else 4
    report = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "time_scale": args.time_scale,
        "source_split": "TRAIN",
        "test_status": "UNUSED",
        "results": results,
        "recommended_workers": recommended,
    }
    root.mkdir(parents=True, exist_ok=True)
    (root / "benchmark.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"recommended_workers": recommended}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
