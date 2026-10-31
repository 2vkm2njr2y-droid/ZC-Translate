param(
    [switch]$IncludeModels,
    [switch]$Clean,
    [switch]$SkipBuild,
    [switch]$ResetData,
    [switch]$Release
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "== 组装免安装目录版 ==" -ForegroundColor Cyan
if (-not (Test-Path ".venv-runtime\Scripts\python.exe")) {
    throw "请先运行 scripts\setup_env.ps1 或 启动翻译器.bat。"
}

$dist = Join-Path $Root "dist\ZCTranslate"
$exe = Join-Path $dist "ZCTranslate.exe"

if (-not $SkipBuild) {
    Write-Host "== 构建 exe（PyInstaller --onedir）==" -ForegroundColor Cyan
    if (-not (Test-Path ".venv-runtime\Scripts\pyinstaller.exe")) {
        & .\.venv-runtime\Scripts\pip.exe install pyinstaller -i https://pypi.tuna.tsinghua.edu.cn/simple
    }

    $pyiArgs = @(
        "--noconfirm", "--windowed", "--onedir", "--name", "ZCTranslate",
        "--paths", ".",
        "--collect-all", "openvino",
        "--collect-all", "openvino_genai",
        "--collect-all", "openvino_tokenizers",
        "--collect-all", "webview",
        "--collect-all", "uvicorn",
        "--collect-all", "rapidocr",
        "--collect-all", "onnxruntime",
        "--collect-all", "pymupdf",
        "--collect-all", "PIL",
        "--collect-all", "docx",
        "--hidden-import", "webview.platforms.edgechromium",
        "--icon", "assets\zc-translate.ico",
        "--add-data", "app\frontend;frontend",
        "--add-data", "app\backend\resources;backend\resources",
        "app\desktop.py"
    )
    if ($Clean) { $pyiArgs = @("--clean") + $pyiArgs }
    & .\.venv-runtime\Scripts\pyinstaller.exe @pyiArgs
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller 构建失败，退出码：$LASTEXITCODE"
    }
} else {
    Write-Host "== 跳过 PyInstaller，复用现有 dist ==" -ForegroundColor Cyan
}

if (-not (Test-Path $exe)) {
    throw "未找到 $exe。请去掉 -SkipBuild 重新构建，或先运行 scripts\build_portable.ps1。"
}

# 只允许操作仓库自身的 dist\ZCTranslate，避免误删/误写。
$expectedDist = Join-Path $Root "dist\ZCTranslate"
$resolvedDist = (Resolve-Path $dist).Path
$resolvedExpectedDist = (Resolve-Path $expectedDist).Path
if ($resolvedDist -ne $resolvedExpectedDist) {
    throw "拒绝操作：$resolvedDist 不是预期目录 $resolvedExpectedDist"
}

$running = Get-Process -Name ZCTranslate -ErrorAction SilentlyContinue
if ($running) {
    throw "ZCTranslate 正在运行（PID: $($running.Id -join ', ')），请先退出应用再打包。"
}

if ($Release -and $IncludeModels) {
    throw "公开发行包不能包含模型：不要同时使用 -Release 和 -IncludeModels。"
}

if ($ResetData) {
    $dataDir = Join-Path $resolvedDist "data"
    if (Test-Path $dataDir) {
        $resolvedData = (Resolve-Path $dataDir).Path
        if ($resolvedData -ne (Join-Path $resolvedExpectedDist "data")) {
            throw "拒绝删除：$resolvedData 不是预期的 data 目录"
        }
        Remove-Item -LiteralPath $resolvedData -Recurse -Force
        Write-Host "已清除包内测试数据：$resolvedData" -ForegroundColor Yellow
    }
}

if ($IncludeModels) {
    Write-Host "复制模型（约 6.6 GB）..." -ForegroundColor Cyan
    $modelsTarget = Join-Path $resolvedDist "models"
    New-Item -ItemType Directory -Force -Path $modelsTarget | Out-Null
    Copy-Item "models\*" $modelsTarget -Recurse -Force
} else {
    Write-Host "未复制模型：包内不包含 models 目录，启动器会查找外部模型。" -ForegroundColor Yellow
}

New-Item -ItemType File -Force -Path (Join-Path $resolvedDist "portable.flag") | Out-Null

