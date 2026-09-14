import unittest

import numpy as np
from gymnasium import spaces

from turbodash.protocol import ActionSpace, StepResult
from turbodash.seeds import TrainingSeedScheduler
from turbodash.vec_env import TurboDashVecEnv


class MockWorker:
    def __init__(self, action_space=ActionSpace.DISCRETE):
        self.seeds = []
        self.action = None
        self.action_space = action_space
        self.handshake = None

    def reset(self, seed):
        self.seeds.append(seed)
        return np.full(236, len(self.seeds), dtype=np.float32)

    def send_step(self, action):
        self.action = action

    def receive_step(self):
        return StepResult(np.full(236, 9, dtype=np.float32), 1.25, False, True, {
            "seed": self.seeds[-1], "terminal_reason": "MaxDuration", "episode_reward": 1.25,
        })

    def close(self):
        pass

    def terminate(self):
        pass


class VecEnvTests(unittest.TestCase):
    def test_terminal_observation_time_limit_and_train_autoreset(self):
        seeds = list(range(1, 701))
        reference = TrainingSeedScheduler(seeds, 99)
        expected_first, expected_second = reference.next_seed(), reference.next_seed()
        worker = MockWorker()
        env = TurboDashVecEnv([worker], TrainingSeedScheduler(seeds, 99))
        initial = env.reset()
        observation, reward, done, infos = env.step(np.array([1]))
        self.assertEqual(worker.seeds, [expected_first, expected_second])
        self.assertEqual(initial.dtype, np.float32)
        self.assertEqual(initial.shape, (1, 236))
        self.assertTrue(done[0])
        self.assertTrue(infos[0]["TimeLimit.truncated"])
        np.testing.assert_array_equal(infos[0]["terminal_observation"], np.full(236, 9, dtype=np.float32))
        np.testing.assert_array_equal(observation[0], np.full(236, 2, dtype=np.float32))

    def test_continuous_box_shape_dtype_and_clamping(self):
        seeds = list(range(1, 701))
        worker = MockWorker(ActionSpace.CONTINUOUS)
        env = TurboDashVecEnv([worker], TrainingSeedScheduler(seeds, 99))
        try:
            self.assertIsInstance(env.action_space, spaces.Box)
            self.assertEqual(env.action_space.shape, (1,))
            self.assertEqual(env.action_space.dtype, np.dtype(np.float32))
            np.testing.assert_array_equal(env.action_space.low, np.array([-1.0], dtype=np.float32))
            np.testing.assert_array_equal(env.action_space.high, np.array([1.0], dtype=np.float32))
            env.reset()
            env.step(np.array([[1.75]], dtype=np.float32))
            self.assertEqual(worker.action, 1.0)
        finally:
            env.close()

    def test_mixed_worker_action_spaces_are_rejected(self):
        seeds = list(range(1, 701))
        with self.assertRaises(ValueError):
            TurboDashVecEnv(
                [MockWorker(ActionSpace.DISCRETE), MockWorker(ActionSpace.CONTINUOUS)],
                TrainingSeedScheduler(seeds, 99),
            )


if __name__ == "__main__":
    unittest.main()
