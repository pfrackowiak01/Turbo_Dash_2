[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Checkpoint,
    [string]$SchedulerState = "",
    [int64]$TargetTimesteps = 5000000,
    [int]$Workers = 4,
    [double]$TimeScale = 20,
    [string]$RunId = "",
    [switch]$AllowDirty
)

$ErrorActionPreference = "Stop"
$TrainingRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $TrainingRoot
$Python = Join-Path $TrainingRoot ".venv\Scripts\python.exe"
$Worker = Join-Path $RepositoryRoot "Builds\ResearchWorker\TurboDashResearchWorker.exe"
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Run Training\Setup-Venv.ps1 first." }
if (-not (Test-Path -LiteralPath $Worker -PathType Leaf)) { throw "Run Training\Build-ResearchWorker.ps1 first." }
$Checkpoint = [IO.Path]::GetFullPath($Checkpoint)
if ($SchedulerState) { $SchedulerState = [IO.Path]::GetFullPath($SchedulerState) }
$Arguments = @("-m", "turbodash.train", "--worker-exe", $Worker, "--resume", $Checkpoint,
    "--workers", $Workers, "--time-scale", $TimeScale.ToString([Globalization.CultureInfo]::InvariantCulture),
    "--timesteps", $TargetTimesteps)
if ($SchedulerState) { $Arguments += @("--scheduler-state", $SchedulerState) }
if ($RunId) { $Arguments += @("--run-id", $RunId) }
if ($AllowDirty) { $Arguments += "--allow-dirty" }
Push-Location $TrainingRoot
try {
    & $Python @Arguments
    if ($LASTEXITCODE -ne 0) { throw "PPO resume failed with exit code $LASTEXITCODE." }
} finally { Pop-Location }
