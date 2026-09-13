using System;
using System.Globalization;
using System.IO;
using System.Net.Sockets;
using System.Text;
using UnityEngine;

namespace TurboDash.Research
{
    internal enum WorkerMessage : byte
    {
        Hello = 1,
        HelloAccepted = 2,
        Reset = 3,
        ResetResult = 4,
        Step = 5,
        StepResult = 6,
        Close = 7,
        CloseAccepted = 8,
        Error = 255
    }

    public static class ResearchWorkerBridge
    {
        public const int TransportVersion = 1;
        private static ResearchWorkerSettings settings;

        public static bool TryCreateOptions(string[] args, out ResearchOptions options)
        {
            options = null;
            if (!ResearchWorkerSettings.HasFlag(args, "--research-worker")) return false;
            settings = ResearchWorkerSettings.Parse(args);
            options = new ResearchOptions
            {
                protocolVersion = ResearchProtocolV1.Version,
                episodeCount = 0,
                maxDuration = settings.MaxDuration,
                maxScore = 0,
                simulationTimeScale = settings.TimeScale,
                controllerType = ResearchWorkerController.TypeName,
                enablePilotReward = true,
                csvPath = settings.CsvPath,
                autoAdvance = false
            };
            return true;
        }

        internal static ResearchWorkerController CreateController()
        {
            if (settings == null) throw new InvalidOperationException("Research worker command line was not initialized.");
            return new ResearchWorkerController(settings);
        }
    }

    internal sealed class ResearchWorkerSettings
    {
        public int WorkerId;
        public string Host;
        public int Port;
        public float TimeScale;
        public float MaxDuration;
        public ActionSpaceType ActionSpace;
        public string CsvPath;

        public static bool HasFlag(string[] args, string name)
            => Array.Exists(args, value => string.Equals(value, name, StringComparison.OrdinalIgnoreCase));

        private static string Value(string[] args, string name, bool required, string fallback = null)
        {
            int index = Array.FindIndex(args, value => string.Equals(value, name, StringComparison.OrdinalIgnoreCase));
            if (index < 0) return fallback;
            if (index + 1 >= args.Length) throw new ArgumentException("Missing value for " + name + ".");
            string value = args[index + 1];
            if (required && string.IsNullOrWhiteSpace(value)) throw new ArgumentException("Empty value for " + name + ".");
            return value;
        }

        public static ResearchWorkerSettings Parse(string[] args)
        {
            int workerId, port;
            float timeScale, maxDuration;
            if (!int.TryParse(Value(args, "--worker-id", true), NumberStyles.Integer, CultureInfo.InvariantCulture, out workerId) || workerId < 0)
                throw new ArgumentException("--worker-id must be a non-negative integer.");
            if (!int.TryParse(Value(args, "--bridge-port", true), NumberStyles.Integer, CultureInfo.InvariantCulture, out port) || port < 1 || port > 65535)
                throw new ArgumentException("--bridge-port must be in range 1..65535.");
            if (!float.TryParse(Value(args, "--time-scale", true), NumberStyles.Float, CultureInfo.InvariantCulture, out timeScale) || timeScale <= 0)
                throw new ArgumentException("--time-scale must be positive.");
            if (!float.TryParse(Value(args, "--max-duration", false, ResearchProtocolV1.DefaultMaxDuration.ToString(CultureInfo.InvariantCulture)),
                NumberStyles.Float, CultureInfo.InvariantCulture, out maxDuration) || maxDuration <= 0)
                throw new ArgumentException("--max-duration must be positive.");
            ActionSpaceType actionSpace;
            if (!Enum.TryParse(Value(args, "--action-space", true), true, out actionSpace))
                throw new ArgumentException("--action-space must be Discrete or Continuous.");
            string csv = Value(args, "--unity-csv", true);
            return new ResearchWorkerSettings
            {
                WorkerId = workerId,
                Host = Value(args, "--bridge-host", true),
                Port = port,
                TimeScale = timeScale,
                MaxDuration = maxDuration,
                ActionSpace = actionSpace,
                CsvPath = Path.GetFullPath(csv)
            };
        }
    }

    public sealed class ResearchWorkerController : IResearchController, IDisposable
    {
        public const string TypeName = "PPOBridge";
        private const int MaxFrameLength = 1024 * 1024;
        private readonly ResearchWorkerSettings settings;
        private TcpClient client;
        private BinaryReader reader;
        private BinaryWriter writer;
        private ResearchMode mode;
        private bool hasOutstandingStep;
        private bool closing;

        internal ResearchWorkerController(ResearchWorkerSettings settings) { this.settings = settings; }
        public string ControllerType => TypeName;
        public ActionSpaceType ActionSpaceType => settings.ActionSpace;

