[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$State,
    [int]$TargetGenerations = 200,
    [ValidateSet("training", "smoke")][string]$Purpose = "training",
    [double]$TrainingMaxDuration = 300,
    [switch]$AllowDirty
)

$ErrorActionPreference = "Stop"
$TrainingRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $TrainingRoot
$Python = Join-Path $TrainingRoot ".venv\Scripts\python.exe"
$Worker = Join-Path $RepositoryRoot "Builds\ResearchWorker\TurboDashResearchWorker.exe"
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Run Training\Setup-Venv.ps1 first." }
if (-not (Test-Path -LiteralPath $Worker -PathType Leaf)) { throw "Run Training\Build-ResearchWorker.ps1 first." }
$State = [IO.Path]::GetFullPath($State)
$Arguments = @(
    "-m", "turbodash.neat_v2_train", "--resume-state", $State, "--worker-exe", $Worker,
    "--target-generations", $TargetGenerations, "--workers", 6, "--time-scale", 20,
    "--training-max-duration", $TrainingMaxDuration.ToString([Globalization.CultureInfo]::InvariantCulture),
    "--purpose", $Purpose
)
if ($AllowDirty) { $Arguments += "--allow-dirty" }
Push-Location $TrainingRoot
try {
    & $Python @Arguments
    if ($LASTEXITCODE -ne 0) { throw "NEAT Discrete v2 resume failed with exit code $LASTEXITCODE." }
} finally {
    Pop-Location
}
