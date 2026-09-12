using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEngine;

namespace TurboDash.Research
{
    [Serializable]
    public sealed class ResearchOptions
    {
        // Diagnostic defaults, not experimental limits or an evaluation seed set.
        public int initialSeed = 12345;
        public int episodeCount = 3;
        public int[] seeds = Array.Empty<int>();
        public float maxDuration = 10;
        public float maxScore;
        public string csvPath = "";
        public bool autoAdvance = true;
        public void Validate()
        {
            if (episodeCount < 0 || maxDuration < 0 || maxScore < 0 ||
                float.IsNaN(maxDuration) || float.IsInfinity(maxDuration) ||
                float.IsNaN(maxScore) || float.IsInfinity(maxScore)) throw new ArgumentException("Invalid episode limits.");
            if (seeds == null) seeds = Array.Empty<int>();
            if (seeds.Length > 0 && episodeCount > seeds.Length) throw new ArgumentException("Not enough explicit seeds.");
        }
        public int SeedFor(int zeroBasedEpisode) => seeds.Length > 0 ? seeds[zeroBasedEpisode]
            : unchecked(initialSeed + zeroBasedEpisode * 104729);
        public bool HasNext(int completed) => seeds.Length > 0
            ? completed < (episodeCount == 0 ? seeds.Length : episodeCount)
            : episodeCount == 0 || completed < episodeCount;
    }

    public enum EpisodeState { Initializing, Resetting, Running, Terminal, Finished, Faulted }

    [DefaultExecutionOrder(-10000)]
    public sealed class ResearchMode : MonoBehaviour
    {
        public const string EditorRequestKey = "TurboDash.Research.Options";
        public static ResearchMode Instance { get; private set; }
        public static bool Active => Instance != null;
        public static bool Running => Active && Instance.State == EpisodeState.Running;
        public static float GameplayTime => Active ? Instance.episodePhysicsTime : Time.time;
        public ResearchOptions Options { get; private set; }
        public EpisodeState State { get; private set; } = EpisodeState.Initializing;
        public EpisodeSummary Current { get; private set; }
        public EpisodeSummary LastCompleted { get; private set; }
        public IResearchController Controller { get; private set; } = new NoActionController();
        public ObservationProvider Observations { get; private set; }
        public string OutputPath { get; private set; }
        public readonly List<ResearchSegment> Segments = new List<ResearchSegment>();
        public event Action<EpisodeSummary> EpisodeStarted;
        public event Action<EpisodeSummary> EpisodeCompleted;

        private GameManager game;
        private EnvironmentManager generator;
        private EnvironmentMovement movement;
        private PlayerCollision player;
        private UIGame ui;
        private readonly List<GameObject> effects = new List<GameObject>();
        private GameMode runtimeGameMode;
        private Quaternion initialEnvironmentRotation;
        private int episodeNumber, segmentSequence;
        private int? requestedSeed;
        private float episodePhysicsTime;
        private GameManager.Location previousLocation;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        private static void ClearStatics() { Instance = null; ResearchEvents.Clear(); }

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
        private static void Bootstrap()
        {
            string json = null;
            string[] args = Environment.GetCommandLineArgs();
            int index = Array.IndexOf(args, "-turboResearchConfig");
            if (index >= 0)
            {
                if (index + 1 >= args.Length) throw new ArgumentException("Missing research configuration path.");
                json = File.ReadAllText(args[index + 1]);
            }
#if UNITY_EDITOR
            if (json == null) json = UnityEditor.SessionState.GetString(EditorRequestKey, "");
#endif
            if (string.IsNullOrWhiteSpace(json)) return;
            ResearchOptions options = JsonUtility.FromJson<ResearchOptions>(json);
            options.Validate();
            var root = new GameObject("ResearchMode");
            Instance = root.AddComponent<ResearchMode>();
            Instance.Options = options;
            DontDestroyOnLoad(root);
            // Runtime-only game mode. Never modify the authored mode assets or player records.
            var save = new GameObject("ResearchSaveService").AddComponent<SaveAndLoadManager>();
            var mode = ScriptableObject.CreateInstance<GameMode>();
            mode.name = "Research runtime mode"; mode.Index = 1; mode.GameModeName = "Research";
            save.allGameModes = new[] { mode, mode, mode };
            save.usedGameMode = mode;
            Instance.runtimeGameMode = mode;
        }

