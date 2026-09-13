import unittest

from turbodash.paths import SEED_ROOT
from turbodash.seeds import TrainingSeedScheduler, load_seed_split


class SeedTests(unittest.TestCase):
    def test_full_permutations_and_resume(self):
        seeds = load_seed_split(SEED_ROOT / "train.json", "train")
        scheduler = TrainingSeedScheduler(seeds, 20260913)
        first_cycle = [scheduler.next_seed() for _ in range(700)]
        self.assertEqual(sorted(first_cycle), sorted(seeds))
        for _ in range(19):
            scheduler.next_seed()
        restored = TrainingSeedScheduler(seeds, 20260913)
        restored.load_state_dict(scheduler.state_dict())
        self.assertEqual([restored.next_seed() for _ in range(23)], [scheduler.next_seed() for _ in range(23)])

    def test_test_split_is_forbidden(self):
        with self.assertRaisesRegex(ValueError, "TEST is forbidden"):
            load_seed_split(SEED_ROOT / "test.json", "test")


if __name__ == "__main__":
    unittest.main()
