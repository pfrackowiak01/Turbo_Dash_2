from __future__ import annotations

import csv
import json
import math
import os
import statistics
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "turbodash-matplotlib"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy import stats

from .seeds import file_sha256

METHODS = ("RuleBasedV1", "PPO-D", "PPO-C", "NEAT-D", "NEAT-C")
COLORS = {"RuleBasedV1": "#777777", "PPO-D": "#2474b5", "PPO-C": "#4aa5d8",
          "NEAT-D": "#d97919", "NEAT-C": "#e4aa39"}
OUTCOMES = (
    "final_score", "survival_time", "episode_reward", "life_loss_count", "collisions",
    "obstacles_avoided", "max_level", "hearts_collected", "shields_collected",
    "boosts_collected", "gold_collected", "diamonds_collected", "turbo_activations",
)


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: Iterable[str] | None = None) -> None:
    names = list(fields or (rows[0].keys() if rows else ()))
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=names, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def load_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", newline="", encoding="utf-8") as stream:
        source = list(csv.DictReader(stream))
    rows: list[dict[str, Any]] = []
    integers = {"test_seed", "repetition_index", "seed", "repetition", "schedule_index", "worker_id",
                "retry_count", "research_protocol_version", "observation_schema_version", "observation_size", "episode_id",
                "decision_count", "segments_passed", "obstacles_encountered", "obstacles_avoided",
                "collisions", "life_loss_count", "shield_hits", "hearts_collected", "shields_collected",
                "boosts_collected", "turbo_activations", "gold_collected", "diamonds_collected", "max_level",
                "outside_stages_reached", "physics_ticks", "discrete_left_count", "discrete_none_count",
                "discrete_right_count", "action_change_count"}
    booleans = {"fatal_collision", "terminated", "truncated"}
    text = {"method", "model_id", "model_sha256", "action_space", "terminal_reason", "completed_utc",
            "continuous_bin_counts"}
    for source_row in source:
        row: dict[str, Any] = {}
        for name, value in source_row.items():
            if name in text:
                row[name] = value
            elif name in booleans:
                row[name] = str(value).lower() == "true"
            elif value == "" or value is None:
                row[name] = None
            elif name in integers:
                row[name] = int(value)
            else:
                row[name] = float(value)
        rows.append(row)
    return rows


def validate_rows(rows: list[dict[str, Any]], protocol: dict[str, Any], strict: bool) -> list[int]:
    expected_repetitions = int(protocol["repetitions"])
    keys = [(row["method"], row["seed"], row["repetition"]) for row in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate method/seed/repetition keys in raw TEST data")
    if set(row["method"] for row in rows) != set(METHODS):
        raise ValueError("Raw TEST data does not contain exactly the five frozen methods")
    seeds = sorted(set(row["seed"] for row in rows))
    expected_per_method = len(seeds) * expected_repetitions
    for method in METHODS:
        method_rows = [row for row in rows if row["method"] == method]
        if len(method_rows) != expected_per_method:
            raise ValueError(f"{method} does not have all seed/repetition combinations")
        actual = {(row["seed"], row["repetition"]) for row in method_rows}
        expected = {(seed, repetition) for seed in seeds for repetition in range(1, expected_repetitions + 1)}
        if actual != expected:
            raise ValueError(f"{method} schedule coverage is incomplete")
    if strict and (len(rows) != 3000 or len(seeds) != 200):
        raise ValueError("Unblinding requires exactly 3000 episodes over 200 TEST seeds")
    return seeds


def aggregate_seed_rows(rows: list[dict[str, Any]], seeds: list[int]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["method"], row["seed"])].append(row)
    result = []
    for method in METHODS:
        for seed in seeds:
            episodes = grouped[(method, seed)]
            item: dict[str, Any] = {"method": method, "seed": seed, "repetitions": len(episodes)}
            for metric in OUTCOMES:
                values = [float(row[metric]) for row in episodes]
                item[metric] = statistics.fmean(values)
                item[f"{metric}_repetition_sd"] = statistics.pstdev(values)
                item[f"{metric}_exact_match"] = len(set(values)) == 1
            result.append(item)
    return result


def bootstrap_mean_ci(values: np.ndarray, rng: np.random.Generator, resamples: int) -> tuple[float, float]:
    n = len(values)
    samples = np.empty(resamples, dtype=np.float64)
    batch = 1000
    for start in range(0, resamples, batch):
        size = min(batch, resamples - start)
        indices = rng.integers(0, n, size=(size, n))
        samples[start:start + size] = values[indices].mean(axis=1)
    return tuple(float(value) for value in np.quantile(samples, [0.025, 0.975]))


def paired_rank_biserial(differences: np.ndarray) -> float:
    nonzero = differences[differences != 0]
    if len(nonzero) == 0:
        return 0.0
    ranks = stats.rankdata(np.abs(nonzero), method="average")
    denominator = float(ranks.sum())
    return float((ranks[nonzero > 0].sum() - ranks[nonzero < 0].sum()) / denominator)


