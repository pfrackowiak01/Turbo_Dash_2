from __future__ import annotations

import enum
import math
import struct
from dataclasses import dataclass

import numpy as np

TRANSPORT_VERSION = 1
RESEARCH_PROTOCOL_VERSION = 1
OBSERVATION_SCHEMA_VERSION = 2
OBSERVATION_SIZE = 236
FIXED_TIMESTEP = 0.01
DECISION_INTERVAL = 0.05
PHYSICS_TICKS_PER_STEP = 5


class Message(enum.IntEnum):
    HELLO = 1
    HELLO_ACCEPTED = 2
    RESET = 3
    RESET_RESULT = 4
    STEP = 5
    STEP_RESULT = 6
    CLOSE = 7
    CLOSE_ACCEPTED = 8
    ERROR = 255


class ActionSpace(enum.IntEnum):
    DISCRETE = 0
    CONTINUOUS = 1

    @classmethod
    def from_name(cls, value: str) -> "ActionSpace":
        try:
            return cls[value.strip().upper()]
        except (AttributeError, KeyError) as exc:
            raise ValueError("action_space must be Discrete or Continuous") from exc


class DiscreteAction(enum.IntEnum):
    LEFT = 0
    NONE = 1
    RIGHT = 2


TERMINAL_REASONS = {0: "", 1: "LivesExhausted", 2: "MaxDuration", 3: "MaxScore"}


class ProtocolError(RuntimeError):
    pass


@dataclass(frozen=True)
class Handshake:
    transport_version: int
    research_version: int
    observation_schema: int
    observation_size: int
    action_space: ActionSpace
    fixed_timestep: float
    decision_interval: float
    worker_id: int

    @classmethod
    def decode(cls, payload: bytes) -> "Handshake":
        expected = struct.calcsize("<BiiiiBffi")
        if len(payload) != expected:
            raise ProtocolError(f"HELLO length {len(payload)} differs from {expected}")
        values = struct.unpack("<BiiiiBffi", payload)
        if values[0] != Message.HELLO:
            raise ProtocolError(f"Expected HELLO, received message {values[0]}")
        try:
            action_space = ActionSpace(values[5])
        except ValueError as exc:
            raise ProtocolError(f"Unknown action space {values[5]}") from exc
        return cls(*values[1:5], action_space, *values[6:])

    def validate(self, worker_id: int, action_space: ActionSpace) -> None:
        expected = {
            "transport_version": TRANSPORT_VERSION,
            "research_version": RESEARCH_PROTOCOL_VERSION,
            "observation_schema": OBSERVATION_SCHEMA_VERSION,
            "observation_size": OBSERVATION_SIZE,
            "action_space": action_space,
            "worker_id": worker_id,
        }
        for name, value in expected.items():
            if getattr(self, name) != value:
                raise ProtocolError(f"Handshake {name}={getattr(self, name)!r}, expected {value!r}")
        if not math.isclose(self.fixed_timestep, FIXED_TIMESTEP, rel_tol=0, abs_tol=1e-6):
            raise ProtocolError(f"Handshake fixed_timestep={self.fixed_timestep}, expected {FIXED_TIMESTEP}")
        if not math.isclose(self.decision_interval, DECISION_INTERVAL, rel_tol=0, abs_tol=1e-6):
            raise ProtocolError(f"Handshake decision_interval={self.decision_interval}, expected {DECISION_INTERVAL}")


@dataclass
class StepResult:
    observation: np.ndarray
    reward: float
    terminated: bool
    truncated: bool
    info: dict


