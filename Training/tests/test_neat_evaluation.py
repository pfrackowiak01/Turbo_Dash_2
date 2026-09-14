import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np

from turbodash.neat_evaluation import GenerationEvaluator
from turbodash.protocol import StepResult


class Genome:
    def __init__(self, key, outputs):
        self.key = key
        self.outputs = outputs
        self.fitness = None


class Network:
    def __init__(self, outputs):
        self.outputs = outputs

    def activate(self, observation):
        return self.outputs


class OneStepWorker:
    def __init__(self):
        self.seed = None
        self.action = None
        self.seeds = []
        self.actions = []

    def reset(self, seed):
        self.seed = seed
        self.seeds.append(seed)
        return np.zeros(236, dtype=np.float32)

    def send_step(self, action):
        self.action = action
        self.actions.append(action)

    def receive_step(self):
        info = {
            "seed": self.seed,
            "decision_count": 1,
            "final_score": (self.action + 1) * 100,
            "life_loss_count": 1,
            "terminal_reason": "MaxDuration",
        }
        return StepResult(np.zeros(236, dtype=np.float32), 0.0, False, True, info)


class NeatEvaluationTests(unittest.TestCase):
    @patch("turbodash.neat_evaluation.neat.nn.FeedForwardNetwork.create")
    def test_two_common_seeds_fitness_transition_count_and_tie_rule(self, create_mock):
        genomes = [
            (7, Genome(7, (2.0, 1.0, 0.0))),
            (8, Genome(8, (1.0, 1.0, 0.0))),
            (9, Genome(9, (0.0, 1.0, 2.0))),
        ]
        create_mock.side_effect = lambda genome, config: Network(genome.outputs)
        workers = [OneStepWorker(), OneStepWorker()]
        with TemporaryDirectory() as temporary:
            result = GenerationEvaluator(workers, Path(temporary) / "episodes.csv").evaluate(
                genomes, object(), (101, 202), 1
            )
        self.assertEqual(result.transitions, 6)
        self.assertEqual(result.champion_id, 9)
        self.assertEqual(result.champion_fitness, 2.5)
        self.assertEqual(genomes[0][1].fitness, 0.5)
        self.assertEqual(genomes[1][1].fitness, 1.5)
        self.assertEqual(genomes[2][1].fitness, 2.5)
        for genome_id in (7, 8, 9):
            self.assertEqual(
                sorted(int(row["seed"]) for row in result.rows if int(row["genome_id"]) == genome_id),
                [101, 202],
            )
        self.assertEqual(sorted(action for worker in workers for action in worker.actions), [0, 0, 1, 1, 2, 2])


if __name__ == "__main__":
    unittest.main()