def holm_adjust(p_values: list[float]) -> list[float]:
    order = sorted(range(len(p_values)), key=lambda index: p_values[index])
    adjusted = [1.0] * len(p_values)
    running = 0.0
    count = len(p_values)
    for rank, index in enumerate(order):
        running = max(running, min(1.0, (count - rank) * p_values[index]))
        adjusted[index] = running
    return adjusted


def primary_statistics(seed_rows: list[dict[str, Any]], seeds: list[int], protocol: dict[str, Any]
                       ) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    matrix = {method: np.asarray([next(row["final_score"] for row in seed_rows
                                             if row["method"] == method and row["seed"] == seed)
                                  for seed in seeds], dtype=np.float64) for method in METHODS}
    if all(np.array_equal(matrix[METHODS[0]], matrix[method]) for method in METHODS[1:]):
        statistic, p_value = 0.0, 1.0
    else:
        statistic, p_value = stats.friedmanchisquare(*(matrix[method] for method in METHODS))
    omnibus = {"test": "Friedman", "analysis_unit": "seed", "n_seeds": len(seeds),
                "statistic": float(statistic), "degrees_of_freedom": len(METHODS) - 1,
                "p_value": float(p_value), "alpha": 0.05, "significant": bool(p_value < 0.05)}
    rng = np.random.default_rng(int(protocol["bootstrap_random_seed"]))
    pairwise: list[dict[str, Any]] = []
    if omnibus["significant"]:
        for first_index, first in enumerate(METHODS):
            for second in METHODS[first_index + 1:]:
                differences = matrix[first] - matrix[second]
                test = (type("WilcoxonZero", (), {"statistic": 0.0, "pvalue": 1.0})()
                        if np.all(differences == 0) else
                        stats.wilcoxon(matrix[first], matrix[second], zero_method="wilcox",
                                      correction=False, alternative="two-sided", method="auto"))
                ci_low, ci_high = bootstrap_mean_ci(differences, rng, int(protocol["bootstrap_resamples"]))
                pairwise.append({
                    "method_a": first, "method_b": second, "n_seeds": len(seeds),
                    "mean_difference_a_minus_b": float(np.mean(differences)),
                    "median_difference_a_minus_b": float(np.median(differences)),
                    "bootstrap_ci95_low": ci_low, "bootstrap_ci95_high": ci_high,
                    "wilcoxon_statistic": float(test.statistic), "p_raw": float(test.pvalue),
                    "paired_rank_biserial": paired_rank_biserial(differences),
                })
        adjusted = holm_adjust([row["p_raw"] for row in pairwise])
        for row, p_adjusted in zip(pairwise, adjusted):
            row["p_holm"] = p_adjusted
            row["significant_holm"] = p_adjusted < 0.05
    method_rows = []
    for method in METHODS:
        values = matrix[method]
        low, high = bootstrap_mean_ci(values, rng, int(protocol["bootstrap_resamples"]))
        item = {
            "method": method, "n_seeds": len(values), "n_episodes": len(values) * int(protocol["repetitions"]),
            "final_score_mean": float(np.mean(values)), "final_score_median": float(np.median(values)),
            "final_score_std": float(np.std(values)), "final_score_q25": float(np.quantile(values, .25)),
            "final_score_q75": float(np.quantile(values, .75)), "final_score_min": float(np.min(values)),
            "final_score_max": float(np.max(values)), "mean_bootstrap_ci95_low": low,
            "mean_bootstrap_ci95_high": high,
        }
        for metric in OUTCOMES:
            metric_values = np.asarray([row[metric] for row in seed_rows if row["method"] == method],
                                       dtype=np.float64)
            item[f"{metric}_mean"] = float(np.mean(metric_values))
            item[f"{metric}_median"] = float(np.median(metric_values))
            item[f"{metric}_std"] = float(np.std(metric_values))
        method_rows.append(item)
    return omnibus, pairwise, method_rows


def winner_decision(method_rows: list[dict[str, Any]], omnibus: dict[str, Any],
                    pairwise: list[dict[str, Any]]) -> dict[str, Any]:
    ranking = sorted(method_rows, key=lambda row: row["final_score_mean"], reverse=True)
    top = ranking[0]["method"]
    comparisons = [row for row in pairwise if top in (row["method_a"], row["method_b"])]
    dominates = []
    for row in comparisons:
        direction = row["mean_difference_a_minus_b"] if row["method_a"] == top else -row["mean_difference_a_minus_b"]
        ci_excludes_zero = row["bootstrap_ci95_low"] > 0 or row["bootstrap_ci95_high"] < 0
        dominates.append(bool(row["significant_holm"] and direction > 0 and ci_excludes_zero))
    winner = top if omnibus["significant"] and len(comparisons) == 4 and all(dominates) else None
    if winner:
        top_set = [winner]
    else:
        top_set = [top]
        for method in METHODS:
            if method == top:
                continue
            comparison = next((row for row in comparisons if method in (row["method_a"], row["method_b"])), None)
            ci_excludes_zero = comparison is not None and (
                comparison["bootstrap_ci95_low"] > 0 or comparison["bootstrap_ci95_high"] < 0)
            if comparison is None or not comparison.get("significant_holm", False) or not ci_excludes_zero:
                top_set.append(method)
    return {"declared_winner": winner, "highest_mean_method": top, "unambiguous": winner is not None,
            "statistically_inseparable_top_set": top_set,
            "rule": "highest mean plus Holm-significant superiority to every other method"}