        internal void Attach(ResearchMode researchMode)
        {
            mode = researchMode ?? throw new ArgumentNullException(nameof(researchMode));
            // PPO updates and a full 100-seed validation may intentionally pause training workers for minutes.
            client = new TcpClient { NoDelay = true, ReceiveTimeout = 3600000, SendTimeout = 120000 };
            client.Connect(settings.Host, settings.Port);
            NetworkStream stream = client.GetStream();
            reader = new BinaryReader(stream, Encoding.UTF8, true);
            writer = new BinaryWriter(stream, Encoding.UTF8, true);
            SendFrame(payload =>
            {
                payload.Write((byte)WorkerMessage.Hello);
                payload.Write(ResearchWorkerBridge.TransportVersion);
                payload.Write(ResearchProtocolV1.Version);
                payload.Write(ObservationFrame.SchemaVersion);
                payload.Write(ObservationProvider.VectorSize);
                payload.Write((byte)ActionSpaceType);
                payload.Write(ResearchProtocolV1.FixedTimestep);
                payload.Write(ResearchProtocolV1.DecisionInterval);
                payload.Write(settings.WorkerId);
            });
            ExpectAccepted(WorkerMessage.HelloAccepted);
            mode.EpisodeStarted += OnEpisodeStarted;
            mode.EpisodeCompleted += OnEpisodeCompleted;
            ReadResetOrClose();
        }

        public void ResetEpisode(int seed) { hasOutstandingStep = false; }

        public SteeringAction Decide(ObservationFrame observation)
        {
            if (closing) return new SteeringAction(0);
            try
            {
                if (hasOutstandingStep)
                    SendStepResult(observation, mode.RewardCalculator.LastDecisionReward, false, false);
                if (!ReadStepOrClose(out SteeringAction action)) return new SteeringAction(0);
                hasOutstandingStep = true;
                return action;
            }
            catch (Exception ex)
            {
                Abort(ex);
                throw;
            }
        }

        private void OnEpisodeStarted(EpisodeSummary summary)
        {
            try
            {
                ObservationFrame observation = mode.Observations.Capture();
                SendFrame(payload =>
                {
                    payload.Write((byte)WorkerMessage.ResetResult);
                    WriteObservation(payload, observation);
                });
            }
            catch (Exception ex) { Abort(ex); throw; }
        }

        private void OnEpisodeCompleted(EpisodeSummary summary)
        {
            if (closing) return;
            try
            {
                if (hasOutstandingStep)
                {
                    SendStepResult(mode.Observations.Capture(), mode.RewardCalculator.LastDecisionReward,
                        summary.terminated, summary.truncated);
                    hasOutstandingStep = false;
                }
                ReadResetOrClose();
            }
            catch (Exception ex) { Abort(ex); throw; }
        }

        private void ReadResetOrClose()
        {
            using (BinaryReader payload = ReadFrame())
            {
                WorkerMessage message = (WorkerMessage)payload.ReadByte();
                if (message == WorkerMessage.Close) { CloseApplication(); return; }
                if (message == WorkerMessage.Error) throw new InvalidDataException(ReadText(payload));
                if (message != WorkerMessage.Reset) throw new InvalidDataException("Expected RESET, received " + message + ".");
                int seed = payload.ReadInt32();
                if (seed <= 0) throw new InvalidDataException("RESET seed must be positive.");
                EnsureConsumed(payload);
                mode.ResetEpisode(seed);
            }
        }

        private bool ReadStepOrClose(out SteeringAction action)
        {
            action = new SteeringAction(0);
            using (BinaryReader payload = ReadFrame())
            {
                WorkerMessage message = (WorkerMessage)payload.ReadByte();
                if (message == WorkerMessage.Close) { CloseApplication(); return false; }
                if (message == WorkerMessage.Error) throw new InvalidDataException(ReadText(payload));
                if (message != WorkerMessage.Step) throw new InvalidDataException("Expected STEP, received " + message + ".");
                if (ActionSpaceType == ActionSpaceType.Discrete)
                {
                    int value = payload.ReadInt32();
                    if (!Enum.IsDefined(typeof(DiscreteAction), value)) throw new InvalidDataException("Discrete action must be 0, 1 or 2.");
                    action = SteeringAction.FromDiscrete((DiscreteAction)value);
                }
                else action = new SteeringAction(payload.ReadSingle());
                EnsureConsumed(payload);
                return true;
            }
        }

