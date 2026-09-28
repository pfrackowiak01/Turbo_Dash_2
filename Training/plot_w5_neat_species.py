"""Render thesis figure W5 from six recorded NEAT-D runs; no simulation imports."""
from __future__ import annotations

import argparse
import configparser
import csv
import hashlib
import json
from pathlib import Path
import statistics

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator


ROOT = Path(__file__).resolve().parents[1]
STEM = "W5_neat_species"


def read_runs() -> list[dict]:
    runs = []
    for version in ("v1", "v2"):
        for number in (1, 2, 3):
            name = (f"neat-discrete-5m-run{number}" if version == "v1"
                    else f"neat-discrete-v2-200g-run{number}")
            directory = ROOT / "Training" / "runs" / name
            metrics_path = directory / "generation_metrics.csv"
            config_path = directory / "neat_config.ini"
            with metrics_path.open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))
            generations = [int(row["generation"]) for row in rows]
            counts = [int(row["species_count"]) for row in rows]
            if not generations or generations != list(range(1, len(rows) + 1)):
                raise ValueError(f"Missing, duplicate or unordered generation in {name}")
            config = configparser.ConfigParser()
            with config_path.open(encoding="utf-8-sig") as stream:
                config.read_file(stream)
            population = config.getint("NEAT", "pop_size")
            threshold = config.getfloat("DefaultSpeciesSet", "compatibility_threshold")
            initialization = config.get("DefaultGenome", "initial_connection")
            if population != 64 or any(not 1 <= count <= population for count in counts):
                raise ValueError(f"Invalid population or species count in {name}")
            if version == "v1":
                if initialization != "full_direct" or threshold != 3.0:
                    raise ValueError(f"Unexpected v1 configuration in {name}")
                if any(count != 1 for count in counts):
                    raise ValueError(f"The one-species v1 annotation needs review: {name}")
            else:
                parts = initialization.split()
                if len(parts) != 2 or parts[0] != "partial_direct" or float(parts[1]) != 0.1 or threshold != 2.5:
                    raise ValueError(f"Unexpected v2 configuration in {name}")
                if len(rows) != 200:
                    raise ValueError(f"Incomplete v2 run: {name}")
                before = [int(row["species_before"]) for row in rows]
                if before[1:] != counts[:-1]:
                    raise ValueError(f"Inconsistent between-generation species state in {name}")
            hashes = {str(path.relative_to(ROOT)).replace("\\", "/"):
                      hashlib.sha256(path.read_bytes()).hexdigest()
                      for path in (metrics_path, config_path)}
            runs.append({
                "version": version, "run": number, "run_id": name,
                "generation": generations, "species_count": counts,
                "initial_connection": initialization, "compatibility_threshold": threshold,
                "experiment_seed": config.getint("NEAT", "seed"),
                "population_size": population, "source_sha256": hashes,
                "statistics": {"generations": len(rows), "min": min(counts),
                               "mean": statistics.fmean(counts), "max": max(counts),
                               "final": counts[-1]},
            })
    return runs