def action_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for method in METHODS:
        subset = [row for row in rows if row["method"] == method]
        decisions = sum(row["decision_count"] for row in subset)
        item: dict[str, Any] = {"method": method, "action_space": subset[0]["action_space"],
                                "episodes": len(subset), "decision_count": decisions,
                                "action_change_rate": sum(row["action_change_count"] for row in subset)
                                / max(1, decisions - len(subset)),
                                "mean_action_hold_decisions": decisions /
                                max(1, len(subset) + sum(row["action_change_count"] for row in subset))}
        if subset[0]["action_space"] == "Discrete":
            for name in ("left", "none", "right"):
                count = sum(row[f"discrete_{name}_count"] for row in subset)
                item[f"{name}_count"] = count
                item[f"{name}_rate"] = count / decisions
        else:
            weights = np.asarray([row["decision_count"] for row in subset], dtype=np.float64)
            for name in ("mean", "mean_abs", "near_zero_rate", "near_max_rate", "left_rate", "right_rate"):
                values = np.asarray([row[f"continuous_{name}"] for row in subset], dtype=np.float64)
                item[name] = float(np.average(values, weights=weights))
            total_second = sum((row["continuous_std"] ** 2 + row["continuous_mean"] ** 2)
                               * row["decision_count"] for row in subset)
            item["std"] = math.sqrt(max(0.0, total_second / decisions - item["mean"] ** 2))
            item["mean_abs_delta_steering"] = float(np.average(
                [row["mean_abs_delta_steering"] for row in subset], weights=weights))
            item["steering_sign_change_rate"] = float(np.average(
                [row["steering_sign_change_rate"] for row in subset], weights=weights))
        output.append(item)
    return output


def strategy_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sources = {
        "collisions_per_100s": "collisions", "obstacles_avoided_per_100s": "obstacles_avoided",
        "life_losses_per_100s": "life_loss_count", "hearts_per_100s": "hearts_collected",
        "shields_per_100s": "shields_collected", "boosts_per_100s": "boosts_collected",
        "turbo_per_100s": "turbo_activations", "gold_per_100s": "gold_collected",
        "diamonds_per_100s": "diamonds_collected",
    }
    output = []
    for method in METHODS:
        subset = [row for row in rows if row["method"] == method]
        total_time = sum(max(float(row["survival_time"]), 1e-9) for row in subset)
        item: dict[str, Any] = {"method": method, "episodes": len(subset),
                                "total_survival_seconds": total_time,
                                "max_duration_success_rate": statistics.fmean(
                                    row["terminal_reason"] == "MaxDuration" for row in subset)}
        for target, source in sources.items():
            item[target] = 100.0 * sum(float(row[source]) for row in subset) / total_time
        output.append(item)
    return output


def kaplan_meier(subset: list[dict[str, Any]], horizon: float) -> tuple[list[float], list[float], dict[float, int]]:
    records = sorted((min(float(row["survival_time"]), horizon), row["terminal_reason"] == "LivesExhausted")
                     for row in subset)
    times, survival = [0.0], [1.0]
    at_risk = len(records)
    for time_value in sorted(set(time for time, _ in records)):
        events = sum(time == time_value and event for time, event in records)
        censored = sum(time == time_value and not event for time, event in records)
        if events:
            times.append(time_value)
            survival.append(survival[-1] * (1.0 - events / at_risk))
        at_risk -= events + censored
    risk = {point: sum(time >= point for time, _ in records) for point in (0, 100, 200, 300, 400, 500)}
    return times, survival, risk


def survival_outputs(rows: list[dict[str, Any]], horizon: float) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    summaries = []
    curves = {}
    for method in METHODS:
        subset = [row for row in rows if row["method"] == method]
        times, survival, risk = kaplan_meier(subset, horizon)
        median = next((time for time, value in zip(times, survival) if value <= 0.5), None)
        summaries.append({"method": method, "episodes": len(subset),
                          "events_lives_exhausted": sum(row["terminal_reason"] == "LivesExhausted" for row in subset),
                          "censored_max_duration": sum(row["terminal_reason"] == "MaxDuration" for row in subset),
                          "km_median_survival": median if median is not None else f">{horizon}",
                          **{f"at_risk_{int(point)}": count for point, count in risk.items()}})
        curves[method] = {"times": times, "survival": survival, "at_risk": risk}
    return summaries, curves