        private IEnumerator Start()
        {
            // All gameplay Start methods finish while TimeManager keeps the game paused.
            yield return null;
            game = GameManager.Instance;
            generator = FindObjectOfType<EnvironmentManager>();
            movement = FindObjectOfType<EnvironmentMovement>();
            player = FindObjectOfType<PlayerCollision>();
            ui = FindObjectOfType<UIGame>();
            if (!game || !generator || !movement || !player || !ui || !TimeManager.Instance || !AudioSystem.Instance)
            { Fail(new InvalidOperationException("Launch ResearchMode directly in DeafultLevel using the Research menu/batch entry.")); yield break; }
            initialEnvironmentRotation = movement.transform.localRotation;
            Observations = new ObservationProvider(this, player, ui);
            OutputPath = string.IsNullOrWhiteSpace(Options.csvPath)
                ? Path.Combine(Application.persistentDataPath, "Research", DateTime.UtcNow.ToString("yyyyMMdd-HHmmss-fffffff") + ".csv")
                : Path.GetFullPath(Options.csvPath);
            if (File.Exists(OutputPath) && new FileInfo(OutputPath).Length > 0)
            { Fail(new IOException("Use a new CSV path for each research session: " + OutputPath)); yield break; }
            // Hide presentation only; UIGame and ImmortalityEffect continue running gameplay logic.
            foreach (var canvas in FindObjectsOfType<Canvas>(true)) canvas.enabled = false;
            Debug.Log("Research CSV: " + OutputPath);
            ResetEpisode(Options.SeedFor(0));
        }

        public void SetController(IResearchController controller)
        {
            if (Running || State == EpisodeState.Resetting) throw new InvalidOperationException("Change controllers between episodes.");
            if (controller != null && (string.IsNullOrWhiteSpace(controller.ControllerType) || !Enum.IsDefined(typeof(ActionSpaceType), controller.ActionSpaceType)))
                throw new ArgumentException("Controller identity and action space must be valid.");
            Controller = controller ?? throw new ArgumentNullException(nameof(controller));
        }

        public void ResetEpisode(int seed)
        {
            if (!generator) throw new InvalidOperationException("Research initialization is not complete.");
            if (State == EpisodeState.Resetting) throw new InvalidOperationException("A reset is already in progress.");
            if (State == EpisodeState.Faulted) throw new InvalidOperationException("Resolve the research fault before restarting.");
            if (Running) Complete("ResetRequested");
            if (State != EpisodeState.Faulted) requestedSeed = seed;
        }

        private void FixedUpdate()
        {
            if (Running) episodePhysicsTime += Time.fixedDeltaTime;
        }

        private void LateUpdate()
        {
            if (requestedSeed.HasValue && State != EpisodeState.Resetting && State != EpisodeState.Faulted)
            {
                int seed = requestedSeed.Value; requestedSeed = null;
                StartCoroutine(ResetRoutine(seed));
                return;
            }
            if (!Running) return;
            try
            {
                Current.survivalTime += Time.deltaTime;
                if (game.gameLocation == GameManager.Location.Inside) Current.timeInside += Time.deltaTime;
                else Current.timeOutside += Time.deltaTime;
                if (previousLocation != game.gameLocation && game.gameLocation == GameManager.Location.Outside) Current.outsideStagesReached++;
                previousLocation = game.gameLocation;
                Current.finalScore = game.gameScore;
                Current.maxLevel = Mathf.Max(Current.maxLevel, (int)game.gameLevel);
                Current.maxEnvironmentSpeed = Mathf.Max(Current.maxEnvironmentSpeed, game.tubeMoveSpeed);
                Segments.RemoveAll(segment => !segment);
                foreach (var segment in Segments) segment.Sample(player.transform.position.z);
                if (game.gameHasEnded || game.playerLives <= 0) Complete("LivesExhausted");
                else if (Options.maxScore > 0 && game.gameScore >= Options.maxScore) Complete("MaxScore");
                else if (Options.maxDuration > 0 && Current.survivalTime >= Options.maxDuration) Complete("MaxDuration");
            }
            catch (Exception ex) { Fail(ex); }
        }

