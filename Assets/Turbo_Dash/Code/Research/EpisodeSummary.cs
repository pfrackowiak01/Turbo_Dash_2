using System;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;

namespace TurboDash.Research
{
    [Serializable]
    public sealed class EpisodeSummary
    {
        public int episodeId;
        public string controllerType, actionSpaceType;
        public int seed;
        public float finalScore, survivalTime;
        public int segmentsPassed, obstaclesEncountered, obstaclesAvoided;
        public int collisionsTotal, lifeLossCount, shieldHits;
        public bool fatalCollision;
        public int heartsCollected, shieldsCollected, boostsCollected, goldCollected, diamondsCollected;
        public int maxLevel = 1, outsideStagesReached;
        public float timeInside, timeOutside, maxEnvironmentSpeed = 50;
        public string terminalReason;
        public string trainingRunId = "", trainingStep = "", generation = "", episodeReward = "", fitness = "", trainingTime = "";

        public const string Header = "episodeId,controllerType,actionSpaceType,seed,finalScore,survivalTime,segmentsPassed,obstaclesEncountered,obstaclesAvoided,collisionsTotal,lifeLossCount,shieldHits,fatalCollision,heartsCollected,shieldsCollected,boostsCollected,goldCollected,diamondsCollected,maxLevel,outsideStagesReached,timeInside,timeOutside,maxEnvironmentSpeed,terminalReason,trainingRunId,trainingStep,generation,episodeReward,fitness,trainingTime";
        public static string Escape(string text)
        {
            text = text ?? "";
            return text.IndexOfAny(new[] { ',', '"', '\r', '\n' }) < 0 ? text : "\"" + text.Replace("\"", "\"\"") + "\"";
        }
        public string ToCsv()
        {
            return string.Join(",", Header.Split(',').Select(name =>
            {
                object value = typeof(EpisodeSummary).GetField(name).GetValue(this);
                return Escape(value is float number ? number.ToString("R", CultureInfo.InvariantCulture)
                    : Convert.ToString(value, CultureInfo.InvariantCulture));
            }));
        }
        public void AppendTo(string path)
        {
            string fullPath = Path.GetFullPath(path);
            Directory.CreateDirectory(Path.GetDirectoryName(fullPath));
            bool exists = File.Exists(fullPath) && new FileInfo(fullPath).Length > 0;
            if (exists && File.ReadLines(fullPath).First() != Header) throw new InvalidDataException("CSV schema differs: " + fullPath);
            using (var writer = new StreamWriter(fullPath, true, new UTF8Encoding(false)))
            {
                if (!exists) writer.WriteLine(Header);
                writer.WriteLine(ToCsv());
            }
        }
    }
}
