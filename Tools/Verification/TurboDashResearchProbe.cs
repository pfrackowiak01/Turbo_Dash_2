// Copy to Assets (outside Editor) ONLY in the verification project.
// -executeMethod TurboDashResearchProbe.Run -turboVerifyResearch -turboResearchConfig <json>
using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using TurboDash.Research;
using UnityEngine;
using UnityEngine.SceneManagement;

public sealed class TurboDashResearchProbe : MonoBehaviour
{
    private readonly List<string> checks = new List<string>();
    private bool finished;
    private float deadline;
    private ResearchMode mode;
    private GameManager game;
    private UIGame ui;
    private EnvironmentMovement movement;
    private GameObject contact;
    private int resets;
    private int completions;
    private string signature;
    private int sceneLoads, sceneLoadsAtStart;
    private readonly List<ResearchEvent> events = new List<ResearchEvent>();

    public static void Run()
    {
#if UNITY_EDITOR
        UnityEditor.SceneManagement.EditorSceneManager.OpenScene("Assets/Turbo_Dash/Design/Scenes/DeafultLevel.unity");
        UnityEditor.EditorApplication.EnterPlaymode();
#endif
    }
    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
    private static void Install()
    {
        if (Environment.GetCommandLineArgs().Contains("-turboVerifyResearch")) new GameObject("ResearchVerification").AddComponent<TurboDashResearchProbe>();
    }
    private void Awake()
    {
        deadline = Time.realtimeSinceStartup + 180;
        Application.logMessageReceived += OnLog;
        SceneManager.sceneLoaded += (scene, loadMode) => sceneLoads++;
    }
    private void OnLog(string text, string stack, LogType type)
    {
        if (type == LogType.Exception || type == LogType.Error || type == LogType.Assert) Finish(text + "\n" + stack);
    }
    private void Update() { if (Time.realtimeSinceStartup > deadline) Finish("Runtime timeout"); }
    private IEnumerator Start()
    {
        var test = RunTests();
        while (!finished)
        {
            object yielded;
            try { if (!test.MoveNext()) break; yielded = test.Current; }
            catch (Exception exception) { Finish(exception.ToString()); yield break; }
            yield return yielded;
        }
    }
    private void Check(bool condition, string name)
    {
        if (!condition) throw new Exception(name);
        checks.Add(name); Debug.Log("RESEARCH PASS: " + name);
    }
    private static T Find<T>() where T : UnityEngine.Object => FindObjectOfType<T>();
    private IEnumerator Contact(string tag)
    {
        if (contact) DestroyImmediate(contact);
        contact = new GameObject("VerificationContact");
        var child = new GameObject(tag); child.transform.SetParent(contact.transform);
        child.tag = tag; child.transform.position = Find<PlayerCollision>().transform.position;
        child.AddComponent<BoxCollider>().isTrigger = true;
        child.AddComponent<Rigidbody>().isKinematic = true;
        Physics.SyncTransforms();
        float contactTime = Time.fixedTime;
        do { yield return null; } while (ResearchMode.Running && Time.fixedTime - contactTime < .02f);
        yield return null;
        if (contact) DestroyImmediate(contact);
    }
    private IEnumerator Reset(int seed)
    {
        int before = resets;
        mode.ResetEpisode(seed);
        while (resets == before) yield return null;
    }
    private void OnReset(EpisodeSummary summary)
    {
        resets++;
        game = GameManager.Instance; ui = Find<UIGame>(); movement = Find<EnvironmentMovement>();
        Check(game.gameScore == 0 && game.timer == 0 && game.gameLevel == 1 && game.gameLocation == GameManager.Location.Inside,
            "Reset " + resets + ": score/level/Inside");
        Check(game.playerLives == 3 && !game.playerShield && !game.playerImmortality && !game.turboEffectEnable && ui.turboSlider.value == 0,
            "Reset " + resets + ": lives and all powerups");
        Check(game.tubeMoveSpeed == 50 && game.extraMoveSpeed == 0 && game.rotationAmount == 0 && Time.timeScale == 1 && !game.gamePaused && !game.gameStart,
            "Reset " + resets + ": speed, rotation, time and UI flags");
        Check(summary.survivalTime == 0 && summary.collisionsTotal == 0 && summary.lifeLossCount == 0 && summary.goldCollected == 0 && summary.segmentsPassed == 0,
            "Reset " + resets + ": clean metrics");
        Check(summary.protocolVersion == 1 && summary.observationSchemaVersion == 2 && summary.decisionInterval == .05f &&
            mode.Decisions.DecisionCount == 0 && mode.Observations.Capture().Vector.Length == 236,
            "Reset " + resets + ": protocol and Observation v2 schema stable");
        Check(FindObjectsOfType<TubeManager>().Length == 5 && mode.Segments.Count(t => t) == 5 && game.safeTubes == 0,
            "Reset " + resets + ": five new tubes, safe budget consumed once");
        Check(FindObjectsOfType<GameManager>().Length == 1 && FindObjectsOfType<SaveAndLoadManager>().Length == 1 &&
            FindObjectsOfType<TimeManager>().Length == 1 && FindObjectsOfType<AudioSystem>().Length == 1,
            "Reset " + resets + ": singleton counts stable");
    }
    private string LayoutWithVisualNoise(bool noise)
    {
        var generator = Find<EnvironmentManager>();
        var spawn = generator.GetType().GetMethod("spawnTube", BindingFlags.Instance | BindingFlags.NonPublic);
        for (int i = 0; i < 30; i++)
        {
            if (noise) for (int n = 0; n < 73; n++) UnityEngine.Random.Range(0, 10000);
            spawn.Invoke(generator, new object[] { 300f + i * 60 });
        }
        return string.Join("|", mode.Segments.Where(t => t).SelectMany(t => t.GetComponentsInChildren<RandomArrangement>())
            .Select(t => t.name + ":" + t.transform.localRotation.ToString("F5")));
    }
    private IEnumerator RunTests()
    {
        mode = ResearchMode.Instance;
        Check(mode, "BeforeSceneLoad research bootstrap");
        mode.Options.autoAdvance = false; mode.Options.maxDuration = 0; mode.Options.maxScore = 0;
        mode.EpisodeStarted += OnReset;
        mode.EpisodeCompleted += summary => completions++;
        ResearchEvents.Raised += data => events.Add(data);
        while (!ResearchMode.Running) yield return null;
        sceneLoadsAtStart = sceneLoads;
        Check(SceneManager.GetActiveScene().name == "DeafultLevel" && !Find<UIMenu>(), "Direct gameplay without Menu");
        Check(ResearchProtocolV1.Version == 1 && Mathf.Abs(Time.fixedDeltaTime - .01f) < .000001f &&
            ResearchProtocolV1.PhysicsTicksPerDecision == 5 && ResearchProtocolV1.DecisionsPerSecond == 20,
            "Research Protocol v1 timing constants");
        Check(FindObjectsOfType<Canvas>(true).All(canvas => !canvas.enabled) && ui.enabled && Find<ImmortalityEffect>().enabled,
            "UI hidden while turbo/protection logic remains active");
        yield return Reset(777);
        signature = LayoutWithVisualNoise(false);
        yield return Reset(777);
        Check(signature == LayoutWithVisualNoise(true), "Same seed reproduces 35 tube layout despite 2190 visual RNG draws");
        yield return Reset(778);
        Check(signature != LayoutWithVisualNoise(false), "Different seed changes layout");
        yield return Reset(777);

        Check(HumanController.ManualDegreesPerSecond(true, false, 12) == 144 && HumanController.ManualDegreesPerSecond(false, true, 12) == -144 &&
            HumanController.ManualDegreesPerSecond(true, true, 12) == 0 && HumanController.ManualDegreesPerSecond(false, false, 12) == 0, "Legacy human manual mapping preserved");
        foreach (var location in new[] { GameManager.Location.Inside, GameManager.Location.Outside })
        {
            game.gameLocation = location;
            foreach (var action in new[] { DiscreteAction.Left, DiscreteAction.None, DiscreteAction.Right })
            {
                movement.transform.localRotation = Quaternion.identity;
                movement.ApplyAction(SteeringAction.FromDiscrete(action), 1f / 144);
                float discrete = Mathf.DeltaAngle(0, movement.transform.eulerAngles.z);
                movement.transform.localRotation = Quaternion.identity;
                movement.ApplyAction(new SteeringAction(action == DiscreteAction.Left ? 1 : action == DiscreteAction.Right ? -1 : 0), 1f / 144);
                Check(Mathf.Abs(discrete - Mathf.DeltaAngle(0, movement.transform.eulerAngles.z)) < .001f, "Discrete/continuous equivalence " + location + " " + action);
                float expected = (action == DiscreteAction.Left ? 1 : action == DiscreteAction.Right ? -1 : 0) * (location == GameManager.Location.Inside ? 1 : -1);
                Check(Mathf.Abs(discrete - expected) < .001f, "Player-relative rotation sign " + location + " " + action);
            }
        }
        game.gameLocation = GameManager.Location.Inside; movement.transform.localRotation = Quaternion.identity;
        movement.ApplyAction(new SteeringAction(.5f), 1f / 144);
        Check(Mathf.Abs(Mathf.DeltaAngle(0, movement.transform.eulerAngles.z) - .5f) < .001f, "Continuous half steering");
        bool rejected = false;
        try { new SteeringAction(float.NaN); } catch (ArgumentOutOfRangeException) { rejected = true; }
        Check(rejected && new SteeringAction(2).Value == 1, "Action validation and clipping");
        ProtocolUnitTests();
        GeometryTests();
        var observation = mode.Observations.Capture().Vector;
        var observationV1 = mode.DiagnosticObservationsV1.Capture().Vector;
        Check(observation.Length == 236 && ObservationProvider.VectorSize == 236 && observation.All(v => !float.IsNaN(v) && !float.IsInfinity(v)), "Observation v2 is a finite fixed 236-float vector");
        Check(observationV1.Length == 2633 && ObservationProviderV1.VectorSize == 2633 && observationV1.All(v => !float.IsNaN(v) && !float.IsInfinity(v)), "Observation v1 remains available as 2633-float reference");
        Check(observation[0] == 1 && observation[1] == 0 && observation[5] == .5f, "Global observation normalization");
        yield return ContentObservationTests();

        yield return Reset(31415);
        Find<EnvironmentManager>().enabled = false;
        foreach (var tube in FindObjectsOfType<TubeMovement>()) tube.enabled = false;
        int prefsGold = PlayerPrefs.GetInt("Coins", 0), prefsDiamond = PlayerPrefs.GetInt("Diamonds", 0);
        events.Clear();
        yield return Contact("Wall");
        Check(game.playerLives == 2 && game.playerImmortality && mode.Current.lifeLossCount == 1, "Physics collision, life loss, protection and metrics");
        yield return Contact("Heart");
        Check(game.playerLives == 3 && mode.Current.heartsCollected == 1, "Physics Heart and metric");
        yield return Contact("Shield");
        Check(game.playerShield && mode.Current.shieldsCollected == 1, "Physics Shield and metric");
        yield return new WaitForSeconds(3.2f);
        Check(!game.playerImmortality, "Protection expires through original timer");
        yield return Contact("Obstacle");
        Check(!game.playerShield && game.playerLives == 3 && mode.Current.shieldHits == 1, "Physics shield consumption without life loss");
        yield return Contact("Gold"); yield return Contact("Diamond");
        Check(mode.Current.goldCollected == 1 && mode.Current.diamondsCollected == 1 && game.playerCoins == 1 && game.playerDiamonds == 1, "Economy pickups recorded per episode");
        Check(PlayerPrefs.GetInt("Coins", 0) == prefsGold && PlayerPrefs.GetInt("Diamonds", 0) == prefsDiamond, "Research pickups do not write PlayerPrefs");
        yield return Contact("Boost"); yield return Contact("Boost"); yield return Contact("Boost");
        Check(game.turboEffectEnable && game.playerImmortality && mode.Current.boostsCollected == 3 && mode.Current.turboActivations == 1, "Full charge automatically activates and counts one turbo start");
        float scoreBefore = game.gameScore, durationBefore = mode.Current.survivalTime;
        yield return new WaitForSeconds(.5f);
        float rate = (game.gameScore - scoreBefore) / (mode.Current.survivalTime - durationBefore);
        Check(Mathf.Abs(rate - 50.6f) < 2, "Turbo score rate matches 23 * 1.1 * 2");
        float waitUntil = Time.time + 25;
        while (game.turboEffectEnable && Time.time < waitUntil) yield return null;
        Check(!game.turboEffectEnable, "Original turbo drain completes");
        yield return new WaitForSeconds(3.2f);
        game.timer = 1001; yield return null; yield return null;
        Check(game.gameLevel == 2, "Research level threshold remains unchanged");
        game.timer = 2001; yield return null; yield return null;
        game.timer = 2801; yield return null; yield return null;
        yield return Contact("Portal");
        Check(game.gameLocation == GameManager.Location.Outside && game.gameLevel == 4 && game.gameScore >= 3000 && mode.Current.outsideStagesReached == 1, "Research portal, FixScore and Outside metrics");
        for (int stage = 1; stage <= 3; stage++)
        {
            game.timer = 3801 + (stage - 1) * 4000; yield return null; yield return null;
            yield return Contact("Portal");
            Check(game.gameLocation == GameManager.Location.Inside && game.gameLevel == stage * 4 + 1, "Return Inside at level " + (stage * 4 + 1));
            game.timer = 5001 + (stage - 1) * 4000; yield return null; yield return null;
            game.timer = 6001 + (stage - 1) * 4000; yield return null; yield return null;
            game.timer = 6801 + (stage - 1) * 4000; yield return null; yield return null;
            yield return Contact("Portal");
            var expectedDifficulty = stage == 1 ? GameManager.LevelDifficulty.Medium : stage == 2 ? GameManager.LevelDifficulty.Hard : GameManager.LevelDifficulty.Easy;
            Check(game.gameLevel == (stage + 1) * 4 && game.gameLocation == GameManager.Location.Outside && game.gameOutsideDifficulty == expectedDifficulty && game.tubeMoveSpeed == 80,
                "Outside cycle and speed cap at level " + ((stage + 1) * 4));
        }
        yield return Contact("Wall"); yield return new WaitForSeconds(3.2f);
        yield return Contact("Wall"); yield return new WaitForSeconds(3.2f);
        yield return Contact("Wall");
        while (ResearchMode.Running) yield return null;
        Check(mode.LastCompleted.terminalReason == "LivesExhausted" && mode.LastCompleted.terminated && !mode.LastCompleted.truncated && mode.LastCompleted.fatalCollision && mode.LastCompleted.lifeLossCount == 4,
            "Three lives plus restored Heart lead to correct fatal terminal summary");
        Check(Enum.GetValues(typeof(ResearchEventType)).Cast<ResearchEventType>().All(type => events.Any(data => data.Type == type)), "All common reward/fitness event types emitted");
        Check(Mathf.Abs(mode.LastCompleted.timeInside + mode.LastCompleted.timeOutside - mode.LastCompleted.survivalTime) < .01f,
            "Inside/Outside times sum to survival time");
        Check(File.ReadAllLines(mode.OutputPath).Length == completions + 1, "Exactly one CSV row per valid completed episode");
        Check(File.ReadLines(mode.OutputPath).First() == EpisodeSummary.Header && mode.LastCompleted.ToCsv().Split(',').Length == 37, "CSV protocol, outcome, turbo and reserved training fields");
        Check(!string.IsNullOrEmpty(mode.LastCompleted.episodeReward) && !string.IsNullOrEmpty(mode.LastCompleted.fitness), "Episode reward and fitness are written for active calculator");
        var previousCulture = CultureInfo.CurrentCulture;
        CultureInfo.CurrentCulture = new CultureInfo("pl-PL");
        Check(new EpisodeSummary { finalScore = 12.5f }.ToCsv().Contains(",12.5,"), "CSV invariant decimal separator");
        CultureInfo.CurrentCulture = previousCulture;
        Check(EpisodeSummary.Escape("a,\"b\"") == "\"a,\"\"b\"\"\"", "CSV quoting");

        var continuousController = new SubmittedActionController("VerificationContinuous", ActionSpaceType.Continuous);
        mode.SetController(continuousController);
        yield return Reset(31416);
        continuousController.Submit(.5f);
        float rotationBefore = movement.transform.localEulerAngles.z;
        yield return new WaitForSeconds(.04f);
        Check(Mathf.DeltaAngle(rotationBefore, movement.transform.localEulerAngles.z) > 0 && mode.Current.actionSpaceType == "Continuous",
            "Submitted continuous controller drives real FixedUpdate rotation and CSV identity");
        ui.AddTurbo(); ui.AddTurbo(); ui.AddTurbo(); yield return null; yield return null;
        Check(game.turboEffectEnable, "Turbo drain active before dirty reset");
        game.playerShield = true; game.playerLives = 1; game.timer = 200;
        movement.transform.Rotate(0, 0, 73);
        yield return Reset(31417);
        yield return new WaitForSeconds(.3f);
        Check(!game.turboEffectEnable && ui.turboSlider.value < .02f && game.playerLives == 3 && !game.playerShield,
            "Dirty reset cancels previous turbo coroutine and clears powerups");
        Check(continuousController.Decide(mode.Observations.Capture()).Value == 0, "Submitted action is cleared on episode reset");
        Check(Mathf.Abs(Mathf.DeltaAngle(0, movement.transform.localEulerAngles.z)) < .001f, "Dirty world rotation reset");
        MetricsTests();
        Find<EnvironmentManager>().enabled = true;
        mode.Options.maxDuration = .3f;
        yield return Reset(42);
        while (ResearchMode.Running) yield return null;
        Check(mode.LastCompleted.terminalReason == "MaxDuration" && !mode.LastCompleted.terminated && mode.LastCompleted.truncated, "Duration is a truncation, not a terminal death");
        mode.Options.maxDuration = 0; mode.Options.maxScore = 1;
        yield return Reset(43);
        while (ResearchMode.Running) yield return null;
        Check(mode.LastCompleted.terminalReason == "MaxScore" && !mode.LastCompleted.terminated && mode.LastCompleted.truncated, "Optional score limit is classified as truncation");
        int rowsBeforeAbort = File.ReadAllLines(mode.OutputPath).Length;
        yield return Reset(431);
        yield return Reset(432);
        Check(File.ReadAllLines(mode.OutputPath).Length == rowsBeforeAbort, "ResetRequested does not create a policy result or CSV row");
        mode.Options.maxDuration = .02f;
        while (ResearchMode.Running) yield return null;
        mode.Options.maxScore = 0; mode.Options.maxDuration = .2f;
        mode.Options.autoAdvance = true; mode.Options.episodeCount = mode.LastCompleted.episodeId + 3;
        var discreteController = new SubmittedActionController("VerificationDiscrete", ActionSpaceType.Discrete);
        mode.SetController(discreteController);
        int beforeAuto = resets;
        yield return Reset(44);
        discreteController.Submit(DiscreteAction.Left);
        rotationBefore = movement.transform.localEulerAngles.z;
        yield return new WaitForSeconds(.03f);
        Check(Mathf.DeltaAngle(rotationBefore, movement.transform.localEulerAngles.z) > 0 && mode.Current.actionSpaceType == "Discrete",
            "Submitted discrete controller drives real FixedUpdate rotation and CSV identity");
        discreteController.Submit(DiscreteAction.None);
        while (mode.State != EpisodeState.Finished) yield return null;
        Check(resets == beforeAuto + 3, "Three episodes automatically terminate, save and reset without scene reload");
        Check(SceneManager.GetActiveScene().name == "DeafultLevel" && mode && FindObjectsOfType<SaveAndLoadManager>().Length == 1,
            "Research session and services survive all resets");
        Check(sceneLoads == sceneLoadsAtStart, "No sceneLoaded event between research episodes");
        Finish(null);
    }

