from __future__ import annotations

import math
from typing import Sequence

import neat
import numpy as np

from .protocol import DiscreteAction, OBSERVATION_SIZE


def select_discrete_action(outputs: Sequence[float]) -> int:
    """Map LEFT/NONE/RIGHT outputs to an action, resolving every exact tie to NONE."""
    values = tuple(float(value) for value in outputs)
    if len(values) != 3 or not all(math.isfinite(value) for value in values):
        raise ValueError("NEAT policy must produce exactly three finite outputs")
    maximum = max(values)
    winners = [index for index, value in enumerate(values) if value == maximum]
    if len(winners) != 1:
        return int(DiscreteAction.NONE)
    return winners[0]


def episode_fitness(final_score: float, life_loss_count: int) -> float:
    return float(final_score) / 100.0 - 0.5 * int(life_loss_count)


class NeatPolicy:
    """Small inference adapter compatible with the shared validation runner."""

    def __init__(self, genome, config: neat.Config):
        self.network = neat.nn.FeedForwardNetwork.create(genome, config)

    def predict(self, observations, deterministic: bool = True):
        if not deterministic:
            raise ValueError("NEAT Discrete inference is deterministic")
        batch = np.asarray(observations, dtype=np.float32)
        if batch.ndim != 2 or batch.shape[1] != OBSERVATION_SIZE:
            raise ValueError(f"Expected observations with shape (n, {OBSERVATION_SIZE})")
        actions = np.asarray(
            [select_discrete_action(self.network.activate(observation)) for observation in batch],
            dtype=np.int64,
        )
        return actions, None