class PayloadReader:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.offset = 0

    def read(self, fmt: str):
        size = struct.calcsize("<" + fmt)
        if self.offset + size > len(self.payload):
            raise ProtocolError("Truncated bridge payload")
        values = struct.unpack_from("<" + fmt, self.payload, self.offset)
        self.offset += size
        return values[0] if len(values) == 1 else values

    def observation(self) -> np.ndarray:
        byte_count = OBSERVATION_SIZE * 4
        if self.offset + byte_count > len(self.payload):
            raise ProtocolError("Truncated observation")
        result = np.frombuffer(self.payload, dtype="<f4", count=OBSERVATION_SIZE, offset=self.offset).copy()
        self.offset += byte_count
        if result.dtype != np.float32 or result.shape != (OBSERVATION_SIZE,):
            raise ProtocolError("Observation shape or dtype mismatch")
        if not np.isfinite(result).all():
            raise ProtocolError("Observation contains NaN or Infinity")
        return result

    def finish(self) -> None:
        if self.offset != len(self.payload):
            raise ProtocolError(f"Unexpected {len(self.payload) - self.offset} trailing payload bytes")


def encode_reset(seed: int) -> bytes:
    if seed <= 0 or seed > 2_147_483_647:
        raise ValueError("seed must be a positive int32")
    return struct.pack("<Bi", Message.RESET, seed)


def encode_step(action: int | float, action_space: ActionSpace) -> bytes:
    if action_space == ActionSpace.DISCRETE:
        value = int(action)
        if value not in tuple(item.value for item in DiscreteAction):
            raise ValueError("Discrete action must be LEFT=0, NONE=1 or RIGHT=2")
        return struct.pack("<Bi", Message.STEP, value)
    value = float(action)
    if not math.isfinite(value):
        raise ValueError("Continuous action must be finite")
    value = min(1.0, max(-1.0, value))
    return struct.pack("<Bf", Message.STEP, value)


def encode_error(message: str) -> bytes:
    data = message.encode("utf-8")
    return struct.pack("<Bi", Message.ERROR, len(data)) + data


def decode_reset_result(payload: bytes) -> np.ndarray:
    reader = PayloadReader(payload)
    if reader.read("B") != Message.RESET_RESULT:
        raise ProtocolError("Expected RESET_RESULT")
    observation = reader.observation()
    reader.finish()
    return observation


def decode_step_result(payload: bytes) -> StepResult:
    reader = PayloadReader(payload)
    if reader.read("B") != Message.STEP_RESULT:
        raise ProtocolError("Expected STEP_RESULT")
    reward = float(reader.read("f"))
    terminated = bool(reader.read("B"))
    truncated = bool(reader.read("B"))
    physics_ticks = int(reader.read("i"))
    observation = reader.observation()
    keys = (
        "episode_id", "seed", "decision_count", "final_score", "survival_time",
        "segments_passed", "obstacles_encountered", "obstacles_avoided", "collisions",
        "life_loss_count", "shield_hits", "fatal_collision", "hearts_collected",
        "shields_collected", "boosts_collected", "turbo_activations", "gold_collected",
        "diamonds_collected", "max_level", "outside_stages_reached", "time_inside",
        "time_outside", "max_environment_speed", "episode_reward", "terminal_reason",
    )
    formats = ("i", "i", "i", "f", "f", "i", "i", "i", "i", "i", "i", "B",
               "i", "i", "i", "i", "i", "i", "i", "i", "f", "f", "f", "f", "B")
    values = [reader.read(fmt) for fmt in formats]
    reader.finish()
    info = dict(zip(keys, values))
    info["physics_ticks"] = physics_ticks
    info["fatal_collision"] = bool(info["fatal_collision"])
    reason_code = int(info["terminal_reason"])
    if reason_code not in TERMINAL_REASONS:
        raise ProtocolError(f"Unknown terminal reason code {reason_code}")
    info["terminal_reason"] = TERMINAL_REASONS[reason_code]
    if not math.isfinite(reward) or not math.isfinite(float(info["episode_reward"])):
        raise ProtocolError("Reward contains NaN or Infinity")
    if terminated and truncated:
        raise ProtocolError("A result cannot be both terminated and truncated")
    if terminated and info["terminal_reason"] != "LivesExhausted":
        raise ProtocolError("terminated must map to LivesExhausted")
    if truncated and info["terminal_reason"] not in ("MaxDuration", "MaxScore"):
        raise ProtocolError("truncated must map to a configured limit")
    return StepResult(observation, reward, terminated, truncated, info)
