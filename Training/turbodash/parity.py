from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

FLOAT_TOLERANCES = {"survivalTime": 0.15}
INTEGER_TOLERANCES = {"collisionsTotal": 1, "obstaclesAvoided": 1}
EXACT_FIELDS = ("lifeLossCount", "maxLevel", "terminalReason")


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare Editor and standalone RuleBasedV1 CSV output")
    parser.add_argument("--editor", type=Path, required=True)
    parser.add_argument("--standalone", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    editor = read_rows(args.editor)
    standalone = read_rows(args.standalone)
    if len(editor) != 5 or len(standalone) != 5:
        raise AssertionError(f"Parity requires 5+5 episodes, got {len(editor)}+{len(standalone)}")
    comparisons = []
    passed = True
    for editor_row, standalone_row in zip(editor, standalone):
        if editor_row["seed"] != standalone_row["seed"]:
            raise AssertionError("Editor and standalone seed order differs")
        fields = {}
        score_difference = abs(float(editor_row["finalScore"]) - float(standalone_row["finalScore"]))
        score_tolerance = max(1.0, 0.01 * max(abs(float(editor_row["finalScore"])), abs(float(standalone_row["finalScore"]))))
        fields["finalScore"] = {"editor": float(editor_row["finalScore"]),
                                "standalone": float(standalone_row["finalScore"]),
                                "difference": score_difference, "tolerance": score_tolerance,
                                "passed": score_difference <= score_tolerance}
        passed = passed and score_difference <= score_tolerance
        for field, tolerance in FLOAT_TOLERANCES.items():
            difference = abs(float(editor_row[field]) - float(standalone_row[field]))
            fields[field] = {"editor": float(editor_row[field]), "standalone": float(standalone_row[field]),
                             "difference": difference, "tolerance": tolerance, "passed": difference <= tolerance}
            passed = passed and difference <= tolerance
        for field, tolerance in INTEGER_TOLERANCES.items():
            difference = abs(int(editor_row[field]) - int(standalone_row[field]))
            fields[field] = {"editor": int(editor_row[field]), "standalone": int(standalone_row[field]),
                             "difference": difference, "tolerance": tolerance, "passed": difference <= tolerance}
            passed = passed and difference <= tolerance
        for field in EXACT_FIELDS:
            equal = editor_row[field] == standalone_row[field]
            fields[field] = {"editor": editor_row[field], "standalone": standalone_row[field], "passed": equal}
            passed = passed and equal
        comparisons.append({"seed": int(editor_row["seed"]), "fields": fields})
    report = {
        "passed": passed,
        "episodes": 5,
        "controller": "RuleBasedV1",
        "time_scale": 20,
        "max_duration": 30,
        "standalone_flags": ["-batchmode", "-nographics"],
        "comparisons": comparisons,
        "test_status": "UNUSED",
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not passed:
        raise AssertionError("Standalone parity exceeded the accepted runtime tolerance")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