        private void SendStepResult(ObservationFrame observation, float reward, bool terminated, bool truncated)
        {
            EpisodeSummary summary = mode.Current;
            SendFrame(payload =>
            {
                payload.Write((byte)WorkerMessage.StepResult);
                payload.Write(reward);
                payload.Write((byte)(terminated ? 1 : 0));
                payload.Write((byte)(truncated ? 1 : 0));
                payload.Write(mode.Decisions.PhysicsTickCount);
                WriteObservation(payload, observation);
                payload.Write(summary.episodeId);
                payload.Write(summary.seed);
                payload.Write(summary.decisionCount);
                payload.Write(summary.finalScore);
                payload.Write(summary.survivalTime);
                payload.Write(summary.segmentsPassed);
                payload.Write(summary.obstaclesEncountered);
                payload.Write(summary.obstaclesAvoided);
                payload.Write(summary.collisionsTotal);
                payload.Write(summary.lifeLossCount);
                payload.Write(summary.shieldHits);
                payload.Write((byte)(summary.fatalCollision ? 1 : 0));
                payload.Write(summary.heartsCollected);
                payload.Write(summary.shieldsCollected);
                payload.Write(summary.boostsCollected);
                payload.Write(summary.turboActivations);
                payload.Write(summary.goldCollected);
                payload.Write(summary.diamondsCollected);
                payload.Write(summary.maxLevel);
                payload.Write(summary.outsideStagesReached);
                payload.Write(summary.timeInside);
                payload.Write(summary.timeOutside);
                payload.Write(summary.maxEnvironmentSpeed);
                payload.Write(mode.RewardCalculator.EpisodeReward);
                payload.Write(TerminalReasonCode(summary.terminalReason));
            });
        }

        private static byte TerminalReasonCode(string reason)
        {
            if (reason == "LivesExhausted") return 1;
            if (reason == "MaxDuration") return 2;
            if (reason == "MaxScore") return 3;
            return 0;
        }

        private static void WriteObservation(BinaryWriter payload, ObservationFrame observation)
        {
            if (observation == null || observation.Vector == null || observation.Vector.Length != ObservationProvider.VectorSize)
                throw new InvalidDataException("Observation v2 must contain exactly " + ObservationProvider.VectorSize + " floats.");
            foreach (float value in observation.Vector)
            {
                if (float.IsNaN(value) || float.IsInfinity(value)) throw new InvalidDataException("Observation contains NaN or Infinity.");
                payload.Write(value);
            }
        }

        private void ExpectAccepted(WorkerMessage expected)
        {
            using (BinaryReader payload = ReadFrame())
            {
                WorkerMessage message = (WorkerMessage)payload.ReadByte();
                if (message == WorkerMessage.Error) throw new InvalidDataException(ReadText(payload));
                if (message != expected) throw new InvalidDataException("Expected " + expected + ", received " + message + ".");
                EnsureConsumed(payload);
            }
        }

        private void SendFrame(Action<BinaryWriter> writePayload)
        {
            if (writer == null) throw new IOException("Bridge is not connected.");
            using (var memory = new MemoryStream())
            {
                using (var payload = new BinaryWriter(memory, Encoding.UTF8, true)) writePayload(payload);
                byte[] bytes = memory.ToArray();
                writer.Write(bytes.Length);
                writer.Write(bytes);
                writer.Flush();
            }
        }

        private BinaryReader ReadFrame()
        {
            if (reader == null) throw new IOException("Bridge is not connected.");
            int length = reader.ReadInt32();
            if (length < 1 || length > MaxFrameLength) throw new InvalidDataException("Invalid bridge frame length: " + length + ".");
            byte[] bytes = reader.ReadBytes(length);
            if (bytes.Length != length) throw new EndOfStreamException("Bridge disconnected during a frame.");
            return new BinaryReader(new MemoryStream(bytes), Encoding.UTF8, false);
        }

        private static string ReadText(BinaryReader payload)
        {
            int length = payload.ReadInt32();
            if (length < 0 || length > MaxFrameLength) throw new InvalidDataException("Invalid bridge text length.");
            byte[] bytes = payload.ReadBytes(length);
            if (bytes.Length != length) throw new EndOfStreamException();
            return Encoding.UTF8.GetString(bytes);
        }

        private static void EnsureConsumed(BinaryReader payload)
        {
            if (payload.BaseStream.Position != payload.BaseStream.Length) throw new InvalidDataException("Unexpected trailing bridge payload.");
        }

        private void CloseApplication()
        {
            if (closing) return;
            closing = true;
            Time.timeScale = 0;
            SendFrame(payload => payload.Write((byte)WorkerMessage.CloseAccepted));
            Application.Quit(0);
        }

        private static void Abort(Exception exception)
        {
            Debug.LogError("Research worker bridge failed: " + exception.Message);
            Application.Quit(2);
        }

        public void Dispose()
        {
            if (mode != null)
            {
                mode.EpisodeStarted -= OnEpisodeStarted;
                mode.EpisodeCompleted -= OnEpisodeCompleted;
            }
            if (reader != null) reader.Dispose();
            if (writer != null) writer.Dispose();
            if (client != null) client.Close();
            reader = null; writer = null; client = null; mode = null;
        }
    }
}
