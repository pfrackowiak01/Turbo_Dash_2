using System;
using System.IO;
using UnityEditor;
using UnityEditor.Build.Reporting;

namespace TurboDash.Research.Editor
{
    public static class ResearchWorkerBuild
    {
        private const string WorkerScene = "Assets/Turbo_Dash/Design/Scenes/DeafultLevel.unity";

        public static void BuildWindows64()
        {
            string[] args = Environment.GetCommandLineArgs();
            int index = Array.IndexOf(args, "--worker-build-output");
            string output = index >= 0 && index + 1 < args.Length
                ? Path.GetFullPath(args[index + 1])
                : Path.GetFullPath("Builds/ResearchWorker/TurboDashResearchWorker.exe");
            Directory.CreateDirectory(Path.GetDirectoryName(output));
            var build = new BuildPlayerOptions
            {
                scenes = new[] { WorkerScene },
                locationPathName = output,
                target = BuildTarget.StandaloneWindows64,
                options = BuildOptions.None
            };
            BuildReport report = BuildPipeline.BuildPlayer(build);
            if (report.summary.result != BuildResult.Succeeded)
                throw new InvalidOperationException("Research Worker build failed: " + report.summary.result);
            UnityEngine.Debug.Log("Research Worker build: " + output + " (" + report.summary.totalSize + " bytes)");
        }
    }
}
