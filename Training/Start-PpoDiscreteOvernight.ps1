[CmdletBinding()]
param(
    [int]$Workers = 6,
    [double]$TimeScale = 20,
    [int64]$Timesteps = 5000000,
    [int]$ExperimentSeed = 20260913,
    [string]$RunId = "",
    [switch]$AllowDirty,
    [switch]$RebuildWorker
)

$ErrorActionPreference = "Stop"
$TrainingRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $TrainingRoot
$Python = Join-Path $TrainingRoot ".venv\Scripts\python.exe"
$Worker = Join-Path $RepositoryRoot "Builds\ResearchWorker\TurboDashResearchWorker.exe"
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Run Training\Setup-Venv.ps1 first." }
if ($RebuildWorker -or -not (Test-Path -LiteralPath $Worker -PathType Leaf)) {
    & (Join-Path $TrainingRoot "Build-ResearchWorker.ps1")
    if ($LASTEXITCODE -ne 0) { throw "Research Worker build failed." }
}
$Arguments = @("-m", "turbodash.train", "--worker-exe", $Worker, "--workers", $Workers,
    "--time-scale", $TimeScale.ToString([Globalization.CultureInfo]::InvariantCulture),
    "--timesteps", $Timesteps, "--experiment-seed", $ExperimentSeed)
if ($RunId) { $Arguments += @("--run-id", $RunId) }
if ($AllowDirty) { $Arguments += "--allow-dirty" }
Push-Location $TrainingRoot
try {
    & $Python -c "from turbodash.protocol import *; assert RESEARCH_PROTOCOL_VERSION == 1 and OBSERVATION_SCHEMA_VERSION == 2 and OBSERVATION_SIZE == 236"
    if ($LASTEXITCODE -ne 0) { throw "Research Protocol verification failed." }
    & $Python @Arguments
    if ($LASTEXITCODE -ne 0) { throw "PPO training failed with exit code $LASTEXITCODE." }
} finally {
    Pop-Location
}
