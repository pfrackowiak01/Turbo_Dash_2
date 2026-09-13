[CmdletBinding()]
param([int]$Port = 6006)

$ErrorActionPreference = "Stop"
$TrainingRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $TrainingRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Run Training\Setup-Venv.ps1 first." }
& $Python -m tensorboard.main --logdir (Join-Path $TrainingRoot "runs") --port $Port
