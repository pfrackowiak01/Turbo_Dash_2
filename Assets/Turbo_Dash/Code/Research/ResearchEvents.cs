using System;

namespace TurboDash.Research
{
    public enum ResearchEventType
    {
        ScoreDelta, Collision, LifeLost, ShieldConsumed, HeartCollected,
        ShieldCollected, BoostCollected, TurboActivated, GoldCollected, DiamondCollected, Terminal
    }
    public readonly struct ResearchEvent
    {
        public readonly ResearchEventType Type;
        public readonly float Value;
        public readonly string Reason;
        public ResearchEvent(ResearchEventType type, float value = 1, string reason = null)
        { Type = type; Value = value; Reason = reason; }
    }
    public static class ResearchEvents
    {
        public static event Action<ResearchEvent> Raised;
        internal static void Clear() { Raised = null; }
        public static void Emit(ResearchEventType type, float value = 1, string reason = null)
        {
            if (!ResearchMode.Running) return;
            var data = new ResearchEvent(type, value, reason);
            ResearchMode.Instance.Record(data);
            Raised?.Invoke(data);
        }
    }
}
