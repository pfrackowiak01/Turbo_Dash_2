[CmdletBinding()]
param(
    [string]$UnityPath = "D:\Aplikacje\2022.3.4f1\Editor\Unity.exe",
    [string]$Output = ""
)

$ErrorActionPreference = "Stop"
$RepositoryRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not $Output) { $Output = Join-Path $RepositoryRoot "Builds\ResearchWorker\TurboDashResearchWorker.exe" }
$Output = [IO.Path]::GetFullPath($Output)
if (-not (Test-Path -LiteralPath $UnityPath -PathType Leaf)) { throw "Unity 2022.3.4f1 was not found: $UnityPath" }

$TempRoot = Join-Path ([IO.Path]::GetPathRoot($RepositoryRoot)) "Temp"
$Staging = Join-Path $TempRoot "TurboDash-ResearchWorker-BuildCache"
$ResolvedStaging = [IO.Path]::GetFullPath($Staging)
if (-not $ResolvedStaging.StartsWith([IO.Path]::GetFullPath($TempRoot), [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to use a staging path outside the system temporary directory."
}
$Log = Join-Path $RepositoryRoot "Builds\ResearchWorker\build.log"
New-Item -ItemType Directory -Force -Path $ResolvedStaging | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Output) | Out-Null
Copy-Item -LiteralPath (Join-Path $RepositoryRoot "Assets") -Destination $ResolvedStaging -Recurse -Force
Copy-Item -LiteralPath (Join-Path $RepositoryRoot "Packages") -Destination $ResolvedStaging -Recurse -Force
Copy-Item -LiteralPath (Join-Path $RepositoryRoot "ProjectSettings") -Destination $ResolvedStaging -Recurse -Force
$UnityArguments = @("-batchmode", "-quit", "-projectPath", ('"' + $ResolvedStaging + '"'),
    "-executeMethod", "TurboDash.Research.Editor.ResearchWorkerBuild.BuildWindows64",
    "--worker-build-output", ('"' + $Output + '"'), "-logFile", ('"' + $Log + '"'))
$UnityProcess = Start-Process -FilePath $UnityPath -ArgumentList $UnityArguments -Wait -PassThru -WindowStyle Hidden
if ($UnityProcess.ExitCode -ne 0) { throw "Unity worker build failed with exit code $($UnityProcess.ExitCode). See $Log" }
if (-not (Test-Path -LiteralPath $Output -PathType Leaf)) { throw "Unity reported success but did not create $Output" }
Write-Host "Research Worker ready: $Output"
