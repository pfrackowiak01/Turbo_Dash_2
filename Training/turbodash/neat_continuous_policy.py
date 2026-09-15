from __future__ import annotations

import math
from typing import Sequence

import neat
import numpy as np

from .protocol import OBSERVATION_SIZE


def select_continuous_action(outputs: Sequence[float]) -> float:
    """Return the single finite steering output, clamped to the protocol Box range."""
    values = tuple(float(value) for value in outputs)
    if len(values) != 1 or not math.isfinite(values[0]):
        raise ValueError("NEAT Continuous policy must produce exactly one finite output")
    return max(-1.0, min(1.0, values[0]))


class NeatContinuousPolicy:
    """Deterministic one-output NEAT adapter for the shared validation runner."""

    def __init__(self, genome, config: neat.Config):
        self.network = neat.nn.FeedForwardNetwork.create(genome, config)

    def predict(self, observations, deterministic: bool = True):
        if not deterministic:
            raise ValueError("NEAT Continuous inference is deterministic")
        batch = np.asarray(observations, dtype=np.float32)
        if batch.ndim != 2 or batch.shape[1] != OBSERVATION_SIZE:
            raise ValueError(f"Expected observations with shape (n, {OBSERVATION_SIZE})")
        actions = np.asarray(
            [[select_continuous_action(self.network.activate(observation))] for observation in batch],
            dtype=np.float32,
        )
        return actions, None
