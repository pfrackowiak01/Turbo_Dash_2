using System;
using UnityEngine;

namespace TurboDash.Research
{
    [Serializable]
    public sealed class RuleBasedParameters
    {
        public float wallCost = 14f;
        public float obstacleCost = 11f;
        public float movingCost = 3f;
        public float approximateCost = 1.5f;
        public float neighbourRisk = .45f;
        public float protectedRiskMultiplier = .2f;
        public float shieldRiskMultiplier = .45f;
        public float outsideRiskMultiplier = 1.15f;
        public float distanceUrgency = 2.5f;
        public float heartAttraction = 7f;
        public float shieldAttraction = 4f;
        public float boostAttraction = 2f;
        public float steeringCost = .22f;
        public float reversalCost = .8f;
        public float stayThreshold = .45f;

        public void Validate()
        {
            foreach (float value in new[] { wallCost, obstacleCost, movingCost, approximateCost, neighbourRisk,
                protectedRiskMultiplier, shieldRiskMultiplier, outsideRiskMultiplier, distanceUrgency,
                heartAttraction, shieldAttraction, boostAttraction, steeringCost, reversalCost, stayThreshold })
                if (float.IsNaN(value) || float.IsInfinity(value) || value < 0)
                    throw new ArgumentException("Rule-based parameters must be finite and non-negative.");
        }
    }

    // Deterministic receding-horizon baseline. The only input is Observation v2.
    public sealed class RuleBasedController : IResearchController
    {
        private readonly RuleBasedParameters parameters;
        private DiscreteAction previousAction = DiscreteAction.None;
        public string ControllerType => "RuleBasedV1";
        public ActionSpaceType ActionSpaceType => ActionSpaceType.Discrete;

        public RuleBasedController(RuleBasedParameters parameters = null)
        {
            this.parameters = parameters ?? new RuleBasedParameters();
            this.parameters.Validate();
        }
        public void ResetEpisode(int seed) { previousAction = DiscreteAction.None; }

        public SteeringAction Decide(ObservationFrame observation)
        {
            if (observation == null || observation.Vector == null || observation.Vector.Length != ObservationV2Layout.VectorSize)
                throw new ArgumentException("RuleBasedController requires Observation v2 (236 floats).", nameof(observation));
            float[] vector = observation.Vector;
            var costs = new float[ObservationV2Layout.SectorCount];
            bool protectedState = vector[ObservationV2Layout.BoostActive] > .5f || vector[ObservationV2Layout.TemporaryProtection] > .5f;
            float protection = protectedState ? parameters.protectedRiskMultiplier
                : vector[ObservationV2Layout.Shield] > .5f ? parameters.shieldRiskMultiplier : 1f;
            float locationRisk = vector[ObservationV2Layout.Outside] > .5f ? parameters.outsideRiskMultiplier : 1f;

            for (int tube = 0; tube < ObservationV2Layout.TubeCount; tube++)
            {
                int tubeOffset = ObservationV2Layout.TubeOffset(tube);
                if (vector[tubeOffset + ObservationV2Layout.TubeExists] < .5f) continue;
                float time = DecodeTime(vector[tubeOffset + ObservationV2Layout.TimeToReach]);
                float tubeWeight = 1f / (1f + time * parameters.distanceUrgency);
                for (int sector = 0; sector < ObservationV2Layout.SectorCount; sector++)
                {
                    int row = ObservationV2Layout.HazardOffset(tube, sector);
                    float occupancy = vector[row + ObservationV2Layout.WallOccupancy] * parameters.wallCost +
                        vector[row + ObservationV2Layout.ObstacleOccupancy] * parameters.obstacleCost;
                    if (occupancy <= 0) continue;
                    float risk = occupancy + vector[row + ObservationV2Layout.MovingHazard] * parameters.movingCost +
                        vector[row + ObservationV2Layout.ApproximateGeometry] * parameters.approximateCost;
                    risk *= tubeWeight * protection * locationRisk;
                    costs[sector] += risk;
                    costs[Wrap(sector - 1)] += risk * parameters.neighbourRisk;
                    costs[Wrap(sector + 1)] += risk * parameters.neighbourRisk;
                }
                AddBonusAttraction(costs, vector, tube, 0,
                    parameters.heartAttraction * Mathf.Clamp01(1f - vector[ObservationV2Layout.Lives]), tubeWeight);
                AddBonusAttraction(costs, vector, tube, 1,
                    vector[ObservationV2Layout.Shield] > .5f ? 0 : parameters.shieldAttraction, tubeWeight);
                AddBonusAttraction(costs, vector, tube, 2,
                    vector[ObservationV2Layout.BoostActive] > .5f ? 0 : parameters.boostAttraction * Mathf.Clamp01(1f - vector[ObservationV2Layout.BoostCharge]), tubeWeight);
            }

            const int currentSector = 6;
            int best = currentSector;
            float bestCost = costs[currentSector];
            for (int sector = 0; sector < costs.Length; sector++)
            {
                int distance = CircularDistance(currentSector, sector);
                float candidate = costs[sector] + distance * parameters.steeringCost;
                DiscreteAction direction = DirectionTo(sector);
                if (previousAction != DiscreteAction.None && direction != DiscreteAction.None && direction != previousAction)
                    candidate += parameters.reversalCost;
                if (candidate < bestCost)
                {
                    bestCost = candidate;
                    best = sector;
                }
            }

            DiscreteAction action = costs[currentSector] - bestCost < parameters.stayThreshold
                ? DiscreteAction.None : DirectionTo(best);
            previousAction = action;
            return SteeringAction.FromDiscrete(action);
        }

        private static void AddBonusAttraction(float[] costs, float[] vector, int tube, int bonus, float attraction, float tubeWeight)
        {
            int row = ObservationV2Layout.BonusOffset(tube, bonus);
            if (attraction <= 0 || vector[row] < .5f) return;
            float angle = Mathf.Atan2(vector[row + 1], vector[row + 2]);
            int nearest = Wrap(Mathf.RoundToInt((angle + Mathf.PI) / (2f * Mathf.PI) * ObservationV2Layout.SectorCount));
            float distanceWeight = 1f - Mathf.Clamp01(vector[row + 3]);
            float value = attraction * tubeWeight * distanceWeight;
            costs[nearest] -= value;
            costs[Wrap(nearest - 1)] -= value * .25f;
            costs[Wrap(nearest + 1)] -= value * .25f;
        }
        private static float DecodeTime(float normalized)
            => normalized >= .999999f ? 1000000f : Mathf.Max(0, normalized) / Mathf.Max(.000001f, 1f - normalized);
        private static int Wrap(int sector)
        {
            while (sector < 0) sector += ObservationV2Layout.SectorCount;
            return sector % ObservationV2Layout.SectorCount;
        }
        private static int CircularDistance(int a, int b)
        {
            int direct = Mathf.Abs(a - b);
            return Mathf.Min(direct, ObservationV2Layout.SectorCount - direct);
        }
        private static DiscreteAction DirectionTo(int sector)
        {
            float angle = ObservationV2Layout.SectorCenter(sector);
            if (Mathf.Abs(angle) < .0001f) return DiscreteAction.None;
            return angle > 0 ? DiscreteAction.Left : DiscreteAction.Right;
        }
    }
}
