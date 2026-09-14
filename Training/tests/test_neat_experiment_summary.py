import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from turbodash.neat_experiment_summary import build_experiment_summary, write_csv
from turbodash.seeds import file_sha256
from turbodash.validation import METRICS


def metric(value):
    return {"mean": value, "median": value, "std": 0.0, "min": value, "max": value}


def validation_summary(score, duration):
    result = {name: metric(float(score if name == "final_score" else 1)) for name in METRICS}
    result.update({
        "episodes": 100,
        "algorithm": "NEAT",
        "action_space": "Discrete",
        "max_duration": float(duration),
        "terminal_distribution": {"MaxDuration": 100},
        "test_status": "UNUSED FOR TRAINING/TUNING/EVALUATION",
    })
    return result


class NeatExperimentSummaryTests(unittest.TestCase):
    def test_selects_only_by_500_second_mean_score_and_writes_csv(self):
        specs = (("run-a", 11, "val-a"), ("run-b", 12, "val-b"), ("run-c", 13, "val-c"))
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index, (run_id, seed, validation_id) in enumerate(specs, start=1):
                best = root / run_id / "best_model"
                best.mkdir(parents=True)
                genome = best / "genome.pkl"
                config = best / "config.ini"
                genome.write_bytes(f"genome-{index}".encode())
                config.write_text(f"config-{index}", encoding="utf-8")
                summary_300 = validation_summary(100 - index, 300)
                selection = {
                    "generation": index,
                    "genome_sha256": file_sha256(genome),
                    "config_sha256": file_sha256(config),
                    "summary": summary_300,
                }
                (best / "selection.json").write_text(json.dumps(selection), encoding="utf-8")
                manifest = {
                    "status": "complete",
                    "algorithm": "NEAT Discrete",
                    "configuration": {
                        "action_space": "Discrete", "experiment_seed": seed,
                        "target_transitions": 5_000_000,
                    },
                    "result": {"cumulative_training_transitions": 5_000_123},
                }
                (root / run_id / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
                validation_dir = root / validation_id / "validation" / "all-100"
                validation_dir.mkdir(parents=True)
                summary_500 = validation_summary(index * 10, 500)
                summary_500["genome_sha256"] = file_sha256(genome)
                summary_500["config_sha256"] = file_sha256(config)
                (validation_dir / "summary.json").write_text(json.dumps(summary_500), encoding="utf-8")
            with patch("turbodash.neat_experiment_summary.RUN_SPECS", specs):
                result = build_experiment_summary(root, 42.5)
            self.assertEqual(result["best_neat_discrete_run"], "run-c")
            self.assertEqual(result["best_mean_finalScore_500"], 30)
            csv_path = root / "summary.csv"
            write_csv(csv_path, result)
            text = csv_path.read_text(encoding="utf-8")
            self.assertIn("validation_500_lifeLossCount_total", text)
            self.assertIn("validation_500_maxLevel_max", text)


if __name__ == "__main__":
    unittest.main()