$copyFiles = @(
    @{ Source = "README.md"; Target = "README.md" },
    @{ Source = "README.en.md"; Target = "README.en.md" },
    @{ Source = "README.ja.md"; Target = "README.ja.md" },
    @{ Source = "README.ko.md"; Target = "README.ko.md" },
    @{ Source = "README.es.md"; Target = "README.es.md" },
    @{ Source = "LICENSE"; Target = "LICENSE" },
    @{ Source = "NOTICE"; Target = "NOTICE" },
    @{ Source = "THIRD_PARTY_NOTICES.md"; Target = "THIRD_PARTY_NOTICES.md" },
    @{ Source = "docs\licensing.md"; Target = "LICENSING.md" },
    @{ Source = "assets\zc-translate.ico"; Target = "zc-translate.ico" },
    @{ Source = "assets\zc-translate-icon.png"; Target = "zc-translate-icon.png" }
)
foreach ($item in $copyFiles) {
    if (Test-Path $item.Source) {
        Copy-Item $item.Source (Join-Path $resolvedDist $item.Target) -Force
    }
}

# 收集依赖的许可证原文。MIT / BSD / Apache-2.0 等许可证要求随二进制分发时
# 保留版权与许可声明；PyInstaller 默认只带 dist-info 元数据，不带这些文件。
$licenseRoot = Join-Path $resolvedDist "licenses"
if (Test-Path $licenseRoot) { Remove-Item -LiteralPath $licenseRoot -Recurse -Force }
New-Item -ItemType Directory -Force -Path $licenseRoot | Out-Null
$sitePackages = Join-Path $Root ".venv-runtime\Lib\site-packages"
if (Test-Path $sitePackages) {
    Get-ChildItem $sitePackages -Directory -Filter "*.dist-info" -ErrorAction SilentlyContinue | ForEach-Object {
        $packageName = $_.Name -replace '\.dist-info$', ''
        $dest = Join-Path $licenseRoot $packageName
        $licenseDir = Join-Path $_.FullName "licenses"
        if (Test-Path $licenseDir) {
            Copy-Item -LiteralPath $licenseDir -Destination $dest -Recurse -Force
        } else {
            $licenseFiles = Get-ChildItem $_.FullName -File -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -match '^(LICEN[CS]E|COPYING|NOTICE)' }
            if ($licenseFiles) {
                New-Item -ItemType Directory -Force -Path $dest | Out-Null
                $licenseFiles | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $dest -Force }
            }
        }
    }
}
Write-Host "已收集第三方许可证原文：$licenseRoot" -ForegroundColor Green

function Convert-ToCrlf([string]$text) {
    return ($text -replace "`r`n", "`n") -replace "`n", "`r`n"
}

# 便携启动器（ASCII，CRLF）；工作区模型回退路径在打包时写入。
$launcherTemplate = Join-Path $Root "scripts\portable-launcher.bat"
if (-not (Test-Path $launcherTemplate)) {
    throw "缺少启动器模板：$launcherTemplate"
}
$workspaceModels = Join-Path $Root "models"

# 直接双击 exe 时读取的模型指针；相对路径以包目录为基准。
# 本机 dist 始终保留可用的开发布局（指向工作区 models），
# 公开发行目录在下面单独复制并改写，避免破坏日常使用的 dist。
$pointerPath = Join-Path $resolvedDist "models-path.txt"
$pointerLines = @(
    "# Edit this file if the models folder moves. Relative paths resolve against this folder.",
    $workspaceModels
)
Set-Content -LiteralPath $pointerPath -Value $pointerLines -Encoding ASCII

$launcher = (Get-Content -Raw -Encoding ASCII $launcherTemplate).Replace(
    "__ZC_WORKSPACE_MODELS__", $workspaceModels
)
$launcherPath = Join-Path $resolvedDist "启动翻译器.bat"
Set-Content -LiteralPath $launcherPath -Value (Convert-ToCrlf $launcher) -Encoding ASCII -NoNewline

# 纯 ASCII 兜底启动器：避免中文文件名在非中文系统解压后乱码导致无法启动。
$asciiLauncher = @"
@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "ZC_MODELS_DIR="
if exist "%~dp0models\" set "ZC_MODELS_DIR=%~dp0models"
if not defined ZC_MODELS_DIR if exist "%~dp0..\models\" set "ZC_MODELS_DIR=%~dp0..\models"
if not defined ZC_MODELS_DIR if exist "%~dp0..\..\models\" set "ZC_MODELS_DIR=%~dp0..\..\models"
if not defined ZC_MODELS_DIR (
  echo [ZC] Models folder not found. Prepare models first - see README.
)
start "" "%~dp0ZCTranslate.exe" %*
"@
$asciiPath = Join-Path $resolvedDist "Start-ZCTranslate.bat"
Set-Content -LiteralPath $asciiPath -Value (Convert-ToCrlf $asciiLauncher) -Encoding ASCII -NoNewline

