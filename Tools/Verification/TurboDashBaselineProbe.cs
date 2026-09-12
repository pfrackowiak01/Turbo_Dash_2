// Copy this file into Assets/Editor ONLY in an isolated verification project.
// Unity -batchmode -projectPath <copy> -executeMethod TurboDashBaselineProbe.Run -logFile <log>
using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

[InitializeOnLoad]
public static class TurboDashBaselineProbe
{
    const string Key = "TurboDash.BaselineProbe";
    static int step;
    static double next, deadline;
    static readonly List<string> checks = new List<string>();
    static readonly List<string> errors = new List<string>();
    static GameObject contact;
    static GameManager gm;
    static bool listening;
    static bool generatedPortalSeen;
    static TurboDashBaselineProbe() { EditorApplication.update += Tick; }

    public static void Run()
    {
        SessionState.SetBool(Key, true);
        EditorSceneManager.OpenScene("Assets/Turbo_Dash/Design/Scenes/Menu.unity");
        EditorApplication.EnterPlaymode();
    }

    static void Check(bool value, string name)
    {
        if (!value) throw new Exception(name);
        checks.Add(name);
        Debug.Log("BASELINE PASS: " + name);
    }

    static T Find<T>() where T : UnityEngine.Object { return UnityEngine.Object.FindObjectOfType<T>(); }
    static void Hit(string tag)
    {
        if (contact) UnityEngine.Object.DestroyImmediate(contact);
        contact = new GameObject("VerificationContact");
        var child = new GameObject("Contact");
        child.transform.SetParent(contact.transform);
        child.tag = tag;
        child.transform.position = Find<PlayerCollision>().transform.position;
        child.AddComponent<BoxCollider>().isTrigger = true;
        child.AddComponent<Rigidbody>().isKinematic = true;
        Physics.SyncTransforms();
    }

