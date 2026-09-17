using System;
using System.IO;
using System.Text;
using UnityEngine;

namespace TurboDash.Research.Editor
{
    // Editor-only differential oracle. It invokes the production RuleBasedController unchanged.
    public static class RuleBasedParityCorpus
    {
        private const int CorpusSchema = 1;
        private const int CorpusSeed = 20261002;
        private const int SequenceCount = 1000;
        private const int DecisionsPerSequence = 12;

        private const uint Outside = 1u << 0;
        private const uint Shield = 1u << 1;
        private const uint Boost = 1u << 2;
        private const uint Protection = 1u << 3;
        private const uint Wall = 1u << 4;
        private const uint Obstacle = 1u << 5;
        private const uint Moving = 1u << 6;
        private const uint Approximate = 1u << 7;
        private const uint Heart = 1u << 8;
        private const uint ShieldBonus = 1u << 9;
        private const uint BoostBonus = 1u << 10;
        private const uint SectorBoundary = 1u << 11;
        private const uint ReversalSequence = 1u << 12;
        private const uint Tube0 = 1u << 13;
        private const uint Tube1 = 1u << 14;
        private const uint Tube2 = 1u << 15;

        public static void Generate()
        {
            string[] args = Environment.GetCommandLineArgs();
            int index = Array.IndexOf(args, "--rulebased-parity-output");
            if (index < 0 || index + 1 >= args.Length)
                throw new ArgumentException("--rulebased-parity-output <path> is required.");
            string output = Path.GetFullPath(args[index + 1]);
            Directory.CreateDirectory(Path.GetDirectoryName(output));

            var random = new XorShift32(CorpusSeed);
            using (var stream = new FileStream(output, FileMode.Create, FileAccess.Write, FileShare.None))
            using (var writer = new BinaryWriter(stream, Encoding.UTF8, false))
            {
                writer.Write(Encoding.ASCII.GetBytes("TDRBPV1!"));
                writer.Write(CorpusSchema);
                writer.Write(ObservationV2Layout.VectorSize);
                writer.Write(SequenceCount);
                writer.Write(DecisionsPerSequence);
                writer.Write(CorpusSeed);
                writer.Write(SequenceCount * DecisionsPerSequence);

                for (int sequence = 0; sequence < SequenceCount; sequence++)
                {
                    var controller = new RuleBasedController();
                    controller.ResetEpisode(CorpusSeed + sequence);
                    DiscreteAction previous = DiscreteAction.None;
                    for (int decision = 0; decision < DecisionsPerSequence; decision++)
                    {
                        int globalIndex = sequence * DecisionsPerSequence + decision;
                        uint flags;
                        float[] vector = CreateObservation(ref random, sequence, decision, globalIndex, out flags);
                        SteeringAction steering = controller.Decide(new ObservationFrame(vector));
                        DiscreteAction action = steering.Value > .5f ? DiscreteAction.Left
                            : steering.Value < -.5f ? DiscreteAction.Right : DiscreteAction.None;
                        writer.Write(sequence);
                        writer.Write(decision);
                        writer.Write((byte)previous);
                        writer.Write((byte)action);
                        writer.Write(flags);
                        for (int value = 0; value < vector.Length; value++) writer.Write(vector[value]);
                        previous = action;
                    }
                }
            }
            Debug.Log("RuleBasedV1 parity corpus written: " + output + " (" +
                      (SequenceCount * DecisionsPerSequence) + " decisions).");
        }

