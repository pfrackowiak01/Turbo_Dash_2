from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import neat
import numpy as np
from gymnasium import spaces
from stable_baselines3 import PPO

from .final_rule_based import RuleBasedV1Policy
from .manifest import git_snapshot
from .neat_checkpoint import read_pickle
from .neat_continuous_policy import NeatContinuousPolicy
from .neat_policy import NeatPolicy
from .paths import DEFAULT_WORKER, REPOSITORY_ROOT, SEED_ROOT
from .protocol import ActionSpace, DiscreteAction
from .seeds import file_sha256, load_seed_split
from .worker import UnityWorker, WorkerPaths, close_workers, start_workers

FINAL_ROOT = REPOSITORY_ROOT / "Training" / "final_test"
SELECTION_PATH = FINAL_ROOT / "final_model_selection.json"
PROTOCOL_PATH = FINAL_ROOT / "final_test_protocol.json"
RAW_PATH = FINAL_ROOT / "raw" / "final_test_episodes.csv"
PROGRESS_PATH = FINAL_ROOT / "final_test_progress.json"
SCHEDULE_PATH = FINAL_ROOT / "test_schedule.json"
RUN_MANIFEST_PATH = FINAL_ROOT / "final_test_run_manifest.json"
WORKER_SESSIONS_ROOT = FINAL_ROOT / "worker_sessions"
TECHNICAL_FAILURES_PATH = FINAL_ROOT / "raw" / "technical_failures.csv"
RAW_FIELDS = (
    "method", "model_id", "model_sha256", "action_space", "test_seed", "repetition_index",
    "seed", "repetition", "schedule_index", "worker_id", "retry_count",
    "research_protocol_version", "observation_schema_version", "observation_size", "fixed_timestep",
    "decision_interval", "max_duration", "time_scale",
    "episode_id", "decision_count", "final_score", "survival_time", "segments_passed",
    "obstacles_encountered", "obstacles_avoided", "collisions", "life_loss_count", "shield_hits",
    "fatal_collision", "hearts_collected", "shields_collected", "boosts_collected",
    "turbo_activations", "gold_collected", "diamonds_collected", "max_level",
    "outside_stages_reached", "time_inside", "time_outside", "max_environment_speed",
    "episode_reward", "fitness", "terminal_reason", "terminated", "truncated", "physics_ticks",
    "discrete_left_count", "discrete_none_count", "discrete_right_count",
    "discrete_left_rate", "discrete_none_rate", "discrete_right_rate",
    "continuous_mean", "continuous_mean_abs", "continuous_std", "continuous_near_zero_rate",
    "continuous_near_max_rate", "continuous_left_rate", "continuous_right_rate", "continuous_bin_counts",
    "action_change_count", "action_change_rate", "mean_action_hold_decisions", "mean_abs_delta_steering",
    "steering_sign_change_rate", "wall_seconds_episode", "completed_utc",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def key(method: str, seed: int, repetition: int) -> str:
    return f"{method}|{int(seed)}|{int(repetition)}"


def require_clean_repository(*, resume: bool) -> str:
    state = git_snapshot()
    entries = list(state["status_porcelain"])
    if resume:
        allowed = (
            "Training/final_test/raw/", "Training/final_test/analysis/", "Training/final_test/plots/",
            "Training/final_test/worker_sessions/", "Training/final_test/final_test_progress.json",
            "Training/final_test/test_schedule.json", "Training/final_test/final_test_run_manifest.json",
            "Training/final_test/final_test_results.json", "Training/final_test/FINAL_TEST_REPORT.md",
        )
        entries = [entry for entry in entries
                   if not entry[3:].replace('"', "").replace("\\", "/").startswith(allowed)]
    if entries:
        raise RuntimeError("Git working tree is not clean; commit/stash every non-result change before TEST")
    return str(state["commit"])


def assert_protocol(protocol: dict[str, Any], workers: int, time_scale: float) -> None:
    expected = {
        "method_order": ["RuleBasedV1", "PPO-D", "PPO-C", "NEAT-D", "NEAT-C"],
        "test_horizon_seconds": 500,
        "test_seed_count": 200,
        "repetitions_per_seed": 3,
        "repetitions": 3,
        "methods": 5,
        "episodes_per_method": 600,
        "expected_total_episodes": 3000,
        "schedule_random_seed": 20260930,
        "schedule_seed": 20260930,
        "workers": 6,
        "time_scale": 20,
        "max_duration": 500,
        "research_protocol_version": 1,
        "observation_schema_version": 2,
        "observation_size": 236,
        "fixed_timestep": 0.01,
        "decision_interval": 0.05,
        "primary_metric": "finalScore",
        "analysis_unit": "seed",
        "technical_retry_limit": 2,
        "bootstrap_resamples": 20000,
    }
    for name, value in expected.items():
        if protocol.get(name) != value:
            raise ValueError(f"Frozen protocol mismatch: {name}")
    if workers != 6 or float(time_scale) != 20.0:
        raise ValueError("Final TEST requires exactly Workers=6 and TimeScale=20")


def verify_selection(selection: dict[str, Any]) -> dict[str, dict[str, Any]]:
    methods = selection.get("methods", [])
    if selection.get("test_status_at_freeze") != "UNREAD_AND_UNUSED" or len(methods) != 5:
        raise ValueError("Frozen model selection manifest is invalid")
    by_name = {item["method"]: item for item in methods}
    if list(by_name) != ["RuleBasedV1", "PPO-D", "PPO-C", "NEAT-D", "NEAT-C"]:
        raise ValueError("Frozen model order is invalid")
    for method, item in by_name.items():
        checks: list[tuple[str, str]] = []
        if method == "RuleBasedV1":
            checks.append((item["source_path"], item["source_sha256"]))
            checks.append((item["inference_adapter_path"], item["inference_adapter_sha256"]))
        elif method.startswith("PPO"):
            checks.extend(((item["model_path"], item["model_sha256"]),
                           (item["source_checkpoint_path"], item["source_checkpoint_sha256"]),
                           (item["config_path"], item["config_sha256"])))
        else:
            checks.extend(((item["genome_path"], item["genome_sha256"]),
                           (item["config_path"], item["config_sha256"])))
        for relative, expected_hash in checks:
            path = REPOSITORY_ROOT / relative
            if not path.is_file() or file_sha256(path) != expected_hash:
                raise RuntimeError(f"Frozen artifact integrity failed for {method}: {relative}")
    return by_name


def load_policies(methods: dict[str, dict[str, Any]]) -> dict[str, Any]:
    policies: dict[str, Any] = {"RuleBasedV1": RuleBasedV1Policy()}
    for method in ("PPO-D", "PPO-C"):
        policies[method] = PPO.load(REPOSITORY_ROOT / methods[method]["model_path"], device="cpu")
        if int(policies[method].num_timesteps) != int(methods[method]["checkpoint_timestep"]):
            raise RuntimeError(f"{method} checkpoint timestep differs from the freeze")
        if tuple(policies[method].observation_space.shape or ()) != (236,):
            raise RuntimeError(f"{method} observation space differs from Observation v2")
    if not isinstance(policies["PPO-D"].action_space, spaces.Discrete) or policies["PPO-D"].action_space.n != 3:
        raise RuntimeError("PPO-D action space differs from Discrete(3)")
    continuous_space = policies["PPO-C"].action_space
    if (not isinstance(continuous_space, spaces.Box) or continuous_space.shape != (1,)
            or not np.allclose(continuous_space.low, -1) or not np.allclose(continuous_space.high, 1)):
        raise RuntimeError("PPO-C action space differs from Box(-1, 1, (1,))")
    for method, policy_type, output_count in (
        ("NEAT-D", NeatPolicy, 3), ("NEAT-C", NeatContinuousPolicy, 1)
    ):
        item = methods[method]
        config = neat.Config(neat.DefaultGenome, neat.DefaultReproduction, neat.DefaultSpeciesSet,
                             neat.DefaultStagnation, str(REPOSITORY_ROOT / item["config_path"]))
        if config.genome_config.num_inputs != 236 or config.genome_config.num_outputs != output_count:
            raise RuntimeError(f"{method} topology differs from the freeze")
        policies[method] = policy_type(read_pickle(REPOSITORY_ROOT / item["genome_path"]), config)
    return policies


def verify_worker_bridge(executable: Path, time_scale: float) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="turbodash-final-preflight-") as directory:
        root = Path(directory)
        worker = UnityWorker(0, executable, WorkerPaths(root / "worker.log", root / "episodes.csv"),
                             time_scale=time_scale, action_space=ActionSpace.DISCRETE, max_duration=500)
        worker.start()
        handshake = worker.handshake
        worker.close()
        if handshake is None:
            raise RuntimeError("Research Worker did not provide a handshake")
        return {
            "transport_version": handshake.transport_version,
            "research_protocol_version": handshake.research_version,
            "observation_schema_version": handshake.observation_schema,
            "observation_size": handshake.observation_size,
            "fixed_timestep": handshake.fixed_timestep,
            "decision_interval": handshake.decision_interval,
        }