# 使用说明（UTF-8 BOM，CRLF）。
$usageSource = Join-Path $Root "docs\portable-usage.txt"
if (-not (Test-Path $usageSource)) {
    throw "缺少使用说明：$usageSource"
}
$usage = (Get-Content -Raw -Encoding UTF8 $usageSource).Replace(
    "__ZC_WORKSPACE_MODELS__", $workspaceModels
)
$usagePath = Join-Path $resolvedDist "使用说明.txt"
Set-Content -LiteralPath $usagePath -Value (Convert-ToCrlf $usage) -Encoding UTF8 -NoNewline

# 公开发行目录：复制一份再改写，dist 里的模型指针、data\ 与日志保持不变。
$releaseDist = $null
if ($Release) {
    $releaseDist = Join-Path $Root "build\release\ZCTranslate"
    $releaseParent = Split-Path $releaseDist -Parent
    if (Test-Path $releaseDist) { Remove-Item -LiteralPath $releaseDist -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $releaseParent | Out-Null
    # 只排除顶层 data\ 与 models\，不要用裸目录名（会误伤 rapidocr\models 等）。
    & robocopy $resolvedDist $releaseDist /MIR `
        /XD (Join-Path $resolvedDist "data") (Join-Path $resolvedDist "models") `
        /XF "*.log" /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "复制发行目录失败：robocopy exit $LASTEXITCODE" }
    foreach ($unexpected in @("data", "models")) {
        $path = Join-Path $releaseDist $unexpected
        if (Test-Path $path) { Remove-Item -LiteralPath $path -Recurse -Force }
    }

    $releasePointer = @(
        "# Put your models folder next to ZCTranslate.exe, or edit this path.",
        "# Relative paths resolve against this folder. See README for how to prepare models.",
        "models"
    )
    Set-Content -LiteralPath (Join-Path $releaseDist "models-path.txt") -Value $releasePointer -Encoding ASCII

    $releaseLauncher = (Get-Content -Raw -Encoding ASCII $launcherTemplate).Replace(
        "__ZC_WORKSPACE_MODELS__", ""
    )
    Set-Content -LiteralPath (Join-Path $releaseDist "启动翻译器.bat") `
        -Value (Convert-ToCrlf $releaseLauncher) -Encoding ASCII -NoNewline

    $releaseUsage = (Get-Content -Raw -Encoding UTF8 $usageSource).Replace(
        "__ZC_WORKSPACE_MODELS__", "models"
    )
    Set-Content -LiteralPath (Join-Path $releaseDist "使用说明.txt") `
        -Value (Convert-ToCrlf $releaseUsage) -Encoding UTF8 -NoNewline
}

$summaryDist = if ($Release -and $releaseDist) { $releaseDist } else { $resolvedDist }
$files = Get-ChildItem $summaryDist -Recurse -File
$total = ($files | Measure-Object Length -Sum).Sum
$hash = (Get-FileHash $exe -Algorithm SHA256).Hash

Write-Host "`n完成：$exe" -ForegroundColor Green
Write-Host ("包大小：{0:N1} MB，{1} 个文件" -f ($total / 1MB), $files.Count)
Write-Host "EXE SHA256：$hash"
Write-Host "本机可运行目录：$resolvedDist（模型指针 -> $workspaceModels，data\ 保留）"
if ($Release) {
    Write-Host "公开发行目录：$releaseDist" -ForegroundColor Yellow
    Write-Host "模式：已去除本机路径、data\ 与模型；打包 ZIP/安装包时使用发行目录。" -ForegroundColor Yellow
    Write-Host "模型：未包含；请把 models 放到包目录，或用 models-path.txt / --models-dir 指向。" -ForegroundColor Yellow
} elseif ($IncludeModels) {
    Write-Host "模型：已复制到 $resolvedDist\models" -ForegroundColor Yellow
} else {
    Write-Host "模型：未复制；启动器会查找 $workspaceModels 或 exe 旁的 models。" -ForegroundColor Yellow
}
Write-Host "启动：双击 $launcherPath"