        private IEnumerator ResetRoutine(int seed)
        {
            State = EpisodeState.Resetting;
            Time.timeScale = 0; game.gamePaused = true; game.gameHasEnded = true;
            // Cancel every gameplay coroutine owner; no previous UI countdown or turbo drain survives.
            game.StopAllCoroutines(); game.CancelInvoke(); ui.StopAllCoroutines(); ui.CancelInvoke();
            foreach (var loader in FindObjectsOfType<LevelLoader>(true)) { loader.StopAllCoroutines(); loader.CancelInvoke(); }
            foreach (var effect in effects) if (effect) { effect.SetActive(false); Destroy(effect); }
            effects.Clear();
            generator.ClearResearchEnvironment(); Segments.Clear();
            // Destroy is deferred by Unity. Leave one paused frame before creating replacements.
            yield return null;
            try
            {
                game.StartGame(); game.showLevelUP = false; game.isNewHighScore = false;
                movement.ResetEpisode(initialEnvironmentRotation);
                player.ResetEpisode();
                ui.ResetEpisodeUI();
                foreach (var protection in FindObjectsOfType<ImmortalityEffect>(true)) protection.ResetEpisode();
                foreach (var camera in FindObjectsOfType<FollowPlayer>(true)) camera.ResetEpisode();
                var cameraFollow = GameObject.FindWithTag("CameraFollow");
                if (cameraFollow)
                {
                    var animator = cameraFollow.GetComponent<Animator>();
                    if (animator) { animator.Rebind(); animator.Update(0); }
                }
                foreach (string tag in new[] { "VisualEffectShield", "VisualEffectTurbo" })
                    foreach (var visual in GameObject.FindGameObjectsWithTag(tag))
                        if (visual.TryGetComponent<Renderer>(out var renderer)) renderer.enabled = false;
                foreach (var trail in FindObjectsOfType<TrailRenderer>()) trail.Clear();
                foreach (var source in FindObjectsOfType<AudioSource>()) source.Stop();
                AudioSystem.Instance.StartPlayGameMusic();
                episodePhysicsTime = 0; segmentSequence = 0;
                GameplayRandom.Reset(seed);
                Controller.ResetEpisode(seed);
                Current = new EpisodeSummary { episodeId = ++episodeNumber, seed = seed,
                    controllerType = Controller.ControllerType, actionSpaceType = Controller.ActionSpaceType.ToString() };
                generator.ResetResearchEnvironment();
            }
            catch (Exception ex) { Fail(ex); yield break; }
            // Start on instantiated motion/bonus components, still at simulation time zero.
            yield return null;
            try
            {
                Physics.SyncTransforms();
                Observations.Capture(); // Fail explicitly if new content exceeds the declared schema.
                game.gameStart = false; game.gamePaused = false; game.gameHasEnded = false;
                previousLocation = GameManager.Location.Inside;
                TimeManager.Instance.ResetTimeScale();
                State = EpisodeState.Running;
                EpisodeStarted?.Invoke(Current);
            }
            catch (Exception ex) { Fail(ex); }
        }

        private void Complete(string reason)
        {
            if (!Running) return;
            Current.finalScore = game.gameScore;
            Current.terminalReason = reason;
            ResearchEvents.Emit(ResearchEventType.Terminal, 1, reason);
            State = EpisodeState.Terminal;
            game.gameHasEnded = true; game.gamePaused = true; Time.timeScale = 0;
            try
            {
                Current.AppendTo(OutputPath);
                LastCompleted = Current;
                EpisodeCompleted?.Invoke(Current);
                if (Options.autoAdvance && Options.HasNext(episodeNumber)) requestedSeed = Options.SeedFor(episodeNumber);
                else State = EpisodeState.Finished;
            }
            catch (Exception ex) { Fail(ex); }
        }

        public void Fail(Exception exception)
        {
            State = EpisodeState.Faulted; requestedSeed = null;
            Time.timeScale = 0;
            if (game) { game.gamePaused = true; game.gameHasEnded = true; }
            Debug.LogException(exception);
        }

        internal void Record(ResearchEvent data)
        {
            switch (data.Type)
            {
                case ResearchEventType.Collision: Current.collisionsTotal++; break;
                case ResearchEventType.LifeLost:
                    Current.lifeLossCount += (int)data.Value;
                    if (game.playerLives == 0) Current.fatalCollision = true;
                    break;
                case ResearchEventType.ShieldConsumed: Current.shieldHits++; break;
                case ResearchEventType.HeartCollected: Current.heartsCollected++; break;
                case ResearchEventType.ShieldCollected: Current.shieldsCollected++; break;
                case ResearchEventType.BoostCollected: Current.boostsCollected++; break;
                case ResearchEventType.GoldCollected: Current.goldCollected++; break;
                case ResearchEventType.DiamondCollected: Current.diamondsCollected++; break;
            }
        }
        public static void RegisterTube(GameObject tube)
        {
            if (!Active) return;
            var segment = tube.AddComponent<ResearchSegment>();
            segment.Sequence = Instance.segmentSequence++;
            Instance.Segments.Add(segment);
            tube.GetComponent<TubeManager>().Initialize();
        }
        public static void RegisterSpawn(GameObject spawned, Transform parent)
        {
            if (!Active) return;
            foreach (var arrangement in spawned.GetComponentsInChildren<RandomArrangement>()) arrangement.Initialize();
            var segment = parent.GetComponentInParent<ResearchSegment>();
            if (segment) segment.Register(spawned);
        }
        public static void TrackEffect(GameObject effect) { if (Active) Instance.effects.Add(effect); }
        private void OnDestroy()
        {
            if (Instance != this) return;
            if (runtimeGameMode) Destroy(runtimeGameMode);
            Instance = null; ResearchEvents.Clear(); Time.timeScale = 1;
        }
    }
}
