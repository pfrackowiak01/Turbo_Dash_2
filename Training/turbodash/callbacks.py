from __future__ import annotations

import math
import time
from pathlib import Path

from stable_baselines3.common.callbacks import BaseCallback

from .manifest import write_json
from .protocol import ActionSpace
from .reporting import append_summary
from .validation import run_validation


class PipelineCallback(BaseCallback):
    def __init__(self, run_dir: Path, scheduler, executable: Path, validation_seeds: list[int], *,
                 checkpoint_interval: int, validation_interval: int, validation_workers: int,
                 time_scale: float, action_space: ActionSpace, verbose: int = 1):
        super().__init__(verbose)
        self.run_dir = run_dir
        self.scheduler = scheduler
        self.executable = executable
        self.validation_seeds = validation_seeds
        self.checkpoint_interval = checkpoint_interval
        self.validation_interval = validation_interval
        self.validation_workers = validation_workers
        self.time_scale = time_scale
        self.action_space = action_space
        self.next_checkpoint = checkpoint_interval
        self.next_validation = validation_interval
        self.best_score = -math.inf
        self.started = time.perf_counter()

    def align_with_existing_steps(self, timesteps: int) -> None:
        self.next_checkpoint = ((timesteps // self.checkpoint_interval) + 1) * self.checkpoint_interval
        self.next_validation = ((timesteps // self.validation_interval) + 1) * self.validation_interval

    def _on_step(self) -> bool:
        wall = time.perf_counter() - self.started
        for info in self.locals.get("infos", []):
            if "terminal_observation" not in info:
                continue
            append_summary(self.run_dir / "training_summary.csv", {
                "kind": "training_episode",
                "total_timesteps": self.num_timesteps,
                "wall_seconds": wall,
                "transitions_per_second": self.num_timesteps / wall if wall else 0,
                **info,
            })
        while self.num_timesteps >= self.next_checkpoint:
            self.save_checkpoint(self.next_checkpoint)
            self.next_checkpoint += self.checkpoint_interval
        while self.num_timesteps >= self.next_validation:
            self.validate(self.next_validation)
            self.next_validation += self.validation_interval
        return True

    def _on_rollout_end(self) -> None:
        values = self.model.logger.name_to_value
        names = {
            "train/policy_gradient_loss": "policy_gradient_loss",
            "train/value_loss": "value_loss",
            "train/entropy_loss": "entropy_loss",
            "train/explained_variance": "explained_variance",
            "train/approx_kl": "approx_kl",
            "train/clip_fraction": "clip_fraction",
        }
        row = {"kind": "ppo_rollout", "total_timesteps": self.num_timesteps}
        for source, target in names.items():
            value = values.get(source, "")
            if value != "" and not math.isfinite(float(value)):
                raise FloatingPointError(f"PPO metric {source} is NaN or Infinity")
            row[target] = value
        wall = time.perf_counter() - self.started
        row["wall_seconds"] = wall
        row["transitions_per_second"] = self.num_timesteps / wall if wall else 0
        append_summary(self.run_dir / "training_summary.csv", row)

    def save_checkpoint(self, label: int | str) -> Path:
        model_path = self.run_dir / "checkpoints" / f"ppo_{label}"
        self.model.save(model_path)
        self.scheduler.save(self.run_dir / "checkpoints" / f"seed_scheduler_{label}.json")
        return model_path.with_suffix(".zip")

    def validate(self, label: int | str):
        output = self.run_dir / "validation" / f"step-{label}"
        summary = run_validation(
            self.model, self.executable, self.validation_seeds, output,
            workers_count=self.validation_workers, time_scale=self.time_scale,
            action_space=self.action_space, max_duration=300,
        )
        mean_score = summary["final_score"]["mean"]
        append_summary(self.run_dir / "training_summary.csv", {
            "kind": "validation",
            "total_timesteps": self.num_timesteps,
            "mean_final_score": mean_score,
            "median_final_score": summary["final_score"]["median"],
            "std_final_score": summary["final_score"]["std"],
        })
        if mean_score > self.best_score:
            self.best_score = mean_score
            self.model.save(self.run_dir / "best_model" / "model")
            write_json(self.run_dir / "best_model" / "selection.json", {
                "criterion": "maximum mean finalScore on 100 VALIDATION seeds",
                "checkpoint_label": label,
                "checkpoint_timestep": int(self.num_timesteps),
                "source_checkpoint": str((self.run_dir / "checkpoints" / f"ppo_{label}.zip").resolve()),
                "validation_summary": str((output / "summary.json").resolve()),
                "summary": summary,
            })
        return summary