def make_schedule(seeds: list[int], protocol: dict[str, Any]) -> list[dict[str, int]]:
    jobs = [{"test_seed": int(seed), "repetition_index": repetition,
             "seed": int(seed), "repetition": repetition}
            for seed in seeds for repetition in range(1, int(protocol["repetitions"]) + 1)]
    random.Random(int(protocol["schedule_random_seed"])).shuffle(jobs)
    for index, job in enumerate(jobs):
        job["schedule_index"] = index
    if len(jobs) != 600 or len({(job["seed"], job["repetition"]) for job in jobs}) != 600:
        raise RuntimeError("Generated TEST schedule is invalid")
    return jobs


def remaining_jobs(method: str, schedule: list[dict[str, int]], completed: set[str]) -> list[dict[str, int]]:
    return [job for job in schedule if key(method, job["seed"], job["repetition"]) not in completed]


def append_row(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=RAW_FIELDS, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerow(row)
        stream.flush()
        os.fsync(stream.fileno())


def append_technical_failure(method: str, job: dict[str, int] | None, attempt: int,
                             exception: Exception) -> None:
    fields = ("status", "method", "test_seed", "repetition_index", "attempt", "error_type", "utc")
    TECHNICAL_FAILURES_PATH.parent.mkdir(parents=True, exist_ok=True)
    exists = TECHNICAL_FAILURES_PATH.exists()
    with TECHNICAL_FAILURES_PATH.open("a", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        if not exists:
            writer.writeheader()
        writer.writerow({"status": "technical_failure", "method": method,
                         "test_seed": "" if job is None else job["seed"],
                         "repetition_index": "" if job is None else job["repetition"],
                         "attempt": attempt, "error_type": type(exception).__name__, "utc": utc_now()})
        stream.flush()
        os.fsync(stream.fileno())


def read_raw(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != RAW_FIELDS:
            raise RuntimeError("Raw TEST CSV header is missing or incompatible")
        rows = list(reader)
    seen: set[str] = set()
    for row in rows:
        item_key = key(row["method"], int(row["seed"]), int(row["repetition"]))
        if item_key in seen:
            raise RuntimeError(f"Duplicate completed TEST key: {item_key}")
        seen.add(item_key)
    return rows


@dataclass
class ActionTelemetry:
    action_space: ActionSpace
    values: list[float] = field(default_factory=list)

    def add(self, value: int | float) -> None:
        self.values.append(float(value))

    def fields(self) -> dict[str, Any]:
        count = len(self.values)
        empty = {
            "discrete_left_count": "", "discrete_none_count": "", "discrete_right_count": "",
            "discrete_left_rate": "", "discrete_none_rate": "", "discrete_right_rate": "",
            "continuous_mean": "", "continuous_mean_abs": "", "continuous_std": "",
            "continuous_near_zero_rate": "", "continuous_near_max_rate": "",
            "continuous_left_rate": "", "continuous_right_rate": "", "continuous_bin_counts": "",
            "action_change_count": sum(a != b for a, b in zip(self.values, self.values[1:])),
            "action_change_rate": (sum(a != b for a, b in zip(self.values, self.values[1:])) / (count - 1))
            if count > 1 else 0.0,
            "mean_action_hold_decisions": count / (1 + sum(a != b for a, b in zip(self.values, self.values[1:]))),
            "mean_abs_delta_steering": "", "steering_sign_change_rate": "",
        }
        if count == 0:
            raise RuntimeError("Completed episode has no decisions")
        if self.action_space == ActionSpace.DISCRETE:
            integers = [int(value) for value in self.values]
            counts = {action: integers.count(int(action)) for action in DiscreteAction}
            empty.update({
                "discrete_left_count": counts[DiscreteAction.LEFT],
                "discrete_none_count": counts[DiscreteAction.NONE],
                "discrete_right_count": counts[DiscreteAction.RIGHT],
                "discrete_left_rate": counts[DiscreteAction.LEFT] / count,
                "discrete_none_rate": counts[DiscreteAction.NONE] / count,
                "discrete_right_rate": counts[DiscreteAction.RIGHT] / count,
            })
        else:
            values = np.asarray(self.values, dtype=np.float64)
            deltas = np.diff(values)
            nonzero_signs = np.sign(values[np.abs(values) > 0.1])
            empty.update({
                "continuous_mean": float(np.mean(values)),
                "continuous_mean_abs": float(np.mean(np.abs(values))),
                "continuous_std": float(np.std(values)),
                "continuous_near_zero_rate": float(np.mean(np.abs(values) < 0.1)),
                "continuous_near_max_rate": float(np.mean(np.abs(values) > 0.9)),
                "continuous_left_rate": float(np.mean(values < -0.1)),
                "continuous_right_rate": float(np.mean(values > 0.1)),
                "continuous_bin_counts": json.dumps(np.histogram(values, bins=np.linspace(-1, 1, 41))[0].tolist()),
                "mean_abs_delta_steering": float(np.mean(np.abs(deltas))) if len(deltas) else 0.0,
                "steering_sign_change_rate": float(np.mean(nonzero_signs[1:] != nonzero_signs[:-1]))
                if len(nonzero_signs) > 1 else 0.0,
            })
        return empty


@dataclass
class ActiveEpisode:
    job: dict[str, int]
    observation: np.ndarray
    telemetry: ActionTelemetry
    started_at: float = field(default_factory=time.perf_counter)


def predict_actions(method: str, policy: Any, observations: np.ndarray, slots: list[int],
                    action_space: ActionSpace) -> np.ndarray:
    if method == "RuleBasedV1":
        return policy.predict_slots(observations, slots)
    actions, _ = policy.predict(observations, deterministic=True)
    values = np.asarray(actions)
    if action_space == ActionSpace.DISCRETE:
        values = values.reshape(len(slots))
        if not np.isin(values, [0, 1, 2]).all():
            raise RuntimeError(f"{method} emitted an invalid discrete action")
        return values.astype(np.int64)
    values = values.reshape(len(slots), -1)
    if values.shape[1] != 1 or not np.isfinite(values).all():
        raise RuntimeError(f"{method} emitted an invalid continuous action")
    return np.clip(values[:, 0], -1.0, 1.0).astype(np.float32)


def progress_payload(completed: set[str], attempts: dict[str, int], started: float,
                     protocol_hash: str, selection_hash: str, status: str) -> dict[str, Any]:
    elapsed = max(0.0, time.monotonic() - started)
    done = len(completed)
    eta = (elapsed / done * (3000 - done)) if done else None
    method_counts = {method: sum(item.startswith(method + "|") for item in completed) for method in
                     ("RuleBasedV1", "PPO-D", "PPO-C", "NEAT-D", "NEAT-C")}
    return {
        "schema": 1, "status": status, "completed_episodes": done, "expected_episodes": 3000,
        "remaining_episodes": 3000 - done, "elapsed_wall_seconds": elapsed,
        "eta_seconds": eta, "completed_by_method": method_counts, "technical_retry_counts": attempts,
        "protocol_sha256": protocol_hash, "model_selection_sha256": selection_hash,
        "updated_utc": utc_now(),
    }


def close_safely(workers: list[UnityWorker]) -> None:
    try:
        close_workers(workers)
    except Exception:
        for worker in workers:
            worker.terminate()


def run_method(method: str, model_info: dict[str, Any], policy: Any, schedule: list[dict[str, int]], completed: set[str],
               attempts: dict[str, int], raw_path: Path, protocol: dict[str, Any], worker_exe: Path,
               started: float, protocol_hash: str, selection_hash: str) -> None:
    action_space = ActionSpace.CONTINUOUS if method in ("PPO-C", "NEAT-C") else ActionSpace.DISCRETE
    pending = remaining_jobs(method, schedule, completed)
    session_root = WORKER_SESSIONS_ROOT / method
    existing_sessions = [int(path.name.split("-")[-1]) for path in session_root.glob("session-[0-9][0-9][0-9][0-9]")]
    session = max(existing_sessions, default=0)
    startup_failures = 0
    while pending:
        session += 1
        run_dir = WORKER_SESSIONS_ROOT / method / f"session-{session:04d}"
        workers: list[UnityWorker] = []
        active: list[ActiveEpisode | None] = [None] * int(protocol["workers"])
        cursor = 0
        try:
            workers = start_workers(int(protocol["workers"]), worker_exe, run_dir,
                                    time_scale=float(protocol["time_scale"]),
                                    max_duration=float(protocol["max_duration"]), action_space=action_space)
            startup_failures = 0
            for slot, worker in enumerate(workers):
                if cursor >= len(pending):
                    break
                job = pending[cursor]
                cursor += 1
                if method == "RuleBasedV1":
                    policy.reset_slot(slot)
                active[slot] = ActiveEpisode(job, worker.reset(job["seed"]), ActionTelemetry(action_space))
            while any(item is not None for item in active):
                slots = [slot for slot, item in enumerate(active) if item is not None]
                observations = np.stack([active[slot].observation for slot in slots])
                values = predict_actions(method, policy, observations, slots, action_space)
                for slot, value in zip(slots, values):
                    sent = int(value) if action_space == ActionSpace.DISCRETE else float(value)
                    active[slot].telemetry.add(sent)
                    workers[slot].send_step(sent)
                for slot in slots:
                    result = workers[slot].receive_step()
                    episode = active[slot]
                    if result.terminated or result.truncated:
                        job = episode.job
                        if int(result.info["seed"]) != job["seed"]:
                            raise RuntimeError("Unity returned a seed different from the scheduled TEST seed")
                        if int(result.info["decision_count"]) != len(episode.telemetry.values):
                            raise RuntimeError("Unity decision count differs from action telemetry")
                        row = {name: "" for name in RAW_FIELDS}
                        row.update(result.info)
                        row.update({
                            "method": method,
                            "model_id": model_info.get("run_id", "RuleBasedV1") + (
                                f"/generation-{model_info['generation']}/genome-{model_info['genome_id']}"
                                if "generation" in model_info else
                                f"/checkpoint-{model_info['checkpoint_timestep']}" if "checkpoint_timestep" in model_info else ""),
                            "model_sha256": model_info.get("model_sha256", model_info.get("genome_sha256", model_info.get("source_sha256"))),
                            "action_space": action_space.name.title(),
                            "test_seed": job["seed"], "repetition_index": job["repetition"],
                            "seed": job["seed"], "repetition": job["repetition"],
                            "schedule_index": job["schedule_index"], "worker_id": slot,
                            "retry_count": attempts.get(key(method, job["seed"], job["repetition"]), 0),
                            "terminated": result.terminated, "truncated": result.truncated,
                            "research_protocol_version": protocol["research_protocol_version"],
                            "observation_schema_version": protocol["observation_schema_version"],
                            "observation_size": protocol["observation_size"],
                            "fixed_timestep": protocol["fixed_timestep"],
                            "decision_interval": protocol["decision_interval"],
                            "max_duration": protocol["max_duration"], "time_scale": protocol["time_scale"],
                            "fitness": float(result.info["final_score"]) / 100.0
                            - 0.5 * int(result.info["life_loss_count"]),
                            "wall_seconds_episode": time.perf_counter() - episode.started_at,
                            "completed_utc": utc_now(),
                        })
                        row.update(episode.telemetry.fields())
                        append_row(raw_path, row)
                        completed.add(key(method, job["seed"], job["repetition"]))
                        if cursor < len(pending):
                            next_job = pending[cursor]
                            cursor += 1
                            if method == "RuleBasedV1":
                                policy.reset_slot(slot)
                            active[slot] = ActiveEpisode(next_job, workers[slot].reset(next_job["seed"]),
                                                         ActionTelemetry(action_space))
                        else:
                            active[slot] = None
                        payload = progress_payload(completed, attempts, started, protocol_hash, selection_hash, "running")
                        atomic_json(PROGRESS_PATH, payload)
                        eta = payload["eta_seconds"]
                        method_done = payload["completed_by_method"][method]
                        eta_text = f"{eta / 60:.1f} min" if eta is not None else "pending"
                        print(f"FINAL TEST | Method={method} {method_done}/600 | Overall={len(completed)}/3000 | "
                              f"Workers=6/6 healthy | retries={sum(attempts.values())} | "
                              f"Elapsed={payload['elapsed_wall_seconds'] / 60:.1f} min | ETA total={eta_text}", flush=True)
                    else:
                        episode.observation = result.observation
            close_workers(workers)
            workers = []
            pending = remaining_jobs(method, schedule, completed)
        except Exception as exc:
            affected = [item.job for item in active if item is not None]
            if not workers:
                startup_failures += 1
                append_technical_failure(method, None, startup_failures, exc)
                if startup_failures > int(protocol["technical_retry_limit"]):
                    raise RuntimeError(f"{method} worker startup failed after retries") from exc
            for job in affected:
                item_key = key(method, job["seed"], job["repetition"])
                attempts[item_key] = attempts.get(item_key, 0) + 1
                append_technical_failure(method, job, attempts[item_key], exc)
                if attempts[item_key] > int(protocol["technical_retry_limit"]):
                    atomic_json(PROGRESS_PATH, progress_payload(
                        completed, attempts, started, protocol_hash, selection_hash, "stopped_technical_failure"))
                    raise RuntimeError(f"Technical retry limit exceeded for {item_key}") from exc
            print(f"Health=RESTARTING | method={method} | affected={len(affected)} | "
                  f"retries={sum(attempts.values())} | error={type(exc).__name__}", flush=True)
            atomic_json(PROGRESS_PATH, progress_payload(
                completed, attempts, started, protocol_hash, selection_hash, "retrying_technical_failure"))
            close_safely(workers)
            pending = remaining_jobs(method, schedule, completed)


def run(args: argparse.Namespace) -> int:
    protocol = read_json(PROTOCOL_PATH)
    selection = read_json(SELECTION_PATH)
    assert_protocol(protocol, args.workers, args.time_scale)
    commit = require_clean_repository(resume=args.resume)
    methods = verify_selection(selection)
    policies = load_policies(methods)
    worker_exe = args.worker_exe.resolve()
    if not worker_exe.is_file():
        raise FileNotFoundError(f"Research Worker build is missing: {worker_exe}")
    worker_hash = file_sha256(worker_exe)
    bridge = verify_worker_bridge(worker_exe, args.time_scale)
    protocol_hash = file_sha256(PROTOCOL_PATH)
    selection_hash = file_sha256(SELECTION_PATH)
    print("Preflight OK: clean Git, frozen artifacts, deterministic policies and worker handshake verified.", flush=True)
    if args.preflight_only:
        print("TEST seed file was not opened; no TEST episode was started.", flush=True)
        return 0

    generated = (RAW_PATH, TECHNICAL_FAILURES_PATH, PROGRESS_PATH, SCHEDULE_PATH, RUN_MANIFEST_PATH,
                 FINAL_ROOT / "final_test_results.json", FINAL_ROOT / "FINAL_TEST_REPORT.md",
                 FINAL_ROOT / "analysis", FINAL_ROOT / "plots", WORKER_SESSIONS_ROOT)
    if args.resume:
        if not RUN_MANIFEST_PATH.is_file() or not SCHEDULE_PATH.is_file() or not RAW_PATH.is_file():
            raise RuntimeError("-Resume requires an existing final TEST run")
    elif any(path.exists() for path in generated):
        raise FileExistsError("Final TEST results already exist; use -Resume only for the same frozen run")

    # This is the first intentional TEST access in the final command, after every preflight check above.
    seeds = load_seed_split(SEED_ROOT / "test.json", "test", allow_test=True)
    train = set(load_seed_split(SEED_ROOT / "train.json", "train"))
    validation = set(load_seed_split(SEED_ROOT / "validation.json", "validation"))
    if set(seeds) & (train | validation):
        raise RuntimeError("TEST seeds overlap TRAIN or VALIDATION")
    schedule = make_schedule(seeds, protocol)
    raw_path = RAW_PATH
    manifest_path = RUN_MANIFEST_PATH
    schedule_path = SCHEDULE_PATH
    if args.resume:
        manifest = read_json(manifest_path)
        if any((manifest.get("protocol_sha256") != protocol_hash,
                manifest.get("model_selection_sha256") != selection_hash,
                manifest.get("worker_sha256") != worker_hash,
                manifest.get("test_seed_sha256") != file_sha256(SEED_ROOT / "test.json"),
                read_json(schedule_path).get("schedule") != schedule)):
            raise RuntimeError("Resume integrity mismatch")
    else:
        manifest = {
            "schema": 1, "status": "running_blinded", "started_utc": utc_now(),
            "git_commit": commit, "git_clean_before_first_test_access": True,
            "protocol_path": str(PROTOCOL_PATH.relative_to(REPOSITORY_ROOT)), "protocol_sha256": protocol_hash,
            "model_selection_path": str(SELECTION_PATH.relative_to(REPOSITORY_ROOT)),
            "model_selection_sha256": selection_hash, "worker_path": str(worker_exe),
            "worker_sha256": worker_hash, "worker_handshake": bridge,
            "test_seed_path": str((SEED_ROOT / "test.json").relative_to(REPOSITORY_ROOT)),
            "test_seed_sha256": file_sha256(SEED_ROOT / "test.json"), "test_seed_count": len(seeds),
            "expected_total_episodes": 3000, "blinded_until_complete": True,
            "python": sys.version, "numpy": np.__version__,
        }
        atomic_json(manifest_path, manifest)
        atomic_json(schedule_path, {"schema": 1, "schedule_random_seed": 20260930, "schedule": schedule})

    rows = read_raw(raw_path)
    completed = {key(row["method"], int(row["seed"]), int(row["repetition"])) for row in rows}
    if len(completed) > 3000:
        raise RuntimeError("Raw TEST data contains too many episodes")
    progress_path = PROGRESS_PATH
    attempts = read_json(progress_path).get("technical_retry_counts", {}) if progress_path.is_file() else {}
    started = time.monotonic()
    atomic_json(progress_path, progress_payload(completed, attempts, started, protocol_hash, selection_hash, "running"))
    for method in protocol["method_order"]:
        run_method(method, methods[method], policies[method], schedule, completed, attempts, raw_path, protocol, worker_exe,
                   started, protocol_hash, selection_hash)
    if len(completed) != 3000 or len(read_raw(raw_path)) != 3000:
        raise RuntimeError("TEST execution ended without exactly 3000 unique valid episodes")
    atomic_json(progress_path, progress_payload(completed, attempts, started, protocol_hash, selection_hash,
                                                "complete_ready_to_unblind"))
    manifest.update({"status": "complete_unblinded", "completed_utc": utc_now(),
                     "valid_episode_count": 3000, "technical_retry_counts": attempts})
    atomic_json(manifest_path, manifest)
    print("All 3000 valid episodes are complete. Unblinding and prespecified analysis begin now.", flush=True)
    from .final_test_analysis import analyze_final_test
    analyze_final_test(raw_path, FINAL_ROOT, protocol, selection, strict=True)
    print(f"Final report: {FINAL_ROOT / 'FINAL_TEST_REPORT.md'}", flush=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the frozen, blinded Turbo Dash final TEST")
    parser.add_argument("--worker-exe", type=Path, default=DEFAULT_WORKER)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--time-scale", type=float, default=20)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--preflight-only", action="store_true",
                        help="verify everything except test.json; never opens TEST and starts no episode")
    return parser


def main() -> int:
    return run(build_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