    static void Tick()
    {
        if (!SessionState.GetBool(Key, false) || !EditorApplication.isPlaying || EditorApplication.isCompiling) return;
        if (!listening)
        {
            listening = true;
            deadline = EditorApplication.timeSinceStartup + 120;
            next = EditorApplication.timeSinceStartup + 2;
            Application.logMessageReceived += OnLog;
        }
        if (EditorApplication.timeSinceStartup > deadline) { Finish("Timeout at step " + step); return; }
        if (EditorApplication.timeSinceStartup < next) return;
        next = EditorApplication.timeSinceStartup + .25;
        if (step == 6 && gm.gameLocation != GameManager.Location.Outside)
        {
            if (GameObject.FindGameObjectsWithTag("Portal").Length > 0) generatedPortalSeen = true;
            return;
        }
        try
        {
            switch (step++)
            {
                case 0:
                    Check(SceneManager.GetActiveScene().name == "Menu", "Menu loaded");
                    Find<UIMenu>().NextGameMode();
                    Check(SaveAndLoadManager.Instance.usedGameMode.Index == 1, "TouchControl selected through menu handler");
                    Find<LevelLoader>().PlayButtonClicked(); next += 2; break;
                case 1:
                    gm = GameManager.Instance;
                    Check(SceneManager.GetActiveScene().name == "DeafultLevel" && gm, "Gameplay loaded from Menu");
                    Check(gm.gameStart && gm.gamePaused && gm.playerLives == 3, "Initial instruction state and three lives");
                    Find<LevelLoader>().StartGameButton(); break;
                case 2:
                    Check(!gm.gameStart && !gm.gamePaused && Time.timeScale == 1, "Start button resumes game");
                    Check(gm.gameLocation == GameManager.Location.Inside && gm.gameScore > 0, "Inside score advances");
                    var movement = Find<EnvironmentMovement>();
                    var flags = BindingFlags.NonPublic | BindingFlags.Instance;
                    foreach (int action in new[] { 1, 0, -1 })
                    {
                        float before = movement.transform.eulerAngles.z;
                        var legacyMethod = movement.GetType().GetMethod("PlayerMovementByDirections", flags);
                        if (legacyMethod != null)
                        {
                            movement.GetType().GetField("leftClicked", flags).SetValue(movement, action == 1);
                            movement.GetType().GetField("rightClicked", flags).SetValue(movement, action == -1);
                            legacyMethod.Invoke(movement, null);
                        }
                        else
                        {
                            var human = movement.GetType().Assembly.GetType("TurboDash.Research.HumanController");
                            float rate = (float)human.GetMethod("ManualDegreesPerSecond").Invoke(null, new object[] { action == 1, action == -1, movement.rotationSpeed });
                            movement.GetType().GetMethod("ApplyDegreesPerSecond").Invoke(movement, new object[] { rate, Time.deltaTime });
                        }
                        float delta = Mathf.DeltaAngle(before, movement.transform.eulerAngles.z);
                        Check(action == 0 ? Mathf.Abs(delta) < .001f : delta * action > 0, "Control rotation " + action + " via supplied input flags");
                    }
                    gm.timer = 1001; break;
                case 3: Check(gm.gameLevel == 2 && gm.tubeMoveSpeed == 55, "Score threshold level 2"); gm.timer = 2001; break;
                case 4: Check(gm.gameLevel == 3 && gm.tubeMoveSpeed == 60, "Score threshold level 3"); gm.timer = 2801; break;
                case 5:
                    Check(gm.isPortalGoingToSpawn, "Portal requested after 2800");
                    // Test fixture protection while the real generated portal travels to the player.
                    gm.turboEffectEnable = true; break;
                case 6:
                    Check(gm.gameLocation == GameManager.Location.Outside && gm.gameLevel == 4 && gm.gameScore >= 3000, "Physics portal contact: Outside, level 4, FixScore");
                    Check(generatedPortalSeen, "Actual portal prefab generated and reached by world movement");
                    gm.turboEffectEnable = false; gm.playerImmortality = false;
                    if (contact) UnityEngine.Object.DestroyImmediate(contact);
                    Find<EnvironmentManager>().enabled = false;
                    foreach (var tube in UnityEngine.Object.FindObjectsOfType<TubeMovement>()) tube.enabled = false;
                    Hit("Wall"); break;
                case 7: Check(gm.playerLives == 2 && gm.playerImmortality, "Physics wall collision removes one life and grants protection"); Hit("Heart"); break;
                case 8: Check(gm.playerLives == 3, "Physics heart pickup restores a life"); Hit("Shield"); break;
                case 9: Check(gm.playerShield, "Physics shield pickup"); gm.playerImmortality = false; Hit("Obstacle"); break;
                case 10: Check(!gm.playerShield && gm.playerLives == 3, "Shield absorbs physics obstacle hit"); Hit("Boost"); break;
                case 11:
                    Check(Find<UIGame>().turboSlider.value > .39f, "Physics Boost pickup charges meter");
                    Find<LevelLoader>().TurnOnTURBO(); break;
                case 12:
                    Check(gm.turboEffectEnable && gm.playerImmortality, "Human turbo button activates protection and score multiplier");
                    gm.TurnOffTurboEffect(); gm.playerImmortality = false; gm.playerLives = 1; Hit("Wall"); break;
                case 13:
                    Check(gm.gameHasEnded && gm.playerLives == 0 && Mathf.Approximately(Time.timeScale, .4f), "Fatal physics collision enters Game Over");
                    if (contact) UnityEngine.Object.DestroyImmediate(contact);
                    Find<LevelLoader>().RetryGameButton(); next += 1; break;
                case 14:
                    gm = GameManager.Instance;
                    Check(gm && !gm.gameHasEnded && gm.gameStart && gm.playerLives == 3 && gm.gameLevel == 1, "Retry returns to fresh human instruction state");
                    Check(SaveAndLoadManager.Instance && Find<PlayerCollision>(), "Retry retains required services and player");
                    Finish(null); break;
            }
        }
        catch (Exception ex) { Finish(ex.ToString()); }
    }

    static void OnLog(string condition, string stack, LogType type)
    {
        if (type == LogType.Exception || type == LogType.Error || type == LogType.Assert) errors.Add(condition + "\n" + stack);
    }
    static void Finish(string failure)
    {
        SessionState.SetBool(Key, false);
        var lines = new List<string> { "Unity: " + Application.unityVersion, "Failure: " + (failure ?? "none") };
        lines.AddRange(checks.ConvertAll(s => "PASS " + s));
        lines.AddRange(errors.ConvertAll(s => "RUNTIME ERROR " + s));
        File.WriteAllLines(Path.Combine(Directory.GetCurrentDirectory(), "baseline-result.txt"), lines);
        EditorApplication.Exit(failure == null && errors.Count == 0 ? 0 : 1);
    }
}
