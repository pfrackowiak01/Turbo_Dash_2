import unittest

import neat

from turbodash.neat_topology import genome_topology
from turbodash.neat_v2_selection import select_budget_records
from turbodash.neat_v2_train import validate_neat_config
from turbodash.paths import TRAINING_ROOT


class NeatV2Tests(unittest.TestCase):
    def test_v1_is_historical_and_v2_changes_only_speciation_start(self):
        def load(name):
            return neat.Config(
                neat.DefaultGenome, neat.DefaultReproduction, neat.DefaultSpeciesSet,
                neat.DefaultStagnation, str(TRAINING_ROOT / "configs" / name),
            )

        v1 = load("neat_discrete_v1.ini")
        v2 = load("neat_discrete_v2.ini")
        self.assertEqual(v1.genome_config.initial_connection, "full_direct")
        self.assertEqual(v1.species_set_config.compatibility_threshold, 3.0)
        self.assertEqual(v2.genome_config.initial_connection, "partial_direct")
        self.assertEqual(v2.genome_config.connection_fraction, 0.10)
        self.assertEqual(v2.species_set_config.compatibility_threshold, 2.5)
        for name in (
            "node_add_prob", "node_delete_prob", "conn_add_prob", "conn_delete_prob",
            "weight_mutate_power", "weight_mutate_rate", "weight_replace_rate",
        ):
            self.assertEqual(getattr(v1.genome_config, name), getattr(v2.genome_config, name))
        validate_neat_config(v2)

    def test_topology_metrics_include_inputs_outputs_connections_and_layers(self):
        config = neat.Config(
            neat.DefaultGenome, neat.DefaultReproduction, neat.DefaultSpeciesSet,
            neat.DefaultStagnation, str(TRAINING_ROOT / "configs" / "neat_discrete_v2.ini"),
        )
        population = neat.Population(config, seed=20260922)
        genome = next(iter(population.population.values()))
        topology = genome_topology(genome, config, species_id=1)
        self.assertEqual(topology["input_count"], 236)
        self.assertEqual(topology["output_count"], 3)
        self.assertEqual(topology["enabled_connection_count"], 71)
        self.assertEqual(topology["hidden_node_count"], 0)
        self.assertEqual(topology["total_node_count"], 239)
        self.assertGreaterEqual(topology["feed_forward_layer_count"], 1)

    def test_budget_selection_uses_completed_generation_boundary_and_validation_score(self):
        records = [
            {"generation": 1, "cumulative_training_transitions": 400_000,
             "elapsed_total_wall_seconds": 100, "validation_mean_final_score": 1},
            {"generation": 50, "cumulative_training_transitions": 4_800_000,
             "elapsed_total_wall_seconds": 5_900, "validation_mean_final_score": 10},
            {"generation": 51, "cumulative_training_transitions": 5_050_000,
             "elapsed_total_wall_seconds": 5_500, "validation_mean_final_score": 9},
            {"generation": 100, "cumulative_training_transitions": 9_000_000,
             "elapsed_total_wall_seconds": 8_000, "validation_mean_final_score": 20},
        ]
        selected = select_budget_records(records, interaction_transitions=5_000_000, wallclock_seconds=5_887)
        self.assertEqual(selected["best_interaction_matched"]["generation"], 50)
        self.assertEqual(selected["best_interaction_matched"]["effective_completed_generation_cutoff"], 5_050_000)
        self.assertEqual(selected["best_wallclock_matched"]["generation"], 51)
        self.assertEqual(selected["best_200_generations"]["generation"], 100)


if __name__ == "__main__":
    unittest.main()
