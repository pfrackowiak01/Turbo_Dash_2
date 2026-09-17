import csv
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from turbodash.final_rule_based import RuleBasedV1Parameters, RuleBasedV1Policy
from turbodash.final_test_analysis import analyze_final_test, holm_adjust
from turbodash.final_test_runner import RAW_FIELDS, key, make_schedule, remaining_jobs
from turbodash.protocol import DiscreteAction


class FinalRuleBasedTests(unittest.TestCase):
    def test_frozen_parameters_match_csharp_defaults(self):
        self.assertEqual(
            tuple(RuleBasedV1Parameters().__dict__.values()),
            (14.0, 11.0, 3.0, 1.5, 0.45, 0.2, 0.45, 1.15, 2.5,
             7.0, 4.0, 2.0, 0.22, 0.8, 0.45),
        )

    def test_empty_observation_stays_and_central_hazard_steers_right(self):
        policy = RuleBasedV1Policy()
        empty = np.zeros(236, dtype=np.float32)
        policy.reset_slot(0)
        self.assertEqual(policy.decide(empty, 0), int(DiscreteAction.NONE))

        hazard = empty.copy()
        tube = policy.tube_offset(0)
        hazard[tube + policy.TUBE_EXISTS] = 1.0
        hazard[policy.hazard_offset(0, 6) + policy.WALL_OCCUPANCY] = 1.0
        policy.reset_slot(0)
        self.assertEqual(policy.decide(hazard, 0), int(DiscreteAction.RIGHT))

    def test_worker_slots_have_independent_episode_state(self):
        policy = RuleBasedV1Policy()
        observations = np.zeros((2, 236), dtype=np.float32)
        for slot in (0, 1):
            policy.reset_slot(slot)
        actions = policy.predict_slots(observations, [0, 1])
        np.testing.assert_array_equal(actions, [DiscreteAction.NONE, DiscreteAction.NONE])


class FinalProtocolTests(unittest.TestCase):
    def test_schedule_is_complete_deterministic_and_reused(self):
        protocol = {"repetitions": 3, "schedule_random_seed": 20260930}
        seeds = list(range(1001, 1201))
        first = make_schedule(seeds, protocol)
        second = make_schedule(seeds, protocol)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 600)
        self.assertEqual(len({(row["seed"], row["repetition"]) for row in first}), 600)

    def test_resume_filters_only_completed_unique_keys(self):
        protocol = {"repetitions": 3, "schedule_random_seed": 20260930}
        schedule = make_schedule(list(range(1001, 1201)), protocol)
        completed = {key("PPO-D", schedule[0]["seed"], schedule[0]["repetition"]),
                     key("PPO-D", schedule[17]["seed"], schedule[17]["repetition"])}
        remaining = remaining_jobs("PPO-D", schedule, completed)
        self.assertEqual(len(remaining), 598)
        self.assertEqual(remaining, [job for index, job in enumerate(schedule) if index not in (0, 17)])

    def test_holm_adjustment_is_monotone_in_sorted_p_values(self):
        raw = [0.04, 0.001, 0.02, 0.6]
        adjusted = holm_adjust(raw)
        ordered = sorted(zip(raw, adjusted))
        self.assertEqual([value for _, value in ordered], sorted(value for _, value in ordered))
        self.assertTrue(all(raw_value <= adjusted_value <= 1 for raw_value, adjusted_value in zip(raw, adjusted)))

    def test_synthetic_analysis_writes_prespecified_outputs(self):
        methods = ("RuleBasedV1", "PPO-D", "PPO-C", "NEAT-D", "NEAT-C")
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw = root / "episodes_raw.csv"
            with raw.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=RAW_FIELDS)
                writer.writeheader()
                for method_index, method in enumerate(methods):
                    continuous = method in ("PPO-C", "NEAT-C")
                    for seed in range(1, 9):
                        for repetition in range(1, 4):
                            row = {name: "" for name in RAW_FIELDS}
                            score = method_index * 1000 + seed * 10 + repetition
                            row.update({
                                "method": method, "action_space": "Continuous" if continuous else "Discrete",
                                "seed": seed, "repetition": repetition, "schedule_index": seed * 3 + repetition,
                                "worker_id": 0, "retry_count": 0, "episode_id": seed,
                                "decision_count": 20, "final_score": score, "survival_time": 100 + method_index,
                                "segments_passed": 5, "obstacles_encountered": 4, "obstacles_avoided": 3,
                                "collisions": 2, "life_loss_count": 1, "shield_hits": 0,
                                "fatal_collision": True, "hearts_collected": 1, "shields_collected": 1,
                                "boosts_collected": 1, "turbo_activations": 1, "gold_collected": 2,
                                "diamonds_collected": 1, "max_level": 3, "outside_stages_reached": 1,
                                "time_inside": 80, "time_outside": 20, "max_environment_speed": 15,
                                "episode_reward": score / 100, "terminal_reason": "LivesExhausted",
                                "terminated": True, "truncated": False, "physics_ticks": 10000,
                                "action_change_count": 4, "action_change_rate": 4 / 19,
                                "completed_utc": "synthetic",
                            })
                            if continuous:
                                row.update({"continuous_mean": 0.1, "continuous_mean_abs": 0.2,
                                            "continuous_std": 0.3, "continuous_near_zero_rate": 0.2,
                                            "continuous_near_max_rate": 0.1, "continuous_left_rate": 0.3,
                                            "continuous_right_rate": 0.4,
                                            "mean_abs_delta_steering": 0.05,
                                            "steering_sign_change_rate": 0.1,
                                            "continuous_bin_counts": json.dumps([0] * 19 + [10, 10] + [0] * 19)})
                            else:
                                row.update({"discrete_left_count": 5, "discrete_none_count": 10,
                                            "discrete_right_count": 5, "discrete_left_rate": .25,
                                            "discrete_none_rate": .5, "discrete_right_rate": .25})
                            writer.writerow(row)
            protocol = {
                "repetitions": 3, "max_duration": 500, "bootstrap_random_seed": 9,
                "bootstrap_resamples": 200, "primary_metric": "finalScore",
            }
            selection = {"methods": [{"method": method, "validation_500_mean_final_score": None}
                                       for method in methods]}
            summary = analyze_final_test(raw, root, protocol, selection, strict=False, write_plots=True)
            self.assertEqual(summary["valid_episodes"], 120)
            self.assertEqual(summary["test_seeds"], 8)
            for name in ("final_test_per_seed.csv", "final_test_method_summary.csv",
                         "final_test_pairwise_statistics.csv", "analysis/final_test_omnibus.json",
                         "final_test_action_analytics.csv", "final_test_strategy_metrics.csv",
                         "analysis/survival_summary.csv", "analysis/nondeterminism_summary.csv",
                         "final_test_generalization.csv", "analysis/test_seed_difficulty.csv",
                         "analysis/failure_overlap.csv", "final_test_results.json",
                         "FINAL_TEST_REPORT.md"):
                self.assertTrue((root / name).is_file(), name)
            self.assertGreaterEqual(len(list((root / "plots").glob("*.png"))), 15)


if __name__ == "__main__":
    unittest.main()
