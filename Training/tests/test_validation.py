import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np

from turbodash.protocol import ActionSpace, StepResult
from turbodash.validation import METRICS, run_validation


class ValidationWorker:
    def __init__(self):
        self.actions = []
        self.seed = None

    def reset(self, seed):
        self.seed = seed
        return np.zeros(236, dtype=np.float32)

    def send_step(self, action):
        self.actions.append(action)

    def receive_step(self):
        info = {metric: 0 for metric in METRICS}
        info.update({"seed": self.seed, "terminal_reason": "MaxDuration", "decision_count": 1})
        return StepResult(np.zeros(236, dtype=np.float32), 0.0, False, True, info)

    def close(self):
        pass

    def terminate(self):
        pass


class ContinuousModel:
    def predict(self, observations, deterministic):
        assert deterministic
        return np.full((len(observations), 1), 1.5, dtype=np.float32), None


class ValidationTests(unittest.TestCase):
    @patch("turbodash.validation.start_workers")
    def test_continuous_validation_uses_box_actions_and_records_duration(self, start_workers_mock):
        workers = [ValidationWorker(), ValidationWorker()]
        start_workers_mock.return_value = workers
        with TemporaryDirectory() as temporary:
            summary = run_validation(
                ContinuousModel(), Path("unused-worker.exe"), list(range(1, 101)), Path(temporary),
                workers_count=2, time_scale=20, action_space=ActionSpace.CONTINUOUS, max_duration=500,
            )
        self.assertEqual(summary["episodes"], 100)
        self.assertEqual(summary["action_space"], "Continuous")
        self.assertEqual(summary["max_duration"], 500.0)
        self.assertEqual(summary["terminal_distribution"], {"MaxDuration": 100})
        self.assertTrue(all(isinstance(action, float) and action == 1.0
                            for worker in workers for action in worker.actions))
        start_workers_mock.assert_called_once_with(
            2, Path("unused-worker.exe"), unittest.mock.ANY, time_scale=20,
            max_duration=500, nographics=True, action_space=ActionSpace.CONTINUOUS,
        )


if __name__ == "__main__":
    unittest.main()
