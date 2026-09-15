import csv
import math
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import neat
import numpy as np

from turbodash.neat_continuous_policy import NeatContinuousPolicy, select_continuous_action
from turbodash.neat_evaluation import GenerationEvaluator
from turbodash.neat_v2_summary import METRIC_MAP, validation_metrics, write_csv
from turbodash.neat_v2_train import experiment_profile, validate_neat_config, validate_pipeline_config
from turbodash.paths import TRAINING_ROOT
from turbodash.protocol import ActionSpace, StepResult


class Genome:
    def __init__(self, key, output):
        self.key = key
        self.output = output
        self.fitness = None


class Network:
    def __init__(self, output):
        self.output = output

    def activate(self, observation):
        return (self.output,)


class OneStepContinuousWorker:
    def __init__(self):
        self.seed = None
        self.actions = []

    def reset(self, seed):
        self.seed = seed
        return np.zeros(236, dtype=np.float32)

    def send_step(self, action):
        self.actions.append(action)

    def receive_step(self):
        action = self.actions[-1]
        return StepResult(
            np.zeros(236, dtype=np.float32), 0.0, False, True,
            {
                "seed": self.seed,
                "decision_count": 1,
                "final_score": (action + 1.0) * 100.0,
                "life_loss_count": 1,
                "terminal_reason": "MaxDuration",
            },
        )


