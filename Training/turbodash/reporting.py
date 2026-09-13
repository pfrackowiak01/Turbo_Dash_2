from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

SUMMARY_FIELDS = [
    "kind", "total_timesteps", "wall_seconds", "transitions_per_second", "seed", "final_score",
    "survival_time", "episode_reward", "life_loss_count", "collisions", "obstacles_avoided",
    "max_level", "hearts_collected", "shields_collected", "boosts_collected", "gold_collected",
    "diamonds_collected", "turbo_activations", "terminal_reason", "mean_final_score",
    "median_final_score", "std_final_score", "policy_gradient_loss", "value_loss", "entropy_loss",
    "explained_variance", "approx_kl", "clip_fraction",
]


def append_summary(path: Path, values: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=SUMMARY_FIELDS, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerow({key: values.get(key, "") for key in SUMMARY_FIELDS})