        private static float[] CreateObservation(ref XorShift32 random, int sequence, int decision,
                                                 int globalIndex, out uint flags)
        {
            var vector = new float[ObservationV2Layout.VectorSize];
            float[] lives = { 0f, .25f, .5f, .75f, 1f };
            float[] normalizedTimes = { 0f, .000001f, .05f, .25f, .5f, .9f, .999998f, .999999f, 1f };
            float[] thresholds = { 0f, .49999994f, .5f, .50000006f, 1f };
            vector[ObservationV2Layout.Lives] = lives[globalIndex % lives.Length];
            vector[ObservationV2Layout.Shield] = thresholds[(globalIndex / 3) % thresholds.Length];
            vector[ObservationV2Layout.BoostCharge] = globalIndex % 7 == 0 ? 1f : random.NextFloat();
            vector[ObservationV2Layout.BoostActive] = thresholds[(globalIndex / 5 + 1) % thresholds.Length];
            vector[ObservationV2Layout.TemporaryProtection] = thresholds[(globalIndex / 7 + 2) % thresholds.Length];
            vector[ObservationV2Layout.Speed] = random.NextFloat();
            vector[ObservationV2Layout.Outside] = thresholds[(globalIndex / 11 + 3) % thresholds.Length];
            vector[ObservationV2Layout.Level] = random.NextFloat();

            flags = 0;
            if (vector[ObservationV2Layout.Outside] > .5f) flags |= Outside;
            if (vector[ObservationV2Layout.Shield] > .5f) flags |= Shield;
            if (vector[ObservationV2Layout.BoostActive] > .5f) flags |= Boost;
            if (vector[ObservationV2Layout.TemporaryProtection] > .5f) flags |= Protection;

            for (int tube = 0; tube < ObservationV2Layout.TubeCount; tube++)
            {
                int tubeOffset = ObservationV2Layout.TubeOffset(tube);
                bool exists = ((globalIndex + tube * 5) % 9 != 0) || random.NextFloat() > .35f;
                vector[tubeOffset + ObservationV2Layout.TubeExists] = exists ? 1f : 0f;
                vector[tubeOffset + ObservationV2Layout.TimeToReach] = normalizedTimes[(globalIndex + tube * 3) % normalizedTimes.Length];
                vector[tubeOffset + ObservationV2Layout.HasPortal] = random.NextFloat() > .5f ? 1f : 0f;
                vector[tubeOffset + ObservationV2Layout.HasHazard] = random.NextFloat() > .25f ? 1f : 0f;
                if (exists) flags |= tube == 0 ? Tube0 : tube == 1 ? Tube1 : Tube2;

                for (int sector = 0; sector < ObservationV2Layout.SectorCount; sector++)
                {
                    int row = ObservationV2Layout.HazardOffset(tube, sector);
                    float wall = random.NextFloat() < .24f ? Occupancy(ref random, globalIndex + sector) : 0f;
                    float obstacle = random.NextFloat() < .24f ? Occupancy(ref random, globalIndex + tube + sector) : 0f;
                    vector[row + ObservationV2Layout.WallOccupancy] = wall;
                    vector[row + ObservationV2Layout.ObstacleOccupancy] = obstacle;
                    vector[row + ObservationV2Layout.NearestHazardDistance] = random.NextFloat();
                    vector[row + ObservationV2Layout.MovingHazard] = random.NextFloat() < .35f ? 1f : 0f;
                    vector[row + ObservationV2Layout.ApproximateGeometry] = random.NextFloat() < .35f ? 1f : 0f;
                    if (wall > 0) flags |= Wall;
                    if (obstacle > 0) flags |= Obstacle;
                    if ((wall > 0 || obstacle > 0) && vector[row + ObservationV2Layout.MovingHazard] > .5f) flags |= Moving;
                    if ((wall > 0 || obstacle > 0) && vector[row + ObservationV2Layout.ApproximateGeometry] > .5f) flags |= Approximate;
                }

                for (int bonus = 0; bonus < ObservationV2Layout.StrategicBonusCount; bonus++)
                {
                    int row = ObservationV2Layout.BonusOffset(tube, bonus);
                    bool present = random.NextFloat() < .42f;
                    vector[row] = present ? 1f : 0f;
                    bool boundary = (globalIndex + tube * 3 + bonus) % 17 == 0;
                    int sector = (globalIndex + tube * 7 + bonus * 3) % ObservationV2Layout.SectorCount;
                    float epsilon = new[] { 0f, -1e-7f, 1e-7f, -1e-5f, 1e-5f }[globalIndex % 5];
                    float angle = boundary
                        ? -Mathf.PI + (sector + .5f) * (2f * Mathf.PI / ObservationV2Layout.SectorCount) + epsilon
                        : -Mathf.PI + random.NextFloat() * 2f * Mathf.PI;
                    vector[row + 1] = Mathf.Sin(angle);
                    vector[row + 2] = Mathf.Cos(angle);
                    vector[row + 3] = thresholds[(globalIndex + tube + bonus) % thresholds.Length];
                    if (present)
                    {
                        flags |= bonus == 0 ? Heart : bonus == 1 ? ShieldBonus : BoostBonus;
                        if (boundary) flags |= SectorBoundary;
                    }
                }
            }

            // First 240 sequences deliberately alternate the safer side. This exercises
            // previousAction and reversalCost repeatedly, not just independent decisions.
            if (sequence < 240)
            {
                flags &= ~(Tube1 | Tube2 | Wall | Obstacle | Moving | Approximate |
                           Heart | ShieldBonus | BoostBonus | SectorBoundary);
                for (int tube = 0; tube < ObservationV2Layout.TubeCount; tube++)
                {
                    int tubeOffset = ObservationV2Layout.TubeOffset(tube);
                    vector[tubeOffset + ObservationV2Layout.TubeExists] = tube == 0 ? 1f : 0f;
                    for (int sector = 0; sector < ObservationV2Layout.SectorCount; sector++)
                    {
                        int row = ObservationV2Layout.HazardOffset(tube, sector);
                        vector[row + ObservationV2Layout.WallOccupancy] = 0;
                        vector[row + ObservationV2Layout.ObstacleOccupancy] = 0;
                        vector[row + ObservationV2Layout.MovingHazard] = 0;
                        vector[row + ObservationV2Layout.ApproximateGeometry] = 0;
                    }
                    for (int bonus = 0; bonus < ObservationV2Layout.StrategicBonusCount; bonus++)
                        vector[ObservationV2Layout.BonusOffset(tube, bonus)] = 0;
                }
                int first = decision % 2 == 0 ? 6 : 0;
                int last = decision % 2 == 0 ? 11 : 6;
                for (int sector = first; sector <= last; sector++)
                {
                    int row = ObservationV2Layout.HazardOffset(0, sector);
                    vector[row + ObservationV2Layout.WallOccupancy] = 1f;
                    vector[row + ObservationV2Layout.MovingHazard] = 1f;
                    vector[row + ObservationV2Layout.ApproximateGeometry] = sector % 2;
                }
                flags |= ReversalSequence | Tube0 | Wall | Moving | Approximate;
            }
            return vector;
        }

        private static float Occupancy(ref XorShift32 random, int index)
        {
            float[] boundaryValues = { .000001f, .01f, .1f, .49999994f, .5f, .50000006f, .9f, 1f };
            return index % 4 == 0 ? boundaryValues[index % boundaryValues.Length] : random.NextFloat();
        }

        private struct XorShift32
        {
            private uint state;
            public XorShift32(int seed) { state = unchecked((uint)seed); if (state == 0) state = 0x6d2b79f5u; }
            public uint NextUInt()
            {
                uint value = state;
                value ^= value << 13;
                value ^= value >> 17;
                value ^= value << 5;
                state = value;
                return value;
            }
            public float NextFloat() => (NextUInt() >> 8) * (1f / 16777216f);
        }
    }
}
