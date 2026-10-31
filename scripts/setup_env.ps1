$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Mirror = "https://pypi.tuna.tsinghua.edu.cn/simple"

Write-Host "== ZC 离线翻译：准备运行环境 ==" -ForegroundColor Cyan
$py = Get-Command py -ErrorAction SilentlyContinue
if (-not $py) {
    throw "未找到 Python 启动器。请先安装 Python 3.12（https://www.python.org/downloads/）。"
}
$version = & py -3.12 --version 2>$null
if (-not $version) {
    throw "未找到 Python 3.12。请安装后重试：winget install Python.Python.3.12"
}
Write-Host "Python: $version"

if (-not (Test-Path ".venv-runtime\Scripts\python.exe")) {
    Write-Host "`n[1/3] 创建运行时环境..." -ForegroundColor Cyan
    & py -3.12 -m venv .venv-runtime
}
& .\.venv-runtime\Scripts\python.exe -m pip install -U pip -i $Mirror
& .\.venv-runtime\Scripts\pip.exe install -r requirements.txt -r requirements-dev.txt -i $Mirror

if (-not (Test-Path ".venv-convert\Scripts\python.exe")) {
    Write-Host "`n[2/3] 创建模型转换环境..." -ForegroundColor Cyan
    & py -3.12 -m venv .venv-convert
}
& .\.venv-convert\Scripts\python.exe -m pip install -U pip -i $Mirror

Write-Host "`n[3/3] 安装转换工具（optimum-intel main 分支，支持 Hy-MT2）..." -ForegroundColor Cyan
if (-not (Test-Path "vendor\optimum-intel\.git")) {
    New-Item -ItemType Directory -Force -Path vendor | Out-Null
    & git clone --depth 1 https://github.com/huggingface/optimum-intel vendor\optimum-intel
}
& .\.venv-convert\Scripts\pip.exe install torch --index-url https://download.pytorch.org/whl/cpu
& .\.venv-convert\Scripts\pip.exe install transformers==5.6.2 optimum==2.3.0 nncf==3.4.0 `
    openvino==2026.4.1 openvino-tokenizers==2026.4.1.0 modelscope==1.40.2 -i $Mirror
& .\.venv-convert\Scripts\pip.exe install -e vendor\optimum-intel --no-deps

Write-Host "`n环境检查：" -ForegroundColor Cyan
& .\.venv-runtime\Scripts\python.exe -c "import openvino as ov; print('OpenVINO', ov.__version__, ov.Core().available_devices)"
& .\.venv-convert\Scripts\python.exe -c "import optimum.intel, transformers; print('optimum-intel', optimum.intel.__version__ if hasattr(optimum.intel,'__version__') else 'dev'); print('transformers', transformers.__version__)"
Write-Host "`n完成。下一步：运行 准备模型.bat，或直接运行 启动翻译器.bat。" -ForegroundColor Green
