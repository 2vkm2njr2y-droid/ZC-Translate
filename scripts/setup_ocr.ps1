$ErrorActionPreference = "Stop"
$python = Join-Path $PSScriptRoot "..\.venv-runtime\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "找不到 .venv-runtime，请先运行 scripts\setup_env.ps1"
}
$mirror = $env:ZC_PIP_INDEX
if (-not $mirror) { $mirror = "https://pypi.tuna.tsinghua.edu.cn/simple" }
& $python -m pip install -i $mirror -r (Join-Path $PSScriptRoot "..\requirements-ocr.txt")
Write-Host "OCR 组件安装完成。首次运行 RapidOCR 可能需要准备本地模型文件。"
