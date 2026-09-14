import csv
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from turbodash.neat_v2_summary import BUDGET_NAMES, METRIC_MAP, build_summary, write_csv


def metric(value):
    return {"mean": value, "median": value, "std": 0.0, "min": value, "max": value}


def validation(value, duration):
    result = {source: metric(value) for source in METRIC_MAP.values()}
    result.update({
        "episodes": 100,
        "action_space": "Discrete",
        "max_duration": duration,
        "terminal_distribution": {"MaxDuration": 25, "LivesExhausted": 75},
        "genome_sha256": "genome-hash",
        "config_sha256": "config-hash",
        "test_status": "UNUSED FOR TRAINING/TUNING/EVALUATION",
    })
    return result


class NeatV2SummaryTests(unittest.TestCase):
    def test_builds_three_run_three_budget_summary_from_synthetic_artifacts(self):
        specs = (("run-a", 1), ("run-b", 2), ("run-c", 3))
        topology = {
            "genome_id": 7, "species_id": 2, "enabled_connection_count": 70,
            "disabled_connection_count": 1, "genome_node_gene_count": 3,
            "total_node_count": 239, "hidden_node_count": 0, "input_count": 236,
            "output_count": 3, "feed_forward_layer_count": 1,
        }
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            validation_map = {"schema": 1, "selections": {}, "test_status": "UNUSED FOR TRAINING/TUNING/EVALUATION"}
            for run_index, (run_id, seed) in enumerate(specs, start=1):
                run_dir = root / run_id
                (run_dir / "milestones").mkdir(parents=True)
                with (run_dir / "generation_metrics.csv").open("w", newline="", encoding="utf-8") as stream:
                    writer = csv.DictWriter(stream, fieldnames=("generation", "species_count"))
                    writer.writeheader()
                    writer.writerows({"generation": generation, "species_count": 3 + generation % 3}
                                     for generation in range(1, 201))
                state_path = run_dir / "state.json"
                state_path.write_text(json.dumps({"checkpoint_metadata": {"current_champion_topology": topology}}), encoding="utf-8")
                for generation in (50, 100, 150, 200):
                    milestone = {
                        "cumulative_training_transitions": generation * 1000,
                        "elapsed_total_wall_seconds": generation * 10,
                        "elapsed_training_wall_seconds": generation * 8,
                        "species_count": 5, "genome_count": 64,
                        "generation_best_training_fitness": 4.2,
                        "current_champion_genome_id": 7,
                        "checkpoint_state": str(state_path),
                    }
                    (run_dir / "milestones" / f"generation-{generation:03d}.json").write_text(
                        json.dumps(milestone), encoding="utf-8"
                    )
                selections = {}
                for budget_index, budget in enumerate(BUDGET_NAMES, start=1):
                    archive = run_dir / f"archive-{budget_index}"
                    archive.mkdir()
                    summary_300 = archive / "summary.json"
                    summary_300.write_text(json.dumps(validation(run_index * 10 + budget_index, 300)), encoding="utf-8")
                    selection = {
                        "generation": budget_index * 10, "genome_id": 7 + budget_index,
                        "species_id": 2, "cumulative_training_transitions": budget_index * 1_000_000,
                        "elapsed_total_wall_seconds": budget_index * 1000,
                        "elapsed_training_wall_seconds": budget_index * 800,
                        "budget_limit": 5_000_000 if budget_index == 1 else 5_887,
                        "budget_basis": "synthetic", "topology": topology,
                        "summary_path": str(summary_300),
                        "summary_sha256": hashlib.sha256(summary_300.read_bytes()).hexdigest(),
                        "genome_sha256": "genome-hash",
                        "config_sha256": "config-hash",
                    }
                    selections[budget] = selection
                    summary_500 = root / f"{run_id}-{budget}.json"
                    summary_500.write_text(json.dumps(validation(run_index * 100 + budget_index, 500)), encoding="utf-8")
                    validation_map["selections"][f"{run_id}:{budget}"] = {
                        "summary_path": str(summary_500), "reused": budget_index == 2,
                        "deduplication_key": f"key-{run_index}-{budget_index}",
                    }
                manifest = {
                    "status": "complete", "algorithm": "NEAT Discrete v2",
                    "configuration": {"experiment_seed": seed},
                    "wallclock_match": {"seconds": 5887, "basis": "total_pipeline_wall_clock"},
                    "result": {
                        "generations_completed": 200, "cumulative_training_transitions": 9_000_000,
                        "elapsed_total_wall_seconds": 7000, "elapsed_training_wall_seconds": 5000,
                        "latest_checkpoint_state": str(state_path),
                        "best_validated_genome": {"genome_id": 10},
                        "budget_selections": selections,
                    },
                }
                (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            map_path = root / "validation-map.json"
            map_path.write_text(json.dumps(validation_map), encoding="utf-8")
            with patch("turbodash.neat_v2_summary.RUN_SPECS", specs):
                summary = build_summary(root, map_path)
            self.assertEqual(len(summary["runs"]), 3)
            self.assertEqual(summary["runs"][0]["final_species_count"], 5)
            self.assertEqual(summary["runs"][0]["budgets"]["best_wallclock_matched"]["validation_500_reused"], True)
            output = root / "summary.csv"
            write_csv(output, summary)
            with output.open(encoding="utf-8") as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 9)


if __name__ == "__main__":
    unittest.main()
