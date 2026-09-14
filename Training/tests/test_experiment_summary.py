import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from turbodash.experiment_summary import REPORTED_METRICS, RUN_SPECS, build_experiment_summary, write_csv


def metric(value):
    return {"mean": value, "median": value, "std": 0.0, "min": value, "max": value}


def validation_summary(score, max_duration):
    result = {
        "episodes": 100,
        "action_space": "Continuous",
        "max_duration": float(max_duration),
        "test_status": "UNUSED FOR TRAINING/TUNING/EVALUATION",
        "final_score": metric(score),
        "survival_time": metric(max_duration),
        "terminal_distribution": {"MaxDuration": 75, "LivesExhausted": 25},
    }
    for source_name in REPORTED_METRICS.values():
        result[source_name] = metric(2.0)
    return result


class ExperimentSummaryTests(unittest.TestCase):
    def test_builds_json_data_and_csv_and_selects_by_500_second_score(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index, (run_id, seed, validation_id) in enumerate(RUN_SPECS, start=1):
                run_dir = root / run_id
                (run_dir / "best_model").mkdir(parents=True)
                (run_dir / "best_model" / "model.zip").write_bytes(b"model")
                (run_dir / "checkpoints").mkdir()
                source_checkpoint = run_dir / "checkpoints" / f"ppo_{index * 500_000}.zip"
                source_checkpoint.write_bytes(b"model")
                (run_dir / "manifest.json").write_text(json.dumps({
                    "status": "complete",
                    "configuration": {
                        "action_space": "Continuous",
                        "experiment_seed": seed,
                        "total_timesteps": 5_000_000,
                    },
                }), encoding="utf-8")
                (run_dir / "best_model" / "selection.json").write_text(json.dumps({
                    "checkpoint_timestep": index * 500_000,
                    "source_checkpoint": str(source_checkpoint),
                    "summary": validation_summary(100 + index, 300),
                }), encoding="utf-8")
                validation_dir = root / validation_id / "validation" / "all-100"
                validation_dir.mkdir(parents=True)
                summary_500 = validation_summary(200 + index, 500)
                summary_500["model_sha256"] = hashlib.sha256(b"model").hexdigest()
                (validation_dir / "summary.json").write_text(
                    json.dumps(summary_500), encoding="utf-8"
                )
            summary = build_experiment_summary(root, 123.5)
            self.assertEqual(summary["best_ppo_continuous_run"], RUN_SPECS[-1][0])
            self.assertEqual(summary["runs"][0]["validation_300"]["MaxDuration_count"], 75)
            self.assertEqual(summary["runs"][0]["validation_500"]["LivesExhausted_count"], 25)
            self.assertEqual(summary["test_status"], "UNUSED FOR TRAINING/TUNING/EVALUATION")
            csv_path = root / "summary.csv"
            write_csv(csv_path, summary)
            with csv_path.open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[0]["validation_500_collisions_total"], "200")


if __name__ == "__main__":
    unittest.main()
