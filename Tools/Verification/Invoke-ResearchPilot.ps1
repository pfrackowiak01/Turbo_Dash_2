param(
    [ValidateSet('Smoke', 'Benchmark', 'Pilot')][string]$Plan = 'Benchmark',
    [ValidateSet(1, 5, 10, 20)][int]$TimeScale = 10,
    [string]$UnityPath = 'D:\Aplikacje\2022.3.4f1\Editor\Unity.exe',
    [int]$TimeoutSecondsPerRun = 1800
)
$ErrorActionPreference = 'Stop'
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$runRoot = Join-Path ([IO.Path]::GetTempPath()) ('TurboDash-Pilot-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $runRoot | Out-Null
Write-Output "Isolated project: $runRoot"
foreach ($folder in @('Assets', 'Packages', 'ProjectSettings')) {
    Copy-Item -LiteralPath (Join-Path $repoRoot $folder) -Destination $runRoot -Recurse
}
$packageCache = Join-Path $repoRoot 'Library/PackageCache'
if (Test-Path -LiteralPath $packageCache) {
    New-Item -ItemType Directory -Path (Join-Path $runRoot 'Library') | Out-Null
    Copy-Item -LiteralPath $packageCache -Destination (Join-Path $runRoot 'Library') -Recurse
}
$seedRoot = Join-Path $repoRoot 'Assets/Turbo_Dash/Research/Seeds'
$train = (Get-Content -Raw -LiteralPath (Join-Path $seedRoot 'train.json') | ConvertFrom-Json).seeds
$validation = (Get-Content -Raw -LiteralPath (Join-Path $seedRoot 'validation.json') | ConvertFrom-Json).seeds
$totalTimer = [Diagnostics.Stopwatch]::StartNew()

function Invoke-PublicBatch([string]$name, [string]$controller, [int[]]$seeds, [int]$scale, [double]$maxDuration = 300) {
    $csvPath = Join-Path $runRoot ($name + '.csv')
    $configPath = Join-Path $runRoot ($name + '.json')
    $logPath = Join-Path $runRoot ($name + '.log')
    $config = [ordered]@{
        protocolVersion = 1
        initialSeed = $seeds[0]
        episodeCount = $seeds.Count
        seeds = $seeds
        maxDuration = $maxDuration
        maxScore = 0
        simulationTimeScale = $scale
        controllerType = $controller
        enablePilotReward = $true
        csvPath = $csvPath
        autoAdvance = $true
    }
    $config | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $configPath -Encoding UTF8
    $arguments = @('-batchmode', '-projectPath', ('"' + $runRoot + '"'), '-executeMethod',
        'TurboDash.Research.Editor.ResearchMenu.RunBatch', '-turboResearchConfig', ('"' + $configPath + '"'),
        '-logFile', ('"' + $logPath + '"'))
    $timer = [Diagnostics.Stopwatch]::StartNew()
    $process = Start-Process -FilePath $UnityPath -ArgumentList $arguments -WindowStyle Hidden -PassThru
    $lastProgress = 0
    while (!$process.WaitForExit(1000)) {
        if ($timer.Elapsed.TotalSeconds -gt $TimeoutSecondsPerRun) {
            Stop-Process -Id $process.Id
            throw "Pilot batch timed out: $name. Log: $logPath"
        }
        if ($timer.Elapsed.TotalSeconds - $lastProgress -gt 30) {
            $lastProgress = $timer.Elapsed.TotalSeconds
            Write-Output ("Batch {0} is running ({1:N0}s)" -f $name, $lastProgress)
        }
    }
    if ($process.ExitCode -ne 0 -or !(Test-Path -LiteralPath $csvPath)) {
        if (Test-Path -LiteralPath $logPath) { Get-Content -LiteralPath $logPath -Tail 80 }
        throw "Public RunBatch failed: $name (exit $($process.ExitCode))."
    }
    $rows = @(Import-Csv -LiteralPath $csvPath)
    if ($rows.Count -ne $seeds.Count) { throw "Expected $($seeds.Count) rows, found $($rows.Count): $name" }
    if (@($rows | Where-Object { $_.protocolVersion -ne '1' -or $_.observationSchemaVersion -ne '2' -or $_.decisionInterval -ne '0.05' }).Count -ne 0) {
        throw "Protocol columns are invalid: $name"
    }
    Write-Output ("BATCH_RESULT name={0} controller={1} scale={2} episodes={3} wallSeconds={4:N3} csv={5}" -f
        $name, $controller, $scale, $rows.Count, $timer.Elapsed.TotalSeconds, $csvPath)
    return $csvPath
}

if ($Plan -eq 'Smoke') {
    Invoke-PublicBatch 'public-launcher-smoke' 'RuleBasedV1' ([int[]]@($train | Select-Object -First 3)) 20 .25
} elseif ($Plan -eq 'Benchmark') {
    $benchmarkSeed = [int[]]@($train | Select-Object -First 1)
    foreach ($scale in @(1, 5, 10, 20)) {
        Invoke-PublicBatch ("benchmark-rule-scale-" + $scale) 'RuleBasedV1' $benchmarkSeed $scale
    }
} else {
    Invoke-PublicBatch 'pilot-noaction-train-10' 'NoAction' ([int[]]@($train | Select-Object -First 10)) $TimeScale
    Invoke-PublicBatch 'pilot-rule-train-30' 'RuleBasedV1' ([int[]]@($train | Select-Object -First 30)) $TimeScale
    Invoke-PublicBatch 'pilot-rule-validation-20' 'RuleBasedV1' ([int[]]@($validation | Select-Object -First 20)) $TimeScale
}
Write-Output ("PILOT_RESULT plan={0} totalWallSeconds={1:N3} directory={2}" -f $Plan, $totalTimer.Elapsed.TotalSeconds, $runRoot)
