using System;
using UnityEngine;

namespace TurboDash.Research
{
    public static class ResearchProtocolV1
    {
        public const int Version = 1;
        public const float FixedTimestep = .01f;
        public const float DecisionInterval = .05f;
        public const int PhysicsTicksPerDecision = 5;
        public const int DecisionsPerSecond = 20;
        public const float DefaultMaxDuration = 300f;

        public static void ValidateRuntime()
        {
            if (Mathf.Abs(Time.fixedDeltaTime - FixedTimestep) > .000001f)
                throw new InvalidOperationException("Research Protocol v1 requires Fixed Timestep 0.01 s.");
        }
    }

    [Serializable]
    public sealed class PilotRewardParameters
    {
        public float scoreScale = .01f;
        public float lifeLossPenalty = .5f;

        public void Validate()
        {
            if (float.IsNaN(scoreScale) || float.IsInfinity(scoreScale) || scoreScale < 0 ||
                float.IsNaN(lifeLossPenalty) || float.IsInfinity(lifeLossPenalty) || lifeLossPenalty < 0)
                throw new ArgumentException("Pilot reward parameters must be finite and non-negative.");
        }
    }

    public sealed class PilotRewardCalculator
    {
        private readonly PilotRewardParameters parameters;
        private float pendingScoreDelta;
        private int pendingLifeLoss;
        public float EpisodeReward { get; private set; }
        public float LastDecisionReward { get; private set; }

        public PilotRewardCalculator(PilotRewardParameters parameters)
        {
            this.parameters = parameters ?? throw new ArgumentNullException(nameof(parameters));
            parameters.Validate();
        }
        public void Reset()
        {
            pendingScoreDelta = 0;
            pendingLifeLoss = 0;
            EpisodeReward = 0;
            LastDecisionReward = 0;
        }
        public void Record(ResearchEvent data)
        {
            if (data.Type == ResearchEventType.ScoreDelta) pendingScoreDelta += data.Value;
            else if (data.Type == ResearchEventType.LifeLost) pendingLifeLoss += Mathf.RoundToInt(data.Value);
        }
        public float CloseDecisionInterval()
        {
            LastDecisionReward = pendingScoreDelta * parameters.scoreScale - pendingLifeLoss * parameters.lifeLossPenalty;
            EpisodeReward += LastDecisionReward;
            pendingScoreDelta = 0;
            pendingLifeLoss = 0;
            return LastDecisionReward;
        }
        public float Fitness(float finalScore, int lifeLossCount)
            => finalScore * parameters.scoreScale - lifeLossCount * parameters.lifeLossPenalty;
    }

    public sealed class DecisionScheduler
    {
        private int ticksSinceDecision;
        public int PhysicsTickCount { get; private set; }
        public int DecisionCount { get; private set; }
        public SteeringAction HeldAction { get; private set; }

        public void Reset()
        {
            ticksSinceDecision = 0;
            PhysicsTickCount = 0;
            DecisionCount = 0;
            HeldAction = new SteeringAction(0);
        }
        public SteeringAction Tick(Func<ObservationFrame> capture, Func<ObservationFrame, SteeringAction> decide,
            Action beforeDecision = null)
        {
            if (capture == null) throw new ArgumentNullException(nameof(capture));
            if (decide == null) throw new ArgumentNullException(nameof(decide));
            if (ticksSinceDecision == 0)
            {
                beforeDecision?.Invoke();
                HeldAction = decide(capture());
                DecisionCount++;
            }
            PhysicsTickCount++;
            ticksSinceDecision++;
            if (ticksSinceDecision == ResearchProtocolV1.PhysicsTicksPerDecision) ticksSinceDecision = 0;
            return HeldAction;
        }
    }
}
