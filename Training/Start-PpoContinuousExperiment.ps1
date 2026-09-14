[CmdletBinding()]
param(
    [int]$Workers = 6,
    [double]$TimeScale = 20,
    [switch]$AllowDirty,
    [switch]$RebuildWorker,
    [switch]$SkipExisting
)

$ErrorActionPreference = "Stop"
$TrainingRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $TrainingRoot
$RunsRoot = Join-Path $TrainingRoot "runs"
$Python = Join-Path $TrainingRoot ".venv\Scripts\python.exe"
$Worker = Join-Path $RepositoryRoot "Builds\ResearchWorker\TurboDashResearchWorker.exe"
$TrainingScript = Join-Path $TrainingRoot "Start-PpoContinuousOvernight.ps1"
$ValidationScript = Join-Path $TrainingRoot "Validate-PpoContinuous.ps1"
$LogPath = Join-Path $RunsRoot "ppo-continuous-experiment.log"
$Stopwatch = [Diagnostics.Stopwatch]::StartNew()
$Runs = @(
    @{ RunId = "ppo-continuous-5m-run1"; Seed = 20260916; ValidationId = "ppo-continuous-run1-best-validation-500" },
    @{ RunId = "ppo-continuous-5m-run2"; Seed = 20260917; ValidationId = "ppo-continuous-run2-best-validation-500" },
    @{ RunId = "ppo-continuous-5m-run3"; Seed = 20260918; ValidationId = "ppo-continuous-run3-best-validation-500" }
)

New-Item -ItemType Directory -Force -Path $RunsRoot | Out-Null
function Write-ExperimentLog([string]$Message) {
    $Line = "[{0}] {1}" -f [DateTime]::UtcNow.ToString("o"), $Message
    Write-Host $Line
    Add-Content -LiteralPath $LogPath -Value $Line -Encoding UTF8
}
function Test-CompletedTrainingRun($Run) {
    $RunRoot = Join-Path $RunsRoot $Run.RunId
    $ManifestPath = Join-Path $RunRoot "manifest.json"
    $ModelPath = Join-Path $RunRoot "best_model\model.zip"
    $SelectionPath = Join-Path $RunRoot "best_model\selection.json"
    if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf) -or
        -not (Test-Path -LiteralPath $ModelPath -PathType Leaf) -or
        -not (Test-Path -LiteralPath $SelectionPath -PathType Leaf)) { return $false }
    $Manifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $ManifestPath | ConvertFrom-Json
    return $Manifest.status -eq "complete" -and
        $Manifest.configuration.action_space -eq "Continuous" -and
        [int]$Manifest.configuration.experiment_seed -eq [int]$Run.Seed -and
        [int64]$Manifest.configuration.total_timesteps -eq 5000000 -and
        [int]$Manifest.configuration.workers -eq $Workers -and
        [double]$Manifest.configuration.time_scale -eq $TimeScale
}
function Test-CompletedValidation($Run) {
    $SummaryPath = Join-Path $RunsRoot "$($Run.ValidationId)\validation\all-100\summary.json"
    $ModelPath = Join-Path $RunsRoot "$($Run.RunId)\best_model\model.zip"
    if (-not (Test-Path -LiteralPath $SummaryPath -PathType Leaf)) { return $false }
    if (-not (Test-Path -LiteralPath $ModelPath -PathType Leaf)) { return $false }
    $Summary = Get-Content -Raw -Encoding UTF8 -LiteralPath $SummaryPath | ConvertFrom-Json
    $ExpectedHash = (Get-FileHash -LiteralPath $ModelPath -Algorithm SHA256).Hash.ToLowerInvariant()
    return [int]$Summary.episodes -eq 100 -and $Summary.action_space -eq "Continuous" -and
        [double]$Summary.max_duration -eq 500 -and
        $Summary.model_sha256 -eq $ExpectedHash -and
        $Summary.test_status -eq "UNUSED FOR TRAINING/TUNING/EVALUATION"
}

try {
    Write-ExperimentLog "PPO Continuous experiment started. Runs are sequential; TEST is UNUSED."
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Run Training\Setup-Venv.ps1 first." }
    if ($RebuildWorker -or -not (Test-Path -LiteralPath $Worker -PathType Leaf)) {
        Write-ExperimentLog "Research Worker build started."
        & (Join-Path $TrainingRoot "Build-ResearchWorker.ps1")
        Write-ExperimentLog "Research Worker build completed."
    }
    foreach ($Run in $Runs) {
        if ($SkipExisting -and (Test-CompletedTrainingRun $Run)) {
            Write-ExperimentLog "Training $($Run.RunId) already complete and verified; skipping."
            continue
        }
        Write-ExperimentLog "Training $($Run.RunId) started (seed $($Run.Seed), 5,000,000 transitions)."
        $Parameters = @{
            RunId = $Run.RunId; Timesteps = 5000000; Workers = $Workers
            TimeScale = $TimeScale; ExperimentSeed = $Run.Seed
        }
        if ($AllowDirty) { $Parameters.AllowDirty = $true }
        & $TrainingScript @Parameters
        if (-not (Test-CompletedTrainingRun $Run)) {
            throw "Training $($Run.RunId) failed or its artifacts did not pass verification."
        }
        Write-ExperimentLog "Training $($Run.RunId) completed; worker processes closed."
    }
    foreach ($Run in $Runs) {
        if ($SkipExisting -and (Test-CompletedValidation $Run)) {
            Write-ExperimentLog "Validation $($Run.ValidationId) already complete and verified; skipping."
            continue
        }
        $Model = Join-Path $RunsRoot "$($Run.RunId)\best_model\model.zip"
        Write-ExperimentLog "Validation $($Run.ValidationId) started (100 VALIDATION seeds, MaxDuration 500 s)."
        & $ValidationScript -Model $Model -RunId $Run.ValidationId -Workers $Workers -TimeScale $TimeScale -MaxDuration 500
        if (-not (Test-CompletedValidation $Run)) {
            throw "Validation $($Run.ValidationId) failed or its artifacts did not pass verification."
        }
        Write-ExperimentLog "Validation $($Run.ValidationId) completed; worker processes closed."
    }
    Write-ExperimentLog "Final JSON/CSV summary generation started."
    Push-Location $TrainingRoot
    try {
        $WallSeconds = $Stopwatch.Elapsed.TotalSeconds.ToString([Globalization.CultureInfo]::InvariantCulture)
        & $Python -m turbodash.experiment_summary --wall-seconds $WallSeconds
        if ($LASTEXITCODE -ne 0) { throw "Final experiment summary generation failed." }
    } finally { Pop-Location }
    $Stopwatch.Stop()
    Write-ExperimentLog ("Experiment completed in {0:N1} wall-clock seconds." -f $Stopwatch.Elapsed.TotalSeconds)
} catch {
    $Stopwatch.Stop()
    Write-ExperimentLog ("Experiment stopped after {0:N1} seconds: {1}" -f $Stopwatch.Elapsed.TotalSeconds, $_.Exception.Message)
    throw
}
