[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$State,
    [int]$Workers = 6,
    [double]$TimeScale = 20,
    [int64]$TargetTransitions = 0,
    [ValidateSet("training", "smoke")][string]$Purpose = "training",
    [int]$MaxGenerations = 0,
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
    "-m", "turbodash.neat_train", "--resume-state", $State, "--worker-exe", $Worker,
    "--workers", $Workers, "--time-scale", $TimeScale.ToString([Globalization.CultureInfo]::InvariantCulture),
    "--purpose", $Purpose
)
if ($TargetTransitions -gt 0) { $Arguments += @("--target-transitions", $TargetTransitions) }
if ($MaxGenerations -gt 0) { $Arguments += @("--max-generations", $MaxGenerations) }
if ($AllowDirty) { $Arguments += "--allow-dirty" }
Push-Location $TrainingRoot
try {
    & $Python @Arguments
    if ($LASTEXITCODE -ne 0) { throw "NEAT Discrete resume failed with exit code $LASTEXITCODE." }
} finally {
    Pop-Location
}
