param(
    [ValidateSet('Baseline', 'Research')][string]$Mode = 'Research',
    [string]$UnityPath = 'D:\Aplikacje\2022.3.4f1\Editor\Unity.exe',
    [string]$Revision = '',
    [int]$TimeoutSeconds = 600
)
$ErrorActionPreference = 'Stop'
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$verificationRoot = Join-Path ([IO.Path]::GetTempPath()) ('TurboDash-' + $Mode + '-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $verificationRoot | Out-Null
Write-Output "Isolated project: $verificationRoot"
if ($Revision) {
    $archivePath = Join-Path $verificationRoot 'source.zip'
    & git -C $repoRoot archive --format=zip --output=$archivePath $Revision
    if ($LASTEXITCODE -ne 0) { throw 'Could not archive the requested revision.' }
    Expand-Archive -LiteralPath $archivePath -DestinationPath $verificationRoot
} else {
    foreach ($folder in @('Assets', 'Packages', 'ProjectSettings')) {
        Copy-Item -LiteralPath (Join-Path $repoRoot $folder) -Destination $verificationRoot -Recurse
    }
}
$version = Get-Content -LiteralPath (Join-Path $verificationRoot 'ProjectSettings/ProjectVersion.txt') -TotalCount 1
if ($version -ne 'm_EditorVersion: 2022.3.4f1') { throw "Unexpected project version: $version" }
# Optional read-only reuse of the installed package sources. Unity owns all generated
# output in this disposable copy; no original Library/ or open editor is changed.
$packageCache = Join-Path $repoRoot 'Library/PackageCache'
if (Test-Path -LiteralPath $packageCache) {
    New-Item -ItemType Directory -Path (Join-Path $verificationRoot 'Library') | Out-Null
    Copy-Item -LiteralPath $packageCache -Destination (Join-Path $verificationRoot 'Library') -Recurse
}
$arguments = @('-batchmode', '-projectPath', ('"' + $verificationRoot + '"'))
if ($Mode -eq 'Baseline') {
    New-Item -ItemType Directory -Path (Join-Path $verificationRoot 'Assets/Editor') -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'TurboDashBaselineProbe.cs') -Destination (Join-Path $verificationRoot 'Assets/Editor/TurboDashBaselineProbe.cs')
    $arguments += @('-executeMethod', 'TurboDashBaselineProbe.Run')
    $resultName = 'baseline-result.txt'
} else {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'TurboDashResearchProbe.cs') -Destination (Join-Path $verificationRoot 'Assets/TurboDashResearchProbe.cs')
    $configPath = Join-Path $verificationRoot 'research-config.json'
    @{ initialSeed = 12345; episodeCount = 3; maxDuration = 10; maxScore = 0; autoAdvance = $true;
        csvPath = (Join-Path $verificationRoot 'episodes.csv') } | ConvertTo-Json | Set-Content -LiteralPath $configPath -Encoding UTF8
    $arguments += @('-executeMethod', 'TurboDashResearchProbe.Run', '-turboVerifyResearch', '-turboResearchConfig', ('"' + $configPath + '"'))
    $resultName = 'research-result.txt'
}
$logPath = Join-Path $verificationRoot 'editor.log'
$arguments += @('-logFile', ('"' + $logPath + '"'))
$process = Start-Process -FilePath $UnityPath -ArgumentList $arguments -WindowStyle Hidden -PassThru
$timer = [Diagnostics.Stopwatch]::StartNew()
$lastProgress = 0
while (!$process.WaitForExit(1000)) {
    if ($timer.Elapsed.TotalSeconds -gt $TimeoutSeconds) {
        Stop-Process -Id $process.Id
        throw "Verification timed out. Log: $logPath"
    }
    if ($timer.Elapsed.TotalSeconds - $lastProgress -gt 30) {
        $lastProgress = $timer.Elapsed.TotalSeconds
        Write-Output ("Unity verification is running ({0:N0}s). Log: {1}" -f $lastProgress, $logPath)
    }
}
$resultPath = Join-Path $verificationRoot $resultName
if (Test-Path -LiteralPath $resultPath) { Get-Content -LiteralPath $resultPath }
if (!(Test-Path -LiteralPath $resultPath) -or !(Select-String -LiteralPath $resultPath -Pattern '^Failure: none$' -Quiet)) {
    throw "Verification failed. Log: $logPath"
}
Write-Output "Verification passed. Report: $resultPath"
