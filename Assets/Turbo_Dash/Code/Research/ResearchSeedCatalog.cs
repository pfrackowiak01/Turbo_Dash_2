using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;

namespace TurboDash.Research
{
    public enum ResearchSeedSplit { Train, Validation, Test }

    [Serializable]
    public sealed class ResearchSeedFile
    {
        public int protocolVersion;
        public string split;
        public int[] seeds;
    }

    public static class ResearchSeedCatalog
    {
        public const int TrainCount = 700, ValidationCount = 100, TestCount = 200;
        public static string DefaultDirectory => Path.Combine(Application.dataPath, "Turbo_Dash", "Research", "Seeds");

        public static int[] Load(ResearchSeedSplit split, string directory = null)
        {
            string name = split.ToString().ToLowerInvariant();
            string path = Path.Combine(directory ?? DefaultDirectory, name + ".json");
            if (!File.Exists(path)) throw new FileNotFoundException("Research seed source of truth is missing.", path);
            ResearchSeedFile file = JsonUtility.FromJson<ResearchSeedFile>(File.ReadAllText(path));
            if (file == null || file.protocolVersion != ResearchProtocolV1.Version ||
                !string.Equals(file.split, name, StringComparison.OrdinalIgnoreCase) || file.seeds == null)
                throw new InvalidDataException("Invalid seed file: " + path);
            int expected = split == ResearchSeedSplit.Train ? TrainCount :
                split == ResearchSeedSplit.Validation ? ValidationCount : TestCount;
            if (file.seeds.Length != expected) throw new InvalidDataException(name + " must contain " + expected + " seeds.");
            return file.seeds;
        }

        public static void ValidateAll(string directory = null)
        {
            var unique = new HashSet<int>();
            foreach (ResearchSeedSplit split in Enum.GetValues(typeof(ResearchSeedSplit)))
                foreach (int seed in Load(split, directory))
                    if (seed <= 0 || !unique.Add(seed))
                        throw new InvalidDataException("Seed values must be positive and globally unique: " + seed);
            if (unique.Count != TrainCount + ValidationCount + TestCount)
                throw new InvalidDataException("Seed catalog size differs from protocol v1.");
        }
    }
}
