[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Model,
    [string]$RunId = "",
    [int]$Workers = 6,
    [double]$TimeScale = 20,
    [double]$MaxDuration = 300
)

$ErrorActionPreference = "Stop"
$TrainingRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $TrainingRoot
$Python = Join-Path $TrainingRoot ".venv\Scripts\python.exe"
$Worker = Join-Path $RepositoryRoot "Builds\ResearchWorker\TurboDashResearchWorker.exe"
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Run Training\Setup-Venv.ps1 first." }
if (-not (Test-Path -LiteralPath $Worker -PathType Leaf)) { throw "Run Training\Build-ResearchWorker.ps1 first." }
if ($MaxDuration -le 0) { throw "MaxDuration must be positive." }
$Model = [IO.Path]::GetFullPath($Model)
$Arguments = @("-m", "turbodash.validate_cli", "--model", $Model, "--worker-exe", $Worker,
    "--workers", $Workers, "--time-scale", $TimeScale.ToString([Globalization.CultureInfo]::InvariantCulture),
    "--max-duration", $MaxDuration.ToString([Globalization.CultureInfo]::InvariantCulture),
    "--action-space", "Continuous")
if ($RunId) { $Arguments += @("--run-id", $RunId) }
Push-Location $TrainingRoot
try {
    & $Python @Arguments
    if ($LASTEXITCODE -ne 0) { throw "PPO Continuous validation failed with exit code $LASTEXITCODE." }
} finally {
    Pop-Location
}
