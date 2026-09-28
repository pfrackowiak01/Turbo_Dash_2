import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from export_review_runs import MAIN_RUNS, export, include, sha256


class ReviewExportTests(unittest.TestCase):
    def test_all_fifteen_runs_include_metrics_and_models(self):
        self.assertEqual(len(MAIN_RUNS), 15)
        for run in MAIN_RUNS:
            for name in ("config.json", "manifest.json", "generation_metrics.csv",
                         "training_episodes.csv", "best_model/genome.pkl",
                         "validation/gen-001/episodes.csv", "validation_archive/gen-001/record.json",
                         "selected_models/best_200_generations/genome.pkl", "milestones/generation-050.json"):
                self.assertTrue(include(Path(run) / name), (run, name))

    def test_exclusions_and_frozen_checkpoint_exceptions(self):
        run = "ppo-discrete-5m-run3"
        self.assertTrue(include(Path(run) / "checkpoints/ppo_3000000.zip"))
        for name in ("checkpoints/ppo_5000000.zip", "worker_logs/worker.json",
                     "validation/step-1/unity_episode_csv/worker.csv", "test.json",
                     "training_sessions/session1/config.json"):
            self.assertFalse(include(Path(run) / name), name)
        self.assertFalse(include(Path("ppo-smoke-100k-final/config.json")))
        self.assertFalse(include(Path("new-unreviewed-run/manifest.json")))

    def test_tensorboard_and_support_artifacts(self):
        self.assertTrue(include(Path("ppo-continuous-5m-run1/tensorboard/PPO_1/events.out.tfevents.123")))
        self.assertFalse(include(Path("ppo-continuous-5m-run1/tensorboard/debug.log")))
        for name in ("ppo-run3-best-validation-500/validation/all-100/episodes.csv",
                     "neat-discrete-v2-speciation-pilot/speciation-pilot.csv",
                     "neat-continuous-v1-experiment-summary.json"):
            self.assertTrue(include(Path(name)), name)

    def test_verified_copy_is_byte_exact_and_never_overwrites(self):
        with TemporaryDirectory() as tmp:
            source, destination = Path(tmp) / "original", Path(tmp) / "review"
            source.mkdir()
            artifact = source / "episodes.csv"
            original = b"score\r\n0\r\n999\r\n"
            artifact.write_bytes(original)
            report = {"copied_bytes": len(original), "source_bytes": len(original)}
            with patch("export_review_runs.plan", return_value=([artifact], report)):
                result = export(source, destination)
            self.assertEqual(result["verification"], "PASS")
            self.assertEqual(artifact.read_bytes(), original)
            self.assertEqual((destination / "episodes.csv").read_bytes(), original)
            saved = json.loads((destination / "review_export_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["files"][0]["sha256"], sha256(artifact))
            with self.assertRaises(FileExistsError):
                export(source, destination)

    def test_overlapping_paths_are_rejected(self):
        with TemporaryDirectory() as tmp:
            source = Path(tmp)
            for target in (source, source / "nested", source.parent):
                with self.assertRaises(ValueError):
                    export(source, target)

    def test_corrupt_copy_is_not_reported_as_success(self):
        with TemporaryDirectory() as tmp:
            source, destination = Path(tmp) / "original", Path(tmp) / "review"
            source.mkdir()
            artifact = source / "config.json"
            artifact.write_bytes(b"original")
            with patch("export_review_runs.plan", return_value=([artifact], {})), \
                 patch("export_review_runs.shutil.copy2", side_effect=lambda src, dst: dst.write_bytes(b"bad")):
                with self.assertRaises(ValueError):
                    export(source, destination)
            self.assertFalse((destination / "review_export_manifest.json").exists())
            self.assertEqual(artifact.read_bytes(), b"original")


if __name__ == "__main__":
    unittest.main()
