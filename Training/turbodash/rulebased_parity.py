from __future__ import annotations

import argparse
import hashlib
import json
import struct
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import numpy as np

from .final_rule_based import RuleBasedV1Policy
from .paths import REPOSITORY_ROOT
from .protocol import DiscreteAction, OBSERVATION_SIZE
from .seeds import file_sha256

MAGIC = b"TDRBPV1!"
HEADER = struct.Struct("<6i")
RECORD = struct.Struct("<iiBBI")
FLAG_NAMES = (
    "outside", "shield", "boost_active", "temporary_protection", "wall", "obstacle",
    "moving_hazard", "approximate_geometry", "heart", "shield_bonus", "boost_bonus",
    "sector_boundary", "reversal_sequence", "tube_0", "tube_1", "tube_2",
)


def action_name(value: int) -> str:
    return DiscreteAction(value).name


def read_corpus(path: Path) -> tuple[dict[str, int], Iterator[tuple[int, int, int, int, int, np.ndarray]]]:
    stream = path.open("rb")
    try:
        if stream.read(len(MAGIC)) != MAGIC:
            raise ValueError("RuleBased parity corpus magic is invalid")
        schema, observation_size, sequences, decisions_per_sequence, seed, records = HEADER.unpack(
            stream.read(HEADER.size)
        )
        metadata = {
            "schema": schema, "observation_size": observation_size, "sequence_count": sequences,
            "decisions_per_sequence": decisions_per_sequence, "generator_seed": seed,
            "observation_count": records,
        }
        if schema != 1 or observation_size != OBSERVATION_SIZE:
            raise ValueError("RuleBased parity corpus schema or observation size is invalid")
        if records != sequences * decisions_per_sequence or records < 10_000:
            raise ValueError("RuleBased parity corpus does not meet the prespecified size")

        def records_iterator():
            try:
                for _ in range(records):
                    record_bytes = stream.read(RECORD.size)
                    if len(record_bytes) != RECORD.size:
                        raise ValueError("RuleBased parity corpus ended in a record header")
                    sequence, decision, previous, action, flags = RECORD.unpack(record_bytes)
                    vector_bytes = stream.read(OBSERVATION_SIZE * 4)
                    if len(vector_bytes) != OBSERVATION_SIZE * 4:
                        raise ValueError("RuleBased parity corpus ended in an observation")
                    vector = np.frombuffer(vector_bytes, dtype="<f4").astype(np.float32, copy=True)
                    if not np.isfinite(vector).all():
                        raise ValueError("RuleBased parity corpus contains a non-finite observation")
                    yield sequence, decision, previous, action, flags, vector
                if stream.read(1):
                    raise ValueError("RuleBased parity corpus has trailing data")
            finally:
                stream.close()

        return metadata, records_iterator()
    except Exception:
        stream.close()
        raise


