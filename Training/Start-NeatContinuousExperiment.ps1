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
$TrainingScript = Join-Path $TrainingRoot "Start-NeatContinuousOvernight.ps1"
$Config = Join-Path $TrainingRoot "configs\neat_continuous_v1.json"
$LogPath = Join-Path $RunsRoot "neat-continuous-v1-experiment.log"
$PreflightId = "neat-continuous-v1-speciation-preflight"
$Stopwatch = [Diagnostics.Stopwatch]::StartNew()
$Runs = @(
    @{ RunId = "neat-continuous-v1-200g-run1"; Seed = 20260925 },
    @{ RunId = "neat-continuous-v1-200g-run2"; Seed = 20260926 },
    @{ RunId = "neat-continuous-v1-200g-run3"; Seed = 20260927 }
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
    $EffectiveConfigPath = Join-Path $Root "neat_config.ini"
    if (-not (Test-Path -LiteralPath $EffectiveConfigPath -PathType Leaf)) { return $false }
    $EffectiveConfig = Get-Content -Raw -Encoding UTF8 -LiteralPath $EffectiveConfigPath
    foreach ($Pattern in @(
        "(?m)^pop_size\s*=\s*64\s*$", "(?m)^num_inputs\s*=\s*236\s*$",
        "(?m)^num_outputs\s*=\s*1\s*$", "(?m)^feed_forward\s*=\s*True\s*$",
        "(?m)^initial_connection\s*=\s*partial_direct 0\.1(?:0)?\s*$",
        "(?m)^activation_default\s*=\s*tanh\s*$", "(?m)^aggregation_default\s*=\s*sum\s*$",
        "(?m)^node_add_prob\s*=\s*0\.05\s*$", "(?m)^node_delete_prob\s*=\s*0\.02\s*$",
        "(?m)^conn_add_prob\s*=\s*0\.2(?:0)?\s*$", "(?m)^conn_delete_prob\s*=\s*0\.1(?:0)?\s*$",
        "(?m)^weight_mutate_power\s*=\s*0\.5\s*$", "(?m)^weight_mutate_rate\s*=\s*0\.5\s*$",
        "(?m)^weight_replace_rate\s*=\s*0\.05\s*$", "(?m)^compatibility_threshold\s*=\s*2\.5\s*$",
        "(?m)^elitism\s*=\s*2\s*$", "(?m)^survival_threshold\s*=\s*0\.2(?:0)?\s*$"
    )) {
        if ($EffectiveConfig -notmatch $Pattern) { return $false }
    }
    if ($Manifest.status -ne "complete" -or $Manifest.algorithm -ne "NEAT Continuous v1" -or
        [int]$Manifest.pipeline_version -ne 2 -or $Manifest.configuration.action_space -ne "Continuous" -or
        $Manifest.configuration.name -ne "NEAT Continuous v1" -or
        [int]$Manifest.configuration.observation_size -ne 236 -or
        [int]$Manifest.configuration.population_size -ne 64 -or
        [int]$Manifest.configuration.episodes_per_genome -ne 2 -or
        [int]$Manifest.configuration.target_generations -ne 200 -or
        [int]$Manifest.configuration.outputs.Count -ne 1 -or
        $Manifest.configuration.outputs[0] -ne "STEERING" -or
        [double]$Manifest.configuration.speciation_preflight.compatibility_threshold -ne 2.5 -or
        $Manifest.configuration.speciation_preflight.initial_connection -ne "partial_direct" -or
        [double]$Manifest.configuration.speciation_preflight.connection_fraction -ne 0.10 -or
        [double]$Manifest.configuration.fitness.score_divisor -ne 100 -or
        [double]$Manifest.configuration.fitness.life_loss_penalty -ne 0.5 -or
        [int]$Manifest.configuration.experiment_seed -ne [int]$Run.Seed -or
        [int]$Manifest.result.generations_completed -ne 200 -or
        $Manifest.result.test_status -ne "UNUSED FOR TRAINING/TUNING/EVALUATION") { return $false }
    foreach ($Name in @("best_interaction_matched", "best_wallclock_matched", "best_200_generations")) {
        $Directory = Join-Path $Root "selected_models\$Name"
        $Genome = Join-Path $Directory "genome.pkl"
        $NeatConfig = Join-Path $Directory "config.ini"
        $Selection = Join-Path $Directory "selection.json"
        if (-not (Test-Path -LiteralPath $Genome -PathType Leaf) -or
            -not (Test-Path -LiteralPath $NeatConfig -PathType Leaf) -or
            -not (Test-Path -LiteralPath $Selection -PathType Leaf)) { return $false }
        $Data = Get-Content -Raw -Encoding UTF8 -LiteralPath $Selection | ConvertFrom-Json
        if ([int]$Data.topology.output_count -ne 1) { return $false }
        if ($Data.genome_sha256 -ne (Get-FileHash -LiteralPath $Genome -Algorithm SHA256).Hash.ToLowerInvariant()) { return $false }
        if ($Data.config_sha256 -ne (Get-FileHash -LiteralPath $NeatConfig -Algorithm SHA256).Hash.ToLowerInvariant()) { return $false }
    }
    return $true
}

