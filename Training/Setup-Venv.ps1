[CmdletBinding()]
param(
    [string]$Python = "py",
    [string]$PythonVersion = "-3.11"
)

$ErrorActionPreference = "Stop"
$TrainingRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $TrainingRoot ".venv"

if ($Python -eq "py") {
    & $Python $PythonVersion -c "import sys; assert sys.version_info[:2] == (3, 11); print(sys.executable)"
    if ($LASTEXITCODE -ne 0) { throw "Python 3.11 x64 is required. Install it, then rerun this script." }
    & $Python $PythonVersion -m venv $Venv
} else {
    & $Python -c "import sys; assert sys.version_info[:2] == (3, 11); print(sys.executable)"
    if ($LASTEXITCODE -ne 0) { throw "The selected interpreter is not Python 3.11." }
    & $Python -m venv $Venv
}
if ($LASTEXITCODE -ne 0) { throw "Creating the Python environment failed." }

$VenvPython = Join-Path $Venv "Scripts\python.exe"
& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }
& $VenvPython -m pip install -r (Join-Path $TrainingRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }
& $VenvPython -m pip freeze --all | Set-Content -Encoding utf8 (Join-Path $TrainingRoot "requirements-lock.txt")
& $VenvPython -c "import stable_baselines3 as s; assert s.__version__ == '2.9.0'; print('stable-baselines3', s.__version__)"
if ($LASTEXITCODE -ne 0) { throw "Stable-Baselines3 verification failed." }
Write-Host "Environment ready: $Venv"
