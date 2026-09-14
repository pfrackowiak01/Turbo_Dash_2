[CmdletBinding()]
param(
    [string]$RunId = "",
    [int64]$Timesteps = 5000000,
    [int]$Workers = 6,
    [double]$TimeScale = 20,
    [int]$ExperimentSeed = 20260916,
    [switch]$AllowDirty,
    [switch]$RebuildWorker
)

$ErrorActionPreference = "Stop"
$TrainingRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $TrainingRoot
$Python = Join-Path $TrainingRoot ".venv\Scripts\python.exe"
$Worker = Join-Path $RepositoryRoot "Builds\ResearchWorker\TurboDashResearchWorker.exe"
$Config = Join-Path $TrainingRoot "configs\ppo_continuous_v1.json"
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Run Training\Setup-Venv.ps1 first." }
if ($RebuildWorker -or -not (Test-Path -LiteralPath $Worker -PathType Leaf)) {
    & (Join-Path $TrainingRoot "Build-ResearchWorker.ps1")
}
$Arguments = @("-m", "turbodash.train", "--config", $Config, "--worker-exe", $Worker,
    "--workers", $Workers, "--time-scale", $TimeScale.ToString([Globalization.CultureInfo]::InvariantCulture),
    "--timesteps", $Timesteps, "--experiment-seed", $ExperimentSeed)
if ($RunId) { $Arguments += @("--run-id", $RunId) }
if ($AllowDirty) { $Arguments += "--allow-dirty" }
Push-Location $TrainingRoot
try {
    & $Python -c "from turbodash.protocol import *; assert RESEARCH_PROTOCOL_VERSION == 1 and OBSERVATION_SCHEMA_VERSION == 2 and OBSERVATION_SIZE == 236 and ActionSpace.CONTINUOUS == 1"
    if ($LASTEXITCODE -ne 0) { throw "Research Protocol verification failed." }
    & $Python @Arguments
    if ($LASTEXITCODE -ne 0) { throw "PPO Continuous training failed with exit code $LASTEXITCODE." }
} finally {
    Pop-Location
}
