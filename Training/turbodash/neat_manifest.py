from __future__ import annotations

import importlib.metadata
from pathlib import Path
from typing import Any

from .manifest import create_manifest

REQUIRED_NEAT_VERSION = "2.0.0"


def require_neat_version() -> str:
    version = importlib.metadata.version("neat-python")
    if version != REQUIRED_NEAT_VERSION:
        raise RuntimeError(f"neat-python {REQUIRED_NEAT_VERSION} is required, found {version}")
    return version


def create_neat_manifest(config: dict[str, Any], *, allow_dirty: bool, run_id: str,
                         purpose: str, worker_executable: Path) -> dict[str, Any]:
    version = require_neat_version()
    manifest = create_manifest(
        config,
        allow_dirty=allow_dirty,
        run_id=run_id,
        purpose=purpose,
        worker_executable=worker_executable,
    )
    manifest["algorithm"] = "NEAT Discrete"
    manifest["python"]["packages"]["neat-python"] = version
    manifest["checkpoint_schema"] = 1
    return manifest