    private void ProtocolUnitTests()
    {
        var scheduler = new DecisionScheduler();
        scheduler.Reset();
        int calls = 0;
        var held = new List<float>();
        for (int tick = 0; tick < 100; tick++)
            held.Add(scheduler.Tick(() => new ObservationFrame(new float[236]), frame =>
            {
                calls++;
                return SteeringAction.FromDiscrete(calls % 2 == 1 ? DiscreteAction.Left : DiscreteAction.Right);
            }).Value);
        Check(calls == 20 && scheduler.DecisionCount == 20 && scheduler.PhysicsTickCount == 100,
            "Decision scheduler makes 20 decisions in ticks [0,100) of 1.00 game second");
        Check(held[0] == 1 && held.Take(5).All(value => value == 1) && held.Skip(5).Take(5).All(value => value == -1),
            "First decision occurs at tick zero and each action is held for five physics ticks");
        scheduler.Reset();
        Check(scheduler.DecisionCount == 0 && scheduler.PhysicsTickCount == 0 && scheduler.HeldAction.Value == 0,
            "Decision scheduler reset clears counters and held action");

        var reward = new PilotRewardCalculator(new PilotRewardParameters());
        reward.Reset();
        reward.Record(new ResearchEvent(ResearchEventType.ScoreDelta, 125));
        reward.Record(new ResearchEvent(ResearchEventType.Collision));
        reward.Record(new ResearchEvent(ResearchEventType.ShieldConsumed));
        reward.Record(new ResearchEvent(ResearchEventType.LifeLost));
        Check(Mathf.Abs(reward.CloseDecisionInterval() - .75f) < .0001f && Mathf.Abs(reward.EpisodeReward - .75f) < .0001f,
            "Pilot reward is scoreDelta/100 minus 0.5 per life loss only");
        Check(Mathf.Abs(reward.Fitness(250, 2) - 1.5f) < .0001f, "Pilot fitness is finalScore/100 minus 0.5 per life loss");

        float sectorWidth = 2 * Mathf.PI / 12;
        Check(ObservationProvider.Intersections(Mathf.PI, .2f, ObservationV2Layout.SectorCenter(0), sectorWidth).Count > 0,
            "Hazard grid handles the -pi/pi wrap boundary");
        Check(ObservationProvider.RelativeAngle(-.5f, 0, false) > ObservationProvider.RelativeAngle(-.4f, 0, false) &&
            ObservationProvider.RelativeAngle(.5f, 0, true) > ObservationProvider.RelativeAngle(.4f, 0, true),
            "Positive relative angle follows LEFT and moves toward zero in Inside and Outside");
        float boundary = ObservationV2Layout.SectorCenter(6) + sectorWidth / 2;
        Check(ObservationProvider.Intersections(boundary, .2f, ObservationV2Layout.SectorCenter(6), sectorWidth).Count > 0 &&
            ObservationProvider.Intersections(boundary, .2f, ObservationV2Layout.SectorCenter(7), sectorWidth).Count > 0,
            "Hazard crossing a sector boundary occupies both sectors");
        Check(Enumerable.Range(0, 12).All(sector => Mathf.Abs(ObservationProvider.UnionLength(
            ObservationProvider.Intersections(0, 2 * Mathf.PI, ObservationV2Layout.SectorCenter(sector), sectorWidth)) - sectorWidth) < .0001f),
            "Full-circle hazard occupies all 12 sectors completely");
        Check(Mathf.Abs(ObservationProvider.UnionLength(new List<Vector2> { new Vector2(0, .4f), new Vector2(.2f, .5f) }) - .5f) < .0001f,
            "Overlapping collider intervals are unioned without occupancy inflation");

        var safe = new float[236]; safe[ObservationV2Layout.Lives] = 1;
        safe[ObservationV2Layout.TubeOffset(0)] = 1;
        var rule = new RuleBasedController();
        Check(rule.Decide(new ObservationFrame((float[])safe.Clone())).Value == 0, "Rule-based baseline chooses NONE for a safe current sector");
        var blocked = (float[])safe.Clone();
        blocked[ObservationV2Layout.HazardOffset(0, 6) + ObservationV2Layout.WallOccupancy] = 1;
        Check(rule.Decide(new ObservationFrame(blocked)).Value != 0, "Rule-based baseline steers away from an occupied current sector");
        rule.ResetEpisode(1);
        var heart = (float[])safe.Clone(); heart[ObservationV2Layout.Lives] = 1f / 3f;
        int heartRow = ObservationV2Layout.BonusOffset(0, 0);
        heart[heartRow] = 1; heart[heartRow + 1] = 1; heart[heartRow + 2] = 0; heart[heartRow + 3] = .1f;
        Check(rule.Decide(new ObservationFrame(heart)).Value == 1, "Rule-based baseline values a reachable Heart when lives are missing");
        bool wrongSchemaRejected = false;
        try { rule.Decide(new ObservationFrame(new float[235])); } catch (ArgumentException) { wrongSchemaRejected = true; }
        Check(wrongSchemaRejected && rule.ActionSpaceType == ActionSpaceType.Discrete, "Rule-based baseline accepts only discrete Observation v2 input");

        ResearchSeedCatalog.ValidateAll();
        var train = ResearchSeedCatalog.Load(ResearchSeedSplit.Train);
        var validation = ResearchSeedCatalog.Load(ResearchSeedSplit.Validation);
        var test = ResearchSeedCatalog.Load(ResearchSeedSplit.Test);
        Check(train.Length == 700 && validation.Length == 100 && test.Length == 200, "Seed split sizes are 700/100/200");
        Check(train.Concat(validation).Concat(test).All(seed => seed > 0) && train.Concat(validation).Concat(test).Distinct().Count() == 1000,
            "All protocol seeds are positive int32 and globally unique");
    }

