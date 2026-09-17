[CmdletBinding()]
param(
    [string]$UnityPath = "D:\Aplikacje\2022.3.4f1\Editor\Unity.exe"
)

$ErrorActionPreference = "Stop"
$TrainingRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $TrainingRoot
$Python = Join-Path $TrainingRoot ".venv\Scripts\python.exe"
$Report = Join-Path $TrainingRoot "final_test\rulebased_parity_verification.json"
$TempRoot = Join-Path ([IO.Path]::GetPathRoot($RepositoryRoot)) "Temp"
$RunToken = [Guid]::NewGuid().ToString("N")
$Staging = Join-Path $TempRoot "TurboDash-RuleBased-Parity-$RunToken"
$Corpus = Join-Path $TempRoot "TurboDash-RuleBased-Parity-$RunToken.bin"
$UnityLog = Join-Path $TempRoot "TurboDash-RuleBased-Parity-$RunToken.log"

if (-not (Test-Path -LiteralPath $UnityPath -PathType Leaf)) { throw "Unity 2022.3.4f1 was not found: $UnityPath" }
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Project Python environment is missing: $Python" }
$ResolvedTemp = [IO.Path]::GetFullPath($TempRoot)
$ResolvedStaging = [IO.Path]::GetFullPath($Staging)
if (-not $ResolvedStaging.StartsWith($ResolvedTemp + [IO.Path]::DirectorySeparatorChar,
        [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to use a parity staging path outside the temporary root."
}

try {
    New-Item -ItemType Directory -Force -Path $ResolvedStaging | Out-Null
    Copy-Item -LiteralPath (Join-Path $RepositoryRoot "Assets") -Destination $ResolvedStaging -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $RepositoryRoot "Packages") -Destination $ResolvedStaging -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $RepositoryRoot "ProjectSettings") -Destination $ResolvedStaging -Recurse -Force

    $UnityArguments = @(
        "-batchmode", "-quit", "-projectPath", ('"' + $ResolvedStaging + '"'),
        "-executeMethod", "TurboDash.Research.Editor.RuleBasedParityCorpus.Generate",
        "--rulebased-parity-output", ('"' + $Corpus + '"'),
        "-logFile", ('"' + $UnityLog + '"')
    )
    $UnityProcess = Start-Process -FilePath $UnityPath -ArgumentList $UnityArguments -Wait -PassThru -WindowStyle Hidden
    if ($UnityProcess.ExitCode -ne 0) {
        throw "Unity C# parity oracle failed with exit code $($UnityProcess.ExitCode). Log: $UnityLog"
    }
    if (-not (Test-Path -LiteralPath $Corpus -PathType Leaf)) { throw "Unity did not create the parity corpus." }

    Push-Location $TrainingRoot
    try {
        & $Python -m turbodash.rulebased_parity --corpus $Corpus --report $Report --unity-version "2022.3.4f1"
        if ($LASTEXITCODE -ne 0) { throw "RuleBasedV1 differential parity comparison failed." }
    } finally {
        Pop-Location
    }
} finally {
    if (Test-Path -LiteralPath $ResolvedStaging) { Remove-Item -LiteralPath $ResolvedStaging -Recurse -Force }
    if (Test-Path -LiteralPath $Corpus) { Remove-Item -LiteralPath $Corpus -Force }
    if (Test-Path -LiteralPath $UnityLog) { Remove-Item -LiteralPath $UnityLog -Force }
}
