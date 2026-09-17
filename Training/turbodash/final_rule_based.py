from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from .protocol import DiscreteAction, OBSERVATION_SIZE


@dataclass(frozen=True)
class RuleBasedV1Parameters:
    wall_cost: float = 14.0
    obstacle_cost: float = 11.0
    moving_cost: float = 3.0
    approximate_cost: float = 1.5
    neighbour_risk: float = 0.45
    protected_risk_multiplier: float = 0.2
    shield_risk_multiplier: float = 0.45
    outside_risk_multiplier: float = 1.15
    distance_urgency: float = 2.5
    heart_attraction: float = 7.0
    shield_attraction: float = 4.0
    boost_attraction: float = 2.0
    steering_cost: float = 0.22
    reversal_cost: float = 0.8
    stay_threshold: float = 0.45


class RuleBasedV1Policy:
    """Inference-only port of the frozen C# RuleBasedController.

    State is kept per Unity worker because ``previousAction`` is episode-local in
    the C# implementation. Calculations are intentionally float32 where Unity's
    controller uses ``float``.
    """

    GLOBAL_SIZE = 8
    TUBE_COUNT = 3
    TUBE_HEADER_SIZE = 4
    SECTOR_COUNT = 12
    HAZARD_FEATURES = 5
    HAZARD_GRID_SIZE = 60
    BONUS_COUNT = 3
    BONUS_FEATURES = 4
    TUBE_SIZE = 76

    LIVES, SHIELD, BOOST_CHARGE, BOOST_ACTIVE = 0, 1, 2, 3
    TEMPORARY_PROTECTION, OUTSIDE = 4, 6
    TUBE_EXISTS, TIME_TO_REACH = 0, 1
    WALL_OCCUPANCY, OBSTACLE_OCCUPANCY = 0, 1
    MOVING_HAZARD, APPROXIMATE_GEOMETRY = 3, 4

    def __init__(self, parameters: RuleBasedV1Parameters | None = None):
        self.p = parameters or RuleBasedV1Parameters()
        self._previous: dict[int, int] = {}

    def reset_slot(self, slot: int) -> None:
        self._previous[int(slot)] = int(DiscreteAction.NONE)

    @classmethod
    def tube_offset(cls, tube: int) -> int:
        return cls.GLOBAL_SIZE + tube * cls.TUBE_SIZE

    @classmethod
    def hazard_offset(cls, tube: int, sector: int) -> int:
        return cls.tube_offset(tube) + cls.TUBE_HEADER_SIZE + sector * cls.HAZARD_FEATURES

    @classmethod
    def bonus_offset(cls, tube: int, bonus: int) -> int:
        return cls.tube_offset(tube) + cls.TUBE_HEADER_SIZE + cls.HAZARD_GRID_SIZE + bonus * cls.BONUS_FEATURES

    @classmethod
    def _direction_to(cls, sector: int) -> int:
        angle = np.float32(-math.pi) + np.float32(sector) * (
            np.float32(2.0 * math.pi) / np.float32(cls.SECTOR_COUNT)
        )
        if abs(float(angle)) < 0.0001:
            return int(DiscreteAction.NONE)
        return int(DiscreteAction.LEFT if angle > 0 else DiscreteAction.RIGHT)

    @classmethod
    def _distance(cls, a: int, b: int) -> int:
        direct = abs(a - b)
        return min(direct, cls.SECTOR_COUNT - direct)

    @staticmethod
    def _decode_time(normalized: np.float32) -> np.float32:
        if normalized >= np.float32(0.999999):
            return np.float32(1_000_000.0)
        return np.maximum(np.float32(0.0), normalized) / np.maximum(
            np.float32(0.000001), np.float32(1.0) - normalized
        )

    def decide(self, observation: np.ndarray, slot: int) -> int:
        vector = np.asarray(observation, dtype=np.float32)
        if vector.shape != (OBSERVATION_SIZE,) or not np.isfinite(vector).all():
            raise ValueError(f"RuleBasedV1 requires one finite {OBSERVATION_SIZE}-float observation")
        p = self.p
        costs = np.zeros(self.SECTOR_COUNT, dtype=np.float32)
        protected = vector[self.BOOST_ACTIVE] > 0.5 or vector[self.TEMPORARY_PROTECTION] > 0.5
        protection = p.protected_risk_multiplier if protected else (
            p.shield_risk_multiplier if vector[self.SHIELD] > 0.5 else 1.0
        )
        location_risk = p.outside_risk_multiplier if vector[self.OUTSIDE] > 0.5 else 1.0

        for tube in range(self.TUBE_COUNT):
            tube_offset = self.tube_offset(tube)
            if vector[tube_offset + self.TUBE_EXISTS] < 0.5:
                continue
            decoded_time = self._decode_time(vector[tube_offset + self.TIME_TO_REACH])
            tube_weight = np.float32(1.0) / (
                np.float32(1.0) + decoded_time * np.float32(p.distance_urgency)
            )
            for sector in range(self.SECTOR_COUNT):
                row = self.hazard_offset(tube, sector)
                occupancy = (
                    vector[row + self.WALL_OCCUPANCY] * np.float32(p.wall_cost)
                    + vector[row + self.OBSTACLE_OCCUPANCY] * np.float32(p.obstacle_cost)
                )
                if occupancy <= 0:
                    continue
                risk = occupancy + (
                    vector[row + self.MOVING_HAZARD] * np.float32(p.moving_cost)
                    + vector[row + self.APPROXIMATE_GEOMETRY] * np.float32(p.approximate_cost)
                )
                risk *= tube_weight * np.float32(protection) * np.float32(location_risk)
                costs[sector] += risk
                costs[(sector - 1) % self.SECTOR_COUNT] += risk * np.float32(p.neighbour_risk)
                costs[(sector + 1) % self.SECTOR_COUNT] += risk * np.float32(p.neighbour_risk)

            attractions = (
                p.heart_attraction * float(np.clip(np.float32(1.0) - vector[self.LIVES], 0.0, 1.0)),
                0.0 if vector[self.SHIELD] > 0.5 else p.shield_attraction,
                0.0 if vector[self.BOOST_ACTIVE] > 0.5 else p.boost_attraction
                * float(np.clip(np.float32(1.0) - vector[self.BOOST_CHARGE], 0.0, 1.0)),
            )
            for bonus, attraction in enumerate(attractions):
                row = self.bonus_offset(tube, bonus)
                if attraction <= 0 or vector[row] < 0.5:
                    continue
                angle = np.float32(math.atan2(float(vector[row + 1]), float(vector[row + 2])))
                raw = (angle + np.float32(math.pi)) / np.float32(2.0 * math.pi) * np.float32(self.SECTOR_COUNT)
                nearest = int(np.rint(raw)) % self.SECTOR_COUNT
                distance_weight = np.float32(1.0) - np.clip(vector[row + 3], np.float32(0), np.float32(1))
                value = np.float32(attraction) * tube_weight * distance_weight
                costs[nearest] -= value
                costs[(nearest - 1) % self.SECTOR_COUNT] -= value * np.float32(0.25)
                costs[(nearest + 1) % self.SECTOR_COUNT] -= value * np.float32(0.25)

        current = 6
        best = current
        best_cost = np.float32(costs[current])
        previous = self._previous.get(int(slot), int(DiscreteAction.NONE))
        for sector in range(self.SECTOR_COUNT):
            direction = self._direction_to(sector)
            candidate = costs[sector] + np.float32(self._distance(current, sector) * p.steering_cost)
            if previous != int(DiscreteAction.NONE) and direction != int(DiscreteAction.NONE) and direction != previous:
                candidate += np.float32(p.reversal_cost)
            if candidate < best_cost:
                best_cost = np.float32(candidate)
                best = sector
        action = (
            int(DiscreteAction.NONE)
            if costs[current] - best_cost < np.float32(p.stay_threshold)
            else self._direction_to(best)
        )
        self._previous[int(slot)] = action
        return action

    def predict_slots(self, observations: np.ndarray, slots: list[int]) -> np.ndarray:
        batch = np.asarray(observations, dtype=np.float32)
        if batch.shape != (len(slots), OBSERVATION_SIZE):
            raise ValueError("RuleBasedV1 batch shape or worker-slot count is invalid")
        return np.asarray([self.decide(obs, slot) for obs, slot in zip(batch, slots)], dtype=np.int64)
