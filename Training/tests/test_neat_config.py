import unittest

import neat

from turbodash.paths import TRAINING_ROOT


class NeatConfigTests(unittest.TestCase):
    def test_frozen_topology_and_evolution_parameters(self):
        config = neat.Config(
            neat.DefaultGenome, neat.DefaultReproduction, neat.DefaultSpeciesSet,
            neat.DefaultStagnation, str(TRAINING_ROOT / "configs" / "neat_discrete_v1.ini"),
        )
        genome = config.genome_config
        self.assertEqual((genome.num_inputs, genome.num_outputs), (236, 3))
        self.assertTrue(genome.feed_forward)
        self.assertEqual(genome.initial_connection, "full_direct")
        self.assertEqual(genome.activation_default, "tanh")
        self.assertEqual(genome.aggregation_default, "sum")
        self.assertEqual(config.pop_size, 64)
        self.assertEqual(config.reproduction_config.elitism, 2)
        self.assertEqual(config.reproduction_config.survival_threshold, 0.20)
        self.assertEqual(config.species_set_config.compatibility_threshold, 3.0)
        self.assertEqual(genome.node_add_prob, 0.05)
        self.assertEqual(genome.node_delete_prob, 0.02)
        self.assertEqual(genome.conn_add_prob, 0.20)
        self.assertEqual(genome.conn_delete_prob, 0.10)
        self.assertEqual(genome.weight_mutate_power, 0.5)
        self.assertEqual(genome.weight_mutate_rate, 0.5)
        self.assertEqual(genome.weight_replace_rate, 0.05)


if __name__ == "__main__":
    unittest.main()
