[CmdletBinding()]
param(
    [switch]$RebuildWorker,
    [switch]$Resume,
    [ValidateRange(1, 64)]
    [int]$Workers = 6,
    [switch]$PreflightOnly
)

$ErrorActionPreference = "Stop"
$TrainingRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $TrainingRoot
$Python = Join-Path $TrainingRoot ".venv\Scripts\python.exe"
$Worker = Join-Path $RepositoryRoot "Builds\ResearchWorker\TurboDashResearchWorker.exe"

if ($Workers -ne 6) { throw "Final TEST protocol requires exactly -Workers 6." }
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Python environment is missing. Run Training\Setup-Venv.ps1 before the final TEST."
}
if ($RebuildWorker -or -not (Test-Path -LiteralPath $Worker -PathType Leaf)) {
    & (Join-Path $TrainingRoot "Build-ResearchWorker.ps1")
    if ($LASTEXITCODE -ne 0) { throw "Research Worker build failed." }
}
if (-not (Test-Path -LiteralPath $Worker -PathType Leaf)) { throw "Research Worker build is missing: $Worker" }

& $Python -c "import scipy, matplotlib; print('Analysis dependencies:', scipy.__version__, matplotlib.__version__)"
if ($LASTEXITCODE -ne 0) { throw "SciPy/Matplotlib are missing. Rerun Training\Setup-Venv.ps1." }

$Arguments = @(
    "-m", "turbodash.final_test_runner",
    "--worker-exe", $Worker,
    "--workers", $Workers,
    "--time-scale", 20
)
if ($Resume) { $Arguments += "--resume" }
if ($PreflightOnly) { $Arguments += "--preflight-only" }

Push-Location $TrainingRoot
try {
    & $Python @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Final TEST pipeline stopped with exit code $LASTEXITCODE." }
} finally {
    Pop-Location
}
