[CmdletBinding()]
param(
    [double]$ComputeMatchSeconds = 0,
    [switch]$RebuildWorker,
    [switch]$AllowDirty,
    [switch]$SkipExisting
)

$ErrorActionPreference = "Stop"
$TrainingRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $TrainingRoot
$RunsRoot = Join-Path $TrainingRoot "runs"
$Python = Join-Path $TrainingRoot ".venv\Scripts\python.exe"
$Worker = Join-Path $RepositoryRoot "Builds\ResearchWorker\TurboDashResearchWorker.exe"
$TrainingScript = Join-Path $TrainingRoot "Start-NeatDiscreteV2Overnight.ps1"
$LogPath = Join-Path $RunsRoot "neat-discrete-v2-experiment.log"
$Stopwatch = [Diagnostics.Stopwatch]::StartNew()
$Runs = @(
    @{ RunId = "neat-discrete-v2-200g-run1"; Seed = 20260922 },
    @{ RunId = "neat-discrete-v2-200g-run2"; Seed = 20260923 },
    @{ RunId = "neat-discrete-v2-200g-run3"; Seed = 20260924 }
)

New-Item -ItemType Directory -Force -Path $RunsRoot | Out-Null
function Write-ExperimentLog([string]$Message) {
    $Line = "[{0}] {1}" -f [DateTime]::UtcNow.ToString("o"), $Message
    Write-Host $Line
    Add-Content -LiteralPath $LogPath -Value $Line -Encoding UTF8
}
function Test-CompletedRun($Run) {
    $Root = Join-Path $RunsRoot $Run.RunId
    $ManifestPath = Join-Path $Root "manifest.json"
    $SelectionsPath = Join-Path $Root "selected_models\selections.json"
    if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf) -or
        -not (Test-Path -LiteralPath $SelectionsPath -PathType Leaf)) { return $false }
    $Manifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $ManifestPath | ConvertFrom-Json
    if ($Manifest.status -ne "complete" -or $Manifest.algorithm -ne "NEAT Discrete v2" -or
        [int]$Manifest.pipeline_version -ne 2 -or [int]$Manifest.configuration.experiment_seed -ne [int]$Run.Seed -or
        [int]$Manifest.result.generations_completed -ne 200 -or
        $Manifest.result.test_status -ne "UNUSED FOR TRAINING/TUNING/EVALUATION") { return $false }
    foreach ($Name in @("best_interaction_matched", "best_wallclock_matched", "best_200_generations")) {
        $Directory = Join-Path $Root "selected_models\$Name"
        $Genome = Join-Path $Directory "genome.pkl"
        $Config = Join-Path $Directory "config.ini"
        $Selection = Join-Path $Directory "selection.json"
        if (-not (Test-Path -LiteralPath $Genome -PathType Leaf) -or
            -not (Test-Path -LiteralPath $Config -PathType Leaf) -or
            -not (Test-Path -LiteralPath $Selection -PathType Leaf)) { return $false }
        $Data = Get-Content -Raw -Encoding UTF8 -LiteralPath $Selection | ConvertFrom-Json
        if ($Data.genome_sha256 -ne (Get-FileHash -LiteralPath $Genome -Algorithm SHA256).Hash.ToLowerInvariant()) { return $false }
        if ($Data.config_sha256 -ne (Get-FileHash -LiteralPath $Config -Algorithm SHA256).Hash.ToLowerInvariant()) { return $false }
    }
    return $true
}

try {
    Write-ExperimentLog "NEAT Discrete v2 experiment started: 3 sequential runs × 200 generations; TEST is UNUSED."
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Run Training\Setup-Venv.ps1 first." }
    if ($RebuildWorker -or -not (Test-Path -LiteralPath $Worker -PathType Leaf)) {
        Write-ExperimentLog "Research Worker build started."
        & (Join-Path $TrainingRoot "Build-ResearchWorker.ps1")
        Write-ExperimentLog "Research Worker build completed."
    }
    if (-not (Test-Path -LiteralPath $Worker -PathType Leaf)) { throw "Research Worker build is missing." }
    foreach ($Run in $Runs) {
        if ($SkipExisting -and (Test-CompletedRun $Run)) {
            Write-ExperimentLog "Run $($Run.RunId) is complete and verified; skipping."
            continue
        }
        Write-ExperimentLog "Run $($Run.RunId) started (seed $($Run.Seed), 200 generations)."
        $Parameters = @{ RunId = $Run.RunId; ExperimentSeed = $Run.Seed; TargetGenerations = 200 }
        if ($ComputeMatchSeconds -gt 0) { $Parameters.ComputeMatchSeconds = $ComputeMatchSeconds }
        if ($AllowDirty) { $Parameters.AllowDirty = $true }
        & $TrainingScript @Parameters
        if (-not (Test-CompletedRun $Run)) {
            throw "Run $($Run.RunId) failed or its artifacts did not pass verification."
        }
        Write-ExperimentLog "Run $($Run.RunId) completed; workers closed."
    }
    Write-ExperimentLog "Deduplicated 500-second validations started (maximum 9 unique policies)."
    Push-Location $TrainingRoot
    try {
        $FinalizeArguments = @("-m", "turbodash.neat_v2_finalize", "--worker-exe", $Worker, "--workers", 6, "--time-scale", 20)
        if ($SkipExisting) { $FinalizeArguments += "--skip-existing" }
        & $Python @FinalizeArguments
        if ($LASTEXITCODE -ne 0) { throw "NEAT v2 final validation/summary failed." }
    } finally {
        Pop-Location
    }
    $Stopwatch.Stop()
    Write-ExperimentLog ("NEAT Discrete v2 experiment completed in {0:N1} wall-clock seconds." -f $Stopwatch.Elapsed.TotalSeconds)
} catch {
    $Stopwatch.Stop()
    Write-ExperimentLog ("NEAT Discrete v2 experiment stopped after {0:N1} seconds: {1}" -f $Stopwatch.Elapsed.TotalSeconds, $_.Exception.Message)
    throw
}
