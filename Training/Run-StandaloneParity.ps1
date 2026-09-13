[CmdletBinding()]
param(
    [string]$UnityPath = "D:\Aplikacje\2022.3.4f1\Editor\Unity.exe",
    [string]$RunId = "parity-final",
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$TrainingRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $TrainingRoot
$Python = Join-Path $TrainingRoot ".venv\Scripts\python.exe"
$Worker = Join-Path $RepositoryRoot "Builds\ResearchWorker\TurboDashResearchWorker.exe"
$BuildCache = Join-Path ([IO.Path]::GetPathRoot($RepositoryRoot)) "Temp\TurboDash-ResearchWorker-BuildCache"
$Run = Join-Path $TrainingRoot "runs\$RunId"
if (Test-Path -LiteralPath $Run) { throw "Run directory exists: $Run" }
if (-not $SkipBuild) {
    & (Join-Path $TrainingRoot "Build-ResearchWorker.ps1") -UnityPath $UnityPath -Output $Worker
    if ($LASTEXITCODE -ne 0) { throw "Research Worker build failed." }
}
if (-not (Test-Path -LiteralPath $Worker -PathType Leaf)) { throw "Research Worker is missing: $Worker" }
if (-not (Test-Path -LiteralPath $BuildCache -PathType Container)) { throw "Editor build cache is missing; rerun without -SkipBuild." }
New-Item -ItemType Directory -Force -Path $Run | Out-Null
$Train = Get-Content -Raw (Join-Path $RepositoryRoot "Assets\Turbo_Dash\Research\Seeds\train.json") | ConvertFrom-Json
$Seeds = @($Train.seeds | Select-Object -First 5)
$Base = [ordered]@{
    protocolVersion = 1; initialSeed = [int]$Seeds[0]; episodeCount = 5; seeds = $Seeds
    # A bounded horizon compares runtime parity before tiny Update/FixedUpdate
    # ordering differences can push RuleBasedV1 onto a different long trajectory.
    maxDuration = 30.0; maxScore = 0.0; simulationTimeScale = 20.0
    controllerType = "RuleBasedV1"; enablePilotReward = $true
    pilotReward = @{ scoreScale = 0.01; lifeLossPenalty = 0.5 }
    ruleBased = @{
        wallCost = 14.0; obstacleCost = 11.0; movingCost = 3.0; approximateCost = 1.5
        neighbourRisk = 0.45; protectedRiskMultiplier = 0.2; shieldRiskMultiplier = 0.45
        outsideRiskMultiplier = 1.15; distanceUrgency = 2.5; heartAttraction = 7.0
        shieldAttraction = 4.0; boostAttraction = 2.0; steeringCost = 0.22
        reversalCost = 0.8; stayThreshold = 0.45
    }
    csvPath = ""; autoAdvance = $true
}
$EditorCsv = Join-Path $Run "editor.csv"
$StandaloneCsv = Join-Path $Run "standalone.csv"
$EditorConfig = Join-Path $Run "editor-config.json"
$StandaloneConfig = Join-Path $Run "standalone-config.json"
$Base.csvPath = $EditorCsv
$Base | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 $EditorConfig
$Base.csvPath = $StandaloneCsv
$Base | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 $StandaloneConfig

$EditorArgs = @("-batchmode", "-projectPath", ('"' + $BuildCache + '"'), "-executeMethod",
    "TurboDash.Research.Editor.ResearchMenu.RunBatch", "-turboResearchConfig", ('"' + $EditorConfig + '"'),
    "-logFile", ('"' + (Join-Path $Run "editor.log") + '"'))
$EditorProcess = Start-Process -FilePath $UnityPath -ArgumentList $EditorArgs -Wait -PassThru -WindowStyle Hidden
if ($EditorProcess.ExitCode -ne 0) { throw "Editor parity run failed with $($EditorProcess.ExitCode)." }

$StandaloneArgs = @("-batchmode", "-nographics", "-turboResearchConfig", ('"' + $StandaloneConfig + '"'),
    "-logFile", ('"' + (Join-Path $Run "standalone.log") + '"'))
$StandaloneProcess = Start-Process -FilePath $Worker -ArgumentList $StandaloneArgs -Wait -PassThru -WindowStyle Hidden
if ($StandaloneProcess.ExitCode -ne 0) { throw "Standalone parity run failed with $($StandaloneProcess.ExitCode)." }

Push-Location $TrainingRoot
try {
    & $Python -m turbodash.parity --editor $EditorCsv --standalone $StandaloneCsv --output (Join-Path $Run "parity.json")
    if ($LASTEXITCODE -ne 0) { throw "Parity comparison failed." }
} finally { Pop-Location }
