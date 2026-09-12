using System;
using UnityEngine;

namespace TurboDash.Research
{
    public static class GameplayRandom
    {
        private static uint state;
        public static void Reset(int seed) { state = unchecked((uint)seed) ^ 0x9E3779B9u; if (state == 0) state = 1; }
        private static uint Next()
        {
            state ^= state << 13; state ^= state >> 17; state ^= state << 5;
            return state;
        }
        public static int Range(int minInclusive, int maxExclusive)
        {
            if (!ResearchMode.Active) return UnityEngine.Random.Range(minInclusive, maxExclusive);
            if (maxExclusive <= minInclusive) throw new ArgumentOutOfRangeException(nameof(maxExclusive));
            uint range = (uint)(maxExclusive - minInclusive);
            // Rejection sampling on the nonzero xorshift32 output space.
            uint limit = uint.MaxValue - uint.MaxValue % range;
            uint sample;
            do { sample = Next(); } while (sample > limit);
            return minInclusive + (int)((sample - 1) % range);
        }
    }
}
