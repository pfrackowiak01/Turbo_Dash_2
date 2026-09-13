from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

EXPECTED_COUNTS = {"train": 700, "validation": 100, "test": 200}


def load_seed_split(path: Path, expected_split: str, *, allow_test: bool = False) -> list[int]:
    expected_split = expected_split.lower()
    if expected_split == "test" and not allow_test:
        raise ValueError("TEST is forbidden for training, smoke, benchmark, validation and tuning")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if data.get("protocolVersion") != 1 or str(data.get("split", "")).lower() != expected_split:
        raise ValueError(f"Seed file {path} is not Research Protocol v1 {expected_split.upper()}")
    seeds = data.get("seeds")
    if not isinstance(seeds, list) or len(seeds) != EXPECTED_COUNTS[expected_split]:
        raise ValueError(f"{expected_split.upper()} must contain {EXPECTED_COUNTS[expected_split]} seeds")
    if any(not isinstance(seed, int) or seed <= 0 or seed > 2_147_483_647 for seed in seeds):
        raise ValueError(f"{expected_split.upper()} contains an invalid seed")
    if len(set(seeds)) != len(seeds):
        raise ValueError(f"{expected_split.upper()} contains duplicate seeds")
    return seeds


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class TrainingSeedScheduler:
    def __init__(self, seeds: list[int], experiment_seed: int):
        if len(seeds) != EXPECTED_COUNTS["train"]:
            raise ValueError("TrainingSeedScheduler requires all 700 TRAIN seeds")
        self.seeds = list(seeds)
        self.experiment_seed = int(experiment_seed)
        self.rng = np.random.default_rng(self.experiment_seed)
        self.order: list[int] = []
        self.index = 0
        self.cycles = 0
        self._reshuffle()

    def _reshuffle(self) -> None:
        self.order = [int(value) for value in self.rng.permutation(self.seeds)]
        self.index = 0
        self.cycles += 1

    def next_seed(self) -> int:
        if self.index == len(self.order):
            self._reshuffle()
        seed = self.order[self.index]
        self.index += 1
        return seed

    def state_dict(self) -> dict[str, Any]:
        return {
            "schema": 1,
            "experiment_seed": self.experiment_seed,
            "seeds": self.seeds,
            "order": self.order,
            "index": self.index,
            "cycles": self.cycles,
            "rng_state": self.rng.bit_generator.state,
        }

    def load_state_dict(self, state: dict[str, Any]) -> None:
        if state.get("schema") != 1 or state.get("experiment_seed") != self.experiment_seed:
            raise ValueError("Seed scheduler state is incompatible")
        if state.get("seeds") != self.seeds or sorted(state.get("order", [])) != sorted(self.seeds):
            raise ValueError("Seed scheduler TRAIN pool differs")
        index = int(state.get("index", -1))
        if index < 0 or index > len(self.seeds):
            raise ValueError("Seed scheduler index is invalid")
        self.order = [int(value) for value in state["order"]]
        self.index = index
        self.cycles = int(state["cycles"])
        self.rng.bit_generator.state = state["rng_state"]

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.state_dict(), indent=2) + "\n", encoding="utf-8")

    def load(self, path: Path) -> None:
        self.load_state_dict(json.loads(path.read_text(encoding="utf-8")))
