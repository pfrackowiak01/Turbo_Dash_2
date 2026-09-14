import json
import random
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import neat

from turbodash.neat_checkpoint import restore_population_exact, save_pipeline_checkpoint
from turbodash.paths import SEED_ROOT, TRAINING_ROOT
from turbodash.seeds import TrainingSeedScheduler, load_seed_split


class NeatCheckpointTests(unittest.TestCase):
    def test_native_population_and_pipeline_state_restore(self):
        source_config = TRAINING_ROOT / "configs" / "neat_discrete_v1.ini"
        config = neat.Config(
            neat.DefaultGenome, neat.DefaultReproduction, neat.DefaultSpeciesSet,
            neat.DefaultStagnation, str(source_config),
        )
        config.pop_size = 8
        config.seed = 1234
        population = neat.Population(config, seed=1234)
        scheduler = TrainingSeedScheduler(load_seed_split(SEED_ROOT / "train.json", "train"), 1234)
        pair = (scheduler.next_seed(), scheduler.next_seed())
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            effective = root / "config.ini"
            config.save(str(effective))
            state_path = save_pipeline_checkpoint(
                population, root / "checkpoints", scheduler,
                run_id="checkpoint-test", transitions=4321,
                next_validation_transition=500000, validations_completed=0,
                effective_config={"experiment_seed": 1234},
                effective_config_path=effective, best_validation=None, best_genome=None,
            )
            expected_random = random.random()
            state = json.loads(state_path.read_text(encoding="utf-8"))
            restored = restore_population_exact(Path(state["native_checkpoint"]))
            self.assertEqual(random.random(), expected_random)
            self.assertEqual(restored.generation, population.generation)
            self.assertEqual(set(restored.population), set(population.population))
            self.assertEqual(state["cumulative_training_transitions"], 4321)
            resumed_scheduler = TrainingSeedScheduler(
                load_seed_split(SEED_ROOT / "train.json", "train"), 1234
            )
            resumed_scheduler.load_state_dict(state["seed_scheduler"])
            self.assertEqual(resumed_scheduler.next_seed(), scheduler.next_seed())
            self.assertEqual(len(set(pair)), 2)


if __name__ == "__main__":
    unittest.main()
