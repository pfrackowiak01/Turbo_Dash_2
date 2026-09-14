import unittest

import numpy as np

from turbodash.neat_policy import NeatPolicy, episode_fitness, select_discrete_action
from turbodash.protocol import DiscreteAction


class FixedNetwork:
    def __init__(self, outputs):
        self.outputs = outputs

    def activate(self, observation):
        return self.outputs


class NeatPolicyTests(unittest.TestCase):
    def test_unique_argmax_maps_left_none_right(self):
        self.assertEqual(select_discrete_action((3, 2, 1)), DiscreteAction.LEFT)
        self.assertEqual(select_discrete_action((1, 3, 2)), DiscreteAction.NONE)
        self.assertEqual(select_discrete_action((1, 2, 3)), DiscreteAction.RIGHT)

    def test_every_exact_maximum_tie_maps_to_none(self):
        for outputs in ((1, 1, 0), (1, 0, 1), (0, 1, 1), (1, 1, 1)):
            self.assertEqual(select_discrete_action(outputs), DiscreteAction.NONE)

    def test_fitness_is_exact_protocol_formula(self):
        self.assertEqual(episode_fitness(275, 3), 1.25)

    def test_validation_adapter_returns_discrete_batch(self):
        policy = object.__new__(NeatPolicy)
        policy.network = FixedNetwork((0.0, 0.0, -1.0))
        actions, state = policy.predict(np.zeros((4, 236), dtype=np.float32), deterministic=True)
        np.testing.assert_array_equal(actions, np.ones(4, dtype=np.int64))
        self.assertIsNone(state)


if __name__ == "__main__":
    unittest.main()