    private void GeometryTests()
    {
        var shape = new GameObject("GeometryProbe");
        var box = shape.AddComponent<BoxCollider>();
        box.size = new Vector3(.5f, 12, 1);
        bool approximate;
        var spans = CircularGeometry.Spans(box, 4, out approximate);
        Check(spans.Count == 2 && !approximate && spans.All(s => s.y < .2f), "Pillar represented by two disjoint narrow angular spans");
        box.size = new Vector3(2, 2, 1); shape.transform.position = new Vector3(4, 0, 0);
        spans = CircularGeometry.Spans(box, 4, out approximate);
        Check(spans.Count == 1 && Mathf.Abs(Mathf.Sin(spans[0].x)) < .001f, "Angular span merges across 0/360 boundary");
        box.size = new Vector3(12, 12, 1); shape.transform.position = Vector3.zero;
        spans = CircularGeometry.Spans(box, 4, out approximate);
        Check(spans.Count == 1 && Mathf.Abs(spans[0].y - Mathf.PI * 2) < .001f, "Full circle occupation");
        shape.transform.position = new Vector3(30, 0, 0);
        Check(CircularGeometry.Spans(box, 4, out approximate).Count == 0, "Collider outside orbit has no occupied span");
        DestroyImmediate(shape);
    }

    private void MetricsTests()
    {
        var tube = new GameObject("MetricsProbe");
        var segment = tube.AddComponent<ResearchSegment>();
        var hazardObject = new GameObject("Logical wall"); hazardObject.transform.SetParent(tube.transform);
        hazardObject.tag = "Wall"; hazardObject.transform.localPosition = new Vector3(0, 0, 10);
        hazardObject.AddComponent<BoxCollider>(); segment.Register(hazardObject);
        int encountered = mode.Current.obstaclesEncountered, avoided = mode.Current.obstaclesAvoided, passed = mode.Current.segmentsPassed;
        segment.Sample(0);
        Check(mode.Current.obstaclesEncountered == encountered, "A future spawned hazard is not yet encountered");
        tube.transform.position = new Vector3(0, 0, -100); Physics.SyncTransforms();
        segment.Sample(0); segment.Sample(0);
        Check(mode.Current.obstaclesEncountered == encountered + 1 && mode.Current.obstaclesAvoided == avoided + 1 && mode.Current.segmentsPassed == passed + 1,
            "Passed segment and avoided logical hazard counted once");
        DestroyImmediate(tube);
    }

