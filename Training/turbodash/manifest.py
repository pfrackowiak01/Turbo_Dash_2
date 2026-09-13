from __future__ import annotations

import importlib.metadata
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .paths import REPOSITORY_ROOT, SEED_ROOT
from .protocol import (
    DECISION_INTERVAL,
    FIXED_TIMESTEP,
    OBSERVATION_SCHEMA_VERSION,
    OBSERVATION_SIZE,
    RESEARCH_PROTOCOL_VERSION,
    TRANSPORT_VERSION,
)
from .seeds import file_sha256

TRACKED_PACKAGES = ("stable-baselines3", "gymnasium", "numpy", "tensorboard", "torch", "psutil")


def git_snapshot() -> dict[str, Any]:
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPOSITORY_ROOT, text=True, encoding="utf-8"
    ).strip()
    status = subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=REPOSITORY_ROOT, text=True, encoding="utf-8"
    )
    return {"commit": commit, "dirty": bool(status.strip()), "status_porcelain": status.splitlines()}


def package_versions() -> dict[str, str]:
    versions = {}
    for package in TRACKED_PACKAGES:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "NOT INSTALLED"
    return versions


def pip_freeze() -> list[str]:
    output = subprocess.check_output(
        [sys.executable, "-m", "pip", "freeze", "--all"], text=True, encoding="utf-8"
    )
    return sorted(line for line in output.splitlines() if line.strip())


def create_manifest(config: dict[str, Any], *, allow_dirty: bool, run_id: str, purpose: str,
                    worker_executable: Path, parent_checkpoint: str | None = None) -> dict[str, Any]:
    git = git_snapshot()
    if git["dirty"] and not allow_dirty:
        raise RuntimeError("Working tree is dirty. Commit/stash changes or explicitly pass --allow-dirty.")
    train_path = SEED_ROOT / "train.json"
    validation_path = SEED_ROOT / "validation.json"
    return {
        "manifest_schema": 1,
        "run_id": run_id,
        "purpose": purpose,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "starting",
        "git": git,
        "research_protocol": {
            "transport_version": TRANSPORT_VERSION,
            "version": RESEARCH_PROTOCOL_VERSION,
            "observation_schema": OBSERVATION_SCHEMA_VERSION,
            "observation_size": OBSERVATION_SIZE,
            "fixed_timestep": FIXED_TIMESTEP,
            "decision_interval": DECISION_INTERVAL,
            "reward": {"score_scale": 0.01, "life_loss_penalty": 0.5},
        },
        "python": {
            "version": sys.version,
            "executable": sys.executable,
            "platform": platform.platform(),
            "packages": package_versions(),
            "pip_freeze": pip_freeze(),
        },
        "configuration": config,
        "worker_executable": str(worker_executable.resolve()),
        "seed_sources": {
            "train": {"path": str(train_path.relative_to(REPOSITORY_ROOT)), "sha256": file_sha256(train_path), "count": 700},
            "validation": {"path": str(validation_path.relative_to(REPOSITORY_ROOT)), "sha256": file_sha256(validation_path), "count": 100},
            "test": "UNUSED FOR TRAINING/TUNING/EVALUATION",
        },
        "parent_checkpoint": parent_checkpoint,
    }


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)
