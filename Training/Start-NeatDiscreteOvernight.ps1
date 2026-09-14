[CmdletBinding()]
param(
    [string]$RunId = "",
    [int64]$TargetTransitions = 5000000,
    [int]$Workers = 6,
    [double]$TimeScale = 20,
    [int]$ExperimentSeed = 20260919,
    [ValidateSet("training", "smoke")][string]$Purpose = "training",
    [int]$PopulationSize = 64,
    [double]$TrainingMaxDuration = 300,
    [int]$MaxGenerations = 0,
    [switch]$AllowDirty,
    [switch]$RebuildWorker
)

$ErrorActionPreference = "Stop"
$TrainingRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $TrainingRoot
$Python = Join-Path $TrainingRoot ".venv\Scripts\python.exe"
$Worker = Join-Path $RepositoryRoot "Builds\ResearchWorker\TurboDashResearchWorker.exe"
$Config = Join-Path $TrainingRoot "configs\neat_discrete_v1.json"
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Run Training\Setup-Venv.ps1 first." }
if ($RebuildWorker -or -not (Test-Path -LiteralPath $Worker -PathType Leaf)) {
    & (Join-Path $TrainingRoot "Build-ResearchWorker.ps1")
}
if (-not (Test-Path -LiteralPath $Worker -PathType Leaf)) { throw "Research Worker build is missing." }
$Arguments = @(
    "-m", "turbodash.neat_train", "--config", $Config, "--worker-exe", $Worker,
    "--workers", $Workers, "--time-scale", $TimeScale.ToString([Globalization.CultureInfo]::InvariantCulture),
    "--target-transitions", $TargetTransitions, "--experiment-seed", $ExperimentSeed,
    "--population-size", $PopulationSize,
    "--training-max-duration", $TrainingMaxDuration.ToString([Globalization.CultureInfo]::InvariantCulture),
    "--purpose", $Purpose
)
if ($RunId) { $Arguments += @("--run-id", $RunId) }
if ($MaxGenerations -gt 0) { $Arguments += @("--max-generations", $MaxGenerations) }
if ($AllowDirty) { $Arguments += "--allow-dirty" }
Push-Location $TrainingRoot
try {
    & $Python -c "import importlib.metadata as m; from turbodash.protocol import *; assert m.version('neat-python') == '2.0.0' and RESEARCH_PROTOCOL_VERSION == 1 and OBSERVATION_SCHEMA_VERSION == 2 and OBSERVATION_SIZE == 236 and ActionSpace.DISCRETE == 0"
    if ($LASTEXITCODE -ne 0) { throw "NEAT/Research Protocol verification failed." }
    & $Python @Arguments
    if ($LASTEXITCODE -ne 0) { throw "NEAT Discrete training failed with exit code $LASTEXITCODE." }
} finally {
    Pop-Location
}
