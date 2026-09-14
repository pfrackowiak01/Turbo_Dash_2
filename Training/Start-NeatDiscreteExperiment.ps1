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
$TrainingScript = Join-Path $TrainingRoot "Start-NeatDiscreteOvernight.ps1"
$ValidationScript = Join-Path $TrainingRoot "Validate-NeatDiscrete.ps1"
$LogPath = Join-Path $RunsRoot "neat-discrete-experiment.log"
$Stopwatch = [Diagnostics.Stopwatch]::StartNew()
$Runs = @(
    @{ RunId = "neat-discrete-5m-run1"; Seed = 20260919; ValidationId = "neat-discrete-run1-best-validation-500" },
    @{ RunId = "neat-discrete-5m-run2"; Seed = 20260920; ValidationId = "neat-discrete-run2-best-validation-500" },
    @{ RunId = "neat-discrete-5m-run3"; Seed = 20260921; ValidationId = "neat-discrete-run3-best-validation-500" }
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
    $GenomePath = Join-Path $RunRoot "best_model\genome.pkl"
    $ConfigPath = Join-Path $RunRoot "best_model\config.ini"
    $SelectionPath = Join-Path $RunRoot "best_model\selection.json"
    if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf) -or
        -not (Test-Path -LiteralPath $GenomePath -PathType Leaf) -or
        -not (Test-Path -LiteralPath $ConfigPath -PathType Leaf) -or
        -not (Test-Path -LiteralPath $SelectionPath -PathType Leaf)) { return $false }
    $Manifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $ManifestPath | ConvertFrom-Json
    $Selection = Get-Content -Raw -Encoding UTF8 -LiteralPath $SelectionPath | ConvertFrom-Json
    $GenomeHash = (Get-FileHash -LiteralPath $GenomePath -Algorithm SHA256).Hash.ToLowerInvariant()
    $ConfigHash = (Get-FileHash -LiteralPath $ConfigPath -Algorithm SHA256).Hash.ToLowerInvariant()
    return $Manifest.status -eq "complete" -and $Manifest.algorithm -eq "NEAT Discrete" -and
        $Manifest.configuration.action_space -eq "Discrete" -and
        $Manifest.configuration.library_version -eq "2.0.0" -and
        [int]$Manifest.configuration.experiment_seed -eq [int]$Run.Seed -and
        [int64]$Manifest.configuration.target_transitions -eq 5000000 -and
        [int64]$Manifest.result.cumulative_training_transitions -ge 5000000 -and
        [int]$Manifest.configuration.population_size -eq 64 -and
        [int]$Manifest.configuration.workers -eq $Workers -and
        [double]$Manifest.configuration.time_scale -eq $TimeScale -and
        $Selection.genome_sha256 -eq $GenomeHash -and $Selection.config_sha256 -eq $ConfigHash -and
        $Manifest.result.test_status -eq "UNUSED FOR TRAINING/TUNING/EVALUATION"
}
function Test-CompletedValidation($Run) {
    $SummaryPath = Join-Path $RunsRoot "$($Run.ValidationId)\validation\all-100\summary.json"
    $GenomePath = Join-Path $RunsRoot "$($Run.RunId)\best_model\genome.pkl"
    $ConfigPath = Join-Path $RunsRoot "$($Run.RunId)\best_model\config.ini"
    if (-not (Test-Path -LiteralPath $SummaryPath -PathType Leaf) -or
        -not (Test-Path -LiteralPath $GenomePath -PathType Leaf) -or
        -not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) { return $false }
    $Summary = Get-Content -Raw -Encoding UTF8 -LiteralPath $SummaryPath | ConvertFrom-Json
    $GenomeHash = (Get-FileHash -LiteralPath $GenomePath -Algorithm SHA256).Hash.ToLowerInvariant()
    $ConfigHash = (Get-FileHash -LiteralPath $ConfigPath -Algorithm SHA256).Hash.ToLowerInvariant()
    return [int]$Summary.episodes -eq 100 -and $Summary.algorithm -eq "NEAT" -and
        $Summary.action_space -eq "Discrete" -and [double]$Summary.max_duration -eq 500 -and
        $Summary.genome_sha256 -eq $GenomeHash -and $Summary.config_sha256 -eq $ConfigHash -and
        $Summary.test_status -eq "UNUSED FOR TRAINING/TUNING/EVALUATION"
}

