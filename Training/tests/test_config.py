import json
import unittest
from pathlib import Path


class ContinuousConfigTests(unittest.TestCase):
    def test_continuous_uses_frozen_ppo_pilot_v1_parameters(self):
        config_path = Path(__file__).resolve().parents[1] / "configs" / "ppo_continuous_v1.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        expected = {
            "algorithm": "PPO",
            "policy": "MlpPolicy",
            "learning_rate": 0.0003,
            "gamma": 0.9995,
            "gae_lambda": 0.95,
            "clip_range": 0.2,
            "ent_coef": 0.01,
            "vf_coef": 0.5,
            "max_grad_norm": 0.5,
            "n_steps": 1024,
            "batch_size": 512,
            "n_epochs": 10,
            "device": "cpu",
            "workers": 6,
            "time_scale": 20,
            "total_timesteps": 5_000_000,
            "checkpoint_interval": 250_000,
            "validation_interval": 500_000,
            "action_space": "Continuous",
        }
        for key, value in expected.items():
            self.assertEqual(config[key], value, key)
        self.assertEqual(config["policy_kwargs"]["net_arch"], {"pi": [256, 256], "vf": [256, 256]})
        self.assertEqual(config["policy_kwargs"]["activation_fn"], "Tanh")
        self.assertFalse(config["normalize_observation"])
        self.assertFalse(config["normalize_reward"])


if __name__ == "__main__":
    unittest.main()
