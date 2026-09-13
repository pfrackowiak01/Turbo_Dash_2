from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .paths import DEFAULT_WORKER, RUNS_ROOT, SEED_ROOT
from .protocol import OBSERVATION_SIZE, ProtocolError
from .seeds import TrainingSeedScheduler, load_seed_split
from .vec_env import TurboDashVecEnv
from .worker import UnityWorker, WorkerPaths, close_workers, start_workers


def run_episode(worker: UnityWorker, seed: int, max_decisions: int = 10000):
    observation = worker.reset(seed)
    rewards = []
    results = []
    for _ in range(max_decisions):
        worker.send_step(1)
        result = worker.receive_step()
        rewards.append(result.reward)
        results.append(result)
        if result.terminated or result.truncated:
            return observation, rewards, results
    raise TimeoutError("Episode did not finish within the decision limit")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the standalone Unity/Python bridge verification")
    parser.add_argument("--worker-exe", type=Path, default=DEFAULT_WORKER)
    parser.add_argument("--run-id")
    args = parser.parse_args()
    executable = args.worker_exe.resolve()
    train_seeds = load_seed_split(SEED_ROOT / "train.json", "train")
    run_id = args.run_id or datetime.now(timezone.utc).strftime("bridge-%Y%m%d-%H%M%S")
    root = RUNS_ROOT / run_id
    root.mkdir(parents=True)
    checks: list[dict] = []

    def check(condition: bool, name: str, detail=""):
        checks.append({"name": name, "passed": bool(condition), "detail": str(detail)})
        if not condition:
            raise AssertionError(f"{name}: {detail}")

    mismatch_worker = UnityWorker(
        0, executable,
        WorkerPaths(root / "mismatch" / "worker_logs" / "worker-0.log",
                    root / "mismatch" / "unity_episode_csv" / "worker-0.csv"),
        time_scale=20, max_duration=2, expected_handshake_worker_id=999,
    )
    try:
        mismatch_worker.start()
        mismatch_rejected = False
    except ProtocolError:
        mismatch_rejected = True
    finally:
        mismatch_worker.terminate()
    check(mismatch_rejected, "real worker handshake protocol mismatch rejection")

    short = UnityWorker(0, executable, WorkerPaths(root / "short" / "worker_logs" / "worker-0.log",
                                                    root / "short" / "unity_episode_csv" / "worker-0.csv"),
                        time_scale=20, max_duration=0.07)
    short.start()
    try:
        check(short.handshake is not None, "handshake success")
        initial = short.reset(train_seeds[0])
        check(initial.shape == (OBSERVATION_SIZE,) and initial.dtype == np.float32,
              "observation exactly 236 float32", f"{initial.shape} {initial.dtype}")
        check(np.isfinite(initial).all(), "initial observation finite")
        short.send_step(0)
        first = short.receive_step()
        check(first.info["physics_ticks"] == 5, "STEP executes exactly 5 physics ticks", first.info["physics_ticks"])
        check(not first.terminated and not first.truncated, "first short episode STEP is nonterminal")
        short_results = [first]
        for action in [2] + [1] * 30:
            short.send_step(action)
            terminal = short.receive_step()
            short_results.append(terminal)
            if terminal.terminated or terminal.truncated:
                break
        check(terminal.truncated and not terminal.terminated and terminal.info["terminal_reason"] == "MaxDuration",
              "MaxDuration maps to truncated")
        check(math.isclose(sum(result.reward for result in short_results), terminal.info["episode_reward"], abs_tol=1e-5),
              "terminal partial reward is included exactly once")
        check(np.isfinite(terminal.observation).all(), "terminal observation finite")
        check(short.paths.csv.is_file(), "Unity episode CSV created")
    finally:
        short.close()
    check(short.last_exit_code == 0, "graceful close exits with code zero", short.last_exit_code)

    deterministic = UnityWorker(0, executable,
        WorkerPaths(root / "deterministic" / "worker_logs" / "worker-0.log",
                    root / "deterministic" / "unity_episode_csv" / "worker-0.csv"),
        time_scale=20, max_duration=300)
    deterministic.start()
    try:
        _, rewards_a, results_a = run_episode(deterministic, train_seeds[1])
        _, rewards_b, results_b = run_episode(deterministic, train_seeds[1])
        final_a, final_b = results_a[-1], results_b[-1]
        check(final_a.terminated and not final_a.truncated and final_a.info["terminal_reason"] == "LivesExhausted",
              "LivesExhausted maps to terminated")
        check(math.isclose(sum(rewards_a), final_a.info["episode_reward"], abs_tol=1e-4),
              "reward equals Unity PilotRewardCalculator episode total")
        check(math.isclose(sum(rewards_b), final_b.info["episode_reward"], abs_tol=1e-4),
              "second terminal interval reward is retained")
        check(abs(final_a.info["final_score"] - final_b.info["final_score"]) <= 1.0 and
              abs(final_a.info["survival_time"] - final_b.info["survival_time"]) <= 0.15 and
              final_a.info["life_loss_count"] == final_b.info["life_loss_count"],
              "same seed and actions repeat within runtime tolerance",
              {"score": [final_a.info["final_score"], final_b.info["final_score"]],
               "time": [final_a.info["survival_time"], final_b.info["survival_time"]]})
    finally:
        deterministic.close()

    auto_workers = start_workers(1, executable, root / "autoreset", time_scale=20, max_duration=0.07)
    scheduler = TrainingSeedScheduler(train_seeds, 20260913)
    reference = TrainingSeedScheduler(train_seeds, 20260913)
    expected_first, expected_second = reference.next_seed(), reference.next_seed()
    env = TurboDashVecEnv(auto_workers, scheduler)
    try:
        env.reset()
        done = np.array([False])
        while not done[0]:
            observation, reward, done, infos = env.step(np.array([1]))
        check(infos[0]["truncated"] and infos[0]["TimeLimit.truncated"], "VecEnv preserves truncation")
        check(infos[0]["terminal_observation"].shape == (236,), "VecEnv preserves terminal_observation")
        check(infos[0]["seed"] == expected_first and env.reset_infos[0]["seed"] == expected_second,
              "auto-reset uses the next TRAIN seed")
    finally:
        env.close()

    parallel = start_workers(4, executable, root / "parallel", time_scale=20, max_duration=2)
    try:
        observations = [worker.reset(train_seeds[index + 2]) for index, worker in enumerate(parallel)]
        for worker, action in zip(parallel, (0, 1, 2, 1)):
            worker.send_step(action)
        results = [worker.receive_step() for worker in parallel]
        check(all(result.info["physics_ticks"] == 5 for result in results), "4 parallel workers step successfully")
        check(all(np.isfinite(result.observation).all() for result in results), "4 parallel observations finite")
        check(True, "discrete mapping 0 LEFT, 1 NONE, 2 RIGHT accepted by Unity")
    finally:
        close_workers(parallel)

    disconnected = UnityWorker(0, executable,
        WorkerPaths(root / "disconnect" / "worker_logs" / "worker-0.log",
                    root / "disconnect" / "unity_episode_csv" / "worker-0.csv"),
        time_scale=20, max_duration=2)
    disconnected.start()
    process = disconnected.process
    disconnected.reset(train_seeds[9])
    disconnected.disconnect()
    try:
        code = process.wait(timeout=15)
        check(code != 0, "worker disconnect terminates process with failure", code)
    finally:
        disconnected.terminate()

    report = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "worker_executable": str(executable),
        "checks": checks,
        "passed": sum(item["passed"] for item in checks),
        "failed": sum(not item["passed"] for item in checks),
        "source_split": "TRAIN",
        "test_status": "UNUSED",
    }
    (root / "bridge-verification.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
