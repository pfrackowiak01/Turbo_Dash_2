from __future__ import annotations

import csv
import json
import statistics
import time
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

from .protocol import ActionSpace
from .worker import close_workers, start_workers

METRICS = (
    "final_score", "survival_time", "episode_reward", "life_loss_count", "collisions",
    "obstacles_avoided", "max_level", "hearts_collected", "shields_collected",
    "boosts_collected", "gold_collected", "diamonds_collected", "turbo_activations",
)


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {"episodes": len(rows)}
    for metric in METRICS:
        values = [float(row[metric]) for row in rows]
        result[metric] = {
            "mean": statistics.fmean(values),
            "median": statistics.median(values),
            "std": statistics.pstdev(values),
            "min": min(values),
            "max": max(values),
        }
    result["terminal_distribution"] = dict(Counter(str(row["terminal_reason"]) for row in rows))
    return result


def write_validation(output_dir: Path, rows: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    fields = ["seed", *METRICS, "terminal_reason", "terminated", "truncated", "decision_count"]
    with (output_dir / "episodes.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def run_validation(model, executable: Path, seeds: list[int], output_dir: Path, *, workers_count: int,
                   time_scale: float, action_space: ActionSpace = ActionSpace.DISCRETE,
                   max_duration: float = 300, nographics: bool = True) -> dict[str, Any]:
    if len(seeds) != 100:
        raise ValueError("Validation must use all 100 frozen VALIDATION seeds")
    if workers_count <= 0:
        raise ValueError("workers_count must be positive")
    workers_count = min(workers_count, len(seeds))
    if max_duration <= 0:
        raise ValueError("max_duration must be positive")
    workers = start_workers(workers_count, executable, output_dir, time_scale=time_scale,
                            max_duration=max_duration, nographics=nographics, action_space=action_space)
    active: list[tuple[int, np.ndarray] | None] = [None] * workers_count
    next_index = 0
    rows: list[dict[str, Any]] = []
    continuous_actions: list[float] = []
    returns = [0.0] * workers_count
    started = time.perf_counter()
    try:
        for index, worker in enumerate(workers):
            seed = seeds[next_index]
            next_index += 1
            active[index] = (seed, worker.reset(seed))
        while any(item is not None for item in active):
            indices = [index for index, item in enumerate(active) if item is not None]
            observations = np.stack([active[index][1] for index in indices])
            actions, _ = model.predict(observations, deterministic=True)
            action_values = np.asarray(actions)
            if action_space == ActionSpace.DISCRETE:
                action_values = action_values.reshape(len(indices))
            else:
                action_values = action_values.reshape(len(indices), -1)
                if action_values.shape[1] != 1 or not np.isfinite(action_values).all():
                    raise ValueError("Continuous model must return one finite action per environment")
                action_values = np.clip(action_values[:, 0], -1.0, 1.0)
                continuous_actions.extend(float(action) for action in action_values)
            for index, action in zip(indices, action_values):
                workers[index].send_step(int(action) if action_space == ActionSpace.DISCRETE else float(action))
            for index in indices:
                result = workers[index].receive_step()
                returns[index] += result.reward
                if result.terminated or result.truncated:
                    seed = active[index][0]
                    row = dict(result.info)
                    row.update({
                        "seed": seed,
                        "terminated": result.terminated,
                        "truncated": result.truncated,
                        "python_reward_sum": returns[index],
                    })
                    rows.append(row)
                    returns[index] = 0
                    if next_index < len(seeds):
                        seed = seeds[next_index]
                        next_index += 1
                        active[index] = (seed, workers[index].reset(seed))
                    else:
                        active[index] = None
                else:
                    active[index] = (active[index][0], result.observation)
        if sorted(int(row["seed"]) for row in rows) != sorted(seeds):
            raise RuntimeError("Validation seed coverage differs from the frozen VALIDATION split")
        summary = summarize(rows)
        summary["wall_seconds"] = time.perf_counter() - started
        summary["action_space"] = action_space.name.title()
        summary["max_duration"] = float(max_duration)
        if action_space == ActionSpace.CONTINUOUS:
            episode_fitnesses = [
                float(row["final_score"]) / 100.0 - 0.5 * int(row["life_loss_count"])
                for row in rows
            ]
            summary["episode_fitness"] = {
                "mean": statistics.fmean(episode_fitnesses),
                "median": statistics.median(episode_fitnesses),
                "std": statistics.pstdev(episode_fitnesses),
                "min": min(episode_fitnesses),
                "max": max(episode_fitnesses),
            }
            near_zero_threshold = 0.1
            near_max_threshold = 0.9
            summary["continuous_action"] = {
                "decision_count": len(continuous_actions),
                "mean_abs_steering": statistics.fmean(abs(value) for value in continuous_actions),
                "mean_steering": statistics.fmean(continuous_actions),
                "steering_std": statistics.pstdev(continuous_actions),
                "fraction_near_zero": sum(abs(value) < near_zero_threshold for value in continuous_actions)
                / len(continuous_actions),
                "fraction_near_max": sum(abs(value) > near_max_threshold for value in continuous_actions)
                / len(continuous_actions),
                "fraction_left": sum(value < -near_zero_threshold for value in continuous_actions)
                / len(continuous_actions),
                "fraction_right": sum(value > near_zero_threshold for value in continuous_actions)
                / len(continuous_actions),
                "near_zero_rule": "abs(steering) < 0.1",
                "near_max_rule": "abs(steering) > 0.9",
                "left_rule": "steering < -0.1",
                "right_rule": "steering > 0.1",
                "role": "analytics_only_not_used_for_fitness_or_selection",
            }
        summary["test_status"] = "UNUSED FOR TRAINING/TUNING/EVALUATION"
        write_validation(output_dir, rows, summary)
        return summary
    finally:
        close_workers(workers)
