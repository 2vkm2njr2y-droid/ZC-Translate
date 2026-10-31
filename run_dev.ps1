$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
if (-not (Test-Path ".venv-runtime\Scripts\python.exe")) {
    & "$PSScriptRoot\setup_env.ps1"
}
& .\.venv-runtime\Scripts\python.exe app\desktop.py --dev @args
