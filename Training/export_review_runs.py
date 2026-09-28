"""Copy the thesis run artifacts without training, evaluation or source changes.

Uses only the standard library. The destination must not exist. A failed export
is left in place for inspection; this tool never deletes or overwrites artifacts.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import shutil


TRAINING = Path(__file__).resolve().parent
MAIN_RUNS = tuple(
    f"{series}-run{number}"
    for series in (
        "ppo-discrete-5m", "ppo-continuous-5m", "neat-discrete-5m",
        "neat-discrete-v2-200g", "neat-continuous-v1-200g",
    )
    for number in (1, 2, 3)
)
SUPPORT_RUNS = (
    "ppo-1m-validation-500-r1", "ppo-4m-validation-500-r1",
    "ppo-run2-best-validation-500", "ppo-run3-best-validation-500",
    *(f"ppo-continuous-run{i}-best-validation-500" for i in (1, 2, 3)),
    *(f"neat-discrete-run{i}-best-validation-500" for i in (1, 2, 3)),
    "neat-discrete-v2-extended-validation-500",
    "neat-continuous-v1-extended-validation-500",
    "neat-discrete-v2-speciation-pilot",
    "neat-continuous-v1-speciation-preflight",
)
SUMMARY_STEMS = (
    "ppo-continuous-experiment-summary", "neat-discrete-experiment-summary",
    "neat-discrete-v2-experiment-summary", "neat-continuous-v1-experiment-summary",
)
# Keep provenance files explicitly referenced by the frozen final selection.
FINAL_CHECKPOINTS = {
    "ppo-discrete-5m-run3/checkpoints/ppo_3000000.zip",
    "ppo-continuous-5m-run3/checkpoints/ppo_2000000.zip",
}
EXCLUDED_DIRS = {"worker_logs", "unity_episode_csv", "training_sessions", "checkpoints"}
DATA_SUFFIXES = {".json", ".csv", ".ini"}


def include(relative: Path) -> bool:
    parts = relative.parts
    if relative.name.lower() == "test.json":
        return False
    if relative.as_posix() in FINAL_CHECKPOINTS:
        return True
    if any(part in EXCLUDED_DIRS for part in parts):
        return False
    if len(parts) == 1:
        return relative.stem in SUMMARY_STEMS and relative.suffix in {".json", ".csv"}
    if parts[0] in SUPPORT_RUNS:
        return relative.suffix in DATA_SUFFIXES
    if parts[0] not in MAIN_RUNS:
        return False
    if len(parts) == 2:
        return relative.suffix in DATA_SUFFIXES
    if parts[1] == "tensorboard":
        return relative.name.startswith("events.out.tfevents.")
    if parts[1] in {"best_model", "selected_models"}:
        return relative.suffix in DATA_SUFFIXES | {".pkl", ".zip"}
    if parts[1] in {"validation", "validation_archive", "milestones"}:
        return relative.suffix in DATA_SUFFIXES | {".pkl"}
    return False


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inventory(source: Path) -> list[Path]:
    """Reject links/junctions rather than following data outside the archive."""
    files = []
    for root, dirs, names in os.walk(source, followlinks=False):
        for name in dirs + names:
            path = Path(root) / name
            if path.is_symlink() or getattr(path.lstat(), "st_file_attributes", 0) & 0x400:
                raise ValueError(f"Links/reparse points are not supported: {path}")
        files.extend(Path(root) / name for name in names)
    return sorted(files)


def plan(source: Path) -> tuple[list[Path], dict]:
    source = source.resolve(strict=True)
    for name in MAIN_RUNS + SUPPORT_RUNS:
        if not (source / name).is_dir():
            raise ValueError(f"Missing expected run: {name}")
    for name in MAIN_RUNS:
        for required in ("manifest.json", "config.json"):
            if not (source / name / required).is_file():
                raise ValueError(f"Missing expected artifact: {name}/{required}")
    for name in FINAL_CHECKPOINTS:
        if not (source / name).is_file():
            raise ValueError(f"Missing frozen checkpoint: {name}")
    files = inventory(source)
    selected = [path for path in files if include(path.relative_to(source))]
    selected_set = set(selected)
    omitted_counts, omitted_bytes = Counter(), Counter()
    for path in files:
        if path not in selected_set:
            top = path.relative_to(source).parts[0]
            omitted_counts[top] += 1
            omitted_bytes[top] += path.stat().st_size
    return selected, {
        "schema": 1,
        "selection_policy": "export_review_runs.py v1; all 15 thesis runs, not ranked by results",
        "source_directory": source.name,
        "main_runs": list(MAIN_RUNS),
        "support_runs": list(SUPPORT_RUNS),
        "source_file_count": len(files),
        "source_bytes": sum(path.stat().st_size for path in files),
        "copied_file_count": len(selected),
        "copied_bytes": sum(path.stat().st_size for path in selected),
        "excluded_by_top_level": {
            name: {"file_count": omitted_counts[name], "bytes": omitted_bytes[name]}
            for name in sorted(omitted_counts)
        },
        "notes": [
            "Original artifacts are copied byte-for-byte; historical paths are not rewritten.",
            "All rows/episodes in included CSV and JSON files are retained.",
            "Not a full resume archive: most intermediate checkpoints and technical logs are omitted.",
            "Final TEST artifacts remain separately in Training/final_test; no TEST is executed.",
            "Counts and bytes exclude the generated README and export manifest.",
        ],
    }


def export(source: Path, destination: Path) -> dict:
    source = source.resolve(strict=True)
    destination = destination.resolve()
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError("Source and destination must not overlap")
    if destination.exists():
        raise FileExistsError(f"Destination already exists; refusing to overwrite: {destination}")
    selected, report = plan(source)
    destination.mkdir(parents=True, exist_ok=False)
    records = []
    for path in selected:
        relative = path.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        before = sha256(path)
        shutil.copy2(path, target)
        if sha256(target) != before or sha256(path) != before:
            raise ValueError(f"Copy verification failed or source changed: {relative}")
        records.append({"path": relative.as_posix(), "bytes": target.stat().st_size, "sha256": before})
    report.update(verification="PASS", files=records)
    (destination / "review_export_manifest.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    main_links = "\n".join(f"- [{name}]({name}/)" for name in MAIN_RUNS)
    support_links = "\n".join(f"- [{name}]({name}/)" for name in SUPPORT_RUNS)
    summary_links = "\n".join(
        f"- [{stem}](./{stem}.csv) ([JSON](./{stem}.json))" for stem in SUMMARY_STEMS
        if (destination / f"{stem}.csv").exists()
    )
    (destination / "README.md").write_text(
        "# Przebiegi wykorzystane w pracy magisterskiej\n\n"
        "To odchudzony eksport danych, nie pełne archiwum do wznawiania treningów. "
        "Oryginały pozostają lokalnie w `Training/runs-original/` (poza Git). "
        "Zachowano wszystkie trzy przebiegi każdej serii, również słabsze wyniki i pilota NEAT-D v1. "
        "Pliki skopiowano bez zmiany zawartości; nie usuwano pojedynczych epizodów.\n\n"
        f"Eksport: **{len(records)} plików źródłowych, {report['copied_bytes'] / 1024**2:.2f} MiB**. "
        f"Pełne archiwum: **{report['source_bytes'] / 1024**3:.2f} GiB**. "
        "Liczby nie obejmują tego README i manifestu eksportu.\n\n"
        "[Manifest eksportu](review_export_manifest.json) zawiera SHA-256 każdego skopiowanego pliku "
        "oraz liczbę i rozmiar pominiętych plików według katalogów. "
        "[Skrypt eksportu](../export_review_runs.py) definiuje jawne reguły doboru.\n\n"
        "## Główne przebiegi\n\n" + main_links + "\n\n"
        "W każdym przebiegu zacznij od `manifest.json` i `config.json`. "
        "PPO: `training_summary.csv`, `validation/`, `best_model/`, `tensorboard/`. "
        "NEAT: `generation_metrics.csv`, `training_episodes.csv`, `neat_config.ini`, "
        "`validation/`, `best_model/`; w v2/C także `validation_archive/`, "
        "`validation_history.json`, `selected_models/` i `milestones/`.\n\n"
        "## Walidacja 500 s i specjacja\n\n" + support_links + "\n\n"
        "## Zestawienia serii\n\n" + summary_links + "\n\n"
        "## Zakres i ograniczenia\n\n"
        "Pominięto obszerne logi workerów, duplikaty CSV z Unity, sesje techniczne, "
        "większość pośrednich checkpointów oraz pomocnicze i nieudane próby techniczne "
        "niewykorzystane w tych seriach. Wyjątkiem są dwa checkpointy PPO wskazane "
        "w zamrożonym manifeście wyboru finalnych modeli. Genomy walidacyjne NEAT zachowano.\n\n"
        "Historyczne manifesty nadal zawierają pierwotne ścieżki lokalne. "
        "Brakujące pliki diagnostyczne/checkpointy znajdują się wyłącznie w archiwum oryginalnym. "
        "Eksport nie służy do kontynuowania istniejących treningów; uruchamiaj nowe eksperymenty "
        "w osobnej kopii roboczej. Nie wymaga ponownego wykonania TEST.\n\n"
        "[Wyniki końcowego TEST](../final_test/) · "
        "[Znane ograniczenia i instrukcje projektu](../../README.md)\n",
        encoding="utf-8",
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=TRAINING / "runs-original")
    parser.add_argument("--destination", type=Path, default=TRAINING / "runs")
    parser.add_argument("--dry-run", action="store_true", help="Inventory only; no writes")
    args = parser.parse_args()
    report = plan(args.source)[1] if args.dry_run else export(args.source, args.destination)
    print(json.dumps({key: value for key, value in report.items() if key != "files"}, indent=2))


if __name__ == "__main__":
    main()
