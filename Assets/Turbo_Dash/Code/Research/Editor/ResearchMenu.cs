using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace TurboDash.Research.Editor
{
    public sealed class ResearchMenu : EditorWindow
    {
        private ResearchOptions options = new ResearchOptions();
        [MenuItem("Turbo Dash/Research/Configure and run")]
        public static void Open() { GetWindow<ResearchMenu>("Turbo Dash Research"); }
        private void OnGUI()
        {
            EditorGUILayout.HelpBox("Diagnostic NoAction controller. Defaults are a smoke test, not research parameters. Zero limits disable a limit.", MessageType.Info);
            options.initialSeed = EditorGUILayout.IntField("First seed", options.initialSeed);
            options.episodeCount = EditorGUILayout.IntField("Episodes (0 = unlimited)", options.episodeCount);
            options.maxDuration = EditorGUILayout.FloatField("Max duration (game seconds)", options.maxDuration);
            options.maxScore = EditorGUILayout.FloatField("Max score", options.maxScore);
            options.csvPath = EditorGUILayout.TextField("CSV path (empty = automatic)", options.csvPath);
            GUI.enabled = !EditorApplication.isPlayingOrWillChangePlaymode;
            if (GUILayout.Button("Start research episodes"))
            {
                options.Validate();
                if (!EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo()) return;
                SessionState.SetString(ResearchMode.EditorRequestKey, JsonUtility.ToJson(options));
                RunBatch();
            }
            GUI.enabled = true;
        }
        // Also accepts -turboResearchConfig <JSON path> in batch mode.
        public static void RunBatch()
        {
            if (Application.isBatchMode) SessionState.SetBool("TurboDash.Research.BatchExit", true);
            EditorSceneManager.OpenScene("Assets/Turbo_Dash/Design/Scenes/DeafultLevel.unity");
            EditorApplication.EnterPlaymode();
        }
        [InitializeOnLoadMethod]
        private static void InstallCleanup()
        {
            EditorApplication.update += () =>
            {
                if (!Application.isBatchMode || !SessionState.GetBool("TurboDash.Research.BatchExit", false) || !ResearchMode.Active) return;
                if (ResearchMode.Instance.State == EpisodeState.Finished || ResearchMode.Instance.State == EpisodeState.Faulted)
                {
                    SessionState.SetBool("TurboDash.Research.BatchExit", false);
                    EditorApplication.Exit(ResearchMode.Instance.State == EpisodeState.Finished ? 0 : 1);
                }
            };
            EditorApplication.playModeStateChanged += change =>
            {
                if (change == PlayModeStateChange.EnteredEditMode) SessionState.EraseString(ResearchMode.EditorRequestKey);
            };
        }
    }
}