    private IEnumerator ContentObservationTests()
    {
        Time.timeScale = 0;
        var savedSegments = mode.Segments.ToArray();
        mode.Segments.Clear();
        var root = new GameObject("ObservationFixture"); root.transform.position = new Vector3(0, 0, 50);
        var segment = root.AddComponent<ResearchSegment>(); mode.Segments.Add(segment);
        var assets = game.allWalls.Cast<ISpawnable>().Concat(game.allObstacles).Concat(game.allGems).ToArray();
        foreach (var location in new[] { GameManager.Location.Inside, GameManager.Location.Outside })
        {
            game.gameLocation = location;
            foreach (var asset in assets)
            {
                var spawned = Instantiate(asset.GetPrefab(), root.transform.position, Quaternion.identity, root.transform);
                ResearchMode.RegisterSpawn(spawned, root.transform);
                yield return null;
                Physics.SyncTransforms();
                var vector = mode.Observations.Capture().Vector;
                var reference = mode.DiagnosticObservationsV1.Capture().Vector;
                int hazardCountV1 = Enumerable.Range(0, ObservationProviderV1.HazardCapacity).Count(i => reference[ObservationProviderV1.GlobalSize + ObservationProviderV1.TubeHeaderSize + i * ObservationProviderV1.HazardSize] == 1);
                float hazardWidthV1 = Enumerable.Range(0, ObservationProviderV1.HazardCapacity).Sum(i => reference[ObservationProviderV1.GlobalSize + ObservationProviderV1.TubeHeaderSize + i * ObservationProviderV1.HazardSize + 5]);
                int bonusCountV1 = Enumerable.Range(0, ObservationProviderV1.BonusCapacity).Count(i => reference[ObservationProviderV1.GlobalSize + ObservationProviderV1.TubeHeaderSize + ObservationProviderV1.HazardCapacity * ObservationProviderV1.HazardSize + i * ObservationProviderV1.BonusSize] == 1);
                float occupancyV2 = Enumerable.Range(0, ObservationV2Layout.SectorCount).Sum(sector =>
                    vector[ObservationV2Layout.HazardOffset(0, sector) + ObservationV2Layout.WallOccupancy] +
                    vector[ObservationV2Layout.HazardOffset(0, sector) + ObservationV2Layout.ObstacleOccupancy]);
                bool strategic = spawned.GetComponentsInChildren<Collider>().Any(c => c.enabled && ObservationProvider.StrategicBonusIndex(c.tag) >= 0);
                int strategicCountV2 = Enumerable.Range(0, 3).Count(bonus => vector[ObservationV2Layout.BonusOffset(0, bonus)] == 1);
                bool contentVisible = asset is Gem
                    ? bonusCountV1 > 0 && strategicCountV2 == (strategic ? 1 : 0)
                    : hazardCountV1 > 0 && vector[ObservationV2Layout.TubeOffset(0) + ObservationV2Layout.HasHazard] == 1 &&
                        (hazardWidthV1 <= .000001f || occupancyV2 > 0);
                Check(vector.Length == 236 && vector.All(v => !float.IsNaN(v) && !float.IsInfinity(v)) &&
                    vector[ObservationV2Layout.Outside] == (location == GameManager.Location.Outside ? 1 : 0) && contentVisible,
                    "Observation v1/v2 authored content " + location + " " + asset.GetPrefab().name + " (v1 hazards " + hazardCountV1 + ", v1 bonuses " + bonusCountV1 + ", v2 occupancy " + occupancyV2.ToString("F3") + ")");
                DestroyImmediate(spawned);
            }
        }

        Check(ObservationV2Layout.TubeCount == 3 && ObservationV2Layout.TubeSize == 76 && ObservationV2Layout.VectorSize == 236,
            "Observation v2 layout is global 8 plus exactly three 76-feature tubes");
        var oneTube = mode.Observations.Capture().Vector;
        Check(oneTube[ObservationV2Layout.TubeOffset(0)] == 1 &&
            oneTube.Skip(ObservationV2Layout.TubeOffset(1)).Take(ObservationV2Layout.TubeSize * 2).All(value => value == 0),
            "Missing second and third tubes are fully zero-padded");
        float expectedTime = ObservationProvider.NormalizeTimeToReach(Mathf.Max(0, root.transform.position.z - game.tubeLength / 2 - Find<PlayerCollision>().transform.position.z) / game.tubeMoveSpeed);
        Check(Mathf.Abs(oneTube[ObservationV2Layout.TubeOffset(0) + ObservationV2Layout.TimeToReach] - expectedTime) < .00001f,
            "Tube timeToReach uses leading-edge distance and current environment speed");
        var extras = new List<GameObject>();
        for (int i = 0; i < 3; i++)
        {
            var extra = new GameObject("ExtraTube" + i); extra.transform.position = new Vector3(0, 0, 80 + i * 30);
            var extraSegment = extra.AddComponent<ResearchSegment>(); extraSegment.Sequence = 100 + i;
            mode.Segments.Add(extraSegment); extras.Add(extra);
        }
        var threeTubes = mode.Observations.Capture().Vector;
        Check(Enumerable.Range(0, 3).All(tube => threeTubes[ObservationV2Layout.TubeOffset(tube)] == 1),
            "Observation v2 exposes at most and exactly the nearest three available tubes");
        foreach (var extra in extras) DestroyImmediate(extra);
        mode.Segments.RemoveAll(segment => !segment || segment != root.GetComponent<ResearchSegment>());

        float radius = new Vector2(Find<PlayerCollision>().transform.position.x, Find<PlayerCollision>().transform.position.y).magnitude;
        float playerAngle = Mathf.Atan2(Find<PlayerCollision>().transform.position.y, Find<PlayerCollision>().transform.position.x);
        Func<string, float, Collider> addBox = (tag, angle) =>
        {
            var child = new GameObject(tag + "Fixture"); child.transform.SetParent(root.transform);
            child.tag = tag; child.transform.position = new Vector3(Mathf.Cos(playerAngle + angle) * radius, Mathf.Sin(playerAngle + angle) * radius, 50);
            var box = child.AddComponent<BoxCollider>(); box.size = new Vector3(1, 1, 1); return box;
        };
        var wall = addBox("Wall", 0); var obstacle = addBox("Obstacle", Mathf.PI / 2);
        var motion = obstacle.gameObject.AddComponent<ObstacleMovement>(); motion.isSideToSide = true;
        var capsuleObject = new GameObject("ApproximateFixture"); capsuleObject.transform.SetParent(root.transform);
        capsuleObject.tag = "Obstacle"; capsuleObject.transform.position = new Vector3(Mathf.Cos(playerAngle - Mathf.PI / 2) * radius, Mathf.Sin(playerAngle - Mathf.PI / 2) * radius, 50);
        capsuleObject.AddComponent<CapsuleCollider>();
        yield return null; Physics.SyncTransforms();
        var features = mode.Observations.Capture().Vector;
        float wallSum = Enumerable.Range(0, 12).Sum(sector => features[ObservationV2Layout.HazardOffset(0, sector) + ObservationV2Layout.WallOccupancy]);
        float obstacleSum = Enumerable.Range(0, 12).Sum(sector => features[ObservationV2Layout.HazardOffset(0, sector) + ObservationV2Layout.ObstacleOccupancy]);
        Check(wallSum > 0 && obstacleSum > 0, "Observation v2 keeps Wall and Obstacle occupancy separate");
        Check(Enumerable.Range(0, 12).Any(sector => features[ObservationV2Layout.HazardOffset(0, sector) + ObservationV2Layout.MovingHazard] == 1), "Observation v2 marks active moving hazards");
        Check(Enumerable.Range(0, 12).Any(sector => features[ObservationV2Layout.HazardOffset(0, sector) + ObservationV2Layout.ApproximateGeometry] == 1), "Observation v2 marks approximate CircularGeometry occupancy");
        Check(Enumerable.Range(0, 12).All(sector => features[ObservationV2Layout.HazardOffset(0, sector) + ObservationV2Layout.WallOccupancy] <= 1 &&
            features[ObservationV2Layout.HazardOffset(0, sector) + ObservationV2Layout.ObstacleOccupancy] <= 1), "Real overlapping hazard occupancy never exceeds one");
        DestroyImmediate(wall.gameObject); DestroyImmediate(obstacle.gameObject); DestroyImmediate(capsuleObject);

        foreach (var bonus in new[] { "Heart", "Shield", "Boost" }) addBox(bonus, (ObservationProvider.StrategicBonusIndex(bonus) - 1) * Mathf.PI / 3);
        var nearerHeart = addBox("Heart", -Mathf.PI / 4); nearerHeart.transform.position = new Vector3(nearerHeart.transform.position.x, nearerHeart.transform.position.y, 40);
        var portal = addBox("Portal", 0);
        yield return null; Physics.SyncTransforms();
        features = mode.Observations.Capture().Vector;
        Check(Enumerable.Range(0, 3).All(bonus => features[ObservationV2Layout.BonusOffset(0, bonus)] == 1), "Observation v2 exposes Heart, Shield and Boost strategic bonuses");
        Check(Mathf.Abs(features[ObservationV2Layout.BonusOffset(0, 0) + 3] -
            Mathf.Clamp01((nearerHeart.bounds.min.z - Find<PlayerCollision>().transform.position.z) / 240f)) < .0001f,
            "Observation v2 selects the nearest available collider of each strategic bonus type");
        Check(features[ObservationV2Layout.TubeOffset(0) + ObservationV2Layout.HasPortal] == 1, "Observation v2 exposes a current Portal in the tube header");
        foreach (Transform child in root.transform.Cast<Transform>().ToArray()) DestroyImmediate(child.gameObject);
        addBox("Gold", 0); addBox("Diamond", Mathf.PI / 2);
        yield return null; Physics.SyncTransforms();
        features = mode.Observations.Capture().Vector;
        Check(Enumerable.Range(0, 3).All(bonus => features[ObservationV2Layout.BonusOffset(0, bonus)] == 0), "Gold and Diamond remain invisible in Observation v2");

        GameplayRandom.Reset(9123);
        mode.Observations.Capture();
        int afterObservation = GameplayRandom.Range(0, 1000000);
        GameplayRandom.Reset(9123);
        int withoutObservation = GameplayRandom.Range(0, 1000000);
        Check(afterObservation == withoutObservation, "Observation v2 does not consume or reveal future generator randomness");
        DestroyImmediate(root);
        mode.Segments.Clear(); mode.Segments.AddRange(savedSegments);
        Time.timeScale = 1;
    }

    private void Finish(string failure)
    {
        if (finished) return;
        finished = true;
        var lines = new List<string> { "Unity: " + Application.unityVersion, "Failure: " + (failure ?? "none"), "Resets observed: " + resets };
        lines.AddRange(checks.Select(check => "PASS " + check));
        File.WriteAllLines(Path.Combine(Directory.GetCurrentDirectory(), "research-result.txt"), lines);
#if UNITY_EDITOR
        UnityEditor.EditorApplication.delayCall += () => UnityEditor.EditorApplication.Exit(failure == null ? 0 : 1);
#endif
    }
}
