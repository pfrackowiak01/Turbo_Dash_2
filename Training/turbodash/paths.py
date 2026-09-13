from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TRAINING_ROOT = REPOSITORY_ROOT / "Training"
SEED_ROOT = REPOSITORY_ROOT / "Assets" / "Turbo_Dash" / "Research" / "Seeds"
DEFAULT_WORKER = REPOSITORY_ROOT / "Builds" / "ResearchWorker" / "TurboDashResearchWorker.exe"
DEFAULT_CONFIG = TRAINING_ROOT / "configs" / "ppo_pilot_v1.json"
RUNS_ROOT = TRAINING_ROOT / "runs"