try {
    Write-ExperimentLog "NEAT Continuous v1 experiment started: preflight plus 3 sequential runs x 200 generations; TEST is UNUSED."
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Run Training\Setup-Venv.ps1 first." }
    if ($RebuildWorker -or -not (Test-Path -LiteralPath $Worker -PathType Leaf)) {
        Write-ExperimentLog "Research Worker build started."
        & (Join-Path $TrainingRoot "Build-ResearchWorker.ps1")
        Write-ExperimentLog "Research Worker build completed."
    }
    if (-not (Test-Path -LiteralPath $Worker -PathType Leaf)) { throw "Research Worker build is missing." }
    Write-ExperimentLog "Continuous threshold preflight started at compatibility_threshold=2.5."
    Push-Location $TrainingRoot
    try {
        $PreflightArguments = @(
            "-m", "turbodash.neat_continuous_preflight", "--config", $Config,
            "--worker-exe", $Worker, "--run-id", $PreflightId,
            "--experiment-seed", 20260925, "--generations", 3,
            "--workers", 6, "--time-scale", 20, "--max-duration", 30
        )
        if ($AllowDirty) { $PreflightArguments += "--allow-dirty" }
        if ($SkipExisting) { $PreflightArguments += "--skip-existing" }
        & $Python @PreflightArguments
        if ($LASTEXITCODE -ne 0) { throw "NEAT Continuous speciation preflight failed." }
    } finally {
        Pop-Location
    }
    $PreflightReportPath = Join-Path $RunsRoot "$PreflightId\speciation-preflight.json"
    $PreflightReport = Get-Content -Raw -Encoding UTF8 -LiteralPath $PreflightReportPath | ConvertFrom-Json
    if (-not $PreflightReport.accepted -or [double]$PreflightReport.compatibility_threshold -ne 2.5) {
        throw "Threshold 2.5 was not accepted; do not start the main experiment."
    }
    Write-ExperimentLog ("Preflight accepted threshold 2.5; species history: {0}." -f ($PreflightReport.species_history -join " -> "))
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
        $FinalizeArguments = @("-m", "turbodash.neat_continuous_finalize", "--worker-exe", $Worker, "--workers", 6, "--time-scale", 20)
        if ($SkipExisting) { $FinalizeArguments += "--skip-existing" }
        & $Python @FinalizeArguments
        if ($LASTEXITCODE -ne 0) { throw "NEAT Continuous final validation/summary failed." }
    } finally {
        Pop-Location
    }
    $ValidationMapPath = Join-Path $RunsRoot "neat-continuous-v1-extended-validation-500\validation-map.json"
    $SummaryPath = Join-Path $RunsRoot "neat-continuous-v1-experiment-summary.json"
    $SummaryCsvPath = Join-Path $RunsRoot "neat-continuous-v1-experiment-summary.csv"
    if (-not (Test-Path -LiteralPath $ValidationMapPath -PathType Leaf) -or
        -not (Test-Path -LiteralPath $SummaryPath -PathType Leaf) -or
        -not (Test-Path -LiteralPath $SummaryCsvPath -PathType Leaf)) {
        throw "NEAT Continuous final artifacts are missing."
    }
    $ValidationMap = Get-Content -Raw -Encoding UTF8 -LiteralPath $ValidationMapPath | ConvertFrom-Json
    Write-ExperimentLog ("Extended validation completed: {0} requested selections, {1} unique validations." -f
        $ValidationMap.requested_selections, $ValidationMap.unique_validations)
    $Stopwatch.Stop()
    Write-ExperimentLog ("NEAT Continuous v1 experiment completed in {0:N1} wall-clock seconds." -f $Stopwatch.Elapsed.TotalSeconds)
} catch {
    $Stopwatch.Stop()
    Write-ExperimentLog ("NEAT Continuous v1 experiment stopped after {0:N1} seconds: {1}" -f $Stopwatch.Elapsed.TotalSeconds, $_.Exception.Message)
    throw
}