try {
    Write-ExperimentLog "NEAT Discrete experiment started. Runs are sequential; TEST is UNUSED."
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Run Training\Setup-Venv.ps1 first." }
    if ($RebuildWorker -or -not (Test-Path -LiteralPath $Worker -PathType Leaf)) {
        Write-ExperimentLog "Research Worker build started."
        & (Join-Path $TrainingRoot "Build-ResearchWorker.ps1")
        Write-ExperimentLog "Research Worker build completed."
    }
    if (-not (Test-Path -LiteralPath $Worker -PathType Leaf)) { throw "Research Worker build is missing." }
    foreach ($Run in $Runs) {
        if ($SkipExisting -and (Test-CompletedTrainingRun $Run)) {
            Write-ExperimentLog "Training $($Run.RunId) already complete and verified; skipping."
            continue
        }
        Write-ExperimentLog "Training $($Run.RunId) started (seed $($Run.Seed), 5,000,000 transitions)."
        $Parameters = @{
            RunId = $Run.RunId; TargetTransitions = 5000000; Workers = $Workers
            TimeScale = $TimeScale; ExperimentSeed = $Run.Seed
        }
        if ($AllowDirty) { $Parameters.AllowDirty = $true }
        & $TrainingScript @Parameters
        if (-not (Test-CompletedTrainingRun $Run)) {
            throw "Training $($Run.RunId) failed or its artifacts did not pass verification."
        }
        Write-ExperimentLog "Training $($Run.RunId) completed; all worker processes closed."
    }
    foreach ($Run in $Runs) {
        if ($SkipExisting -and (Test-CompletedValidation $Run)) {
            Write-ExperimentLog "Validation $($Run.ValidationId) already complete and verified; skipping."
            continue
        }
        $Genome = Join-Path $RunsRoot "$($Run.RunId)\best_model\genome.pkl"
        $Config = Join-Path $RunsRoot "$($Run.RunId)\best_model\config.ini"
        Write-ExperimentLog "Validation $($Run.ValidationId) started (100 VALIDATION seeds, MaxDuration 500 s)."
        & $ValidationScript -Genome $Genome -Config $Config -RunId $Run.ValidationId -Workers $Workers -TimeScale $TimeScale -MaxDuration 500
        if (-not (Test-CompletedValidation $Run)) {
            throw "Validation $($Run.ValidationId) failed or its artifacts did not pass verification."
        }
        Write-ExperimentLog "Validation $($Run.ValidationId) completed; all worker processes closed."
    }
    Write-ExperimentLog "Final JSON/CSV summary generation started."
    Push-Location $TrainingRoot
    try {
        $WallSeconds = $Stopwatch.Elapsed.TotalSeconds.ToString([Globalization.CultureInfo]::InvariantCulture)
        & $Python -m turbodash.neat_experiment_summary --wall-seconds $WallSeconds
        if ($LASTEXITCODE -ne 0) { throw "Final NEAT summary generation failed." }
    } finally {
        Pop-Location
    }
    $Stopwatch.Stop()
    Write-ExperimentLog ("Experiment completed in {0:N1} wall-clock seconds." -f $Stopwatch.Elapsed.TotalSeconds)
} catch {
    $Stopwatch.Stop()
    Write-ExperimentLog ("Experiment stopped after {0:N1} seconds: {1}" -f $Stopwatch.Elapsed.TotalSeconds, $_.Exception.Message)
    throw
}