def compare_corpus(corpus: Path, report_path: Path, csharp_source: Path, python_source: Path,
                   oracle_source: Path, unity_version: str) -> dict[str, Any]:
    metadata, records = read_corpus(corpus)
    policy = RuleBasedV1Policy()
    coverage = Counter()
    csharp_actions = Counter()
    python_actions = Counter()
    previous_states = Counter()
    transitions = Counter()
    csharp_action_bytes = bytearray()
    python_action_bytes = bytearray()
    first_mismatch: dict[str, Any] | None = None
    mismatch_count = 0
    matches = 0
    last_sequence = -1
    expected_decision = 0
    previous_csharp = int(DiscreteAction.NONE)
    previous_python = int(DiscreteAction.NONE)

    for sequence, decision, recorded_previous, csharp_action, flags, observation in records:
        if sequence != last_sequence:
            if last_sequence >= 0 and expected_decision != metadata["decisions_per_sequence"]:
                raise ValueError("C# corpus has an incomplete decision sequence")
            if sequence != last_sequence + 1 or decision != 0:
                raise ValueError("C# corpus sequence order is invalid")
            policy.reset_slot(0)
            last_sequence = sequence
            expected_decision = 0
            previous_csharp = int(DiscreteAction.NONE)
            previous_python = int(DiscreteAction.NONE)
        if decision != expected_decision or recorded_previous != previous_csharp:
            raise ValueError("C# corpus previousAction or decision index is internally inconsistent")
        expected_decision += 1

        for bit, name in enumerate(FLAG_NAMES):
            if flags & (1 << bit):
                coverage[name] += 1
        coverage["inside"] += int(not bool(flags & 1))
        coverage["lives_zero"] += int(observation[0] == 0)
        coverage["lives_partial"] += int(0 < observation[0] < 1)
        coverage["lives_full"] += int(observation[0] == 1)

        python_previous = int(policy._previous.get(0, int(DiscreteAction.NONE)))
        if python_previous != previous_python:
            raise RuntimeError("Python parity harness lost previousAction state")
        python_action = int(policy.decide(observation, 0))
        csharp_action_bytes.append(csharp_action)
        python_action_bytes.append(python_action)
        csharp_actions[action_name(csharp_action)] += 1
        python_actions[action_name(python_action)] += 1
        previous_states[action_name(recorded_previous)] += 1
        transitions[f"{action_name(recorded_previous)}->{action_name(csharp_action)}"] += 1

        if python_action == csharp_action:
            matches += 1
        else:
            mismatch_count += 1
            if first_mismatch is None:
                bits = observation.view(np.uint32)
                first_mismatch = {
                    "sequence": sequence,
                    "decision_index": decision,
                    "csharp_previous_action": action_name(recorded_previous),
                    "python_previous_action": action_name(python_previous),
                    "csharp_action": action_name(csharp_action),
                    "python_action": action_name(python_action),
                    "coverage_flags": [name for bit, name in enumerate(FLAG_NAMES) if flags & (1 << bit)],
                    "observation_float32": [float(value) for value in observation],
                    "observation_float32_bits": [f"0x{int(value):08x}" for value in bits],
                }
        previous_csharp = csharp_action
        previous_python = python_action

    if last_sequence + 1 != metadata["sequence_count"] or expected_decision != metadata["decisions_per_sequence"]:
        raise ValueError("C# corpus sequence count is invalid")
    status = "PASS" if mismatch_count == 0 and matches == metadata["observation_count"] else "FAIL"
    report = {
        "schema": 1,
        "verification": "differential parity: production C# RuleBasedController vs Python RuleBasedV1Policy",
        "status": status,
        "pass_condition": "100% identical discrete actions",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "unity_version": unity_version,
        "test_data_status": "SYNTHETIC_OBSERVATIONS_ONLY; test.json UNREAD_AND_UNUSED; TEST episodes 0",
        "corpus": metadata,
        "corpus_sha256": file_sha256(corpus),
        "sources": {
            "csharp_controller": str(csharp_source.relative_to(REPOSITORY_ROOT)),
            "csharp_controller_sha256": file_sha256(csharp_source),
            "python_policy": str(python_source.relative_to(REPOSITORY_ROOT)),
            "python_policy_sha256": file_sha256(python_source),
            "csharp_oracle": str(oracle_source.relative_to(REPOSITORY_ROOT)),
            "csharp_oracle_sha256": file_sha256(oracle_source),
        },
        "result": {
            "compared_actions": metadata["observation_count"],
            "identical_actions": matches,
            "mismatch_count": mismatch_count,
            "match_rate": matches / metadata["observation_count"],
            "csharp_action_stream_sha256": hashlib.sha256(csharp_action_bytes).hexdigest(),
            "python_action_stream_sha256": hashlib.sha256(python_action_bytes).hexdigest(),
            "csharp_action_distribution": dict(csharp_actions),
            "python_action_distribution": dict(python_actions),
            "previous_action_state_distribution": dict(previous_states),
            "stateful_transition_distribution": dict(transitions),
        },
        "coverage_counts": {name: int(coverage[name]) for name in ("inside", *FLAG_NAMES,
                                                                    "lives_zero", "lives_partial", "lives_full")},
        "first_mismatch": first_mismatch,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if status != "PASS":
        raise RuntimeError(
            f"RuleBasedV1 parity FAILED: {mismatch_count} mismatches; first mismatch is in {report_path}"
        )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare C# and Python RuleBasedV1 on a binary float32 corpus")
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--unity-version", default="2022.3.4f1")
    parser.add_argument("--csharp-source", type=Path,
                        default=REPOSITORY_ROOT / "Assets/Turbo_Dash/Code/Research/RuleBasedController.cs")
    parser.add_argument("--python-source", type=Path,
                        default=REPOSITORY_ROOT / "Training/turbodash/final_rule_based.py")
    parser.add_argument("--oracle-source", type=Path,
                        default=REPOSITORY_ROOT / "Assets/Turbo_Dash/Code/Research/Editor/RuleBasedParityCorpus.cs")
    args = parser.parse_args()
    report = compare_corpus(args.corpus.resolve(), args.report.resolve(), args.csharp_source.resolve(),
                            args.python_source.resolve(), args.oracle_source.resolve(), args.unity_version)
    print(f"RuleBasedV1 differential parity: {report['status']} "
          f"({report['result']['identical_actions']}/{report['result']['compared_actions']} identical)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