class NeatContinuousTests(unittest.TestCase):
    def test_selector_requires_one_finite_output_and_clamps(self):
        self.assertEqual(select_continuous_action((-2.0,)), -1.0)
        self.assertEqual(select_continuous_action((0.25,)), 0.25)
        self.assertEqual(select_continuous_action((2.0,)), 1.0)
        for invalid in ((), (0.0, 1.0), (math.nan,), (math.inf,), (-math.inf,)):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                select_continuous_action(invalid)

    @patch("turbodash.neat_continuous_policy.neat.nn.FeedForwardNetwork.create")
    def test_policy_returns_float32_column_without_discretization(self, create_mock):
        create_mock.return_value = Network(-0.375)
        policy = NeatContinuousPolicy(object(), object())
        actions, state = policy.predict(np.zeros((2, 236), dtype=np.float32))
        self.assertIsNone(state)
        self.assertEqual(actions.shape, (2, 1))
        self.assertEqual(actions.dtype, np.float32)
        np.testing.assert_allclose(actions[:, 0], [-0.375, -0.375])

    @patch("turbodash.neat_evaluation.neat.nn.FeedForwardNetwork.create")
    def test_generation_evaluation_sends_continuous_float_actions(self, create_mock):
        genomes = [(7, Genome(7, -2.0)), (8, Genome(8, 0.25)), (9, Genome(9, 2.0))]
        create_mock.side_effect = lambda genome, config: Network(genome.output)
        workers = [OneStepContinuousWorker(), OneStepContinuousWorker()]
        with TemporaryDirectory() as temporary:
            result = GenerationEvaluator(
                workers, Path(temporary) / "episodes.csv",
                action_selector=select_continuous_action,
            ).evaluate(genomes, object(), (101, 202), 1)
        self.assertEqual(result.transitions, 6)
        self.assertEqual(result.champion_id, 9)
        actions = sorted(action for worker in workers for action in worker.actions)
        self.assertEqual(actions, [-1.0, -1.0, 0.25, 0.25, 1.0, 1.0])
        self.assertTrue(all(isinstance(action, float) for action in actions))

    def test_frozen_continuous_config_and_pipeline_profile(self):
        config = neat.Config(
            neat.DefaultGenome, neat.DefaultReproduction, neat.DefaultSpeciesSet,
            neat.DefaultStagnation,
            str(TRAINING_ROOT / "configs" / "neat_continuous_v1.ini"),
        )
        validate_neat_config(config, expected_outputs=1)
        pipeline = __import__("json").loads(
            (TRAINING_ROOT / "configs" / "neat_continuous_v1.json").read_text(encoding="utf-8")
        )
        validate_pipeline_config(pipeline, "training")
        profile = experiment_profile(pipeline)
        self.assertEqual(profile["action_space"], ActionSpace.CONTINUOUS)
        self.assertEqual(profile["output_count"], 1)
        self.assertEqual(profile["manifest_algorithm"], "NEAT Continuous v1")

    def test_continuous_summary_requires_analytics_marked_non_selective(self):
        metric = {"mean": 1.0, "median": 1.0, "std": 0.0, "min": 1.0, "max": 1.0}
        summary = {source: metric for source in METRIC_MAP.values()}
        summary.update({
            "episodes": 100,
            "action_space": "Continuous",
            "max_duration": 300,
            "terminal_distribution": {"MaxDuration": 100},
            "continuous_action": {
                "mean_abs_steering": 0.2,
                "mean_steering": 0.1,
                "steering_std": 0.3,
                "fraction_near_zero": 0.2,
                "fraction_near_max": 0.1,
                "fraction_left": 0.3,
                "fraction_right": 0.5,
                "role": "analytics_only_not_used_for_fitness_or_selection",
            },
            "episode_fitness": metric,
            "test_status": "UNUSED FOR TRAINING/TUNING/EVALUATION",
        })
        metrics = validation_metrics(summary, 300, "Continuous")
        self.assertEqual(metrics["continuous_action"]["mean_abs_steering"], 0.2)

    def test_synthetic_continuous_summary_csv_contains_action_metrics(self):
        metric = {"mean": 1.0, "median": 1.0, "std": 0.0, "min": 1.0, "max": 1.0}
        validation = {public: metric for public in METRIC_MAP}
        validation.update({
            "episodeFitness": metric,
            "terminal_distribution": {"MaxDuration": 100},
            "continuous_action": {
                "mean_abs_steering": 0.2, "mean_steering": 0.1, "steering_std": 0.3,
                "fraction_near_zero": 0.2, "fraction_near_max": 0.1,
                "fraction_left": 0.3, "fraction_right": 0.5,
            },
        })
        topology = {
            "enabled_connection_count": 24, "disabled_connection_count": 0,
            "total_node_count": 237, "hidden_node_count": 0, "input_count": 236,
            "output_count": 1, "feed_forward_layer_count": 1,
        }
        milestone = {
            "cumulative_training_transitions": 1, "elapsed_total_wall_seconds": 2,
            "elapsed_training_wall_seconds": 1, "species_count": 3,
            "best_training_fitness": 1.0,
        }
        budget = {
            "selected_generation": 1, "selected_genome_id": 7, "selected_species_id": 2,
            "train_transitions_at_selection": 10, "elapsed_total_wall_seconds_at_selection": 2,
            "elapsed_training_wall_seconds_at_selection": 1, "validation_500_reused": False,
            "topology": topology, "validation_300": validation, "validation_500": validation,
        }
        summary = {"runs": [{
            "run_id": "synthetic", "experiment_seed": 1, "generations_completed": 200,
            "total_train_transitions": 10, "total_wall_clock_seconds": 2,
            "training_only_wall_clock_seconds": 1, "species_count_min": 2,
            "species_count_mean": 3, "species_count_max": 4, "final_species_count": 3,
            "best_validated_genome_id": 7,
            "milestone_checkpoints": {str(value): milestone for value in (50, 100, 150, 200)},
            "budgets": {"best_200_generations": budget},
        }]}
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "summary.csv"
            write_csv(path, summary)
            with path.open(encoding="utf-8") as stream:
                row = next(csv.DictReader(stream))
        self.assertEqual(row["output_count"], "1")
        self.assertEqual(row["validation_500_episodeFitness_mean"], "1.0")
        self.assertEqual(row["validation_500_mean_abs_steering"], "0.2")


if __name__ == "__main__":
    unittest.main()