def draw_figure(runs: list[dict], output: Path) -> None:
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 11,
        "axes.labelsize": 12, "axes.titlesize": 15,
        "axes.spines.top": False, "axes.spines.right": False,
        "svg.fonttype": "none", "pdf.fonttype": 42,
        "savefig.facecolor": "white",
    })
    fig, ax = plt.subplots(figsize=(10.6, 6.6))
    fig.subplots_adjust(left=0.085, right=0.975, bottom=0.21, top=0.72)
    fig.text(0.085, 0.955, "W5. Liczba gatunków w kolejnych generacjach",
             fontsize=16, weight="bold", color="#172b3a")
    fig.text(0.085, 0.893, "NEAT-D v1: full_direct  |  próg kompatybilności 3,0",
             fontsize=11, color="#a34416")
    fig.text(0.085, 0.849, "NEAT-D v2: partial_direct 0,10  |  próg kompatybilności 2,5",
             fontsize=11, color="#172b3a")

    colors = ("#0072B2", "#009E73", "#8C4B98")
    styles = ("-", (0, (6, 2.4)), (0, (1, 1.7)))
    for item in runs:
        if item["version"] == "v1":
            ax.step(item["generation"], item["species_count"], where="post",
                    color="#B84C17", linewidth=2.4, linestyle=(0, (5, 2)),
                    label="v1 — 3 przebiegi*" if item["run"] == 1 else "_nolegend_",
                    zorder=4)
            ax.plot(item["generation"][-1], item["species_count"][-1],
                    marker=("o", "s", "^")[item["run"] - 1], color="#B84C17",
                    markersize=6, markerfacecolor="white", markeredgewidth=1.4, zorder=5)
        else:
            number = item["run"] - 1
            ax.step(item["generation"], item["species_count"], where="post",
                    color=colors[number], linestyle=styles[number],
                    linewidth=(2.5, 2.3, 2.2)[number], label=f"v2 — przebieg {item['run']}",
                    zorder=2 + number / 10)

    ax.set(xlabel="Generacja", ylabel="Liczba gatunków", xlim=(0, 204), ylim=(0, 9))
    ax.xaxis.set_major_locator(MultipleLocator(20))
    ax.yaxis.set_major_locator(MultipleLocator(1))
    ax.grid(axis="y", color="#DCE2E7", linewidth=0.7)
    ax.set_axisbelow(True)
    ax.tick_params(axis="both", length=3, color="#8B98A2")
    for spine in ax.spines.values():
        spine.set_color("#89969F")
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.018), ncols=4,
              frameon=False, fontsize=10.2, handlelength=2.7,
              columnspacing=1.5, borderaxespad=0)
    ax.annotate("v1: zawsze 1 gatunek", xy=(35, 1), xytext=(8, 0.36),
                fontsize=10.5, color="#A34416",
                arrowprops={"arrowstyle": "->", "color": "#A34416", "lw": 1.1},
                bbox={"facecolor": "white", "edgecolor": "none", "pad": 2})
    v2_counts = [count for item in runs if item["version"] == "v2"
                 for count in item["species_count"]]
    ax.text(84, 7.9, f"v2: {min(v2_counts)}–{max(v2_counts)} gatunków w zapisanych przebiegach",
            color="#344654", fontsize=10.5)
    fig.text(0.085, 0.117,
             "* Krzywe v1 pokrywają się. Końce przebiegów: 61, 63 i 58 generacji; v2: po 200 generacji.",
             fontsize=9.3, color="#425461")
    fig.text(0.085, 0.078,
             "Punkty pochodzą z generation_metrics.csv; stan po zakończeniu generacji. Bez wygładzania.",
             fontsize=9.3, color="#425461")
    for extension in ("png", "pdf", "svg"):
        fig.savefig(output / f"{STEM}.{extension}", dpi=300,
                    metadata={"Creator": "Turbo Dash — plot_w5_neat_species.py"}
                    if extension in ("pdf", "svg") else None)
    plt.close(fig)


def write_data(runs: list[dict], output: Path) -> None:
    fields = ("version", "run", "run_id", "generation", "species_count")
    with (output / f"{STEM}.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for item in runs:
            for generation, count in zip(item["generation"], item["species_count"]):
                writer.writerow({"version": item["version"], "run": item["run"],
                                 "run_id": item["run_id"], "generation": generation,
                                 "species_count": count})
    provenance = {
        "figure": "W5", "measurement": "species_count after completed generation/reproduction",
        "data_rows": sum(len(item["generation"]) for item in runs),
        "smoothing": False, "extrapolation": False,
        "scope": "Three historical NEAT-D v1 runs and three full NEAT-D v2 runs.",
        "excluded": "Separate three-generation v2 tuning pilot; seed catalogs; TEST data.",
        "interpretation": "Descriptive comparison; initialization and threshold changed together, "
                          "with different RNG seeds and stopping budgets; no isolated causal attribution.",
        "sources": [{key: value for key, value in item.items()
                     if key not in ("generation", "species_count")} for item in runs],
    }
    (output / f"{STEM}.json").write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "docs" / "figures")
    args = parser.parse_args()
    runs = read_runs()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    draw_figure(runs, args.output_dir)
    write_data(runs, args.output_dir)
    print(json.dumps({"output": str(args.output_dir.resolve()),
                      "runs": {item["run_id"]: item["statistics"] for item in runs}},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