def nondeterminism(rows: list[dict[str, Any]], seed_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for method in METHODS:
        subset = [row for row in seed_rows if row["method"] == method]
        raw_groups = defaultdict(list)
        for row in rows:
            if row["method"] == method:
                raw_groups[row["seed"]].append(float(row["final_score"]))
        k = len(next(iter(raw_groups.values())))
        seed_means = np.asarray([statistics.fmean(values) for values in raw_groups.values()])
        ms_between = k * float(np.var(seed_means, ddof=1)) if len(seed_means) > 1 else 0.0
        ms_within = sum(sum((value - statistics.fmean(values)) ** 2 for value in values)
                        for values in raw_groups.values()) / max(1, len(raw_groups) * (k - 1))
        icc = (ms_between - ms_within) / (ms_between + (k - 1) * ms_within) \
            if ms_between + (k - 1) * ms_within > 0 else 1.0
        output.append({
            "method": method, "seeds": len(subset),
            "mean_within_seed_final_score_sd": statistics.fmean(row["final_score_repetition_sd"] for row in subset),
            "median_within_seed_final_score_sd": statistics.median(row["final_score_repetition_sd"] for row in subset),
            "exact_final_score_match_seed_rate": statistics.fmean(row["final_score_exact_match"] for row in subset),
            "mean_within_seed_survival_sd": statistics.fmean(row["survival_time_repetition_sd"] for row in subset),
            "between_seed_sd_of_mean_final_score": float(np.std(seed_means, ddof=0)),
            "variance_component_between_seed": max(0.0, (ms_between - ms_within) / k),
            "variance_component_within_seed": ms_within,
            "icc_one_way_random": float(icc),
        })
    return output


def seed_difficulty(seed_rows: list[dict[str, Any]], seeds: list[int]
                    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_key = {(row["method"], row["seed"]): float(row["final_score"]) for row in seed_rows}
    difficulty = []
    relative = []
    for seed in seeds:
        scores = [by_key[(method, seed)] for method in METHODS]
        environment_mean = statistics.fmean(scores)
        difficulty.append({"seed": seed, "mean_final_score_across_methods": environment_mean})
        for method in METHODS:
            others = [by_key[(other, seed)] for other in METHODS if other != method]
            relative.append({"method": method, "seed": seed, "method_final_score": by_key[(method, seed)],
                             "other_methods_mean": statistics.fmean(others),
                             "relative_advantage": by_key[(method, seed)] - statistics.fmean(others)})
    difficulty.sort(key=lambda row: row["mean_final_score_across_methods"])
    for rank, row in enumerate(difficulty, 1):
        row["difficulty_rank_hardest_first"] = rank
        row["difficulty_rank_easiest_first"] = len(difficulty) - rank + 1
    selected = []
    for method in METHODS:
        subset = sorted((row for row in relative if row["method"] == method),
                        key=lambda row: row["relative_advantage"], reverse=True)
        for rank, row in enumerate(subset[:10], 1):
            selected.append({**row, "extreme": "relative_best", "rank": rank})
        for rank, row in enumerate(reversed(subset[-10:]), 1):
            selected.append({**row, "extreme": "relative_worst", "rank": rank})
    return difficulty, selected


def failure_overlap(rows: list[dict[str, Any]], seeds: list[int]) -> tuple[list[dict[str, Any]], np.ndarray]:
    failed: dict[str, set[int]] = {}
    for method in METHODS:
        failed[method] = {seed for seed in seeds if statistics.fmean(
            row["terminal_reason"] == "LivesExhausted" for row in rows
            if row["method"] == method and row["seed"] == seed) >= 2 / 3}
    matrix = np.zeros((len(METHODS), len(METHODS)), dtype=np.float64)
    output = []
    for i, first in enumerate(METHODS):
        for j, second in enumerate(METHODS):
            union = failed[first] | failed[second]
            value = len(failed[first] & failed[second]) / len(union) if union else 1.0
            matrix[i, j] = value
            output.append({"method_a": first, "method_b": second,
                           "high_failure_seed_count_a": len(failed[first]),
                           "high_failure_seed_count_b": len(failed[second]),
                           "intersection_count": len(failed[first] & failed[second]),
                           "jaccard_overlap": value,
                           "high_failure_rule": "LivesExhausted in at least 2 of 3 repetitions"})
    return output, matrix


def generalization(method_rows: list[dict[str, Any]], selection: dict[str, Any]) -> list[dict[str, Any]]:
    selected = {item["method"]: item for item in selection["methods"]}
    output = []
    for row in method_rows:
        validation = selected[row["method"]].get("validation_500_mean_final_score")
        test = row["final_score_mean"]
        output.append({"method": row["method"], "validation_500_mean_final_score": validation,
                       "test_mean_final_score": test,
                       "absolute_gap_test_minus_validation": None if validation is None else test - validation,
                       "relative_gap": None if validation in (None, 0) else (test - validation) / validation,
                       "note": "unavailable: no pre-existing VALIDATION 500" if validation is None else "descriptive"})
    return output


def save_figure(fig: plt.Figure, path: Path) -> None:
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def generate_plots(rows: list[dict[str, Any]], seed_rows: list[dict[str, Any]], pairwise: list[dict[str, Any]],
                   curves: dict[str, Any], nondet: list[dict[str, Any]], strategy: list[dict[str, Any]],
                   generalization_rows: list[dict[str, Any]], difficulty: list[dict[str, Any]],
                   overlap_matrix: np.ndarray, output: Path) -> None:
    plots = output / "plots"
    plots.mkdir(exist_ok=True)
    values = {method: np.asarray([row["final_score"] for row in seed_rows if row["method"] == method]) for method in METHODS}
    labels, colors = list(METHODS), [COLORS[m] for m in METHODS]

    fig, ax = plt.subplots(figsize=(8, 5)); parts = ax.violinplot([values[m] for m in METHODS], showextrema=False)
    for body, color in zip(parts["bodies"], colors): body.set_facecolor(color); body.set_alpha(.55)
    ax.boxplot([values[m] for m in METHODS], widths=.18, showfliers=False); ax.set_xticks(range(1, 6), labels)
    ax.set(ylabel="Mean finalScore per TEST seed", title="Final score distribution (seed-level means)")
    save_figure(fig, plots / "01_finalScore_violin_box.png")

    fig, ax = plt.subplots(figsize=(8, 5))
    for method in METHODS:
        ordered=np.sort(values[method]); ax.step(ordered,np.arange(1,len(ordered)+1)/len(ordered),where="post",label=method,color=COLORS[method])
    ax.set(xlabel="Mean finalScore per TEST seed",ylabel="ECDF",title="Final score empirical distributions"); ax.legend()
    save_figure(fig, plots / "02_finalScore_ecdf.png")

    fig, ax = plt.subplots(figsize=(8,5)); parts=ax.violinplot([[r["survival_time"] for r in seed_rows if r["method"]==m] for m in METHODS],showextrema=False)
    for body,color in zip(parts["bodies"],colors): body.set_facecolor(color); body.set_alpha(.55)
    ax.boxplot([[r["survival_time"] for r in seed_rows if r["method"]==m] for m in METHODS],widths=.18,showfliers=False); ax.set_xticks(range(1,6),labels)
    ax.set(ylabel="Mean survival time per seed [s]",title="Survival time distribution"); save_figure(fig,plots/"03_survivalTime_violin_box.png")

    fig, ax = plt.subplots(figsize=(8,6))
    for method in METHODS: ax.step(curves[method]["times"],curves[method]["survival"],where="post",label=method,color=COLORS[method])
    ax.set(xlim=(0,500),ylim=(0,1.02),xlabel="Survival time [s]",ylabel="Kaplan–Meier survival",title="Descriptive survival curves"); ax.legend()
    table=[[curves[m]["at_risk"][p] for p in (0,100,200,300,400,500)] for m in METHODS]
    plt.table(cellText=table,rowLabels=METHODS,colLabels=[0,100,200,300,400,500],cellLoc="center",bbox=[0,-.48,1,.32]); fig.subplots_adjust(bottom=.34)
    fig.savefig(plots/"04_survival_kaplan_meier.png",dpi=300,bbox_inches="tight"); plt.close(fig)

    fig, ax=plt.subplots(figsize=(8,5)); ax.bar(labels,[next(r["max_duration_success_rate"] for r in strategy if r["method"]==m) for m in METHODS],color=colors)
    ax.set(ylim=(0,1),ylabel="Fraction of episodes",title="MaxDuration success rate"); save_figure(fig,plots/"05_maxDuration_success_rate.png")

    fig, ax=plt.subplots(figsize=(8,6))
    if pairwise:
        names=[f"{r['method_a']} − {r['method_b']}" for r in pairwise]; means=np.asarray([r["mean_difference_a_minus_b"] for r in pairwise]); low=np.asarray([r["bootstrap_ci95_low"] for r in pairwise]); high=np.asarray([r["bootstrap_ci95_high"] for r in pairwise])
        ax.errorbar(means,range(len(names)),xerr=[means-low,high-means],fmt="o",color="#333333",capsize=3); ax.set_yticks(range(len(names)),names)
    else: ax.text(.5,.5,"No post-hoc tests: Friedman not significant",ha="center",va="center",transform=ax.transAxes)
    ax.axvline(0,color="black",lw=.8); ax.set(xlabel="Paired mean finalScore difference (95% bootstrap CI)",title="Pairwise final score effects")
    save_figure(fig,plots/"06_pairwise_finalScore_difference_forest.png")

    matrix=np.column_stack([values[m] for m in METHODS]); normalized=(matrix-matrix.mean(axis=1,keepdims=True))/np.where(matrix.std(axis=1,keepdims=True)==0,1,matrix.std(axis=1,keepdims=True))
    fig,ax=plt.subplots(figsize=(7,9)); image=ax.imshow(normalized,aspect="auto",cmap="coolwarm",vmin=-2,vmax=2); ax.set_xticks(range(5),labels); ax.set(ylabel="TEST seeds",title="Within-seed standardized finalScore"); fig.colorbar(image,ax=ax,label="z within seed")
    save_figure(fig,plots/"07_method_seed_heatmap.png")

    fig,ax=plt.subplots(figsize=(9,5)); x=np.arange(5); width=.36
    ax.bar(x-width/2,[next(r["collisions_per_100s"] for r in strategy if r["method"]==m) for m in METHODS],width,label="collisions")
    ax.bar(x+width/2,[next(r["life_losses_per_100s"] for r in strategy if r["method"]==m) for m in METHODS],width,label="life losses"); ax.set_xticks(x,labels); ax.set(ylabel="Events per 100 s",title="Normalized collision and life-loss rates"); ax.legend()
    save_figure(fig,plots/"08_collision_and_life_loss_rates.png")

    metrics=("hearts_per_100s","shields_per_100s","boosts_per_100s","turbo_per_100s","gold_per_100s","diamonds_per_100s"); fig,ax=plt.subplots(figsize=(10,5)); width=.13
    for i,metric in enumerate(metrics): ax.bar(x+(i-2.5)*width,[next(r[metric] for r in strategy if r["method"]==m) for m in METHODS],width,label=metric.replace("_per_100s",""))
    ax.set_xticks(x,labels); ax.set(ylabel="Items per 100 s",title="Normalized bonus strategy"); ax.legend(ncols=3)
    save_figure(fig,plots/"09_bonus_strategy_rates.png")

    discrete=["RuleBasedV1","PPO-D","NEAT-D"]; fig,ax=plt.subplots(figsize=(8,5)); xd=np.arange(3); width=.25
    for i,action in enumerate(("left","none","right")):
        rates=[sum(r[f"discrete_{action}_count"] for r in rows if r["method"]==m)/sum(r["decision_count"] for r in rows if r["method"]==m) for m in discrete]; ax.bar(xd+(i-1)*width,rates,width,label=action)
    ax.set_xticks(xd,discrete); ax.set(ylabel="Fraction of decisions",title="Discrete action profiles"); ax.legend()
    save_figure(fig,plots/"10_discrete_action_profiles.png")

    fig,ax=plt.subplots(figsize=(8,5)); centers=np.linspace(-.975,.975,40)
    for method in ("PPO-C","NEAT-C"):
        counts=np.sum([np.asarray(json.loads(r["continuous_bin_counts"]),dtype=np.int64) for r in rows if r["method"]==method],axis=0); ax.step(centers,counts/counts.sum(),where="mid",label=method,color=COLORS[method])
    ax.set(xlabel="Steering",ylabel="Fraction of decisions per 0.05 bin",title="Continuous steering profiles"); ax.legend()
    save_figure(fig,plots/"11_continuous_steering_profiles.png")

    available=[r for r in generalization_rows if r["validation_500_mean_final_score"] is not None]; fig,ax=plt.subplots(figsize=(9,5)); xg=np.arange(len(available)); width=.36
    ax.bar(xg-width/2,[r["validation_500_mean_final_score"] for r in available],width,label="VALIDATION 500"); ax.bar(xg+width/2,[r["test_mean_final_score"] for r in available],width,label="TEST 500"); ax.set_xticks(xg,[r["method"] for r in available]); ax.set(ylabel="Mean finalScore",title="Validation-to-test generalization"); ax.legend()
    save_figure(fig,plots/"12_validation_vs_test_generalization.png")

    fig,ax=plt.subplots(figsize=(8,5)); ax.bar(labels,[r["mean_within_seed_final_score_sd"] for r in nondet],color=colors); ax.set(ylabel="Mean within-seed SD over 3 repetitions",title="Repeat variability")
    save_figure(fig,plots/"13_repeat_variability.png")

    hardest=difficulty[:20]; fig,ax=plt.subplots(figsize=(10,5)); ax.bar([str(r["seed"]) for r in hardest],[r["mean_final_score_across_methods"] for r in hardest],color="#777777"); ax.tick_params(axis="x",rotation=70); ax.set(ylabel="Mean finalScore across methods",xlabel="TEST seed",title="Twenty hardest TEST seeds")
    save_figure(fig,plots/"14_hardest_test_seeds.png")

    fig,ax=plt.subplots(figsize=(7,6)); image=ax.imshow(overlap_matrix,vmin=0,vmax=1,cmap="viridis"); ax.set_xticks(range(5),labels,rotation=30,ha="right"); ax.set_yticks(range(5),labels); ax.set(title="High-failure seed overlap (Jaccard)");
    for i in range(5):
        for j in range(5): ax.text(j,i,f"{overlap_matrix[i,j]:.2f}",ha="center",va="center",color="white" if overlap_matrix[i,j]<.55 else "black")
    fig.colorbar(image,ax=ax,label="Jaccard overlap"); save_figure(fig,plots/"15_failure_overlap_heatmap.png")


def render_report(output: Path, protocol: dict[str, Any], selection: dict[str, Any],
                  method_rows: list[dict[str, Any]], omnibus: dict[str, Any],
                  pairwise: list[dict[str, Any]], winner: dict[str, Any], survival: list[dict[str, Any]],
                  strategy: list[dict[str, Any]], nondet: list[dict[str, Any]],
                  generalization_rows: list[dict[str, Any]], run_manifest: dict[str, Any]) -> None:
    ranking = sorted(method_rows, key=lambda row: row["final_score_mean"], reverse=True)
    lines = ["# Turbo Dash — końcowy raport TEST", "",
             "Analizę odślepiono dopiero po zapisaniu 3000 poprawnych epizodów. Raport przedstawia fakty liczbowe bez spekulacyjnej interpretacji.", "",
             "## Protokół i integralność", "",
             f"- 200 seedów TEST × 3 powtórzenia × 5 metod = 3000 poprawnych epizodów; MaxDuration={protocol['max_duration']} s.",
             f"- Jednostka analizy głównej: seed; metryka główna: {protocol['primary_metric']}.",
             f"- Git wykonania: `{run_manifest.get('git_commit', 'n/a')}`; worker SHA-256: `{run_manifest.get('worker_sha256', 'n/a')}`.",
             f"- Retry techniczne: {sum(run_manifest.get('technical_retry_counts', {}).values())}.", "",
             "### Zamrożone modele", "",
             "| Metoda | Model/wersja | Artefakt | SHA-256 |", "|---|---|---|---|"]
    for item in selection["methods"]:
        model_id = item.get("run_id", "RuleBasedV1")
        if "checkpoint_timestep" in item:
            model_id += f", checkpoint {item['checkpoint_timestep']}"
        if "generation" in item:
            model_id += f", generation {item['generation']}, genome {item['genome_id']}"
        artifact = item.get("model_path", item.get("genome_path", item.get("source_path")))
        digest = item.get("model_sha256", item.get("genome_sha256", item.get("source_sha256")))
        lines.append(f"| {item['method']} | {model_id} | `{artifact}` | `{digest}` |")
    lines += ["",
             "## Wynik główny", "", "| Metoda | Średnia finalScore | Mediana | 95% CI bootstrap |", "|---|---:|---:|---:|"]
    for row in ranking:
        lines.append(f"| {row['method']} | {row['final_score_mean']:.3f} | {row['final_score_median']:.3f} | [{row['mean_bootstrap_ci95_low']:.3f}, {row['mean_bootstrap_ci95_high']:.3f}] |")
    lines += ["", f"Test Friedmana: χ²={omnibus['statistic']:.4f}, df={omnibus['degrees_of_freedom']}, p={omnibus['p_value']:.6g}.", ""]
    if winner["declared_winner"]:
        lines.append(f"Jednoznaczny zwycięzca według zamrożonej reguły: **{winner['declared_winner']}**.")
    else:
        lines.append("Brak jednoznacznego zwycięzcy według zamrożonej reguły. Statystycznie nierozdzielny zbiór czołowy: " + ", ".join(winner["statistically_inseparable_top_set"]) + ".")
        lines.append(f"{ranking[0]['method']} ma najwyższą wartość numeryczną, lecz nie spełnia warunku jednoznacznej przewagi statystycznej nad czołówką.")
    lines += ["", "## Porównania parami", ""]
    if pairwise:
        lines += ["| A − B | Średnia różnica | 95% CI | p Holm | rank-biserial |", "|---|---:|---:|---:|---:|"]
        for row in pairwise:
            lines.append(f"| {row['method_a']} − {row['method_b']} | {row['mean_difference_a_minus_b']:.3f} | [{row['bootstrap_ci95_low']:.3f}, {row['bootstrap_ci95_high']:.3f}] | {row['p_holm']:.6g} | {row['paired_rank_biserial']:.4f} |")
    else:
        lines.append("Test omnibus nie był istotny; zgodnie z protokołem nie wykonano testów post-hoc.")
    lines += ["", "## Wyniki drugorzędne", "",
              "| Metoda | Survival [s] | MaxDuration | Kolizje/100 s | Utraty życia/100 s | MaxLevel |", "|---|---:|---:|---:|---:|---:|"]
    by_strategy = {row["method"]: row for row in strategy}
    for row in ranking:
        item = by_strategy[row["method"]]
        lines.append(f"| {row['method']} | {row['survival_time_mean']:.3f} | {item['max_duration_success_rate']:.3%} | {item['collisions_per_100s']:.3f} | {item['life_losses_per_100s']:.3f} | {row['max_level_mean']:.3f} |")
    lines += ["", "Kaplan–Meier jest analizą opisową: `LivesExhausted` jest zdarzeniem, a `MaxDuration` obserwacją prawostronnie cenzurowaną.", "",
              "## Generalizacja VALIDATION 500 → TEST 500", "",
              "| Metoda | Validation | TEST | Różnica | Względna |", "|---|---:|---:|---:|---:|"]
    for row in generalization_rows:
        if row["validation_500_mean_final_score"] is None:
            lines.append(f"| {row['method']} | niedostępne | {row['test_mean_final_score']:.3f} | — | — |")
        else:
            lines.append(f"| {row['method']} | {row['validation_500_mean_final_score']:.3f} | {row['test_mean_final_score']:.3f} | {row['absolute_gap_test_minus_validation']:.3f} | {row['relative_gap']:.2%} |")
    lines += ["", "## Strategia i powtarzalność", "",
              "Pełne znormalizowane metryki strategii i telemetria akcji znajdują się w CSV. Niedeterministyczność obejmuje rozrzut trzech powtórzeń, wariancję między seedami i ICC; nie wpływa na wybór zwycięzcy.", "",
              "## Artefakty", "",
              "Surowe epizody są w `raw/final_test_episodes.csv`, a tabele w katalogu głównym i `analysis/`.", "",
              "Wykresy PNG 300 dpi:", ""]
    for name in (
        "01_finalScore_violin_box.png", "02_finalScore_ecdf.png", "03_survivalTime_violin_box.png",
        "04_survival_kaplan_meier.png", "05_maxDuration_success_rate.png",
        "06_pairwise_finalScore_difference_forest.png", "07_method_seed_heatmap.png",
        "08_collision_and_life_loss_rates.png", "09_bonus_strategy_rates.png",
        "10_discrete_action_profiles.png", "11_continuous_steering_profiles.png",
        "12_validation_vs_test_generalization.png", "13_repeat_variability.png",
        "14_hardest_test_seeds.png", "15_failure_overlap_heatmap.png",
    ):
        lines.append(f"- [`{name}`](plots/{name})")
    lines.append("")
    (output / "FINAL_TEST_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def analyze_final_test(raw_path: Path, output: Path, protocol: dict[str, Any], selection: dict[str, Any],
                       *, strict: bool = True, write_plots: bool = True) -> dict[str, Any]:
    rows = load_rows(raw_path)
    seeds = validate_rows(rows, protocol, strict)
    seed_rows = aggregate_seed_rows(rows, seeds)
    omnibus, pairwise, method_rows = primary_statistics(seed_rows, seeds, protocol)
    winner = winner_decision(method_rows, omnibus, pairwise)
    actions = action_summary(rows)
    strategy = strategy_summary(rows)
    survival, curves = survival_outputs(rows, float(protocol["max_duration"]))
    nondet = nondeterminism(rows, seed_rows)
    generalization_rows = generalization(method_rows, selection)
    difficulty, relative_extremes = seed_difficulty(seed_rows, seeds)
    overlap_rows, overlap_matrix = failure_overlap(rows, seeds)
    analysis_dir = output / "analysis"
    analysis_dir.mkdir(exist_ok=True)
    write_csv(output / "final_test_per_seed.csv", seed_rows)
    write_csv(output / "final_test_method_summary.csv", method_rows)
    write_csv(output / "final_test_pairwise_statistics.csv", pairwise, ("method_a","method_b","n_seeds","mean_difference_a_minus_b","median_difference_a_minus_b","bootstrap_ci95_low","bootstrap_ci95_high","wilcoxon_statistic","p_raw","p_holm","significant_holm","paired_rank_biserial"))
    write_json(analysis_dir / "final_test_omnibus.json", omnibus)
    write_csv(output / "final_test_action_analytics.csv", actions)
    write_csv(output / "final_test_strategy_metrics.csv", strategy)
    write_csv(output / "final_test_generalization.csv", generalization_rows)
    write_csv(analysis_dir / "survival_summary.csv", survival)
    write_csv(analysis_dir / "nondeterminism_summary.csv", nondet)
    write_csv(analysis_dir / "test_seed_difficulty.csv", difficulty)
    write_csv(analysis_dir / "method_seed_relative_extremes.csv", relative_extremes)
    write_csv(analysis_dir / "failure_overlap.csv", overlap_rows)
    manifest_path = output / "final_test_run_manifest.json"
    schedule_path = output / "test_schedule.json"
    run_manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    summary = {"schema": 1, "valid_episodes": len(rows), "test_seeds": len(seeds),
               "analysis_unit": "seed", "method_summary": method_rows, "omnibus": omnibus,
               "winner_decision": winner, "pairwise_tests_performed": len(pairwise),
               "bootstrap_resamples": int(protocol["bootstrap_resamples"]),
               "survival_role": "descriptive", "protocol": protocol,
               "selected_models": selection["methods"],
               "test_schedule_sha256": file_sha256(schedule_path) if schedule_path.is_file() else None,
               "git_commit": run_manifest.get("git_commit"), "method_summaries": method_rows,
               "pairwise_statistics": pairwise, "secondary_metrics": method_rows,
               "strategy_metrics": strategy, "action_analytics": actions,
               "survival_summary": survival, "nondeterminism": nondet,
               "seed_difficulty": difficulty, "failure_overlap": overlap_rows,
               "generalization_gap": generalization_rows, "technical_integrity": run_manifest,
               "completion_status": {"status": "complete", "valid_episodes": len(rows),
                                     "expected_episodes": 3000 if strict else len(rows)}}
    write_json(output / "final_test_results.json", summary)
    if write_plots:
        generate_plots(rows, seed_rows, pairwise, curves, nondet, strategy, generalization_rows,
                       difficulty, overlap_matrix, output)
    render_report(output, protocol, selection, method_rows, omnibus, pairwise, winner, survival,
                  strategy, nondet, generalization_rows, run_manifest)
    return summary
