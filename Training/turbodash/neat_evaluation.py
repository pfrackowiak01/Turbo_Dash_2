from __future__ import annotations

import csv
from collections import defaultdict, deque
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import neat

from .neat_policy import episode_fitness, select_discrete_action
from .worker import UnityWorker


EPISODE_FIELDS = (
    "generation", "genome_id", "episode_index", "seed", "fitness", "final_score",
    "life_loss_count", "survival_time", "episode_reward", "collisions", "obstacles_avoided",
    "max_level", "hearts_collected", "shields_collected", "boosts_collected",
    "gold_collected", "diamonds_collected", "turbo_activations", "terminal_reason",
    "terminated", "truncated", "decision_count", "python_reward_sum",
)


@dataclass
class ActiveEpisode:
    genome_id: int
    episode_index: int
    seed: int
    observation: Any
    decisions: int = 0
    reward_sum: float = 0.0


@dataclass(frozen=True)
class GenerationEvaluation:
    generation: int
    seed_pair: tuple[int, int]
    transitions: int
    champion_id: int
    champion_fitness: float
    champion: Any
    rows: tuple[dict[str, Any], ...]


class GenerationEvaluator:
    def __init__(self, workers: list[UnityWorker], episode_csv: Path):
        if not workers:
            raise ValueError("At least one Unity worker is required")
        self.workers = workers
        self.episode_csv = episode_csv

    def evaluate(self, genomes, config: neat.Config, seed_pair: tuple[int, int],
                 generation: int) -> GenerationEvaluation:
        if len(seed_pair) != 2 or seed_pair[0] == seed_pair[1]:
            raise ValueError("Every generation requires two distinct TRAIN seeds")
        ordered = sorted(genomes, key=lambda item: item[0])
        if not ordered:
            raise ValueError("Cannot evaluate an empty population")
        genome_by_id = dict(ordered)
        networks = {
            genome_id: neat.nn.FeedForwardNetwork.create(genome, config)
            for genome_id, genome in ordered
        }
        jobs = deque(
            (genome_id, episode_index, seed)
            for genome_id, _ in ordered
            for episode_index, seed in enumerate(seed_pair, start=1)
        )
        active: list[ActiveEpisode | None] = [None] * len(self.workers)
        rows: list[dict[str, Any]] = []
        scores: dict[int, list[float]] = defaultdict(list)
        transitions = 0

        def assign(worker_index: int) -> None:
            if not jobs:
                active[worker_index] = None
                return
            genome_id, episode_index, seed = jobs.popleft()
            observation = self.workers[worker_index].reset(seed)
            active[worker_index] = ActiveEpisode(genome_id, episode_index, seed, observation)

        for index in range(min(len(self.workers), len(jobs))):
            assign(index)
        while any(item is not None for item in active):
            indices = [index for index, item in enumerate(active) if item is not None]
            for index in indices:
                episode = active[index]
                outputs = networks[episode.genome_id].activate(episode.observation)
                self.workers[index].send_step(select_discrete_action(outputs))
            for index in indices:
                episode = active[index]
                result = self.workers[index].receive_step()
                episode.decisions += 1
                episode.reward_sum += float(result.reward)
                transitions += 1
                if result.terminated or result.truncated:
                    if int(result.info["seed"]) != episode.seed:
                        raise RuntimeError("Unity episode seed differs from the scheduled TRAIN seed")
                    if int(result.info["decision_count"]) != episode.decisions:
                        raise RuntimeError("Unity and Python decision counts differ")
                    fitness = episode_fitness(result.info["final_score"], result.info["life_loss_count"])
                    scores[episode.genome_id].append(fitness)
                    row = {field: result.info.get(field) for field in EPISODE_FIELDS}
                    row.update({
                        "generation": generation,
                        "genome_id": episode.genome_id,
                        "episode_index": episode.episode_index,
                        "seed": episode.seed,
                        "fitness": fitness,
                        "terminated": result.terminated,
                        "truncated": result.truncated,
                        "python_reward_sum": episode.reward_sum,
                    })
                    rows.append(row)
                    assign(index)
                else:
                    episode.observation = result.observation

        expected_episodes = len(ordered) * 2
        if len(rows) != expected_episodes or transitions < expected_episodes:
            raise RuntimeError("Generation evaluation did not complete exactly two episodes per genome")
        for genome_id, genome in ordered:
            values = scores[genome_id]
            if len(values) != 2:
                raise RuntimeError(f"Genome {genome_id} did not receive exactly two fitness samples")
            genome.fitness = float(sum(values) / 2.0)
        champion_id, champion = max(ordered, key=lambda item: item[1].fitness)
        self._append_rows(rows)
        return GenerationEvaluation(
            generation=generation,
            seed_pair=seed_pair,
            transitions=transitions,
            champion_id=champion_id,
            champion_fitness=float(champion.fitness),
            champion=deepcopy(champion),
            rows=tuple(rows),
        )

    def _append_rows(self, rows: list[dict[str, Any]]) -> None:
        self.episode_csv.parent.mkdir(parents=True, exist_ok=True)
        exists = self.episode_csv.exists()
        with self.episode_csv.open("a", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=EPISODE_FIELDS, extrasaction="ignore")
            if not exists:
                writer.writeheader()
            writer.writerows(rows)
