from __future__ import annotations

import time
from typing import Any

import gymnasium as gym
import numpy as np
from stable_baselines3.common.vec_env import VecEnv

from .protocol import OBSERVATION_SIZE
from .seeds import TrainingSeedScheduler
from .worker import UnityWorker


class TurboDashVecEnv(VecEnv):
    """SB3 VecEnv over already-independent Unity worker processes."""

    def __init__(self, workers: list[UnityWorker], scheduler: TrainingSeedScheduler):
        if not workers:
            raise ValueError("At least one Unity worker is required")
        self.workers = workers
        self.scheduler = scheduler
        self._actions: np.ndarray | None = None
        self._episode_returns = np.zeros(len(workers), dtype=np.float64)
        self._episode_lengths = np.zeros(len(workers), dtype=np.int64)
        self._episode_started = np.zeros(len(workers), dtype=np.float64)
        observation_space = gym.spaces.Box(low=-1.0, high=1.0, shape=(OBSERVATION_SIZE,), dtype=np.float32)
        action_space = gym.spaces.Discrete(3)
        super().__init__(len(workers), observation_space, action_space)

    def reset(self) -> np.ndarray:
        observations = []
        self.reset_infos = []
        for index, worker in enumerate(self.workers):
            seed = self.scheduler.next_seed()
            observations.append(worker.reset(seed))
            self.reset_infos.append({"seed": seed})
            self._episode_returns[index] = 0
            self._episode_lengths[index] = 0
            self._episode_started[index] = time.perf_counter()
        return np.stack(observations).astype(np.float32, copy=False)

    def step_async(self, actions: np.ndarray) -> None:
        actions = np.asarray(actions).reshape(self.num_envs)
        if self._actions is not None:
            raise RuntimeError("step_async called twice")
        self._actions = actions.copy()
        sent = 0
        try:
            for worker, action in zip(self.workers, self._actions):
                worker.send_step(int(action))
                sent += 1
        except Exception:
            for worker in self.workers[:sent]:
                worker.terminate()
            raise

    def step_wait(self):
        if self._actions is None:
            raise RuntimeError("step_wait called without step_async")
        observations: list[np.ndarray] = []
        rewards = np.empty(self.num_envs, dtype=np.float32)
        dones = np.empty(self.num_envs, dtype=bool)
        infos: list[dict[str, Any]] = []
        try:
            for index, worker in enumerate(self.workers):
                result = worker.receive_step()
                rewards[index] = result.reward
                done = result.terminated or result.truncated
                dones[index] = done
                self._episode_returns[index] += result.reward
                self._episode_lengths[index] += 1
                info = dict(result.info)
                info["terminated"] = result.terminated
                info["truncated"] = result.truncated
                if result.truncated:
                    info["TimeLimit.truncated"] = True
                if done:
                    info["terminal_observation"] = result.observation.copy()
                    info["episode"] = {
                        "r": float(self._episode_returns[index]),
                        "l": int(self._episode_lengths[index]),
                        "t": time.perf_counter() - self._episode_started[index],
                    }
                    next_seed = self.scheduler.next_seed()
                    observations.append(worker.reset(next_seed))
                    self.reset_infos[index] = {"seed": next_seed}
                    self._episode_returns[index] = 0
                    self._episode_lengths[index] = 0
                    self._episode_started[index] = time.perf_counter()
                else:
                    observations.append(result.observation)
                infos.append(info)
        finally:
            self._actions = None
        stacked = np.stack(observations).astype(np.float32, copy=False)
        if not np.isfinite(stacked).all() or not np.isfinite(rewards).all():
            raise FloatingPointError("Unity returned NaN or Infinity")
        return stacked, rewards, dones, infos

    def close(self) -> None:
        first_error: Exception | None = None
        for worker in self.workers:
            try:
                worker.close()
            except Exception as exc:
                first_error = first_error or exc
                worker.terminate()
        if first_error:
            raise first_error

    def get_attr(self, attr_name: str, indices=None):
        selected = self._get_indices(indices)
        if attr_name == "render_mode":
            return [None for _ in selected]
        return [getattr(self.workers[index], attr_name) for index in selected]

    def set_attr(self, attr_name: str, value: Any, indices=None) -> None:
        selected = self._get_indices(indices)
        for index in selected:
            setattr(self.workers[index], attr_name, value)

    def env_method(self, method_name: str, *method_args, indices=None, **method_kwargs):
        selected = self._get_indices(indices)
        return [getattr(self.workers[index], method_name)(*method_args, **method_kwargs) for index in selected]

    def env_is_wrapped(self, wrapper_class, indices=None):
        return [False for _ in self._get_indices(indices)]

    def get_images(self):
        return [None] * self.num_envs
